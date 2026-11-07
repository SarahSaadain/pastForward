#!/usr/bin/env bash
# Rebuild the two mini screening databases of the tier-1 test set from pinned NCBI accessions:
#   ecmsd_mini/       the 3 files pastForward checks for (masked taxid-named mitogenomes + taxdump)
#   centrifuge_mini/  mini.{1,2,3}.cf, set as centrifuge.settings.index in .test/config/config.yaml
# Needs curl, unzip, python3, bbmask.sh (in the ECMSD env, workflow/envs/ecmsd.yaml) and
# centrifuge-build (build it with the env from workflow/envs/centrifuge.yaml: the index format can
# change between Centrifuge versions). Both must be on PATH.
set -euo pipefail
R="$(cd "$(dirname "$0")" && pwd)"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT

efetch() { # efetch <accession.version> [<start> <stop>]
  curl -sSf --retry 3 "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&rettype=fasta&retmode=text&id=$1${2:+&seq_start=$2&seq_stop=$3}" |
    awk '!/^>/{printf "%s", $0} END{print ""}'
  sleep 0.4
}

# ECMSD: mitogenomes named by bare taxid, as ECMSD's renameFASTA_taxid.py writes them.
# Target D. melanogaster, two close relatives, the human spike-in and three mammal decoys.
mkdir -p "$R/ecmsd_mini/NCBI_taxdump"
while read -r acc taxid; do
  printf ">%s\n%s\n" "$taxid" "$(efetch "$acc")"
done >"$W/mito.fna" <<EOF
NC_024511.2 7227
NC_005781.1 7240
NC_001322.1 7245
NC_012920.1 9606
NC_005089.1 10090
NC_006853.1 9913
NC_000845.1 9823
EOF
bbmask.sh -Xmx1g in="$W/mito.fna" out="$W/mito_masked.fna" overwrite=t 2>"$W/bbmask.log"
gzip -9nc "$W/mito_masked.fna" >"$R/ecmsd_mini/mitochondrion_refseq_taxid_masked.fna.gz"

# Centrifuge: the reference pieces plus both spike-ins, one taxid each.
while read -r name taxid acc start stop; do
  printf ">%s\n%s\n" "$name" "$(efetch "$acc" $start $stop)"
  printf "%s\t%s\n" "$name" "$taxid" >>"$W/seqid2taxid.tsv"
done >"$W/centrifuge.fa" <<EOF
dmel_chr4 7227 NC_004353.4 420001 720000
dmel_mito 7227 NC_024511.2
wolbachia_wmel 163164 NC_002978.6 100001 150000
ecoli_k12 562 NC_000913.3 1000001 1100000
human_mito 9606 NC_012920.1
EOF

# Taxonomy (pinned monthly NCBI archive), pruned to the ancestors of every taxid above up to root 1.
curl -sSf -o "$W/taxdmp.zip" https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump_archive/taxdmp_2026-11-01.zip
unzip -q "$W/taxdmp.zip" nodes.dmp names.dmp -d "$W"
python3 - "$W" "$R/ecmsd_mini/NCBI_taxdump" 7227 7240 7245 9606 10090 9913 9823 163164 562 <<'EOF'
import sys
src, dst, *taxids = sys.argv[1:]
parent = {}
for line in open(f"{src}/nodes.dmp"):
    f = line.split("\t|\t")
    parent[f[0]] = f[1]
keep = set()
for t in taxids:
    while t not in keep:
        keep.add(t)
        t = parent[t]
with open(f"{dst}/nodes.dmp", "w") as out:
    out.writelines(l for l in open(f"{src}/nodes.dmp") if l.split("\t|\t")[0] in keep)
with open(f"{dst}/names.dmp", "w") as out:
    out.writelines(l for l in open(f"{src}/names.dmp")
                   if l.split("\t|\t")[0] in keep and "scientific name" in l)
EOF

mkdir -p "$R/centrifuge_mini"
centrifuge-build -p 4 --seed 1 --ftabchars 6 --conversion-table "$W/seqid2taxid.tsv" \
  --taxonomy-tree "$R/ecmsd_mini/NCBI_taxdump/nodes.dmp" --name-table "$R/ecmsd_mini/NCBI_taxdump/names.dmp" \
  "$W/centrifuge.fa" "$R/centrifuge_mini/mini" >"$W/centrifuge-build.log"

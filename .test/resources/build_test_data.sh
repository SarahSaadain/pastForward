#!/usr/bin/env bash
# Rebuild the whole tier-1 test set in .test/ from pinned public sequences:
# reference, TE library, SCGs, simulated reads (simulate_reads.py) and both mini databases
# (build_mini_dbs.sh). Needs curl and python3 here, plus what build_mini_dbs.sh lists.
# The built files are committed, so a test run never needs this script or the network.
set -euo pipefail
T="$(cd "$(dirname "$0")/.." && pwd)"
R="$T/resources"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT

# efetch <accession.version> [<start> <stop>]: one sequence as FASTA, sequence on one line.
efetch() {
  curl -sSf --retry 3 "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&rettype=fasta&retmode=text&id=$1${2:+&seq_start=$2&seq_stop=$3}" |
    awk '!/^>/{printf "%s", $0} END{print ""}'
  sleep 0.4 # NCBI allows 3 requests per second without an API key
}
mkdir -p "$T"/Dmel/input/{read_module,reference_module,reveal_module/scg,reveal_module/feature_library}
fa() { echo ">$1"; fold -w 70 <<<"$2"; } # fa <name> <sequence>

chr4=$(efetch NC_004353.4 420001 720000) # 300 kb of D. melanogaster chr4
mito=$(efetch NC_024511.2)               # D. melanogaster mitogenome
wmel=$(efetch NC_002978.6 100001 150000) # 50 kb of Wolbachia wMel
{ fa chr4 "$chr4"; fa mito "$mito"; fa wolbachia "$wmel"; } >"$T/Dmel/input/reference_module/dmel_mini.fa"

# SCGs: four 5 kb chr4 chunks with no TE hit and no second BLAST hit (e<1e-5) in the slice.
i=0
for start in 45000 110000 165000 235000; do
  i=$((i + 1))
  fa "scg$i" "${chr4:start:5000}"
done >"$T/Dmel/input/reveal_module/scg/scg_mini.fa"

# Three real D. melanogaster TE consensus sequences, headers cut to the family name.
curl -sSf https://raw.githubusercontent.com/bergmanlab/drosophila-transposons/9b28cdbe9d2b3ef895df37f8495b33104677e516/current/D_mel_transposon_sequence_set.fa |
  awk '/^>/{split(substr($1,2),a,"#"); keep=(a[1]=="jockey"||a[1]=="opus"||a[1]=="roo"); if(keep) print ">"a[1]; next} keep' \
    >"$T/Dmel/input/reveal_module/feature_library/te_mini.fa"

# Spike-ins for HistA only: human mitogenome (ECMSD control), 100 kb of E. coli K-12 (Centrifuge control).
fa human_mito "$(efetch NC_012920.1)" >"$W/human_mito.fa"
fa ecoli "$(efetch NC_000913.3 1000001 1100000)" >"$W/ecoli.fa"

python3 "$R/simulate_reads.py" "$T/Dmel/input/reference_module/dmel_mini.fa" \
  "$T/Dmel/input/reveal_module/feature_library/te_mini.fa" "$W/human_mito.fa" "$W/ecoli.fa" \
  "$T/Dmel/input/read_module"

"$R/build_mini_dbs.sh"

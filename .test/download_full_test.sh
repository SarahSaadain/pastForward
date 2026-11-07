#!/usr/bin/env bash
# Tier 2 test data: real historical Dmel reads, downloaded into a ready pastForward project root.
#
# Usage: .test/download_full_test.sh [TARGET_DIR]      (default: .test/full)
#        N=200000 .test/download_full_test.sh /scratch/pf_full
#
# Reads: Shpak et al. 2023 (PRJNA945389), two 1800s museum specimens (supplement Table S1):
#   SL04  Dmel1800s-1, early 1800s, Sweden (Lund)    SRR23876564
#   GP9   Dmel1800s-2, mid 1800s, Germany (Passau)   SRR23876562
# Both runs are paired-end NovaSeq, 2 x 151 bp. Only the first N read pairs (default 1,000,000)
# are streamed from ENA with head, so the full runs (8-10 GB per file) are never downloaded.
# ENA can't give an md5 for a subset, so the md5 of the *uncompressed* subset is pinned below
# Streaming is deterministic. Compressed bytes are not, because they depend on the local gzip.
# Only N=20000 and the default N have a pinned md5. Other N values get a line-count check only.
#
# Then run from TARGET_DIR:  ./pastForward check && ./pastForward run --cores <N>
# ECMSD and Centrifuge download their databases into TARGET_DIR/resources on the first run
# (ECMSD 5-10 GB peak, Centrifuge index 7.9 GB). To skip them, set both
# pipeline.read_module.taxonomic_screening.tools.{ecmsd,centrifuge}.execute to false in
# TARGET_DIR/config/config.yaml. BUSCO also downloads drosophilidae_odb12 (a few hundred MB).
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
ROOT=${1:-$REPO/.test/full}
N=${N:-1000000}
ENA=https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR238
REF_URL=https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/001/215/GCF_000001215.4_Release_6_plus_ISO1_MT/GCF_000001215.4_Release_6_plus_ISO1_MT_genomic.fna.gz
REF_MD5=869cf40e4f5c7ca27d04ca9ae7baee4f # NCBI md5checksums.txt, of the .fna.gz
TE_URL=https://raw.githubusercontent.com/bergmanlab/drosophila-transposons/9b28cdbe9d2b3ef895df37f8495b33104677e516/current/D_mel_transposon_sequence_set.fa
TE_MD5=4f941649e09d2bd0ba8feae96d69bcdd # md5 of the raw file at this commit

# md5 of the uncompressed subset, "<file>:<N>" -> md5. Other N values skip the md5 check.
md5_for() {
    case "$1:$2" in
        SL04_R1:20000) echo 8295abf87fa0ab5830cb390a01289b03 ;;
        SL04_R2:20000) echo 364580011ab6de84be6103fa0d10d3c9 ;;
        GP9_R1:20000) echo a0286f4667681c3e24ca467897289e14 ;;
        GP9_R2:20000) echo 5aac430e02db0a907cff1bfa2c54e002 ;;
        SL04_R1:1000000) echo e16852147bdadbc7c8ffbf2338a6abcd ;;
        SL04_R2:1000000) echo 2330c51644a0cef30326ecfbcd232241 ;;
        GP9_R1:1000000) echo 192c4cb538e7f26cb412d71b8f6afda1 ;;
        GP9_R2:1000000) echo acadfb29537dc14d606d8ba812e32d97 ;;
        *) echo "" ;;
    esac
}

md5of() { if command -v md5sum >/dev/null; then md5sum | cut -d' ' -f1; else command md5 -q; fi; }

# Keep the first N records of one ENA file. Done when the line count (and md5, if pinned) match.
fetch_subset() { # <name> <ena path>
    local out=$READS/$1.fastq.gz want; want=$(md5_for "$1" "$N")
    if [[ -s $out ]] && [[ $(gzip -dc "$out" | wc -l | tr -d ' ') == $((4 * N)) ]]; then
        [[ -z $want || $(gzip -dc "$out" | md5of) == "$want" ]] && { echo "ok    $1"; return; }
    fi
    echo "fetch $1 (first $N reads of $ENA/$2)"
    [[ -n $want ]] || echo "note  no pinned md5 for N=$N, checking the line count only"
    # head closes the pipe early, so curl/gzip die of SIGPIPE (stderr muted): the line count check catches real failures.
    { curl -sSfL "$ENA/$2" 2>/dev/null | gzip -dc | head -n $((4 * N)) || true; } | gzip -n > "$out.part"
    local got; got=$(gzip -dc "$out.part" | wc -l | tr -d ' ')
    [[ $got == $((4 * N)) ]] || { echo "ERROR: $1 has $got lines, want $((4 * N)) (network, or N > run size)" >&2; exit 1; }
    [[ -z $want || $(gzip -dc "$out.part" | md5of) == "$want" ]] || { echo "ERROR: md5 mismatch for $1" >&2; exit 1; }
    mv "$out.part" "$out"
}

fetch_fasta() { # <out .fa> <url> <md5 of the downloaded file>
    [[ -s $1 ]] && { echo "ok    $(basename "$1")"; return; }
    echo "fetch $2"
    curl -sSfL "$2" -o "$1.dl"
    [[ $(md5of < "$1.dl") == "$3" ]] || { echo "ERROR: md5 mismatch for $2" >&2; exit 1; }
    if [[ $2 == *.gz ]]; then gzip -dc "$1.dl" > "$1.part"; rm "$1.dl"; else mv "$1.dl" "$1.part"; fi
    mv "$1.part" "$1"
}

echo "pastForward tier 2 test data -> $ROOT (N=$N read pairs per sample)"
echo "WARNING: a full run needs ~25 GB free disk for ECMSD/Centrifuge/BUSCO databases and several hours."
READS=$ROOT/Dmel/input/read_module
mkdir -p "$READS" "$ROOT/Dmel/input/reference_module" "$ROOT/Dmel/input/reveal_module/feature_library" "$ROOT/config"
[[ -e $ROOT/config/config.yaml ]] || cp "$REPO/.test/full/config/config.yaml" "$ROOT/config/config.yaml"
[[ -e $ROOT/workflow && ! -L $ROOT/workflow ]] && { echo "ERROR: $ROOT/workflow is a real folder, not a link to $REPO/workflow" >&2; exit 1; }
ln -sfn "$REPO/workflow" "$ROOT/workflow"
ln -sfn "$REPO/pastForward" "$ROOT/pastForward"

fetch_subset SL04_R1 064/SRR23876564/SRR23876564_1.fastq.gz
fetch_subset SL04_R2 064/SRR23876564/SRR23876564_2.fastq.gz
fetch_subset GP9_R1 062/SRR23876562/SRR23876562_1.fastq.gz
fetch_subset GP9_R2 062/SRR23876562/SRR23876562_2.fastq.gz
fetch_fasta "$ROOT/Dmel/input/reference_module/GCF_000001215.4_Release_6_plus_ISO1_MT_genomic.fna" "$REF_URL" "$REF_MD5"
fetch_fasta "$ROOT/Dmel/input/reveal_module/feature_library/Dmel_TE.fa" "$TE_URL" "$TE_MD5"

echo "Done. Next: cd $ROOT && ./pastForward check && ./pastForward run --cores <N>"

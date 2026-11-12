#!/usr/bin/env bash
# =================================================================================================
# Runs the synthetic project twice, once with the code at <git-ref> and once with this working
# tree (uncommitted changes included), then compares the requested output files and the
# per-rule benchmarks. Use it to show that a change keeps outputs identical, or to time it.
#
# Each run gets its own copy of tests/integration/synthetic_project/ in a temp dir, without
# processed/ or results/, so every target is built fresh. The two runs share one conda prefix
# (PF_CONDA_PREFIX, default ~/.snakemake/pf_conda), so envs are built only once.
#
# Requirements: the snakemake conda env activated (PATH alone breaks the job envs), rsync, git.
#
# Usage (from anywhere):
#   tests/integration/compare_with_ref.sh [--cores N] [--keep] <git-ref> [<target>...]
#     <target>  a path relative to the project dir, e.g.
#               Dmel/processed/reference_module/dmel_mini/mapped/HistA_dmel_mini_sorted_dedupped.bam
#               No targets: both runs build everything, and only benchmarks are compared.
#     --keep    keep the temp dir (and the ref worktree) and print its path
#
# Comparison: .bam by sorted SAM records (on a difference, it says which fields differ),
# .json with sorted keys and "version" lines dropped, anything else byte for byte.
#
# Known noise: mapDamage's MCMC model fit is random. Rescaled BAMs from two runs differ in a few
# base qualities (field 11) and the MR tag even when the code is the same. To test a rescale
# change, rescale both with the same Stats_out_MCMC_correct_prob.csv (mapDamage --rescale-only).
# =================================================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT="$REPO_ROOT/tests/integration/synthetic_project"
CONDA_PREFIX_DIR="${PF_CONDA_PREFIX:-$HOME/.snakemake/pf_conda}"
CORES=2
KEEP=0

while [ $# -gt 0 ]; do
  case "$1" in
    --cores) CORES="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) break ;;
  esac
done
[ $# -ge 1 ] || { echo "usage: $0 [--cores N] [--keep] <git-ref> [<target>...]" >&2; exit 2; }
REF="$1"; shift
TARGETS=("$@")

command -v snakemake >/dev/null || { echo "ERROR: snakemake not on PATH. Run: conda activate snakemake" >&2; exit 2; }
git -C "$REPO_ROOT" rev-parse --verify -q "$REF^{commit}" >/dev/null || { echo "ERROR: unknown git ref: $REF" >&2; exit 2; }

W="$(mktemp -d -t pf_compare.XXXXXX)"
cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    echo ""
    echo "Kept: $W  (remove with: git -C $REPO_ROOT worktree remove --force $W/ref_code; rm -rf $W)"
  else
    git -C "$REPO_ROOT" worktree remove --force "$W/ref_code" 2>/dev/null
    rm -rf "$W"
  fi
}
trap cleanup EXIT

git -C "$REPO_ROOT" worktree add -q --detach "$W/ref_code" "$REF" || exit 1
for v in ref new; do
  rsync -a --exclude .snakemake --exclude processed --exclude results "$PROJECT/" "$W/proj_$v/"
done

for v in ref new; do
  code="$W/ref_code"; [ "$v" = new ] && code="$REPO_ROOT"
  echo "Running $v code ($( [ "$v" = ref ] && echo "$REF" || echo "working tree")), log: $W/run_$v.log"
  if ! (cd "$W/proj_$v" && snakemake -s "$code/workflow/Snakefile" --cores "$CORES" \
      --software-deployment-method conda --conda-prefix "$CONDA_PREFIX_DIR" \
      --rerun-trigger mtime --notemp ${TARGETS[@]+"${TARGETS[@]}"} >"$W/run_$v.log" 2>&1); then
    echo "ERROR: $v run failed. Last lines of $W/run_$v.log:" >&2
    tail -20 "$W/run_$v.log" >&2
    KEEP=1
    exit 1
  fi
done

SAMTOOLS="$(command -v samtools || ls "$CONDA_PREFIX_DIR"/*/bin/samtools 2>/dev/null | head -1)"

echo ""
echo "== Outputs"
ndiff=0
for t in ${TARGETS[@]+"${TARGETS[@]}"}; do
  a="$W/proj_ref/$t"; b="$W/proj_new/$t"
  if [ ! -e "$a" ] || [ ! -e "$b" ]; then echo "MISSING  $t"; ndiff=$((ndiff + 1)); continue; fi
  case "$t" in
    *.bam)
      [ -n "$SAMTOOLS" ] || { echo "ERROR: no samtools on PATH or in $CONDA_PREFIX_DIR" >&2; exit 2; }
      "$SAMTOOLS" view "$a" | sort >"$W/a.sam"; "$SAMTOOLS" view "$b" | sort >"$W/b.sam"
      if cmp -s "$W/a.sam" "$W/b.sam"; then
        echo "SAME     $t ($(wc -l <"$W/a.sam") reads)"
      else
        ndiff=$((ndiff + 1))
        fields=""
        for f in 1-9 10 11 12-; do
          cmp -s <(cut -f"$f" "$W/a.sam" | sort) <(cut -f"$f" "$W/b.sam" | sort) || fields="$fields $f"
        done
        echo "DIFF     $t (reads $(wc -l <"$W/a.sam") vs $(wc -l <"$W/b.sam"), $(diff "$W/a.sam" "$W/b.sam" | grep -c '^<') records differ, fields:$fields)"
      fi ;;
    *.json)
      if diff -q <(python3 -m json.tool --sort-keys "$a" | grep -v version) \
                 <(python3 -m json.tool --sort-keys "$b" | grep -v version) >/dev/null; then
        echo "SAME     $t"
      else echo "DIFF     $t"; ndiff=$((ndiff + 1)); fi ;;
    *)
      if cmp -s "$a" "$b"; then echo "SAME     $t"; else echo "DIFF     $t"; ndiff=$((ndiff + 1)); fi ;;
  esac
done

echo ""
echo "== Benchmarks (seconds, max RSS in MB; n = jobs of that rule)"
python3 - "$W" <<'EOF'
import collections, glob, json, sys

w = sys.argv[1]
stats = {}
for v in ("ref", "new"):
    by = collections.defaultdict(list)
    for f in glob.glob(f"{w}/proj_{v}/**/*.benchmark.jsonl", recursive=True):
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                by[r["rule_name"]].append(r)
    stats[v] = by


def cell(rs):
    if not rs:
        return f"{'-':>27}"
    s = [r["s"] for r in rs]
    rss = max(r.get("max_rss") or 0 for r in rs)
    return f"n={len(rs):<3} sum={sum(s):7.1f} max={max(s):7.1f} {rss:5.0f}"


print(f"{'rule':44} {'ref':>36} | {'new':>36}")
for rule in sorted(set(stats["ref"]) | set(stats["new"])):
    print(f"{rule[:44]:44} {cell(stats['ref'][rule]):>36} | {cell(stats['new'][rule]):>36}")
EOF
for v in ref new; do echo "$v: $(grep -m1 'Elapsed' "$W/run_$v.log" || echo 'no elapsed time in log')"; done

[ "$ndiff" -eq 0 ]

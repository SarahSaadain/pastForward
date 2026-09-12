#!/usr/bin/env bash
# =================================================================================================
# Repeatable Snakemake-level integration checks for the configurable species data locations
# feature (species_dir/reads_dir/.../processed_dir/results_dir + the cross-project lock).
#
# Complements tests/test_species_paths.py (pure-Python, no Snakemake needed) by driving the real
# `snakemake` CLI against throwaway project directories, so it also catches anything that only
# shows up when Snakemake itself parses initialize.smk and builds the DAG - e.g. rule/wildcard
# resolution through the symlinks, or Snakemake's own dry-run/onsuccess hook timing.
#
# Requirements: a conda environment named "snakemake" (see config/README.md). Nothing in the real
# repo is modified - each scenario runs in its own temp directory that only symlinks workflow/.
#
# Usage:
#   tests/dryrun_scenarios.sh            # run all scenarios, clean up afterwards
#   tests/dryrun_scenarios.sh --keep     # keep the scenario workspace for inspection, print its path
# =================================================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ENV="snakemake"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

# macOS ships BSD coreutils, which has no `timeout`; GNU coreutils (`brew install coreutils`)
# installs it prefixed as `gtimeout` to avoid clobbering the BSD tools.
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD="gtimeout"
else
  echo "ERROR: no 'timeout' or 'gtimeout' on PATH. On macOS: brew install coreutils." >&2
  exit 2
fi

PASS_COUNT=0
FAIL_COUNT=0
FAILED_NAMES=()

pass() { echo "PASS  $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "FAIL  $1"; echo "      $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); FAILED_NAMES+=("$1"); }

WORKDIR="$(mktemp -d -t pf_dryrun_scenarios.XXXXXX)"
cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    echo ""
    echo "Scenario workspace kept at: $WORKDIR"
  else
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

# -------------------------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------------------------
make_project() {  # make_project <dir>
  mkdir -p "$1/config"
  ln -s "$REPO_ROOT/workflow" "$1/workflow"
}

make_species_root() {  # make_species_root <root_dir>
  mkdir -p "$1/input/read_module" "$1/input/reference_module" \
           "$1/input/reveal_module/scg" "$1/input/reveal_module/feature_library" \
           "$1/input/reveal_module/competition" "$1/processed" "$1/results"
}

make_fake_data() {  # make_fake_data <species_root_dir_containing_input/>
  printf '>chr1\nACGTACGTACGTACGTACGTACGTACGTACGT\n' > "$1/input/reference_module/genome.fasta"
  printf '@r\nACGTACGTACGTACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIIIIIIIIIIIIIII\n' | gzip > "$1/input/read_module/IND001_R1.fastq.gz"
  printf '@r\nACGTACGTACGTACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIIIIIIIIIIIIIII\n' | gzip > "$1/input/read_module/IND001_R2.fastq.gz"
}

job_total() {  # job_total <dryrun_log_file> - the "total   N" line from Snakemake's job stats table
  # Snakemake's console + logger handlers both print the summary table, so the line appears
  # twice in the log (plain, then timestamp-prefixed) - take the first match only.
  grep -E "^total[[:space:]]" "$1" | head -1 | awk '{print $2}'
}

run_dryrun() {  # run_dryrun <project_dir> <log_file> -> sets $DRYRUN_EXIT
  ( cd "$1" && "$TIMEOUT_CMD" 120 snakemake --cores 4 --dryrun > "$2" 2>&1 )
  DRYRUN_EXIT=$?
}

# -------------------------------------------------------------------------------------------
# Activate the snakemake conda environment
# -------------------------------------------------------------------------------------------
if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found on PATH." >&2
  exit 2
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
  echo "ERROR: conda environment '$CONDA_ENV' not found. Create it per config/README.md (Snakemake >= 9.9.0)." >&2
  exit 2
fi
conda activate "$CONDA_ENV"

echo "Repo:      $REPO_ROOT"
echo "Workspace: $WORKDIR"
echo "Snakemake: $(snakemake --version)"
echo ""

# =============================================================================================
# Scenario 1: default / fallback - no config overrides -> zero behavior change
# =============================================================================================
S1="$WORKDIR/1_default"
make_project "$S1"
cat > "$S1/config/config.yaml" <<'EOF'
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
EOF
mkdir -p "$S1/Dmel"
make_species_root "$S1/Dmel"
make_fake_data "$S1/Dmel"

run_dryrun "$S1" "$S1/dryrun.log"
if [ "$DRYRUN_EXIT" -eq 0 ]; then
  pass "1a: default layout dry-run succeeds"
else
  fail "1a: default layout dry-run succeeds" "exit code $DRYRUN_EXIT, see $S1/dryrun.log"
fi
if find "$S1/Dmel" -type l | grep -q .; then
  fail "1b: no symlinks created when nothing is configured" "found: $(find "$S1/Dmel" -type l)"
else
  pass "1b: no symlinks created when nothing is configured"
fi
S1_JOBS="$(job_total "$S1/dryrun.log")"

# =============================================================================================
# Scenario 2: fresh species_dir -> symlinks created, DAG resolves identically to scenario 1
# =============================================================================================
S2="$WORKDIR/2_species_dir"
make_project "$S2"
EXT2="$WORKDIR/2_external_data"
make_species_root "$EXT2"
make_fake_data "$EXT2"
cat > "$S2/config/config.yaml" <<EOF
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
    species_dir: "$EXT2"
EOF

run_dryrun "$S2" "$S2/dryrun.log"
if [ "$DRYRUN_EXIT" -eq 0 ]; then
  pass "2a: species_dir dry-run succeeds"
else
  fail "2a: species_dir dry-run succeeds" "exit code $DRYRUN_EXIT, see $S2/dryrun.log"
fi

ALL_LINKED=1
for rel in input/read_module input/reference_module input/reveal_module/scg \
           input/reveal_module/feature_library input/reveal_module/competition processed results; do
  link="$S2/Dmel/$rel"
  target="$(cd "$EXT2/$rel" && pwd -P)"
  if [ ! -L "$link" ]; then
    fail "2b: symlink created at $rel" "missing symlink at $link"
    ALL_LINKED=0
  elif [ "$(readlink "$link")" != "$target" ]; then
    fail "2b: symlink created at $rel" "readlink=$(readlink "$link") expected=$target"
    ALL_LINKED=0
  fi
done
[ "$ALL_LINKED" -eq 1 ] && pass "2b: all 7 category symlinks created with correct realpath targets"

S2_JOBS="$(job_total "$S2/dryrun.log")"
if [ -n "$S1_JOBS" ] && [ "$S1_JOBS" = "$S2_JOBS" ]; then
  pass "2c: DAG job count identical to default layout ($S2_JOBS jobs) - symlinks are transparent to Snakemake"
else
  fail "2c: DAG job count identical to default layout" "scenario1=$S1_JOBS scenario2=$S2_JOBS"
fi

# =============================================================================================
# Scenario 3: idempotency - rerunning must not error or recreate the symlink
# =============================================================================================
MTIME_BEFORE="$(stat -c %Y "$S2/Dmel/input/read_module" 2>/dev/null)"
run_dryrun "$S2" "$S2/dryrun2.log"
if [ "$DRYRUN_EXIT" -eq 0 ]; then
  pass "3a: second dry-run with same config succeeds"
else
  fail "3a: second dry-run with same config succeeds" "exit code $DRYRUN_EXIT, see $S2/dryrun2.log"
fi
MTIME_AFTER="$(stat -c %Y "$S2/Dmel/input/read_module" 2>/dev/null)"
if [ "$MTIME_BEFORE" = "$MTIME_AFTER" ]; then
  pass "3b: symlink not recreated (idempotent)"
else
  fail "3b: symlink not recreated (idempotent)" "mtime changed: $MTIME_BEFORE -> $MTIME_AFTER"
fi

# =============================================================================================
# Scenario 4: conflict detection - a real pre-existing directory must never be overwritten
# =============================================================================================
S4="$WORKDIR/4_conflict_realdir"
make_project "$S4"
mkdir -p "$S4/Dmel/input/read_module"
echo "preexisting" > "$S4/Dmel/input/read_module/keepme.txt"
EXT4="$WORKDIR/4_external_reads"
mkdir -p "$EXT4"
cat > "$S4/config/config.yaml" <<EOF
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
    reads_dir: "$EXT4"
EOF

run_dryrun "$S4" "$S4/dryrun.log"
if [ "$DRYRUN_EXIT" -ne 0 ] && grep -q "SpeciesDataLocationError" "$S4/dryrun.log"; then
  pass "4a: conflicting real directory causes a clear SpeciesDataLocationError"
else
  fail "4a: conflicting real directory causes a clear SpeciesDataLocationError" "exit=$DRYRUN_EXIT, see $S4/dryrun.log"
fi
if [ -f "$S4/Dmel/input/read_module/keepme.txt" ] && [ ! -L "$S4/Dmel/input/read_module" ]; then
  pass "4b: pre-existing real directory left completely untouched"
else
  fail "4b: pre-existing real directory left completely untouched" "keepme.txt or dir-vs-symlink state changed"
fi

# =============================================================================================
# Scenario 5: conflict detection - a symlink pointing elsewhere must never be repointed
# =============================================================================================
S5="$WORKDIR/5_conflict_wrong_symlink"
make_project "$S5"
mkdir -p "$S5/Dmel/input"
SOMEWHERE_ELSE="$WORKDIR/5_somewhere_else"
mkdir -p "$SOMEWHERE_ELSE"
ln -s "$SOMEWHERE_ELSE" "$S5/Dmel/input/read_module"
EXT5="$WORKDIR/5_external_reads"
mkdir -p "$EXT5"
cat > "$S5/config/config.yaml" <<EOF
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
    reads_dir: "$EXT5"
EOF

run_dryrun "$S5" "$S5/dryrun.log"
if [ "$DRYRUN_EXIT" -ne 0 ] && grep -q "SpeciesDataLocationError" "$S5/dryrun.log"; then
  pass "5a: symlink-to-elsewhere conflict causes a clear SpeciesDataLocationError"
else
  fail "5a: symlink-to-elsewhere conflict causes a clear SpeciesDataLocationError" "exit=$DRYRUN_EXIT, see $S5/dryrun.log"
fi
if [ "$(readlink "$S5/Dmel/input/read_module")" = "$SOMEWHERE_ELSE" ]; then
  pass "5b: pre-existing symlink's target left completely untouched"
else
  fail "5b: pre-existing symlink's target left completely untouched" "readlink=$(readlink "$S5/Dmel/input/read_module" 2>&1)"
fi

# =============================================================================================
# Scenario 6: dry runs must never leak the cross-project lock (Snakemake skips onsuccess: for
# --dryrun, so the lock must simply not be acquired in the first place - see species_paths.py)
# =============================================================================================
S6="$WORKDIR/6_lock_dryrun"
make_project "$S6"
EXT6="$WORKDIR/6_external_data"
make_species_root "$EXT6"
make_fake_data "$EXT6"
cat > "$S6/config/config.yaml" <<EOF
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
    species_dir: "$EXT6"
EOF

run_dryrun "$S6" "$S6/dryrun1.log"
run_dryrun "$S6" "$S6/dryrun2.log"  # twice, to also prove no stale-lock churn is left behind
if [ "$DRYRUN_EXIT" -eq 0 ] && [ ! -e "$EXT6/processed/.pastforward.lock" ] && [ ! -e "$EXT6/results/.pastforward.lock" ]; then
  pass "6: two consecutive dry-runs leave no .pastforward.lock behind"
else
  fail "6: two consecutive dry-runs leave no .pastforward.lock behind" \
       "processed lock: $([ -e "$EXT6/processed/.pastforward.lock" ] && echo present || echo absent), results lock: $([ -e "$EXT6/results/.pastforward.lock" ] && echo present || echo absent)"
fi

# =============================================================================================
# Scenario 7: a real (non-dry) run acquires the lock and releases it via onsuccess:. Uses a
# minimal synthetic Snakefile (not the full pastForward pipeline, which needs bioinformatics
# conda envs) that drives species_paths.py exactly the way workflow/Snakefile does.
# =============================================================================================
S7="$WORKDIR/7_lock_real_run"
mkdir -p "$S7"
EXT7="$WORKDIR/7_external_processed"
mkdir -p "$EXT7"
cat > "$S7/Snakefile" <<EOF
import sys, os
sys.path.insert(0, "$REPO_ROOT/workflow")
from scripts.species_paths import setup_species_data_locations, release_pastforward_locks

TARGET = "$EXT7"
cfg = {"species": {"X": {"processed_dir": TARGET}}}
setup_species_data_locations(cfg, dry_run=workflow.output_settings.dryrun)

rule all:
    input: "out.txt"

rule make_out:
    output: "out.txt"
    shell: "touch {output}"

onsuccess:
    release_pastforward_locks()
EOF
( cd "$S7" && "$TIMEOUT_CMD" 30 snakemake --cores 1 -s Snakefile > run.log 2>&1 )
S7_EXIT=$?
if [ "$S7_EXIT" -eq 0 ] && [ ! -e "$EXT7/.pastforward.lock" ]; then
  pass "7: real run acquires the lock and releases it via onsuccess:"
else
  fail "7: real run acquires the lock and releases it via onsuccess:" \
       "exit=$S7_EXIT, lock present=$([ -e "$EXT7/.pastforward.lock" ] && echo yes || echo no), see $S7/run.log"
fi

# =============================================================================================
# Scenario 8: the SNP divergence check is off by default and, when switched on, its
# snp_divergence_method picks which per-individual rules end up in the DAG.
# =============================================================================================
make_snp_project() {  # make_snp_project <dir> <extra_analysis_settings_yaml_or_empty>
  make_project "$1"
  cat > "$1/config/config.yaml" <<EOF
project_name: "pastForward_Project"
pipeline:
  reference_module:
    analysis:
      settings:
$2
species:
  Dmel:
    name: "Drosophila melanogaster"
EOF
  mkdir -p "$1/Dmel"
  make_species_root "$1/Dmel"
  make_fake_data "$1/Dmel"
}

# 8a: default config (check off) must not pull any snp_divergence rule into the DAG
if grep -qE "^(combine_snp_divergence|call_snps_for_divergence|plot_snp_divergence_bar)[[:space:]]" "$S1/dryrun.log"; then
  fail "8a: snp divergence check is off by default" "a snp_divergence rule appeared in $S1/dryrun.log"
else
  pass "8a: snp divergence check is off by default"
fi

# 8b: samtools_stats tier reuses the existing samtools stats files, no bcftools rules
S8B="$WORKDIR/8_snp_samtools_stats"
make_snp_project "$S8B" "        snp_divergence_check: true"
run_dryrun "$S8B" "$S8B/dryrun.log"
if [ "$DRYRUN_EXIT" -eq 0 ]; then
  pass "8b: samtools_stats tier dry-run succeeds"
else
  fail "8b: samtools_stats tier dry-run succeeds" "exit code $DRYRUN_EXIT, see $S8B/dryrun.log"
fi
if grep -qE "^combine_snp_divergence[[:space:]]" "$S8B/dryrun.log" &&
   grep -qE "^plot_snp_divergence_bar[[:space:]]" "$S8B/dryrun.log"; then
  pass "8c: samtools_stats tier schedules the combine and plot rules"
else
  fail "8c: samtools_stats tier schedules the combine and plot rules" "see $S8B/dryrun.log"
fi
if grep -qE "^(build_snp_divergence_regions|call_snps_for_divergence|count_snp_divergence_callable_bases|compute_snp_divergence_stats)[[:space:]]" "$S8B/dryrun.log"; then
  fail "8d: samtools_stats tier pulls in no bcftools rule" "a bcftools-tier rule appeared in $S8B/dryrun.log"
else
  pass "8d: samtools_stats tier pulls in no bcftools rule"
fi

# 8e: bcftools tier adds the region BED, calling, callable-bases and stats rules
S8E="$WORKDIR/8_snp_bcftools"
make_snp_project "$S8E" "        snp_divergence_check: true
        snp_divergence_method: bcftools"
run_dryrun "$S8E" "$S8E/dryrun.log"
if [ "$DRYRUN_EXIT" -eq 0 ]; then
  pass "8e: bcftools tier dry-run succeeds"
else
  fail "8e: bcftools tier dry-run succeeds" "exit code $DRYRUN_EXIT, see $S8E/dryrun.log"
fi
S8E_MISSING=""
for expected_rule in build_snp_divergence_regions call_snps_for_divergence \
                     count_snp_divergence_callable_bases compute_snp_divergence_stats \
                     combine_snp_divergence; do
  grep -qE "^${expected_rule}[[:space:]]" "$S8E/dryrun.log" || S8E_MISSING="$S8E_MISSING $expected_rule"
done
if [ -z "$S8E_MISSING" ]; then
  pass "8f: bcftools tier schedules every bcftools-tier rule"
else
  fail "8f: bcftools tier schedules every bcftools-tier rule" "missing:$S8E_MISSING, see $S8E/dryrun.log"
fi

# 8g: target_bases 0 means call the whole reference, so no region BED is built
S8G="$WORKDIR/8_snp_bcftools_whole_reference"
make_snp_project "$S8G" "        snp_divergence_check: true
        snp_divergence_method: bcftools
        snp_divergence_target_bases: 0"
run_dryrun "$S8G" "$S8G/dryrun.log"
if [ "$DRYRUN_EXIT" -eq 0 ] && ! grep -qE "^build_snp_divergence_regions[[:space:]]" "$S8G/dryrun.log"; then
  pass "8g: target_bases 0 skips the region BED rule"
else
  fail "8g: target_bases 0 skips the region BED rule" \
       "exit=$DRYRUN_EXIT, see $S8G/dryrun.log"
fi

# 8h: an unknown method fails fast instead of silently doing nothing
S8H="$WORKDIR/8_snp_bad_method"
make_snp_project "$S8H" "        snp_divergence_check: true
        snp_divergence_method: nonsense"
run_dryrun "$S8H" "$S8H/dryrun.log"
if [ "$DRYRUN_EXIT" -ne 0 ] && grep -q "Unknown snp_divergence_method" "$S8H/dryrun.log"; then
  pass "8h: an unknown snp_divergence_method fails with a clear error"
else
  fail "8h: an unknown snp_divergence_method fails with a clear error" \
       "exit=$DRYRUN_EXIT, see $S8H/dryrun.log"
fi

# =============================================================================================
# Scenario 9: benchmarking - workflow/rules/benchmark.smk attaches a benchmark file to every
# rule after the fact, using Snakemake internals (Rule.benchmark, Rule.log_modifier,
# Workflow.output_settings). A Snakemake upgrade that changes those must fail here rather than
# in a user's run.
# =============================================================================================
S9="$WORKDIR/9_benchmark"
make_project "$S9"
cat > "$S9/config/config.yaml" <<'EOF'
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
EOF
mkdir -p "$S9/Dmel"
make_species_root "$S9/Dmel"
make_fake_data "$S9/Dmel"

run_dryrun "$S9" "$S9/dryrun.log"
if [ "$DRYRUN_EXIT" -eq 0 ]; then
  pass "9a: dry-run with benchmarks attached succeeds"
else
  fail "9a: dry-run with benchmarks attached succeeds" "exit code $DRYRUN_EXIT, see $S9/dryrun.log"
fi

# 9b: the DAG job count is unchanged - a benchmark file is not an output, so it adds no job
S9_JOBS="$(job_total "$S9/dryrun.log")"
if [ -n "$S1_JOBS" ] && [ "$S1_JOBS" = "$S9_JOBS" ]; then
  pass "9b: DAG job count unchanged by benchmarks ($S9_JOBS jobs)"
else
  fail "9b: DAG job count unchanged by benchmarks" "scenario1=$S1_JOBS scenario9=$S9_JOBS"
fi

# 9c: every scheduled job carries a benchmark path next to its log path
if grep -qE "^    benchmark: .*\.benchmark\.jsonl$" "$S9/dryrun.log"; then
  pass "9c: jobs are scheduled with a .benchmark.jsonl path"
else
  fail "9c: jobs are scheduled with a .benchmark.jsonl path" "no benchmark line in $S9/dryrun.log"
fi

# 9d: rules marked `cache: True` must be skipped. Snakemake rejects a rule that is both
# cacheable and benchmarked, and does so at DAG build time, which kills the whole run.
if grep -q "may not be marked as eligible" "$S9/dryrun.log"; then
  fail "9d: cache-eligible rules are left unbenchmarked" \
       "Snakemake rejected a cacheable rule carrying a benchmark, see $S9/dryrun.log"
else
  pass "9d: cache-eligible rules are left unbenchmarked"
fi

# 9e: a real (tiny, conda-free) job actually writes the file, in the extended JSON-lines format
# that `./pastForward benchmark` reads. The dry runs above only prove the paths were attached.
S9E="$WORKDIR/9_benchmark_write"
mkdir -p "$S9E"
cat > "$S9E/Snakefile" <<EOF
rule all:
    input:
        "out.txt",


rule make_out:
    output:
        "out.txt",
    log:
        "out.log",
    shell:
        "touch {output} > {log} 2>&1"


include: "$REPO_ROOT/workflow/rules/benchmark.smk"
EOF
( cd "$S9E" && "$TIMEOUT_CMD" 120 snakemake --cores 1 > "$S9E/run.log" 2>&1 )
if [ -f "$S9E/out.benchmark.jsonl" ]; then
  pass "9e: a real job writes out.benchmark.jsonl next to out.log"
else
  fail "9e: a real job writes out.benchmark.jsonl next to out.log" "see $S9E/run.log"
fi
# rule_name only appears in the extended format, which benchmark.smk switches on for the whole
# workflow - without it the aggregator cannot tell which rule a file belongs to.
if grep -q '"rule_name": "make_out"' "$S9E/out.benchmark.jsonl" 2>/dev/null; then
  pass "9f: the record is in extended format, with no --benchmark-extended flag passed"
else
  fail "9f: the record is in extended format, with no --benchmark-extended flag passed" \
       "$(cat "$S9E/out.benchmark.jsonl" 2>/dev/null || echo "no benchmark file")"
fi

# =============================================================================================
# Scenario 10: the shipped workflow profile (workflow/profiles/default/config.yaml). Snakemake
# discovers it by path and by filename, and gets both wrong silently: a profile at the top of the
# project instead of under workflow/ is never seen from a project root that only symlinks
# workflow/, and a key Snakemake does not recognize is ignored without a warning. So assert the
# effect on a real DAG, not the file's existence.
# =============================================================================================
S10="$WORKDIR/10_profile"
make_project "$S10"
cat > "$S10/config/config.yaml" <<'EOF'
project_name: "pastForward_Project"
species:
  Dmel:
    name: "Drosophila melanogaster"
EOF
mkdir -p "$S10/Dmel"
make_species_root "$S10/Dmel"
make_fake_data "$S10/Dmel"

run_dryrun "$S10" "$S10/dryrun.log"

# 10a: found through the workflow/ symlink, from a project root with no profiles/ of its own
if grep -q "workflow specific profile workflow/profiles/default" "$S10/dryrun.log"; then
  pass "10a: workflow profile is discovered through the workflow/ symlink"
else
  fail "10a: workflow profile is discovered through the workflow/ symlink" \
       "no discovery line in $S10/dryrun.log - wrong path, or wrong filename for this version"
fi

# 10b: its default-resources actually reach the jobs. No rule declares a runtime of its own, so
# every scheduled job must carry the profile's. A typo'd key would leave the line out entirely.
PROFILE_RUNTIME="$(grep -oE "runtime=[0-9]+" "$S10/dryrun.log" | head -1)"
if [ "$PROFILE_RUNTIME" = "runtime=240" ]; then
  pass "10b: the profile's default-resources reach the scheduled jobs ($PROFILE_RUNTIME)"
else
  fail "10b: the profile's default-resources reach the scheduled jobs" \
       "expected runtime=240, got '${PROFILE_RUNTIME:-no runtime in any resources line}'"
fi

# 10c: the DAG is unchanged by the profile. Resources are requests, not targets - if the job count
# moves, the profile is doing something it should not.
S10_JOBS="$(job_total "$S10/dryrun.log")"
if [ -n "$S1_JOBS" ] && [ "$S1_JOBS" = "$S10_JOBS" ]; then
  pass "10c: DAG job count unchanged by the profile ($S10_JOBS jobs)"
else
  fail "10c: DAG job count unchanged by the profile" "scenario1=$S1_JOBS scenario10=$S10_JOBS"
fi

# 10d: --workflow-profile none is the documented escape hatch, so it has to still build a DAG
( cd "$S10" && "$TIMEOUT_CMD" 120 snakemake --cores 4 --dryrun \
    --workflow-profile none > "$S10/no_profile.log" 2>&1 )
S10_NONE_EXIT=$?
S10_NONE_JOBS="$(job_total "$S10/no_profile.log")"
if [ "$S10_NONE_EXIT" -eq 0 ] && [ "$S10_NONE_JOBS" = "$S10_JOBS" ]; then
  pass "10d: --workflow-profile none still builds the same DAG"
else
  fail "10d: --workflow-profile none still builds the same DAG" \
       "exit $S10_NONE_EXIT, jobs $S10_NONE_JOBS vs $S10_JOBS, see $S10/no_profile.log"
fi

# =============================================================================================
echo ""
echo "$PASS_COUNT passed, $FAIL_COUNT failed"
if [ "$FAIL_COUNT" -ne 0 ]; then
  echo "Failed: ${FAILED_NAMES[*]}"
  exit 1
fi
exit 0

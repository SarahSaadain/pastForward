#!/usr/bin/env bash
# Dry-runs the synthetic project with only some modules switched on, one config per subset in
# synthetic_project/config/subsets/. Each subset is layered over config/config.yaml with
# --configfile. Checks that the run plans, and that jobs of switched-off modules stay out.
# No conda envs are built, so it needs only Snakemake on PATH.
#
# Usage: tests/integration/module_subsets.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/synthetic_project"
command -v snakemake >/dev/null || { echo "ERROR: snakemake not on PATH" >&2; exit 2; }
WORK="$(mktemp -d -t pf_module_subsets.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# <config name>|<rule prefix that must be planned>|!<rule prefix that must not be planned>|...
CASES=(
  "reads_only|remove_adapters_paired_with_fastp|!map_reads_to_reference|!map_reads_to_scg|!create_multiqc_species"
  "reads_reference|get_adapter_removal_final|map_reads_to_reference|!map_reads_to_scg"
  "reference_only|map_reads_to_reference|!ecmsd_taxonomic_screening|!run_multiqc_raw|!map_reads_to_scg"
  "reveal_only|map_reads_to_scg_feature_library|!map_reads_to_reference|!ecmsd_taxonomic_screening|!run_multiqc_raw"
)
FAILS=0
for case in "${CASES[@]}"; do
  IFS='|' read -ra parts <<< "$case"; name="${parts[0]}"
  P="$WORK/$name"; mkdir -p "$P/Dmel"
  cp -r "$SRC/config" "$SRC/resources" "$P/"; cp -r "$SRC/Dmel/input" "$P/Dmel/"
  ln -s "$REPO_ROOT/workflow" "$P/workflow"
  if ! (cd "$P" && snakemake --cores 2 --dryrun --configfile "config/subsets/$name.yaml" > log 2>&1); then
    echo "FAIL  $name: dry run failed, see $P/log"; tail -5 "$P/log"; FAILS=$((FAILS+1)); continue
  fi
  rules="$(grep -A1 'output files have to be generated' "$P/log" | tail -1 | tr -d ' ' | tr ',' '\n')"
  bad=""
  for r in "${parts[@]:1}"; do
    if [[ $r == !* ]]; then grep -q "^${r#!}" <<< "$rules" && bad="$bad unexpected ${r#!}"
    else grep -q "^$r" <<< "$rules" || bad="$bad missing $r"; fi
  done
  if [ -n "$bad" ]; then echo "FAIL  $name:$bad"; FAILS=$((FAILS+1)); else echo "PASS  $name ($(wc -l <<< "$rules") rules)"; fi
done
exit $((FAILS > 0))

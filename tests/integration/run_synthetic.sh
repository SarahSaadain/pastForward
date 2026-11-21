#!/usr/bin/env bash
# Real (non-dry) pipeline run on tests/integration/synthetic_project/, with the environment set up
# the way job envs need it. Extra arguments go straight to snakemake.
#
# Usage:
#   tests/integration/run_synthetic.sh                                 # whole project
#   tests/integration/run_synthetic.sh --until mapdamage_combine_chunk_tables
#   tests/integration/run_synthetic.sh --forcerun mapdamage_combine_chunk_tables --until mapdamage_combine_chunk_tables
#
# Rerunning a step whose outputs are temp() (e.g. mapdamage_count_chunk): --forcerun that rule
# finds nothing to do, because its outputs are gone. Force the rule that consumes them instead.
#
# Environment:
#   PF_SNAKEMAKE_ENV   conda env name or path with snakemake (default: snakemake)
#   PF_CONDA_PREFIX    where job envs live (default: ~/.snakemake/pf_conda, shared with compare_with_ref.sh)
#   PF_CORES           --cores (default: 4)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# A job env's bin left on PATH (e.g. from an editor's shell snapshot) shadows the job envs' python,
# and jobs fail with "No module named 'snakemake_wrapper_utils'". Activating does not remove it.
PATH="$(printf %s "$PATH" | tr : '\n' | grep -v '/\.snakemake/' | paste -sd:)"
export PATH

command -v conda >/dev/null || { echo "ERROR: conda not on PATH" >&2; exit 2; }
source "$(conda info --base)/etc/profile.d/conda.sh"
# Activate, not PATH-prepend: a prepended env bin stays first inside every job env.
conda activate "${PF_SNAKEMAKE_ENV:-snakemake}"

cd "$REPO_ROOT"
exec snakemake --directory tests/integration/synthetic_project \
  --cores "${PF_CORES:-4}" \
  --software-deployment-method conda \
  --conda-prefix "${PF_CONDA_PREFIX:-$HOME/.snakemake/pf_conda}" \
  --keep-going --rerun-trigger mtime \
  "$@"

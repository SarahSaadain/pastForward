# Tests

```text
tests/
  unit/          fast pure-Python tests, no Snakemake or conda. Plus their helpers
                 (pf_test_library.py, build_test_library.py) and fixtures/
  integration/   needs Snakemake: test_cli_snakemake.py, dryrun_scenarios.sh,
                 module_subsets.sh (read only, read+ref, ref only, reveal only),
                 and synthetic_project/ (a small project with known answers) with
                 test_synthetic_run.py that checks its results,
                 and real_data_project/ (tier 2: download_full_test.sh fetches real
                 reads, config/ is tracked, the data is not)
```

All Python unit tests run with either:

```bash
python3 tests/unit/test_<name>.py                   # a single module
python3 -m unittest discover tests/unit -v           # everything, from the repo root
```

They need only pyyaml, jsonschema and pandas, not Snakemake or conda. That keeps them fast
enough to run before every commit to catch obviously-broken new development. There are three
exceptions:

- `test_cli_snakemake.py` holds the CLI tests for `run`, `resume`, `unlock` and
  `doctor --rebuild-envs`. These commands stop early when no `snakemake` is on PATH. So the
  tests skip themselves without it, and `discover` reports them as skipped. To run them, put
  the Snakemake env on PATH:

  ```bash
  PATH=<snakemake-env>/bin:$PATH python3 -m unittest tests/integration/test_cli_snakemake.py -v
  ```

  CI installs Snakemake, so they always run there.
- `test_synthetic_run.py` (below) checks the output of a finished pipeline run on `tests/integration/synthetic_project/`.
  It skips itself when that output is missing.
- `integration/module_subsets.sh` dry-runs the synthetic project with only some modules on. The
  subset configs are in `synthetic_project/config/subsets/` and are layered over `config.yaml`
  with `--configfile`. It needs only Snakemake on PATH, no conda envs.
- `dryrun_scenarios.sh` (below) is a slower, separate integration check.

## `test_file_manager.py` / `test_expected_output_manager.py` / `test_endogenous_reads_stats.py`

These are the ones to reach for when changing discovery logic, config-driven DAG targets, or
adding a new pipeline step/config toggle. They are the fastest way to tell whether the change
did what you meant, before running a real (or even a dry) Snakemake pipeline.

Both `test_file_manager.py` and `test_expected_output_manager.py` build a small synthetic
species library on disk for each test, via the shared builder in `pf_test_library.py`, then
exercise the real pipeline code against it in a throwaway temp directory. The library holds raw
reads (paired/single-end, both R1/R2 and standalone 1/2 naming, plus a file with no recognizable
marker and an uncompressed `.fastq`, both of which must be discovered-but-ignored), two reference
genomes (one with a dotted filename, to check ID sanitization), a feature library, and (where
relevant) an SCG library and competition FASTA. No mocking of file discovery: these are real
files on real disk, matching the conventions in CLAUDE.md's "Species/file discovery" and "Raw
read filenames" sections.

- **`test_file_manager.py`**: `workflow/scripts/file_manager.py`'s discovery functions
  directly: read pairing/individual/sample extraction, reference/feature-library/SCG discovery
  and config filtering (including the `ConfigValidationError` path for a requested-but-missing
  individual/reference/library), competition FASTA resolution, and SCG auto-determination
  eligibility (`should_auto_determine_scg`).

- **`test_expected_output_manager.py`**: the DAG-target computation chain
  (`expected_output_manager.py` + its four `expected_output_manager_<module>_processing.py`
  submodules): which output paths `rule all` requests for a given `config.yaml`. Covers the
  `species`/module-level/sub-step `execute: false` gates, `skip_existing_files`, and the
  SCG-selector default (see below). Since these `.py` files are Snakemake `include:` targets
  that rely on sharing the Snakefile's globals (`config`, and each other's top-level functions)
  rather than importing anything, `workflow/scripts/pipeline_namespace.py` loads them into a
  shared namespace dict the same way, so they can run standalone (the same loader
  `./pastForward check`/`preview` use).

- **`test_endogenous_reads_stats.py`**: the two endogenous-reads statistics helpers that are
  plain functions with no `snakemake` object dependency at import time
  (`parse_endogenous_from_stats.py`, `combine_endogenous_reads.py`): stats parsing, malformed
  values, division-by-zero, and multi-file combination.

- **`test_coverage_summary.py`**: the per-scaffold depth analysis
  (`analyze_coverage_from_bam.py`, fed depth text directly, so no samtools or pysam needed), the combined coverage CSVs
  (`combine_analyzed_depth_breadth_files.py`) and the MultiQC coverage summary
  (`summarize_coverage.py`): scaffold names kept as text across read chunks (no split `4` row,
  no dropped `NA` scaffold) and a length-weighted average depth, each script alone and as one
  chain. It needs pandas, and skips
  itself when pandas is not installed.

`scg_selector.execute` defaults to `True` in
`expected_output_manager_reveal_module_processing.py`, the same as in
`file_manager.should_auto_determine_scg()`, `check.py`, and the docs. Writing these tests turned
up a bug where that one default had drifted to `False`, so a config that (per the docs)
correctly omits `scg_selector.execute` entirely would silently skip SCG auto-determination and,
with it, all of REVEAL. `TestScgSelectorDefaults` in `test_expected_output_manager.py` locks the
documented behavior in.

## `build_test_library.py`: materializing a library to poke at by hand

```bash
python3 tests/unit/build_test_library.py
cd tests/unit/fixtures/pf_test_library && snakemake --cores 2 --software-deployment-method conda --dryrun
```

Builds the same synthetic species library (via `pf_test_library.py`) as a persistent project
directory under `tests/unit/fixtures/` (gitignored, rebuilt from scratch every time). It holds a
`config.yaml` and a `workflow/` symlink into this repo alongside the species data, so it's
immediately usable for a manual dry-run sanity check. It's also rebuilt once as a side effect of
running `test_expected_output_manager.py` (see that file's `setUpModule`), so running the test
suite refreshes it.

## `test_species_paths.py`

Covers the configurable species data locations feature (`species_dir`, `reads_dir`,
`reference_dir`, `scg_dir`, `feature_library_dir`, `competition_dir`, `processed_dir`,
`results_dir`, see [config/README.md](../config/README.md#storing-species-data-elsewhere)) and
its cross-project lock: symlink creation, idempotency, both conflict cases, `execute: false`
skipping, the cross-project lock (fresh acquire, stale takeover, foreign-host refusal, scoped
release, releasing already-taken locks when a later one conflicts), and that the load-time
symlink setup takes no lock.

## `test_synthetic_run.py`: known answers from the `tests/integration/synthetic_project/` run

`tests/integration/synthetic_project/` is a small synthetic project. Its reads were simulated with known answers. HistA is a
historical sample and ModB a modern one. The tests check that a finished run reproduces them:

- damage: HistA has C>T at the 5' end that drops inward, ModB has none (mapDamage)
- authenticity table: HistA `ok`, ModB `check` for missing damage, HistA reads shorter
- duplicates: HistA 15 to 35 % (20 % simulated, DeDup measures about 26 %), ModB under 8 %
- screening: human reads in HistA only (ECMSD and Centrifuge), E. coli in HistA only
- REVEAL: copy numbers of opus, roo, jockey and the SCGs within 25 % of the designed values,
  and opus flagged as gained or lost

Values are checked against ranges, not exact numbers, so tool updates do not break them.

Run the pipeline on `tests/integration/synthetic_project/` first, with the Snakemake env active. Then run the tests:

```bash
snakemake --directory tests/integration/synthetic_project --cores 4 --software-deployment-method conda
python3 -m unittest tests/integration/test_synthetic_run.py -v
```

Without `tests/integration/synthetic_project/Dmel/results/` the whole file is skipped. To check another project directory,
set `PF_TEST_PROJECT=<path>`.

## `dryrun_scenarios.sh`: Snakemake integration checks

Drives the real `snakemake` CLI against throwaway project directories (each just symlinks this
repo's `workflow/`) to catch anything only visible once Snakemake itself parses `initialize.smk`
and builds the DAG: rule/wildcard resolution through the symlinks, and Snakemake's own
hook timing (the cross-project lock is taken in `onstart:`, which dry runs and `--lint` never
fire, see the comment on `acquire_pastforward_locks`).

Requires a conda environment named `snakemake` (Snakemake >= 9.26.1, see
[config/README.md](../config/README.md)). The first run may be slow while Snakemake clones
`snakemake-wrappers` into `~/.cache/snakemake` for a wrapper-based rule. That cache is reused on
later runs.

```bash
tests/integration/dryrun_scenarios.sh            # runs all scenarios, cleans up its temp workspace
tests/integration/dryrun_scenarios.sh --keep     # keeps the workspace and prints its path, for inspection
```

Scenarios: default/fallback (zero symlinks, zero behavior change), fresh `species_dir` (symlinks
created, DAG job count identical to the default-layout run), idempotent re-run, both conflict
cases (pre-existing real directory / pre-existing symlink elsewhere, which must error and leave
the conflicting path untouched), dry-runs never leaking `.pastforward.lock`, and `--lint`
taking no lock while a real run acquires it in `onstart:` and releases it via `onsuccess:`.

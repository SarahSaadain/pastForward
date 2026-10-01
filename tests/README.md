# Tests

All Python unit tests run with either:

```bash
python3 tests/test_<name>.py                   # a single module
python3 -m unittest discover tests -v           # everything, from the repo root
```

None of them need Snakemake or conda, which is what makes them fast enough to run before
every commit to catch obviously-broken new development. `dryrun_scenarios.sh` (below) is the
one exception, and is a slower, separate integration check.

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

`scg_selector.execute` defaults to `True` in
`expected_output_manager_reveal_module_processing.py`, the same as in
`file_manager.should_auto_determine_scg()`, `check.py`, and the docs. Writing these tests turned
up a bug where that one default had drifted to `False`, so a config that (per the docs)
correctly omits `scg_selector.execute` entirely would silently skip SCG auto-determination and,
with it, all of REVEAL. `TestScgSelectorDefaults` in `test_expected_output_manager.py` locks the
documented behavior in.

## `build_test_library.py`: materializing a library to poke at by hand

```bash
python3 tests/build_test_library.py
cd tests/fixtures/pf_test_library && snakemake --cores 2 --software-deployment-method conda --dryrun
```

Builds the same synthetic species library (via `pf_test_library.py`) as a persistent project
directory under `tests/fixtures/` (gitignored, rebuilt from scratch every time). It holds a
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
release), and the dry-run lock skip.

## `dryrun_scenarios.sh`: Snakemake integration checks

Drives the real `snakemake` CLI against throwaway project directories (each just symlinks this
repo's `workflow/`) to catch anything only visible once Snakemake itself parses `initialize.smk`
and builds the DAG: rule/wildcard resolution through the symlinks, and Snakemake's own
dry-run/`onsuccess:` hook timing (dry runs never fire `onsuccess:`/`onerror:`, so the
cross-project lock must not be acquired during a dry run, see the comment in
`setup_species_data_locations`).

Requires a conda environment named `snakemake` (Snakemake >= 9.9.0, see
[config/README.md](../config/README.md)). The first run may be slow while Snakemake clones
`snakemake-wrappers` into `~/.cache/snakemake` for a wrapper-based rule. That cache is reused on
later runs.

```bash
tests/dryrun_scenarios.sh            # runs all scenarios, cleans up its temp workspace
tests/dryrun_scenarios.sh --keep     # keeps the workspace and prints its path, for inspection
```

Scenarios: default/fallback (zero symlinks, zero behavior change), fresh `species_dir` (symlinks
created, DAG job count identical to the default-layout run), idempotent re-run, both conflict
cases (pre-existing real directory / pre-existing symlink elsewhere, which must error and leave
the conflicting path untouched), dry-runs never leaking `.pastforward.lock`, and a real run
acquiring then releasing the lock via `onsuccess:`.

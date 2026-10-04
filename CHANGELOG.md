# Changelog

All notable changes to this project will be documented in this file.


## [Unreleased]

### New Features

- **`./pastForward tools create-species`**: creates a species' `input/` folders in the project root and prints a `species:` block for `config/config.yaml`. Takes several species at once and leaves existing folders alone. See [README.md](README.md#running-the-pipeline)
- **`./pastForward tools link-reads`**: `--source <folder> --species <species>` (or `-d`/`-s`) symlinks every `*.fastq.gz`/`*.fq.gz` file in the source folder into `<species>/input/read_module/`, so reads can stay where they are. Existing names are never overwritten, and names the pipeline cannot use are listed in a warning. See [README.md](README.md#running-the-pipeline)
- **`./pastForward touch`**: wraps `snakemake --touch` to mark existing outputs as up to date, for example after copying results from another machine. Only timestamps change. See [README.md](README.md#running-the-pipeline)
- **`./pastForward benchmark`**: every rule now writes a `*.benchmark.jsonl` file next to its log. `./pastForward benchmark` sums these up per rule (wall time, peak memory, core-hours), and `--emit-profile` prints a `set-resources:` block for HPC runs. On macOS only wall time is recorded. See [docs/snakemake.md](docs/snakemake.md#benchmarking-a-run)
- **Default workflow profile**: `workflow/profiles/default/profile.yaml` gives every rule a default request of 8 GB memory and 4 hours wall time, and sets `--keep-going` and `--rerun-trigger mtime`. Snakemake picks it up without a flag. Cluster jobs no longer fall back to the partition's defaults. See [docs/snakemake.md](docs/snakemake.md#resource-defaults)
- **SNP divergence check**: `pipeline.reference_module.analysis.settings.snp_divergence_check` flags individuals whose divergence from the reference is an outlier within their cohort. This can point to a wrong reference, cross-species contamination, or a mislabeled individual. Warning only. Methods: `samtools_stats` (default, no extra runtime), `bcftools` (adds heterozygous-call rate), or `both`. Default `false`. See [config/parameters.md](config/parameters.md)
- **`pipeline.reveal_module.normalization.settings.skip_low_coverage_individuals`**: excludes individuals with too little SCG coverage for REVEAL normalization instead of failing the whole species. Excluded individuals are listed in `{species}_{feature_library}_excluded_individuals.tsv`. Default `false`. See [config/parameters.md](config/parameters.md)
- **Short flags**: `status -w`, `abort -f`, `print-log -l` and `print-log -t [N]`
- **`./pastForward check` and `preview` take `--configfile`**, merged on top of `config/config.yaml` the same way Snakemake does it for `run`
- **`./pastForward unlock` handles `.pastforward.lock`**: it lists the cross-project locks in the config's `processed_dir`/`results_dir` targets, and `--cross-project` removes them. A lock whose run is still alive on this host is never removed. See [docs/FAQ.md](docs/FAQ.md)
- **`./pastForward <command> --help`** (or `-h`) shows the help for that one command. A mistyped command now suggests the closest one
- **`config/max_config_modern_sample.yaml`**: example config for modern DNA. All steps run as in `max_config_sample.yaml`, except deduplication, damage rescaling and damage analysis, which are off

### Changed

- **Sample names keep everything in the read filename except `R1`/`R2`**: text after the read number (e.g. `_set1_lane6`) used to be dropped, so several lanes of one library collapsed into one sample and the run stopped with `has more than one R1 candidate`. Each lane is now its own sample and is still merged per individual. Note: on existing projects with text after the read number, per-sample files get new names, so mapping and later steps rerun. See [config/README.md](config/README.md#naming-your-read-files)
- **`./pastForward status` shows how a run ended**: a new `Status:` line (`Running`, `Completed`, `Aborted`, `Failed`, `Interrupted`, ...) replaces the red `PID: ... (not running)` that made clean finishes look like errors. The progress bar is colored by state
- **`./pastForward --help` groups commands by task**. Command names and flags are unchanged
- **REVEAL is installed from bioconda**: `version_source: "conda"` (the default) now installs `reveal-tools=1.*` from [bioconda](https://github.com/bioconda/bioconda-recipes/pull/67451) instead of the newest GitHub release
- **`--software-deployment-method conda` replaces `--use-conda`** in the CLI and docs, since Snakemake 8 deprecated `--use-conda`. The old flag still works. The CLI no longer overrides a deployment flag you pass yourself (e.g. `--sdm apptainer`)
- **Read counting is about 4x faster**, using ISA-L instead of Python's `gzip`
- **Snakemake 9.26.1 or newer is required** (was 9.9.0). Older versions have bugs that hit this pipeline. They can rerun jobs whose outputs are up to date (fixed in 9.11, 9.22 and 9.26). From 9.16.3 to 9.19 they read the profile's `runtime` as seconds instead of minutes. Before 9.24 they leak benchmark threads, which crashed long runs with "Too many open files". Update with `conda update -n snakemake snakemake`
- **`./pastForward status` shows Snakemake's own run time** for a finished run, from the `Elapsed time` line Snakemake logs on exit. A killed run still falls back to the log file's last write

### Bug Fixes

- **`./pastForward run --configfile <file>` failed without `config/config.yaml`**, even though Snakemake does not need it then. Same for `dryrun` and `touch`. A missing `--configfile` file is now reported before Snakemake starts
- **`./pastForward print-log` could show the wrong log**: a `dryrun` started during a run was newer, so it was shown instead of the run. While a tracked run is going, its log is shown
- **`./pastForward unlock` left a `.pastforward.lock` behind** when the config sets `processed_dir` or `results_dir`. Same host runs took it over, but it looked like a stuck lock
- **`./pastForward status --watch` flickered**: each refresh cleared the screen before drawing. It now draws over the previous frame

- **Workflow failed to parse without `config/config.yaml`**: a fresh clone has no config, so `snakemake --lint` and the [Snakemake workflow catalog](https://snakemake.github.io/snakemake-workflow-catalog) reported the workflow as broken. A missing config is now reported with a clear message when you run it
- **`./pastForward dryrun` did not match `./pastForward run`**: it left out `--rerun-trigger mtime` and could show an almost full rerun that `run` would never do
- **`./pastForward status` called a tracked dry run force-killed**: `run -n` is now labeled as a dry run
- **`./pastForward check` could hide read files with unusable names**: it now always prints a `WARNING: reads not used` line with the reason for each file
- **`./pastForward doctor --rebuild-envs` crashed on environments shared by several rules** with `FileNotFoundError`
- **BUSCO SCG library step broke on Snakemake >= 9.17.0** with `ImportError: cannot import name 'snakemake' from 'snakemake.script'` ([#11](https://github.com/SarahSaadain/pastForward/issues/11))
- **`dedup_deduplicate_bam_cluster` lost its log on a crash**: the log was inside an output folder that Snakemake deletes on failure
- **REVEAL conda environments could fail with `libicui18n.so.58: cannot open shared object file`**: the `defaults` channel is removed from the REVEAL env files. Rebuild old envs with `./pastForward doctor --rebuild-envs reveal`

### Docs

- **FAQ**: new sections on reprocessing cascades, why REVEAL processing does not deduplicate, benchmark files, workflow profiles, and SNP divergence status values

### CI / Maintenance

- `workflow/rules/initialize.smk` formatted so the workflow catalog's older snakefmt also accepts it
- `workflow/scripts/cli.py` split into a `workflow/scripts/cli/` package
- Three REVEAL library rules now write their own log file

## [2.1.0] - 2026-08-20

### New Features

- **`pastForward` CLI**: a wrapper around `snakemake` at the project root — `run`/`resume` (backgrounded by default), `status`/`abort`/`unlock`, `check`/`preview`, `dryrun`, `doctor` (list/rebuild conda envs), `print-log`, `version`. `run`/`dryrun` write timestamped logs to `logs/`. `check`/`preview` run in-process, so they return in well under a second and need no Snakemake at all (`preview.py` was renamed to `check.py` to match). See [README.md](README.md#running-the-pipeline); plain `snakemake` usage moved to [docs/snakemake.md](docs/snakemake.md)
- **Configurable ECMSD/REVEAL version source**: `tools.ecmsd.settings.version_source` and `pipeline.reveal_module.settings.version_source` (both default `conda`) can side-load either tool straight from GitHub — `latest_release`, or an experimental `dev` — instead of its conda build. Each value has its own conda env, so switching it rebuilds automatically. For ECMSD, `conda` is the bioconda package `ecmsd=1.*`. REVEAL is not on bioconda yet, so `conda` has no package to install and `workflow/envs/reveal.post-deploy.sh` stands in for it by side-loading REVEAL's newest tagged release: the REVEAL default is therefore unpinned until `reveal-tools` is published — a single run stays consistent, but an environment rebuilt later can pick up a newer REVEAL. See [config/parameters.md](config/parameters.md) and [docs/FAQ.md](docs/FAQ.md)

### Bug Fixes

- **Read-number marker in raw read filenames**: a bare `1`/`2` mid-filename (e.g. `IND001_B_1_box-1-22_R1_001.fastq.gz`) could beat the explicit `R1`/`R2` token and cut the sample ID at the wrong underscore, silently merging two specimens into one sample. `R1`/`R2` now always wins, and `get_raw_reads_for_sample()` raises instead of silently picking one of several matching files
- **Read-number marker still confusable when only the other read's file carried the explicit token**: the fix above only preferred `R1`/`R2` over a bare digit when the *same* filename had that token. A file with only `_R2` (no `_R1` of its own) could still have a bare replicate/box number — e.g. the `_1_` in `..._1_box-3-227_R2.fastq.gz` — mistaken for a bare R1 marker, and its counterpart's `_2_` for a bare R2 marker, silently colliding two different replicates into one phantom sample. The R-form preference is now filename-wide: any explicit `R1`/`R2` token anywhere in the name disables the bare-digit fallback entirely, for both read numbers
- **ECMSD `cov_threshold` default**: the rule fell back to `50` when the key was omitted, while [config/parameters.md](config/parameters.md), the samples, and the config designer all documented `25`. The rule now uses `25` as intended
- **ECMSD samples with no hits**: newer ECMSD writes an empty result table instead of failing when a sample has no hits, and the pipeline now handles that case — the sample is kept as a `none_detected` placeholder row so MultiQC's relative-stacked bargraph still renders, and the per-sample `_ReadLengths.png`/`_Proportions.png` plots ECMSD skips for an empty result are no longer declared rule outputs
- **`pastForward status` false "Interrupted" on a clean finish**: the force-kill check compared the logged progress percentage to the literal string `"100.0"`, but Snakemake only prints a decimal for non-round percentages — a clean 100% finish can log `(100%)` instead of `(100.0%)`, which the string compare rejected. A completed run could therefore be reported as force-killed (SIGKILL/OOM) with a bogus `resume` suggestion. The comparison is now numeric
- **`check`/`preview` misreported ambiguous read filenames as "none found"**: an unresolvable naming conflict (e.g. two bare `_1` markers, or a `_1`/`_2` conflict left on the R2 side of an otherwise-valid `R1`-named pair) raises `ValueError` from `file_manager.py`, but `check.py`'s per-species summary caught it with a bare `except Exception` and printed `Individuals: (none found)` / `Reads: (reads not found)` — indistinguishable from "no files exist at all" and hiding which file was actually the problem. Both spots now catch `ValueError` first and show the real message, matching the pattern already used for Competition FASTA errors

### Changed

- **`contamination` renamed to `taxonomic_screening`**: config key, workflow folders, output folder, and rule names now say what the step measures. The old config key still works (rewritten at startup with a deprecation warning); the output folder `{species}/results/read_module/contamination/` has no fallback, so rename it in existing projects or let pastForward regenerate it. See [config/parameters.md](config/parameters.md)
- **No `config/config.yaml` ships with the pipeline any more**: it is now `config/min_config_sample.yaml`, and `config.yaml` is gitignored so your own config survives a `git pull`. Copy a sample, or generate one with `config/config_designer.html`, before the first run. See [config/README.md](config/README.md)
- **`pipeline.global.skip_existing_files` defaults to `false`** (was `true`), and a warning is logged whenever it is on. Existing outputs were dropped from Snakemake's target list, so changed inputs did not propagate downstream and results could end up inconsistent. See [docs/FAQ.md](docs/FAQ.md)
- **`visualization.settings.individual_plots` defaults to `skip`** (was `plot`): per-individual REVEAL plots are off unless asked for
- **Two outputs moved from `processed/` to `results/`**: the auto-determined SCG library `{species}_relevant_scg.fasta` and the `filter_unmapped_reads` FASTQ/FASTA exports are primary outputs, not intermediates. Move the old folders in existing projects or let pastForward regenerate them. SCG-selector logging now also says whether a previous SCG library was reused or a new one determined
- **MultiQC report wording for ECMSD**: the ECMSD section no longer lists bacteria as an example contaminant — ECMSD screens a mitochondrial database, so bacteria never show up there. It now says so and points at the Centrifuge section
- **REVEAL conda env files renamed** from `reveal_module.{yaml,post-deploy.sh}` to `reveal.{yaml,post-deploy.sh}`, matching the `ecmsd*` naming
- **Run log opens with an ASCII pastForward banner**, so the start of a run is easy to find in a long log

### Docs

- **Update guide**: [docs/update.md](docs/update.md) describes how to move an existing project folder to a newer pastForward version, both for a git clone and for a downloaded zip, plus what to check afterwards. Covers the manual migration needed when coming from a 1.x version (renamed config keys, `raw/` to `input/`, moved result folders) and the `config/config.yaml` handover for updates from before 2.1.0, where that file was still tracked by git. Linked from [README.md](README.md#quick-start) and [config/README.md](config/README.md#step-3-get-pastforward)
- **README overhaul**: "Running the Pipeline" leads with the CLI; direct-`snakemake` usage, flags, backgrounding, and HPC/cluster notes moved to [docs/snakemake.md](docs/snakemake.md)
- **Sample defaults corrected**: `config/max_config_sample.yaml` and `config/config_designer.html` listed `tools.centrifuge.settings.include_human_taxid: true`, while the rule and [config/parameters.md](config/parameters.md) default it to `false`
- **Adapter sequence FAQ corrected**: [docs/FAQ.md](docs/FAQ.md) claimed custom adapters are supplied as a path to a FASTA file. `pipeline.read_module.adapter_removal.settings.adapters_sequences.{r1,r2}` is passed to fastp as `--adapter_sequence`/`--adapter_sequence_r2`, so the value is the sequence itself
- **MultiQC report paths corrected**: [README.md](README.md) pointed at `{species}/results/summary_module/...`, but the rules write to `{species}/results/summary/...`
- **Duplicate paragraph and a broken sentence removed** from [docs/process_overview.md](docs/process_overview.md): the damage-rescaling section repeated its input-BAM selection paragraph, and a bad find/replace had left "ancient and historical DNA and historical DNA is characterised by"

### CI / Maintenance

- `tests/dryrun_scenarios.sh` falls back to `gtimeout` on macOS, which doesn't ship GNU `timeout`
- `file_manager.py` no longer imports `logger` from the stdlib `venv` module and uses `logging.getLogger(__name__)` instead
- Removed dead code and unused imports; consolidated duplicated FASTA-glob discovery in `file_manager.py` and repeated nested config lookups in the expected-output managers

## [2.0.2] - 2026-08-17

> Hotfix released directly from `main`, for projects using the per-species data-location overrides added in 2.0.1. Both fixes are also in `develop`.

### Bug Fixes

- **Reference standardization no longer writes into `input/`**: it used to `os.rename()` the discovered reference in place and let the mapper index rules write into `input/reference_module/`, which could rename away or litter an external, possibly read-only `reference_dir`. It now only symlinks a standardized name into `{species}/processed/reference_module/{reference}/reference/`, and indexing plus every downstream consumer reads from there
- **Standardization symlinks survive moving the project folder**: the reference, feature-library, and SCG-library symlinks resolved their target with a fully canonicalizing `realpath`, baking the external absolute path into the link. All three now use a lexical relative path, matching what `species_paths.py`'s own symlinks already did

## [2.0.1] - 2026-08-10

### New Features

- **Configurable species data locations**: New optional per-species `config.yaml` settings (`species_dir`, `reads_dir`, `reference_dir`, `scg_dir`, `feature_library_dir`, `competition_dir`, `processed_dir`, `results_dir`) let a species' data live outside the project directory instead of the fixed `<species>/{input,processed,results}` layout. pastForward resolves these into symlinks at the conventional locations at startup, so all existing rules/scripts keep working unchanged; when none are set, behavior is identical to before. `processed_dir`/`results_dir` overrides are additionally protected by a new cross-project lock (`.pastforward.lock`, written inside the resolved target) that detects two independent projects resolving to the same output location — separate from, and not cleared by, Snakemake's own `--unlock`. See [config/README.md](config/README.md#storing-species-data-elsewhere) and [docs/FAQ.md](docs/FAQ.md).

### Bug Fixes

- **SCG/feature-library rule collision**: An SCG FASTA legitimately named `scg.fasta` produced the same processed-output path as the generic feature-library rules, raising `AmbiguousRuleException` while building the DAG; the SCG rules' processed path now has one fewer directory segment so the two patterns can never collide, regardless of what a library file is named
- **`scg_selector.execute` default**: Expected-output calculation defaulted this setting to `False`, out of sync with discovery, preview logging, and the docs (all default `True`) — a config that correctly omitted the key would silently skip SCG auto-determination and all of `reveal_module`. Now defaults to `True` as documented
- **DeDup logging**: `dedup_deduplicate_bam_cluster` declared a `log:` file but the shell command never wrote to it; dedup's output is now redirected there

### CI / Maintenance

- `snakemake --lint` backlog fully resolved (zero findings): added missing `log:` directives to 79 rules, missing `conda:` environments to 25 rules, migrated 9 long `run:` blocks into `script:` files, fixed absolute-path false positives, and split mixed rules/functions across 21 files into a new `workflow/rules/common.smk`; a (currently disabled, pending re-enable) `lint.yml` CI workflow was added to keep this clean going forward
- Applied `snakefmt` formatting across all `.smk` files
- Added a fast pure-Python regression test suite (`tests/test_file_manager.py`, `tests/test_expected_output_manager.py`, `tests/test_endogenous_reads_stats.py`) covering discovery and DAG-target logic without needing Snakemake or conda
- New CI workflow stamps a `<base-version>-dev.<timestamp>+<sha>` version on every push to `develop`, so unreleased test runs can be traced to a commit
- Setup docs (`README.md`, `config/README.md`, `docs/FAQ.md`) rewritten as a step-by-step guide for non-technical users, with REVEAL and ECMSD linked as the tools behind core analyses and REVEAL input file placement (feature library, SCG) documented

## [2.0.0]

> ⚠️ NOTE: This release restructures the pipeline's configuration and output layout, renames all four pipeline stages for naming consistency, and replaces the vendored `teplotter` scripts with the standalone [REVEAL](https://github.com/SarahSaadain/REVEAL) toolkit. Existing configs and output directories will need to be updated/reorganized to match.

### Breaking Changes

- **Module renames**: All four pipeline stages are renamed to a consistent `_module` convention: `dynamics` → `reveal_module`, `raw_reads_processing` → `read_module`, `reference_processing` → `reference_module`, `summary_processing` → `summary_module`. Rule/script directories under `workflow/rules/` and `workflow/scripts/` are renamed accordingly (e.g. `dynamics/` → `reveal_module/`, `raw_read/` → `read_module/`, `reads_to_reference/` → `reference_module/`, `processing_summary/` → `summary_module/`); existing configs must update the corresponding `pipeline.*` keys
- **REVEAL as external dependency**: The vendored `teplotter` scripts under `workflow/scripts/dynamics/teplotter/` have been removed. Rules now call the `REVEAL` CLI (new `workflow/envs/reveal_module.yaml` conda environment) instead of invoking local copies of `bam2so.py`, `normalize-so.py`, `estimate-so.py`, `so2plotable.py`, and the plotting/stats/compare scripts. REVEAL isn't published on bioconda yet, so `reveal_module.yaml` currently pins REVEAL's own runtime deps and a post-deploy script (`workflow/envs/reveal_module.post-deploy.sh`) side-loads the pinned REVEAL release into that conda environment automatically; once the `reveal-tools` bioconda package exists, that yaml can go back to a plain `reveal-tools` dependency and the post-deploy script can be deleted, with no rule changes required
- **Config structure**: The former `dynamics.pf_normalization` sub-stage is removed; `reveal_module` settings are now split into `pipeline.reveal_module.visualization.settings` (plot-rendering options), `pipeline.reveal_module.analysis.settings` (`coverage_analysis`, `snp_analysis`, `indel_analysis` toggles), `pipeline.reveal_module.sequence_overview.settings` (bam2so thresholds: `mapping_quality_threshold`, `minimum_count_snp`, `minimum_frequency_snp`, `minimum_count_indel`, `minimum_frequency_indel`), and `pipeline.reveal_module.normalization.settings` (normalize-so thresholds: `end_distance`, `exclude_quantile`)
- **Config structure**: Quality checking settings (`quality_checking_raw`/`trimmed`/`quality_filtered`/`merged`) consolidated under a single `analysis` key — existing configs using the old flat structure must be updated
- **Config structure**: MultiQC output paths now require species and individual level directory structure
- **Config structure**: New `ECMSD` config section, and an updated `MultiQC` section
- **Config structure**: `pipeline.read_module.contamination_analysis` renamed to `pipeline.read_module.contamination`
- **Default mapper changed**: Default aligner switched from `bwa-mem` to `bwa-mem2`
- **Folder structure**: The species input root is now `{species}/input/` (previously `{species}/raw/`); read files now live under `{species}/input/read_module/` (previously `input/reads/`) and reference genomes under `{species}/input/reference_module/` (previously `input/ref/`)
- **Folder structure**: Output directories now include species and individual level subdirectories throughout; `reference_module` results are namespaced under `{species}/results/reference_module/{reference}/...` (previously `{species}/results/{reference}/...` and `{species}/processed/{reference}/...`), with the final per-individual BAM (`_final.bam`) now written to `{species}/results/reference_module/{reference}/mapped/` (previously `{species}/processed/{reference}/mapped/`)
- **Folder structure**: Contamination analysis outputs moved to `{species}/results/read_module/contamination/` (previously `{species}/results/contamination_analysis/`)
- **Config structure**: The Snakemake rule `preseq_c_curve` is now `preseq_complexitiy_curve`, matching the new `pipeline.reference_module.analysis.settings.preseq_complexitiy_curve` toggle (output file names and the underlying `preseq c_curve` command are unchanged)

### New Features

- **`reveal_module`**: The vendored `teplotter` scripts are replaced by the standalone REVEAL toolkit for TE/genomic-feature dynamics normalization, adding cross-library stats combination, plotting options for individual and comparison outputs, flag files for quick sequence checks, SNP/indel statistics calculation and comparison, mean coverage calculation, additional output columns, and gzip-compressed output. Independent `coverage_analysis` (default: on), `snp_analysis` (default: off), and `indel_analysis` (default: off) settings control which per-individual and species-level outputs are generated
- **SCG & feature library mapping**: New analysis mapping reads to a combined single-copy-gene (SCG) and feature library reference (via `minimap2`/`bwa-aln`/`bwa-mem2`) for TE and genomic feature abundance comparisons; SCGs can be auto-determined with BUSCO or supplied as a pre-built FASTA; adds per-individual depth normalization and scoring for SCG ranking, minimum mapping quality and contig-count filtering for SCG/feature library reads, and an option to keep the mapped BAM as a permanent output; inputs now support different file extensions
- **Competitive mapping**: Optional competition FASTA can be combined with the SCG/feature library reference before mapping; reads mapping to competition sequences are filtered out afterwards to reduce false-positive mappings from competing sources (e.g. host genome fragments)
- **Species configuration**: New `execute` option to conditionally include/exclude a species from processing; new species-level settings for individuals, references, and feature libraries (correctly applied across the read, reference, and reveal modules); preview logging now reports counts of references, individuals, samples, feature libraries, and SCG libraries
- **DeDup**: Deduplication now uses a modified DeDup fork for improved performance over upstream DeDup; the fork's jar is pinned and side-loaded automatically into the `dedup` conda environment via a post-deploy script the first time that environment is created (behind a `dedup` command matching upstream bioconda's own wrapper convention); minimum contigs-per-cluster is now configurable (default `1`). If this fork's improvements are ever released under the upstream `dedup` bioconda package, the env's dependency can revert to plain `dedup` with no rule changes needed
- **Config Designer**: New interactive configuration designer to guide pipeline setup, kept in sync with the current module/config structure
- **Configurable mapper selection**: Pipeline now supports `bwa-aln`, `bwa-mem2`, and `minimap2` for reveal and reference processing via config
- **MultiQC refactor**: Restructured data preparation and analytics rules; output paths now include species and individual level directories; added optional `c_curve`, `qualimap`, and `samtools stats` analysis stages; streamlined contamination analysis execution logic for species and individual reports
- **Raw reads analysis settings**: Per-stage quality checking options (raw, trimmed, quality-filtered, merged reads); read count statistics now mandatory output
- **Raw read naming convention**: read files may now use a bare `1`/`2` instead of `R1`/`R2` as the read-number marker (e.g. `Sample_1.fastq.gz` or `Sample_1_001.fastq.gz`), as long as the digit stands alone as its own underscore-delimited segment
- **ECMSD settings**: Pinned to ECMSD `1.2.*`; new `cov_threshold` (minimum % of reference covered) and `top_n` (number of top references to plot) settings, alongside mapping quality and taxonomic hierarchy settings; contamination analysis rule now produces a ranked summary output
- **Unmapped reads handling**: Enhanced post-mapping processing; BAM files now optionally extract or remove unmapped reads; extraction now uses the pre-filter BAM together with `samtools`/`fastx`
- **Centrifuge**: Output compressed with `pigz` and marked as temporary to reduce disk usage
- **Preview logging**: now also reports raw read files found in `input/read_module/` that don't match the R1/R2 naming convention, and uncompressed `.fastq` files (the pipeline only processes `.fastq.gz`), both of which were previously silently ignored
- **Automated version sync**: CI workflow now manages version synchronization automatically
- **README**: Added minimum configuration requirements section
- **Initialize**: Now shows identified files on startup
- **FAQ**: Expanded with adapter removal, pre-processed reads, and DeDup fork guidance

### Bug Fixes

- `file_manager`: Improved error messages for read file retrieval
- Expected raw read outputs now always created even when other pipeline stages are disabled
- `move_rescaled_bam`: output paths for rescaled BAM and index now use temp files to avoid leftover files

---

## [1.0.1] - 2026-04-26

### New Features

- Updated config with dynamics and summary settings

### Bug Fixes

- BAM rules: replaced `mv` with `cp` to prevent data loss; guarded header logging in subprocess mode
- Log paths consolidated to `processed/`; cleaned up f-strings; fixed R scripts
- Git version retrieval now includes error handling and logs process ID

### CI / Maintenance

- Added GitHub Actions workflow for automatic version tagging on main branch
- Added automated release creation
- Version now dynamically set from git tag instead of hardcoded string

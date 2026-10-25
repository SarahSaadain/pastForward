# Changelog

All notable changes to this project will be documented in this file.


## [Unreleased]

### New Features

- **Config validation**: `config.yaml` is now checked against [workflow/schemas/config.schema.yaml](workflow/schemas/config.schema.yaml) at startup, and by `./pastForward check` and `preview` before they create any data-location symlink. Unknown keys, wrong types (e.g. `execute: "false"` as a string) and invalid values (e.g. an unknown `mapper`) now stop the run, with every problem listed at once and a "did you mean" hint for misspelled keys. Before, a misspelled key was silently ignored, so a typo in `execute: false` ran the step anyway. `execute` on `mapping`, `sequence_overview` or `normalization` is now an error too, since those steps always run and the setting never had an effect. A section whose lines are all commented out (e.g. an empty `settings:`) is reported as empty instead of crashing later with an `AttributeError`. When `jsonschema` is not installed, `check`/`preview` print a warning and skip the validation

- **`./pastForward status` shows conda env installs**: a new `Conda envs:` line appears when the run installs conda environments. While running it names the env being installed and how many are done. After the run it shows how many were installed, or which env did not finish

### Changed

- **Faster BAM splitting for deduplication**: each contig cluster now reads only its own contigs through the sorted BAM index. Before, every cluster scanned the whole BAM, so a run with `--cores 32` read every BAM 32 times. The output is the same
- **Plot logs in one place**: the logs of the read-count, coverage, endogenous-read and raw-vs-endogenous plots were written under `processed/`, while the SNP-divergence plot and the REVEAL plots log under `results/` next to their output. They now all log next to the plot under `results/`, and so do their `.benchmark.jsonl` files. Old logs under `processed/.../plots/` are no longer updated
- **Less disk and I/O for pass-through copies**: the final BAM, the rescaled BAM, the final trimmed and quality-filtered reads, and single-sample read merges are now hard links instead of full copies. Input files stay in place. The rules fall back to a copy when the files are on different filesystems. A symlinked input is linked to the file it points to, so a relative symlink does not break. Raw reads passed through when adapter removal is off are still copied: they stay on disk, and a hard link would share their timestamp and could make Snakemake rerun jobs after results are synced or `.snakemake` is deleted
- **Less disk use with `bwa-aln` mapping in the REVEAL module**: the sorted BAM that still holds unmapped reads is now deleted after filtering, as the `bwa-mem2` and `minimap2` outputs already were. Only the filtered BAM is kept per individual and library

### Bug Fixes

- **One definition of endogenous reads**: the endogenous CSV and the raw-and-endogenous plot counted mapped reads after deduplication. The endogenous plot and the MultiQC summary counted them before deduplication. All of them now count mapped reads before deduplication, out of the filtered reads that went into mapping. With deduplication on, the count comes from DeDup and the removed duplicates are added back to the total. With deduplication off, samtools stats is used as before. Projects with deduplication on rerun the endogenous CSV and the raw-and-endogenous plot once
- **SCG mapping no longer gets flags meant for another mapper**: `scg_selector` used to borrow `reveal_module.mapping.settings.mapper_extra_params` even when it used a different mapper. For example, bwa-aln flags went to minimap2, which then also lacked `-ax sr`. The flags are now borrowed only when both steps use the same mapper. Otherwise the SCG mapper's own defaults apply. The default flags for each mapper now live in one helper in `common.smk`
- **`./pastForward doctor --rebuild-envs` no longer deletes envs in use**: it now stops with an error while a tracked run is still active. Wait for the run to finish or stop it with `./pastForward abort`, then retry
- **`--cores=N` now works**: `./pastForward run --cores=8` was rejected and `./pastForward dryrun --cores=8` added `--cores 1` on top. Both now accept the `=` form. `./pastForward status` also reads the core count from it
- **Workflow catalog lint failed on the Snakemake version check**: the Snakemake workflow catalog lints every clone with its own pinned Snakemake (9.21.0), so the `9.26.1` minimum stopped `snakemake --lint` at parse time. The minimum version is no longer checked when `--lint` is passed. Lint runs no jobs, so the older version is safe there. Every other command still requires 9.26.1
- **ECMSD database was rebuilt inside every screening job**: Snakemake treated the database folder as done as soon as it existed, so a partly built folder never reran the setup job. Each screening job then built the missing files itself, and parallel jobs raced on the same files. The setup job now produces the three files ECMSD reads (`mitochondrion_refseq_taxid_masked.fna.gz`, `NCBI_taxdump/nodes.dmp`, `NCBI_taxdump/names.dmp`) at the configured `tools.ecmsd.settings.database` path (default `resources/ecmsd_database`). A missing or partly built database is therefore built once, before any sample is screened. An empty database file found at startup stops the run and names the file: delete it and run again.
- **Wrong config key in the competition FASTA error**: the error for a missing competition FASTA named `pipeline.reveal_module.mapping.competitive_mapping.execute`. It now names the real key, `pipeline.reveal_module.mapping.settings.competitive_mapping`
- **fastp adapter flags**: setting only `adapters_sequences.r1` no longer passes an empty `--adapter_sequence_r2` to fastp for paired-end reads. Each adapter flag is now passed only when its value is set. An empty `adapters_sequences:` line no longer stops the run with an `AttributeError`
- **Clashing reference, feature library and SCG file names now stop the run**: two FASTA files that resolve to the same ID (e.g. `genome.fa` next to `genome.fna`, or `X.0.fna` next to `X_0.fna`) used to be silently reduced to one. More than one SCG file per species used to pick one by chance. Both now fail at startup with an error naming the files. Feature library and SCG clashes only print a warning when `pipeline.reveal_module.execute` is false, since nothing reads those files then
- **Reads placed directly in the species folder were deleted on a real run**: since benchmarking was added (v2.2.0), moving `<species>/<read>` into `<species>/input/read_module/` failed in the benchmark step and Snakemake then deleted the moved file, so the raw read was lost. `prepare_raw_reads` is no longer benchmarked
- **`skip_low_coverage_individuals` hid real REVEAL normalize errors**: any failure of `REVEAL normalize`, such as a corrupt coverage file, was treated as low coverage and the individual was silently excluded. Only the `Insufficient coverage to normalize` error is skipped now. Other errors fail the rule
- **Raw FastQC failed for reads placed directly in the species folder**: the lookup only checked `<species>/input/read_module/`, so it raised before the step that moves the reads there could run. It now also accepts `<species>/<file>`
- **MultiQC species and reference reports had no mapping stats under the default config**: the report inputs read `reference_module.execute` with a default of `False`, so qualimap, samtools stats, preseq and mapDamage were left out. The default is now `True`, as in the rest of the pipeline
- **Per-individual BAM MultiQC report had no breadth-of-coverage section**: it requested `*_depth_coverage_avg.csv`, which MultiQC does not render, instead of `*_coverage_analysis.tsv`. It now uses the same inputs as the other reports. Its qualimap input is also the per-individual copy the other reports use. The four MultiQC report input lists are now built by one shared function
- **Deduplicated BAM sort log no longer overwrites the mapped BAM sort log**: both sort rules wrote `{individual}_{reference}_sorted_bam.log`, so the second one replaced the first one's log and benchmark. The deduplicated sort now writes `{individual}_{reference}_sorted_dedupped_bam.log`
- **`.pastforward.lock` was left behind by `snakemake --lint` and `./pastForward doctor --rebuild-envs`**: the cross-project lock for `processed_dir`/`results_dir` was taken when the workflow loaded, so any call that does not run jobs left it behind. It is now taken only when a real run starts, before its first job, and released when that run ends. If taking a second lock fails for any reason, the locks already taken are released

### CI / Maintenance

- **Removed the unused `prepare_custom_data_depth` rule**: nothing requested its `*_depth_coverage_avg.csv` or `*_depth_coverage_max.csv` outputs. The rule and its script `prepare_custom_data_depth.py` are gone. `summarize_coverage` is unchanged
- **One process-alive check**: the CLI and the cross-project lock had two copies of the same PID check, and the CLI one treated pid 0 or -1 as alive. Both now use the one in `species_paths.py`, which returns not alive for those
- **Dedup cluster input functions share one parser**: `dedup_merge_split_bams_input` and `dedup_merge_split_jsons_input` read the cluster file names in two slightly different ways. Both now use one helper. The cluster files are always `cluster_<int>_<int>.bed`, so the requested files are unchanged
- **Startup log shows the Linux distro name again**: the platform line now ends with the distro (for example `Ubuntu 26.04.1 LTS`), read from `/etc/os-release`. The old `platform.linux_distribution()` call never worked on Python 3.8 or later, and the dead macOS version code is gone (macOS already shows its version in the same line)
- **Dead lines removed from the per-species read count rule**: `combine_counts_per_species` had an unused variable and a `conda:` line. Snakemake ignores `conda:` on `run:` rules, so the rule runs in the main environment as before

## [2.2.0] - 2026-10-06

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

- **`pastForward` CLI**: a wrapper around `snakemake` at the project root. Commands: `run`/`resume` (backgrounded by default), `status`/`abort`/`unlock`, `check`/`preview`, `dryrun`, `doctor` (list/rebuild conda envs), `print-log` and `version`. `run`/`dryrun` write timestamped logs to `logs/`. `check`/`preview` run in-process, so they return in well under a second and do not need Snakemake at all. `preview.py` was renamed to `check.py` to match. See [README.md](README.md#running-the-pipeline). Plain `snakemake` usage moved to [docs/snakemake.md](docs/snakemake.md)
- **Configurable ECMSD/REVEAL version source**: `tools.ecmsd.settings.version_source` and `pipeline.reveal_module.settings.version_source` (both default `conda`) can side-load either tool straight from GitHub instead of its conda build, as `latest_release` or an experimental `dev`. Each value has its own conda env, so switching it rebuilds automatically. For ECMSD, `conda` is the bioconda package `ecmsd=1.*`. REVEAL is not on bioconda yet, so `conda` has no package to install. Instead, `workflow/envs/reveal.post-deploy.sh` side-loads REVEAL's newest tagged release. The REVEAL default is therefore unpinned until `reveal-tools` is published. A single run stays consistent, but an environment rebuilt later can pick up a newer REVEAL. See [config/parameters.md](config/parameters.md) and [docs/FAQ.md](docs/FAQ.md)

### Bug Fixes

- **Read-number marker in raw read filenames**: a bare `1`/`2` in the middle of a filename (e.g. `IND001_B_1_box-1-22_R1_001.fastq.gz`) could win over the explicit `R1`/`R2` token. The sample ID was then cut at the wrong underscore, and two specimens were silently merged into one sample. `R1`/`R2` now always wins, and `get_raw_reads_for_sample()` raises an error instead of silently picking one of several matching files
- **Read-number marker could still be confused when only the other read's file had the explicit token**: the fix above preferred `R1`/`R2` over a bare digit only when the *same* filename had that token. A file with only `_R2` (no `_R1` of its own) could still have a bare replicate or box number mistaken for a bare R1 marker, such as the `_1_` in `..._1_box-3-227_R2.fastq.gz`. Its counterpart's `_2_` could be mistaken for a bare R2 marker. Two different replicates then collided into one phantom sample. The preference now applies to the whole filename: any explicit `R1`/`R2` token anywhere in the name turns off the bare-digit fallback for both read numbers
- **ECMSD `cov_threshold` default**: the rule fell back to `50` when the key was omitted, while [config/parameters.md](config/parameters.md), the sample configs and the config designer all documented `25`. The rule now uses `25`
- **ECMSD samples with no hits**: newer ECMSD writes an empty result table instead of failing when a sample has no hits, and the pipeline now handles that case. The sample is kept as a `none_detected` placeholder row, so MultiQC's relative-stacked bargraph still renders. ECMSD skips the per-sample `_ReadLengths.png`/`_Proportions.png` plots for an empty result, so they are no longer declared rule outputs
- **`pastForward status` showed a false "Interrupted" on a clean finish**: the force-kill check compared the logged progress percentage to the literal string `"100.0"`. Snakemake only prints a decimal for non-round percentages, so a clean finish can log `(100%)` instead of `(100.0%)`, and the string compare rejected it. A completed run could then be reported as force-killed (SIGKILL/OOM), with a bogus `resume` suggestion. The comparison is now numeric
- **`check`/`preview` reported ambiguous read filenames as "none found"**: an unresolvable naming conflict raises `ValueError` from `file_manager.py`. Examples are two bare `_1` markers, or a `_1`/`_2` conflict left on the R2 side of an otherwise valid `R1`-named pair. `check.py`'s per-species summary caught it with a bare `except Exception` and printed `Individuals: (none found)` / `Reads: (reads not found)`. That looked the same as "no files exist at all" and hid which file caused the problem. Both spots now catch `ValueError` first and show the real message, as was already done for Competition FASTA errors

### Changed

- **`contamination` renamed to `taxonomic_screening`**: the config key, workflow folders, output folder and rule names now say what the step measures. The old config key still works and is rewritten at startup with a deprecation warning. The output folder `{species}/results/read_module/contamination/` has no fallback, so rename it in existing projects or let pastForward regenerate it. See [config/parameters.md](config/parameters.md)
- **No `config/config.yaml` ships with the pipeline any more**: it is now `config/min_config_sample.yaml`, and `config.yaml` is gitignored so your own config survives a `git pull`. Before the first run, copy a sample or generate one with `config/config_designer.html`. See [config/README.md](config/README.md)
- **`pipeline.global.skip_existing_files` defaults to `false`** (was `true`), and a warning is logged whenever it is on. Existing outputs were dropped from Snakemake's target list, so changed inputs did not propagate downstream and results could end up inconsistent. See [docs/FAQ.md](docs/FAQ.md)
- **`visualization.settings.individual_plots` defaults to `skip`** (was `plot`): per-individual REVEAL plots are off unless asked for
- **Two outputs moved from `processed/` to `results/`**: the auto-determined SCG library `{species}_relevant_scg.fasta` and the `filter_unmapped_reads` FASTQ/FASTA exports are primary outputs, not intermediates. Move the old folders in existing projects or let pastForward regenerate them. SCG-selector logging now also says whether a previous SCG library was reused or a new one determined
- **MultiQC report wording for ECMSD**: the ECMSD section no longer lists bacteria as an example contaminant. ECMSD screens a mitochondrial database, so bacteria never show up there. The section now says so and points to the Centrifuge section
- **REVEAL conda env files renamed** from `reveal_module.{yaml,post-deploy.sh}` to `reveal.{yaml,post-deploy.sh}`, matching the `ecmsd*` naming
- **Run log opens with an ASCII pastForward banner**, so the start of a run is easy to find in a long log

### Docs

- **Update guide**: [docs/update.md](docs/update.md) explains how to move an existing project folder to a newer pastForward version, for a git clone and for a downloaded zip, and what to check afterwards. It covers the manual migration from a 1.x version (renamed config keys, `raw/` to `input/`, moved result folders). It also covers the `config/config.yaml` handover for updates from before 2.1.0, when git still tracked that file. Linked from [README.md](README.md#quick-start) and [config/README.md](config/README.md#step-3-get-pastforward)
- **README overhaul**: "Running the Pipeline" now starts with the CLI. Direct `snakemake` usage, flags, backgrounding and HPC/cluster notes moved to [docs/snakemake.md](docs/snakemake.md)
- **Sample defaults corrected**: `config/max_config_sample.yaml` and `config/config_designer.html` listed `tools.centrifuge.settings.include_human_taxid: true`, while the rule and [config/parameters.md](config/parameters.md) default it to `false`
- **Adapter sequence FAQ corrected**: [docs/FAQ.md](docs/FAQ.md) said custom adapters are given as a path to a FASTA file. `pipeline.read_module.adapter_removal.settings.adapters_sequences.{r1,r2}` is passed to fastp as `--adapter_sequence`/`--adapter_sequence_r2`, so the value is the sequence itself
- **MultiQC report paths corrected**: [README.md](README.md) pointed to `{species}/results/summary_module/...`, but the rules write to `{species}/results/summary/...`
- **Duplicate paragraph and a broken sentence removed** from [docs/process_overview.md](docs/process_overview.md): the damage-rescaling section repeated its input-BAM selection paragraph, and a bad find/replace had left "ancient and historical DNA and historical DNA is characterised by"

### CI / Maintenance

- `tests/dryrun_scenarios.sh` falls back to `gtimeout` on macOS, which doesn't ship GNU `timeout`
- `file_manager.py` no longer imports `logger` from the stdlib `venv` module and uses `logging.getLogger(__name__)` instead
- Removed dead code and unused imports. Merged the duplicated FASTA-glob discovery in `file_manager.py` and the repeated nested config lookups in the expected-output managers

## [2.0.2] - 2026-08-17

> Hotfix released directly from `main`, for projects using the per-species data-location overrides added in 2.0.1. Both fixes are also in `develop`.

### Bug Fixes

- **Reference standardization no longer writes into `input/`**: it used to `os.rename()` the discovered reference in place, and the mapper index rules wrote into `input/reference_module/`. This could rename away or litter an external, possibly read-only `reference_dir`. It now only symlinks a standardized name into `{species}/processed/reference_module/{reference}/reference/`, and indexing and every later step read from there
- **Standardization symlinks survive moving the project folder**: the reference, feature-library and SCG-library symlinks resolved their target with a fully canonicalizing `realpath`, which baked the external absolute path into the link. All three now use a lexical relative path, as `species_paths.py`'s own symlinks already did

## [2.0.1] - 2026-08-10

### New Features

- **Configurable species data locations**: new optional per-species settings in `config.yaml` (`species_dir`, `reads_dir`, `reference_dir`, `scg_dir`, `feature_library_dir`, `competition_dir`, `processed_dir`, `results_dir`) let a species' data live outside the project directory instead of the fixed `<species>/{input,processed,results}` layout. At startup, pastForward turns these into symlinks at the usual locations, so all existing rules and scripts work unchanged. When none are set, behavior is the same as before. `processed_dir`/`results_dir` overrides are also protected by a new cross-project lock (`.pastforward.lock`, written inside the resolved target). It detects two independent projects that resolve to the same output location. This lock is separate from Snakemake's own `--unlock`, which does not clear it. See [config/README.md](config/README.md#storing-species-data-elsewhere) and [docs/FAQ.md](docs/FAQ.md).

### Bug Fixes

- **SCG/feature-library rule collision**: an SCG FASTA named `scg.fasta` produced the same processed-output path as the generic feature-library rules, so building the DAG raised `AmbiguousRuleException`. The SCG rules' processed path now has one fewer directory level, so the two patterns cannot collide, whatever a library file is named
- **`scg_selector.execute` default**: the expected-output calculation defaulted this setting to `False`, while discovery, preview logging and the docs all default it to `True`. A config that correctly left out the key would silently skip SCG auto-determination and all of `reveal_module`. It now defaults to `True` as documented
- **DeDup logging**: `dedup_deduplicate_bam_cluster` declared a `log:` file, but the shell command never wrote to it. DeDup's output now goes there

### CI / Maintenance

- `snakemake --lint` backlog fully resolved (zero findings): added missing `log:` directives to 79 rules and missing `conda:` environments to 25 rules, moved 9 long `run:` blocks into `script:` files, fixed absolute-path false positives, and split mixed rules and functions across 21 files into a new `workflow/rules/common.smk`. A `lint.yml` CI workflow was added to keep it clean (disabled for now, pending re-enable)
- Applied `snakefmt` formatting across all `.smk` files
- Added a fast pure-Python regression test suite (`tests/test_file_manager.py`, `tests/test_expected_output_manager.py`, `tests/test_endogenous_reads_stats.py`) that covers discovery and DAG-target logic without Snakemake or conda
- New CI workflow stamps a `<base-version>-dev.<timestamp>+<sha>` version on every push to `develop`, so unreleased test runs can be traced to a commit
- Setup docs (`README.md`, `config/README.md`, `docs/FAQ.md`) rewritten as a step-by-step guide for non-technical users. REVEAL and ECMSD are linked as the tools behind the core analyses, and where to place REVEAL input files (feature library, SCG) is documented

## [2.0.0]

> NOTE: This release restructures the pipeline's configuration and output layout, renames all four pipeline stages to one naming scheme, and replaces the vendored `teplotter` scripts with the standalone [REVEAL](https://github.com/SarahSaadain/REVEAL) toolkit. Existing configs and output directories must be updated to match.

### Breaking Changes

- **Module renames**: all four pipeline stages now end in `_module`: `dynamics` → `reveal_module`, `raw_reads_processing` → `read_module`, `reference_processing` → `reference_module`, `summary_processing` → `summary_module`. Rule and script directories under `workflow/rules/` and `workflow/scripts/` are renamed to match (e.g. `dynamics/` → `reveal_module/`, `raw_read/` → `read_module/`, `reads_to_reference/` → `reference_module/`, `processing_summary/` → `summary_module/`). Existing configs must update the matching `pipeline.*` keys
- **REVEAL as external dependency**: the vendored `teplotter` scripts under `workflow/scripts/dynamics/teplotter/` are removed. Rules now call the `REVEAL` CLI (new `workflow/envs/reveal_module.yaml` conda environment) instead of local copies of `bam2so.py`, `normalize-so.py`, `estimate-so.py`, `so2plotable.py` and the plotting/stats/compare scripts. REVEAL isn't on bioconda yet, so `reveal_module.yaml` pins REVEAL's own runtime dependencies, and a post-deploy script (`workflow/envs/reveal_module.post-deploy.sh`) side-loads the pinned REVEAL release into that conda environment automatically. Once the `reveal-tools` bioconda package exists, that yaml can go back to a plain `reveal-tools` dependency and the post-deploy script can be deleted, with no rule changes
- **Config structure**: the former `dynamics.pf_normalization` sub-stage is removed. `reveal_module` settings are now split into `pipeline.reveal_module.visualization.settings` (plot options), `pipeline.reveal_module.analysis.settings` (`coverage_analysis`, `snp_analysis`, `indel_analysis` toggles), `pipeline.reveal_module.sequence_overview.settings` (bam2so thresholds: `mapping_quality_threshold`, `minimum_count_snp`, `minimum_frequency_snp`, `minimum_count_indel`, `minimum_frequency_indel`) and `pipeline.reveal_module.normalization.settings` (normalize-so thresholds: `end_distance`, `exclude_quantile`)
- **Config structure**: quality checking settings (`quality_checking_raw`/`trimmed`/`quality_filtered`/`merged`) now live under a single `analysis` key. Existing configs using the old flat structure must be updated
- **Config structure**: MultiQC output paths now require species and individual level directories
- **Config structure**: new `ECMSD` config section, and an updated `MultiQC` section
- **Config structure**: `pipeline.read_module.contamination_analysis` renamed to `pipeline.read_module.contamination`
- **Default mapper changed**: the default aligner is now `bwa-mem2` instead of `bwa-mem`
- **Folder structure**: the species input root is now `{species}/input/` (previously `{species}/raw/`). Read files now live under `{species}/input/read_module/` (previously `input/reads/`) and reference genomes under `{species}/input/reference_module/` (previously `input/ref/`)
- **Folder structure**: output directories now include species and individual level subdirectories throughout. `reference_module` results are now under `{species}/results/reference_module/{reference}/...` (previously `{species}/results/{reference}/...` and `{species}/processed/{reference}/...`). The final per-individual BAM (`_final.bam`) is now written to `{species}/results/reference_module/{reference}/mapped/` (previously `{species}/processed/{reference}/mapped/`)
- **Folder structure**: contamination analysis outputs moved to `{species}/results/read_module/contamination/` (previously `{species}/results/contamination_analysis/`)
- **Config structure**: the Snakemake rule `preseq_c_curve` is now `preseq_complexitiy_curve`, matching the new `pipeline.reference_module.analysis.settings.preseq_complexitiy_curve` toggle (output file names and the underlying `preseq c_curve` command are unchanged)

### New Features

- **`reveal_module`**: the vendored `teplotter` scripts are replaced by the standalone REVEAL toolkit for TE/genomic-feature dynamics normalization. It adds cross-library stats combination, plotting options for individual and comparison outputs, flag files for quick sequence checks, SNP/indel statistics and comparison, mean coverage calculation, more output columns and gzip-compressed output. Separate `coverage_analysis` (default: on), `snp_analysis` (default: off) and `indel_analysis` (default: off) settings control which per-individual and species-level outputs are generated
- **SCG & feature library mapping**: new analysis that maps reads to a combined single-copy-gene (SCG) and feature library reference (with `minimap2`/`bwa-aln`/`bwa-mem2`) to compare TE and genomic feature abundance. SCGs can be auto-determined with BUSCO or supplied as a pre-built FASTA. Also adds per-individual depth normalization and scoring for SCG ranking, minimum mapping quality and contig-count filtering for SCG/feature library reads, and an option to keep the mapped BAM as a permanent output. Inputs can now use different file extensions
- **Competitive mapping**: an optional competition FASTA can be combined with the SCG/feature library reference before mapping. Reads that map to competition sequences are filtered out afterwards, to reduce false-positive mappings from competing sources (e.g. host genome fragments)
- **Species configuration**: new `execute` option to include or exclude a species from processing. New species-level settings for individuals, references and feature libraries, applied correctly across the read, reference and reveal modules. Preview logging now reports counts of references, individuals, samples, feature libraries and SCG libraries
- **DeDup**: deduplication now uses a modified DeDup fork that performs better than upstream DeDup. The fork's jar is pinned and side-loaded automatically into the `dedup` conda environment by a post-deploy script the first time that environment is created. It runs behind a `dedup` command, matching upstream bioconda's own wrapper convention. The minimum contigs per cluster is now configurable (default `1`). If the fork's changes are ever released in the upstream `dedup` bioconda package, the env can go back to plain `dedup` with no rule changes
- **Config Designer**: new interactive config designer to guide pipeline setup, kept in sync with the current module and config structure
- **Configurable mapper selection**: the pipeline now supports `bwa-aln`, `bwa-mem2` and `minimap2` for reveal and reference processing, chosen in the config
- **MultiQC refactor**: restructured the data preparation and analytics rules. Output paths now include species and individual level directories. Added optional `c_curve`, `qualimap` and `samtools stats` analysis stages. Simplified the contamination analysis logic for species and individual reports
- **Raw reads analysis settings**: quality checking options per stage (raw, trimmed, quality-filtered, merged reads). Read count statistics are now a mandatory output
- **Raw read naming convention**: read files may now use a bare `1`/`2` instead of `R1`/`R2` as the read-number marker (e.g. `Sample_1.fastq.gz` or `Sample_1_001.fastq.gz`), as long as the digit is its own underscore-delimited segment
- **ECMSD settings**: pinned to ECMSD `1.2.*`. New `cov_threshold` (minimum % of reference covered) and `top_n` (number of top references to plot) settings, next to the mapping quality and taxonomic hierarchy settings. The contamination analysis rule now produces a ranked summary output
- **Unmapped reads handling**: unmapped reads can now optionally be extracted from or removed from BAM files after mapping. Extraction uses the pre-filter BAM together with `samtools`/`fastx`
- **Centrifuge**: output is compressed with `pigz` and marked as temporary to save disk space
- **Preview logging**: now also reports raw read files in `input/read_module/` that don't match the R1/R2 naming convention, and uncompressed `.fastq` files (the pipeline only processes `.fastq.gz`). Both were silently ignored before
- **Automated version sync**: a CI workflow now keeps versions in sync automatically
- **README**: added a minimum configuration requirements section
- **Initialize**: now shows the files it found on startup
- **FAQ**: new entries on adapter removal, pre-processed reads and the DeDup fork

### Bug Fixes

- `file_manager`: better error messages for read file retrieval
- Expected raw read outputs are now always created, even when other pipeline stages are disabled
- `move_rescaled_bam`: output paths for the rescaled BAM and index now use temp files to avoid leftover files

---

## [1.0.1] - 2026-04-26

### New Features

- Updated config with dynamics and summary settings

### Bug Fixes

- BAM rules: replaced `mv` with `cp` to prevent data loss, and guarded header logging in subprocess mode
- Log paths consolidated to `processed/`. Cleaned up f-strings and fixed R scripts
- Git version retrieval now has error handling and logs the process ID

### CI / Maintenance

- Added GitHub Actions workflow for automatic version tagging on main branch
- Added automated release creation
- Version is now set from the git tag instead of a hardcoded string

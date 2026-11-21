# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### New Features

- **Report info in every MultiQC report**: two new sections at the bottom. "Tool versions" lists the pastForward, ECMSD and REVEAL versions, how each was installed, and the ECMSD database with its release and download dates. "Where to find the raw results" lists the result folder of every step that is switched on. Existing projects rebuild their MultiQC reports once. After upgrading a tool inside an existing env, delete `resources/tool_versions/` to refresh the versions.
- **New mappers**: `mapper` also takes `bwa-mem3`, `bwa-mem`, `minibwa`, `bowtie` and `bowtie2`, for the reference mapping, the SCG selector and the feature-library mapping. bwa-mem3 is a faster successor of bwa-mem2 with the same alignments plus bug fixes (`--compat=bwa-mem2` in `mapper_extra_params` gives exact legacy output). minibwa is the successor of bwa-mem for short reads, about twice as fast as bwa-mem2, with different alignments. bwa-mem shares the bwa-aln index. bowtie suits reads under about 50 bp, bowtie2 longer ones. The FAQ, `docs/process_overview.md` and the config designer suggest a mapper by read length.
- **Quality trimming**: `read_module.quality_filtering.settings.trim_low_quality: true` trims bases below `trim_quality` (default `2`) from both read ends, like AdapterRemoval `--trimqualities`. Window size is `trim_window_size` (default `1`). Default `false`.
- **Merge overlap setting**: `read_module.adapter_removal.settings.merge_min_overlap` sets the overlap fastp needs to merge a read pair. Default 10 (fastp's own is 30), so more short-insert pairs merge. Existing projects rerun adapter removal and everything after it once. Set `30` for the old behaviour.
- **BAM filtering**: `reference_module.bam_filtering` (default off) keeps only reads with at least `min_mapq` and `min_read_length` in `_final.bam`. QC statistics still use the unfiltered BAM.
- **mapDamage settings**: `damage_rescaling.settings.rescale_seqlength`, `rescale_length_5p` and `rescale_length_3p` set mapDamage's sequence and rescale lengths, with mapDamage's own defaults. `downsample` (default `0`, all reads) fits the damage model on a fraction or number of reads, which saves time on large BAMs. Rescaling still covers every read.
- **Keep intermediate files**: `keep_bam: true` under `mapping`, `deduplication` or `damage_rescaling` keeps that BAM and copies it to `results/reference_module/{reference}/mapped/`. `keep_reads: true` under `adapter_removal` or `quality_filtering` does the same for reads (`results/read_module/reads_trimmed_final/`, `reads_final/`). Steps switched on later then no longer remap or rebuild reads. Default `false`. Switching it on for a finished project redoes that step once.
- **Compressed mapping indexes**: bwa-mem2, bwa-aln and minimap2 indexes are kept as `.gz` (about half the size) and unpacked only when a run maps. Nothing is remapped. If both the index and its `.gz` are gone, the index is rebuilt and every individual remaps.
- **Authenticity table**: `{reference}_authenticity.tsv` in `analytics/species_level/{species}/authenticity/` has one row per individual with endogenous %, duplicate rate, read length, terminal damage, depth, breadth and MAPQ, plus a verdict (`ok`, `check` or `no_data`). Thresholds are `analysis.settings.authenticity_*`. Turn it off with `authenticity_summary: false`. Nothing reruns.
- **Read composition tables**: `{species}_read_composition_by_sample.csv` and `_by_individual.csv` in `results/read_module/statistics/` split adapter-removed reads into merged, unmerged and unpaired. Nothing reruns.
- **Coverage analysis switch**: `reference_module.analysis.settings.coverage_analysis: false` skips the `samtools depth` step with its plots and MultiQC sections. The authenticity table then takes depth and breadth from Qualimap, if it runs. Default `true`.
- **Config validation**: `config.yaml` is checked against `workflow/schemas/config.schema.yaml` at startup, by `check` and `preview`, and by `run`, `resume`, `dryrun` and `touch` before Snakemake starts. Unknown keys, wrong types and invalid values stop the run, all listed at once with "did you mean" hints. Before, a misspelled key was silently ignored. `execute` on `mapping`, `sequence_overview` or `normalization` is now an error, since those steps always run.
- **`./pastForward install`**: checks conda, sets up a Snakemake env (`pastforward`, or an existing `snakemake` env with 9.26.1 or newer), builds every tool env the config needs, and prints the next steps.
- **No `conda activate` needed**: `./pastForward` remembers the last env with snakemake in `~/.config/pastforward/cli.json` and uses it when snakemake is not on PATH. Set `"auto_activate": false` there to turn this off.
- **`./pastForward status` shows conda env installs** while a run builds them.
- **`./pastForward tools link-reference` and `link-feature-library`**: symlink a FASTA, or every FASTA in a folder, into the species' input folders. `-c` links the competition FASTA. `--species` is optional when the project has one species, also for `link-reads`.
- **CLI quips**: some commands print a short joke, in a terminal only. `PASTFORWARD_QUIET=1` hides them.
- **Test data**: `tests/integration/synthetic_project/` is a 4.7 MB synthetic project with known answers. It runs offline in about 10 minutes on 4 cores (`tests/integration/run_synthetic.sh`, then `test_synthetic_run.py`). `tests/integration/real_data_project/download_full_test.sh` builds a real one from two 1800s museum specimens (Shpak et al. 2023). See the README's Test data section.
- **Integration test scripts**: `tests/integration/module_subsets.sh` dry-runs the synthetic project with only some modules on. `compare_with_ref.sh <git-ref>` compares outputs and benchmarks of a git ref with the working tree.

### Changed

- **Default mapper is bwa-mem3** (was bwa-mem2). The two indexes are not compatible. Existing projects that never set `mapper` rebuild the index and remap once. Set `mapper: "bwa-mem2"` to keep the old one. When switching between the two by hand, delete the old index and its `.gz`.
- **DeDup heap default 2000 MB** (was 20000), with up to two retries that double it. In a test, peak memory fell from 10.8 GB to 1.2 GB with identical output. Raise `mem_mb` if the log still shows `OutOfMemoryError` after the last retry. Finished deduplication does not rerun.
- **ECMSD `cov_threshold` default 5** (was 25), so low-coverage samples keep more references.
- **Mapping threads follow `--cores`**: cores are split across mapping jobs (aiming at 16 threads for bwa-mem2, bwa-mem3 and minibwa, 8 for the others) instead of a fixed 10 or 15. `--set-threads` still overrides it. Nothing remaps.
- **Faster mapDamage**: counting and rescaling run in parallel per deduplication cluster (rescale 2 to 4 times faster), with the same reads as one full rescale. With rescaling on, the merged deduplicated BAM is only built when `deduplication.settings.keep_bam` is on. `misincorporation.txt` and `dnacomp.txt` are kept gzipped. Finished projects do not rerun.
- **Balanced deduplication clusters**: contigs are grouped per individual by read count, so one cluster no longer holds most reads, and each cluster reads only its own contigs. Same output. `min_contigs_per_cluster` and `max_contigs_per_cluster` are ignored with a warning. The old `dedup_cluster/clusters/` and `dedup_<start>_<end>/` folders can be deleted.
- **Coverage analysis streams `samtools depth`**: no temporary per-base file (7.9 GB for a 368 Mb genome), up to 10 times faster, identical CSV.
- **Faster read discovery**: a dry run with 300 samples dropped from 48 s to 33 s.
- **Per-rule memory requests in the shipped profile**: 56 rules get `mem_mb` measured from real runs, the rest keep 8000 MB. Check the large mapping requests (up to 128 GB) before a cluster run.
- **Hard links instead of copies** for the final BAM, the rescaled BAM, the final reads and single-sample merges, when on the same filesystem. Raw reads and the kept BAMs and reads in `results/` are still copied.
- **Plot logs moved to `results/`**, next to their plot.
- **Less disk use with `bwa-aln` in the REVEAL module**: the unmapped-read BAM is deleted after filtering.
- **One file per mapper**: mapper rules live in `mappers/<mapper>.smk` in each of the three mapping folders. No behaviour change.

### Removed

- **Unused `plot_coverage_breadth_bins.R`**: nothing called it.

### Bug Fixes

- **Endogenous reads had several definitions**: all outputs now count mapped reads before deduplication, out of the filtered reads that went into mapping, so they never exceed 100%. Projects with deduplication on rerun the endogenous CSV and plot once.
- **Reads placed directly in the species folder were deleted** (since v2.2.0), and raw FastQC failed on them. Reads added there after the first run were ignored. They are now moved into `input/read_module/` on every run, and a name clash stops the run.
- **Quality filtering `min_length` defaults to 30, as documented** (was 15). Existing outputs do not rerun. Use `--forcerun filter_reads_by_quality` to apply it.
- **`filter_unmapped_reads` defaulted to `remove` in the code**, not `keep` as documented.
- **MultiQC reports lacked mapping stats under the default config**, and the per-individual BAM report lacked breadth of coverage.
- **MultiQC "Coverage Overview" depth was too low**: it is now weighted by scaffold length.
- **Coverage output typo**: the MultiQC column `avgerage_depth` is now `average_depth`.
- **Scaffold names in the depth analysis**: a numeric name such as `4` could split into two rows, and names like `NA` were dropped. Delete old coverage CSVs to refresh them.
- **Empty `mapper_extra_params` broke minimap2**. It now falls back to the defaults, so `""` no longer switches off the bwa-aln defaults.
- **SCG mapping got another mapper's flags**: it borrows `reveal_module.mapping` flags only when both steps use the same mapper.
- **Clashing FASTA names stop the run**: `genome.fa` next to `genome.fna`, or several SCG files, used to be silently reduced to one.
- **`skip_low_coverage_individuals` hid real REVEAL errors**. Only `Insufficient coverage to normalize` is skipped now.
- **ECMSD database was rebuilt inside every screening job**. One setup job builds it, and an empty database file stops the run.
- **mapDamage chunks failed on a half-written `.fai`** when several started at once. It is now built once beforehand.
- **Random `get_final_bam` failure "Output ... has older modification time"**: the BAM index is now copied instead of hard-linked.
- **Centrifuge taxon counts** had a bogus `1 taxID` line.
- **fastp adapter flags**: setting only `r1` passed an empty `r2` adapter, and an empty `adapters_sequences:` crashed.
- **bwa-mem3 and minibwa envs did not solve** under strict channel priority.
- **Deduplicated BAM sort log overwrote the mapped BAM sort log.**
- **Two runs could take the cross-project lock at once**. The lock is now created atomically.
- **`.pastforward.lock` was left behind** by `snakemake --lint` and `doctor --rebuild-envs`. It is now taken only for real runs.
- **The CLI trusted a reused PID**, so `abort -f` could kill an unrelated program. The PID is now checked against snakemake.
- **`doctor --rebuild-envs` deleted envs in use**. It now stops during a run.
- **`--cores=N`, `-c8`, `-j8` and `-jall` were not recognised.**
- **Ctrl-C in a foreground run printed a traceback**. It now prints "Interrupted." and the resume command.
- **Unit tests overwrote `~/.config/pastforward/cli.json`**, so `./pastForward` lost its recorded env.
- **MultiQC logo missing** with `snakemake --directory`.
- **Wrong config key in the competition FASTA error.**
- **Workflow catalog lint failed on the version check**. The minimum version is skipped with `--lint`.

### CI / Maintenance

- **ruff, snakefmt and unit tests in CI** (`lint.yml`), plus a `.pre-commit-config.yaml` that runs them and snakemake lint on every commit. All Python was reformatted once with `ruff format`.
- **Test data workflow** (`test-data.yml`) runs the synthetic project. Started by hand only.
- **Unit tests**: `python3 -m unittest discover tests` now finds them (it ran 0 before). The 8 tests that need snakemake moved to `tests/integration/test_cli_snakemake.py`. SCG ranking and the shared `common.smk` helpers are tested.
- **README badges** for the Zenodo DOI and the Lint workflow.
- **Cleanup**: `_setting()` and other `common.smk` helpers replace about 60 copied config lookups. The unused `prepare_custom_data_depth` rule and dead lines are removed. The startup log shows the Linux distro again.

## [2.2.0] - 2026-10-06

### New Features

- **`./pastForward tools create-species`**: creates a species' `input/` folders and prints a `species:` block for `config/config.yaml`. Takes several species at once and leaves existing folders alone
- **`./pastForward tools link-reads`**: `--source <folder> --species <species>` (or `-d`/`-s`) symlinks every `*.fastq.gz`/`*.fq.gz` file into `<species>/input/read_module/`. Existing names are never overwritten, and unusable names are listed in a warning
- **`./pastForward touch`**: wraps `snakemake --touch` to mark existing outputs as up to date, e.g. after copying results from another machine
- **`./pastForward benchmark`**: every rule writes a `*.benchmark.jsonl` file next to its log. The command sums them per rule (wall time, peak memory, core-hours), and `--emit-profile` prints a `set-resources:` block for HPC runs. macOS records wall time only. See [docs/snakemake.md](docs/snakemake.md#benchmarking-a-run)
- **Default workflow profile**: `workflow/profiles/default/profile.yaml` requests 8 GB memory and 4 hours per rule by default, and sets `--keep-going` and `--rerun-trigger mtime`. Cluster jobs no longer fall back to the partition's defaults. See [docs/snakemake.md](docs/snakemake.md#resource-defaults)
- **SNP divergence check**: `pipeline.reference_module.analysis.settings.snp_divergence_check` flags individuals whose divergence from the reference is an outlier in their cohort, which can mean a wrong reference, contamination or a mislabeled individual. Warning only. Methods: `samtools_stats` (default, no extra runtime), `bcftools` (adds heterozygous-call rate) or `both`. Default `false`. See [config/parameters.md](config/parameters.md)
- **`pipeline.reveal_module.normalization.settings.skip_low_coverage_individuals`**: excludes individuals with too little SCG coverage for normalization instead of failing the species. They are listed in `{species}_{feature_library}_excluded_individuals.tsv`. Default `false`
- **Short flags**: `status -w`, `abort -f`, `print-log -l` and `print-log -t [N]`
- **`check` and `preview` take `--configfile`**, merged on top of `config/config.yaml` as Snakemake does for `run`
- **`./pastForward unlock` handles `.pastforward.lock`**: it lists the cross-project locks in `processed_dir`/`results_dir`, and `--cross-project` removes them. A lock whose run is alive on this host is never removed
- **`./pastForward <command> --help`** (or `-h`) shows help for that command. A mistyped command suggests the closest one
- **`config/max_config_modern_sample.yaml`**: example config for modern DNA, like `max_config_sample.yaml` but with deduplication, damage rescaling and damage analysis off

### Changed

- **Sample names keep everything in the read filename except `R1`/`R2`**: text after the read number (e.g. `_set1_lane6`) used to be dropped, so several lanes collapsed into one sample and the run stopped with `has more than one R1 candidate`. Each lane is now its own sample and is still merged per individual. On existing projects with such names, per-sample files get new names, so mapping and later steps rerun. See [config/README.md](config/README.md#naming-your-read-files)
- **`./pastForward status` shows how a run ended**: a `Status:` line (`Running`, `Completed`, `Aborted`, `Failed`, `Interrupted`, ...) replaces the red `PID: ... (not running)`. The progress bar is colored by state. A finished run shows Snakemake's own `Elapsed time`
- **`./pastForward --help` groups commands by task**. Names and flags are unchanged
- **REVEAL is installed from bioconda**: `version_source: "conda"` (the default) installs `reveal-tools=1.*` instead of the newest GitHub release
- **`--software-deployment-method conda` replaces `--use-conda`** in the CLI and docs. The old flag still works. The CLI no longer overrides a deployment flag you pass yourself
- **Read counting is about 4x faster**, using ISA-L instead of Python's `gzip`
- **Snakemake 9.26.1 or newer is required** (was 9.9.0). Older versions can rerun up-to-date jobs (fixed in 9.11, 9.22 and 9.26), read the profile's `runtime` as seconds instead of minutes (9.16.3 to 9.19), and leak benchmark threads that crashed long runs with "Too many open files" (before 9.24). Update with `conda update -n snakemake snakemake`

### Bug Fixes

- **`run --configfile <file>` failed without `config/config.yaml`**, as did `dryrun` and `touch`. A missing `--configfile` file is now reported before Snakemake starts
- **`print-log` could show the wrong log**: a `dryrun` started during a run was shown instead. While a tracked run is going, its log is shown
- **`unlock` left a `.pastforward.lock` behind** when the config sets `processed_dir` or `results_dir`
- **`status --watch` flickered**: it now draws over the previous frame
- **Workflow failed to parse without `config/config.yaml`**, so `snakemake --lint` and the [workflow catalog](https://snakemake.github.io/snakemake-workflow-catalog) reported it as broken. A missing config is now reported with a clear message at run time
- **`dryrun` did not match `run`**: it left out `--rerun-trigger mtime` and could show a near-full rerun that `run` would never do
- **`status` called a tracked dry run force-killed**: `run -n` is now labeled as a dry run
- **`check` could hide read files with unusable names**: it now always prints a `WARNING: reads not used` line with the reason per file
- **`doctor --rebuild-envs` crashed on environments shared by several rules** with `FileNotFoundError`
- **BUSCO SCG library step broke on Snakemake >= 9.17.0** with `ImportError: cannot import name 'snakemake' from 'snakemake.script'` ([#11](https://github.com/SarahSaadain/pastForward/issues/11))
- **`dedup_deduplicate_bam_cluster` lost its log on a crash**: the log was inside an output folder that Snakemake deletes on failure
- **REVEAL conda envs could fail with `libicui18n.so.58: cannot open shared object file`**: the `defaults` channel is removed from the env files. Rebuild old envs with `./pastForward doctor --rebuild-envs reveal`

### Docs

- **FAQ**: new sections on reprocessing cascades, why REVEAL processing does not deduplicate, benchmark files, workflow profiles and SNP divergence status values

### CI / Maintenance

- `workflow/rules/initialize.smk` formatted so the workflow catalog's older snakefmt accepts it
- `workflow/scripts/cli.py` split into a `workflow/scripts/cli/` package
- Three REVEAL library rules write their own log file

## [2.1.0] - 2026-08-20

### New Features

- **`pastForward` CLI**: a wrapper around `snakemake` at the project root. Commands: `run`/`resume` (backgrounded by default), `status`/`abort`/`unlock`, `check`/`preview`, `dryrun`, `doctor` (list/rebuild conda envs), `print-log` and `version`. `run`/`dryrun` write timestamped logs to `logs/`. `check`/`preview` run in-process in under a second without Snakemake. `preview.py` was renamed to `check.py`. See [README.md](README.md#running-the-pipeline). Plain `snakemake` usage moved to [docs/snakemake.md](docs/snakemake.md)
- **Configurable ECMSD/REVEAL version source**: `tools.ecmsd.settings.version_source` and `pipeline.reveal_module.settings.version_source` (default `conda`) can install either tool from GitHub as `latest_release` or an experimental `dev`. Each value has its own conda env, so switching rebuilds automatically. For ECMSD, `conda` is the bioconda package `ecmsd=1.*`. REVEAL was not on bioconda yet, so `conda` side-loaded its newest tagged release through `workflow/envs/reveal.post-deploy.sh`, and an env rebuilt later could pick up a newer REVEAL. See [config/parameters.md](config/parameters.md)

### Bug Fixes

- **Read-number marker in raw read filenames**: a bare `1`/`2` in the middle of a filename (e.g. `IND001_B_1_box-1-22_R1_001.fastq.gz`) could win over the explicit `R1`/`R2` token, cutting the sample ID at the wrong underscore and silently merging two specimens. Any explicit `R1`/`R2` token anywhere in the name now turns off the bare-digit fallback for both read numbers, even when only the other read's file has the token. `get_raw_reads_for_sample()` raises an error instead of silently picking one of several matches
- **ECMSD `cov_threshold` default**: the rule used `50` when the key was omitted, while the docs, sample configs and config designer said `25`. The rule now uses `25`
- **ECMSD samples with no hits**: newer ECMSD writes an empty result table instead of failing. The sample is kept as a `none_detected` placeholder row so MultiQC's stacked bargraph renders. The per-sample `_ReadLengths.png`/`_Proportions.png` plots are no longer declared outputs, since ECMSD skips them for an empty result
- **`status` showed a false "Interrupted" on a clean finish**: the force-kill check compared the progress to the string `"100.0"`, but Snakemake can log `(100%)`. A completed run was reported as killed, with a bogus `resume` suggestion. The comparison is now numeric
- **`check`/`preview` reported ambiguous read filenames as "none found"**: a naming conflict raised `ValueError`, which was swallowed and printed as `Individuals: (none found)`. The real message is now shown

### Changed

- **`contamination` renamed to `taxonomic_screening`** in the config key, workflow folders, output folder and rule names. The old config key still works and is rewritten at startup with a deprecation warning. The output folder `{species}/results/read_module/contamination/` has no fallback: rename it or let pastForward regenerate it
- **No `config/config.yaml` ships with the pipeline**: it is now `config/min_config_sample.yaml`, and `config.yaml` is gitignored so your config survives a `git pull`. Copy a sample or generate one with `config/config_designer.html`. See [config/README.md](config/README.md)
- **`pipeline.global.skip_existing_files` defaults to `false`** (was `true`), and a warning is logged whenever it is on. Existing outputs were dropped from Snakemake's targets, so changed inputs did not propagate and results could be inconsistent. See [docs/FAQ.md](docs/FAQ.md)
- **`visualization.settings.individual_plots` defaults to `skip`** (was `plot`)
- **Two outputs moved from `processed/` to `results/`**: the auto-determined SCG library `{species}/..._relevant_scg.fasta` and the `filter_unmapped_reads` FASTQ/FASTA exports. Move the old folders or let pastForward regenerate them. SCG-selector logging now says whether a previous SCG library was reused
- **MultiQC ECMSD section no longer lists bacteria as an example contaminant**: ECMSD screens a mitochondrial database, so the section now points to Centrifuge for bacteria
- **REVEAL conda env files renamed** from `reveal_module.{yaml,post-deploy.sh}` to `reveal.{yaml,post-deploy.sh}`
- **Run log opens with an ASCII pastForward banner**

### Docs

- **Update guide**: [docs/update.md](docs/update.md) explains how to move a project to a newer version, for a git clone and a zip download. It covers manual migration from 1.x and the `config/config.yaml` handover for updates from before 2.1.0
- **README overhaul**: "Running the Pipeline" starts with the CLI. Direct `snakemake` usage and HPC notes moved to [docs/snakemake.md](docs/snakemake.md)
- **Sample defaults corrected**: `max_config_sample.yaml` and `config_designer.html` listed `tools.centrifuge.settings.include_human_taxid: true`, while the rule and docs default it to `false`
- **Adapter sequence FAQ corrected**: `adapters_sequences.{r1,r2}` is the sequence itself, passed to fastp as `--adapter_sequence`/`--adapter_sequence_r2`, not a path to a FASTA file
- **MultiQC report paths corrected**: the rules write to `{species}/results/summary/...`, not `summary_module/`
- **Fixed [docs/process_overview.md](docs/process_overview.md)**: removed a duplicated paragraph in the damage-rescaling section and a broken sentence

### CI / Maintenance

- `tests/integration/dryrun_scenarios.sh` falls back to `gtimeout` on macOS
- `file_manager.py` uses `logging.getLogger(__name__)` instead of importing `logger` from the stdlib `venv` module
- Removed dead code and unused imports. Merged the duplicated FASTA-glob discovery in `file_manager.py` and repeated config lookups in the expected-output managers

## [2.0.2] - 2026-08-17

> Hotfix released from `main` for projects using the per-species data-location overrides added in 2.0.1. Both fixes are also in `develop`.

### Bug Fixes

- **Reference standardization no longer writes into `input/`**: it used to `os.rename()` the discovered reference in place, and the mapper index rules wrote into `input/reference_module/`. This could rename away or litter an external, possibly read-only `reference_dir`. It now only symlinks a standardized name into `{species}/processed/reference_module/{reference}/reference/`, and indexing and later steps read from there
- **Standardization symlinks survive moving the project folder**: the reference, feature-library and SCG-library symlinks baked the external absolute path into the link. All three now use a lexical relative path

## [2.0.1] - 2026-08-10

### New Features

- **Configurable species data locations**: optional per-species settings (`species_dir`, `reads_dir`, `reference_dir`, `scg_dir`, `feature_library_dir`, `competition_dir`, `processed_dir`, `results_dir`) let a species' data live outside the project directory. At startup they become symlinks at the usual locations, so rules and scripts work unchanged. Without them, behavior is the same as before. `processed_dir`/`results_dir` overrides are protected by a cross-project lock (`.pastforward.lock` inside the resolved target), which detects two projects resolving to the same output location. Snakemake's `--unlock` does not clear it. See [config/README.md](config/README.md#storing-species-data-elsewhere) and [docs/FAQ.md](docs/FAQ.md)

### Bug Fixes

- **SCG/feature-library rule collision**: an SCG FASTA named `scg.fasta` produced the same processed path as the generic feature-library rules, raising `AmbiguousRuleException`. The SCG rules' path has one fewer directory level now
- **`scg_selector.execute` default**: the expected-output calculation defaulted to `False`, while everything else defaults to `True`. A config that left out the key silently skipped SCG auto-determination and all of `reveal_module`
- **DeDup logging**: `dedup_deduplicate_bam_cluster` declared a `log:` file but never wrote to it

### CI / Maintenance

- `snakemake --lint` backlog resolved (zero findings): added `log:` to 79 rules and `conda:` to 25, moved 9 long `run:` blocks into `script:` files, and split mixed rules and functions across 21 files into `workflow/rules/common.smk`. A `lint.yml` workflow keeps it clean (disabled for now)
- Applied `snakefmt` to all `.smk` files
- Added a fast pure-Python test suite (`tests/unit/test_file_manager.py`, `tests/unit/test_expected_output_manager.py`, `tests/unit/test_endogenous_reads_stats.py`) for discovery and DAG-target logic
- New CI workflow stamps a `<base-version>-dev.<timestamp>+<sha>` version on every push to `develop`
- Setup docs (`README.md`, `config/README.md`, `docs/FAQ.md`) rewritten as a step-by-step guide for non-technical users, with REVEAL and ECMSD linked and the REVEAL input locations (feature library, SCG) documented

## [2.0.0]

> NOTE: This release restructures the configuration and output layout, renames all four pipeline stages to one scheme, and replaces the vendored `teplotter` scripts with the standalone [REVEAL](https://github.com/SarahSaadain/REVEAL) toolkit. Existing configs and output directories must be updated.

### Breaking Changes

- **Module renames**: all four stages end in `_module`: `dynamics` → `reveal_module`, `raw_reads_processing` → `read_module`, `reference_processing` → `reference_module`, `summary_processing` → `summary_module`. Folders under `workflow/rules/` and `workflow/scripts/` are renamed to match (`dynamics/` → `reveal_module/`, `raw_read/` → `read_module/`, `reads_to_reference/` → `reference_module/`, `processing_summary/` → `summary_module/`). Update the matching `pipeline.*` config keys
- **REVEAL as external dependency**: the vendored `teplotter` scripts are removed. Rules call the `REVEAL` CLI from a new conda env (`workflow/envs/reveal_module.yaml`). REVEAL was not on bioconda yet, so a post-deploy script (`reveal_module.post-deploy.sh`) side-loaded the pinned release. Once `reveal-tools` is on bioconda, the yaml can depend on it directly and the script can go, with no rule changes
- **Config structure**:
  - The `dynamics.pf_normalization` sub-stage is removed. `reveal_module` settings are split into `visualization.settings` (plot options), `analysis.settings` (`coverage_analysis`, `snp_analysis`, `indel_analysis`), `sequence_overview.settings` (`mapping_quality_threshold`, `minimum_count_snp`, `minimum_frequency_snp`, `minimum_count_indel`, `minimum_frequency_indel`) and `normalization.settings` (`end_distance`, `exclude_quantile`), all under `pipeline.reveal_module`
  - Quality checking settings (`quality_checking_raw`/`trimmed`/`quality_filtered`/`merged`) live under one `analysis` key
  - MultiQC output paths need species and individual level directories
  - New `ECMSD` section and updated `MultiQC` section
  - `pipeline.read_module.contamination_analysis` is now `pipeline.read_module.contamination`
  - Rule `preseq_c_curve` is now `preseq_complexitiy_curve`, matching `pipeline.reference_module.analysis.settings.preseq_complexitiy_curve`. Output file names and the `preseq c_curve` command are unchanged
- **Default mapper**: `bwa-mem2` instead of `bwa-mem`
- **Folder structure**:
  - `{species}/input/` replaces `{species}/raw/`. Reads are in `input/read_module/` (was `input/reads/`) and references in `input/reference_module/` (was `input/ref/`)
  - Output directories include species and individual level subdirectories. `reference_module` results are under `{species}/results/reference_module/{reference}/...` (was `{species}/results/{reference}/...` and `{species}/processed/{reference}/...`)
  - The final per-individual BAM (`_final.bam`) is written to `{species}/results/reference_module/{reference}/mapped/` (was `processed/`)
  - Contamination outputs moved to `{species}/results/read_module/contamination/` (was `{species}/results/contamination_analysis/`)

### New Features

- **`reveal_module`**: REVEAL replaces the vendored `teplotter` scripts for TE/genomic-feature dynamics normalization. It adds cross-library stats combination, plotting options, flag files for quick sequence checks, SNP/indel statistics and comparison, mean coverage calculation, more output columns and gzip output. `coverage_analysis` (default: on), `snp_analysis` (default: off) and `indel_analysis` (default: off) control which outputs are made
- **SCG and feature library mapping**: maps reads to a combined single-copy-gene (SCG) and feature library reference (`minimap2`/`bwa-aln`/`bwa-mem2`) to compare TE and genomic feature abundance. SCGs come from BUSCO auto-determination or a pre-built FASTA. Adds per-individual depth normalization, SCG ranking scores, minimum mapping quality and contig-count filters, an option to keep the mapped BAM, and different file extensions for inputs
- **Competitive mapping**: an optional competition FASTA is combined with the SCG/feature library reference before mapping. Reads mapping to competition sequences are filtered out afterwards, to reduce false positives from competing sources such as host genome fragments
- **Species configuration**: `execute` includes or excludes a species. New species-level settings for individuals, references and feature libraries apply across the read, reference and reveal modules. Preview logging reports counts of references, individuals, samples, feature libraries and SCG libraries
- **DeDup**: deduplication uses a modified DeDup fork that performs better than upstream. Its pinned jar is side-loaded into the `dedup` conda env by a post-deploy script and runs behind a `dedup` command. Minimum contigs per cluster is configurable (default `1`). If the changes reach upstream bioconda `dedup`, the env can go back to plain `dedup` with no rule changes
- **Config Designer**: interactive designer to guide setup, in sync with the current config structure
- **Configurable mapper**: `bwa-aln`, `bwa-mem2` and `minimap2` for reveal and reference processing
- **MultiQC refactor**: restructured data preparation and analytics rules, with species and individual level output paths. Optional `c_curve`, `qualimap` and `samtools stats` stages. Simpler contamination analysis logic
- **Raw reads analysis settings**: quality checking per stage (raw, trimmed, quality-filtered, merged). Read count statistics are mandatory
- **Raw read naming**: a bare `1`/`2` can replace `R1`/`R2` as the read-number marker (e.g. `Sample_1.fastq.gz`, `Sample_1_001.fastq.gz`) when it is its own underscore-delimited segment
- **ECMSD settings**: pinned to ECMSD `1.2.*`. New `cov_threshold` (minimum % of reference covered) and `top_n` (references to plot). The contamination rule produces a ranked summary
- **Unmapped reads handling**: unmapped reads can be extracted from or removed from BAM files after mapping. Extraction uses the pre-filter BAM with `samtools`/`fastx`
- **Centrifuge**: output is compressed with `pigz` and marked temporary
- **Preview logging**: reports raw read files in `input/read_module/` that do not match the R1/R2 convention, and uncompressed `.fastq` files (only `.fastq.gz` is processed). Both were silently ignored before
- **Automated version sync** by a CI workflow
- **README**: minimum configuration requirements section
- **Initialize**: shows the files it found on startup
- **FAQ**: entries on adapter removal, pre-processed reads and the DeDup fork

### Bug Fixes

- `file_manager`: better error messages for read file retrieval
- Expected raw read outputs are always created, even when other stages are disabled
- `move_rescaled_bam`: rescaled BAM and index use temp files to avoid leftovers

## [1.0.1] - 2026-04-26

### New Features

- Updated config with dynamics and summary settings

### Bug Fixes

- BAM rules: replaced `mv` with `cp` to prevent data loss, and guarded header logging in subprocess mode
- Log paths consolidated to `processed/`. Cleaned up f-strings and fixed R scripts
- Git version retrieval has error handling and logs the process ID

### CI / Maintenance

- GitHub Actions workflow for automatic version tagging on main
- Automated release creation
- Version is set from the git tag instead of a hardcoded string

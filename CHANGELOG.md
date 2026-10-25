# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### New Features

- **Config validation**: `config.yaml` is checked against [workflow/schemas/config.schema.yaml](workflow/schemas/config.schema.yaml) at startup, and by `./pastForward check` and `preview` before they create any symlink. Unknown keys, wrong types (e.g. `execute: "false"`) and invalid values (e.g. an unknown `mapper`) stop the run. All problems are listed at once, with a "did you mean" hint for misspelled keys. Before, a misspelled key was silently ignored. `execute` on `mapping`, `sequence_overview` or `normalization` is now an error, since those steps always run. An empty section (e.g. `settings:` with every line commented out) is reported instead of crashing later. Without `jsonschema` installed, `check`/`preview` warn and skip validation.
- **Read composition after adapter removal**: `{species}_read_composition_by_sample.csv` and `{species}_read_composition_by_individual.csv` in `results/read_module/statistics/` split adapter-removed reads into merged, unmerged and unpaired (or single-end), with counts and percent. They are built from the fastp JSON and the existing read count, so nothing reruns. With adapter removal off, paired-end reads count as unmerged. A mismatch between the fastp report and the read count stops the step.
- **Authenticity triage table**: `{reference}_authenticity.tsv` in `results/reference_module/{reference}/analytics/species_level/{species}/authenticity/` has one row per individual: endogenous %, duplicate rate, mapped read length, 5' C-to-T and 3' G-to-A at position 1, mean depth, breadth and mean MAPQ. The `verdict` column is `ok`, `check` (`verdict_reason` names the threshold) or `no_data` (a file was missing). Thresholds are `pipeline.reference_module.analysis.settings.authenticity_*`. `authenticity_summary: false` turns it off. It only reads files other steps already keep, so nothing reruns. Columns of switched-off steps are `NA`.
- **`./pastForward status` shows conda env installs**: a `Conda envs:` line names the env being installed and how many are done. After the run it shows how many were installed, or which one did not finish.

### Changed

- **ECMSD `cov_threshold` default lowered to 5**: was 25. Low-coverage samples, typical for ancient DNA, kept fewer references. Set `tools.ecmsd.settings.cov_threshold` to keep the old value. Existing projects rerun ECMSD only if the config sets no value and the rule reruns for another reason
- **Faster BAM splitting for deduplication**: each contig cluster reads only its own contigs through the BAM index, instead of scanning the whole BAM. Output is the same.
- **Plot logs in one place**: logs and `.benchmark.jsonl` files of the read-count, coverage, endogenous-read and raw-vs-endogenous plots moved from `processed/` to `results/`, next to the plot. Old logs under `processed/.../plots/` are no longer updated.
- **Hard links for pass-through copies**: the final BAM, the rescaled BAM, the final trimmed and quality-filtered reads, and single-sample read merges are hard links instead of copies. A copy is used when the files are on different filesystems. Raw reads passed through with adapter removal off are still copied, since a shared timestamp could make Snakemake rerun jobs after a sync.
- **Less disk use with `bwa-aln` in the REVEAL module**: the sorted BAM holding unmapped reads is deleted after filtering, as for `bwa-mem2` and `minimap2`.
- **Coverage analysis reads the depth file once**: run time drops by about a quarter (54 s to 40 s on a 200 Mb genome). Progress is logged every 100 million positions.

### Removed

- **Unused `plot_coverage_breadth_bins.R`**: nothing called it.

### Bug Fixes

- **Typos in coverage outputs**: the MultiQC column `avgerage_depth` is now `average_depth`, and the breadth violin plot axis reads "Breadth Coverage". Update anything that reads the old column name.
- **`filter_unmapped_reads` default action is `keep` in the code too**: docs and schema said `keep`, but the code used `remove` when `settings.action` was missing. Set `action: remove` for a mapped-only BAM.
- **MultiQC "Coverage Overview" depth was too low**: it was a plain mean over scaffolds, so many small scaffolds (dm6 has 1,870) pulled it down. It is now weighted by scaffold length, like the combined coverage CSV and the authenticity table.
- **Scaffold names in the depth analysis**: names were read in chunks with guessed types, so a numeric name such as `4` could split into two rows, and `NA`, `nan`, `null` or `N/A` was dropped. Names are now always text. Delete the old coverage analysis CSVs and summaries to refresh them, since Snakemake does not rerun on script changes.
- **Empty `mapper_extra_params` broke minimap2**: `""` replaced the mapper defaults with nothing, so minimap2 wrote PAF instead of SAM. An empty value now falls back to the defaults. `""` can no longer switch off the bwa-aln defaults (`-n 0.01 -k 2 -l 1024 -o 2`): set the flags you want instead.
- **One definition of endogenous reads**: all outputs now count mapped reads before deduplication, out of the filtered reads that went into mapping. With deduplication on, removed duplicates are added back to the mapped count and the total. DeDup's own count is not used, since it includes secondary and supplementary alignments and could exceed 100%. The endogenous plot and the MultiQC chart take the total from the endogenous CSV (new `mapped_input_reads` column). Projects with deduplication on rerun the endogenous CSV and the raw-and-endogenous plot once.
- **SCG mapping got flags meant for another mapper**: `scg_selector` borrowed `reveal_module.mapping.settings.mapper_extra_params` even with a different mapper. It now borrows them only when both steps use the same mapper. Defaults for each mapper live in one helper in `common.smk`.
- **`./pastForward doctor --rebuild-envs` deleted envs in use**: it now stops while a tracked run is active.
- **`--cores=N` and `-c8` now work**: `--cores=8`, `-c8`, `-j8` and `-jall` were not recognised, and `dryrun` added `--cores 1` on top. `run`, `resume`, `dryrun` and `status` now read them.
- **Workflow catalog lint failed on the Snakemake version check**: the catalog lints with Snakemake 9.21.0. The 9.26.1 minimum is now skipped when `--lint` is passed.
- **ECMSD database was rebuilt inside every screening job**: Snakemake treated an existing database folder as done, so parallel jobs raced to build the missing files. The setup job now produces the three files ECMSD reads (`mitochondrion_refseq_taxid_masked.fna.gz`, `NCBI_taxdump/nodes.dmp`, `NCBI_taxdump/names.dmp`) at `tools.ecmsd.settings.database` (default `resources/ecmsd_database`). An empty database file at startup stops the run and names the file.
- **Wrong config key in the competition FASTA error**: it now names `pipeline.reveal_module.mapping.settings.competitive_mapping`.
- **fastp adapter flags**: setting only `adapters_sequences.r1` no longer passes an empty `--adapter_sequence_r2`. An empty `adapters_sequences:` no longer raises `AttributeError`.
- **Clashing reference, feature library and SCG file names stop the run**: two FASTA files with the same ID (e.g. `genome.fa` and `genome.fna`) used to be reduced to one, and several SCG files picked one by chance. Both now fail at startup and name the files. Feature library and SCG clashes only warn when `pipeline.reveal_module.execute` is false.
- **Reads placed directly in the species folder were deleted**: since v2.2.0, moving `<species>/<read>` into `<species>/input/read_module/` failed in the benchmark step, and Snakemake deleted the moved file. `prepare_raw_reads` is no longer benchmarked.
- **`skip_low_coverage_individuals` hid real REVEAL normalize errors**: any failure, such as a corrupt coverage file, excluded the individual. Only `Insufficient coverage to normalize` is skipped now.
- **Raw FastQC failed for reads placed directly in the species folder**: the lookup now also accepts `<species>/<file>`.
- **MultiQC reports lacked mapping stats under the default config**: `reference_module.execute` defaulted to `False` in the report inputs, which left out qualimap, samtools stats, preseq and mapDamage. The default is now `True`.
- **Per-individual BAM MultiQC report had no breadth-of-coverage section**: it requested `*_depth_coverage_avg.csv` instead of `*_coverage_analysis.tsv`, and used a different qualimap input than the other reports. All four report input lists now come from one function.
- **Deduplicated BAM sort log overwrote the mapped BAM sort log**: the deduplicated sort now writes `{individual}_{reference}_sorted_dedupped_bam.log`.
- **`.pastforward.lock` was left behind by `snakemake --lint` and `./pastForward doctor --rebuild-envs`**: the lock is now taken only when a real run starts and released when it ends. If a second lock cannot be taken, the first is released.

### CI / Maintenance

- **Shared helpers in `common.smk`**: `_dedup_enabled`, `_mapper_extra` and `_scg_mapper_and_extra` replace repeated code in the rule files. The SCG mapper choice is unit tested in `tests/test_common_helpers.py`. Behaviour is unchanged.
- **Removed the unused `prepare_custom_data_depth` rule** and its script. Nothing requested its outputs.
- **One process-alive check** in `species_paths.py`, used by the CLI and the cross-project lock. pid 0 or -1 now count as not alive.
- **Dedup cluster input functions share one parser**: the requested files are unchanged.
- **Startup log shows the Linux distro name again**, read from `/etc/os-release`.
- **Dead lines removed from `combine_counts_per_species`**: an unused variable and a `conda:` line that Snakemake ignores on `run:` rules.

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

- `tests/dryrun_scenarios.sh` falls back to `gtimeout` on macOS
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
- Added a fast pure-Python test suite (`tests/test_file_manager.py`, `tests/test_expected_output_manager.py`, `tests/test_endogenous_reads_stats.py`) for discovery and DAG-target logic
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

---

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

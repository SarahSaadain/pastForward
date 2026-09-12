# Configuration Parameters

Full reference of all `config.yaml` settings and their defaults. See [README.md](README.md) for setup instructions and the minimal config, or [max_config_sample.yaml](max_config_sample.yaml) for a fully-commented example config using every available setting.

## Global Settings

* **project\_name**: Name of the project.

## Pipeline Settings

Defines the overall pipeline behavior, including execution controls and process details.

### Pipeline Stages and Process Steps

* The pipeline is broken into **stages** (e.g., `read_module`, `reference_module`).
* Each stage contains multiple **process steps** (e.g., `adapter_removal`, `deduplication`, ...).
* Both stages and process steps can be controlled with `execute: true/false` flags to enable or disable them.
* Some process steps include additional configurable settings (e.g., adapter sequences, database paths, ...).
* If an enabled process step requires data from a previous stage which is disabled in the config, the pipeline will execute the disabled process step anyway.

### Important Defaults

* You **do not need to specify all stages or process steps** explicitly.
* Any **stage or process step not provided in the config defaults to `execute: true`** and will be executed.

### Global Pipeline Settings

| Setting | Default | Description |
|---|---|---|
| `pipeline.global.skip_existing_files` | `false` | When true, output files that already exist are not requested from Snakemake, so they are never re-computed. This also means changed input files do not propagate to existing downstream outputs, which can leave results inconsistent. Keep it `false` to use Snakemake's normal re-run behaviour. |

### Stage: `read_module`

Quality checking, adapter removal, quality filtering, merging, taxonomic screening, and read count statistics of raw reads.

> **Read count statistics always run.** Per-stage counts (raw → trimmed → quality-filtered) are written unconditionally as `{species}/results/read_module/statistics/{species}_reads_counts.csv`.

#### `analysis`

Controls FastQC + MultiQC quality reports at each processing stage and read count visualisation. Individual stages are toggled via `settings`.

| Setting | Default | Description |
|---|---|---|
| `settings.multiqc_raw_reads` | on | FastQC/MultiQC on raw reads. |
| `settings.multiqc_trimmed_reads` | on | FastQC/MultiQC on adapter-trimmed reads. |
| `settings.multiqc_quality_filtered_reads` | on | FastQC/MultiQC on quality-filtered reads. |
| `settings.multiqc_merged_reads` | on | FastQC/MultiQC on merged per-individual reads. |
| `settings.create_plots` | on | Generate read count bar plots per species. |

#### `adapter_removal`

| Setting | Default | Description |
|---|---|---|
| `settings.min_quality` | `0` | Minimum base quality score for adapter trimming. |
| `settings.min_length` | `0` | Minimum read length after adapter removal. |
| `settings.poly_x_min_len` | `5` | Minimum length to trigger poly-X tail trimming. |
| `settings.unqualified_percent_limit` | `40` | Max percentage of unqualified bases allowed in a read. |
| `settings.n_base_limit` | `5` | Max number of N bases allowed in a read. |
| `settings.adapters_sequences.r1` | auto-detect | Adapter sequence for read 1. If omitted, fastp detects adapters automatically. |
| `settings.adapters_sequences.r2` | auto-detect | Adapter sequence for read 2. If omitted, fastp detects adapters automatically. |
| `settings.extra_params` | — | Optional extra parameters passed directly to fastp. |

#### `quality_filtering`

| Setting | Default | Description |
|---|---|---|
| `settings.min_quality` | `15` | Minimum base quality score for quality filtering. |
| `settings.min_length` | `30` | Minimum read length after quality filtering. |
| `settings.unqualified_percent_limit` | `40` | Max percentage of unqualified bases allowed in a read. |
| `settings.n_base_limit` | `5` | Max number of N bases allowed in a read. |

#### `taxonomic_screening`

Both tools operate on quality-filtered reads and can be toggled independently. Reads are classified against a
reference database, and the resulting taxon proportions are used to judge how much of a sample is exogenous
(contaminating) DNA.

> Renamed from `contamination`. The old key still works and is rewritten to `taxonomic_screening`
> at startup, with a deprecation warning in the log.

**ECMSD** maps reads against a curated mitochondrial reference database.

| Setting | Default | Description |
|---|---|---|
| `tools.ecmsd.settings.version_source` | `conda` | Where to get the ECMSD binary. `conda` uses the bioconda-packaged `ecmsd=1.*` release (`workflow/envs/ecmsd.yaml`); `latest_release` always side-loads the newest tagged release from [capoony/ECMSD](https://github.com/capoony/ECMSD) (`ecmsd_git_release.yaml`); `dev` **(experimental)** side-loads the tip of ECMSD's `development` branch, unreleased and untested (`ecmsd_git_development.yaml`). Each value has its own conda env, so switching it builds or reuses that env automatically. Picking up a newer release/commit on an already-built unpinned env still needs a manual rebuild, see [FAQ.md](FAQ.md). |
| `tools.ecmsd.settings.database` | — | Path to the ECMSD database folder. If omitted, the pipeline auto-creates a database at `resources/ecmsd_database` via `ECMSD --create-db`. |
| `tools.ecmsd.settings.cov_threshold` | `25` | Minimum % of reference covered by reads to retain it. |
| `tools.ecmsd.settings.top_n` | `25` | Number of top references to generate alignment plots for. |
| `tools.ecmsd.settings.mapping_quality` | `20` | Minimum mapping quality score to include a read. |
| `tools.ecmsd.settings.taxonomic_hierarchy` | `species` | Taxonomic level at which to aggregate and report results. Options: `species`, `genus`, `family`, `order`. |

**Centrifuge** does k-mer-based taxonomic classification against a user-provided database.

| Setting | Default | Description |
|---|---|---|
| `tools.centrifuge.settings.include_human_taxid` | `false` | When true, the human taxid is included in the Centrifuge analysis. |
| `tools.centrifuge.settings.index` | — | Optional path to the Centrifuge index prefix. If omitted, the default index will be downloaded automatically. |
| `tools.centrifuge.settings.conda_env` | — | Optional path to a custom conda environment for Centrifuge. |

### Stage: `reference_module`

Mapping, deduplication, damage analysis, and coverage. Runs per individual per reference.

#### `mapping`

Merged per-individual reads are mapped to the reference genome. Mapping always runs when Reference Processing is enabled.

| Setting | Default | Description |
|---|---|---|
| `settings.mapper` | `bwa-mem2` | Mapper to use. Options: `bwa-aln` (classic seed-and-extend), `bwa-mem2` (default), `minimap2` (versatile, uses `-ax sr` preset for short reads). |
| `settings.mapper_extra_params` | — | Optional extra parameters passed directly to the mapper. For `bwa-aln`, defaults to `-n 0.01 -k 2 -l 1024 -o 2` (Oliva et al. 2021). |

#### `deduplication`

Removes PCR and sequencing duplicates using DeDup. Default: **on**.

Uses a [modified DeDup fork](https://github.com/SarahSaadain/DeDup) for performance improvements over upstream DeDup ([benchmark comparison repo](https://github.com/SarahSaadain/DeDup_comparison_fork)).

| Setting | Default | Description |
|---|---|---|
| `settings.min_contigs_per_cluster` | `1` | Minimum number of contigs grouped into a cluster. Small contigs below this count are merged together before deduplication. |
| `settings.max_contigs_per_cluster` | `500` | Maximum number of contigs grouped per deduplication cluster. Lower values use less memory but increase runtime. Reduce (e.g. to 100) only for large, highly fragmented reference genomes. |
| `settings.mem_mb` | `20000` | Memory (MB) for DeDup's JVM heap (`-Xms`/`-Xmx`), also requested from the cluster scheduler as `resources.mem_mb`. Increase for large reference genomes/BAM files; decrease for small ones to free up cluster resources. |

#### `filter_unmapped_reads`

Optionally removes or extracts reads that did not map to the reference. Default: **off**.

| Setting | Default | Description |
|---|---|---|
| `settings.action` | `keep` | What to do with unmapped reads: `keep` retains them in the final BAM (default, must be changed explicitly), `remove` writes a mapped-reads-only BAM, `extract_fastq` writes unmapped reads to a compressed FASTQ, `extract_fasta` writes unmapped reads to a compressed FASTA. |

#### Other `reference_module` steps

| Step | Default | Description |
|---|---|---|
| `damage_rescaling` | on | Profiles cytosine deamination and rescales base quality scores using mapDamage2. |
| `analysis` | on | Computes coverage breadth and mean depth; runs Qualimap and Preseq. Endogenous content data always generated. |
| `analysis.settings.damage_analysis` | on | Visualises damage patterns (mapDamage2) and includes them in the MultiQC report. |
| `analysis.settings.create_plots` | on | Generate coverage breadth/depth and endogenous reads plots per reference. |
| `analysis.settings.individual_multiqc` | on | Generate a per-individual BAM MultiQC report. |
| `analysis.settings.species_multiqc` | on | Generate a per-reference MultiQC report aggregating all individuals. |
| `analysis.settings.preseq_complexitiy_curve` | on | Include Preseq complexitiy_curve complexity data in MultiQC reports. |
| `analysis.settings.qualimap` | on | Include Qualimap BAM QC data in MultiQC reports. |
| `analysis.settings.samtools_stats` | on | Include samtools stats data in MultiQC reports. |
| `analysis.settings.qualimap_mem_mb` | `4096` | Memory (MB) requested from the cluster scheduler for Qualimap. Increase for large reference genomes/BAM files; decrease for small ones to free up cluster resources. |
| `analysis.settings.snp_divergence_check` | `false` | When `true`, measure how far each individual diverges from the reference and flag individuals whose divergence is a cohort outlier. Flags a possible wrong reference genome, cross-species contamination, or mislabeled individual. Warning only, the run continues. Unrelated to `reveal_module`'s `snp_analysis`. |
| `analysis.settings.snp_divergence_method` | `samtools_stats` | How the divergence number is obtained. `samtools_stats` reuses the per-individual samtools stats file that is already produced (mismatches / bases mapped), costs no extra runtime and adds no dependency, but gives no heterozygous-call rate. `bcftools` calls SNPs per individual, adding the heterozygous-call rate and a MultiQC panel at real runtime cost. |
| `analysis.settings.snp_divergence_outlier_zscore` | `3.5` | Modified z-score above which an individual is flagged. Only the high side is flagged. |
| `analysis.settings.snp_divergence_min_callable_bases` | `100000` | Individuals with fewer callable bases are reported as `insufficient_data` instead of being scored, and are left out of the cohort median. |
| `analysis.settings.snp_divergence_target_bases` | `10000000` | `bcftools` method only. Reference bases to call per individual, so runtime scales with this budget instead of genome size. The same region set is used for every individual. `0` uses the whole reference. |
| `analysis.settings.snp_divergence_min_contig_length` | `10000` | `bcftools` method only. Contigs shorter than this are never picked for the region set. |
| `analysis.settings.snp_divergence_min_depth` | `3` | `bcftools` method only. Minimum read depth for a site to count toward SNP density. |
| `analysis.settings.snp_divergence_max_depth` | `50` | `bcftools` method only. Maximum per-site depth passed to `bcftools mpileup --max-depth`. |
| `analysis.settings.snp_divergence_min_mapping_quality` | `30` | `bcftools` method only. Minimum mapping quality passed to `mpileup --min-MQ` and `samtools depth --min-MQ`. |
| `analysis.settings.snp_divergence_min_base_quality` | `30` | `bcftools` method only. Minimum base quality passed to `mpileup --min-BQ` and `samtools depth --min-BQ`. |

The `status` column of `{reference}_combined_snp_divergence.csv` holds one of four values:

| Status | Meaning |
|---|---|
| `ok` | Scored against the cohort and not an outlier. |
| `outlier` | Scored against the cohort with a modified z-score above `snp_divergence_outlier_zscore`. Check the reference genome, cross-species contamination, and whether the individual is mislabeled. |
| `insufficient_data` | Fewer callable bases than `snp_divergence_min_callable_bases`. The individual is not scored and does not affect the cohort median. |
| `insufficient_cohort` | The individual has enough callable bases, but fewer than three usable individuals were mapped to this reference. The score is cohort relative, and the median and MAD carry no information below three individuals, so no individual is scored and nothing is flagged. This minimum of three is fixed and not configurable. |

### Stage: `reveal_module`

TE and genomic feature abundance analysis. Maps to a combined SCG + feature library for depth-normalised comparisons.

Place feature libraries in `{species}/input/reveal_module/feature_library/` and, optionally, a pre-built SCG FASTA in `{species}/input/reveal_module/scg/`. If no SCG FASTA is provided and `scg_selector.execute` is `true`, SCGs are determined automatically via BUSCO (requires a lineage configured per species). To use competitive mapping, place a single competition FASTA in `{species}/input/reveal_module/competition/`.

| Setting | Default | Description |
|---|---|---|
| `settings.version_source` | `conda` | Where to get the REVEAL toolkit. `conda` takes REVEAL from the bioconda package `reveal-tools=1.*` (`reveal.yaml`). `latest_release` side-loads the newest tagged release from [SarahSaadain/REVEAL](https://github.com/SarahSaadain/REVEAL) instead (`reveal_git_release.yaml`). `dev` **(experimental)** side-loads the tip of REVEAL's `develop` branch, unreleased and untested (`reveal_git_development.yaml`). Each value has its own conda env, so switching it builds or reuses that env automatically. Picking up a newer release/commit on an already-built unpinned `latest_release`/`dev` env still needs a manual rebuild, see [FAQ.md](FAQ.md). |

#### `scg_selector`

Automatically identifies single-copy genes (SCGs) from the reference genome using BUSCO. SCGs serve as coverage normalisers for the REVEAL pipeline. Skipped automatically when a user-provided SCG FASTA is already present in `{species}/input/reveal_module/scg/` or when no BUSCO lineage is configured for the species.

Can also be used standalone (without feature libraries) to produce an SCG ranking table as the sole output.

| Setting | Default | Description |
|---|---|---|
| `execute` | `true` | Enable SCG auto-determination when no user-provided FASTA is present. |
| `settings.mapper` | *(inherits from `reveal_module.mapping.settings.mapper`)* | Mapper for reads-to-SCG-library mapping. Uncomment to override. Options: `bwa-mem2`, `bwa-aln`, `minimap2`. |
| `settings.mapper_extra_params` | *(inherits from `reveal_module.mapping.settings.mapper_extra_params`)* | Optional extra parameters for the mapper. Falls back to mapper-specific defaults if not set. |
| `settings.num_top_scgs` | `20` | Number of top-ranked SCGs to retain as normalisers. |
| `settings.min_length_scg` | `4000` | Minimum SCG sequence length in bp to include from BUSCO results. |
| `settings.max_length_scg` | `8000` | Maximum SCG sequence length in bp to include from BUSCO results. |
| `settings.min_mapq` | `0` | Minimum mapping quality for reads in the SCG library BAM. Reads with MAPQ below this value are removed after unmapped-read removal. The same threshold is applied when computing per-contig coverage stats for ranking. Set to `0` (default) to disable MAPQ filtering. |
| `settings.keep_mapped_bam` | `false` | When `true`, the filtered sorted SCG BAM and its index (`{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.bam[.bai]`) are kept as permanent outputs. When `false` (default), they are marked as temporary and deleted after SCG ranking consumes them. |

**Per-species SCG settings** (directly under `species.<key>`):

| Setting | Default | Description |
|---|---|---|
| `lineage` | — | **Required** for SCG auto-determination. BUSCO lineage database name (e.g. `drosophilidae_odb12`). Browse available lineages at [busco.ezlab.org](https://busco.ezlab.org/). |
| `scg_reference` | auto-detect | Path to the reference genome to use for BUSCO. Required when multiple FASTA files exist in `{species}/input/reference_module/`; if only one is present it is auto-detected and logged. |

#### `mapping`

| Setting | Default | Description |
|---|---|---|
| `settings.mapper` | `bwa-mem2` | Mapper for feature-library mapping. Same options as `reference_module.mapping`. |
| `settings.mapper_extra_params` | — | Optional extra parameters passed directly to the mapper. |
| `settings.keep_mapped_bam` | `false` | When `true`, the filtered sorted BAM and its index (`{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam[.bai]`) are kept as permanent outputs and explicitly requested by the pipeline. When `false` (default), they are marked as temporary and deleted after REVEAL consumes them. Set to `true` to inspect the mapped BAM or to run the mapping step independently of REVEAL. |
| `settings.min_mapq_scg` | `0` | Minimum mapping quality applied selectively to SCG sequences (`_scg` suffix) in the combined library BAM. Reads mapping to SCG references with MAPQ below this value are removed after mapping. Feature library reads are not affected. Set to `0` (default) to disable. |
| `settings.min_mapq_fle` | `0` | Minimum mapping quality applied selectively to feature library sequences (`_fle` suffix) in the combined library BAM. Reads mapping to feature references with MAPQ below this value are removed after mapping. SCG reads are not affected. Set to `0` (default) to disable. |

#### `competitive_mapping`

Competitive mapping adds a competition FASTA to the combined reference (alongside SCG and feature library sequences) before mapping. Reads mapping to competition sequences are removed after mapping, so only SCG and feature library reads reach downstream analysis. This is useful for reducing false-positive mappings when reads originate from competing sources (e.g. a host genome fragment).

To use competitive mapping, place exactly one FASTA file in `{species}/input/reveal_module/competition/`. The pipeline auto-discovers it, so no path needs to be specified in the config.

Competition sequences are internally suffixed with `_comp` to distinguish them from SCG (`_scg`) and feature library (`_fle`) sequences.

| Setting | Default | Description |
|---|---|---|
| `settings.competitive_mapping` | `false` | When `true`, the FASTA in `{species}/input/reveal_module/competition/` is included in the combined reference. Reads mapping to `_comp` sequences are filtered out after mapping. |

#### Other `reveal_module` steps

| Step / Setting | Default | Description |
|---|---|---|
| `visualization` | on | Generates SO profiles (per-position coverage, SNP, and indel information) normalised into a REVEAL directory structure for per-individual TE occupancy plots and a faceted species-level comparison plot. |
| `analysis` | on | Produces coverage/SNP/indel stats and comparisons per `analysis.settings.*` below. |
| `analysis.settings.coverage_analysis` | `true` | When `true`, produce per-individual and species-level coverage stats, comparisons, and plots. |
| `analysis.settings.snp_analysis` | `false` | When `true`, produce per-individual and species-level SNP stats and comparisons. |
| `analysis.settings.indel_analysis` | `false` | When `true`, produce per-individual and species-level indel stats and comparisons. |
| `visualization.settings.individual_plots` | `skip` | `plot` generates plotables and renders per-individual plots, `plotable_only` generates plotables only and skips rendering, `skip` skips both. |
| `visualization.settings.comparison_plots` | `plot` | `plot` generates plotables and renders the faceted species comparison plot, `plotable_only` generates plotables only and skips rendering, `skip` skips both. |
| `visualization.settings.y_axis_log_scale_threshold_individual` | `25` | Y-axis value above which per-individual plots switch to a log scale. |
| `visualization.settings.y_axis_log_scale_threshold_species` | `25` | Y-axis value above which the species comparison plot switches to a log scale. |
| `visualization.settings.visualization_bin_size` | `target:5000` | Bin size for per-position coverage plotables. Accepts a fixed integer (e.g. `100`), `target:N` to auto-compute `bin_size = max(1, seq_len // N)` per sequence, or length-threshold rules (e.g. `10000:1,100000:10,default:500`). |
| `sequence_overview.settings.mapping_quality_threshold` | `5` | Mapping quality threshold for bam2so; reads below this value are treated as ambiguously mapped and excluded. |
| `sequence_overview.settings.minimum_count_snp` | `5` | Minimum number of reads supporting a variant for it to be called as a SNP. |
| `sequence_overview.settings.minimum_frequency_snp` | `0.1` | Minimum allele frequency (0 to 1) for a SNP call. |
| `sequence_overview.settings.minimum_count_indel` | `3` | Minimum number of reads supporting an indel for it to be reported. |
| `sequence_overview.settings.minimum_frequency_indel` | `0.01` | Minimum allele frequency (0 to 1) for an indel call. |
| `normalization.settings.end_distance` | `100` | Number of positions from each end of a sequence excluded when computing the normalisation factor, to avoid edge-coverage artefacts. |
| `normalization.settings.exclude_quantile` | `25` | Percentile used to exclude the most extreme coverage values from normalisation (excludes both the top and bottom tail). |
| `normalization.settings.skip_low_coverage_individuals` | `false` | When an individual's SCG coverage is too low for REVEAL to compute a normalisation factor, exclude that individual from normalised outputs and species-level comparisons/plots instead of failing them. Excluded individuals are listed, with the reason, in `{species}_{feature_library}_excluded_individuals.tsv`. Default `false` keeps today's behaviour: a low-coverage individual fails the whole species-level REVEAL comparison. |

### Stage: `summary_module`

Consolidates all QC outputs into MultiQC HTML reports.

| Setting | Default | Description |
|---|---|---|
| `settings.individual_multiqc` | on | Generate a per-individual MultiQC summary report (all references, one individual). |
| `settings.species_multiqc` | on | Generate a per-species MultiQC summary report (all individuals, all references). |

## Species settings

Each entry under `species:` in the config corresponds to a species folder in the pipeline root. The key must match the folder name exactly.

| Setting | Default | Description |
|---|---|---|
| `execute` | `true` | Whether to process this species. Set to `false` to skip all pipeline stages for this species without removing it from the config. Skipped species are listed in the startup preview log. |
| `name` | — | Human-readable species name used in reports. |
| `individuals` | *(all discovered)* | Optional list of individual IDs to process. Each ID must match the part of a read filename before the first `_` (e.g. `IND001` from `IND001_L001_R1.fastq.gz`). If omitted, all individuals discovered in `{species}/input/read_module/` are used. An error is raised if any listed ID is not found on disk. |
| `references` | *(all discovered)* | Optional list of reference IDs to process. IDs are derived from filenames: basename without extension, dots replaced by underscores (e.g. `EquCab3.0.fna` → `EquCab3_0`). If omitted, all references in `{species}/input/reference_module/` are used. An error is raised if any listed ID is not found on disk. |
| `feature_libraries` | *(all discovered)* | Optional list of feature library IDs to use for the REVEAL stage. Same ID format as `references`. If omitted, all libraries in `{species}/input/reveal_module/feature_library/` are used. An error is raised if any listed ID is not found on disk. |
| `lineage` | — | Required for SCG auto-determination. BUSCO lineage name (e.g. `drosophilidae_odb12`). Browse available lineages at [busco.ezlab.org](https://busco.ezlab.org/). |
| `scg_reference` | auto-detect | Explicit path to the reference FASTA used by BUSCO. Required when multiple FASTAs exist in `{species}/input/reference_module/`; auto-detected and logged when exactly one is present. |
| `species_dir` | *(none, data stays in-project)* | Optional: point the whole species root at a location outside the project. Must contain the same `input/{read_module,reference_module,reveal_module/{scg,feature_library,competition}}`, `processed/`, `results/` layout as a normal species folder. Sets the default target for every setting below. Each can still be overridden individually. See [README.md](README.md#storing-species-data-elsewhere). |
| `reads_dir` | *(none)* | Optional: override the location of `{species}/input/read_module/`. |
| `reference_dir` | *(none)* | Optional: override the location of `{species}/input/reference_module/`. |
| `scg_dir` | *(none)* | Optional: override the location of `{species}/input/reveal_module/scg/`. |
| `feature_library_dir` | *(none)* | Optional: override the location of `{species}/input/reveal_module/feature_library/`. |
| `competition_dir` | *(none)* | Optional: override the location of `{species}/input/reveal_module/competition/`. |
| `processed_dir` | *(none)* | Optional: override the location of `{species}/processed/`. Protected by a cross-project lock, see [FAQ.md](../docs/FAQ.md). |
| `results_dir` | *(none)* | Optional: override the location of `{species}/results/`. Protected by a cross-project lock, see [FAQ.md](../docs/FAQ.md). |

When `individuals`, `references`, or `feature_libraries` are specified, the startup preview logs which items were found but not selected under **"ignored"** entries. This makes it easy to verify your selection before a full run.

For `species_dir`/`reads_dir`/`reference_dir`/`scg_dir`/`feature_library_dir`/`competition_dir`/`processed_dir`/`results_dir`, resolution order per setting is: an explicit setting > a path derived from `species_dir` > today's in-project default. If none of these are set for a species, behavior is unchanged from before this feature existed.

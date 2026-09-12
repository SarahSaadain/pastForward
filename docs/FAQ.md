# pastForward FAQ

## Setup & Installation

For a full step-by-step walkthrough, including installing conda and Snakemake from scratch, see the [Setup Guide](../config/README.md). The questions below cover specific details.

**Q: What version of Snakemake do I need?**
Version 9.9.0 or newer. pastForward checks this automatically at startup and won't run on an older version.

**Q: What version of conda do I need?**
24.7.1 or newer is recommended (or a compatible tool such as Mamba or Miniforge). Conda installs and manages all the other software the pipeline needs, through the `--use-conda` flag.

**Q: Do I need to install all the bioinformatics tools myself?**
No. As long as you run with `--use-conda`, Snakemake installs everything each step needs automatically, the first time you run it.

**Q: Can I run pastForward without conda?**
Not reliably. Every step is tied to a specific conda environment, which keeps software versions consistent and reproducible. Without `--use-conda`, you'd need to install every required tool yourself, with matching versions, and put them all on your PATH.

**Q: Where does pastForward live relative to my input/output data? Do I need a separate copy for each project?**
A pastForward **project** is a single folder containing the `workflow/` and `config/` folders (a copy of the pastForward repository) plus one `<species>/` folder for each species you want to process. By default, the pipeline code and your data live side by side in that same folder. To start a new project, copy pastForward into a new folder and add your species folders there.

If you'd rather keep some or all of a species' data outside the project folder (a different disk, a shared mount, and so on), you can. See "Can I store a species' data outside the project directory?" in the Configuration section below. Without that setting, everything works exactly as described above.

One project can process one species or many. Combining several species in one project folder shares a single `snakemake` command and config, which is handy for a quick look across a batch, for example checking data quality for several species from a low-depth trial-sequencing run. Giving each species its own project folder lets you start, re-run, and configure it independently, which is usually the better choice for a full production run. See [Project Structure](../config/README.md#project-structure) for a folder diagram.

**Q: How does pastForward know which files to create?**
It works out the expected output files from your config and whatever input data it finds. At the start of every run, it checks which input files are present and prints a summary.

From that, it prints a list of every file it plans to create during this run. Use a dry run to check this list before running the pipeline for real, so you can confirm your input files are being detected and will be processed the way you expect.

---

## Input Data

**Q: Where do I put my raw sequencing reads?**
Place them in `<species>/input/read_module/`. pastForward expects compressed FASTQ files following a specific naming convention (see below) to group samples by individual for merging.

**Q: What read file format does pastForward expect?**
Reads must be compressed FASTQ (`.fastq.gz`). The filename must follow the convention:

```
<Individual>_[<FreeText>_]<ReadNumber>[_<FreeText>].fastq.gz
```

`<ReadNumber>` is either `R1`/`R2`, or a bare `1`/`2` that stands alone as its own segment: immediately before the extension (`..._1.fastq.gz`) or between underscores (`..._1_<FreeText>.fastq.gz`). A bare digit will not match inside a longer number such as `_10_` or `_21`.

Everything before the first underscore is treated as the individual identifier and is used to group samples for merging.

**Q: My data is single-end. Does pastForward support that?**
Yes. pastForward auto-detects single-end vs. paired-end by checking whether a matching read 2 file (`R2` or a standalone `2`) exists for each read 1 file. Both modes are handled automatically.

**Q: Can I have multiple sequencing runs for the same individual?**
Yes. All samples belonging to the same individual (same prefix before the first underscore) are merged into a single FASTQ during the "Merge by Individual" step. You can place all run files in `<species>/input/read_module/` and they will be processed and concatenated automatically.

**Q: Where do I put the reference genome?**
Place it in `<species>/input/reference_module/`. pastForward accepts `.fa`, `.fasta`, and `.fna` extensions and normalises them internally. Multiple reference genomes per species are supported. Each is processed independently.

**Q: Can I point to files outside the species folder without moving them?**
The recommended approach is to place files directly in the species folder. pastForward will detect and move them to the correct subfolders automatically on the first run.

**Q: I have a lot of data. Can I symlink to it instead of copying?**
Yes, at two levels:
- **Per file**: place a symlink in the expected location under `<species>/input/`, named according to pastForward's naming convention. The file it points to keeps its own name and can live anywhere on disk, including outside the project folder entirely. pastForward detects and uses symlinked files directly without copying.
- **Per folder**: point an entire category (or the whole species) at a location outside the project via `species.<key>.reads_dir`, `reference_dir`, `species_dir`, etc. in `config.yaml`. See "Can I store a species' data outside the project directory?" below.

Use per-file symlinks for a handful of files. Use the folder-level config options when you want a whole category (or the whole species) to live elsewhere without hand-placing a symlink for every file.

**Q: Can I have multiple species in the same project?**
Yes. Each species is processed independently, so you can have as many species as needed within the same project. Just add additional entries under the `species` section in the config.yaml and place their respective data in separate subfolders under `<species>/input/`.

**Q: Do I need to provide a separate reference genome for each species?**
Yes. Each species entry in the config must have its own reference genome placed in `<species>/input/reference_module/`. pastForward processes each species independently, so it requires a reference genome for each one to perform mapping and downstream analyses.

**Q: Can I use multiple references for the same species?**
Yes. pastForward supports multiple references per species. Just place each reference file in `<species>/input/reference_module/` and pastForward will process them independently, generating separate outputs for each reference.

**Q: Does the reference need to be a reference genome?**
No. The reference can be any FASTA file of sequences you want to map to and analyse. While a reference genome is typical, you could also use a transcriptome assembly, a custom set of contigs, or even a single sequence if that suits your research question.

**Q: Which format does the reference need to be in?**
The reference must be in FASTA format with a `.fa`, `.fasta`, or `.fna` extension. pastForward normalises the reference internally, so you can use any of these extensions without issue.

**Q: Can I process only a subset of individuals for a species?**
Yes. Add an `individuals` list under the species entry in `config.yaml`:

```yaml
species:
  Dmel:
    name: "Drosophila melanogaster"
    individuals:
      - IND001
      - IND002
```

Each entry must match the individual identifier extracted from read filenames, the part before the first `_` (e.g. `IND001` from `IND001_L001_R1.fastq.gz`). If the list is omitted, all individuals discovered on disk are processed. The startup preview reports which individuals were found but not selected, under an "ignored" section.

**Q: Can I use only specific reference genomes for a species?**
Yes. Add a `references` list under the species entry:

```yaml
species:
  Dmel:
    name: "Drosophila melanogaster"
    references:
      - genome
```

Each entry must match the reference ID derived from the filename: basename without extension, with dots replaced by underscores (e.g. `EquCab3.0.fna` → `EquCab3_0`). If omitted, all references in `{species}/input/reference_module/` are used.

**Q: Can I use only specific feature libraries for the REVEAL stage?**
Yes. Add a `feature_libraries` list under the species entry:

```yaml
species:
  Dmel:
    name: "Drosophila melanogaster"
    feature_libraries:
      - my_lib
```

Same ID format as references (filename stem, dots → underscores). If omitted, all libraries in `{species}/input/reveal_module/feature_library/` are used.

**Q: What happens if I list an individual, reference, or feature library that does not exist on disk?**
pastForward raises an error at startup and aborts before any processing starts. The error message lists which IDs were not found and shows all available IDs, so you can correct the config. This prevents silent misconfiguration where a typo would cause a run to silently skip data.

**Q: Can I add new samples after the first run?**
Yes, at any time. Add the new FASTQ files to the matching `<species>/input/read_module/` folder. pastForward detects and processes them on the next run.

In case you use `skip_existing_files: true`, pastForward will not re-process existing files, so only the new samples will be processed without affecting previous results. This might be an issue if summary reports need to be updated to include the new samples, as they may rely on outputs from all samples. Either you can re-run pastForward without `skip_existing_files` to regenerate all outputs including the new samples, or you can remove the summary reports, so they will be regenerated with the new samples included.

**Q: What does `skip_existing_files` do, and should I turn it on?**
When `pipeline.global.skip_existing_files: true`, pastForward drops every output file that already exists from the target list it hands to Snakemake, so those files are never re-computed.

> ⚠️ Warning: Because those files are not requested at all, Snakemake can no longer see that they are out of date. If you change an input file (or an upstream step re-runs), existing downstream outputs are **not** updated and your results can end up inconsistent.

It defaults to `false`, which leaves Snakemake's normal re-run logic in charge: only what actually changed is recomputed. Turn it on only to resume an interrupted run without reprocessing completed steps, and only when you know the inputs have not changed. pastForward logs a warning on every run in which the option is enabled.

**Q: I added new samples but they are not showing up in the reports. What do I do?**
If you added new samples after the first run and your summary reports are not updating, it may be because pastForward is skipping existing files. 

To fix this, you can either:
1. Re-run pastForward without `skip_existing_files: true` to regenerate all outputs and include the new samples in the reports.
2. Manually delete the existing summary report files so that pastForward regenerates them with the new samples included

You can see the skipped files in pastForward log (use a dry run to check). 

**Q: How can I validate that my input files are correctly formatted and will be processed by pastForward?**
You can perform a dry run of pastForward using the command:
```bash
snakemake --cores <N> --use-conda --dryrun
```

At the beginning of each run, pastForward performs an input validation step that checks for the presence and correct formatting of all required input files. It will print a summary of the detected files and any issues found. 

Additionally, it will print all the files that will be requested by pastForward based on the current config. You can review this list to ensure that all your input files are correctly detected and will be processed as expected.

Lastly, you can also see the rules that will be executed and their inputs/outputs. Use that to check pastForward is set up correctly before you run it for real.

**Q: Can I provide the adapter sequences for adapter removal?**
Yes. Put the adapter sequence itself into the config under `pipeline.read_module.adapter_removal.settings.adapters_sequences.[r1|r2]`. It is passed straight to fastp as `--adapter_sequence` (and `--adapter_sequence_r2` for read 2). If you leave them out, fastp tries to auto-detect the adapters from the read data.

**Q: Can I provide already pre-processed reads?**
Yes. If you have already pre-processed reads (e.g., adapter-trimmed and quality-filtered) and want to skip the raw reads processing step, you can place your pre-processed FASTQ files in the expected location under `<species>/input/read_module/` with the correct naming convention. 

To skip the adapter removal and quality filtering steps, set the `execute` flag to `false` for those steps in the config:

```yaml
pipeline:
  read_module:
    adapter_removal:
      execute: false
    quality_filtering:
      execute: false
``` 

This way, pastForward will use your pre-processed reads directly for downstream steps without attempting to re-process them. 

**Q: My reads are already merged (e.g. already adapter removed, quality filtered, and combined per individual). Can I add them?**
Yes. pastForward runs all the read_module steps by default, but if your data has already been through some of them, disable those steps in the config so they are not applied twice. Place your prepared FASTQ files under `<species>/input/read_module/`, still following pastForward's [read file naming convention](../config/README.md#naming-your-read-files), and set `execute: false` for whichever steps you've already applied (see "Can I provide already pre-processed reads?" above for the adapter removal and quality filtering example).

---

## Configuration

**Q: What is the minimum config I need to run pastForward?**
A project name and at least one species entry:

```yaml
project_name: "my_project"

species:
  Dmel:
    name: "Drosophila melanogaster"
```

All pastForward stages are enabled by default, so this minimal config is sufficient to run the full pipeline.

**Q: How do I configure pastForward without editing YAML by hand?**
Open `config/config_designer.html` in a browser. The interactive Config Designer lets you toggle pastForward stages and species settings and exports a ready-to-use `config.yaml`.

**Q: How do I disable a pastForward stage I don't need?**
Set its `execute` flag to `false` in `config/config.yaml`. For example, to skip taxonomic screening:

```yaml
pipeline:
  read_module:
    taxonomic_screening:
      execute: false
```

**Q: Can I enable or disable specific steps after a completed run?**
Yes. You can modify the config to enable or disable specific steps and then re-run pastForward. pastForward will detect which outputs are missing or outdated based on the new configuration and will only execute the necessary rules to generate the required outputs.

For example, if you initially ran pastForward with taxonomic screening disabled and later want to enable it, simply set `execute: true` for the taxonomic screening step in the config and re-run pastForward. It will then execute only the rules related to taxonomic screening without re-running the entire pipeline.

> ⚠️ Warning: In some cases, enabling certain steps may affect downstream outputs (e.g., summary reports). In such cases, pastForward will automatically re-run the affected downstream rules to ensure that all outputs are consistent with the new configuration (Snakemake default behavior). Using `skip_existing_files: true` can help avoid unnecessary re-processing of unchanged files, but be cautious as it may still lead to re-processing of some steps. In such cases, you can also disable the affected downstream steps temporarily, run pastForward to generate the new outputs for the enabled step, and then re-enable the downstream steps in a subsequent run to update the reports or other affected outputs. Check using a dry run to see which steps will be re-run and adjust the config accordingly to minimise unnecessary processing.
>
> Example: If you enable taxonomic screening after the first run (e.g. reads + ref + summary), pastForward will need to re-run adapter removal and quality filtering for all samples to generate the necessary inputs for taxonomic screening. Since these outputs are temporary, they are not stored between runs. To allow taxonomic screening, pastForward must re-generate these outputs. In this case Snakemake will determine that there has been a change and conclude that all downstream steps that depend on these outputs need to be re-run to ensure consistency. Using `skip_existing_files: true` can help avoid unnecessary re-processing, but it is better to check the pastForward log to ensure that the re-processing is indeed suppressed. If Snakemake still triggers a re-run (e.g. reference processing, mapping, ...), the downstream steps can be temporarily disabled in the config.

**Q: Which settings are most likely to trigger a large reprocessing cascade?**
Most `execute: false` toggles only affect their own step's output. A handful of settings decide which file becomes a step's permanent result, out of a chain of intermediate files that get deleted once nothing else needs them. The pipeline always writes the same result filename (`_final.bam`, `_trimmed_final.fastq.gz`, `_quality_filtered_final.fastq.gz`) no matter which steps ran, but the config decides which upstream file gets copied there. Change one of these settings after a completed run, and Snakemake notices the copy rule now points at a different file. That file was already cleaned up once it was no longer needed, so the whole chain behind it has to be regenerated, for every individual or sample that uses it, not just the new ones.

| Setting | Picks between | Regenerating means re-running |
|---|---|---|
| `pipeline.reference_module.damage_rescaling.execute` | rescaled BAM vs. deduplicated/sorted BAM | mapping → deduplication (if enabled) → damage analysis/rescaling, for every individual on that reference |
| `pipeline.reference_module.deduplication.execute` | deduplicated BAM vs. sorted BAM | mapping → deduplication, for every individual on that reference |
| `pipeline.reference_module.filter_unmapped_reads.execute` with `settings.action: remove` | mapped-only BAM vs. whatever the two settings above would have picked | mapping → deduplication → damage analysis, for every individual on that reference |
| `pipeline.read_module.adapter_removal.execute` | adapter-trimmed reads vs. raw reads | adapter removal and everything downstream that reads the merged per-individual FASTQ: quality filtering, merging, mapping, deduplication, damage analysis, REVEAL, taxonomic screening, for every sample |
| `pipeline.read_module.quality_filtering.execute` | quality-filtered reads vs. adapter-trimmed reads | quality filtering and the same downstream chain as above, for every sample |

Three other situations cause the same kind of cascade without an obvious setting to blame:

- **A new step needs a file that was already cleaned up.** Enabling taxonomic screening after the first run (see the example above) is one case. Adding FastQC reports for trimmed/quality-filtered reads is another: if even one sample's report is missing, Snakemake has to regenerate the intermediate file behind it, which pulls mapping and everything after it back in for that sample.
- **Adding samples changes a shared file every individual maps against.** This is intentional: with automatic SCG selection (`pipeline.reveal_module.scg_selector.execute: true`), ranking which single-copy genes to use is a species-wide decision, not a per-individual one. Add individuals, and the ranking can legitimately change, which rewrites the shared SCG file, the combined SCG/feature-library reference, and its index, so every individual gets re-mapped and re-analyzed against the updated version. Providing your own fixed SCG FASTA under `{species}/input/reveal_module/scg/` avoids this, at the cost of losing the automatic per-species ranking.

**Before flipping one of these settings on a project that already has results, do a dry run first** (`snakemake --cores <N> --use-conda --dryrun`) and check how many jobs it plans. If the count is much larger than the change seems to justify, one of these chains is almost always why.

**Q: Can I store a species' data outside the project directory?**
Yes. By default a species' data must live at `<species>/input`, `<species>/processed`, and `<species>/results` inside the project directory. To point some or all of it elsewhere, set one or more of the following optional keys under `species.<key>` in `config.yaml`: `species_dir` (whole species root, which sets the default for everything below), `reads_dir`, `reference_dir`, `scg_dir`, `feature_library_dir`, `competition_dir`, `processed_dir`, `results_dir`. An explicit key always wins over a path derived from `species_dir`.

```yaml
species:
  Dmel:
    name: "Drosophila melanogaster"
    species_dir: "/mnt/big_disk/pastforward_data/Dmel"
    processed_dir: "/scratch/pastforward_processed/Dmel"
```

If none of these are set for a species, nothing on disk is touched beyond what pastForward already does by default. When one is set, pastForward creates a symlink at the conventional in-project location (e.g. `Dmel/input/read_module`) pointing at the configured path, once at startup. This is idempotent (safe to re-run), and pastForward refuses to overwrite anything that already exists there (a real folder, or a symlink pointing elsewhere) rather than risk clobbering existing data. See [Project Structure](../config/README.md#storing-species-data-elsewhere) for the full list of keys.

`processed_dir` and `results_dir` are additionally protected by a **cross-project lock**: a `.pastforward.lock` file written inside the resolved target directory itself, recording the owning project's working directory, PID, hostname, and start time. This is separate from Snakemake's own lock (see "pastForward says it is locked" below). It exists because two *different* project directories/configs could otherwise resolve to the same `processed_dir`/`results_dir` and run concurrently without Snakemake's own per-project lock ever seeing the conflict. It's released automatically when a run finishes (success or error). If a run is killed hard enough that it can't release its own lock (e.g. `kill -9`, a crashed machine), the next run on the *same* host detects that the recorded PID is no longer running and takes over automatically, logging a warning. If the lock was written on a *different* host, pastForward can't verify whether that PID is still alive and fails with an error instead of guessing. If you're sure that run is no longer active, delete the `.pastforward.lock` file inside the target directory manually. Unlike Snakemake's lock, `snakemake --unlock` does **not** clear this one.

---

## Running pastForward

**Q: What is the recommended command to run pastForward?**
```bash
snakemake --cores <N> --use-conda --keep-going --rerun-trigger mtime
```

`--keep-going` lets pastForward continue past individual rule failures (e.g., ECMSD failing on low-coverage samples). `--rerun-trigger mtime` re-runs only rules whose inputs have changed since the last run.

**Q: How do I run pastForward in the background so I can close my terminal?**
```bash
nohup snakemake --cores 40 --use-conda --keep-going --rerun-trigger mtime > pipeline.log 2>&1 &
```

Monitor progress with `tail -f pipeline.log`.

**Q: How do I do a dry run to see what would be executed without actually running anything?**
```bash
snakemake --cores <N> --use-conda --dryrun
```

**Q: pastForward crashed midway. How do I resume?**
Re-run with `--rerun-incomplete` to pick up where it left off:

```bash
snakemake --cores <N> --use-conda --keep-going --rerun-trigger mtime --rerun-incomplete
```

**Q: How do I force a specific rule or file to be regenerated?**
Delete the output file and re-run, or use `--forcerun <rule_name>` to force a specific rule. Use `--touch` with `--forceall` to mark all outputs as up to date without re-running (use as a last resort). Check the Snakemake documentation for more options on controlling rule execution.

**Q: I have lots of data. How does pastForward manage disk space?**
pastForward deletes intermediate files as soon as they are no longer needed. The final outputs (e.g. `_final.bam`, summary reports) are kept, while temporary files (e.g. raw mappings, rescaled BAMs) are removed once they have been processed. Where possible, outputs are also compressed.

Still, watch disk usage during the first run to make sure you have enough space for the intermediate files, especially with large datasets.

**Q: Can I run multiple instances of pastForward simultaneously?**
Yes, you can run multiple instances of pastForward simultaneously, provided that each instance has its own independent working directory and configuration. This allows you to process different datasets or run the same dataset with different parameters in parallel.

The one exception: if you've configured `processed_dir`/`results_dir` (or `species_dir`) to point outside the project directory (see "Can I store a species' data outside the project directory?" above), and two independent projects' configs happen to resolve to the *same* target directory, the second one to start will fail fast with a cross-project lock error instead of racing the first. Instances that keep all data in-project (the default), or whose overrides resolve to different targets, are unaffected.

**Q: What are all these `.benchmark.jsonl` files next to my log files?**
They are pastForward's timing and memory measurements. Every step writes one after it finishes, recording wall time, peak memory, the number of threads it used, and the size of its inputs. The file is named after that step's log file, so the two sit side by side.

They are always written, they cost no measurable runtime, and they are tiny. They are also not pipeline outputs, so deleting them never makes anything re-run:

```bash
find . -name '*.benchmark.jsonl' -delete
```

Read them with `./pastForward benchmark`, which turns them into one row per rule (jobs run, median and longest wall time, peak memory, total core-hours, largest input), ordered by the most expensive rule first.

**Q: `./pastForward benchmark` says it found nothing, or shows far fewer rules than my pipeline has. Why?**
Because a benchmark file is written only when a job actually runs. Snakemake never re-runs a step just because its benchmark file is missing, which is what keeps this from invalidating existing results, but it also means a finished project has nothing to report until something runs again. To measure a whole pipeline, run it in a fresh project folder, or add `--forceall`.

Two other gaps are expected. A step that failed writes nothing at all, because Snakemake records the measurement only on success, so a step that was killed for using too much memory leaves no trace of that. And the three reference-indexing steps are never measured, because Snakemake does not allow a step to be both benchmarked and eligible for its between-workflow cache.

**Q: Why is every memory column in `./pastForward benchmark` empty?**
You are almost certainly on macOS. Snakemake measures memory through psutil, and macOS refuses a process access to its own children's memory, so every memory, CPU and I/O value comes back as `NA` and only wall time survives. Nothing is wrong with your run. For real memory numbers, do the measuring run on a Linux machine.

Peak memory on Linux is sampled every 0.5 seconds for the first 15 seconds of a job and every 30 seconds after that, so treat it as a good number to size a request from, with headroom, rather than as an exact peak.

**Q: Does pastForward support running on an HPC cluster (e.g. via Slurm or PBS)?**
pastForward is a plain Snakemake workflow, so it should in principle work with Snakemake's [cluster/HPC execution support](https://snakemake.readthedocs.io/en/stable/executing/cluster.html) (e.g. via the Slurm or PBS [executor plugins](https://snakemake.github.io/snakemake-plugin-catalog/)), without any changes to the pipeline itself. This has not yet been specifically tested with pastForward. Testing on a Slurm-based HPC cluster is planned.

**Q: Can I stop a running pastForward instance without corrupting the results?**
Yes. You can terminate the process (e.g. with `Ctrl+C` or `kill`) without corrupting results. pastForward leaves behind a lock file so that concurrent runs cannot interfere with each other.

In case you run pastForward in the background, you can stop it using `kill -SIGINT <PID>` where `<PID>` is the process ID of the running instance (you can get it with `head <pipeline.log>`).

When you are ready to resume, run pastForward again with the same command. It will detect the existing lock file and prompt you to unlock it using `snakemake --unlock`. After unlocking, you can re-run pastForward, and it will pick up where it left off without corrupting any results.

---

## Read Mapping

**Q: Which mapper should I use for my data?**
- **bwa-aln**: recommended for very short aDNA/hDNA reads (<70 bp). Generates the most accurate alignments, but can be very slow. That is why bwa-mem2 is the default mapper, as it is much faster and still performs well on short reads.
- **bwa-mem2**: the default. Faster, designed for reads above 70 bp, but performs well on shorter reads too.
- **minimap2**: versatile, and uses the `-ax sr` preset for short reads. If you want a "quick and dirty" mapping to check your data, minimap2 is a good choice. However, it is not optimised for the specific challenges of aDNA/hDNA and may produce lower-quality alignments compared to bwa-aln or bwa-mem2.

Set the mapper via `pipeline.reference_module.mapping.settings.mapper`.

**Q: Can I use different mappers for reference processing and REVEAL processing?**
Yes. The mapper is configured independently under `pipeline.reference_module.mapping.settings.mapper` and `pipeline.reveal_module.mapping.settings.mapper`.

---

## Deduplication & Damage

**Q: Which DeDup build does pastForward use?**
A [modified DeDup fork](https://github.com/SarahSaadain/DeDup), not upstream DeDup. The fork includes performance improvements. It isn't published on bioconda, so the pinned jar is side-loaded automatically into the `dedup` conda environment by `workflow/envs/dedup.post-deploy.sh` the first time it's created. There is no manual build step. Benchmarks against upstream DeDup are tracked in a [separate comparison repo](https://github.com/SarahSaadain/DeDup_comparison_fork).

**Q: Why does deduplication split the BAM into clusters?**
DeDup can use large amounts of memory on reference genomes with many contigs. Splitting by contig cluster caps peak memory use. Adjust `deduplication.settings.max_contigs_per_cluster` (default 500). Lower values reduce memory at the cost of more merge operations.

Also, splitting by cluster allows for more efficient parallel processing. Each cluster is processed independently, so multiple clusters can be deduplicated simultaneously across available CPU cores.

**Q: What determines which BAM becomes the `_final.bam`?**
pastForward follows a priority chain: rescaled BAM → deduplicated BAM → sorted BAM, using the most-processed available result based on which steps are enabled.

**Q: Deduplication runs in reference_module. Why not in REVEAL processing too?**
See "Why doesn't REVEAL processing deduplicate reads..." in the REVEAL Module section below. Short version: it's deliberate, not a gap, because of how the feature library is built.

---

## Taxonomic Screening

**Q: This step used to be called `contamination`. Do my old configs still work?**
Yes. `pipeline.read_module.contamination` is still accepted and is rewritten to `pipeline.read_module.taxonomic_screening` at startup, with a deprecation warning in the log. Only the output folder changed without a fallback: results now land in `{species}/results/read_module/taxonomic_screening/` instead of `{species}/results/read_module/contamination/`. Rename that folder in existing projects (or let pastForward regenerate it) to reuse previous results.

**Q: Why is it called taxonomic screening and not contamination analysis?**
Both ECMSD and Centrifuge are taxonomic read classifiers. They assign reads to reference taxa and report proportions/top taxa, the same kind of output any metagenomic profiling tool would produce. Neither computes a dedicated contamination statistic (e.g. mismatch-to-consensus or heterozygosity-based estimates), so the step is named after what it measures. Reading the result as a contamination signal is the interpretation you apply on top: each sample is expected to come from one known target organism, so a significant proportion of reads assigned to other taxa points to exogenous/contaminating DNA rather than to a community worth characterizing.

**Q: ECMSD keeps failing on some samples. Do I have to fix this before pastForward continues?**
No. Run with `--keep-going` and pastForward will skip the failed samples and continue processing everything else. ECMSD failures are common on low-coverage or low-quality samples.

**Q: Why does ECMSD fail on some samples?**
ECMSD is sensitive to low-coverage samples and may fail to detect contamination in some cases. It is recommended to run pastForward with `--keep-going` and ignore ECMSD failures.

**Q: Can I reuse the same ECMSD database for multiple runs?**
Yes. The ECMSD database is downloaded and stored in the pipeline's resource directory. If it already exists, pastForward will reuse it without re-downloading. You can safely run multiple instances of pastForward without worrying about redundant ECMSD database downloads.

**Q: Can I reuse the same ECMSD database for multiple pastForward instances?**
Yes. As long as the ECMSD database is accessible at the expected path in the pipeline's resource directory, multiple pastForward instances can use the same database for taxonomic screening without conflict.

Use `tools.ecmsd.settings.database` to specify a custom path to the ECMSD database if needed. Otherwise, pastForward will manage it automatically.

**Q: Can I make pastForward always use the latest ECMSD release instead of the bioconda-pinned one?**
Yes. Set `tools.ecmsd.settings.version_source: "latest_release"` to side-load the newest tagged release from [capoony/ECMSD](https://github.com/capoony/ECMSD) instead of the bioconda-packaged `ecmsd=1.*`. There is also an **experimental** `"dev"` option that tracks the tip of ECMSD's `development` branch. It is unreleased and untested, so use it at your own risk. Each `version_source` value has its own dedicated conda env file (`workflow/envs/ecmsd*.yaml`), so switching the setting switches which env a rule depends on, and Snakemake builds or reuses that env automatically. See the REVEAL Module section below for the one case that still needs a manual rebuild. The mechanism is identical for both tools.

**Q: The Centrifuge database isn't specified. What happens?**
If `tools.centrifuge.settings.index` is not set, pastForward will attempt to download a default index automatically. For reproducible runs, specify your own index path.

**Q: Can I use a custom Centrifuge database?**
Yes. Set `tools.centrifuge.settings.index` to the path of your custom index. pastForward will use it for taxonomic screening instead of downloading the default.

**Q: Can I reuse the same index for multiple runs?**
Yes. pastForward checks if the specified Centrifuge index already exists and will reuse it if found. You can safely point to the same index across multiple runs without worrying about redundant downloads.

**Q: Can I reuse the same Centrifuge database for multiple pastForward instances?**
Yes. As long as the Centrifuge index is accessible at the specified path, multiple pastForward instances can use the same database for taxonomic screening without conflict.

You can even share the same Centrifuge index across different projects or species, as long as the path is correctly specified in each config. That saves resources and keeps taxonomic screening consistent across datasets.

---

## REVEAL Module

**Q: What goes in the feature library?**
A FASTA file of the genomic feature sequences (e.g. transposable elements, genes) you want to quantify. Place it under `<species>/input/reveal_module/feature_library/`. Multiple feature libraries per species are supported and each is processed independently.

**Q: Do I need to provide SCG sequences?**
Not necessarily. If a FASTA file is placed under `<species>/input/reveal_module/scg/` it is used directly. Otherwise, if `pipeline.reveal_module.scg_selector.execute: true` (the default) and a BUSCO lineage is configured under `species.<key>.lineage`, pastForward determines SCGs automatically from the reference genome.

**Q: How are SCGs selected automatically?**
BUSCO identifies complete single-copy genes in the reference genome. Candidate sequences are filtered by length (`min_length_scg` / `max_length_scg`, defaults 4,000 to 8,000 bp), then scored on coverage breadth, depth evenness, and cross-individual consistency. The top-ranked sequences (`num_top_scgs`, default 20) are selected. See [scg_determination.md](scg_determination.md) for the full scoring methodology.

**Q: How does pastForward determine the reference genome for determining SCGs?**
pastForward will use the reference specified in `species.<key>.scg_reference` if set. Otherwise, it auto-detects the reference from `<species>/input/reference_module/`, provided exactly one reference file is present there.

In case multiple references are available in `<species>/input/reference_module/`, pastForward will raise an error asking you to specify which one to use for SCG selection by setting `species.<key>.scg_reference` to the path of the desired reference.

**Q: What does the copy number fold-change flag mean in the REVEAL output?**
Sequences are flagged if the log₂ fold-change in median coverage across individuals exceeds `CN_FC` (default ≥ 2) or the absolute difference exceeds `CN_ABS` (default Δ ≥ 10). Flagged sequences are sorted to the top of the comparison table and written to a companion `_flagged_seqids.tsv` file.

**Q: Deduplication runs in reference_module (via DeDup). Why doesn't REVEAL processing deduplicate reads too?**
reveal_module maps reads fresh from the merged FASTQ against the combined SCG + feature-library reference; it does not run DeDup or any other deduplication tool on that mapping. This is intentional, not an oversight.

The feature library is a many-genomic-copies-to-one-consensus reference: reads from distinct, independent copies of a repeat or transposable element elsewhere in the genome legitimately align to the same consensus coordinate, with the same start position and CIGAR. Deduplicating here would strip real multi-copy signal rather than PCR artifacts, biasing the copy-number/abundance signal REVEAL exists to measure in the first place, in the opposite direction from what dedup is meant to fix.

**Q: Which REVEAL build does pastForward install?**
`pipeline.reveal_module.settings.version_source` picks which build. The default `"conda"` takes REVEAL from the bioconda-packaged `reveal-tools=1.*`. `"latest_release"` side-loads the newest tagged release from [SarahSaadain/REVEAL](https://github.com/SarahSaadain/REVEAL) instead, in its own conda env. There is also an **experimental** `"dev"` option that tracks the tip of REVEAL's `develop` branch. It is unreleased and untested, so use it at your own risk. The same three options exist for ECMSD via `tools.ecmsd.settings.version_source`, where `"conda"` is the bioconda package `ecmsd=1.*` — the mechanism is identical for both tools.

**Q: I set `version_source` to `latest_release` or `dev`, but pastForward is still using the old version. Why?**
The `latest_release`/`dev` builds of REVEAL and ECMSD are installed by a conda post-deploy script that runs exactly once, right when their conda environment is first created. It has no way to notice a config change on later runs, so it never re-checks GitHub on its own. Switching `version_source` itself (e.g. `conda` to `latest_release`) points the rule at a different env file, and Snakemake builds that env fresh on its own, so you do not have to do anything by hand. But staying on the same unpinned `version_source` while wanting to pick up a newer release/commit needs that one environment force-rebuilt:
```bash
./pastForward doctor --rebuild-envs ecmsd_git_release   # or: ecmsd_git_development, reveal_git_release, reveal_git_development
./pastForward doctor --rebuild-envs                      # rebuilds every conda env, not just these
```
`./pastForward doctor` on its own lists every conda environment the pipeline uses and whether each is currently built, without changing anything. Under the hood this deletes that environment's folder under `.snakemake/conda/` and runs `snakemake --use-conda --conda-create-envs-only` to recreate it. That is the same thing you'd do by hand with plain `snakemake --cores <N> --use-conda --conda-create-envs-only --conda-cleanup-envs`. This is intentional: it keeps a single pipeline run reproducible even when `version_source` is set to a moving target, at the cost of not auto-updating mid-project.

---

## Reports

**Q: Where are the MultiQC reports?**
- Per-individual: `{species}/results/summary/individual_level/{individual}_multiqc.html`
- Per-species: `{species}/results/summary/species_level/{species}_multiqc.overall.html`

**Q: A step was disabled. Will the report still work?**
Yes. Each report only requests inputs from enabled steps. Disabled steps are left out, so the report reflects what was run.

---

## Troubleshooting

**Q: pastForward says it is locked. What do I do?**
A lock file is left behind when a previous run was forcefully terminated. Run `snakemake --unlock` to remove it, then re-run normally. Do not delete the lock file manually.

This is Snakemake's own lock, scoped to this project's working directory (its `.snakemake/` folder). It's unrelated to the separate cross-project `.pastforward.lock` file described in "Can I store a species' data outside the project directory?" above. `snakemake --unlock` does not touch that one. If pastForward instead reports a `.pastforward.lock` conflict, see that Q&A for how to resolve it.

**Q: I accidentally deleted some intermediate files. Can I regenerate them?**
Yes. Delete the corresponding output files (or use `--forcerun`) and re-run pastForward. Snakemake will re-execute only the rules needed to regenerate the missing files.

**Q: How do I know what version of pastForward code was used for a run?**
Each run logs a full provenance record to the pastForward log, including the git commit hash, Snakemake and Python versions, platform details, and the full configuration that was loaded.

**Q: Centrifuge fails to build its conda environment on my Mac. Why?**
This is a known limitation of the Centrifuge bioconda package, not a config issue. Bioconda ships Centrifuge builds for `linux-64`, `linux-aarch64`, and `osx-64` (Intel), but not `osx-arm64`. On Apple Silicon Macs, conda defaults to `osx-arm64`, so it can never find the package.

Workaround: force conda to resolve Intel (`osx-64`) packages and let macOS run them through Rosetta 2.

1. Install Rosetta 2 if you haven't already:
   ```bash
   softwareupdate --install-rosetta --agree-to-license
   ```
2. Before running the pipeline, tell conda to use the Intel subdir:
   ```bash
   export CONDA_SUBDIR=osx-64
   ```
   This applies to every conda environment Snakemake creates in that shell session, not just Centrifuge's, so the whole pipeline runs under Rosetta emulation for that run.
3. If a Centrifuge env was already partially created under `osx-arm64`, clear it out first by removing the `.snakemake` folder in the project directory, then re-run with `--use-conda` as usual.

Alternatively, if Centrifuge isn't required for your analysis, disable it in the config instead (`pipeline.read_module.taxonomic_screening.tools.centrifuge.execute: false`, see `config/parameters.md`).

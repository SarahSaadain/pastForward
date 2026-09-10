<p align="center"><img src="docs/img/pastforward_logo_block.svg" width="250"/></p>

# pastForward - A pipeline for ancient and historical DNA based on Snakemake

[![Snakemake](https://img.shields.io/badge/snakemake-≥9.9.0-brightgreen.svg)](https://snakemake.github.io)
[![GitHub release](https://img.shields.io/github/v/release/SarahSaadain/aDNA_Pipeline_Snakemake)](https://github.com/SarahSaadain/aDNA_Pipeline_Snakemake/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

pastForward analyzes raw ancient and historical DNA from a sequencing facility. It checks read quality and screens for contamination, with methods suited to the short, damaged reads such samples usually give. It maps reads to a reference genome and corrects them for DNA damage, so they are ready for downstream analysis. Optionally, it can also compare genomic features across time points or between specimens, such as transposon insertions, gene copy number changes, or endosymbiont strain replacements.

pastForward is built on [Snakemake](https://snakemake.github.io).


> **Note:** pastForward uses two purpose-built tools: [REVEAL](https://github.com/SarahSaadain/REVEAL) for transposable element and genomic feature dynamics, and [ECMSD](https://github.com/capoony/ECMSD) for contamination screening against a curated mitochondrial database. See their READMEs for details on each tool.

## Workflow Overview

![Pipeline Overview](docs/img/pf_pipeline_process_withoutLogo.svg)

For detailed information about the processing steps, see the [Process Overview](docs/process_overview.md) page. For common questions and troubleshooting, see the [FAQ](docs/FAQ.md).

## Quick Start

New to pastForward? These four steps take you from nothing to a finished run. Each one links to more detail.

1. **Install Conda and Snakemake, and download pastForward.** The [Setup Guide](config/README.md) walks through this step by step.
2. **Add your species and sequencing data.** Also covered in the [Setup Guide](config/README.md#step-4-add-your-species-and-data), including how your read files need to be named.
3. **Create a `config.yaml` file.** Every pipeline stage is turned on by default, but can be adjusted if required. To run with default settings, a config with a project name and species list is enough. If you want to adjust the config but would rather not edit a text file by hand, open the [Config Designer](https://sarahsaadain.github.io/pastForward/config/config_designer.html) in your browser to create your config.
4. **Run the pipeline.** See [Running the Pipeline](#running-the-pipeline) below for the exact command.

Already running pastForward and want a newer version? See the [Update Guide](docs/update.md).

## Running the Pipeline

Run `./pastForward` from your **project folder**, the folder that directly contains `workflow/`, `config/`, and your `<species>/` folders. See [Project Structure](config/README.md#project-structure) for what that folder should look like.

For a new project, run these in order:

1. **`./pastForward check`**: see what pastForward finds on disk for your config (species/individuals/references/...). Fix your data or config first if anything looks wrong here.
2. **`./pastForward preview`**: see the output files a run would produce, including ones it'll skip.
3. **`./pastForward dryrun`** *(optional)*: a full Snakemake dry run, to double-check the exact rules that would execute.
4. **`./pastForward run --cores 40`**: runs the pipeline, in the background by default.

```bash
./pastForward check
./pastForward preview
./pastForward dryrun            # optional

./pastForward run --cores 40             # runs the pipeline, in the background, with the suggested flags
./pastForward run --cores 40 --fg        # same, but in the foreground
./pastForward resume --cores 40          # like run, but also picks back up rules left incomplete by a crash/kill

./pastForward status           # project, config, PID, progress bar, and the last few pipeline steps of the tracked background run
./pastForward status --watch   # same, plus a log tail, reprinted every 5s until the run ends (Ctrl-C to stop early)
./pastForward abort            # stop it gracefully (SIGTERM; snakemake shuts down its own subprocesses)
./pastForward abort --force    # or kill it and everything it started, immediately
./pastForward unlock           # clear a stale lock left by a crashed run
./pastForward touch            # mark existing output files as up to date, so the next run skips the steps that made them
./pastForward doctor                        # list conda envs and whether each is built
./pastForward doctor --rebuild-envs ecmsd   # force one (or, with no names, all) to be recreated
./pastForward print-log        # print the most recently written log from logs/
./pastForward print-log --tail 50  # only the last 50 lines (default 20)
./pastForward print-log --live     # tail -f the log (Ctrl-C to stop)

./pastForward version          # print the pipeline version
```

`run` requires `--cores <N>` (or `-j`/`--jobs`). pastForward will not guess a thread count for you. `--use-conda`, `--keep-going`, and `--rerun-trigger mtime` are added automatically, but if you pass one of them yourself, your value is used instead. Any other extra arguments (e.g. `--forceall`) go straight through to Snakemake. `run` also refuses to start if a tracked run is still alive in the same project folder. Stop that one with `abort` first.

`touch` runs `snakemake --touch`: it only updates the timestamps of output files that already exist, so Snakemake treats them as up to date and skips the steps that produced them. Nothing is recomputed and no file content changes. It is meant for cases where the results are fine but their timestamps are not, e.g. after copying results in from another machine. Output files that do not exist yet are skipped with a warning, and by default only files Snakemake already considers out of date are touched. Add `--forcerun <rule>` or `--forceall` to touch the rest as well.

Each `run`/`dryrun`/`touch` writes a timestamped log to `logs/` in your project folder. `status` reads the most recent `run` back out of there.

Snakemake keeps track of what's already been done and only re-runs steps that are missing or out of date. To start completely over, delete the relevant `results` and `processed` folders and run the pipeline again.

Want to call `snakemake` directly, tune its flags, run without the CLI wrapper, or run on an HPC cluster? See [Running with Snakemake](docs/snakemake.md).

## Reports

pastForward generates a MultiQC report for:

* **Each species** (all samples from that species together, so you can compare results across them)
  * Location: `{species}/results/summary/species_level/{species}_multiqc.overall.html`
* **Each individual sample**
  * Location: `{species}/results/summary/individual_level/{individual}_multiqc.html`

These reports summarize reads before and after trimming, taxonomic screening, coverage, deduplication, and damage rescaling. Use them to judge the quality of your sequenced reads and decide whether a sample needs additional library preparation.

## Citation

If you use pastForward in your research, please cite:

> Saadain, S., Kapun, M., & Kofler, R. (2026). pastForward: a Snakemake pipeline for ancient and historical DNA with eukaryote-wide taxonomic screening and tracking of copy-number variation. *bioRxiv*. https://doi.org/10.64898/2026.08.07.743613

# Setup Guide

This guide walks through everything you need to set up and configure pastForward.

## What You'll Need

pastForward runs on two free tools:

* **Conda** installs and manages all the other software the pipeline needs.
* **Snakemake** runs the pipeline itself and can be installed using conda. Version **9.9.0** or newer is required.


## Step 1: Install Conda

If you don't already have conda, install [Miniforge](https://github.com/conda-forge/miniforge). Follow the instructions for your operating system.

## Step 2: Install Snakemake

Run:

```bash
conda create -c conda-forge -c bioconda -c nodefaults -n snakemake snakemake   # one-time
conda activate snakemake                                                      # every new terminal, before using pastForward
snakemake --help                                                              # sanity check, should print the help page
```

For more installation options, see the [Snakemake documentation](https://snakemake.readthedocs.io/en/stable/getting_started/installation.html).

## Step 3: Get pastForward

[Download](https://github.com/SarahSaadain/pastForward/releases) or clone this repository into a folder on your computer using:

```bash
git clone https://github.com/SarahSaadain/pastForward.git
```

That folder becomes your **project folder**. pastForward, your data, and your results will all live inside it. To move an existing project folder to a newer pastForward version later, see the [Update Guide](../docs/update.md). See [Project Structure](#project-structure) below for what this folder should contain.

## Step 4: Add Your Species and Data

### Project Structure

A pastForward **project** is a single folder containing the `workflow/` and `config/` folders (the pipeline code you just downloaded) plus one folder per species you want to process:

```text
my_project/                  <- project folder, run `./pastForward` (or `snakemake`) from here
├── workflow/                <- pastForward pipeline code (do not edit)
├── config/                  <- config.yaml, config_designer.html
├── pastForward               <- CLI wrapper, see "Running the Pipeline" in README.md
├── Dmel/                    <- one folder per species; name must match the `species:` key in config.yaml
│   ├── input/
│   ├── processed/
│   └── results/
└── Dsim/
    ├── input/
    ├── processed/
    └── results/
```

The pipeline code and your data live side by side in this one folder. There's no separate install location.

One project can handle one species or many. Which you choose depends on how you want to work:

* **Combine several species in one project folder** if you just want a quick look across many species at once, sharing a single command and config. For example, checking data quality across a batch from a low-depth trial run.
* **Give each species its own project folder** if you want to start, re-run, and configure each one independently without affecting the others. This is the better choice for a full production run.

### Add a Species

To add a new species:

1. Create a folder for it in the project root. The folder name must exactly (case sensitive) match the species key you'll use under `species:` in `config.yaml` (see [Configuration](#configuration-configyaml) below).
2. Put your raw read files and reference genome inside that folder (see below).

Or let pastForward do step 1 for you. Run `./pastForward tools create-species Dmel` from the project root. It creates `Dmel/` with every `input/` subfolder listed below, and prints a `species:` block to copy into `config.yaml`.

#### Providing Your Data

The simplest option: drop your raw read files and reference genome inside the `<species>` folder. The first time you run pastForward, it finds them and moves them to the right place. This shortcut only works for reads and the reference genome. REVEAL input files (feature library, and optionally SCG) must go in their specific folders, not just anywhere in `<species>`.

If you want to put the files straight into their final location, put them here:

* raw reads in `<species>/input/read_module/`
* the reference genome(s) in `<species>/input/reference_module/`
* (optional) a feature library in `<species>/input/reveal_module/feature_library/`, a FASTA of TE or other genomic feature sequences to compare across samples. Needed only if you're using the REVEAL comparison stage
* (optional) a pre-built SCG (single-copy gene) FASTA in `<species>/input/reveal_module/scg/`. If you skip this, pastForward determines SCGs automatically via BUSCO, as long as `pipeline.reveal_module.scg_selector.execute` is `true` (the default) and `species.<key>.lineage` is set to a BUSCO lineage name (e.g. `drosophilidae_odb12`, see [busco.ezlab.org](https://busco.ezlab.org/)). No lineage configured and no FASTA provided means SCG determination is skipped.

If your files are large, shared with other tools, or already live somewhere else on disk, you don't need to copy them. Place a **symlink** in the expected location instead, and pastForward will use it directly. The symlink's name must follow pastForward's naming convention (below), but the real file it points to can keep its own name and live anywhere.

#### Storing Species Data Elsewhere

> This is an optional, advanced feature. Skip this section if your data lives inside the project folder as shown above. That's the default, and most people don't need to change it.

If you'd rather keep some or all of a species' data elsewhere (a different disk, a shared network drive, or a folder outside the project entirely), set one or more of the following optional settings under `species.<key>` in `config.yaml`. If you don't set any of these, nothing changes from the default behavior described above.

| Setting | Overrides |
|---|---|
| `species_dir` | The whole species root. Must contain the same `input/{read_module,reference_module,reveal_module/{scg,feature_library,competition}}`, `processed/`, `results/` layout as a normal species folder. Used as the default target for every setting below. |
| `reads_dir` | `<species>/input/read_module/` |
| `reference_dir` | `<species>/input/reference_module/` |
| `scg_dir` | `<species>/input/reveal_module/scg/` |
| `feature_library_dir` | `<species>/input/reveal_module/feature_library/` |
| `competition_dir` | `<species>/input/reveal_module/competition/` |
| `processed_dir` | `<species>/processed/` |
| `results_dir` | `<species>/results/` |

If you set both `species_dir` and one of the more specific settings, the specific setting wins.

```yaml
species:
  Dmel:
    name: "Drosophila melanogaster"
    # Everything for Dmel lives on a different disk...
    species_dir: "/mnt/big_disk/pastforward_data/Dmel"
    # ...except processed/, which should go to fast local scratch instead.
    processed_dir: "/scratch/pastforward_processed/Dmel"
```

At startup, pastForward creates a shortcut (symlink) at the usual in-project location (e.g. `Dmel/input/read_module`) pointing at your configured target, so every part of the pipeline keeps working normally. A few things to know:

* This happens automatically, once per run, before pastForward looks for any input files.
* If something already exists at the usual location (a real folder, or a shortcut to somewhere else), pastForward will stop and show an error instead of overwriting it. Fix the config, or move/remove the conflicting folder, then try again.
* `processed_dir` and `results_dir` are additionally protected against two different projects accidentally writing to the same place at the same time. See [FAQ.md](../docs/FAQ.md) if you run into a lock error.

#### What Gets Created Automatically

You don't need to create any folders beyond your species folder. Everything else is created as the pipeline runs:

* `<species>/processed/` holds files created while the pipeline is working. Most are temporary files and are deleted automatically once they're no longer needed. Some are kept so the pipeline can pick up from a failed step without starting over.
* `<species>/results/` holds your final results and reports. This is the folder you will look at.

Everything related to a reference is grouped under a `<reference>` folder inside `processed/` or `results/`. For most purposes, only `results/` matters. If you need more detail, the `processed/` folder usually has it. A couple of large intermediate file types (`.sam` and unsorted `.bam` files) are always deleted to save disk space. If you ever need to redo a step, just delete its output files and re-run pastForward.

#### Naming Your Read Files

pastForward needs your raw read filenames to follow one consistent pattern, so it can tell which files belong to which sample and which read pair they are. A few correct examples:

```text
Dmel01_DabneyProtocol_R1_006.fastq.gz
Dmel01_DabneyProtocol_1.fastq.gz
Dmel01_DabneyProtocol_R1.fq.gz
```

Pattern:

```text
<Individual>_[<FreeText>_]<ReadNumber>[_<FreeText>].fastq.gz
```

* **`<Individual>`** is a unique ID for the sample, e.g. `Dmel01`. It's everything **before the first underscore**, and pastForward uses it to group files that belong together.
* **`<FreeText>`** (optional, can appear before or after the read number) is any extra label you want, e.g. a protocol name. Useful when the same individual was extracted twice with different methods.
* **`<ReadNumber>`** marks which read of the pair this file is: `R1`/`R2`, or a plain `1`/`2`. It can sit in the middle of the filename (followed by more `<FreeText>`) or be the last part, right before the extension, as in the second and third examples above. A plain `1` or `2` must stand on its own between underscores or right before the file extension. It won't be picked up inside a longer number like `_10_` or `_21`. In case you provide single end data, use `1` or `R1` as well.
* The file must end in **`.fastq.gz`** or **`.fq.gz`** (compressed FASTQ). Uncompressed `.fastq`/`.fq` files are not supported.

## Configuration (`config.yaml`)

`config.yaml` tells pastForward which species to process and which pipeline options to use.

If you don't want to edit the config in a terminal, open the [Config Designer](https://sarahsaadain.github.io/pastForward/config/config_designer.html) in your web browser. It walks you through every option and writes a ready-to-use `config.yaml` for you.

If you'd rather write it yourself, every pipeline stage is turned on by default, so a minimal config only needs a project name and species list:

```yaml
project_name: "pastForward_Project"

species:
  Dmel:
    name: "Drosophila melanogaster"
```

* For the full list of settings, their defaults, and what they do, see [parameters.md](parameters.md).
* For a fully-commented example using every available setting, see [max_config_sample.yaml](max_config_sample.yaml).

Once your data is in place and your config is ready, head back to the main [README](../README.md#running-the-pipeline) to start the pipeline.

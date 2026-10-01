# Updating pastForward

Your project folder holds two kinds of things:

* **Pipeline code**: `workflow/`, the `pastForward` CLI, `docs/`, `README.md`, `CHANGELOG.md`, and the sample/reference files in `config/`. An update replaces these.
* **Your stuff**: `config/config.yaml`, your `<species>/` folders (input, processed, results), `logs/`, `.pastforward/`. An update never touches these.

## Before You Update

1. Note the version you are on:
   * From 2.1.0 on: `./pastForward version`.
   * Before that there is no `pastForward` CLI. Start a dry run instead, `snakemake --cores 1 --software-deployment-method conda --dryrun`, and read the first log line, which says `pastForward <version> run:`.
   * If `workflow/scripts/version.py` does not exist at all, you are on a 1.x version. `git describe --tags` tells you which one, if you have a git clone.
2. Make sure nothing is running: `./pastForward status`, and `./pastForward abort` if a run is still alive. Before 2.1.0 there is no tracked background run, so stop the `snakemake` process yourself if one is still going.
3. Read [CHANGELOG.md](../CHANGELOG.md) for everything between your version and the new one. Config keys and output folders are occasionally renamed, and those entries tell you what to adjust.

## Coming From a 1.x Version?

Version 2.0.0 renamed every pipeline stage, restructured the config, and moved the input and output folders. Nothing of that is migrated for you: a 1.x `config.yaml` is not understood by a 2.x pipeline, and 1.x data folders are not found where the pipeline now looks. Plan for a bit of manual work, and read the [2.0.0 entry in CHANGELOG.md](../CHANGELOG.md) in full before you start.

### 1. Write a New Config

Start from a fresh config instead of patching your old one key by key. Open [config/config_designer.html](../config/config_designer.html) in your browser, or copy `config/min_config_sample.yaml` to `config/config.yaml`, then carry over the settings you had changed. Use this table to find where each of them went:

| 1.x key | 2.x key |
|---|---|
| `pipeline.raw_reads_processing` | `pipeline.read_module` |
| `pipeline.reference_processing` | `pipeline.reference_module` |
| `pipeline.dynamics` | `pipeline.reveal_module` |
| `pipeline.summary_processing` | `pipeline.summary_module` |
| `...quality_checking_raw` / `_trimmed` / `_quality_filtered` / `_merged` | one `pipeline.read_module.analysis` block, with a `multiqc_*_reads` setting per stage |
| `...contamination_analysis` | `pipeline.read_module.taxonomic_screening` (called `contamination` in 2.0.x) |
| `pipeline.dynamics.teplotter`, `pipeline.dynamics.pf_normalization` | gone, replaced by `pipeline.reveal_module.sequence_overview`, `.normalization`, `.analysis` and `.visualization` |

The full list of settings is in [config/parameters.md](../config/parameters.md). The 2.x defaults are sensible on their own, so anything you never changed can be left out.

### 2. Move Your Input Files

The species input folders were renamed. For each species folder:

```bash
cd Dmel                        # your species folder
mkdir -p input/read_module input/reference_module
mv raw/reads/* input/read_module/
mv raw/ref/*   input/reference_module/
rmdir raw/reads raw/ref raw
```

Read filenames themselves did not change, so your files can keep their names. 2.x additionally accepts a bare `1`/`2` instead of `R1`/`R2`.

### 3. Decide What to Do With Old Results

Output paths changed too. The important ones:

| 1.x location | 2.x location |
|---|---|
| `{species}/results/{reference}/...` | `{species}/results/reference_module/{reference}/...` |
| `{species}/processed/{reference}/mapped/*_final.bam` | `{species}/results/reference_module/{reference}/mapped/` |
| `{species}/results/contamination_analysis/` | `{species}/results/read_module/taxonomic_screening/` |

You have two options. Either move the old folders to the new paths, so the pipeline sees that work as done and skips it, or leave them where they are and let 2.x recompute from your raw reads. Moving is faster but fiddly, and the 2.x outputs are not identical anyway: the default mapper changed from `bwa-mem` to `bwa-mem2`, and REVEAL replaced the old `teplotter` scripts. For a small dataset, recomputing into a clean project folder is the safer choice.

Whichever you pick, finish with `./pastForward check` and `./pastForward dryrun` and look at what it plans to do before starting a real run.

## Coming From a Version Before 2.1.0?

Up to and including v2.0.2, `config/config.yaml` was part of the repository. From v2.1.0 on it is gitignored, and the file that ships with pastForward is `config/min_config_sample.yaml` instead.

That means a `git pull` across that boundary collides with your own config: git either refuses to pull because the file has local changes, or, if you never edited it, deletes it as part of the update.

Copy it aside before you update, and put it back afterwards:

```bash
cp config/config.yaml config/config.yaml.bak
# ... update, see below ...
cp config/config.yaml.bak config/config.yaml
```

From v2.1.0 on this is no longer needed. Your `config.yaml` is ignored by git and stays untouched.

## Update With Git

If you got pastForward with `git clone`, run this in your project folder:

```bash
git pull
```

To move to a specific release instead of the latest development state:

```bash
git fetch --tags
git checkout v2.1.0
```

`config/config.yaml` is gitignored and your species folders are untracked, so both survive the pull untouched.

If git refuses to pull because you changed pipeline files yourself, either keep those changes with `git stash` (then `git stash pop` after the pull) or throw them away with `git checkout -- <file>`.

If the pull still does not go through, for example because you have local commits you do not need or because the branch history was rewritten upstream, you can force your copy to match the remote exactly. **This throws away every local commit and local change on the branch**, so only do it if you are sure you need nothing from them:

```bash
# 1. Set aside your config.yaml so it survives the reset
git stash push -u -m "keep config" config/config.yaml

# 2. Discard local commits and match the remote exactly
git fetch origin
git reset --hard origin/develop     # or origin/main

# 3. Bring your config.yaml back
git stash pop
```

## Update Without Git

Download the release you want as a zip, then copy the code parts over your project folder. Replace `v2.1.0` with the version you want.

```bash
# 1. Download and unpack, somewhere outside your project folder
cd ~/Downloads
curl -L -o pastForward.zip https://github.com/SarahSaadain/pastForward/archive/refs/tags/v2.1.0.zip
unzip pastForward.zip          # creates pastForward-2.1.0/

# 2. Copy the code into your project folder
cd /path/to/my_project
rm -rf workflow
cp -r ~/Downloads/pastForward-2.1.0/workflow .
cp -r ~/Downloads/pastForward-2.1.0/docs .
cp ~/Downloads/pastForward-2.1.0/pastForward .
cp ~/Downloads/pastForward-2.1.0/README.md ~/Downloads/pastForward-2.1.0/CHANGELOG.md .
cp ~/Downloads/pastForward-2.1.0/config/*.md ~/Downloads/pastForward-2.1.0/config/*sample.yaml ~/Downloads/pastForward-2.1.0/config/config_designer.html config/
chmod +x pastForward
```

Two things to watch:

* `rm -rf workflow` is there because a plain copy would leave files behind that the new version deleted or renamed. Nothing of yours lives in `workflow/`, but skip that line if you edited the pipeline code yourself and want to keep it.
* The `cp` into `config/` deliberately lists the sample and reference files only, so your own `config.yaml` is not overwritten.

## After Updating

Run these in your project folder, in order:

```bash
./pastForward version   # confirm the new version
./pastForward check     # config and data discovery
./pastForward doctor    # conda environments
./pastForward dryrun    # what a run would do now
```

* `check` is where a renamed or removed config key shows up, as a warning or an error. Fix `config.yaml` as described in the changelog entry.
* Conda environment files can change between versions. Snakemake builds the new environment by itself on the next run; `./pastForward doctor --rebuild-envs` forces it earlier.
* If something behaves oddly after the update, delete the hidden `.snakemake/` folder in your project folder and run again. It caches the conda environments and Snakemake's own bookkeeping, both of which can hold on to state from the old version. It is safe to delete: pastForward rebuilds it, and because runs use `--rerun-trigger mtime`, finished results are not redone just because the bookkeeping is gone. The cost is time, since every conda environment is built again on the next run.
* Your existing results stay. Snakemake re-runs only what is missing or out of date, so a normal update does not throw away finished work. If a release moved or renamed an output folder, either move it as the changelog says or let pastForward regenerate it.

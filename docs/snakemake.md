# Running with Snakemake

pastForward is a [Snakemake](https://snakemake.github.io) workflow. The [`pastForward` CLI](../README.md#running-the-pipeline) is a thin wrapper around `snakemake` that covers day-to-day use (backgrounding, progress checks, a clean stop) and is the recommended way to run the pipeline. This page is for calling `snakemake` directly instead. It covers the flags worth tuning, running on an HPC cluster, and how Snakemake decides what to (re-)run.

Run these commands from your **project folder**, the folder that directly contains `workflow/`, `config/`, and your `<species>/` folders. See [Project Structure](../config/README.md#project-structure) for what that folder should look like.

## Calling `snakemake` Directly

```bash
# minimum command to run the pipeline
snakemake --cores <number_of_threads> --use-conda

# suggested command to run the pipeline
snakemake --cores <number_of_threads> --use-conda --keep-going --rerun-trigger mtime
```

Replace `<number_of_threads>` with the number of CPU threads you want to give the pipeline.

**What the suggested flags do:**

* `--use-conda` lets Snakemake install and use the software each step needs automatically.
* `--keep-going` lets the pipeline carry on if one step fails, instead of stopping everything. This matters because the taxonomic screening tool ECMSD sometimes fails on individual samples with low-quality or low-coverage data. With this flag, the rest of the pipeline still runs.
* `--rerun-trigger mtime` re-runs a step only when its input files have changed since the last run, instead of Snakemake's more thorough (and slower) default checks.

**A few other flags you might want:**

* `--dryrun` (or `-n`): show what the pipeline *would* do, without running anything. Use it to check if pastForward picks up all your data correctly (this is what `./pastForward dryrun` runs for you).
* `--configfile <path_to_config.yaml>`: use a config file other than the default.
* `--rerun-incomplete`: pick back up rules that failed or were cancelled in a previous run (this is what `./pastForward resume` runs for you).
* `--rerun-trigger <code|input|mtime|params|software-env>`: choose what counts as "changed" when deciding whether to re-run a step. By default, all of these are checked, which is the safest option. `mtime` (used above) checks only file modification times, which is faster but less thorough.
* `--unlock`: clear a stale Snakemake lock left by a crashed run (this is what `./pastForward unlock` runs for you).

For the full list of Snakemake's command-line options, see the [Snakemake documentation](https://snakemake.readthedocs.io/en/stable/executing/cli.html).

## Running in the Background

Large datasets can take a while to process, so it's often best to run pastForward in the background. That way it keeps running even if you close your terminal window. `./pastForward run` does this by default. The equivalent with plain `snakemake` is:

```bash
nohup snakemake --cores 40 --use-conda --keep-going --rerun-trigger mtime > pipeline.log 2>&1 &
```

This starts the pipeline and sends all its output to a file called `pipeline.log`. Check progress any time with `tail -f pipeline.log`.

## Restarting the Pipeline

Snakemake keeps track of what's already been done and only re-runs steps that are missing or out of date. To start completely over, delete the relevant `results` and `processed` folders and run the pipeline again.

If the pipeline crashed or was stopped partway through, add `--rerun-incomplete` when you restart it (or use `./pastForward resume`). This re-runs any step that was left unfinished, even if its files look unchanged since the last run.

If a stale Snakemake lock is left behind by a hard crash, clear it with `--unlock` (or `./pastForward unlock`) before re-running.

## Forcing a Re-run

To redo a specific step, delete its output file and re-run, or use `--forcerun <rule_name>` to force a specific rule. Use `--touch` with `--forceall` to mark all outputs as up to date without re-running (use as a last resort). Check the Snakemake documentation for more options on controlling rule execution.

## Benchmarking a Run

Every step of the pipeline records how long it took and how much memory it used. Snakemake writes one small file per job, named after that step's log file with `.benchmark.jsonl` instead of `.log`, so the measurements sit next to the step they belong to. This is always on and needs no flag. It costs nothing measurable in runtime and one tiny file per job.

Summarize them with:

```bash
./pastForward benchmark
```

That prints one row per rule: how many jobs ran, the median and longest wall time, the highest peak memory, total core-hours, and the largest input a job of that rule was given. Rules are listed most expensive first, so the top of the table is where a run spends its time.

```bash
./pastForward benchmark --emit-profile
```

adds a Snakemake `set-resources:` block built from those numbers, with the wall time doubled and the memory multiplied by 1.5 for headroom. It is a starting point for the resource requests an HPC cluster needs, not a finished answer. Paste it into a [Snakemake profile](https://snakemake.readthedocs.io/en/stable/executing/cli.html#profiles), or pass single entries as `--set-resources <rule>:<resource>=<value>`.

**What these numbers can and cannot tell you:**

* **They only cover jobs that actually ran.** A benchmark file is not a pipeline output, so a missing one never causes a re-run. On a project that is already finished, there is nothing to summarize until something runs again. To measure a full pipeline, use a fresh project folder, or add `--forceall`.
* **A failed step records nothing.** Snakemake writes the file only after a job succeeds, so a step that ran out of memory and was killed leaves no trace. The numbers always come from a run that worked.
* **On macOS you get wall time only.** Snakemake samples memory through psutil, which macOS does not let a process read for its own children. Every memory, CPU and I/O column comes out as `NA`. For memory numbers, measure on Linux.
* **Peak memory is a sample, not an exact peak.** It is measured every 0.5 seconds for the first 15 seconds and every 30 seconds after that, so a short spike later in a long job can be missed. It is good enough to size a request with headroom.
* **The three reference-indexing steps are not measured.** They are marked as eligible for Snakemake's between-workflow caching, and Snakemake does not allow a step to be both cacheable and benchmarked. To measure one of them, remove its `cache:` line in `workflow/rules/reference_module/processing/prepare_reference_for_mapping.smk`.

To delete the files again:

```bash
find . -name '*.benchmark.jsonl' -delete
```

## Resource Defaults

pastForward ships a [Snakemake profile](https://snakemake.readthedocs.io/en/stable/executing/cli.html#profiles) at `workflow/profiles/default/config.yaml`. Snakemake finds it by itself, with no flag, because it sits next to the `Snakefile`. It does two things:

* It sets `--keep-going` and `--rerun-trigger mtime` from the suggested command above, so a plain `snakemake` call decides what to re-run, and what to do about a failed step, the same way `./pastForward run` does. You still have to pass `--use-conda` yourself (see below).
* It gives every step a default memory (8 GB) and wall time (4 hours) request, for steps that don't ask for something specific themselves.

The memory and time defaults only matter on a cluster, where every job has to say how much it needs (see below). On a single machine they change nothing: Snakemake only limits how many jobs run at once if you give it a total budget with `--resources mem_mb=<N>`, which nothing does by default.

They are a generous floor, not measurements. To get real numbers for your data, run the pipeline once and then:

```bash
./pastForward benchmark --emit-profile
```

This prints a `set-resources:` block measured from that run, which you can paste into the profile below the `default-resources:` block. A `set-resources:` entry also overrides a value written into a rule, which `default-resources:` does not.

**To change a setting, edit `workflow/profiles/default/config.yaml`, or override it on the command line:**

```bash
# more memory for one step, just for this run
snakemake --cores 40 --set-resources run_busco_for_scg_determination:mem_mb=32000

# ignore the shipped profile completely
snakemake --cores 40 --use-conda --workflow-profile none
```

`--use-conda` is deliberately left out of the profile, so it is still the one flag you always have to type. The reason is that Snakemake checks your conda version and resolves every environment while it builds the job graph, and refuses to run at all on conda older than 24.7.1. Defaulting it would apply that to `--dryrun` too, so checking whether the pipeline found your data would need a working conda first. Leaving it out keeps a dry run free of all that.

Do **not** create your own `profiles/default/` folder in your project folder to change one value. Snakemake uses that one *instead* of the shipped one rather than merging the two, so you would silently lose every other setting. See [the FAQ](FAQ.md) for the safe ways to override.

## Running on an HPC Cluster

pastForward is a standard Snakemake workflow, so it should work with Snakemake's [cluster/HPC execution support](https://snakemake.readthedocs.io/en/stable/executing/cluster.html) (for example, Slurm or PBS) via the matching [executor plugin](https://snakemake.github.io/snakemake-plugin-catalog/), with no changes to the pipeline itself. This hasn't been specifically tested yet on a Slurm-based cluster, though that's planned. If you try it, feedback is very welcome.

Two things are worth knowing before you try.

**Every job needs a memory and a time request, and the shipped profile gives it one.** Without those, a batch system falls back to the partition's defaults, and a partition wall time is often under an hour, which kills the longer steps partway through. The [resource defaults](#resource-defaults) above cover this with a generous floor. Replace them with measured numbers (`./pastForward benchmark --emit-profile`) before a large run, because a floor that fits the small steps is not the same as a request that fits the big ones.

**Cluster settings belong in a separate profile, not in the shipped one.** Things like the account and partition to submit to are specific to your machine, so keep them apart from the pipeline's own resource numbers. Write your own profile folder and pass it with `--profile`. Snakemake merges the two, so you don't have to repeat anything from the shipped one:

```yaml
# my_slurm_profile/config.yaml
executor: slurm
jobs: 100
latency-wait: 60
default-resources:
  slurm_account: "your_account"
  slurm_partition: "your_partition"
```

```bash
./pastForward run --profile my_slurm_profile --jobs 100
```

This needs `snakemake-executor-plugin-slurm` installed alongside Snakemake. Also note that compute nodes often have no internet access, while many steps download their software the first time they run, so build the environments on the login node first with `./pastForward doctor --rebuild-envs`.

# =================================================================================================
#     Benchmarking
# =================================================================================================
# Attaches a benchmark file to every rule in the workflow, so a run records how long each job took
# and how much memory it used. `./pastForward benchmark` turns the resulting files into a per-rule
# resource table.
#
# Snakemake has no global "benchmark everything" switch, and a `benchmark:` directive repeated in
# every rule definition would be well over a hundred near-identical lines to keep in sync. The
# `benchmark` property is settable after a rule is defined, so this file attaches them all in one
# pass instead. It must therefore be included AFTER every rule file.
#
# The benchmark path mirrors the rule's own `log:` path, with `.log` swapped for
# `.benchmark.jsonl`. Snakemake requires a benchmark file to carry exactly the same wildcards as
# the rule's output and log files, and the log path satisfies that by construction, for every
# rule, with nothing to check per rule. Every rule has a `log:` today, so the fallback to the
# first output file below only exists to keep a future rule that forgets one from silently
# losing its measurements. The `.jsonl` suffix makes Snakemake write JSON lines instead of TSV.
#
# Three things worth knowing about the measurements themselves:
#   - A missing benchmark file never triggers a re-run, because Snakemake's up-to-date check only
#     looks at `output:`. Switching this on therefore invalidates nothing, but it also produces
#     nothing on a finished project: files appear only as jobs actually run.
#   - A failed job writes no benchmark at all, since Snakemake re-raises the error before writing
#     the record. The job that runs out of memory leaves nothing behind.
#   - The three reference-indexing rules are marked `cache: True`, and Snakemake does not allow
#     a rule to be cacheable and benchmarked at once, so they are skipped. To measure one of
#     them, drop its `cache:` line in
#     workflow/rules/reference_module/processing/prepare_reference_for_mapping.smk.
#   - On macOS every column except wall time is "NA": the sampler calls psutil's
#     memory_full_info(), which is denied on darwin even for the process's own children. Memory
#     numbers have to be measured on Linux.
#
# To delete them all again: find . -name '*.benchmark.jsonl' -delete


BENCHMARK_SUFFIX = ".benchmark.jsonl"

try:
    # Record the extended fields (rule name, wildcards, threads, resources, per-input file sizes)
    # rather than the ten-column default, which does not even say which rule produced it. Set here
    # rather than as a `--benchmark-extended` flag so it also applies to a plain `snakemake` call.
    workflow.output_settings.benchmark_extended = True

    for _benchmark_rule in workflow.rules:
        if _benchmark_rule.benchmark is not None:
            continue
        # Snakemake refuses to let a rule be both benchmarked and eligible for between-workflow
        # caching (`cache: True`), because a result served from the cache has no run to measure.
        # It raises a WorkflowError at DAG build time, well after this loop, so skip those rules
        # here rather than letting them break the run. Where that flag lives moved between
        # versions: 9.9.0 keeps it on the workflow, 9.25.1 hangs a RuleCache off every rule
        # whose `.output` says whether caching is actually on. An unrecognized future shape is
        # treated as cached, which costs one rule's measurements rather than the whole run.
        _benchmark_cache = getattr(_benchmark_rule, "cache", None)
        if _benchmark_cache is not None:
            _benchmark_cached = getattr(_benchmark_cache, "output", True)
        else:
            _benchmark_cached = bool(
                getattr(workflow, "cache_rules", {}).get(_benchmark_rule.name)
            )
        if _benchmark_cached:
            continue
        if _benchmark_rule.log:
            _benchmark_target = str(_benchmark_rule.log[0])
            _benchmark_modifier = _benchmark_rule.log_modifier
            if _benchmark_target.endswith(".log"):
                _benchmark_target = _benchmark_target[: -len(".log")]
        elif _benchmark_rule.output:
            _benchmark_target = str(_benchmark_rule.output[0])
            _benchmark_modifier = _benchmark_rule.output_modifier
        else:
            # `all` and anything else with neither a log nor an output. Nothing to hang a
            # benchmark file off, and nothing worth measuring either.
            continue
        # Assigning `benchmark` runs the path through apply_path_modifier(), which asserts the
        # modifier is not None. Snakemake only fills `benchmark_modifier` in for rules declared
        # inside a `module:`, so borrow the modifier belonging to the path just copied.
        _benchmark_rule.benchmark_modifier = _benchmark_modifier
        _benchmark_rule.benchmark = f"{_benchmark_target}{BENCHMARK_SUFFIX}"
except Exception as _benchmark_error:
    # `Rule.benchmark` and `Workflow.output_settings` are internals, not documented API, so a
    # Snakemake upgrade could change them. Losing the measurements is an inconvenience; refusing
    # to run the pipeline over them is not acceptable, so warn and carry on.
    logger.warning(
        f"Could not attach benchmark files to the workflow "
        f"({type(_benchmark_error).__name__}: {_benchmark_error}). "
        f"The run continues normally, but `./pastForward benchmark` will have nothing to report. "
        f"This usually means a Snakemake upgrade changed an internal API."
    )

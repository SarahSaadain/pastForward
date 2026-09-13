"""benchmark: summarize the per-job benchmark files every run writes."""
import json
import math
import os
import statistics
from pathlib import Path

from .common import CYAN, DIM, YELLOW, _color, _die, _ensure_project_root, _format_duration


# Written by every rule, via workflow/rules/benchmark.smk. One JSON line per job.
BENCHMARK_SUFFIX = ".benchmark.jsonl"
# Snakemake writes "NA" wherever it could not sample a value: a job that finished before the
# first sample, or any job at all on macOS, where psutil is denied a child process's memory.
BENCHMARK_MISSING = "NA"
# `runtime` is in minutes and `mem_mb` in MB, both at the observed maximum plus headroom.
BENCHMARK_RUNTIME_FACTOR = 2.0
BENCHMARK_MEM_FACTOR = 1.5


def _find_benchmark_files(root="."):
    # os.walk rather than Path.rglob because rglob never descends into a symlinked directory,
    # and a species' processed/ or results/ folder is a symlink whenever the config points it
    # outside the project (see workflow/scripts/species_paths.py) - which is exactly the setup
    # where all the benchmark files live behind one.
    files = []
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        # followlinks=True can otherwise walk forever around a symlink cycle.
        real = os.path.realpath(dirpath)
        if real in seen:
            dirnames[:] = []
            continue
        seen.add(real)
        # Skip the pipeline's own code and every dot-directory (.snakemake, .git, .pastforward):
        # no run ever writes a benchmark file there.
        dirnames[:] = [d for d in dirnames if d != "workflow" and not d.startswith(".")]
        files += [os.path.join(dirpath, f) for f in filenames if f.endswith(BENCHMARK_SUFFIX)]
    return sorted(files)


def _benchmark_number(value):
    """A benchmark field as a float, or None if Snakemake could not measure it."""
    if value is None or value == BENCHMARK_MISSING:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_benchmark_records(paths):
    """Parse benchmark files into records. Returns (records, unreadable_paths)."""
    records, unreadable = [], []
    for path in paths:
        try:
            lines = Path(path).read_text().splitlines()
        except OSError:
            unreadable.append(path)
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                unreadable.append(path)
                break
    return records, unreadable


def _summarize_benchmarks(records):
    """Group benchmark records per rule. Returns rows sorted by total core-hours, descending."""
    by_rule = {}
    for record in records:
        # rule_name is an extended-format field. benchmark.smk turns the extended format on for
        # the whole workflow, so it is only missing for files written before that landed.
        by_rule.setdefault(record.get("rule_name") or "(unknown rule)", []).append(record)

    rows = []
    for rule_name, group in by_rule.items():
        seconds = [s for s in (_benchmark_number(r.get("s")) for r in group) if s is not None]
        memory = [m for m in (_benchmark_number(r.get("max_rss")) for r in group) if m is not None]
        core_seconds = sum(
            (_benchmark_number(r.get("s")) or 0) * (_benchmark_number(r.get("threads")) or 1) for r in group
        )
        input_sizes = [
            sum(r["input_size_mb"].values()) for r in group if isinstance(r.get("input_size_mb"), dict)
        ]
        rows.append(
            {
                "rule": rule_name,
                "jobs": len(group),
                "median_s": statistics.median(seconds) if seconds else None,
                "max_s": max(seconds) if seconds else None,
                "max_rss_mb": max(memory) if memory else None,
                "core_hours": core_seconds / 3600,
                "max_input_mb": max(input_sizes) if input_sizes else None,
            }
        )
    return sorted(rows, key=lambda row: row["core_hours"], reverse=True)


def _emit_benchmark_profile(rows):
    print("# Snakemake resource settings derived from the benchmarks above. Paste into")
    print("# workflow/profiles/default/config.yaml, below its `default-resources:` block, or")
    print("# pass individual entries as `--set-resources <rule>:<resource>=<value>`.")
    print(
        f"# runtime is in minutes at {BENCHMARK_RUNTIME_FACTOR:g}x the longest job observed; mem_mb is "
        f"{BENCHMARK_MEM_FACTOR:g}x the highest peak memory observed."
    )
    print("# These are starting points measured on one dataset on one machine, not limits.")
    print("set-resources:")
    for row in rows:
        if row["max_s"] is None:
            continue
        print(f"  {row['rule']}:")
        print(f"    runtime: {max(1, math.ceil(BENCHMARK_RUNTIME_FACTOR * row['max_s'] / 60))}")
        if row["max_rss_mb"] is not None:
            print(f"    mem_mb: {max(1, math.ceil(BENCHMARK_MEM_FACTOR * row['max_rss_mb']))}")


def _print_benchmark_table(rows):
    headers = ("Rule", "Jobs", "Median", "Max", "Max RSS", "Core-h", "Max input")
    body = [
        (
            row["rule"],
            str(row["jobs"]),
            _format_duration(row["median_s"]) if row["median_s"] is not None else "-",
            _format_duration(row["max_s"]) if row["max_s"] is not None else "-",
            f"{row['max_rss_mb']:.0f} MB" if row["max_rss_mb"] is not None else "-",
            f"{row['core_hours']:.2f}",
            f"{row['max_input_mb']:.0f} MB" if row["max_input_mb"] is not None else "-",
        )
        for row in rows
    ]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *body)]

    def _row(cells):
        # Rule names left, every measured number right, so the columns line up on the decimal.
        return cells[0].ljust(widths[0]) + "  " + "  ".join(c.rjust(w) for c, w in zip(cells[1:], widths[1:]))

    print(_color(CYAN, _row(headers)))
    for cells in body:
        print(_row(cells))


def cmd_benchmark(argv):
    _ensure_project_root(require_snakemake=False)
    emit_profile = "--emit-profile" in argv
    rest = [a for a in argv if a != "--emit-profile"]
    if rest:
        _die(f"pastForward benchmark: unknown argument(s): {' '.join(rest)}")

    paths = _find_benchmark_files()
    if not paths:
        _die(
            f"pastForward: no {BENCHMARK_SUFFIX} files found here. They are written as jobs run, "
            "so a finished project has none until something actually re-runs."
        )
    records, unreadable = _load_benchmark_records(paths)
    if not records:
        _die(f"pastForward: found {len(paths)} benchmark file(s), but none of them held a usable record.")
    rows = _summarize_benchmarks(records)

    print(
        _color(CYAN, "Benchmarks:")
        + f" {len(records)} job(s) across {len(rows)} rule(s), from {len(paths)} file(s)."
    )
    print()
    _print_benchmark_table(rows)

    no_memory = [row for row in rows if row["max_rss_mb"] is None]
    print()
    if no_memory:
        print(
            _color(
                YELLOW,
                f"No memory was recorded for {len(no_memory)} of {len(rows)} rule(s).",
            )
        )
        print(
            _color(
                DIM,
                "  Snakemake cannot read a child process's memory on macOS, and a job shorter than\n"
                "  about half a second finishes before the first sample either way. For usable memory\n"
                "  numbers, measure on Linux.",
            )
        )
    print(
        _color(
            DIM,
            "Peak memory is sampled every 0.5s for the first 15s and every 30s after that, so it is\n"
            "an estimate to size a request from, not an exact peak. A job that failed wrote no\n"
            "benchmark at all, so a rule that ran out of memory is missing from this table.",
        )
    )
    if unreadable:
        print(_color(YELLOW, f"{len(unreadable)} file(s) could not be read and were skipped."))
    if emit_profile:
        print()
        _emit_benchmark_profile(rows)

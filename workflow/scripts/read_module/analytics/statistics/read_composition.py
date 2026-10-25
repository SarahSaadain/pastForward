"""Split the adapter-removed reads of each sample into merged, unmerged and unpaired reads.

Uses only files that already exist after adapter removal: the fastp JSON report and the
adapter-removed read count. The trimmed FASTQ parts are temp files, so counting them
directly would rerun fastp and everything after it.

How the split is derived for paired-end samples (fastp with --merge):
- merged   M = merged_and_filtered.total_reads
- fastp counts the filter result per pair for both mates. A pair with one failing mate
  counts as 2 failed reads, even though the good mate is kept as an unpaired read.
  So passed_filter_reads = 2*M + unmerged reads, and unmerged = passed - 2*M.
- unpaired = adapter-removed count - M - unmerged.
"""

import csv
import json

COUNT_COLUMNS = ["merged_reads", "unmerged_reads", "unpaired_reads", "single_end_reads"]
PERCENT_COLUMNS = [c.replace("_reads", "_percent") for c in COUNT_COLUMNS]


def _add_percent(row):
    total = row["adapter_removed_reads"]
    for count, percent in zip(COUNT_COLUMNS, PERCENT_COLUMNS):
        row[percent] = round(100 * row[count] / total, 2) if total else 0.0
    return row


def sample_composition(sample, adapter_removed_reads, fastp, paired=None):
    """One row for a sample. `fastp` is the parsed fastp JSON report.

    `fastp=None` means adapter removal was skipped: nothing was merged, so the reads of a
    paired-end sample are all unmerged, and `paired` must be given.
    """
    if fastp is None and paired is None:
        raise ValueError(f"{sample}: without a fastp report the layout must be given")
    if paired is None:
        paired = "merged_and_filtered" in fastp
    row = {
        "sample": sample,
        "individual": sample.split("_")[0],
        "layout": "paired" if paired else "single",
        "adapter_removed_reads": adapter_removed_reads,
        **dict.fromkeys(COUNT_COLUMNS, 0),
    }
    if not paired:
        row["single_end_reads"] = adapter_removed_reads
        return _add_percent(row)
    if fastp is None:
        row["unmerged_reads"] = adapter_removed_reads
        return _add_percent(row)

    try:
        merged = fastp["merged_and_filtered"]["total_reads"]
        passed = fastp["filtering_result"]["passed_filter_reads"]
    except KeyError as e:
        raise ValueError(
            f"{sample}: fastp JSON has no {e} field. Was fastp run with --merge?"
        ) from None
    unmerged = passed - 2 * merged
    unpaired = adapter_removed_reads - merged - unmerged
    if unmerged < 0 or unmerged % 2 or unpaired < 0:
        raise ValueError(
            f"{sample}: fastp JSON (passed={passed}, merged={merged}) does not fit the "
            f"adapter-removed count ({adapter_removed_reads}). Reports may be from different "
            f"runs, or a fastp option such as --include_unmerged changed the output."
        )
    row.update(merged_reads=merged, unmerged_reads=unmerged, unpaired_reads=unpaired)
    return _add_percent(row)


def by_individual(rows):
    """Sum sample rows per individual. Layout is 'mixed' when PE and SE samples meet."""
    out = {}
    for r in rows:
        ind = out.setdefault(
            r["individual"],
            {
                "individual": r["individual"],
                "samples": 0,
                "layout": r["layout"],
                "adapter_removed_reads": 0,
                **dict.fromkeys(COUNT_COLUMNS, 0),
            },
        )
        ind["samples"] += 1
        if ind["layout"] != r["layout"]:
            ind["layout"] = "mixed"
        for c in ["adapter_removed_reads"] + COUNT_COLUMNS:
            ind[c] += r[c]
    return [_add_percent(out[k]) for k in sorted(out)]


def _write(path, rows, first_columns):
    columns = first_columns + ["adapter_removed_reads"] + COUNT_COLUMNS + PERCENT_COLUMNS
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    # No fastp reports when adapter removal is skipped.
    json_paths = list(snakemake.input.fastp_json) or [None] * len(snakemake.params.samples)
    rows = []
    for sample, paired, json_path, count_path in zip(
        snakemake.params.samples, snakemake.params.paired, json_paths, snakemake.input.counts
    ):
        with open(count_path) as f:
            count = int(f.read().strip())
        fastp = None
        if json_path:
            with open(json_path) as f:
                fastp = json.load(f)
        rows.append(sample_composition(sample, count, fastp, paired=paired))
    rows.sort(key=lambda r: r["sample"])
    _write(snakemake.output.by_sample, rows, ["sample", "individual", "layout"])
    _write(snakemake.output.by_individual, by_individual(rows), ["individual", "samples", "layout"])

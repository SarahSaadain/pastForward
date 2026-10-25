"""
One authenticity triage row per individual, collected from files earlier steps already
keep on disk. Nothing is computed from a BAM here.

Each input group is a list with one file per individual, in the order of `individuals`.
An empty group means its step is switched off: its columns are NA and nothing is reported.
A file from a switched-on step that is missing or unreadable gives NA too, and the
individual gets verdict no_data unless a threshold already says check. This script never
fails on such a file, so one incomplete individual does not block the table.

ct_5p_pos1 and ga_3p_pos1 come from mapDamage run on the deduplicated (or sorted) BAM,
never the rescaled one. Rescaling removes the damage signal this table measures, so do not
"fix" the mapDamage input to the rescaled BAM.
"""
import csv
import json
import sys

VERDICT_OK = "ok"
VERDICT_CHECK = "check"
VERDICT_NO_DATA = "no_data"

# The only place the defaults live. Config keys authenticity_<name> override them one by one.
DEFAULT_THRESHOLDS = {
    "min_endogenous_percent": 10.0,
    "min_ct_5p_pos1": 0.01,
    "min_median_mapped_length": 30,
    "max_duplicate_rate": 0.5,
    "min_mean_depth": 1.0,
}

COLUMNS = [
    "individual",
    "n_samples",
    "total_reads",
    "mapped_reads",
    "endogenous_percent",
    "duplicate_rate",
    "cluster_factor",
    "median_mapped_length",
    "mean_mapped_length",
    "ct_5p_pos1",
    "ga_3p_pos1",
    "mean_depth",
    "breadth_percent",
    "mean_mapq",
    "verdict",
    "verdict_reason",
]

FORMATS = {
    "endogenous_percent": ".4f",
    "duplicate_rate": ".4f",
    "cluster_factor": ".4f",
    "mean_mapped_length": ".2f",
    "ct_5p_pos1": ".4f",
    "ga_3p_pos1": ".4f",
    "mean_depth": ".4f",
    "breadth_percent": ".4f",
    "mean_mapq": ".2f",
}


def parse_mean_mapq(path):
    # MAPQ lines exist only in newer samtools stats output. Without them the column is NA.
    reads = weighted = 0
    with open(path) as f:
        for line in f:
            if line.startswith("MAPQ\t"):
                _, mapq, count = line.split("\t")[:3]
                reads += int(count)
                weighted += int(mapq) * int(count)
    return {"mean_mapq": weighted / reads if reads else None}


def parse_endogenous(path):
    with open(path) as f:
        row = next(csv.DictReader(f))
    return {
        "total_reads": int(row["total_reads"]),
        "mapped_reads": int(row["mapped_reads"]),
        "endogenous_percent": float(row["proportion"]),
    }


def parse_dedup(path):
    with open(path) as f:
        metrics = json.load(f)["metrics"]
    return {
        "duplicate_rate": float(metrics["dup_rate"]),
        "cluster_factor": float(metrics["clusterfactor"]),
    }


def _position_one(path):
    with open(path) as f:
        for line in f:
            fields = line.split()
            if fields and fields[0] == "1":
                return float(fields[1])
    raise ValueError("no position 1 row")


def parse_ct5p(path):
    return {"ct_5p_pos1": _position_one(path)}


def parse_ga3p(path):
    return {"ga_3p_pos1": _position_one(path)}


def parse_lengths(path):
    # lgdistribution.txt lists mapped read lengths per strand, so lengths are summed over
    # both strands. These are lengths of mapped reads, not of the whole library.
    counts = {}
    with open(path) as f:
        for line in f:
            fields = line.split()
            if len(fields) < 3 or line.startswith("#") or fields[0] not in ("+", "-"):
                continue
            length = int(fields[1])
            counts[length] = counts.get(length, 0) + int(fields[2])
    total = sum(counts.values())
    if not total:
        raise ValueError("no length rows")
    seen = 0
    for length in sorted(counts):
        seen += counts[length]
        if seen * 2 >= total:
            median = length
            break
    mean = sum(length * count for length, count in counts.items()) / total
    return {"median_mapped_length": median, "mean_mapped_length": mean}


def parse_coverage(path):
    depth_sum = covered = total = 0
    with open(path) as f:
        for row in csv.DictReader(f):
            bases = int(row["total_bases"])
            depth_sum += float(row["avg_depth"]) * bases
            covered += int(row["covered_bases"])
            total += bases
    if not total:
        raise ValueError("no scaffold rows")
    return {"mean_depth": depth_sum / total, "breadth_percent": covered / total * 100}


PARSERS = {
    "stats": parse_mean_mapq,
    "endogenous": parse_endogenous,
    "dedup": parse_dedup,
    "ct5p": parse_ct5p,
    "ga3p": parse_ga3p,
    "lengths": parse_lengths,
    "coverage": parse_coverage,
}


def threshold_reasons(row, thresholds):
    checks = [
        ("endogenous_percent", "<", thresholds["min_endogenous_percent"]),
        ("ct_5p_pos1", "<", thresholds["min_ct_5p_pos1"]),
        ("median_mapped_length", "<", thresholds["min_median_mapped_length"]),
        ("duplicate_rate", ">", thresholds["max_duplicate_rate"]),
        ("mean_depth", "<", thresholds["min_mean_depth"]),
    ]
    reasons = []
    for column, op, limit in checks:
        value = row.get(column)
        if value is None:
            continue
        if (op == "<" and value < limit) or (op == ">" and value > limit):
            reasons.append(f"{column}{op}{limit:g}")
    return reasons


def summarize_individual(individual, n_samples, files, thresholds):
    """files maps an input group to this individual's file, or None when the step is off."""
    row = {"individual": individual, "n_samples": n_samples}
    missing = []
    for group, path in files.items():
        if path is None:
            continue
        try:
            row.update(PARSERS[group](path))
        except (OSError, ValueError, KeyError, StopIteration, IndexError) as e:
            print(f"{individual}: could not read {group} file {path}: {type(e).__name__} {e}", file=sys.stderr)
            missing.append(group)
    reasons = threshold_reasons(row, thresholds)
    if reasons:
        row["verdict"] = VERDICT_CHECK
    elif missing:
        row["verdict"] = VERDICT_NO_DATA
    else:
        row["verdict"] = VERDICT_OK
    row["verdict_reason"] = ";".join(reasons + [f"missing_{group}" for group in missing])
    return row


def _cell(column, value):
    if value is None:
        return "NA"
    if column in FORMATS:
        return format(value, FORMATS[column])
    return str(value)


def create_authenticity_summary(individuals, n_samples, inputs, threshold_overrides, output_path):
    thresholds = {**DEFAULT_THRESHOLDS, **threshold_overrides}
    rows = []
    for index, individual in enumerate(individuals):
        files = {group: (paths[index] if paths else None) for group, paths in inputs.items()}
        rows.append(summarize_individual(individual, n_samples[index], files, thresholds))
    with open(output_path, "w") as out:
        out.write("\t".join(COLUMNS) + "\n")
        for row in sorted(rows, key=lambda r: r["individual"]):
            out.write("\t".join(_cell(c, row.get(c)) for c in COLUMNS) + "\n")
    flagged = [row["individual"] for row in rows if row["verdict"] != VERDICT_OK]
    print(f"{len(flagged)} of {len(rows)} individual(s) not ok: {', '.join(flagged) or 'none'}")


if __name__ == "__main__":
    sys.stdout = sys.stderr = open(snakemake.log[0], "w")
    create_authenticity_summary(
        list(snakemake.params.individuals),
        list(snakemake.params.n_samples),
        {group: list(snakemake.input.get(group, [])) for group in PARSERS},
        {
            key: float(value)
            for key, value in snakemake.params.threshold_overrides.items()
            if key in DEFAULT_THRESHOLDS
        },
        snakemake.output.tsv,
    )

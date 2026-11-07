"""Per-scaffold depth and breadth straight from the BAM, without a per-base file on disk.

`samtools depth` (no -aa) is streamed into pandas. Total bases come from the BAM header, so
zero-depth positions never need to be printed. The CSV matches the old
`samtools depth -aa` file + pandas result byte for byte, including row order.
"""

import subprocess
import sys

import numpy as np
import pandas as pd

CHUNK = 10**7


def summarize_depth_stream(stream, names, lengths, chunksize=CHUNK):
    """Sum `samtools depth` lines (scaffold, position, depth) per scaffold.

    Returns one (scaffold, depth_sum, max_depth, covered_bases, total_bases) tuple per header
    scaffold, in header order. Scaffolds with no line get zeros.
    """
    acc = {}
    try:
        for chunk in pd.read_csv(
            stream,
            sep="\t",
            header=None,
            names=["scaffold", "position", "depth"],
            usecols=[0, 2],
            # Scaffold names stay text: "4" is not a number and "NA" is a name, not missing
            dtype={"scaffold": "category", "depth": np.int64},
            keep_default_na=False,
            chunksize=chunksize,
        ):
            codes = chunk["scaffold"].cat.codes.to_numpy()
            depth = chunk["depth"].to_numpy()
            cats = chunk["scaffold"].cat.categories
            k = len(cats)
            sums = np.zeros(k, np.int64)
            np.add.at(sums, codes, depth)
            maxes = np.zeros(k, np.int64)
            np.maximum.at(maxes, codes, depth)
            covered = np.bincount(codes[depth > 0], minlength=k)
            for c in np.flatnonzero(np.bincount(codes, minlength=k)):
                a = acc.setdefault(str(cats[c]), [0, 0, 0])
                a[0] += int(sums[c])
                a[1] = max(a[1], int(maxes[c]))
                a[2] += int(covered[c])
    except pd.errors.EmptyDataError:
        pass  # no covered base at all
    unknown = set(acc) - set(names)
    if unknown:
        raise RuntimeError(
            f"samtools depth reported scaffolds not in the BAM header: {sorted(unknown)[:5]}"
        )
    return [(n, *acc.get(n, (0, 0, 0)), L) for n, L in zip(names, lengths)]


def legacy_order(rows, chunk=10**6):
    """Row order of the old script: the -aa file (header order, one line per base) read in
    1M-line chunks, scaffolds sorted by name inside each chunk, first-seen order kept.
    The combine step sums rows in file order, so another order could change the last float digit.
    """
    seen, out, i, pos, bounds = set(), [], 0, 0, []
    for r in rows:
        bounds.append((pos, pos + r[4], r))
        pos += r[4]
    for k in range(0, pos, chunk):
        while i < len(bounds) and bounds[i][1] <= k:
            i += 1
        j, here = i, []
        while j < len(bounds) and bounds[j][0] < k + chunk:
            here.append(bounds[j][2])
            j += 1
        for r in sorted(here, key=lambda r: r[0]):
            if r[0] not in seen:
                seen.add(r[0])
                out.append(r)
    return out


def write_summary(rows, out):
    summary = pd.DataFrame(
        legacy_order(rows),
        columns=["scaffold", "depth_sum", "max_depth", "covered_bases", "total_bases"],
    )
    summary = summary.set_index("scaffold").astype("int64")
    summary["avg_depth"] = summary["depth_sum"] / summary["total_bases"]
    summary["percent_covered"] = (summary["covered_bases"] / summary["total_bases"]) * 100
    summary[["avg_depth", "max_depth", "covered_bases", "total_bases", "percent_covered"]].to_csv(out)


def coverage_rows(bam, log=sys.stderr):
    import pysam  # here, not at the top: the unit tests run without pysam

    with pysam.AlignmentFile(bam) as f:
        names, lengths = f.references, f.lengths
    proc = subprocess.Popen(["samtools", "depth", bam], stdout=subprocess.PIPE, stderr=log)
    try:
        return summarize_depth_stream(proc.stdout, names, lengths)
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError(f"samtools depth failed on {bam} (exit {proc.returncode})")


if __name__ == "__main__":
    if "snakemake" in globals():
        with open(snakemake.log[0], "w") as log:
            write_summary(coverage_rows(snakemake.input.bam, log), snakemake.output.analysis)
    else:
        write_summary(coverage_rows(sys.argv[1]), sys.argv[2])

"""Sum the mapDamage count tables of the per-contig chunks into one table per individual.

The tables are plain counts per key (contig, end, strand, position or strand, length), and
every read sits in exactly one chunk, so the sums equal the tables of one full mapDamage run.
"""

import sys
from pathlib import Path

# Table file name -> (output tag in the rule, key columns). misincorporation and dnacomp are
# keyed by Chr End Std Pos, lgdistribution by Std Length.
TABLES = {
    "misincorporation.txt": ("misinc", 4),
    "dnacomp.txt": ("dnacomp", 4),
    "lgdistribution.txt": ("lg_dist", 2),
}


def combine_chunk_tables(chunk_paths, out_path, n_keys):
    """Write the table that sums every chunk table in chunk_paths, keyed by the first n_keys columns.

    Rows keep the order in which their key first appears. The first chunk's comments are kept,
    except the per-chunk "using mapped file" line, which becomes one summary line at the end.
    """
    header, version_lines, totals = None, [], {}
    for path in chunk_paths:
        lines = Path(path).read_text().splitlines(keepends=True)
        comments = [line for line in lines if line.startswith("#")]
        body = [line for line in lines if not line.startswith("#")]
        if header is None:
            header = body[0]
            version_lines = [
                line for line in comments if "using mapped file" not in line
            ]
        elif body[0] != header:
            raise ValueError(f"{path}: header {body[0]!r} differs from {header!r}")
        for line in body[1:]:
            fields = line.rstrip("\n").split("\t")
            key = tuple(fields[:n_keys])
            counts = [int(value) for value in fields[n_keys:]]
            if key in totals:
                totals[key] = [a + b for a, b in zip(totals[key], counts)]
            else:
                totals[key] = counts

    with open(out_path, "w") as out:
        out.writelines(version_lines)
        out.write(f"# summed over {len(chunk_paths)} per-contig chunk tables\n")
        out.write(header)
        for key, counts in totals.items():
            out.write("\t".join([*key, *map(str, counts)]) + "\n")


if __name__ == "__main__":
    sys.stdout = sys.stderr = open(snakemake.log[0], "w")
    for name, (tag, n_keys) in TABLES.items():
        chunk_paths = [p for p in snakemake.input if Path(p).name == name]
        combine_chunk_tables(chunk_paths, snakemake.output[tag], n_keys)

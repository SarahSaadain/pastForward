from isal import igzip


def get_fastq_read_count(fastq_file):
    """Count reads in a FASTQ file (handles gzipped files). Each read is 4 lines."""
    opener = igzip.open if fastq_file.endswith(".gz") else open
    with opener(fastq_file, "rb") as f:
        newlines = sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1 << 20), b""))
    # Round up so a file without a trailing newline still counts its last read
    return (newlines + 3) // 4


# Input is either FASTQ file(s), or a .count file from the previous step when
# that step was skipped, in which case its count is passed through unchanged.
files = list(snakemake.input)
if len(files) == 1 and files[0].endswith(".count"):
    with open(files[0]) as f:
        count = int(f.read().strip())
else:
    count = sum(get_fastq_read_count(f) for f in files)

with open(snakemake.output.counted, "w") as f:
    f.write(str(count))

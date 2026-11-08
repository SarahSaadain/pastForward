#!/usr/bin/env python3
import pandas as pd

# Snakemake input/output/params
centrifuge_file = snakemake.input[0]  # Centrifuge report
total_reads_file = snakemake.input[
    1
]  # File containing total number of reads (single number)
output_csv = snakemake.output[0]  # Output CSV
sample_name = snakemake.params.sample  # Sample name

# Read Centrifuge report
df = pd.read_csv(centrifuge_file, sep="\t")

# Read total reads
with open(total_reads_file) as f:
    total_reads = int(f.read().strip())


# Classified reads = sum of numReads excluding root
classified_reads = df["numReads"].sum()

# Uniquely classified reads = sum of numUniqueReads excluding root
unique_classified_reads = df["numUniqueReads"].sum()

non_unque_classified = classified_reads - unique_classified_reads

unclassified_reads = total_reads - classified_reads


# Create output DataFrame
summary = pd.DataFrame(
    [
        {
            "sample": sample_name,
            "unclassified_reads": unclassified_reads,
            "non_unique_classified_reads": non_unque_classified,
            "unique_classified_reads": unique_classified_reads,
        }
    ]
)

# Save TSV
summary.to_csv(output_csv, sep="\t", index=False)

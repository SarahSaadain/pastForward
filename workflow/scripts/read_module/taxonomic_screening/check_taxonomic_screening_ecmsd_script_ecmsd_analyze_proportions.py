#!/usr/bin/env python3
import pandas as pd

# Snakemake input/output/params
proportions_file = snakemake.input[0]  # Proportions file
total_reads_file = snakemake.input[1]  # File containing total number of reads
output_tsv = snakemake.output[0]
sample_name = snakemake.params.sample  #

# Read proportions file
df = pd.read_csv(proportions_file, sep="\t")

# Read total reads
with open(total_reads_file) as f:
    total_reads = int(f.read().strip())

# Classified reads = sum of TotalReads
classified_reads = df["TotalReads"].sum()


# Unclassified reads
unclassified_reads = total_reads - classified_reads

# Create summary DataFrame
summary = pd.DataFrame(
    [
        {
            "sample": sample_name,
            "unclassified_reads": unclassified_reads,
            "classified_reads": classified_reads,
        }
    ]
)

# Save TSV
summary.to_csv(output_tsv, sep="\t", index=False)

#!/usr/bin/env python3
import pandas as pd

# Snakemake input/output/params
input_file = snakemake.input[0]
output_unique = snakemake.output[0]
output_total = snakemake.output[1]
sample_name = snakemake.params.sample  # get sample name from Snakemake params
include_human = snakemake.params.get(
    "include_human", False
)  # get include_human flag from Snakemake params

# Read Centrifuge report
df = pd.read_csv(input_file, sep="\t")


def top_n_wide(df, col, sample_name, n=10):
    # Sort by column
    df_sorted = df.sort_values(by=col, ascending=False).copy()

    # add taxID to name
    df_sorted["name"] = df_sorted.apply(
        lambda row: f"{row['name']} (taxID:{row['taxID']})", axis=1
    )

    # Top N taxa
    top = df_sorted.iloc[:n].copy()
    others = df_sorted.iloc[n:]

    # Sum "others"
    others_sum = others[col].sum() if not others.empty else 0

    # Prepare wide format: taxon names as columns
    top_dict = dict(zip(top["name"], top[col]))
    top_dict["Others"] = others_sum
    top_dict["sample"] = sample_name

    # Convert to DataFrame with sample as first column
    wide_df = pd.DataFrame([top_dict])
    cols = ["sample"] + [c for c in wide_df.columns if c != "sample"]
    wide_df = wide_df[cols]
    return wide_df


# Create tables
df_unique = top_n_wide(df, "numUniqueReads", sample_name, n=10)
df_total = top_n_wide(df, "numReads", sample_name, n=10)

if not include_human:
    # Remove human taxa if present
    human_taxids = [9606]  # Common human tax
    df_unique = df_unique[
        [
            col
            for col in df_unique.columns
            if not any(str(taxid) in col for taxid in human_taxids)
        ]
    ]
    df_total = df_total[
        [
            col
            for col in df_total.columns
            if not any(str(taxid) in col for taxid in human_taxids)
        ]
    ]

# Write output
df_unique.to_csv(output_unique, sep="\t", index=False)
df_total.to_csv(output_total, sep="\t", index=False)

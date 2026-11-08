import os

import pandas as pd

input_files = snakemake.input
output_file = snakemake.output[0]

combined_df = pd.DataFrame()

for file in input_files:
    if os.path.exists(file):
        df = pd.read_csv(file, sep="\t")
        combined_df = pd.concat([combined_df, df], ignore_index=True)
    else:
        print(f"Warning: Input file {file} does not exist and will be skipped.")

# sort the columns: endogenous, duplicates, non_endogenous
columns_order = ["individual", "endogenous", "duplicates", "non_endogenous"]
combined_df = combined_df[columns_order]

combined_df.to_csv(output_file, sep="\t", index=False)

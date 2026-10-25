import pandas as pd

input_file = snakemake.input[0]
output_file = snakemake.output[0]

df = pd.read_csv(input_file, sep="\t")

df_out = pd.DataFrame()
df_out["individual"] = df["individual"]

# delta calculations
#df_out["adapter_removed"] = df["raw_reads"] - df["after_adapter_removed"]
#df_out["quality_filtered"] = df["after_adapter_removed"] - df["after_quality_filter"]
df_out["non_endogenous"] = df["mapped_input_reads"] - df["mapped_endogenous_reads"]
df_out["duplicates"] = df["mapped_endogenous_reads"] - df["endogenous_duplicates_removed"]
df_out["endogenous"] = df["endogenous_duplicates_removed"]

#sort the columns: endogenous, duplicates, non_endogenous
columns_order = ["individual", "endogenous", "duplicates", "non_endogenous"]
df_out = df_out[columns_order]

df_out.to_csv(output_file, sep="\t", index=False)

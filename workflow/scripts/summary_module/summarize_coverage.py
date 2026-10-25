import pandas as pd

# Snakemake provides these automatically
input_file = snakemake.input[0]
output_file = snakemake.output[0]
individual = snakemake.params.individual
reference = snakemake.params.reference

# Read CSV
df = pd.read_csv(input_file)

# Calculate requested summary values
max_depth = df["max_depth"].max()
total_covered_bases = df["covered_bases"].sum()
total_total_bases = df["total_bases"].sum()
# Weight by scaffold length, so many small unplaced scaffolds do not drag the genome-wide depth down
total_avg_depth = (df["avg_depth"] * df["total_bases"]).sum() / total_total_bases if total_total_bases > 0 else 0
total_percent_covered = total_covered_bases / total_total_bases * 100 if total_total_bases > 0 else 0

# Prepare header and row
header = [
    "individual",
    "avgerage_depth",
    "max_depth",
    "total_covered_bases",
    "total_bases",
    "percent_covered"
]

row = [
    f"{individual}_{reference}",
    total_avg_depth,
    max_depth,
    total_covered_bases,
    total_total_bases,
    total_percent_covered
]

# Write output
with open(output_file, "w") as f:
    f.write("\t".join(header) + "\n")
    f.write("\t".join(map(str, row)) + "\n")

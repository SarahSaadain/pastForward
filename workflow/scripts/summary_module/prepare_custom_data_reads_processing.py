import json
import pandas as pd

# Snakemake variables
reads_file = snakemake.input.reads
endogenous_file = snakemake.input.get("endogenous", [])
dedup_file = snakemake.input.get("dedup", [])

individual = snakemake.params.individual
reference = snakemake.params.reference
output_file = snakemake.output[0]

# ------------------------
# Load reads CSV
# ------------------------
reads_df = pd.read_csv(reads_file)
reads_df = reads_df[reads_df["individual"] == individual]

reads_summary = reads_df[
    [
        "raw_count",
        "adapter_removed_count",
        "quality_filtered_count"
    ]
].sum().to_dict()

# ------------------------
# Default dedup structure (safe fallback)
# ------------------------
dedup_data = {
    "mapped_reads": 0,
    "total_removed": 0
}
# Denominator for every endogenous %. Without an endogenous CSV, fall back to
# the quality-filtered count, which is what went into mapping.
mapped_input_reads = reads_summary.get("quality_filtered_count", 0)

# ------------------------
# If mapping stats provided → set endogenous
# ------------------------
if endogenous_file:
    mapping_df = pd.read_csv(endogenous_file, sep=",")
    mapped_reads = int(mapping_df["mapped_reads"].iloc[0])
    dedup_data["mapped_reads"] = mapped_reads
    mapped_input_reads = int(mapping_df["total_reads"].iloc[0])

# ------------------------
# If dedup provided → take the removed duplicates from it
# ------------------------
# The mapped count stays from the endogenous CSV: DeDup's mapped_reads also
# counts secondary and supplementary alignments, so it can exceed the total.
if dedup_file:
    with open(dedup_file) as f:
        real_dedup = json.load(f)["metrics"]

    dedup_data["total_removed"] = real_dedup.get("total_removed", 0)

# ------------------------
# Build final table (UNCHANGED STRUCTURE)
# ------------------------
summary = {
    "individual": f"{individual}_{reference}",
    "raw_reads": reads_summary.get("raw_count", 0),
    "after_adapter_removed": reads_summary.get("adapter_removed_count", 0),
    "after_quality_filter": reads_summary.get("quality_filtered_count", 0),
    "mapped_input_reads": mapped_input_reads,
    "mapped_endogenous_reads": dedup_data["mapped_reads"],
    "endogenous_duplicates_removed": dedup_data["mapped_reads"] - dedup_data["total_removed"]
}

# ------------------------
# Write TSV
# ------------------------
pd.DataFrame([summary]).to_csv(output_file, sep="\t", index=False)

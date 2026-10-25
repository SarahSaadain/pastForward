import json
import os
import sys

def determine_endogenous_reads_from_stats(stats_file, output_file, individual_id, dedup_file=None):
    """
    Parse samtools stats file and compute mapped/unmapped proportion.

    Endogenous = mapped reads before deduplication, out of all filtered reads
    that went into mapping. The stats file is taken from the deduplicated BAM
    when deduplication runs, so the DeDup JSON then supplies the mapped count
    and the removed duplicates are added back to the total.

    Args:
        stats_file (str): Path to the samtools stats file.
        output_file (str): Path to the output CSV file.
        individual_id (str): The ID of the individual (from Snakemake wildcards).
        dedup_file (str, optional): Merged DeDup JSON, given when deduplication is enabled.
    """
    total_reads = 0
    mapped_reads = 0

    # 1. Parse the samtools stats file
    try:
        with open(stats_file) as f:
            for line in f:
                if line.startswith("SN"):
                    parts = line.strip().split("\t")
                    if len(parts) < 3:
                        continue # Skip malformed lines

                    # Find total reads
                    if parts[1].startswith("raw total sequences:"):
                        # Convert to int, handling potential non-numeric data gracefully
                        try:
                            total_reads = int(parts[2])
                        except ValueError:
                            print(f"Warning: Could not parse total reads value '{parts[2]}' in {stats_file}", file=sys.stderr)
                            total_reads = 0
                    
                    # Find mapped reads
                    elif parts[1].startswith("reads mapped:"):
                        try:
                            mapped_reads = int(parts[2])
                        except ValueError:
                            print(f"Warning: Could not parse mapped reads value '{parts[2]}' in {stats_file}", file=sys.stderr)
                            mapped_reads = 0
    except FileNotFoundError:
        print(f"Error: Stats file not found at {stats_file}", file=sys.stderr)
        # Set reads to 0 if file is missing to allow workflow to continue
        total_reads = 0
        mapped_reads = 0

    if dedup_file:
        with open(dedup_file) as f:
            dedup_metrics = json.load(f)["metrics"]
        mapped_reads = int(dedup_metrics["mapped_reads"])
        total_reads += int(dedup_metrics["total_removed"])

    # 2. Calculate proportion
    proportion = mapped_reads / total_reads * 100 if total_reads > 0 else 0.0

    # 3. Write output CSV
    with open(output_file, "w") as out:
        # Added 'Individual' to the header
        out.write("filename,individual,mapped_reads,total_reads,proportion\n")
        out.write(
            f"{os.path.basename(stats_file)},"
            f"{individual_id},"
            f"{mapped_reads},"
            f"{total_reads},"
            f"{proportion:.4f}\n"
        )


if __name__ == "__main__":
    # Assuming 'individual' is the wildcard name used in your Snakemake rule
    # If your wildcard is named 'sample', use snakemake.wildcards.sample instead.
    individual_id = snakemake.wildcards.individual 
    
    determine_endogenous_reads_from_stats(
        snakemake.input.stats,
        snakemake.output.csv,
        individual_id,
        snakemake.input.get("dedup") or None,
    )
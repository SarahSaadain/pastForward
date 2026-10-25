import os
import collections
import pandas as pd

def analyze_coverage_file(coverage_file, analysis_file_path):
    """
    Perform extended coverage analysis on a samtools depth file and save to CSV.
    """

    coverage_file_base_name = os.path.basename(coverage_file)

    print(f"Performing extended analysis for {coverage_file_base_name}")

    summary_data = collections.defaultdict(lambda: {
        "depth_sum": 0,
        "max_depth": 0,
        "covered_bases": 0,
        "total_bases": 0
    })

    lines_processed = 0
    chunk_size = 10**6

    try:
        for chunk in pd.read_csv(coverage_file, sep="\t", header=None,
                                 names=["scaffold", "position", "depth"],
                                 # Scaffold names stay text: no per-chunk number guessing, and "NA" is a name, not missing
                                 dtype={"scaffold": str}, keep_default_na=False,
                                 chunksize=chunk_size):

            grouped = chunk.groupby("scaffold")
            for scaffold, group in grouped:
                summary_data[scaffold]["depth_sum"] += group["depth"].sum()
                summary_data[scaffold]["max_depth"] = max(
                    summary_data[scaffold]["max_depth"],
                    group["depth"].max()
                )
                summary_data[scaffold]["covered_bases"] += (group["depth"] > 0).sum()
                summary_data[scaffold]["total_bases"] += len(group)

            lines_processed += len(chunk)
            # No total line count: counting means a second full read of a file with one line per reference base
            if lines_processed % (100 * chunk_size) == 0:
                print(f"Progress for {coverage_file_base_name}: {lines_processed:,} positions processed")

    except Exception as e:
        raise Exception(f"Failed during processing of {coverage_file}: {e}")

    summary = pd.DataFrame.from_dict(summary_data, orient="index")
    summary.index.name = "scaffold"
    summary["avg_depth"] = summary["depth_sum"] / summary["total_bases"]
    summary["percent_covered"] = (summary["covered_bases"] / summary["total_bases"]) * 100
    summary = summary[["avg_depth", "max_depth", "covered_bases", "total_bases", "percent_covered"]]

    print(f"Saving summary to {analysis_file_path} ...")
    summary.to_csv(analysis_file_path)

if __name__ == "__main__":
    analyze_coverage_file(snakemake.input.depth_txt, snakemake.output.analysis)

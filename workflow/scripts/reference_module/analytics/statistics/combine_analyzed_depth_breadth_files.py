import pandas as pd
import os

def combine_analysis_files(individual_analysis_files, combined_file_path, combined_detailed_file_path):
    """
    Combine multiple extended coverage analysis files into aggregated summary and detailed CSVs.
    """

    print(f"Combining {len(individual_analysis_files)} analysis files")

    if not individual_analysis_files:
        raise Exception("No individual analysis files provided")

    combined_data = []
    detailed_rows = []

    for analysis_file in individual_analysis_files:
        try:
            # Scaffold names stay text: "4" stays "4" and "NA" is a name, not missing
            df_analysis = pd.read_csv(analysis_file, dtype={"scaffold": str}, keep_default_na=False)

            if df_analysis.empty:
                print(f"Analysis file {analysis_file} is empty.")
                continue

            # Parse BAM filename from analysis filename
            original_bam_base = os.path.basename(analysis_file).replace(
                "_coverage_analysis.csv", ""
            )
            original_bam_filename = original_bam_base + "_final.bam"

            # --- Aggregated stats ---
            total_bases_sum = df_analysis['total_bases'].sum()
            overall_avg_depth = (
                (df_analysis['avg_depth'] * df_analysis['total_bases']).sum() / total_bases_sum
                if total_bases_sum > 0 else 0
            )
            overall_max_depth = df_analysis['max_depth'].max()
            overall_covered_bases = df_analysis['covered_bases'].sum()
            overall_total_bases = total_bases_sum
            overall_percent_covered = (
                (overall_covered_bases / overall_total_bases) * 100
                if overall_total_bases > 0 else 0
            )

            combined_data.append({
                "Filename": original_bam_filename,
                "OverallAvgDepth": overall_avg_depth,
                "OverallMaxDepth": overall_max_depth,
                "OverallCoveredBases": overall_covered_bases,
                "OverallTotalBases": overall_total_bases,
                "OverallPercentCovered": overall_percent_covered
            })

            # --- Append raw rows, tagged with filename ---
            df_analysis['Filename'] = original_bam_filename
            detailed_rows.append(df_analysis)

        except Exception as e:
            raise Exception(f"Error processing {analysis_file}: {e}")

    # --- Save aggregated summary ---
    if combined_data:
        df_combined = pd.DataFrame(combined_data)
        df_combined.to_csv(combined_file_path, index=False)
        print(f"Combined coverage summary written to: {combined_file_path}")
    else:
        print("No valid aggregated data to write.")

    # --- Save detailed per-scaffold data ---
    if detailed_rows:
        df_detailed = pd.concat(detailed_rows, ignore_index=True)
        df_detailed.to_csv(combined_detailed_file_path, index=False)
        print(f"Detailed coverage file written to: {combined_detailed_file_path}")
    else:
        print("No detailed data to write.")


if __name__ == "__main__":
    combine_analysis_files(
        snakemake.input,
        snakemake.output.combined,
        snakemake.output.detailed,
    )

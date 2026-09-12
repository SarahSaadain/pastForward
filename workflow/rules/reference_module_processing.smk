# =================================================================================================
#     Reads to Reference Processing Workflow
# =================================================================================================
# This file coordinates the steps for mapping aDNA reads to a reference and downstream analyses.
# Each include statement brings in rules for a specific processing or analysis step.


# Prepare the reference for mapping (indexing, etc.)
include: "reference_module/processing/prepare_reference_for_mapping.smk"
# Map ancient DNA reads to the reference
include: "reference_module/processing/map_reads_to_reference.smk"
# Deduplicate mapped reads
include: "reference_module/processing/deduplication.smk"
# Analyze DNA damage patterns and rescale BAM files
include: "reference_module/processing/analyze_damage_and_rescale_bam.smk"
# Get the final BAM file
include: "reference_module/processing/get_final_bam.smk"
# Optionally remove or extract unmapped reads after QC statistics are captured
include: "reference_module/processing/filter_unmapped_reads.smk"
# Determine coverage depth and breadth statistics
include: "reference_module/analytics/determine_coverage_depth_breadth.smk"
# Calculate additional mapping statistics using samtools
include: "reference_module/analytics/analyze_bam_with_samtools_stats.smk"
# Calculate additional mapping statistics using Qualimap
include: "reference_module/analytics/analyze_bam_with_qualimap.smk"
# Calculate additional mapping statistics using preseq
include: "reference_module/analytics/analyze_bam_with_preseq_lc_extrap.smk"
# Flag individuals whose divergence from the reference is a cohort outlier
include: "reference_module/analytics/analyze_snp_divergence.smk"
# Prepare custom content for MultiQC reports
include: "reference_module/analytics/create_multiqc_prepare_custom_data_breadth.smk"
include: "reference_module/analytics/create_multiqc_prepare_custom_data_depth.smk"
include: "reference_module/analytics/create_multiqc_prepare_custom_data_reads_processing.smk"
include: "reference_module/analytics/create_multiqc_prepare_custom_folder_links.smk"
# create_multiqc_bam.smk
include: "reference_module/analytics/create_multiqc_bam.smk"
# create_multiqc_reference.smk
include: "reference_module/analytics/create_multiqc_reference.smk"
# Calculate endogenous reads
include: "reference_module/analytics/determine_endogenous_reads.smk"
# Plot endogenous reads statistics
include: "reference_module/plotting/plot_endogenous_reads.smk"
# Plot coverage breadth across the reference
include: "reference_module/plotting/plot_coverage_breadth.smk"
# Plot coverage depth across the reference
include: "reference_module/plotting/plot_coverage_depth.smk"
# Plot raw and endogenous reads
include: "reference_module/plotting/plot_raw_and_endogenous_reads.smk"
# Plot per-individual SNP divergence from the reference
include: "reference_module/plotting/plot_snp_divergence.smk"


# =================================================================================================
# End of reference_module_processing.smk
# =================================================================================================

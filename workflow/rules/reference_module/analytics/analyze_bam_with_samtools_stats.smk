####################################################
# Snakemake rules
####################################################


# Rule: Generate samtools stats for BAM files
rule analyze_bam_with_samtools_stats:
    input:
        # Use the pre-filter BAM so that unmapped-read statistics are always
        # captured, even when filter_unmapped_reads is enabled with action="remove".
        bam=_pre_filter_bam,
    output:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats",
    log:
        "{species}/processed/reference_module/{reference}/statistics/{individual}/{individual}_{reference}_final.bam.stats.log",
    message:
        "Generating samtools stats for {input.bam}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/stats"

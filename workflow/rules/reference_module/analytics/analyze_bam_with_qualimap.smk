rule analyze_bam_with_qualimap:
    input:
        # Use the pre-filter BAM so that unmapped-read statistics are always
        # captured, even when filter_unmapped_reads is enabled with action="remove".
        bam=_pre_filter_bam,
    output:
        directory(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/qualimap"
        ),
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/qualimap/qualimapReport.html",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/{individual}_qualimap.log",
    # optional specification of memory usage of the JVM that snakemake will respect with global
    # resource restrictions (https://snakemake.readthedocs.io/en/latest/snakefiles/rules.html#resources)
    # and which can be used to request RAM during cluster job submission as `{resources.mem_mb}`:
    # https://snakemake.readthedocs.io/en/latest/executing/cluster.html#job-properties
    resources:
        mem_mb=config.get("pipeline", {})
        .get("reference_module", {})
        .get("analysis", {})
        .get("settings", {})
        .get("qualimap_mem_mb", 4096),
    wrapper:
        f"{WRAPPER_VERSION}/bio/qualimap/bamqc"

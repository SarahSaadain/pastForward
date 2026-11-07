####################################################
# Snakemake rules
####################################################


# Rule: Per-scaffold depth and breadth, streamed from samtools depth (no per-base file on disk)
rule analyze_mapped_reads_coverage:
    input:
        bam="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam",
    output:
        analysis="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/coverage/{individual}_{reference}_coverage_analysis.csv",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/coverage/{individual}_{reference}_coverage_analysis.log",
    conda:
        "../../../envs/coverage.yaml"
    message:
        "Analyzing coverage depth and breadth for {input.bam}"
    script:
        "../../../scripts/reference_module/analytics/statistics/analyze_coverage_from_bam.py"


# Rule: Combine coverage analysis files
rule combine_analyzed_mapped_reads_coverage:
    input:
        analysis=lambda wildcards: expand(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/coverage/{individual}_{reference}_coverage_analysis.csv",
            species=wildcards.species,
            reference=wildcards.reference,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        combined="{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis.csv",
        detailed="{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis_detailed.csv",
    log:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
    message:
        "Combining coverage analysis files for species {params.species}"
    script:
        "../../../scripts/reference_module/analytics/statistics/combine_analyzed_depth_breadth_files.py"

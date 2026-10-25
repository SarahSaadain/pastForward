####################################################
# Snakemake rules
####################################################


# Rule: Determine endogenous reads from BAM stats
rule determine_mapped_reads_endogenous:
    input:
        stats="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats",
        # Endogenous counts mapped reads before deduplication, so take them from DeDup when it runs.
        dedup=(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/dedup/{individual}_{reference}_final.dedup.json"
            if _dedup_enabled()
            else []
        ),
    output:
        csv="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/endogenous/{individual}_{reference}.endogenous.csv",
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/endogenous/{individual}_{reference}_endogenous.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Determining endogenous reads for {input.stats}"
    script:
        "../../../scripts/reference_module/analytics/statistics/parse_endogenous_from_stats.py"


# Rule: Combine endogenous reads for all individuals
rule combine_determine_mapped_reads_endogenous:
    input:
        lambda wildcards: expand(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/endogenous/{individual}_{reference}.endogenous.csv",
            species=wildcards.species,
            reference=wildcards.reference,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/endogenous/{reference}_endogenous.csv",
    log:
        "{species}/processed/reference_module/{reference}/analytics/{species}/endogenous/{reference}_endogenous.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Combining endogenous reads for species {wildcards.species}"
    script:
        "../../../scripts/reference_module/analytics/statistics/combine_endogenous_reads.py"

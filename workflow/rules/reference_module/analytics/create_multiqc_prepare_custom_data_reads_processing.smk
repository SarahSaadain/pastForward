####################################################
# Snakemake rules
####################################################


rule prepare_custom_data_reads_processing_absolute_values:
    input:
        reads="{species}/results/read_module/statistics/{species}_reads_counts.csv",
        endogenous=lambda wildcards: (
            f"{wildcards.species}/results/reference_module/{wildcards.reference}/analytics/individual_level/{wildcards.individual}/endogenous/{wildcards.individual}_{wildcards.reference}.endogenous.csv"
            if config.get("pipeline", {})
            .get("reference_module", {})
            .get("execute", True)
            == True
            else []
        ),
        dedup=lambda wildcards: (
            []
            if config.get("pipeline", {})
            .get("reference_module", {})
            .get("execute", True)
            == False
            else (
                f"{wildcards.species}/results/reference_module/{wildcards.reference}/analytics/individual_level/{wildcards.individual}/dedup/{wildcards.individual}_{wildcards.reference}_final.dedup.json"
                if _dedup_enabled()
                else []
            )
        ),
    output:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        individual="{individual}",
        reference="{reference}",
    script:
        "../../../scripts/summary_module/prepare_custom_data_reads_processing.py"


rule combine_custom_data_reads_processing_absolute_values:
    input:
        lambda wildcards: expand(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv",
            species=wildcards.species,
            reference=wildcards.reference,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        "{species}/results/summary/species_level/{species}_overall/multiqc_custom_content/{species}_{reference}_reads_processing_summary_combined.tsv",
    log:
        "{species}/results/summary/species_level/{species}_overall/multiqc_custom_content/{species}_{reference}_reads_processing_summary_combined.log",
    conda:
        "../../../envs/python_and_r.yaml"
    script:
        "../../../scripts/reference_module/analytics/combine_custom_data_reads_processing_absolute_values.py"


rule prepare_custom_data_reads_processing_stacked_values:
    input:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv",
    output:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.tsv",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.log",
    conda:
        "../../../envs/python_and_r.yaml"
    script:
        "../../../scripts/reference_module/analytics/prepare_custom_data_reads_processing_stacked_values.py"


rule combine_custom_data_reads_processing_stacked_values:
    input:
        lambda wildcards: expand(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.tsv",
            species=wildcards.species,
            reference=wildcards.reference,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        "{species}/results/summary/species_level/{species}_overall/multiqc_custom_content/{species}_{reference}_reads_processing_summary_stacked_combined.tsv",
    log:
        "{species}/results/summary/species_level/{species}_overall/multiqc_custom_content/{species}_{reference}_reads_processing_summary_stacked_combined.log",
    conda:
        "../../../envs/python_and_r.yaml"
    script:
        "../../../scripts/reference_module/analytics/combine_custom_data_reads_processing_stacked_values.py"

import textwrap


####################################################
# Snakemake rules
####################################################
rule create_multiqc_species:
    input:
        create_multiqc_species_input,
        config="{species}/results/summary/species_level/{species}_overall/{species}_species_overall_multiqc_config.yaml",
    output:
        "{species}/results/summary/species_level/{species}_multiqc.overall.html",
        directory(
            "{species}/results/summary/species_level/{species}_overall/species_multiqc_data"
        ),
    log:
        "{species}/results/summary/species_level/{species}_overall/multiqc.log",
    params:
        extra="--verbose",  # Optional: extra parameters for multiqc.
        use_input_files_only=True,
    wrapper:
        f"{WRAPPER_VERSION}/bio/multiqc"


rule create_multiqc_species_config:
    output:
        "{species}/results/summary/species_level/{species}_overall/{species}_species_overall_multiqc_config.yaml",
    log:
        "{species}/results/summary/species_level/{species}_overall/{species}_species_overall_multiqc_config.log",
    conda:
        "../../envs/python_and_r.yaml"
    script:
        "../../scripts/summary_module/create_multiqc_species_individual_script_create_multiqc_species_individual_config.py"

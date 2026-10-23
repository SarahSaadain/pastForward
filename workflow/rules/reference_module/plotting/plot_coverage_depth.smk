####################################################
# Snakemake rules
####################################################


# Rule: Plot depth coverage violin by individual
rule plot_mapped_reads_depth_coverage_violin:
    input:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis_detailed.csv",
    output:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_depth_coverage_violin.png",
    log:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_depth_coverage_violin.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
    message:
        "Plotting depth coverage violin for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/plotting/plot_coverage_depth_by_individuals_violin.R"


# Rule: Plot depth coverage bar by individual
rule plot_mapped_reads_depth_coverage_bar:
    input:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis_detailed.csv",
    output:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_depth_coverage_bar.png",
    log:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_depth_coverage_bar.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
    message:
        "Plotting depth coverage bar for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/plotting/plot_coverage_depth_by_individuals_bar.R"

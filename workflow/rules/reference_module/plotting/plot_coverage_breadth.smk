####################################################
# Snakemake rules
####################################################


# Rule: Plot coverage breadth violin by individual
rule plot_mapped_reads_coverage_breadth_violin:
    input:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis_detailed.csv",
    output:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_coverage_breadth_violin.png",
    log:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_coverage_breadth_violin.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
    message:
        "Plotting coverage breadth violin for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/plotting/plot_coverage_breadth_by_individuals_violin.R"


# Rule: Plot coverage breadth bar by individual
rule plot_mapped_reads_coverage_breadth_bar:
    input:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/coverage/{reference}_combined_coverage_analysis_detailed.csv",
    output:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_coverage_breadth_bar.png",
    log:
        "{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_coverage_breadth_bar.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
    message:
        "Plotting coverage breadth bar for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/plotting/plot_coverage_breadth_by_individuals_bar.R"

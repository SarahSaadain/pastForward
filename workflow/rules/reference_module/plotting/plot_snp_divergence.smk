####################################################
# Snakemake rules
####################################################


# Rule: Plot per-individual SNP divergence with the cohort outlier threshold
rule plot_snp_divergence_bar:
    input:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/snp_divergence/{reference}_combined_snp_divergence.csv",
    output:
        "{species}/results/reference_module/{reference}/plots/snp_divergence/{species}_{reference}_snp_divergence_bar.png",
    log:
        "{species}/results/reference_module/{reference}/plots/snp_divergence/{species}_{reference}_snp_divergence_bar.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
    message:
        "Plotting SNP divergence for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/plotting/plot_snp_divergence_bar.R"

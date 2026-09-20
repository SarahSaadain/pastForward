####################################################
# Snakemake rules
####################################################


# Rule: Plot per-individual SNP divergence with the cohort outlier threshold
#
# One plot per method, so a plot from an earlier method is never mistaken for the
# current one and both can be shown side by side when the method is "both".
rule plot_snp_divergence_bar:
    input:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/snp_divergence/{reference}_combined_snp_divergence_{method}.csv",
    output:
        "{species}/results/reference_module/{reference}/plots/snp_divergence/{species}_{reference}_snp_divergence_{method}_bar.png",
    log:
        "{species}/results/reference_module/{reference}/plots/snp_divergence/{species}_{reference}_snp_divergence_{method}_bar.log",
    # Species and reference names may contain underscores, so the method has to be
    # pinned down for Snakemake to split the filename correctly.
    wildcard_constraints:
        method="samtools_stats|bcftools",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        species=lambda wildcards: wildcards.species,
        method=lambda wildcards: wildcards.method,
    message:
        "Plotting {wildcards.method} SNP divergence for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/plotting/plot_snp_divergence_bar.R"

####################################################
# Snakemake rules
####################################################


# Rule: Plot read count comparison for species
rule plot_read_counts:
    input:
        "{species}/results/read_module/statistics/{species}_reads_counts.csv",
    output:
        "{species}/results/read_module/plots/{species}_read_counts.png",
    log:
        "{species}/results/read_module/plots/{species}_read_counts.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Plotting read counts comparison for species {wildcards.species}"
    script:
        "../../../scripts/read_module/plotting/plot_read_counts.R"


# Rule: Plot read count comparison by individual
rule plot_read_counts_comparison_by_individual:
    input:
        "{species}/results/read_module/statistics/{species}_reads_counts.csv",
    output:
        "{species}/results/read_module/plots/{species}_read_counts_comparison_by_individual.png",
    log:
        "{species}/results/read_module/plots/{species}_read_counts_comparison_by_individual.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Plotting read counts comparison per individual for species {wildcards.species}"
    script:
        "../../../scripts/read_module/plotting/plot_read_counts_comparison_by_individual.R"

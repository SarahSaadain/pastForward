import pandas as pd

####################################################
# Snakemake rules
####################################################


# Rule: Count reads in raw FASTQ files
rule count_reads_raw:
    input:
        fastq=lambda wc: get_raw_reads_for_sample(wc.species, wc.sample),
    output:
        counted="{species}/processed/read_module/statistics/{sample}_raw.count",
    log:
        "{species}/processed/read_module/statistics/{sample}_raw.log",
    conda:
        "../../../../envs/python_isal.yaml"
    message:
        "Counting reads in raw FASTQ file(s) {input.fastq}"
    script:
        "../../../../scripts/read_module/analytics/statistics/count_reads.py"


# Rule: Count reads in trimmed FASTQ files
# If adapter removal is inactive, copy count from raw reads instead
rule count_reads_trimmed:
    input:
        source=lambda wc: (
            f"{wc.species}/processed/read_module/reads_trimmed/{wc.sample}_trimmed_final.fastq.gz"
            if config.get("pipeline", {})
            .get("read_module", {})
            .get("adapter_removal", {})
            .get("execute", True)
            else f"{wc.species}/processed/read_module/statistics/{wc.sample}_raw.count"
        ),
    output:
        counted="{species}/processed/read_module/statistics/{sample}_trimmed.count",
    log:
        "{species}/processed/read_module/statistics/{sample}_trimmed.log",
    conda:
        "../../../../envs/python_isal.yaml"
    message:
        "Counting reads in {input.source}"
    script:
        "../../../../scripts/read_module/analytics/statistics/count_reads.py"


# Rule: Count reads in quality-filtered FASTQ files
# If quality filtering is inactive, copy count from trimmed reads instead
rule count_reads_quality_filtered:
    input:
        source=lambda wc: (
            f"{wc.species}/processed/read_module/reads_quality_filtered/{wc.sample}_quality_filtered_final.fastq.gz"
            if config.get("pipeline", {})
            .get("read_module", {})
            .get("quality_filtering", {})
            .get("execute", True)
            else f"{wc.species}/processed/read_module/statistics/{wc.sample}_trimmed.count"
        ),
    output:
        counted="{species}/processed/read_module/statistics/{sample}_quality_filtered.count",
    log:
        "{species}/processed/read_module/statistics/{sample}_quality_filtered.log",
    conda:
        "../../../../envs/python_isal.yaml"
    message:
        "Counting reads in {input.source}"
    script:
        "../../../../scripts/read_module/analytics/statistics/count_reads.py"


# Rule: Combine read counts per sample
rule combine_counts_per_sample:
    input:
        raw_reads="{species}/processed/read_module/statistics/{sample}_raw.count",
        trimmed_reads="{species}/processed/read_module/statistics/{sample}_trimmed.count",
        quality_filtered_reads="{species}/processed/read_module/statistics/{sample}_quality_filtered.count",
    output:
        counts="{species}/processed/read_module/statistics/{sample}_reads_counts.csv",
    log:
        "{species}/processed/read_module/statistics/{sample}_reads_counts.log",
    conda:
        "../../../../envs/python_and_r.yaml"
    message:
        "Combining read counts for sample {wildcards.sample}"
    script:
        "../../../../scripts/read_module/analytics/statistics/combine_counts_per_sample.py"


# Rule: Combine read counts per species
rule combine_counts_per_species:
    input:
        lambda wildcards: expand(
            "{species}/processed/read_module/statistics/{sample}_reads_counts.csv",
            sample=get_sample_ids_for_species(wildcards.species),
            species=wildcards.species,
        ),
    output:
        counts="{species}/results/read_module/statistics/{species}_reads_counts.csv",
    log:
        "{species}/results/read_module/statistics/{species}_reads_counts.log",
    conda:
        "../../../../envs/python_and_r.yaml"
    run:
        data = []
        pd.concat(
            [
                pd.read_csv(
                    f,
                    header=None,
                    names=[
                        "reads_file",
                        "individual",
                        "raw_count",
                        "adapter_removed_count",
                        "quality_filtered_count",
                    ],
                )
                for f in input
            ],
            ignore_index=True,
        ).to_csv(output.counts, index=False)

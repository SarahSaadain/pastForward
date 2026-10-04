####################################################
# Snakemake rules
####################################################


# Rule: Run MultiQC on raw FastQC outputs
rule run_multiqc_raw:
    input:
        lambda wildcards: get_expected_output_fastqc_raw(wildcards.species),
    output:
        "{species}/results/read_module/{species}_multiqc_raw.html",
    log:
        "{species}/processed/read_module/{species}_multiqc_raw.log",
    params:
        extra="--verbose",  # Optional: extra parameters for multiqc.
    message:
        "Running MultiQC on raw FastQC outputs for species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/multiqc"


# Rule: Run MultiQC on trimmed FastQC outputs
rule run_multiqc_trimmed:
    input:
        lambda wildcards: get_expected_output_fastqc_trimmed(wildcards.species),
    output:
        "{species}/results/read_module/{species}_multiqc_trimmed.html",
    log:
        "{species}/processed/read_module/{species}_multiqc_trimmed.log",
    params:
        extra="--verbose",  # Optional: extra parameters for multiqc.
    message:
        "Running MultiQC on trimmed FastQC outputs for species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/multiqc"


# Rule: Run MultiQC on quality-filtered FastQC outputs
rule run_multiqc_quality_filtered:
    input:
        lambda wildcards: get_expected_output_fastqc_quality_filtered(wildcards.species),
    output:
        "{species}/results/read_module/{species}_multiqc_quality_filtered.html",
    log:
        "{species}/processed/read_module/{species}_multiqc_quality_filtered.log",
    params:
        extra="--verbose",  # Optional: extra parameters for multiqc.
    message:
        "Running MultiQC on quality-filtered FastQC outputs for species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/multiqc"


# Rule: Run MultiQC on merged FastQC outputs
rule run_multiqc_merged:
    input:
        lambda wildcards: get_expected_output_fastqc_merged(wildcards.species),
    output:
        "{species}/results/read_module/{species}_multiqc_merged.html",
    log:
        "{species}/processed/read_module/{species}_multiqc_merged.log",
    params:
        extra="--verbose",  # Optional: extra parameters for multiqc.
    message:
        "Running MultiQC on merged FastQC outputs for species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/multiqc"

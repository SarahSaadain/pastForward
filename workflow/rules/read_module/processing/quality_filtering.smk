####################################################
# Snakemake rules
####################################################


# Rule: Quality filtering of reads using fastp
rule filter_reads_by_quality:
    input:
        sample=[
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed_final.fastq.gz"
        ],
    output:
        trimmed=temp(
            "{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered.fastq.gz"
        ),
        failed=temp(
            "{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered.failed.fastq.gz"
        ),
        html="{species}/results/read_module/reads_quality_filtered/fastp_report/{sample}_quality_filtered.html",
        json="{species}/results/read_module/reads_quality_filtered/fastp_report/{sample}_quality_filtered.json",
    log:
        "{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered.log",
    threads: 10
    params:
        extra=(
            f"--disable_adapter_trimming "
            f"--qualified_quality_phred {config.get('pipeline',{}).get('read_module',{}).get('quality_filtering',{}).get('settings',{}).get('min_quality', '15')} "
            f"--length_required {config.get('pipeline',{}).get('read_module',{}).get('quality_filtering',{}).get('settings',{}).get('min_length', '15')} "
            f"--unqualified_percent_limit {config.get('pipeline',{}).get('read_module',{}).get('quality_filtering',{}).get('settings',{}).get('unqualified_percent_limit',40)} "
            f"--n_base_limit {config.get('pipeline',{}).get('read_module',{}).get('quality_filtering',{}).get('settings',{}).get('n_base_limit',5)}"
        ),
    message:
        "Quality filtering reads in {input.sample}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastp"


rule get_quality_filtered_final:
    input:
        # If quality filtering is enabled, use the quality filtered reads as input for the next steps in the pipeline.
        # If quality filtering is not enabled, use the trimmed reads as input for the next steps in the pipeline.
        source=lambda wildcards: (
            f"{wildcards.species}/processed/read_module/reads_quality_filtered/{wildcards.sample}_quality_filtered.fastq.gz"
            if config.get("pipeline", {})
            .get("read_module", {})
            .get("quality_filtering", {})
            .get("execute", True)
            else f"{wildcards.species}/processed/read_module/reads_trimmed/{wildcards.sample}_trimmed_final.fastq.gz"
        ),
    output:
        final=temp(
            "{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered_final.fastq.gz"
        ),
    log:
        "{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered_final.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Selecting quality filtered reads for {wildcards.sample}"
    shell:
        'cp "{input.source}" "{output.final}" > "{log}" 2>&1'

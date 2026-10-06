####################################################
# Snakemake rules
####################################################


# Rule: Run FastQC on raw reads
rule run_fastqc_raw:
    input:
        lambda wildcards: get_raw_read_path_for_stem(
            wildcards.species, wildcards.sample
        ),
    output:
        html="{species}/results/read_module/reads_raw/fastqc/{sample}_raw_fastqc.html",
        zip="{species}/results/read_module/reads_raw/fastqc/{sample}_raw_fastqc.zip",
    log:
        "{species}/processed/read_module/reads_raw/fastqc/{sample}_fastqc.log",
    threads: 1
    resources:
        mem_mb=1024,
    params:
        extra="--quiet",
        mem_overhead_factor=0.1,
    message:
        "Running FastQC on raw reads for sample {wildcards.sample} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastqc"


# Rule: Run FastQC on adapter-trimmed reads
rule run_fastqc_adapter_removed:
    input:
        "{species}/processed/read_module/reads_trimmed/{sample}_trimmed_final.fastq.gz",
    output:
        html="{species}/results/read_module/reads_trimmed/fastqc/{sample}_trimmed_fastqc.html",
        zip="{species}/results/read_module/reads_trimmed/fastqc/{sample}_trimmed_fastqc.zip",
    log:
        "{species}/processed/read_module/reads_trimmed/fastqc/{sample}_trimmed_fastqc.log",
    threads: 1
    resources:
        mem_mb=1024,
    params:
        extra="--quiet",
        mem_overhead_factor=0.1,
    message:
        "Running FastQC on adapter-trimmed reads for sample {wildcards.sample} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastqc"


# Rule: Run FastQC on quality-filtered reads
rule run_fastqc_quality_filtered:
    input:
        "{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered_final.fastq.gz",
    output:
        html="{species}/results/read_module/reads_quality_filtered/fastqc/{sample}_quality_filtered_fastqc.html",
        zip="{species}/results/read_module/reads_quality_filtered/fastqc/{sample}_quality_filtered_fastqc.zip",
    log:
        "{species}/processed/read_module/reads_quality_filtered/fastqc/{sample}_quality_filtered_fastqc.log",
    threads: 1
    resources:
        mem_mb=1024,
    params:
        extra="--quiet",
        mem_overhead_factor=0.1,
    message:
        "Running FastQC on quality-filtered reads for sample {wildcards.sample} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastqc"


# Rule: Run FastQC on merged reads
rule run_fastqc_merged:
    input:
        merged="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
    output:
        html="{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.html",
        zip="{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.zip",
    log:
        "{species}/processed/read_module/reads_merged/fastqc/{individual}_fastqc.log",
    threads: 1
    resources:
        mem_mb=1024,
    params:
        extra="--quiet",
        mem_overhead_factor=0.1,
    message:
        "Running FastQC on merged reads for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastqc"

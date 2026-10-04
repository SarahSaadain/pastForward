####################################################
# Snakemake rules
####################################################


# Rule: Adapter removal for single-end reads using fastp
rule remove_adapters_single_with_fastp:
    input:
        sample=lambda wc: get_raw_reads_for_sample(wc.species, wc.sample),  # Get the single read file for SE
    output:
        trimmed=temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.se.fastq.gz"
        ),
        failed=temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.se.failed.fastq.gz"
        ),
        html="{species}/results/read_module/reads_trimmed/fastp_report/{sample}_trimmed.se.html",
        json="{species}/results/read_module/reads_trimmed/fastp_report/{sample}_trimmed.se.json",
    log:
        "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.se.log",
    threads: 10
    params:
        adapters=lambda wc: (
            f"--adapter_sequence {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('adapters_sequences',{}).get('r1')}"
            if config.get("pipeline", {})
            .get("read_module", {})
            .get("adapter_removal", {})
            .get("settings", {})
            .get("adapters_sequences", {})
            .get("r1")
            else ""
        ),
        extra=lambda wc: (
            f"--length_required {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('min_length',0)} "
            f"--qualified_quality_phred {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('min_quality',0)} "
            f"--trim_poly_x "
            f"--poly_x_min_len {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('poly_x_min_len',5)} "
            f"--unqualified_percent_limit {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('unqualified_percent_limit',40)} "
            f"--n_base_limit {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('n_base_limit',5)} "
            f"{config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('extra_params', '')}"
        ),
    message:
        "Trimming adapters from single-end reads in {input.sample}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastp"


# Rule: Adapter removal for paired-end reads using fastp
rule remove_adapters_paired_with_fastp:
    input:
        sample=lambda wc: get_raw_reads_for_sample(wc.species, wc.sample),
    output:
        trimmed=[
            temp(
                "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.R1.fastq.gz"
            ),
            temp(
                "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.R2.fastq.gz"
            ),
        ],
        # Unpaired reads separately
        unpaired1=temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.unpaired.R1.fastq.gz"
        ),
        unpaired2=temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.unpaired.R2.fastq.gz"
        ),
        merged=temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.fastq.gz"
        ),
        failed=temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.failed.fastq.gz"
        ),
        html="{species}/results/read_module/reads_trimmed/fastp_report/{sample}_trimmed.pe.html",
        json="{species}/results/read_module/reads_trimmed/fastp_report/{sample}_trimmed.pe.json",
    log:
        "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.log",
    threads: 10
    params:
        adapters=lambda wc: (
            f"--adapter_sequence {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('adapters_sequences',{}).get('r1', '')} "
            f"--adapter_sequence_r2 {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('adapters_sequences',{}).get('r2', '')}"
            if config.get("pipeline", {})
            .get("read_module", {})
            .get("adapter_removal", {})
            .get("settings", {})
            .get("adapters_sequences")
            else "--detect_adapter_for_pe"
        ),
        extra=lambda wc: (
            f"--length_required {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('min_length',0)} "
            f"--trim_poly_x "
            f"--poly_x_min_len {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('poly_x_min_len',5)} "
            f"--qualified_quality_phred {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('min_quality',0)} "
            f"--unqualified_percent_limit {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('unqualified_percent_limit',40)} "
            f"--n_base_limit {config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('n_base_limit',5)} "
            f"--merge "
            f"{config.get('pipeline',{}).get('read_module',{}).get('adapter_removal',{}).get('settings',{}).get('extra_params', '')}"
        ),
    message:
        "Trimming adapters from paired-end reads and merging for {input.sample}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastp"


rule get_adapter_removal_final:
    input:
        determine_reads_trimmed_final_input,
    output:
        temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed_final.fastq.gz"
        ),
    log:
        "{species}/processed/read_module/reads_trimmed/{sample}_determine_trimmed_final.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Getting trimmed reads in {wildcards.sample}"
    shell:
        """
        echo "Determining final trimmed reads for {wildcards.sample}" >"{log}" 2>&1
        echo "Input: {input}" >>"{log}" 2>&1
        echo "Output: {output}" >>"{log}" 2>&1
        cat {input} >"{output}"
        echo "Determination completed for {wildcards.sample}" >>"{log}" 2>&1
        """


rule merge_reads_adapter_removal_pe:
    input:
        merged="{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.fastq.gz",
        trimmed1="{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.R1.fastq.gz",
        trimmed2="{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.R2.fastq.gz",
        unpaired1="{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.unpaired.R1.fastq.gz",
        unpaired2="{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.unpaired.R2.fastq.gz",
    output:
        temp(
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.merged.fastq.gz"
        ),
    log:
        "{species}/processed/read_module/reads_trimmed/{sample}_merge_trimmed_pe.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Merging trimmed reads for paired-end"
    shell:
        """
        echo "Merging trimmed paired-end reads for {wildcards.sample}" >"{log}" 2>&1
        echo "Input files:" >>"{log}" 2>&1
        echo "Merged: {input.merged}" >>"{log}" 2>&1
        echo "Trimmed R1: {input.trimmed1}" >>"{log}" 2>&1
        echo "Trimmed R2: {input.trimmed2}" >>"{log}" 2>&1
        echo "Unpaired R1: {input.unpaired1}" >>"{log}" 2>&1
        echo "Unpaired R2: {input.unpaired2}" >>"{log}" 2>&1
        echo "Output: {output}" >>"{log}" 2>&1
        cat "{input.merged}" "{input.trimmed1}" "{input.trimmed2}" "{input.unpaired1}" "{input.unpaired2}" >"{output}"
        echo "Merging completed for {wildcards.sample}" >>"{log}" 2>&1
        """

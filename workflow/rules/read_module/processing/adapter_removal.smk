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
        adapters=lambda wc: _fastp_adapter_flags(paired=False),
        extra=lambda wc: (
            f"--length_required {_setting('read_module', 'adapter_removal', 'settings', 'min_length', default=0)} "
            f"--qualified_quality_phred {_setting('read_module', 'adapter_removal', 'settings', 'min_quality', default=0)} "
            f"--trim_poly_x "
            f"--poly_x_min_len {_setting('read_module', 'adapter_removal', 'settings', 'poly_x_min_len', default=5)} "
            f"--unqualified_percent_limit {_setting('read_module', 'adapter_removal', 'settings', 'unqualified_percent_limit', default=40)} "
            f"--n_base_limit {_setting('read_module', 'adapter_removal', 'settings', 'n_base_limit', default=5)} "
            f"{_setting('read_module', 'adapter_removal', 'settings', 'extra_params', default= '')}"
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
        # If neither adapter is set, let fastp auto-detect.
        adapters=lambda wc: _fastp_adapter_flags(paired=True)
        or "--detect_adapter_for_pe",
        extra=lambda wc: (
            f"--length_required {_setting('read_module', 'adapter_removal', 'settings', 'min_length', default=0)} "
            f"--trim_poly_x "
            f"--poly_x_min_len {_setting('read_module', 'adapter_removal', 'settings', 'poly_x_min_len', default=5)} "
            f"--qualified_quality_phred {_setting('read_module', 'adapter_removal', 'settings', 'min_quality', default=0)} "
            f"--unqualified_percent_limit {_setting('read_module', 'adapter_removal', 'settings', 'unqualified_percent_limit', default=40)} "
            f"--n_base_limit {_setting('read_module', 'adapter_removal', 'settings', 'n_base_limit', default=5)} "
            f"--merge "
            f"{_merge_overlap_flag()}"
            f"{_setting('read_module', 'adapter_removal', 'settings', 'extra_params', default= '')}"
        ),
    message:
        "Trimming adapters from paired-end reads and merging for {input.sample}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/fastp"


# keep_reads: the trimmed reads stay in processed/ (no temp) so later steps never rebuild them,
# and keep_trimmed_reads below adds a copy in results/. Pointless without adapter removal, where
# the file is only a copy of the raw reads.
_KEEP_TRIMMED = _setting(
    "read_module", "adapter_removal", "settings", "keep_reads", default=False
) and _setting("read_module", "adapter_removal", "execute", default=True)


rule get_adapter_removal_final:
    input:
        determine_reads_trimmed_final_input,
    output:
        (
            "{species}/processed/read_module/reads_trimmed/{sample}_trimmed_final.fastq.gz"
            if _KEEP_TRIMMED
            else temp(
                "{species}/processed/read_module/reads_trimmed/{sample}_trimmed_final.fastq.gz"
            )
        ),
    log:
        "{species}/processed/read_module/reads_trimmed/{sample}_determine_trimmed_final.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        # Raw reads (adapter removal off) stay on disk, so they get a real copy.
        # A hard link would share their timestamp and could trigger reruns.
        hardlink=_setting("read_module", "adapter_removal", "execute", default=True),
    message:
        "Getting trimmed reads in {wildcards.sample}"
    shell:
        """
        echo "Determining final trimmed reads for {wildcards.sample}" >"{log}" 2>&1
        echo "Input: {input}" >>"{log}" 2>&1
        echo "Output: {output}" >>"{log}" 2>&1
        set -- {input}
        if [ $# -eq 1 ] && [ "{params.hardlink}" = True ]; then
            ln -fL "$1" "{output}" 2>/dev/null || cp "$1" "{output}"
        else
            cat "$@" >"{output}"
        fi
        echo "Determination completed for {wildcards.sample}" >>"{log}" 2>&1
        """


# A copy, not a hard link: the processed/ reads stay (see _hardlink_or_copy).
rule keep_trimmed_reads:
    input:
        "{species}/processed/read_module/reads_trimmed/{sample}_trimmed_final.fastq.gz",
    output:
        "{species}/results/read_module/reads_trimmed_final/{sample}_trimmed_final.fastq.gz",
    log:
        "{species}/processed/read_module/reads_trimmed/{sample}_keep_trimmed_reads.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Keeping trimmed reads of {wildcards.sample} in results"
    shell:
        f'({_hardlink_or_copy("{input}", "{output}", False)}) > "{{log}}" 2>&1'


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

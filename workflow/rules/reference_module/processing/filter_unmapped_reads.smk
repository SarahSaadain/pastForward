####################################################
# Snakemake rules for handling unmapped reads.
#
# These rules are inserted BETWEEN the last processing step
# (damage rescaling / deduplication / sorting) and get_final_bam,
# so the final BAM always reflects the chosen action.
#
# Statistics rules (samtools stats, qualimap) use get_pre_filter_bam_path
# (defined in get_final_bam.smk) so that unmapped-read metrics are
# always captured regardless of the chosen action.
#
# Config option (reference_module.filter_unmapped_reads):
#   execute: false          # set to true to enable
#   action: "remove"        # "remove" | "extract_fastq" | "extract_fasta"
#
# action = "remove"
#   Produces a mapped-reads-only BAM as a temp intermediate, which
#   get_final_bam then copies to {individual}_{reference}_final.bam.
#   The original pre-filter BAM is left on disk (it is the last
#   processing-step output and is not marked temp).
#
# action = "extract_fastq" / "extract_fasta"
#   Extracts unmapped reads directly from the pre-filter BAM into a
#   compressed FASTQ or FASTA file (samtools/fastx wrapper, -f 4 flag).
#   get_final_bam copies the unmodified pre-filter BAM to _final.bam.
####################################################


# ---------------------------------------------------------------------------
# action: "remove"
# Produce a mapped-reads-only BAM (flag -F 4 excludes unmapped reads).
# Marked temp because get_final_bam copies its content to _final.bam.
# ---------------------------------------------------------------------------
rule filter_mapped_only_bam:
    input:
        bam=_pre_filter_bam,
        bai=f"{_pre_filter_bam}.bai",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.log",
    threads: 4
    params:
        extra="-F 4",  # exclude unmapped reads
    message:
        "Filtering unmapped reads from BAM for {wildcards.individual} mapped to {wildcards.reference}."
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


rule index_mapped_only_bam:
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.bam",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.bam.bai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.bam.bai.log",
    threads: 4
    params:
        extra="",
    message:
        "Indexing mapped-only BAM for {wildcards.individual} mapped to {wildcards.reference}."
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"


# ---------------------------------------------------------------------------
# action: "extract_fastq"
# Extract unmapped reads (-f 4) from the pre-filter BAM directly to
# compressed FASTQ using samtools/fastx (outputtype="fastq").
# ---------------------------------------------------------------------------
rule convert_unmapped_reads_to_fastq:
    input:
        _pre_filter_bam,
    output:
        "{species}/results/reference_module/{reference}/unmapped/{individual}_{reference}_unmapped.fastq.gz",
    log:
        "{species}/results/reference_module/{reference}/unmapped/{individual}_{reference}_unmapped_fastq.log",
    threads: 4
    params:
        outputtype="fastq",
        extra="-f 4",
    message:
        "Extracting unmapped reads to FASTQ for {wildcards.individual} mapped to {wildcards.reference}."
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/fastx"


# ---------------------------------------------------------------------------
# action: "extract_fasta"
# Extract unmapped reads (-f 4) from the pre-filter BAM directly to
# compressed FASTA using samtools/fastx (outputtype="fasta").
# ---------------------------------------------------------------------------
rule convert_unmapped_reads_to_fasta:
    input:
        _pre_filter_bam,
    output:
        "{species}/results/reference_module/{reference}/unmapped/{individual}_{reference}_unmapped.fasta.gz",
    log:
        "{species}/results/reference_module/{reference}/unmapped/{individual}_{reference}_unmapped_fasta.log",
    threads: 4
    params:
        outputtype="fasta",
        extra="-f 4",
    message:
        "Extracting unmapped reads to FASTA for {wildcards.individual} mapped to {wildcards.reference}."
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/fastx"

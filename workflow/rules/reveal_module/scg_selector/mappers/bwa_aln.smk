####################################################
# REVEAL SCG-library mapper: bwa-aln
# Included by map_reads_to_scg_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_scg_sel_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################


rule index_scg_library_for_mapping_bwa_aln:
    input:
        "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
    output:
        temp(
            multiext(
                "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            )
        ),
    log:
        "{species}/processed/reveal_module/scg/{species}_scg_library_bwa_aln_index.log",
    message:
        "Indexing SCG library {input} with BWA (for BWA ALN)"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/index"


rule align_reads_to_scg_library_bwa_aln:
    input:
        fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
        idx=multiext(
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sai"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa_aln.log",
    threads: 10
    params:
        extra=_scg_sel_mapper_extra,
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/aln"


rule map_reads_to_scg_library_bwa_aln:
    input:
        fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
        sai="{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sai",
        idx=multiext(
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.unsorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa_samse.log",
    threads: 1
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/samse"


rule sort_scg_bam_reads:
    input:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.unsorted.with_unmapped.bam",
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_sort_bam.log",
    threads: 8
    message:
        "Sorting SCG BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/sort"

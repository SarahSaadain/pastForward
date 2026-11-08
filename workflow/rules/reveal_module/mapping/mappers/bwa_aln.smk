####################################################
# REVEAL feature-library mapper: bwa-aln
# Included by map_reads_to_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_dyn_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################


rule index_library_for_mapping_bwa_aln:
    input:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
    output:
        temp(
            multiext(
                "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            )
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_bwa_aln_index.log",
    message:
        "Indexing SCG and Feature library {input} with BWA (for BWA ALN)"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/index"


rule align_reads_to_library_bwa_aln:
    input:
        fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
        idx=multiext(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sai"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bwa_aln.log",
    threads: 10
    params:
        extra=_dyn_mapper_extra,
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/aln"


rule map_reads_to_scg_feature_library_bwa_aln:
    input:
        fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
        sai="{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sai",
        idx=multiext(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.unsorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bwa_samse.log",
    threads: 1
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/samse"


rule sort_bam_reads_to_library:
    input:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.unsorted.with_unmapped.bam",
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_sort_bam.log",
    threads: 8
    message:
        "Sorting BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/sort"

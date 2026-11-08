####################################################
# Reference mapper: bwa-aln (bwa aln + samse)
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py. The REVEAL steps have their own mappers/ folders.
####################################################


rule index_reference_for_mapping_bwa_aln:
    input:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            )
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_bwa_aln_index.log",
    cache: True
    message:
        "Indexing reference {wildcards.reference} with BWA (for BWA ALN)"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/index"


rule align_reads_to_reference_bwa_aln:
    input:
        fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.sai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_bwa_aln.log",
    threads: 10
    params:
        extra=_ref_mapper_extra,
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/aln"


rule map_reads_to_reference_bwa_aln:
    input:
        fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
        sai="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.sai",
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
    threads: 1
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/samse"

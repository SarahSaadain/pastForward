####################################################
# Reference mapper: bwa-mem2
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py (the other mapping steps still pick their mapper in their own .smk).
####################################################


rule index_reference_for_mapping_bwa_mem2:
    input:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".0123",
                ".amb",
                ".ann",
                ".bwt.2bit.64",
                ".pac",
            )
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_bwa_mem2_index.log",
    cache: True
    message:
        "Indexing reference {wildcards.reference} with BWA-MEM2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa-mem2/index"


rule map_reads_to_reference_bwa_mem2:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
            ".0123",
            ".amb",
            ".ann",
            ".bwt.2bit.64",
            ".pac",
        ),
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
    threads: 15
    params:
        extra=_ref_mapper_extra,
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa-mem2/mem"

####################################################
# Reference mapper: minimap2
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py. The REVEAL steps have their own mappers/ folders.
####################################################


rule index_reference_for_mapping_minimap2:
    input:
        target="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/reference/{reference}.mmi"
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_minimap2_index.log",
    cache: True
    resources:
        mem_mb=16000,
    message:
        "Indexing reference {wildcards.reference} with minimap2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/minimap2/index"


rule map_reads_to_reference_minimap2:
    input:
        query=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        target="{species}/processed/reference_module/{reference}/reference/{reference}.mmi",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
    threads: 15
    params:
        extra=_ref_mapper_extra,
        sorting="none",
    wrapper:
        f"{WRAPPER_VERSION}/bio/minimap2/aligner"

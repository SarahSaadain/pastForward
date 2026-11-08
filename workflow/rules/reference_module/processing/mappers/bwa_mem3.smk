####################################################
# Reference mapper: bwa-mem3
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py. The REVEAL steps have their own mappers/ folders.
####################################################
# No wrapper exists for bwa-mem3: plain shell rules in workflow/envs/bwa_mem3.yaml. Its index has no .0123 file.


rule index_reference_for_mapping_bwa_mem3:
    input:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".amb",
                ".ann",
                ".bwt.2bit.64",
                ".pac",
            )
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_bwa_mem3_index.log",
    cache: True
    conda:
        "../../../../envs/bwa_mem3.yaml"
    message:
        "Indexing reference {wildcards.reference} with BWA-MEM3"
    shell:
        "bwa-mem3 index {input} 2> {log}"


rule map_reads_to_reference_bwa_mem3:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
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
    conda:
        "../../../../envs/bwa_mem3.yaml"
    threads: 15
    params:
        extra=_ref_mapper_extra,
    shell:
        "(bwa-mem3 mem -t {threads} {params.extra} {input.ref:q} {input.reads} --bam=0 "
        "| samtools view -b -o {output}) 2> {log}"

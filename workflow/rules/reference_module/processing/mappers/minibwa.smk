####################################################
# Reference mapper: minibwa
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py. The REVEAL steps have their own mappers/ folders.
####################################################
# No wrapper exists for minibwa: plain shell rules in workflow/envs/minibwa.yaml. Index = .l2b + .mbw, prefix = the FASTA path.


rule index_reference_for_mapping_minibwa:
    input:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".mbw",
                ".l2b",
            )
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_minibwa_index.log",
    cache: True
    conda:
        "../../../../envs/minibwa.yaml"
    message:
        "Indexing reference {wildcards.reference} with minibwa"
    shell:
        "minibwa index {input} 2> {log}"


rule map_reads_to_reference_minibwa:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
            ".mbw",
            ".l2b",
        ),
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
    conda:
        "../../../../envs/minibwa.yaml"
    threads: 15
    params:
        extra=_ref_mapper_extra,
    shell:
        "(minibwa map -t {threads} {params.extra} {input.ref:q} {input.reads} "
        "| samtools view -b -o {output}) 2> {log}"

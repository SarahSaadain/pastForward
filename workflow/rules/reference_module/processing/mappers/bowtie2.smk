####################################################
# Reference mapper: bowtie2
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py.
####################################################
# Index = .1-4.bt2 + .rev.1-2.bt2 (genomes over about 4 Gb get .bt2l and are not supported), prefix = the FASTA path.


rule index_reference_for_mapping_bowtie2:
    input:
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".1.bt2",
                ".2.bt2",
                ".3.bt2",
                ".4.bt2",
                ".rev.1.bt2",
                ".rev.2.bt2",
            )
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_bowtie2_index.log",
    cache: True
    threads: 4
    message:
        "Indexing reference {wildcards.reference} with bowtie2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bowtie2/build"


rule map_reads_to_reference_bowtie2:
    input:
        sample=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
            ".1.bt2",
            ".2.bt2",
            ".3.bt2",
            ".4.bt2",
            ".rev.1.bt2",
            ".rev.2.bt2",
        ),
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
    threads: _reference_mapping_threads
    params:
        extra=_ref_mapper_extra,
    wrapper:
        f"{WRAPPER_VERSION}/bio/bowtie2/align"

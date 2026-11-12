####################################################
# Reference mapper: bowtie
# Included by map_reads_to_reference.smk when pipeline.reference_module.mapping.settings.mapper picks it.
# Needs `_ref_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py.
####################################################
# No wrapper exists for bowtie: plain shell rules in workflow/envs/bowtie.yaml. Index = .1-4.ebwt + .rev.1-2.ebwt (genomes over about 4 Gb get .ebwtl and are not supported), prefix = the FASTA path.


rule index_reference_for_mapping_bowtie:
    input:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        temp(
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".1.ebwt",
                ".2.ebwt",
                ".3.ebwt",
                ".4.ebwt",
                ".rev.1.ebwt",
                ".rev.2.ebwt",
            )
        ),
    log:
        "{species}/processed/reference_module/{reference}/index/{reference}_bowtie_index.log",
    cache: True
    conda:
        "../../../../envs/bowtie.yaml"
    threads: 4
    message:
        "Indexing reference {wildcards.reference} with bowtie"
    shell:
        "bowtie-build --threads {threads} {input:q} {input:q} > {log} 2>&1"


rule map_reads_to_reference_bowtie:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        idx=multiext(
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
            ".1.ebwt",
            ".2.ebwt",
            ".3.ebwt",
            ".4.ebwt",
            ".rev.1.ebwt",
            ".rev.2.ebwt",
        ),
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
    conda:
        "../../../../envs/bowtie.yaml"
    threads: _reference_mapping_threads
    params:
        extra=_ref_mapper_extra,
    shell:
        "(bowtie -S -p {threads} {params.extra} {input.ref:q} {input.reads} "
        "| samtools view -b -o {output}) 2> {log}"

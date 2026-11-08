####################################################
# REVEAL feature-library mapper: bowtie
# Included by map_reads_to_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_dyn_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py.
####################################################
# No wrapper exists for bowtie: plain shell rules in workflow/envs/bowtie.yaml. Index = .1-4.ebwt + .rev.1-2.ebwt (genomes over about 4 Gb get .ebwtl and are not supported), prefix = the FASTA path.


rule index_library_for_mapping_bowtie:
    input:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
    output:
        temp(
            multiext(
                "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
                ".1.ebwt",
                ".2.ebwt",
                ".3.ebwt",
                ".4.ebwt",
                ".rev.1.ebwt",
                ".rev.2.ebwt",
            )
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_bowtie_index.log",
    conda:
        "../../../../envs/bowtie.yaml"
    threads: 4
    message:
        "Indexing SCG and Feature library {input} with bowtie"
    shell:
        "bowtie-build --threads {threads} {input:q} {input:q} > {log} 2>&1"


rule map_reads_to_scg_feature_library_bowtie:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
        idx=multiext(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
            ".1.ebwt",
            ".2.ebwt",
            ".3.ebwt",
            ".4.ebwt",
            ".rev.1.ebwt",
            ".rev.2.ebwt",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bowtie.log",
    conda:
        "../../../../envs/bowtie.yaml"
    threads: 10
    params:
        extra=_dyn_mapper_extra,
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG and Feature library with bowtie"
    shell:
        "(bowtie -S -p {threads} {params.extra} {input.ref:q} {input.reads} "
        "| samtools sort -@ 2 -o {output}) 2> {log}"

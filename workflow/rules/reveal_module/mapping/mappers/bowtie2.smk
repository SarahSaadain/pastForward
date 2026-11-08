####################################################
# REVEAL feature-library mapper: bowtie2
# Included by map_reads_to_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_dyn_mapper_extra` from the including file. To add a mapper: copy this file, add the name
# to the `mapper` enum in workflow/schemas/config.schema.yaml, and to _SUFFIXES in
# workflow/scripts/index_compression.py.
####################################################
# Index = .1-4.bt2 + .rev.1-2.bt2 (genomes over about 4 Gb get .bt2l and are not supported), prefix = the FASTA path.
# The align wrapper cannot sort, so the mapping rule is a shell rule (bowtie2 | samtools sort) in workflow/envs/bowtie2.yaml.


rule index_library_for_mapping_bowtie2:
    input:
        ref="{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
    output:
        temp(
            multiext(
                "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
                ".1.bt2",
                ".2.bt2",
                ".3.bt2",
                ".4.bt2",
                ".rev.1.bt2",
                ".rev.2.bt2",
            )
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_bowtie2_index.log",
    threads: 4
    message:
        "Indexing SCG and Feature library {input.ref} with bowtie2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bowtie2/build"


rule map_reads_to_scg_feature_library_bowtie2:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
        idx=multiext(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
            ".1.bt2",
            ".2.bt2",
            ".3.bt2",
            ".4.bt2",
            ".rev.1.bt2",
            ".rev.2.bt2",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bowtie2.log",
    conda:
        "../../../../envs/bowtie2.yaml"
    threads: 10
    params:
        extra=_dyn_mapper_extra,
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG and Feature library with bowtie2"
    shell:
        "(bowtie2 -p {threads} {params.extra} -x {input.ref:q} -U {input.reads} "
        "| samtools sort -@ 2 -o {output}) 2> {log}"

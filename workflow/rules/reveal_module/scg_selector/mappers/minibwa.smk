####################################################
# REVEAL SCG-library mapper: minibwa
# Included by map_reads_to_scg_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_scg_sel_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################
# No wrapper exists for minibwa: plain shell rules in workflow/envs/minibwa.yaml. Index = .l2b + .mbw, prefix = the FASTA path.


rule index_scg_library_for_mapping_minibwa:
    input:
        "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
    output:
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.mbw"),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.l2b"),
    log:
        "{species}/processed/reveal_module/scg/{species}_scg_library_minibwa_index.log",
    conda:
        "../../../../envs/minibwa.yaml"
    message:
        "Indexing SCG library {input} with minibwa"
    shell:
        "minibwa index {input} 2> {log}"


rule map_reads_to_scg_library_minibwa:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
        idx=multiext(
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
            ".mbw",
            ".l2b",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_minibwa.log",
    conda:
        "../../../../envs/minibwa.yaml"
    threads: 10
    params:
        extra=_scg_sel_mapper_extra,
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG library with minibwa"
    shell:
        "(minibwa map -t {threads} {params.extra} {input.ref:q} {input.reads} "
        "| samtools sort -@ 2 -o {output}) 2> {log}"

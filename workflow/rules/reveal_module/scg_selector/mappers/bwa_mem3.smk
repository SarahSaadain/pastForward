####################################################
# REVEAL SCG-library mapper: bwa-mem3
# Included by map_reads_to_scg_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_scg_sel_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################
# No wrapper exists for bwa-mem3: plain shell rules in workflow/envs/bwa_mem3.yaml. Its index has no .0123 file.


rule index_scg_library_for_mapping_bwa_mem3:
    input:
        "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
    output:
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.amb"),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.ann"),
        temp(
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.bwt.2bit.64"
        ),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.pac"),
    log:
        "{species}/processed/reveal_module/scg/{species}_scg_library_bwa_index.log",
    conda:
        "../../../../envs/bwa_mem3.yaml"
    message:
        "Indexing SCG library {input} with BWA-MEM3"
    shell:
        "bwa-mem3 index {input} 2> {log}"


rule map_reads_to_scg_library_bwa_mem3:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        ref="{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
        idx=multiext(
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
            ".amb",
            ".ann",
            ".bwt.2bit.64",
            ".pac",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa.log",
    conda:
        "../../../../envs/bwa_mem3.yaml"
    threads: 10
    params:
        extra=_scg_sel_mapper_extra,
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG library with BWA-MEM3"
    shell:
        "(bwa-mem3 mem -t {threads} {params.extra} {input.ref:q} {input.reads} --bam=0 "
        "| samtools sort -@ 2 -o {output}) 2> {log}"

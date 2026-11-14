####################################################
# REVEAL SCG-library mapper: bwa-mem
# Included by map_reads_to_scg_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_scg_sel_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################


rule index_scg_library_for_mapping_bwa_mem:
    input:
        "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
    output:
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.sa"),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.amb"),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.ann"),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.bwt"),
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.pac"),
    log:
        "{species}/processed/reveal_module/scg/{species}_scg_library_bwa_index.log",
    message:
        "Indexing SCG library {input} with BWA-MEM"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/index"


rule map_reads_to_scg_library_bwa_mem:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        idx=multiext(
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
            ".amb",
            ".ann",
            ".bwt",
            ".pac",
            ".sa",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa.log",
    threads: 10
    params:
        extra=_scg_sel_mapper_extra,
        sorting="samtools",
        sort_order="coordinate",
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG library with BWA-MEM"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa/mem"

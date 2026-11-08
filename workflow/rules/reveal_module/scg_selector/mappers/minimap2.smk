####################################################
# REVEAL SCG-library mapper: minimap2
# Included by map_reads_to_scg_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_scg_sel_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################


rule index_scg_library_for_mapping_minimap2:
    input:
        target="{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
    output:
        temp("{species}/processed/reveal_module/scg/{species}_scg_library.fasta.mmi"),
    log:
        "{species}/processed/reveal_module/scg/{species}_scg_library_minimap2_index.log",
    message:
        "Indexing SCG library {input} with minimap2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/minimap2/index"


rule map_reads_to_scg_library_minimap2:
    input:
        query=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        target="{species}/processed/reveal_module/scg/{species}_scg_library.fasta.mmi",
    output:
        temp(
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_minimap2.log",
    threads: 10
    params:
        extra=_scg_sel_mapper_extra,
        sorting="coordinate",
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG library with minimap2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/minimap2/aligner"

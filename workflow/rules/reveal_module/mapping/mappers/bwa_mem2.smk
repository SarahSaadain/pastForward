####################################################
# REVEAL feature-library mapper: bwa-mem2
# Included by map_reads_to_library.smk for the configured mapper (see config.schema.yaml enum).
# Needs `_dyn_mapper_extra` from the including file. To add a mapper: copy this file, add the name to the
# `mapper` enum in workflow/schemas/config.schema.yaml and to _SUFFIXES in workflow/scripts/index_compression.py.
####################################################


rule index_library_for_mapping_bwa_mem2:
    input:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.0123"
        ),
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.amb"
        ),
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.ann"
        ),
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.bwt.2bit.64"
        ),
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.pac"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_bwa_index.log",
    message:
        "Indexing SCG and Feature library {input} with BWA-MEM2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa-mem2/index"


rule map_reads_to_scg_feature_library_bwa_mem2:
    input:
        reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
        idx=multiext(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
            ".amb",
            ".ann",
            ".bwt.2bit.64",
            ".pac",
            ".0123",
        ),
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bwa.log",
    threads: 10
    params:
        extra=_dyn_mapper_extra,
        sort="samtools",
        sort_order="coordinate",
    message:
        "Mapping reads of {wildcards.individual} to {wildcards.species} SCG and Feature library with BWA-MEM2"
    wrapper:
        f"{WRAPPER_VERSION}/bio/bwa-mem2/mem"

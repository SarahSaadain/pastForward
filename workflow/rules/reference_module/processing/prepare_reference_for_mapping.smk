####################################################
# Snakemake rules
####################################################
_ref_mapper = (
    config.get("pipeline", {})
    .get("reference_module", {})
    .get("mapping", {})
    .get("settings", {})
    .get("mapper", "bwa-mem2")
)


rule standardize_reference_extension_to_fa:
    input:
        ref=_standardize_reference_extension_to_fa_ref_path,
    output:
        fa="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    log:
        "{species}/processed/reference_module/{reference}/reference/{reference}_standardize.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Linking reference {wildcards.reference} for {wildcards.species} into processed/ as .fa (input/ is never modified)"
    script:
        "../../../scripts/reference_module/processing/standardize_reference_extension_to_fa.py"


if _ref_mapper == "minimap2":

    rule index_reference_for_mapping_minimap2:
        input:
            target="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        output:
            "{species}/processed/reference_module/{reference}/reference/{reference}.mmi",
        log:
            "{species}/processed/reference_module/{reference}/index/{reference}_minimap2_index.log",
        cache: True
        resources:
            mem_mb=16000,
        message:
            "Indexing reference {wildcards.reference} with minimap2"
        wrapper:
            f"{WRAPPER_VERSION}/bio/minimap2/index"

elif _ref_mapper == "bwa-aln":

    # bwa-aln
    rule index_reference_for_mapping_bwa_aln:
        input:
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        output:
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        log:
            "{species}/processed/reference_module/{reference}/index/{reference}_bwa_aln_index.log",
        cache: True
        resources:
            mem_mb=369000,
        message:
            "Indexing reference {wildcards.reference} with BWA (for BWA ALN)"
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa/index"

else:

    rule index_reference_for_mapping_bwa_mem2:
        input:
            "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        output:
            multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".0123",
                ".amb",
                ".ann",
                ".bwt.2bit.64",
                ".pac",
            ),
        log:
            "{species}/processed/reference_module/{reference}/index/{reference}_bwa_mem2_index.log",
        cache: True
        resources:
            mem_mb=369000,
        message:
            "Indexing reference {wildcards.reference} with BWA-MEM2"
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa-mem2/index"


rule index_reference_with_samtools:
    input:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa.fai",
    log:
        "{species}/processed/reference_module/{reference}/reference/{reference}.fa.fai.log",
    params:
        extra="",
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/faidx"

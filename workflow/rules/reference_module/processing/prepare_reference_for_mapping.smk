####################################################
# Snakemake rules
####################################################
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


# The mapper-specific index rule lives in mappers/<mapper>.smk (included by map_reads_to_reference.smk).


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

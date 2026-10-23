####################################################
# Determine the BAM produced by the last processing step before any
# unmapped-read filtering.  Snakemake expands {wildcards} in string
# inputs, so this module-level variable can be used directly as a rule
# input across this file and any file included after it
# (filter_unmapped_reads.smk, analytics rules, etc.).
####################################################

if (
    config.get("pipeline", {})
    .get("reference_module", {})
    .get("damage_rescaling", {})
    .get("execute", True)
):
    _pre_filter_bam = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled.bam"
elif (
    config.get("pipeline", {})
    .get("reference_module", {})
    .get("deduplication", {})
    .get("execute", True)
):
    _pre_filter_bam = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam"
else:
    _pre_filter_bam = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam"

####################################################
# Snakemake rules
####################################################

_filter_remove = (
    config.get("pipeline", {})
    .get("reference_module", {})
    .get("filter_unmapped_reads", {})
    .get("execute", False)
    and config.get("pipeline", {})
    .get("reference_module", {})
    .get("filter_unmapped_reads", {})
    .get("settings", {})
    .get("action", "remove")
    == "remove"
)

if _filter_remove:

    # When unmapped reads are removed, get_final_bam copies from the mapped-only
    # intermediate produced by filter_mapped_only_bam + index_mapped_only_bam.
    rule get_final_bam:
        input:
            bam="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.bam",
            bai="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_mapped_only.bam.bai",
        output:
            bam="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam",
            bai="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam.bai",
        log:
            "{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.log",
        conda:
            "../../../envs/python_and_r.yaml"
        message:
            "Getting final (mapped-only) BAM for {wildcards.individual} of {wildcards.species}."
        shell:
            # Use a hard link (copy if cross-filesystem) so the mapped-only intermediate is still available for any
            # other rule that depends on it; temp() handles deletion afterwards.
            """
            echo "Linking final bam and bai for {wildcards.individual} mapped to {wildcards.reference}..." >"{log}" 2>&1
            echo "Input bam: {input.bam}" >>"{log}" 2>&1
            echo "Output bam: {output.bam}" >>"{log}" 2>&1
            ln -fL "{input.bam}" "{output.bam}" 2>/dev/null || cp "{input.bam}" "{output.bam}" >>"{log}" 2>&1
            ln -fL "{input.bai}" "{output.bai}" 2>/dev/null || cp "{input.bai}" "{output.bai}" >>"{log}" 2>&1
            echo "Done linking final bam and bai for {wildcards.individual} mapped to {wildcards.reference}." >>"{log}" 2>&1
            """

else:

    # Default: copy directly from the last processing-step BAM (_pre_filter_bam).
    rule get_final_bam:
        input:
            bam=_pre_filter_bam,
            bai=f"{_pre_filter_bam}.bai",
        output:
            bam="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam",
            bai="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam.bai",
        log:
            "{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.log",
        conda:
            "../../../envs/python_and_r.yaml"
        message:
            "Getting final bam for {wildcards.individual} of {wildcards.species}."
        shell:
            # The final bam is just a copy of the bam that is output from the last step of the reference
            # processing pipeline (either damage rescaling, deduplication, or mapping)
            # We hard link (copy if cross-filesystem) instead of move. If we would use move here, other rules will not know that the input bam
            # will be renamed. These other rules will then fail because the input bam is not found (as it has been renamed).
            # By using copy, we ensure that the input bam is still available for other rules that need it.
            # The input bam will be deleted at the end of the pipeline when the intermediate files are cleaned up.
            """
            echo "Linking final bam and bai for {wildcards.individual} mapped to {wildcards.reference}..." >"{log}" 2>&1
            echo "Input bam: {input.bam}" >>"{log}" 2>&1
            echo "Output bam: {output.bam}" >>"{log}" 2>&1
            ln -fL "{input.bam}" "{output.bam}" 2>/dev/null || cp "{input.bam}" "{output.bam}" >>"{log}" 2>&1
            ln -fL "{input.bai}" "{output.bai}" 2>/dev/null || cp "{input.bai}" "{output.bai}" >>"{log}" 2>&1
            echo "Done linking final bam and bai for {wildcards.individual} mapped to {wildcards.reference}." >>"{log}" 2>&1
            """

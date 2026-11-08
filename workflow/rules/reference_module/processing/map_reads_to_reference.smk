####################################################
# Snakemake rules
####################################################
_ref_settings = _setting("reference_module", "mapping", "settings", default={})
_ref_mapper = _ref_settings.get("mapper", "bwa-mem3")
_ref_mapper_extra = _mapper_extra(_ref_settings, _ref_mapper)


# One file per mapper in mappers/ holds its index rule and its mapping rule(s).
# Name = mapper with "-" as "_" (bwa-mem2 -> bwa_mem2.smk).
include: f"mappers/{_ref_mapper.replace('-', '_')}.smk"


# keep_bam: the sorted BAM and its index stay in processed/ (no temp) so a later step never
# remaps, and the keep_bam rule below adds a copy in results/.
_KEEP_SORTED_BAM = _setting(
    "reference_module", "mapping", "settings", "keep_bam", default=False
)
_SORTED_BAM = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam"
_SORTED_BAM_BAI = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam.bai"


# Rule: Sort BAM file
rule sort_mapped_reads_bam:
    # 3 Sort BAM
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam",
    output:
        _SORTED_BAM if _KEEP_SORTED_BAM else temp(_SORTED_BAM),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_bam.log",
    threads: 10
    message:
        "Sorting BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/sort"


# Rule: Index BAM file
rule index_mapped_sorted_reads_bam:
    # 4 Index BAM
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam",
    output:
        _SORTED_BAM_BAI if _KEEP_SORTED_BAM else temp(_SORTED_BAM_BAI),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam.bai.log",
    threads: 5
    params:
        extra="",  # optional params string
    message:
        "Indexing BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"


# One rule for all kept BAMs (sorted, deduplicated, rescaled). Hard link when results/ is on the same disk (no extra space), copy otherwise.
rule keep_bam:
    input:
        bam="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_{stage}.bam",
        bai="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_{stage}.bam.bai",
    output:
        bam="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_{stage}.bam",
        bai="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_{stage}.bam.bai",
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_keep_{stage}_bam.log",
    wildcard_constraints:
        stage="sorted|sorted_dedupped|sorted_dedupped_rescaled",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Keeping {wildcards.stage} BAM of {wildcards.individual} mapped to {wildcards.reference} in results"
    shell:
        """
        ln -f "{input.bam}" "{output.bam}" >"{log}" 2>&1 || cp -p "{input.bam}" "{output.bam}" >>"{log}" 2>&1
        ln -f "{input.bai}" "{output.bai}" >>"{log}" 2>&1 || cp -p "{input.bai}" "{output.bai}" >>"{log}" 2>&1
        """

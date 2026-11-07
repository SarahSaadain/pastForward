####################################################
# Snakemake rules
####################################################
_ref_settings = _setting("reference_module", "mapping", "settings", default={})
_ref_mapper = _ref_settings.get("mapper", "bwa-mem2")
_ref_mapper_extra = _mapper_extra(_ref_settings, _ref_mapper)

if _ref_mapper == "minimap2":

    rule map_reads_to_reference_minimap2:
        input:
            query=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
            target="{species}/processed/reference_module/{reference}/reference/{reference}.mmi",
        output:
            temp(
                "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
            ),
        log:
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
        threads: 15
        params:
            extra=_ref_mapper_extra,
            sorting="none",
        wrapper:
            f"{WRAPPER_VERSION}/bio/minimap2/aligner"

elif _ref_mapper == "bwa-aln":

    # bwa-aln
    rule align_reads_to_reference_bwa_aln:
        input:
            fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
            idx=multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        output:
            temp(
                "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.sai"
            ),
        log:
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_bwa_aln.log",
        threads: 10
        params:
            extra=_ref_mapper_extra,
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa/aln"

    rule map_reads_to_reference_bwa_aln:
        input:
            fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
            sai="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.sai",
            idx=multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        output:
            temp(
                "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
            ),
        log:
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
        threads: 1
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa/samse"

else:

    rule map_reads_to_reference_bwa_mem2:
        input:
            reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
            idx=multiext(
                "{species}/processed/reference_module/{reference}/reference/{reference}.fa",
                ".0123",
                ".amb",
                ".ann",
                ".bwt.2bit.64",
                ".pac",
            ),
        output:
            temp(
                "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted.bam"
            ),
        log:
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}.bam.log",
        threads: 15
        params:
            extra=_ref_mapper_extra,
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa-mem2/mem"


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

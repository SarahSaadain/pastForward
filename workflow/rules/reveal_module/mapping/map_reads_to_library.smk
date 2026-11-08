####################################################
# Snakemake rules
####################################################
_dyn_settings = _setting("reveal_module", "mapping", "settings", default={})
_dyn_mapper = _dyn_settings.get("mapper", "bwa-mem2")
_dyn_mapper_extra = _mapper_extra(_dyn_settings, _dyn_mapper)
_dyn_keep_mapped_bam = _dyn_settings.get("keep_mapped_bam", False)
_dyn_min_mapq_scg = _dyn_settings.get("min_mapq_scg", 0)
_dyn_min_mapq_fle = _dyn_settings.get("min_mapq_fle", 0)
_comp_execute = _setting(
    "reveal_module", "mapping", "settings", "competitive_mapping", default=False
)

_MAPPED_BAM = "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam"
_MAPPED_BAI = f"{_MAPPED_BAM}.bai"
_MAPPED_BAM_PRECOMP = "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.precomp.bam"
_MAPPED_BAM_PREMAPQ = "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.premapq.bam"


# One file per mapper in mappers/ holds its index and mapping rule(s).
# Name = mapper with "-" as "_" (bwa-mem2 -> bwa_mem2.smk).
include: f"mappers/{_dyn_mapper.replace('-', '_')}.smk"


if _comp_execute:

    # Rule: Remove unmapped reads — output is intermediate (competition filter follows)
    rule remove_unmapped_reads_to_scg_feature_library:
        input:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam",
        output:
            bam=temp(_MAPPED_BAM_PRECOMP),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_remove_unmapped.log",
        threads: 2
        params:
            extra="-b -F 4",
        message:
            "Removing unmapped reads from BAM file for {input}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/samtools/view"

    # Rule: Remove reads mapping to competition sequences (_comp suffix)
    rule filter_competition_reads_from_bam:
        input:
            bam=_MAPPED_BAM_PRECOMP,
        output:
            bam=(
                temp(_MAPPED_BAM_PREMAPQ)
                if (_dyn_min_mapq_scg > 0 or _dyn_min_mapq_fle > 0)
                else (_MAPPED_BAM if _dyn_keep_mapped_bam else temp(_MAPPED_BAM))
            ),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_filter_comp.log",
        conda:
            "../../../envs/samtools.yaml"
        threads: 2
        message:
            "Filtering competition sequences from BAM for {wildcards.individual}"
        shell:
            # Stream the BAM through awk to drop @SQ headers and alignment records for _comp references.
            # No index needed because we process the stream linearly.
            """
            samtools view -h "{input.bam}" \
                | awk -f workflow/scripts/reveal_module/mapping/filter_out_comp_bam_records.awk \
                | samtools view -b >"{output.bam}" 2>"{log}"
            """

else:

    # Rule: Remove unmapped reads — output is either pre-MAPQ intermediate or the final BAM
    rule remove_unmapped_reads_to_scg_feature_library:
        input:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam",
        output:
            bam=(
                temp(_MAPPED_BAM_PREMAPQ)
                if (_dyn_min_mapq_scg > 0 or _dyn_min_mapq_fle > 0)
                else (_MAPPED_BAM if _dyn_keep_mapped_bam else temp(_MAPPED_BAM))
            ),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_remove_unmapped.log",
        threads: 2
        params:
            extra="-b -F 4",
        message:
            "Removing unmapped reads from BAM file for {input}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/samtools/view"


if _dyn_min_mapq_scg > 0 or _dyn_min_mapq_fle > 0:

    # Rule: Apply per-suffix MAPQ filters; SCG (_scg) and feature (_fle) thresholds are independent.
    rule filter_reveal_reads_from_bam_by_mapq:
        input:
            bam=_MAPPED_BAM_PREMAPQ,
        output:
            bam=_MAPPED_BAM if _dyn_keep_mapped_bam else temp(_MAPPED_BAM),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_filter_mapq.log",
        conda:
            "../../../envs/samtools.yaml"
        threads: 2
        params:
            min_mapq_scg=_dyn_min_mapq_scg,
            min_mapq_fle=_dyn_min_mapq_fle,
        message:
            "Filtering reads by MAPQ (SCG < {params.min_mapq_scg}, FLE < {params.min_mapq_fle}) for {wildcards.individual}"
        shell:
            """
            samtools view -h "{input.bam}" \
                | awk -v mq_scg={params.min_mapq_scg} -v mq_fle={params.min_mapq_fle} \
                    'BEGIN{{OFS="\t"}} /^@/{{print; next}} ($3 ~ /_scg$/ && $5+0 < mq_scg) {{next}} ($3 ~ /_fle$/ && $5+0 < mq_fle) {{next}} {{print}}' \
                | samtools view -b -o "{output.bam}" 2>"{log}"
            """


# SAMTOOLS doesn't parallelize the indexing work — it only parallelizes compression/decompression.
rule index_bam_reads_to_library:
    input:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam",
    output:
        _MAPPED_BAI if _dyn_keep_mapped_bam else temp(_MAPPED_BAI),
    log:
        "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_index.log",
    threads: 5
    params:
        extra="",
    message:
        "Indexing BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"

####################################################
# Snakemake rules
####################################################

_scg_sel_settings = _setting("reveal_module", "scg_selector", "settings", default={})
_dyn_settings = _setting("reveal_module", "mapping", "settings", default={})
_scg_sel_mapper, _scg_sel_mapper_extra = _scg_mapper_and_extra(
    _scg_sel_settings, _dyn_settings
)
_scg_keep_bam = _scg_sel_settings.get("keep_mapped_bam", False)
_scg_min_mapq = _scg_sel_settings.get("min_mapq", 0)

_SCG_SORTED_BAM = "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.bam"
_SCG_SORTED_BAI = f"{_SCG_SORTED_BAM}.bai"


# One file per mapper in mappers/ holds its index and mapping rule(s).
# Name = mapper with "-" as "_" (bwa-mem2 -> bwa_mem2.smk).
include: f"mappers/{_scg_sel_mapper.replace('-', '_')}.smk"


_mapq_extra = f" -q {_scg_min_mapq}" if _scg_min_mapq > 0 else ""


# Remove unmapped reads and optionally apply MAPQ filter in one pass.
# Since all references in the SCG library are SCG sequences, samtools -q filters globally.
rule remove_unmapped_reads_and_filter_by_mapq_from_scg_bam:
    input:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam",
    output:
        bam=_SCG_SORTED_BAM if _scg_keep_bam else temp(_SCG_SORTED_BAM),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_remove_unmapped.log",
    threads: 2
    params:
        extra=f"-b -F 4{_mapq_extra}",
    message:
        "Removing unmapped reads from SCG BAM for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


# SAMTOOLS doesn't parallelize the indexing work — it only parallelizes compression/decompression.
rule index_scg_bam_reads:
    input:
        _SCG_SORTED_BAM,
    output:
        _SCG_SORTED_BAI if _scg_keep_bam else temp(_SCG_SORTED_BAI),
    log:
        "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_index.log",
    threads: 5
    params:
        extra="",
    message:
        "Indexing SCG BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"

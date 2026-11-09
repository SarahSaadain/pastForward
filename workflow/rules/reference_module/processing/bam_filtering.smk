####################################################
# Optional MAPQ and read-length filter on the reference BAM.
#
# Config (reference_module.bam_filtering, default off):
#   settings.min_mapq        # keep reads with MAPQ >= this (0 = no filter)
#   settings.min_read_length # keep reads with length >= this in bp (0 = no filter)
# Unmapped reads have MAPQ 0, so min_mapq > 0 drops them too. What happens to unmapped reads
# otherwise is set in filter_unmapped_reads (its "remove" action is applied here as -F 4).
# QC statistics read _pre_filter_bam, so they still describe the unfiltered BAM.
####################################################


rule filter_bam_by_mapq_and_length:
    input:
        bam=_pre_filter_bam,
        bai=f"{_pre_filter_bam}.bai",
    output:
        temp(_BAM_FILTERED),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_filtered.log",
    threads: 4
    params:
        extra=_bam_filter_extra(_filter_remove),
    message:
        "Filtering BAM by MAPQ and read length for {wildcards.individual} mapped to {wildcards.reference}."
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


rule index_filtered_bam:
    input:
        _BAM_FILTERED,
    output:
        temp(f"{_BAM_FILTERED}.bai"),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_filtered.bam.bai.log",
    threads: 4
    params:
        extra="",
    message:
        "Indexing filtered BAM for {wildcards.individual} mapped to {wildcards.reference}."
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"

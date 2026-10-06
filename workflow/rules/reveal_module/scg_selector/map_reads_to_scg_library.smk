####################################################
# Snakemake rules
####################################################

_scg_sel_settings = (
    config.get("pipeline", {})
    .get("reveal_module", {})
    .get("scg_selector", {})
    .get("settings", {})
)
_dyn_settings = (
    config.get("pipeline", {})
    .get("reveal_module", {})
    .get("mapping", {})
    .get("settings", {})
)
_dyn_mapper_default = _dyn_settings.get("mapper", "bwa-mem2")
_scg_sel_mapper = _scg_sel_settings.get("mapper") or _dyn_mapper_default
_SCG_BWA_ALN_DEFAULTS = (
    "-n 0.01 -k 2 -l 1024 -o 2"  # Oliva et al. 2021 (10.1093/bib/bbab076)
)
_SCG_MINIMAP2_DEFAULTS = "-ax sr"
_mapper_extra_fallback = (
    _SCG_BWA_ALN_DEFAULTS
    if _scg_sel_mapper == "bwa-aln"
    else (_SCG_MINIMAP2_DEFAULTS if _scg_sel_mapper == "minimap2" else "")
)
_scg_sel_mapper_extra = (
    _scg_sel_settings.get("mapper_extra_params")
    or _dyn_settings.get("mapper_extra_params")
    or _mapper_extra_fallback
)
_scg_keep_bam = _scg_sel_settings.get("keep_mapped_bam", False)
_scg_min_mapq = _scg_sel_settings.get("min_mapq", 0)

_SCG_SORTED_BAM = "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.bam"
_SCG_SORTED_BAI = f"{_SCG_SORTED_BAM}.bai"

if _scg_sel_mapper == "minimap2":

    rule index_scg_library_for_mapping_minimap2:
        input:
            target="{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
        output:
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.mmi",
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

elif _scg_sel_mapper == "bwa-aln":

    rule index_scg_library_for_mapping_bwa_aln:
        input:
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
        output:
            multiext(
                "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        log:
            "{species}/processed/reveal_module/scg/{species}_scg_library_bwa_aln_index.log",
        message:
            "Indexing SCG library {input} with BWA (for BWA ALN)"
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa/index"

    rule align_reads_to_scg_library_bwa_aln:
        input:
            fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
            idx=multiext(
                "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        output:
            temp(
                "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sai"
            ),
        log:
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa_aln.log",
        threads: 10
        params:
            extra=_scg_sel_mapper_extra,
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa/aln"

    rule map_reads_to_scg_library_bwa_aln:
        input:
            fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
            sai="{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sai",
            idx=multiext(
                "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        output:
            temp(
                "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.unsorted.with_unmapped.bam"
            ),
        log:
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa_samse.log",
        threads: 1
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa/samse"

    rule sort_scg_bam_reads:
        input:
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.unsorted.with_unmapped.bam",
        output:
            temp(
                "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
            ),
        log:
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_sort_bam.log",
        threads: 8
        message:
            "Sorting SCG BAM file for {input}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/samtools/sort"

else:
    # bwa-mem2 (default)

    rule index_scg_library_for_mapping_bwa_mem2:
        input:
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
        output:
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.0123",
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.amb",
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.ann",
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.bwt.2bit.64",
            "{species}/processed/reveal_module/scg/{species}_scg_library.fasta.pac",
        log:
            "{species}/processed/reveal_module/scg/{species}_scg_library_bwa_index.log",
        message:
            "Indexing SCG library {input} with BWA-MEM2"
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa-mem2/index"

    rule map_reads_to_scg_library_bwa_mem2:
        input:
            reads=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
            idx=multiext(
                "{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
                ".amb",
                ".ann",
                ".bwt.2bit.64",
                ".pac",
                ".0123",
            ),
        output:
            temp(
                "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.with_unmapped.bam"
            ),
        log:
            "{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library_bwa.log",
        threads: 10
        params:
            extra=_scg_sel_mapper_extra,
            sort="samtools",
            sort_order="coordinate",
        message:
            "Mapping reads of {wildcards.individual} to {wildcards.species} SCG library with BWA-MEM2"
        wrapper:
            f"{WRAPPER_VERSION}/bio/bwa-mem2/mem"


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

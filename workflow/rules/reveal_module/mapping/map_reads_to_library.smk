####################################################
# Snakemake rules
####################################################
_dyn_settings = (
    config.get("pipeline", {})
    .get("reveal_module", {})
    .get("mapping", {})
    .get("settings", {})
)
_dyn_mapper = _dyn_settings.get("mapper", "bwa-mem2")
_BWA_ALN_DEFAULTS = (
    "-n 0.01 -k 2 -l 1024 -o 2"  # Oliva et al. 2021 (10.1093/bib/bbab076)
)
_MINIMAP2_DEFAULTS = "-ax sr"
_dyn_mapper_extra = _dyn_settings.get(
    "mapper_extra_params",
    (
        _BWA_ALN_DEFAULTS
        if _dyn_mapper == "bwa-aln"
        else (_MINIMAP2_DEFAULTS if _dyn_mapper == "minimap2" else "")
    ),
)
_dyn_keep_mapped_bam = _dyn_settings.get("keep_mapped_bam", False)
_dyn_min_mapq_scg = _dyn_settings.get("min_mapq_scg", 0)
_dyn_min_mapq_fle = _dyn_settings.get("min_mapq_fle", 0)
_comp_execute = (
    config.get("pipeline", {})
    .get("reveal_module", {})
    .get("mapping", {})
    .get("settings", {})
    .get("competitive_mapping", False)
)

_MAPPED_BAM = "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam"
_MAPPED_BAI = f"{_MAPPED_BAM}.bai"
_MAPPED_BAM_PRECOMP = "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.precomp.bam"
_MAPPED_BAM_PREMAPQ = "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.premapq.bam"

if _dyn_mapper == "minimap2":

    rule index_library_for_mapping_minimap2:
        input:
            target="{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
        output:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.mmi",
        log:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_minimap2_index.log",
        message:
            "Indexing SCG and Feature library {input} with minimap2"
        wrapper:
            "v9.3.0/bio/minimap2/index"

    rule map_reads_to_scg_feature_library_minimap2:
        input:
            query=["{species}/results/read_module/reads_merged/{individual}.fastq.gz"],
            target="{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.mmi",
        output:
            temp(
                "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam"
            ),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_minimap2.log",
        threads: 10
        params:
            extra=_dyn_mapper_extra,
            sorting="coordinate",
        message:
            "Mapping reads of {wildcards.individual} to {wildcards.species} SCG and Feature library with minimap2"
        wrapper:
            "v9.3.0/bio/minimap2/aligner"

elif _dyn_mapper == "bwa-aln":

    rule index_library_for_mapping_bwa_aln:
        input:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
        output:
            multiext(
                "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        log:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_bwa_aln_index.log",
        message:
            "Indexing SCG and Feature library {input} with BWA (for BWA ALN)"
        wrapper:
            "v9.3.0/bio/bwa/index"

    rule align_reads_to_library_bwa_aln:
        input:
            fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
            idx=multiext(
                "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        output:
            temp(
                "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sai"
            ),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bwa_aln.log",
        threads: 10
        params:
            extra=_dyn_mapper_extra,
        wrapper:
            "v9.3.0/bio/bwa/aln"

    rule map_reads_to_scg_feature_library_bwa_aln:
        input:
            fastq="{species}/results/read_module/reads_merged/{individual}.fastq.gz",
            sai="{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sai",
            idx=multiext(
                "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
                ".amb",
                ".ann",
                ".bwt",
                ".pac",
                ".sa",
            ),
        output:
            temp(
                "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.unsorted.with_unmapped.bam"
            ),
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_bwa_samse.log",
        threads: 1
        wrapper:
            "v9.3.0/bio/bwa/samse"

    rule sort_bam_reads_to_library:
        input:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.unsorted.with_unmapped.bam",
        output:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.with_unmapped.bam",
        log:
            "{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg_sort_bam.log",
        threads: 8
        message:
            "Sorting BAM file for {input}"
        wrapper:
            "v9.3.0/bio/samtools/sort"

else:

    # bwa-mem2 (default)
    rule index_library_for_mapping_bwa_mem2:
        input:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
        output:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.0123",
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.amb",
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.ann",
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.bwt.2bit.64",
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta.pac",
        log:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg_bwa_index.log",
        message:
            "Indexing SCG and Feature library {input} with BWA-MEM2"
        wrapper:
            "v9.3.0/bio/bwa-mem2/index"

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
            "v9.3.0/bio/bwa-mem2/mem"


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
            "v9.3.0/bio/samtools/view"

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
            "v9.3.0/bio/samtools/view"


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
        "v9.3.0/bio/samtools/index"

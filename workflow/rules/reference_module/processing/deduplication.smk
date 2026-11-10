####################################################
# Snakemake rules
####################################################

# keep_bam: the deduplicated BAM and its index stay in processed/ (no temp) so a later step
# (e.g. damage rescaling) never redoes dedup, and the keep_bam rule (map_reads_to_reference.smk) adds a copy in results/.
_KEEP_DEDUP_BAM = _setting(
    "reference_module", "deduplication", "settings", "keep_bam", default=False
)
_DEDUP_BAM = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam"
_DEDUP_BAM_BAI = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam.bai"


# Rule: Count reads per contig from the sorted BAM's index (seconds, no read scan)
rule dedup_count_reads_per_contig:
    input:
        bam="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam",
        bai="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam.bai",
    output:
        idxstats=temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/{individual}_{reference}_idxstats.tsv"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/{individual}_{reference}_idxstats.log",
    conda:
        "../../../envs/samtools.yaml"
    message:
        "Counting reads per contig for individual {wildcards.individual} in species {wildcards.species}"
    shell:
        """
        samtools idxstats "{input.bam}" >"{output.idxstats}" 2>"{log}"
        """


# Checkpoint: Pack whole contigs into clusters with about the same number of reads
checkpoint dedup_create_all_contig_clusters:
    input:
        idxstats="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/{individual}_{reference}_idxstats.tsv",
    output:
        cluster_folder=directory(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/clusters"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_create_all_contig_clusters.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        cores=workflow.cores,
    message:
        "Creating contig clusters for deduplication for individual {wildcards.individual} in species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/processing/deduplication_script_dedup_create_all_contig_clusters.py"


rule save_unmapped_reads_from_bam:
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam",
    output:
        bam=temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unmapped_reads.bam"
        ),
        # needs to be called .unsorted.bam otherwise snakemake had problems with unambigous names
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unmapped_reads.log",
    threads: 2
    params:
        extra="-b -f 4",  # optional params string
    message:
        "Converting SAM to BAM for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


# Rule: Split BAM file into contig clusters
rule dedup_split_bam_into_clusters_by_contig_cluster:
    input:
        # the wrapper passes input[0] to samtools, so the BAM must stay first
        bam="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam",
        bai="{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam.bai",
    output:
        bam=temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{cluster}.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_{cluster}.bam.log",
    threads: 2
    params:
        # -M uses the index to read only this cluster's contigs instead of scanning the whole BAM
        extra="-M -L {species}/processed/reference_module/{reference}/dedup_cluster/{individual}/clusters/cluster_{cluster}.bed",
        region="",  # optional region string
    message:
        "Splitting BAM file {input.bam} into cluster {wildcards.cluster} for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


# Rule: Index split cluster BAM file
rule dedup_index_split_cluster_bam:
    input:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{cluster}.bam",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{cluster}.bam.bai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{cluster}.bam.bai.log",
    threads: 2
    params:
        extra="",  # optional params string
    message:
        "Indexing split BAM file for cluster {wildcards.cluster} for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"


# Rule: Deduplicate BAM file for each contig cluster
rule dedup_deduplicate_bam_cluster:
    input:
        bam="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{cluster}.bam",
        bai="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{cluster}.bam.bai",
    output:
        dedup_folder=directory(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{cluster}/"
        ),
        dedup_bam=temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{cluster}/{individual}_{reference}_cluster_{cluster}_rmdup.bam"
        ),
        dedup_hist="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{cluster}/{individual}_{reference}_cluster_{cluster}.hist",
        dedup_json="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{cluster}/{individual}_{reference}_cluster_{cluster}.dedup.json",
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{cluster}.dedup.log",
    conda:
        "../../../envs/dedup.yaml"
    resources:
        mem_mb=_setting(
            "reference_module", "deduplication", "settings", "mem_mb", default=20000
        ),
    params:
        mem_mb=_setting(
            "reference_module", "deduplication", "settings", "mem_mb", default=20000
        ),
    message:
        "Deduplicating BAM file for {input.bam} using dedup for individual {wildcards.individual} in species {wildcards.species}"
    shell:
        """
        mkdir -p "{output.dedup_folder}"
        dedup -Xms{params.mem_mb}m -Xmx{params.mem_mb}m --input "{input.bam}" --merged --output "{output.dedup_folder}" >"{log}" 2>&1
        """


# Rule: Merge deduplicated BAM files
rule dedup_merge_bam_clusters:
    input:
        dedup_merge_split_bams_input,
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted_dedupped.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted_dedupped.log",
    threads: 8
    params:
        extra="",  # optional additional parameters as string
    message:
        "Merging deduplicated BAM files for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/merge"


# Rule: Sort BAM file
rule sort_mapped_dedupped_reads_bam:
    # 3 Sort BAM
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted_dedupped.bam",
    output:
        _DEDUP_BAM if _KEEP_DEDUP_BAM else temp(_DEDUP_BAM),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_bam.log",
    threads: 10
    message:
        "Sorting deduplicated BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/sort"


# Rule: Index BAM file
rule dedup_index_dedupped_bam:
    # 4 Index BAM
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam",
    output:
        _DEDUP_BAM_BAI if _KEEP_DEDUP_BAM else temp(_DEDUP_BAM_BAI),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam.bai.log",
    threads: 5
    params:
        extra="",  # optional params string
    message:
        "Indexing deduplicated BAM file for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"


# Rule: Merge DeDup JSON files
rule dedup_merge_cluster_jsons:
    input:
        dedup_merge_split_jsons_input,
    output:
        json="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/dedup/{individual}_{reference}_final.dedup.json",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/dedup/{individual}_{reference}_final.dedup.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Merging DeDup JSON files for individual {wildcards.individual} in species {wildcards.species}"
    script:
        "../../../scripts/reference_module/processing/deduplication_script_dedup_merge_cluster_jsons.py"

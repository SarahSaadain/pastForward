####################################################
# Snakemake rules
####################################################


# Rule: Extract contig names from reference FAI
# Rule: Extract contigs as BED (full-length intervals) from reference FAI
rule dedup_extract_contigs_from_reference_fai:
    input:
        fai="{species}/processed/reference_module/{reference}/reference/{reference}.fa.fai",
    output:
        bed=temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/contigs.bed"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/contigs.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Extracting full-length contig BED from FAI for {wildcards.species} / {wildcards.reference}"
    shell:
        """
        awk '{{print $1 "\t0\t" $2}}' "{input.fai}" >"{output.bed}" 2>"{log}"
        """


# Checkpoint: Create all contig clusters for deduplication
checkpoint dedup_create_all_contig_clusters:
    input:
        contigs="{species}/processed/reference_module/{reference}/dedup_cluster/contigs.bed",
    output:
        cluster_folder=directory(
            "{species}/processed/reference_module/{reference}/dedup_cluster/clusters"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/dedup_create_all_contig_clusters.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        cores=workflow.cores,
        min_contigs_per_cluster=config.get("pipeline", {})
        .get("reference_module", {})
        .get("deduplication", {})
        .get("settings", {})
        .get("min_contigs_per_cluster", 1),
        max_contigs_per_cluster=config.get("pipeline", {})
        .get("reference_module", {})
        .get("deduplication", {})
        .get("settings", {})
        .get("max_contigs_per_cluster", 500),
    message:
        "Creating contig clusters for deduplication for species {wildcards.species} and reference {wildcards.reference}"
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
        "v9.3.0/bio/samtools/view"


# Rule: Split BAM file into contig clusters
rule dedup_split_bam_into_clusters_by_contig_cluster:
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam",
    output:
        bam=temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{start}_{end}.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_{start}_{end}.bam.log",
    threads: 2
    params:
        extra="-L {species}/processed/reference_module/{reference}/dedup_cluster/clusters/cluster_{start}_{end}.bed",
        region="",  # optional region string
    message:
        "Splitting BAM file {input} into cluster {wildcards.start}-{wildcards.end} for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        "v9.3.0/bio/samtools/view"


# Rule: Index split cluster BAM file
rule dedup_index_split_cluster_bam:
    input:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{start}_{end}.bam",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{start}_{end}.bam.bai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{start}_{end}.bam.bai.log",
    threads: 2
    params:
        extra="",  # optional params string
    message:
        "Indexing split BAM file for cluster {wildcards.start}-{wildcards.end} for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        "v9.3.0/bio/samtools/index"


# Rule: Deduplicate BAM file for each contig cluster
rule dedup_deduplicate_bam_cluster:
    input:
        bam="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{start}_{end}.bam",
        bai="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/split_cluster/{individual}_{reference}_cluster_{start}_{end}.bam.bai",
    output:
        dedup_folder=directory(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{start}_{end}/"
        ),
        dedup_bam=temp(
            "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{start}_{end}/{individual}_{reference}_cluster_{start}_{end}_rmdup.bam"
        ),
        dedup_hist="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{start}_{end}/{individual}_{reference}_cluster_{start}_{end}.hist",
        dedup_json="{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{start}_{end}/{individual}_{reference}_cluster_{start}_{end}.dedup.json",
    log:
        "{species}/processed/reference_module/{reference}/dedup_cluster/{individual}/dedup_{start}_{end}.dedup.log",
    conda:
        "../../../envs/dedup.yaml"
    resources:
        mem_mb=config.get("pipeline", {})
        .get("reference_module", {})
        .get("deduplication", {})
        .get("settings", {})
        .get("mem_mb", 20000),
    params:
        mem_mb=config.get("pipeline", {})
        .get("reference_module", {})
        .get("deduplication", {})
        .get("settings", {})
        .get("mem_mb", 20000),
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
        "v9.3.0/bio/samtools/merge"


# Rule: Sort BAM file
rule sort_mapped_dedupped_reads_bam:
    # 3 Sort BAM
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_unsorted_dedupped.bam",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_bam.log",
    threads: 10
    message:
        "Sorting deduplicated BAM file for {input}"
    wrapper:
        "v9.3.0/bio/samtools/sort"


# Rule: Index BAM file
rule dedup_index_dedupped_bam:
    # 4 Index BAM
    input:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam",
    output:
        temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam.bai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped.bam.bai.log",
    threads: 5
    params:
        extra="",  # optional params string
    message:
        "Indexing deduplicated BAM file for {input}"
    wrapper:
        "v9.3.0/bio/samtools/index"


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

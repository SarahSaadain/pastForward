####################################################
# Snakemake rules
####################################################


# mapDamage -n: 0 (default) = all reads, below 1 = fraction of reads, 1 or more = number of reads.
# It only thins the reads used for the damage tables and the model. Rescaling still covers every read.
# _mapdamage_extra (common.smk): rescale_seqlength (--seq-length), rescale_length_5p / _3p (--rescale-length-5p/-3p): always
# passed. Defaults: 12 bases, rescale lengths follow seq-length (unset or null = default; a rescale length of 0 is passed on).
_RESCALE_SPLIT = "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/split/{individual}_{reference}_chunk_{chunk}"


# Rule: Analyze DNA damage using mapDamage2 (damage tables, plots and the rescaling model).
# The BAM is rescaled afterwards in parallel chunks (rules below), so this rule writes no BAM.
rule analyze_mapdamage_and_rescale_bam:
    input:
        bam=_mapdamage_input_bam,
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        directory=directory(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/"
        ),
        GtoA3p="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.3pGtoA_freq.txt",
        CtoT5p="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.5pCtoT_freq.txt",
        dnacomp=temp(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.dnacomp.txt"
        ),
        lg_dist="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.lgdistribution.txt",
        misinc=temp(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.misincorporation.txt"
        ),
        plot_misinc="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Fragmisincorporation_plot.pdf",
        plot_len="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Length_plot.pdf",
        stats_ref="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.dnacomp_genome.csv",
        stats_prob="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_correct_prob.csv",
        stats_hist="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_hist.pdf",
        stats_iter="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_iter.csv",
        stats_summ="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_iter_summ_stat.csv",
        stats_plot_freq="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_post_pred.pdf",
        stats_plot_trace="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_trace.pdf",
        log="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Runtime_log.txt",
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}.rule.log",
    params:
        # optional parameters for mapdamage2 (except -i, -r, -d, --rescale); no bam output, so the wrapper adds no --rescale
        extra=_mapdamage_extra(),
    message:
        "Analyze damage and rescale {input.bam}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/mapdamage2"


# Rule: Cut the input BAM into one chunk per dedup contig cluster (whole contigs, balanced by
# reads). mapDamage rescales each read on its own, so per-chunk rescaling plus a merge gives the
# same reads as one full rescale, only in parallel.
rule rescale_split_bam_by_contig_cluster:
    input:
        # the wrapper passes input[0] to samtools, so the BAM must stay first
        bam=_mapdamage_input_bam,
        bai=lambda wildcards: _mapdamage_input_bam(wildcards) + ".bai",
    output:
        bam=temp(f"{_RESCALE_SPLIT}.bam"),
    log:
        f"{_RESCALE_SPLIT}.bam.log",
    wildcard_constraints:
        chunk=r"\d+",
    threads: 2
    params:
        # -M uses the index to read only this cluster's contigs instead of scanning the whole BAM
        # the cluster files exist: rescale_merge_chunks_input only asks for chunks after the checkpoint ran
        extra="-M -L {species}/processed/reference_module/{reference}/dedup_cluster/{individual}/clusters/cluster_{chunk}.bed",
        region="",
    message:
        "Splitting {input.bam} into rescale chunk {wildcards.chunk}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


# Rule: Reads without a contig ('*'). Not -f 4: unmapped reads with a mapped mate sit on the
# mate's contig and are already in that cluster's chunk.
rule rescale_split_bam_unplaced_reads:
    input:
        bam=_mapdamage_input_bam,
        bai=lambda wildcards: _mapdamage_input_bam(wildcards) + ".bai",
    output:
        bam=temp(_RESCALE_SPLIT.replace("{chunk}", "unplaced") + ".bam"),
    log:
        _RESCALE_SPLIT.replace("{chunk}", "unplaced") + ".bam.log",
    threads: 2
    params:
        extra="",
        region="'*'",
    message:
        "Extracting reads without a contig from {input.bam} for rescaling"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


# Rule: Rescale one chunk with the model from analyze_mapdamage_and_rescale_bam. With only a bam
# output and stats_prob as input, the wrapper runs mapDamage --rescale-only on that model.
rule rescale_bam_chunk:
    input:
        bam=f"{_RESCALE_SPLIT}.bam",
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        stats_prob="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_correct_prob.csv",
    output:
        bam=temp(f"{_RESCALE_SPLIT}_rescaled.bam"),
    log:
        f"{_RESCALE_SPLIT}_rescaled.log",
    wildcard_constraints:
        chunk=r"\d+|unplaced",
    params:
        # --seq-length and the rescale lengths must match the model run
        extra=_mapdamage_extra(),
    message:
        "Rescaling chunk {wildcards.chunk} of {wildcards.individual} with mapDamage"
    wrapper:
        f"{WRAPPER_VERSION}/bio/mapdamage2"


# Rule: Merge the rescaled chunks into the BAM the sort step reads
rule rescale_merge_bam_chunks:
    input:
        rescale_merge_chunks_input,
    output:
        temp(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}_merge.log",
    threads: 8
    params:
        extra="",
    message:
        "Merging rescaled chunks for individual {wildcards.individual} in species {wildcards.species}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/merge"


# Rule: Keep the two large mapDamage tables only as .gz. No rule reads them, so the
# plain .txt files are temp() in analyze_mapdamage_and_rescale_bam.
rule compress_mapdamage_tables:
    input:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.{table}.txt",
    output:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.{table}.txt.gz",
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}.{table}.compress.log",
    wildcard_constraints:
        table="misincorporation|dnacomp",
    conda:
        "../../../envs/pigz.yaml"
    threads: 2
    message:
        "Compressing mapDamage {wildcards.table} table for {wildcards.individual}"
    shell:
        'pigz -p {threads} -c "{input}" > "{output}" 2> "{log}"'


# Rule: Sort rescaled BAM file
# 3 Sort BAM
rule sort_rescaled_bam:
    input:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.bam",
    output:
        temp(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam"
        ),
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}_sorted.bam.log",
    threads: 10
    message:
        "Sort rescaled BAM for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/sort"


# Rule: Index rescaled BAM file
# 4 Index BAM
rule index_rescaled_bam:
    input:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam",
    output:
        temp(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam.bai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}_sorted.bam.bai.log",
    threads: 10
    message:
        "Index rescaled BAM for {input}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/index"


# keep_bam: the rescaled BAM and its index stay in processed/ (no temp) so a later step never
# redoes rescaling, and the keep_bam rule (map_reads_to_reference.smk) adds a copy in results/.
_KEEP_RESCALED_BAM = _setting(
    "reference_module", "damage_rescaling", "settings", "keep_bam", default=False
)
_RESCALED_BAM = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled.bam"
_RESCALED_BAM_BAI = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled.bam.bai"


# Rule: Move rescaled BAM and index to processed directory
rule move_rescaled_bam:
    input:
        sorted_bam="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam",
        bam_index="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam.bai",
    output:
        sorted_bam=_RESCALED_BAM if _KEEP_RESCALED_BAM else temp(_RESCALED_BAM),
        bam_index=(_RESCALED_BAM_BAI if _KEEP_RESCALED_BAM else temp(_RESCALED_BAM_BAI)),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled_move.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Move rescaled BAM and index to processed directory for {input.sorted_bam}"
    shell:
        """
        ln -fL "{input.sorted_bam}" "{output.sorted_bam}" >"{log}" 2>&1 || cp "{input.sorted_bam}" "{output.sorted_bam}" >>"{log}" 2>&1
        cp "{input.bam_index}" "{output.bam_index}" >>"{log}" 2>&1
        """

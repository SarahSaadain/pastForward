####################################################
# Snakemake rules
####################################################


# mapDamage -n: 0 (default) = all reads, below 1 = fraction of reads, 1 or more = number of reads.
# It only thins the reads used for the damage tables and the model. Rescaling still covers every read.
# _mapdamage_extra (common.smk): rescale_seqlength (--seq-length), rescale_length_5p / _3p (--rescale-length-5p/-3p): always
# passed. Defaults: 12 bases, rescale lengths follow seq-length (unset or null = default; a rescale length of 0 is passed on).
_RESCALE_SPLIT = "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/split/{individual}_{reference}_chunk_{chunk}"
_MAPPED_SORTED_BAM = "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted.bam"
_MD = "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}"
_MD_REF = "{species}/processed/reference_module/{reference}/reference/{reference}.fa"
_MD_LOG = "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}"
# Keys are the mapdamage2 wrapper's output tags, which map them to mapDamage's own file names.
_MD_TABLES = {
    "misinc": f"{_MD}.misincorporation.txt",
    "dnacomp": f"{_MD}.dnacomp.txt",
    "lg_dist": f"{_MD}.lgdistribution.txt",
}
_MD_PLOTS = {
    "GtoA3p": f"{_MD}.3pGtoA_freq.txt",
    "CtoT5p": f"{_MD}.5pCtoT_freq.txt",
    "plot_misinc": f"{_MD}.Fragmisincorporation_plot.pdf",
    "plot_len": f"{_MD}.Length_plot.pdf",
}
_MD_STATS = {
    "stats_ref": f"{_MD}.dnacomp_genome.csv",
    "stats_prob": f"{_MD}.Stats_out_MCMC_correct_prob.csv",
    "stats_hist": f"{_MD}.Stats_out_MCMC_hist.pdf",
    "stats_iter": f"{_MD}.Stats_out_MCMC_iter.csv",
    "stats_summ": f"{_MD}.Stats_out_MCMC_iter_summ_stat.csv",
    "stats_plot_freq": f"{_MD}.Stats_out_MCMC_post_pred.pdf",
    "stats_plot_trace": f"{_MD}.Stats_out_MCMC_trace.pdf",
    "log": f"{_MD}.Runtime_log.txt",
}
# The two large tables are kept only as .gz (compress_mapdamage_tables), so the .txt files are temp().
_MD_TABLES_OUT = {
    tag: temp(path) if tag in ("misinc", "dnacomp") else path
    for tag, path in _MD_TABLES.items()
}


if _mapdamage_split_counting():

    # Rule: Count the damage tables of one chunk (one DeDup cluster, or one contig cluster of
    # the sorted BAM with dedup off). The counts are per read, so the chunk sums equal one full run.
    rule mapdamage_count_chunk:
        input:
            bam=_mapdamage_chunk_bam,
            ref=_MD_REF,
        output:
            misinc=temp(f"{_RESCALE_SPLIT}_counts/misincorporation.txt"),
            dnacomp=temp(f"{_RESCALE_SPLIT}_counts/dnacomp.txt"),
            lg_dist=temp(f"{_RESCALE_SPLIT}_counts/lgdistribution.txt"),
        log:
            f"{_RESCALE_SPLIT}_counts.log",
        wildcard_constraints:
            chunk=r"\d+",
        params:
            # only table outputs, so the wrapper adds no mode flag and --no-stats is passed here
            extra=f"--no-stats {_mapdamage_extra()}",
        message:
            "Counting damage tables for chunk {wildcards.chunk} of {wildcards.individual}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/mapdamage2"

    # Rule: Sum the chunk tables into the tables of the individual. Reads without a contig are
    # all unmapped and mapDamage counts no unmapped read, so the 'unplaced' chunk is not counted.
    # Reads are mapped single-end (merged), so no unmapped read sits on a mate's contig.
    rule mapdamage_combine_chunk_tables:
        input:
            mapdamage_chunk_tables_input,
        output:
            **_MD_TABLES_OUT,
        log:
            f"{_MD_LOG}.combine.log",
        conda:
            "../../../envs/python_and_r.yaml"
        message:
            "Summing mapDamage chunk tables for {wildcards.individual}"
        script:
            "../../../scripts/reference_module/processing/analyze_damage_script_combine_chunk_tables.py"

    # Rule: Damage plots and the 5' C>T / 3' G>A tables from the summed tables (--plot-only).
    rule mapdamage_plot:
        input:
            **_MD_TABLES,
            ref=_MD_REF,
        output:
            **_MD_PLOTS,
        log:
            f"{_MD_LOG}.plot.log",
        params:
            # the wrapper adds --no-stats for plot outputs; mapDamage accepts it with --plot-only
            extra=f"--plot-only {_mapdamage_extra()}",
        message:
            "Plotting damage for {wildcards.individual}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/mapdamage2"

    # Rule: Fit the damage model from the summed tables. Only stats outputs, so the wrapper
    # runs mapDamage --stats-only, with the input tables linked into its work folder.
    # The old rule name stays, so the profile entry, benchmarks and logs keep their names.
    rule analyze_mapdamage_and_rescale_bam:
        input:
            ref=_MD_REF,
            misinc=_MD_TABLES["misinc"],
            dnacomp=_MD_TABLES["dnacomp"],
            GtoA3p=_MD_PLOTS["GtoA3p"],
            CtoT5p=_MD_PLOTS["CtoT5p"],
        output:
            **_MD_STATS,
        log:
            f"{_MD_LOG}.rule.log",
        params:
            extra=_mapdamage_extra(),
        message:
            "Fitting the damage model for {wildcards.individual}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/mapdamage2"

else:

    # Rule: With downsample set, mapDamage takes its subset from the whole BAM, which a
    # per-chunk count cannot copy: one run makes the tables, plots and the model. No bam
    # output, so the wrapper adds no --rescale; the BAM is rescaled in chunks below.
    rule analyze_mapdamage_and_rescale_bam:
        input:
            bam=_mapdamage_input_bam,
            ref=_MD_REF,
        output:
            **_MD_TABLES_OUT,
            **_MD_PLOTS,
            **_MD_STATS,
        log:
            f"{_MD_LOG}.rule.log",
        params:
            # optional parameters for mapdamage2 (except -i, -r, -d, --rescale)
            extra=_mapdamage_extra(),
        message:
            "Analyze damage of {input.bam}"
        wrapper:
            f"{WRAPPER_VERSION}/bio/mapdamage2"


# Rule: Cut the mapDamage input BAM into one chunk per contig cluster (whole contigs, balanced
# by reads). Used with dedup off, or with dedup keep_bam (cut from the kept dedup BAM); otherwise
# the DeDup cluster BAMs are the chunks (_mapdamage_chunk_bam). mapDamage rescales each read on
# its own, so per-chunk rescaling plus a merge gives the same reads as one full rescale.
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
        # the cluster files exist: chunk inputs are only asked for after the checkpoint ran
        extra="-M -L {species}/processed/reference_module/{reference}/dedup_cluster/{individual}/clusters/cluster_{chunk}.bed",
        region="",
    message:
        "Splitting {input.bam} into rescale chunk {wildcards.chunk}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/samtools/view"


# Rule: Reads without a contig ('*'), taken from the sorted BAM. DeDup never sees them (no
# cluster holds them), so they are the same with dedup on or off. Not -f 4: unmapped reads
# with a mapped mate sit on the mate's contig and are already in that cluster's chunk.
rule rescale_split_bam_unplaced_reads:
    input:
        bam=_MAPPED_SORTED_BAM,
        bai=f"{_MAPPED_SORTED_BAM}.bai",
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
        bam=_mapdamage_chunk_bam,
        ref=_MD_REF,
        stats_prob=_MD_STATS["stats_prob"],
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
# plain .txt files are temp() in the rule that makes them.
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

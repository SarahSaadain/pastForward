####################################################
# Snakemake rules
####################################################


# Rule: Analyze DNA damage and rescale BAM using mapDamage2
rule analyze_mapdamage_and_rescale_bam:
    input:
        bam=lambda wildcards: (
            f"{wildcards.species}/processed/reference_module/{wildcards.reference}/mapped/{wildcards.individual}_{wildcards.reference}_sorted_dedupped.bam"
            if config.get("pipeline", {})
            .get("reference_module", {})
            .get("deduplication", {})
            .get("execute", True)
            == True
            else f"{wildcards.species}/processed/reference_module/{wildcards.reference}/mapped/{wildcards.individual}_{wildcards.reference}_sorted.bam"
        ),
        ref="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
    output:
        directory=directory(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/"
        ),
        GtoA3p="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.3pGtoA_freq.txt",
        CtoT5p="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.5pCtoT_freq.txt",
        dnacomp="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.dnacomp.txt",
        lg_dist="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.lgdistribution.txt",
        misinc="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.misincorporation.txt",
        plot_misinc="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Fragmisincorporation_plot.pdf",
        plot_len="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Length_plot.pdf",
        stats_ref="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.dnacomp_genome.csv",
        stats_prob="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_correct_prob.csv",
        stats_hist="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_hist.pdf",
        stats_iter="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_iter.csv",
        stats_summ="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_iter_summ_stat.csv",
        stats_plot_freq="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_post_pred.pdf",
        stats_plot_trace="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Stats_out_MCMC_trace.pdf",
        bam=temp(
            "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.bam"
        ),
        log="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.Runtime_log.txt",
    log:
        "{species}/processed/reference_module/{reference}/analytics/{individual}/mapdamage/{individual}_{reference}.rule.log",
    params:
        extra="",  # optional parameters for mapdamage2 (except -i, -r, -d, --rescale)
    message:
        "Analyze damage and rescale {input.bam}"
    wrapper:
        f"{WRAPPER_VERSION}/bio/mapdamage2"


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


# Rule: Move rescaled BAM and index to processed directory
rule move_rescaled_bam:
    input:
        sorted_bam="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam",
        bam_index="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}_sorted.bam.bai",
    output:
        sorted_bam=temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled.bam"
        ),
        bam_index=temp(
            "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled.bam.bai"
        ),
    log:
        "{species}/processed/reference_module/{reference}/mapped/{individual}_{reference}_sorted_dedupped_rescaled_move.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Move rescaled BAM and index to processed directory for {input.sorted_bam}"
    shell:
        """
        cp "{input.sorted_bam}" "{output.sorted_bam}" >"{log}" 2>&1
        cp "{input.bam_index}" "{output.bam_index}" >>"{log}" 2>&1
        """

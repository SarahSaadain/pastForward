####################################################
# Per-individual SNP divergence against the reference.
#
# The statistic is cohort-relative: each individual's divergence rate is scored
# against the median of the other individuals mapped to the same reference. A
# clear outlier points at a wrong reference genome, cross-species contamination,
# or a mislabeled individual.
#
# Two tiers, selected with analysis.settings.snp_divergence_method:
#   samtools_stats (the default) reuses the per-individual samtools stats file an
#     existing rule already writes, so it costs no extra runtime and pulls in no
#     extra dependency. It gives no heterozygous-call rate.
#   bcftools calls SNPs per individual on a fixed, shared, budget-capped slice of
#     the reference. It adds the heterozygous-call rate at real but bounded cost.
#   both runs the two side by side, so the cheap number and the called number can be
#     compared on the same cohort.
#
# Every species-level output carries the method in its filename. Two methods can
# therefore coexist, and a file left over from an earlier method is never mistaken
# for the current one when the config changes.
####################################################

_snp_divergence_settings = (
    config.get("pipeline", {})
    .get("reference_module", {})
    .get("analysis", {})
    .get("settings", {})
)

_SNP_DIVERGENCE_ENABLED = (
    _snp_divergence_settings.get("snp_divergence_check", False) == True
)
_SNP_DIVERGENCE_METHOD = _snp_divergence_settings.get(
    "snp_divergence_method", "samtools_stats"
)
_SNP_DIVERGENCE_OUTLIER_ZSCORE = float(
    _snp_divergence_settings.get("snp_divergence_outlier_zscore", 3.5)
)
_SNP_DIVERGENCE_TARGET_BASES = int(
    _snp_divergence_settings.get("snp_divergence_target_bases", 10000000)
)
_SNP_DIVERGENCE_MIN_CONTIG_LENGTH = int(
    _snp_divergence_settings.get("snp_divergence_min_contig_length", 10000)
)
_SNP_DIVERGENCE_MIN_DEPTH = int(
    _snp_divergence_settings.get("snp_divergence_min_depth", 3)
)
_SNP_DIVERGENCE_MAX_DEPTH = int(
    _snp_divergence_settings.get("snp_divergence_max_depth", 50)
)
_SNP_DIVERGENCE_MIN_MAPPING_QUALITY = int(
    _snp_divergence_settings.get("snp_divergence_min_mapping_quality", 30)
)
_SNP_DIVERGENCE_MIN_BASE_QUALITY = int(
    _snp_divergence_settings.get("snp_divergence_min_base_quality", 30)
)
_SNP_DIVERGENCE_MIN_CALLABLE_BASES = int(
    _snp_divergence_settings.get("snp_divergence_min_callable_bases", 100000)
)

if _SNP_DIVERGENCE_ENABLED and _SNP_DIVERGENCE_METHOD not in (
    "samtools_stats",
    "bcftools",
    "both",
):
    raise ConfigValidationError(
        f"Unknown snp_divergence_method '{_SNP_DIVERGENCE_METHOD}'. "
        "Valid options are 'samtools_stats', 'bcftools' and 'both'."
    )

# A base budget of 0 means call across the whole reference, so no region BED is
# built and bcftools mpileup runs without --regions-file.
if _SNP_DIVERGENCE_TARGET_BASES > 0:
    _SNP_DIVERGENCE_REGIONS = [
        "{species}/processed/reference_module/{reference}/snp_divergence/{reference}_regions.bed"
    ]
else:
    _SNP_DIVERGENCE_REGIONS = []

# Which per-individual file the species-level combine rule reads, per method. The
# method is a wildcard of the combine rule, so Snakemake resolves backwards from the
# requested output to whichever per-individual rules that method needs.
_SNP_DIVERGENCE_INDIVIDUAL_STATS = {
    "bcftools": "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/snp_divergence/{individual}_{reference}.bcftools_stats.txt",
    "samtools_stats": "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats",
}

_SNP_DIVERGENCE_INDIVIDUAL_CALLABLE = "{species}/processed/reference_module/{reference}/snp_divergence/{individual}/{individual}_{reference}_callable_bases.txt"


####################################################
# Snakemake rules
####################################################


# Rule: Pick the shared slice of the reference to call SNPs on (bcftools tier)
rule build_snp_divergence_regions:
    input:
        fai="{species}/processed/reference_module/{reference}/reference/{reference}.fa.fai",
    output:
        bed="{species}/processed/reference_module/{reference}/snp_divergence/{reference}_regions.bed",
    log:
        "{species}/processed/reference_module/{reference}/snp_divergence/{reference}_regions.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        target_bases=_SNP_DIVERGENCE_TARGET_BASES,
        min_contig_length=_SNP_DIVERGENCE_MIN_CONTIG_LENGTH,
    message:
        "Selecting SNP divergence regions for {wildcards.species} / {wildcards.reference}"
    script:
        "../../../scripts/reference_module/analytics/statistics/build_snp_divergence_regions.py"


# Rule: Call SNPs for one individual against the reference (bcftools tier)
rule call_snps_for_divergence:
    input:
        bam="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam",
        bai="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam.bai",
        reference="{species}/processed/reference_module/{reference}/reference/{reference}.fa",
        regions=_SNP_DIVERGENCE_REGIONS,
    output:
        vcf="{species}/processed/reference_module/{reference}/snp_divergence/{individual}/{individual}_{reference}_calls.vcf.gz",
    log:
        "{species}/processed/reference_module/{reference}/snp_divergence/{individual}/{individual}_{reference}_calls.log",
    conda:
        "../../../envs/bcftools.yaml"
    params:
        # --regions-file uses the BAM index for random access, so only the budgeted
        # slice is read. Dropped entirely when the whole reference is requested.
        regions_arg=lambda wildcards, input: (
            f"--regions-file {input.regions}" if input.regions else ""
        ),
        max_depth=_SNP_DIVERGENCE_MAX_DEPTH,
        min_depth=_SNP_DIVERGENCE_MIN_DEPTH,
        min_mapping_quality=_SNP_DIVERGENCE_MIN_MAPPING_QUALITY,
        min_base_quality=_SNP_DIVERGENCE_MIN_BASE_QUALITY,
    message:
        "Calling SNPs for SNP divergence check on {input.bam}"
    shell:
        # Single threaded on purpose. bcftools --threads only parallelizes BGZF
        # compression, and Snakemake already runs individuals side by side.
        """
        bcftools mpileup \
            --fasta-ref "{input.reference}" \
            {params.regions_arg} \
            --skip-indels \
            --max-depth {params.max_depth} \
            --min-MQ {params.min_mapping_quality} \
            --min-BQ {params.min_base_quality} \
            --annotate FORMAT/DP \
            --output-type u \
            "{input.bam}" 2>"{log}" \
            | bcftools call --multiallelic-caller --variants-only --output-type u 2>>"{log}" \
            | bcftools view \
                --include 'FORMAT/DP>={params.min_depth}' \
                --output-type z \
                -o "{output.vcf}" 2>>"{log}"
        """


# Rule: Count callable bases for one individual (bcftools tier)
rule count_snp_divergence_callable_bases:
    input:
        bam="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam",
        bai="{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam.bai",
        regions=_SNP_DIVERGENCE_REGIONS,
    output:
        txt="{species}/processed/reference_module/{reference}/snp_divergence/{individual}/{individual}_{reference}_callable_bases.txt",
    log:
        "{species}/processed/reference_module/{reference}/snp_divergence/{individual}/{individual}_{reference}_callable_bases.log",
    conda:
        "../../../envs/samtools.yaml"
    params:
        # The denominator has to be measured on the same regions and with the same
        # quality thresholds as the numerator, otherwise the rate is not comparable
        # across the cohort.
        regions_arg=lambda wildcards, input: (
            f"-b {input.regions}" if input.regions else ""
        ),
        min_depth=_SNP_DIVERGENCE_MIN_DEPTH,
        min_mapping_quality=_SNP_DIVERGENCE_MIN_MAPPING_QUALITY,
        min_base_quality=_SNP_DIVERGENCE_MIN_BASE_QUALITY,
    message:
        "Counting callable bases for SNP divergence check on {input.bam}"
    shell:
        """
        samtools depth \
            {params.regions_arg} \
            --min-MQ {params.min_mapping_quality} \
            --min-BQ {params.min_base_quality} \
            "{input.bam}" 2>"{log}" \
            | awk -v min_depth={params.min_depth} '$3 >= min_depth {{ callable_bases++ }} END {{ print callable_bases + 0 }}' >"{output.txt}"
        """


# Rule: Summarise one individual's calls with bcftools stats (bcftools tier)
rule compute_snp_divergence_stats:
    input:
        vcf="{species}/processed/reference_module/{reference}/snp_divergence/{individual}/{individual}_{reference}_calls.vcf.gz",
    output:
        stats="{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/snp_divergence/{individual}_{reference}.bcftools_stats.txt",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/snp_divergence/{individual}_{reference}.bcftools_stats.log",
    conda:
        "../../../envs/bcftools.yaml"
    message:
        "Computing bcftools stats for SNP divergence check on {input.vcf}"
    shell:
        """
        bcftools stats --samples - "{input.vcf}" >"{output.stats}" 2>"{log}"
        """


# Rule: Combine per-individual divergence and flag cohort outliers (both tiers)
rule combine_snp_divergence:
    input:
        stats=lambda wildcards: expand(
            _SNP_DIVERGENCE_INDIVIDUAL_STATS[wildcards.method],
            species=wildcards.species,
            reference=wildcards.reference,
            individual=get_individuals_for_species(wildcards.species),
        ),
        # Only the bcftools method measures its own denominator. The samtools_stats
        # method takes it from the same stats file as the numerator.
        callable_bases=lambda wildcards: (
            expand(
                _SNP_DIVERGENCE_INDIVIDUAL_CALLABLE,
                species=wildcards.species,
                reference=wildcards.reference,
                individual=get_individuals_for_species(wildcards.species),
            )
            if wildcards.method == "bcftools"
            else []
        ),
    output:
        combined="{species}/results/reference_module/{reference}/analytics/species_level/{species}/snp_divergence/{reference}_combined_snp_divergence_{method}.csv",
        detailed="{species}/results/reference_module/{reference}/analytics/species_level/{species}/snp_divergence/{reference}_combined_snp_divergence_{method}_detailed.csv",
    log:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/snp_divergence/{reference}_combined_snp_divergence_{method}.log",
    # Reference names may contain underscores, so the method has to be pinned down
    # for Snakemake to split {reference}_combined_snp_divergence_{method} correctly.
    wildcard_constraints:
        method="samtools_stats|bcftools",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        # Expanded from the same individual list and in the same order as the
        # inputs above, so the combine script can pair files to individuals
        # without parsing IDs back out of filenames.
        individuals=lambda wildcards: get_individuals_for_species(wildcards.species),
        method=lambda wildcards: wildcards.method,
        outlier_zscore=_SNP_DIVERGENCE_OUTLIER_ZSCORE,
        min_callable_bases=_SNP_DIVERGENCE_MIN_CALLABLE_BASES,
    message:
        "Combining {wildcards.method} SNP divergence results for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/analytics/statistics/combine_snp_divergence.py"

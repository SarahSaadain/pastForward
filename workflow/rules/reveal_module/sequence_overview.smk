####################################################
# Module-level settings for rules
####################################################

_comp_execute = _setting(
    "reveal_module", "mapping", "settings", "competitive_mapping", default=False
)

####################################################
# Snakemake rules
####################################################


rule determine_visualization_of_individual_bam_to_so:
    input:
        bam="{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam",
        fasta=lambda wildcards: (
            f"{wildcards.species}/processed/reveal_module/{wildcards.feature_library}/library/{wildcards.feature_library}_and_scg.no_comp.suffixed.fasta"
            if _comp_execute
            else f"{wildcards.species}/processed/reveal_module/{wildcards.feature_library}/library/{wildcards.feature_library}_and_scg.suffixed.fasta"
        ),
    output:
        coverage=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_bam2so.log",
    conda:
        REVEAL_CONDA_ENV
    params:
        mapqth=lambda _: _setting(
            "reveal_module",
            "sequence_overview",
            "settings",
            "mapping_quality_threshold",
            default=5,
        ),
        mc_snp=lambda _: _setting(
            "reveal_module",
            "sequence_overview",
            "settings",
            "minimum_count_snp",
            default=5,
        ),
        mf_snp=lambda _: _setting(
            "reveal_module",
            "sequence_overview",
            "settings",
            "minimum_frequency_snp",
            default=0.1,
        ),
        mc_indel=lambda _: _setting(
            "reveal_module",
            "sequence_overview",
            "settings",
            "minimum_count_indel",
            default=3,
        ),
        mf_indel=lambda _: _setting(
            "reveal_module",
            "sequence_overview",
            "settings",
            "minimum_frequency_indel",
            default=0.01,
        ),
    message:
        "Determining REVEAL coverage for {wildcards.individual} of {wildcards.species} using bam2so."
    shell:
        """
        REVEAL bam2so \
            --infile "{input.bam}" \
            --fasta "{input.fasta}" \
            --outfile "{output.coverage}" \
            --mapqth {params.mapqth} \
            --mc-snp {params.mc_snp} \
            --mf-snp {params.mf_snp} \
            --mc-indel {params.mc_indel} \
            --mf-indel {params.mf_indel} \
            2>"{log}"
        """


rule compress_visualization_coverage_of_individual:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL coverage output for {wildcards.individual} of {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'

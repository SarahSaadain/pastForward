####################################################
# Snakemake rules
####################################################


rule compute_scg_stats_for_bam:
    input:
        bam="{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.bam",
        bai="{species}/processed/reveal_module/scg/reads_mapped/{individual}_scg_library.sorted.bam.bai",
    output:
        stats="{species}/processed/reveal_module/scg/stats/{individual}_scg_stats.json",
    log:
        "{species}/processed/reveal_module/scg/stats/{individual}_scg_stats.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Computing SCG coverage stats for {wildcards.individual} of {wildcards.species}"
    script:
        "../../../scripts/reveal_module/scg/compute_scg_stats_for_bam.py"


# Ranking TSV/JSON go to results/ — they are primary outputs the user cares about
rule determine_scg_ranking:
    input:
        stats=lambda wildcards: expand(
            "{species}/processed/reveal_module/scg/stats/{individual}_scg_stats.json",
            species=wildcards.species,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        ranked_tsv="{species}/results/reveal_module/scg/{species}_scg_ranked.tsv",
        ranked_json="{species}/results/reveal_module/scg/{species}_scg_ranked.json",
    log:
        "{species}/results/reveal_module/scg/{species}_scg_ranked.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Ranking SCGs across individuals for {wildcards.species}"
    script:
        "../../../scripts/reveal_module/scg/determine_scg_ranking.py"


# Intermediate selection files stay in processed/
rule filter_top_scgs:
    input:
        ranked_scgs="{species}/results/reveal_module/scg/{species}_scg_ranked.tsv",
    output:
        relevant_contigs="{species}/processed/reveal_module/scg/{species}_relevant_scg.txt",
        relevant_contigs_bed="{species}/processed/reveal_module/scg/{species}_relevant_scg.bed",
    log:
        "{species}/processed/reveal_module/scg/{species}_relevant_scg.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        num_top_scgs=lambda wildcards: (
            _setting(
                "reveal_module", "scg_selector", "settings", "num_top_scgs", default=20
            )
        ),
    message:
        "Selecting top {params.num_top_scgs} SCGs for {wildcards.species}"
    shell:
        """
        awk 'NR>1 && NR<={params.num_top_scgs}+1 {{print $1}}' "{input.ranked_scgs}" | sort -u >"{output.relevant_contigs}" 2>"{log}"
        awk '{{print $1 "\t0\t1000000000"}}' "{output.relevant_contigs}" | sort -u >"{output.relevant_contigs_bed}" 2>>"{log}"
        """


# The filtered FASTA is a primary output the user cares about, goes to results/ —
# it also feeds into the REVEAL prepare_libraries pipeline
rule filter_scg_fasta:
    input:
        fasta="{species}/processed/reveal_module/scg/{species}_scg_library.fasta",
        id_list="{species}/processed/reveal_module/scg/{species}_relevant_scg.txt",
    output:
        filtered="{species}/results/reveal_module/scg/{species}_relevant_scg.fasta",
    log:
        "{species}/results/reveal_module/scg/{species}_relevant_scg_fasta.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Filtering SCG FASTA to top-ranked sequences for {wildcards.species}"
    script:
        "../../../scripts/reveal_module/scg/filter_scg_fasta.py"

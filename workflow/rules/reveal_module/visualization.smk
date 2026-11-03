####################################################
# Snakemake rules
####################################################


rule prepare_visualization_plotables_of_individual:
    input:
        coverage="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv.gz",
    output:
        plotable=temp(
            directory(
                "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable"
            )
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable.log",
    conda:
        REVEAL_CONDA_ENV
    params:
        bin_size=lambda _: _setting(
            "reveal_module",
            "visualization",
            "settings",
            "visualization_bin_size",
            default="target:5000",
        ),
    message:
        "Preparing REVEAL visualization for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        REVEAL so2plotable \
            --so "{input.coverage}" \
            --outdir "{output.plotable}" \
            --bin-size "{params.bin_size}" \
            --seq-ids ALL \
            --sample-id "{wildcards.individual}" >"{log}" 2>&1
        """


rule run_visualization_plots_of_individual:
    input:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable",
    output:
        directory(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plots"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plots.log",
    conda:
        REVEAL_CONDA_ENV
    threads: 15
    params:
        log_threshhold=lambda _: _setting(
            "reveal_module",
            "visualization",
            "settings",
            "y_axis_log_scale_threshold_individual",
            default=25,
        ),
    message:
        "Running REVEAL visualization for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        REVEAL plot --folder "{input}" --outdir "{output}" --log {params.log_threshhold} --threads {threads} >"{log}" 2>&1
        """


rule run_visualization_plots_of_species:
    input:
        lambda wildcards: expand(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable",
            species=wildcards.species,
            feature_library=wildcards.feature_library,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        plots=directory(
            "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plots_facet"
        ),
        merged=temp(
            directory(
                "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plotables_facet"
            )
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plots_facet.log",
    conda:
        REVEAL_CONDA_ENV
    threads: 15
    params:
        log_threshhold=lambda _: _setting(
            "reveal_module",
            "visualization",
            "settings",
            "y_axis_log_scale_threshold_species",
            default=25,
        ),
    message:
        "Running REVEAL visualization for {wildcards.species}."
    shell:
        """
        REVEAL plot --folders {input} --outdir "{output.plots}" --merged-dir "{output.merged}" --log {params.log_threshhold} --threads {threads} >"{log}" 2>&1
        """


rule compress_visualization_plotable_of_individual:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable.tar.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL plotables of individual for {wildcards.individual} of {wildcards.species}"
    shell:
        'tar -c "{input.source}" | pigz -p {threads} > "{output.target}" 2> "{log}"'


rule compress_visualization_plotable_of_species:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plotables_facet",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plotables_facet.tar.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plotables_facet_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL plotables of species for {wildcards.species}"
    shell:
        'tar -c "{input.source}" | pigz -p {threads} > "{output.target}" 2> "{log}"'

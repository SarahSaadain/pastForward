####################################################
# Snakemake rules
####################################################


rule normalize_visualization_of_individual:
    input:
        coverage="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.tsv.gz",
    output:
        normalized=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv"
        ),
        exclusion_reason="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.exclusion_reason.txt",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.log",
    conda:
        REVEAL_CONDA_ENV
    params:
        end_distance=lambda _: config.get("pipeline", {})
        .get("reveal_module", {})
        .get("normalization", {})
        .get("settings", {})
        .get("end_distance", 100),
        exclude_quantile=lambda _: config.get("pipeline", {})
        .get("reveal_module", {})
        .get("normalization", {})
        .get("settings", {})
        .get("exclude_quantile", 25),
        skip_low_coverage=lambda _: config.get("pipeline", {})
        .get("reveal_module", {})
        .get("normalization", {})
        .get("settings", {})
        .get("skip_low_coverage_individuals", False),
    message:
        "Normalizing REVEAL coverage for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        set +e
        REVEAL normalize \
            --so "{input.coverage}" \
            --outfile "{output.normalized}" \
            --end-distance {params.end_distance} \
            --exclude-quantile {params.exclude_quantile} >"{log}" 2>&1
        rc=$?
        set -e

        if [ $rc -ne 0 ]; then
            if [ "{params.skip_low_coverage}" = "True" ]; then
                echo "$(tail -n 1 "{log}")" >"{output.exclusion_reason}"
                : >"{output.normalized}"
            else
                exit $rc
            fi
        else
            : >"{output.exclusion_reason}"
        fi
        """


rule compress_visualization_coverage_normalized_of_individual:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL normalized output for {wildcards.individual} of {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'

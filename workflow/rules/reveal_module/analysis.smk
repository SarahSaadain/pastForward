####################################################
# Snakemake rules
####################################################


rule estimate_visualization_of_individual:
    input:
        coverage="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.tsv.gz",
    output:
        estimation=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_estimation.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_estimation.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Estimating REVEAL coverage for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        REVEAL estimate --so "{input.coverage}" --outfile "{output.estimation}" >"{log}" 2>&1
        """


rule calculate_visualization_normalized_stats_of_individual:
    input:
        coverage="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv.gz",
        exclusion_reason="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.exclusion_reason.txt",
    output:
        stats="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.stats.tsv",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.stats.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Calculating normalized stats for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        if [ -s "{input.exclusion_reason}" ]; then
            echo "Skipping REVEAL covstats for {wildcards.individual}: excluded due to low coverage (see {input.exclusion_reason})" >"{log}"
            printf 'seqid\\tsampleid\\tseq_len\\tmedian_cov\\tmad_cov\\tcv_cov\\tmax_cov\\tfrac_low\\tn_snps\\tsnp_density\\tmedian_alt\\n' >"{output.stats}"
        else
            REVEAL covstats \
                --so "{input.coverage}" \
                --outfile "{output.stats}" \
                --sample-id "{wildcards.individual}" >"{log}" 2>&1
        fi
        """


rule calculate_visualization_snp_stats_of_individual:
    input:
        coverage="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv.gz",
    output:
        stats=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Calculating SNP stats for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        REVEAL snpstats \
            --so "{input.coverage}" \
            --outfile "{output.stats}" \
            --sample-id "{wildcards.individual}" >"{log}" 2>&1
        """


rule calculate_visualization_indel_stats_of_individual:
    input:
        coverage="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv.gz",
    output:
        stats=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Calculating indel stats for {wildcards.individual} of {wildcards.species}."
    shell:
        """
        REVEAL indelstats \
            --so "{input.coverage}" \
            --outfile "{output.stats}" \
            --sample-id "{wildcards.individual}" >"{log}" 2>&1
        """


rule compare_visualization_stats_accross_individuals_of_species:
    input:
        lambda wildcards: expand(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.stats.tsv",
            species=wildcards.species,
            feature_library=wildcards.feature_library,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        stats=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Running REVEAL coverage comparison for {wildcards.species}."
    shell:
        """
        stats_files=""
        stats_count=0
        for f in {input}; do
            if [ "$(wc -l <"$f")" -gt 1 ]; then
                stats_files="$stats_files $f"
                stats_count=$((stats_count + 1))
            fi
        done

        if [ "$stats_count" -lt 2 ]; then
            : >"{output.stats}"
            echo "Fewer than two individuals with usable coverage stats for {wildcards.species}/{wildcards.feature_library} (low-coverage individuals excluded); skipping REVEAL covcompare." >"{log}"
        else
            REVEAL covcompare --stats $stats_files --outfile "{output.stats}" >"{log}" 2>&1
        fi
        """


rule compare_visualization_snp_stats_across_individuals_of_species:
    input:
        lambda wildcards: expand(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats.tsv.gz",
            species=wildcards.species,
            feature_library=wildcards.feature_library,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        comparison=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_snp_comparison.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_snp_comparison.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Comparing SNP stats across individuals of {wildcards.species}."
    shell:
        """
        snp_files=""
        snp_count=0
        for f in {input}; do
            if [ "$(zcat "$f" | wc -l)" -gt 1 ]; then
                snp_files="$snp_files $f"
                snp_count=$((snp_count + 1))
            fi
        done

        if [ "$snp_count" -lt 2 ]; then
            : >"{output.comparison}"
            echo "Fewer than two individuals with usable SNP stats for {wildcards.species}/{wildcards.feature_library} (low-coverage individuals excluded); skipping REVEAL snpcompare." >"{log}"
        else
            REVEAL snpcompare \
                --snpstats $snp_files \
                --outfile "{output.comparison}" >"{log}" 2>&1
        fi
        """


rule compare_visualization_indel_stats_across_individuals_of_species:
    input:
        lambda wildcards: expand(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats.tsv.gz",
            species=wildcards.species,
            feature_library=wildcards.feature_library,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        comparison=temp(
            "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_indel_comparison.tsv"
        ),
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_indel_comparison.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Comparing indel stats across individuals of {wildcards.species}."
    shell:
        """
        indel_files=""
        indel_count=0
        for f in {input}; do
            if [ "$(zcat "$f" | wc -l)" -gt 1 ]; then
                indel_files="$indel_files $f"
                indel_count=$((indel_count + 1))
            fi
        done

        if [ "$indel_count" -lt 2 ]; then
            : >"{output.comparison}"
            echo "Fewer than two individuals with usable indel stats for {wildcards.species}/{wildcards.feature_library} (low-coverage individuals excluded); skipping REVEAL indelcompare." >"{log}"
        else
            REVEAL indelcompare \
                --indelstats $indel_files \
                --outfile "{output.comparison}" >"{log}" 2>&1
        fi
        """


rule combine_visualization_stats_across_feature_libraries:
    input:
        lambda wildcards: expand(
            "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.tsv.gz",
            species=wildcards.species,
            feature_library=get_feature_library_ids_for_species(wildcards.species),
        ),
    output:
        combined="{species}/results/reveal_module/{species}_reveal_coverage_comparison.tsv",
    log:
        "{species}/results/reveal_module/{species}_reveal_coverage_comparison.log",
    conda:
        "../../envs/python_and_r.yaml"
    params:
        feature_libraries=lambda wildcards: get_feature_library_ids_for_species(
            wildcards.species
        ),
    message:
        "Combining REVEAL stats comparisons across all feature libraries for {wildcards.species}."
    script:
        "../../scripts/reveal_module/combine_visualization_stats_across_feature_libraries.py"


rule extract_flagged_seqids:
    input:
        tsv="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.tsv.gz",
    output:
        txt="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_flagged_seqids.tsv",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_flagged_seqids.log",
    conda:
        "../../envs/python_and_r.yaml"
    script:
        "../../scripts/reveal_module/extract_flagged_seqids.py"


rule collect_excluded_individuals_of_species:
    input:
        reasons=lambda wildcards: expand(
            "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.exclusion_reason.txt",
            species=wildcards.species,
            feature_library=wildcards.feature_library,
            individual=get_individuals_for_species(wildcards.species),
        ),
    output:
        tsv="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_excluded_individuals.tsv",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_excluded_individuals.log",
    conda:
        "../../envs/python_and_r.yaml"
    params:
        individuals=lambda wildcards: get_individuals_for_species(wildcards.species),
    message:
        "Collecting individuals excluded from REVEAL normalization for {wildcards.species}."
    script:
        "../../scripts/reveal_module/collect_excluded_individuals.py"


rule compress_visualization_snp_stats_of_individual:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL SNP stats for {wildcards.individual} of {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'


rule compress_visualization_indel_stats_of_individual:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL indel stats for {wildcards.individual} of {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'


rule compress_visualization_coverage_comparison_of_species:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL coverage comparison for {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'


rule compress_visualization_snp_comparison_of_species:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_snp_comparison.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_snp_comparison.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_snp_comparison_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL SNP comparison for {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'


rule compress_visualization_indel_comparison_of_species:
    input:
        source="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_indel_comparison.tsv",
    output:
        target="{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_indel_comparison.tsv.gz",
    log:
        "{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_indel_comparison_compress.log",
    conda:
        "../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing REVEAL indel comparison for {wildcards.species}"
    shell:
        'pigz -p {threads} -c "{input.source}" > "{output.target}" 2> "{log}"'

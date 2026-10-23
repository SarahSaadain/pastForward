# Module-level settings for rules
####################################################

_ecmsd_taxonomic_hierarchy = (
    config.get("pipeline", {})
    .get("read_module", {})
    .get("taxonomic_screening", {})
    .get("tools", {})
    .get("ecmsd", {})
    .get("settings", {})
    .get("taxonomic_hierarchy", "species")
)

_ecmsd_tax_hierarchy_proportions_txt_output = f"{{species}}/results/read_module/taxonomic_screening/ecmsd/{{individual}}/{{sample}}/mapping/{{sample}}_Mito_summary_{_ecmsd_taxonomic_hierarchy}_proportions.txt"
_ecmsd_tax_hierarchy_summary_txt_output = f"{{species}}/results/read_module/taxonomic_screening/ecmsd/{{individual}}/{{sample}}/mapping/{{sample}}_Mito_summary_{_ecmsd_taxonomic_hierarchy}.txt"

####################################################
# Snakemake rules
####################################################


rule ecmsd_database_setup:
    output:
        [os.path.join(_ecmsd_db_folder(), f) for f in _ECMSD_DB_FILES],
    log:
        "resources/ecmsd_database_setup.log",
    conda:
        ECMSD_CONDA_ENV
    params:
        db_folder=lambda wildcards, output: os.path.dirname(output[0]),
    message:
        "Setting up ECMSD database."
    shell:
        """
        mkdir -p "{params.db_folder}"
        ECMSD --create-db --db-folder "{params.db_folder}" >"{log}" 2>&1
        """


rule ecmsd_taxonomic_screening:
    input:
        fastq="{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered_final.fastq.gz",
        database=_ecmsd_database_input,
    # ECMSD also writes {sample}_Mito_summary_{hierarchy}_{ReadLengths,Proportions}.png next to
    # the files below, but only when the sample has hits to plot - an empty result yields the
    # tables and no plots. They are deliberately not declared as outputs, so a sample with no
    # hits does not fail the rule.
    output:
        summary="{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/mapping/{sample}_Mito_summary.txt",
        paf="{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/mapping/{sample}_Mito.paf.gz",
        coverage="{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/mapping/{sample}_Mito_coverage.txt",
        ranked_summary="{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/mapping/{sample}_Mito_summary.ref_summary.txt",
        tax_hierarchy_proportions=_ecmsd_tax_hierarchy_proportions_txt_output,
        tax_hierarchy_summary=_ecmsd_tax_hierarchy_summary_txt_output,
    log:
        "{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/mapping/{sample}_ecmsd.log",
    conda:
        ECMSD_CONDA_ENV
    threads: 15
    params:
        cov_threshold=config.get("pipeline", {})
        .get("read_module", {})
        .get("taxonomic_screening", {})
        .get("tools", {})
        .get("ecmsd", {})
        .get("settings", {})
        .get("cov_threshold", 25),
        top_n=config.get("pipeline", {})
        .get("read_module", {})
        .get("taxonomic_screening", {})
        .get("tools", {})
        .get("ecmsd", {})
        .get("settings", {})
        .get("top_n", 25),
        mapping_quality=config.get("pipeline", {})
        .get("read_module", {})
        .get("taxonomic_screening", {})
        .get("tools", {})
        .get("ecmsd", {})
        .get("settings", {})
        .get("mapping_quality", 20),
        taxonomic_hierarchy=config.get("pipeline", {})
        .get("read_module", {})
        .get("taxonomic_screening", {})
        .get("tools", {})
        .get("ecmsd", {})
        .get("settings", {})
        .get("taxonomic_hierarchy", "species"),
        prefix="{sample}",
        db_folder=_ecmsd_db_folder,
        db_files=_ECMSD_DB_FILES,
    message:
        "Running ECMSD taxonomic screening for {input.fastq}"
    shell:
        """
        outdir=$(dirname "$(dirname "{output.summary}")")
        mkdir -p "$outdir"

        echo "Running ECMSD for sample {wildcards.sample}" >"{log}" 2>&1
        echo "Input FASTQ: {input.fastq}" >>"{log}" 2>&1
        echo "Output folder: $outdir" >>"{log}" 2>&1

        # ECMSD rebuilds a broken database inside the job, and parallel jobs would race on it.
        for f in {params.db_files}; do
            if [ ! -s "{params.db_folder}/$f" ]; then
                echo "ERROR: ECMSD database file {params.db_folder}/$f is missing or empty. Build the database once with: ECMSD --create-db --db-folder {params.db_folder}" >>"{log}"
                exit 1
            fi
        done

        ECMSD \
            --fwd "{input.fastq}" \
            --out "$outdir" \
            --threads {threads} \
            --prefix "{params.prefix}" \
            --cov-threshold {params.cov_threshold} \
            --top-n {params.top_n} \
            --mapping_quality {params.mapping_quality} \
            --taxonomic-hierarchy "{params.taxonomic_hierarchy}" \
            --db-folder "{params.db_folder}" \
            --force >>"{log}" 2>&1
        """


rule ecmsd_merge_hits_per_individual:
    input:
        lambda wildcards: expand(
            _ecmsd_tax_hierarchy_proportions_txt_output,
            sample=get_samples_for_species_individual(
                wildcards.species, wildcards.individual
            ),
            species=wildcards.species,
            individual=wildcards.individual,
        ),
    output:
        "{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.tsv",
    log:
        "{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        taxonomic_hierarchy=_ecmsd_taxonomic_hierarchy,
    script:
        "../../../scripts/read_module/taxonomic_screening/check_taxonomic_screening_ecmsd_script_ecmsd_merge_hits_per_individual.py"


rule ecmsd_analyze_proportions:
    input:
        report=_ecmsd_tax_hierarchy_proportions_txt_output,
        count_reads="{species}/processed/read_module/statistics/{sample}_quality_filtered.count",
    output:
        "{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/pipeline/{sample}_ecmsd_proportions.tsv",
    log:
        "{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/pipeline/{sample}_ecmsd_proportions.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        sample="{sample}",
    script:
        "../../../scripts/read_module/taxonomic_screening/check_taxonomic_screening_ecmsd_script_ecmsd_analyze_proportions.py"

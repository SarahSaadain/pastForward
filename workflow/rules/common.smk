####################################################
# Common Python helper functions for rules
####################################################
# Helper functions used by more than one caller, or too involved to express
# as an inline lambda, are collected here (per `snakemake --lint`'s "mixed
# rules and functions" guidance) so their originating rule files stay
# rules-only. Small one-off helpers stay inline as lambdas at their call site.

import glob
import os


def determine_reads_trimmed_final_input(wildcards):

    species = wildcards.species
    sample = wildcards.sample

    adapter_removal_active = (
        config.get("pipeline", {})
        .get("read_module", {})
        .get("adapter_removal", {})
        .get("execute", True)
    )
    reads = get_raw_reads_for_sample(species, sample)
    if adapter_removal_active:
        if len(reads) == 2:
            # Paired-end: use the merged reads from fastp_pe
            return f"{species}/processed/read_module/reads_trimmed/{sample}_trimmed.pe.merged.fastq.gz"
        else:
            # Single-end: use the trimmed reads from fastp_se
            return f"{species}/processed/read_module/reads_trimmed/{sample}_trimmed.se.fastq.gz"
    else:
        # Adapter removal inactive: pass raw reads through directly (SE: 1 file, PE: 2 files)
        return reads


def merge_reads_by_individual_input(wildcards):

    species = wildcards.species
    individual = wildcards.individual

    samples_of_individual = get_samples_for_species_individual(species, individual)

    if len(samples_of_individual) == 0:
        logger.info(f"Requested individual: {individual}")
        logger.error(
            f"No raw read files found for individual {individual}. Check that the individual ID is correct and that raw read files are present."
        )
        raise Exception(
            f"No raw read files found for individual {individual}. Check that the individual ID is correct and that raw read files are present."
        )

    # for each raw R1 file, generate the corresponding quality-filtered filename
    quality_filtered_files = []
    for sample in samples_of_individual:
        qf_file = f"{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered_final.fastq.gz"
        quality_filtered_files.append(qf_file)

    return quality_filtered_files


def create_multiqc_bam_individual_input(wildcards):

    species = wildcards.species
    reference = wildcards.reference
    individual = wildcards.individual

    file_list = []

    # for individual in individuals:
    # get samples for individual
    samples_of_individual = get_samples_for_species_individual(species, individual)

    if config.get("pipeline", {}).get("read_module", {}).get("execute", True) == True:

        if (
            config.get("pipeline", {})
            .get("read_module", {})
            .get("taxonomic_screening", {})
            .get("execute", True)
            == True
        ):

            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("taxonomic_screening", {})
                .get("tools", {})
                .get("centrifuge", {})
                .get("execute", True)
                == True
            ):

                for sample in samples_of_individual:
                    raw_reads = get_raw_reads_for_sample(species, sample)
                    file_list.append(
                        f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_total_taxa.tsv"
                    )

            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("taxonomic_screening", {})
                .get("tools", {})
                .get("ecmsd", {})
                .get("execute", True)
                == True
            ):
                file_list.append(
                    f"{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.tsv"
                )

        # merged reads fastqc
        if (
            config.get("pipeline", {})
            .get("read_module", {})
            .get("analysis", {})
            .get("execute", True)
            == True
            and config.get("pipeline", {})
            .get("read_module", {})
            .get("analysis", {})
            .get("settings", {})
            .get("multiqc_merged_reads", True)
            == True
        ):
            file_list.append(
                f"{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.zip"
            )

    if (
        config.get("pipeline", {})
        .get("reference_module", {})
        .get("analysis", {})
        .get("execute", True)
        == True
    ):
        # file_list.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.lc_extrap")
        if (
            config.get("pipeline", {})
            .get("reference_module", {})
            .get("analysis", {})
            .get("settings", {})
            .get("preseq_complexitiy_curve", True)
            == True
        ):
            file_list.append(
                f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.c_curve.txt"
            )
        if (
            config.get("pipeline", {})
            .get("reference_module", {})
            .get("analysis", {})
            .get("settings", {})
            .get("qualimap", True)
            == True
        ):
            file_list.append(
                directory(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/qualimap"
                )
            )
        if (
            config.get("pipeline", {})
            .get("reference_module", {})
            .get("analysis", {})
            .get("settings", {})
            .get("samtools_stats", True)
            == True
        ):
            file_list.append(
                f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats"
            )
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv"
        )
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.tsv"
        )
        # file_list.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_analysis.tsv")
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_depth_coverage_avg.csv"
        )
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_summary.tsv"
        )

    if (
        config.get("pipeline", {})
        .get("reference_module", {})
        .get("damage_rescaling", {})
        .get("execute", True)
        == True
    ):
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/3pGtoA_freq.txt"
        )
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/5pCtoT_freq.txt"
        )
        file_list.append(
            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/lgdistribution.txt"
        )

    return file_list


def create_multiqc_reference_input(wildcards):
    """Generate a list of input files for MultiQC report for all individuals of a species mapped to one reference."""

    species = wildcards.species
    reference = wildcards.reference
    individuals = get_individuals_for_species(species)

    file_list = []

    for individual in individuals:

        samples_of_individual = get_samples_for_species_individual(species, individual)

        if (
            config.get("pipeline", {}).get("read_module", {}).get("execute", True)
            == True
        ):

            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("taxonomic_screening", {})
                .get("execute", True)
                == True
            ):

                if (
                    config.get("pipeline", {})
                    .get("read_module", {})
                    .get("taxonomic_screening", {})
                    .get("tools", {})
                    .get("centrifuge", {})
                    .get("execute", True)
                    == True
                ):

                    for sample in samples_of_individual:
                        raw_reads = get_raw_reads_for_sample(species, sample)
                        file_list.append(
                            f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_total_taxa.tsv"
                        )

                if (
                    config.get("pipeline", {})
                    .get("read_module", {})
                    .get("taxonomic_screening", {})
                    .get("tools", {})
                    .get("ecmsd", {})
                    .get("execute", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.tsv"
                    )

            # merged reads fastqc
            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("analysis", {})
                .get("execute", True)
                == True
                and config.get("pipeline", {})
                .get("read_module", {})
                .get("analysis", {})
                .get("settings", {})
                .get("multiqc_merged_reads", True)
                == True
            ):
                file_list.append(
                    f"{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.zip"
                )

        # bam analytics for the single reference
        if (
            config.get("pipeline", {}).get("reference_module", {}).get("execute", False)
            == True
        ):

            if (
                config.get("pipeline", {})
                .get("reference_module", {})
                .get("analysis", {})
                .get("execute", True)
                == True
            ):
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("preseq_complexitiy_curve", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.c_curve.txt"
                    )
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("qualimap", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/qualimap/{individual}_{reference}"
                    )
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("samtools_stats", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats"
                    )
                # Only the bcftools tier of the SNP divergence check produces a file
                # MultiQC can render. The samtools_stats tier reuses the samtools stats
                # file already added above, so it needs nothing here.
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("snp_divergence_check", False)
                    == True
                    and config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("snp_divergence_method", "samtools_stats")
                    == "bcftools"
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/snp_divergence/{individual}_{reference}.bcftools_stats.txt"
                    )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.tsv"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_analysis.tsv"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_summary.tsv"
                )

            if (
                config.get("pipeline", {})
                .get("reference_module", {})
                .get("damage_rescaling", {})
                .get("execute", True)
                == True
            ):
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/3pGtoA_freq.txt"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/5pCtoT_freq.txt"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/lgdistribution.txt"
                )

    logger.debug(
        f"MultiQC reference input files for species {species}, reference {reference}: {file_list}"
    )

    return file_list


def dedup_merge_split_bams_input(wildcards):
    """
    Get all dedup BAMs corresponding to the contig group files named as 'cluster_{start}_{end}.bed'.
    """
    # Get checkpoint output folder
    # we use the checkpoint here to make sure that the files are generated before we try to access them
    # for more info see: https://snakemake.readthedocs.io/en/stable/snakefiles/rules.html#data-dependent-conditional-execution
    checkpoint_output = checkpoints.dedup_create_all_contig_clusters.get(
        species=wildcards.species, reference=wildcards.reference
    ).output.cluster_folder

    # Find all group files
    group_files = sorted(glob.glob(os.path.join(checkpoint_output, "cluster_*.bed")))

    logger.debug(f"Found {len(group_files)} contig cluster files for deduplication.")
    logger.debug(f"Cluster files: {group_files}")

    bam_files = []
    for group_file in group_files:
        group_name = os.path.splitext(os.path.basename(group_file))[0]  # "group_1_50"
        start_end = group_name.split("_")[1:]  # ["1", "50"]
        start, end = map(int, start_end)
        bam_path = (
            f"{wildcards.species}/processed/reference_module/{wildcards.reference}/dedup_cluster/"
            f"{wildcards.individual}/dedup_{start}_{end}/{wildcards.individual}_{wildcards.reference}_cluster_{start}_{end}_rmdup.bam"
        )
        bam_files.append(bam_path)

    # add unmapped reads bam file to the list of bams to merge
    bam_files.append(
        f"{wildcards.species}/processed/reference_module/{wildcards.reference}/mapped/{wildcards.individual}_{wildcards.reference}_unmapped_reads.bam"
    )

    logger.debug(f"Requesting {len(bam_files)} deduplicated BAM files for merging.")
    logger.debug(f"Deduplicated BAM files: {bam_files}")

    return bam_files


def dedup_merge_split_jsons_input(wildcards):
    """
    Get all DeDup JSON files corresponding to contig group files
    named as 'cluster_{start}_{end}.bed'.
    """
    # Resolve checkpoint output folder (forces execution before globbing)
    checkpoint_output = checkpoints.dedup_create_all_contig_clusters.get(
        species=wildcards.species, reference=wildcards.reference
    ).output.cluster_folder

    # Find all contig group files
    group_files = sorted(glob.glob(os.path.join(checkpoint_output, "cluster_*_*.bed")))

    logger.info(f"Found {len(group_files)} contig group files.")
    logger.debug(f"Group files: {group_files}")

    json_files = []

    for group_file in group_files:
        # group_1_500.txt → start=1, end=500
        group_name = os.path.basename(group_file)
        group_name = os.path.splitext(group_name)[0]

        _, start, end = group_name.split("_", 2)

        json_path = (
            f"{wildcards.species}/processed/reference_module/{wildcards.reference}/dedup_cluster/"
            f"{wildcards.individual}/dedup_{start}_{end}/{wildcards.individual}_{wildcards.reference}_cluster_{start}_{end}.dedup.json"
        )

        json_files.append(json_path)

    logger.info(f"Requesting {len(json_files)} DeDup JSON files for MultiQC.")
    logger.debug(f"DeDup JSON files: {json_files}")

    return json_files


def _standardize_reference_extension_to_fa_ref_path(wildcards):
    # Get the list of reference tuples (sanitized_name, full_path)
    # the full_path contains the original file path
    reference_tuples = get_reference_file_list_for_species(wildcards.species)

    # Find the path corresponding to the sanitized reference name
    ref_path = next(
        (path for name, path in reference_tuples if name == wildcards.reference), None
    )

    if ref_path is None:
        raise ValueError(
            f"Reference {wildcards.reference} not found for species {wildcards.species}. "
            f"Available references: {reference_tuples}"
        )

    if not os.path.exists(ref_path):
        raise FileNotFoundError(f"Reference file {ref_path} does not exist.")

    return ref_path


def get_competition_fasta_input(wildcards):
    path = get_competition_fasta_for_species(wildcards.species)
    if not path:
        raise ValueError(
            f"pipeline.reveal_module.mapping.competitive_mapping.execute is true, but no competition "
            f"FASTA was found in '{wildcards.species}/input/reveal_module/competition/' for species "
            f"'{wildcards.species}'. Place exactly one FASTA file there to use competitive mapping."
        )
    return path


def clean_scg_library_name_input(wildcards):
    """
    Return the FASTA path for the SCG library: user-provided if available,
    otherwise the auto-determined path produced by the SCG selector.
    """
    species = wildcards.species
    scg_library = wildcards.scg_library

    # Try user-provided SCG library first
    try:
        scg_library_path = get_scg_library_file_for_species_and_library(
            species, scg_library
        )
        return scg_library_path
    except Exception:
        pass

    # Fall back to auto-determined SCG output
    auto_id = get_effective_scg_library_id_for_species(species)
    if scg_library == auto_id:
        auto_path = f"{species}/results/reveal_module/scg/{species}_relevant_scg.fasta"
        if os.path.exists(auto_path):
            logger.info(
                f"Found SCG library from a previous run for {species} at {auto_path}, reusing it."
            )
        else:
            logger.info(
                f"No SCG library found for {species}, it will be auto-determined."
            )
        return auto_path

    raise ValueError(
        f"No SCG library file could be determined for species {species} and library {scg_library}."
    )


def clean_feature_library_name_input(wildcards):
    """
    Return the full path to the FASTA file for this feature library.
    """
    species = wildcards.species
    feature_library = wildcards.feature_library

    feature_library_path = get_feature_library_file_for_species_and_library(
        species, feature_library
    )

    if not feature_library_path:
        raise ValueError(
            f"No feature library file could be determined for species {species} and library {feature_library}."
        )

    return feature_library_path


def _scg_setting(wildcards, key, default):
    """Return pipeline-level reveal_module.scg_selector.settings.{key}, falling back to default."""
    return (
        config.get("pipeline", {})
        .get("reveal_module", {})
        .get("scg_selector", {})
        .get("settings", {})
        .get(key, default)
    )


def _get_busco_lineage(wildcards):
    lineage = config.get("species", {}).get(wildcards.species, {}).get("lineage")
    if lineage is None:
        raise ValueError(
            f"BUSCO lineage is required for species '{wildcards.species}' but was not provided. "
            f"Set species.{wildcards.species}.lineage in your config."
        )
    return lineage


def create_multiqc_species_individual_input(wildcards):
    """Generate a list of input files for MultiQC report for a given species and its individuals."""

    species = wildcards.species
    individual = wildcards.individual

    try:
        # Get all reference for the species
        references = get_references_ids_for_species(species)
    except Exception as e:
        # Print error if reference files are missing or inaccessible
        logging.info(e)
        references = []

    file_list = []

    # for individual in individuals:
    # get samples for individual
    samples_of_individual = get_samples_for_species_individual(species, individual)

    if config.get("pipeline", {}).get("read_module", {}).get("execute", True) == True:

        if (
            config.get("pipeline", {})
            .get("read_module", {})
            .get("taxonomic_screening", {})
            .get("execute", True)
            == True
        ):

            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("taxonomic_screening", {})
                .get("tools", {})
                .get("centrifuge", {})
                .get("execute", True)
                == True
            ):

                for sample in samples_of_individual:
                    raw_reads = get_raw_reads_for_sample(species, sample)
                    file_list.append(
                        f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_total_taxa.tsv"
                    )

            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("taxonomic_screening", {})
                .get("tools", {})
                .get("ecmsd", {})
                .get("execute", True)
                == True
            ):

                file_list.append(
                    f"{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.tsv"
                )

        # merged reads fastqc
        if (
            config.get("pipeline", {})
            .get("read_module", {})
            .get("analysis", {})
            .get("execute", True)
            == True
            and config.get("pipeline", {})
            .get("read_module", {})
            .get("analysis", {})
            .get("settings", {})
            .get("multiqc_merged_reads", True)
            == True
        ):
            file_list.append(
                f"{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.zip"
            )

    # bam analytics
    if (
        config.get("pipeline", {}).get("reference_module", {}).get("execute", True)
        == True
    ):

        for reference in references:

            if (
                config.get("pipeline", {})
                .get("reference_module", {})
                .get("analysis", {})
                .get("execute", True)
                == True
            ):
                # file_list.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.lc_extrap")
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("preseq_complexitiy_curve", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.c_curve.txt"
                    )
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("qualimap", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/qualimap/{individual}_{reference}"
                    )
                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("settings", {})
                    .get("samtools_stats", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats"
                    )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.tsv"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_analysis.tsv"
                )
                # file_list.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_depth_coverage_avg.csv")
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_summary.tsv"
                )

            if (
                config.get("pipeline", {})
                .get("reference_module", {})
                .get("damage_rescaling", {})
                .get("execute", True)
                == True
            ):
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/3pGtoA_freq.txt"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/5pCtoT_freq.txt"
                )
                file_list.append(
                    f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/lgdistribution.txt"
                )

    logger.debug(f"MultiQC input files for species {species}: {file_list}")

    return file_list


def create_multiqc_species_input(wildcards):
    """Generate a list of input files for MultiQC report for a given species and its individuals."""

    species = wildcards.species
    individuals = get_individuals_for_species(species)

    try:
        # Get all reference for the species
        references = get_references_ids_for_species(species)
    except Exception as e:
        # Print error if reference files are missing or inaccessible
        logging.info(e)
        references = []

    file_list = []

    for individual in individuals:

        # for individual in individuals:
        # get samples for individual
        samples_of_individual = get_samples_for_species_individual(species, individual)

        if (
            config.get("pipeline", {}).get("read_module", {}).get("execute", True)
            == True
        ):

            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("taxonomic_screening", {})
                .get("execute", True)
                == True
            ):

                if (
                    config.get("pipeline", {})
                    .get("read_module", {})
                    .get("taxonomic_screening", {})
                    .get("tools", {})
                    .get("centrifuge", {})
                    .get("execute", True)
                    == True
                ):

                    for sample in samples_of_individual:
                        raw_reads = get_raw_reads_for_sample(species, sample)
                        file_list.append(
                            f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_total_taxa.tsv"
                        )

                if (
                    config.get("pipeline", {})
                    .get("read_module", {})
                    .get("taxonomic_screening", {})
                    .get("tools", {})
                    .get("ecmsd", {})
                    .get("execute", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.tsv"
                    )

            # merged reads fastqc
            if (
                config.get("pipeline", {})
                .get("read_module", {})
                .get("analysis", {})
                .get("execute", True)
                == True
                and config.get("pipeline", {})
                .get("read_module", {})
                .get("analysis", {})
                .get("settings", {})
                .get("multiqc_merged_reads", True)
                == True
            ):
                file_list.append(
                    f"{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.zip"
                )

        # bam analytics
        if (
            config.get("pipeline", {}).get("reference_module", {}).get("execute", False)
            == True
        ):
            for reference in references:

                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("analysis", {})
                    .get("execute", True)
                    == True
                ):
                    # file_list.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.lc_extrap")
                    if (
                        config.get("pipeline", {})
                        .get("reference_module", {})
                        .get("analysis", {})
                        .get("settings", {})
                        .get("preseq_complexitiy_curve", True)
                        == True
                    ):
                        file_list.append(
                            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/preseq/{individual}_{reference}.c_curve.txt"
                        )
                    if (
                        config.get("pipeline", {})
                        .get("reference_module", {})
                        .get("analysis", {})
                        .get("settings", {})
                        .get("qualimap", True)
                        == True
                    ):
                        file_list.append(
                            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/qualimap/{individual}_{reference}"
                        )
                    if (
                        config.get("pipeline", {})
                        .get("reference_module", {})
                        .get("analysis", {})
                        .get("settings", {})
                        .get("samtools_stats", True)
                        == True
                    ):
                        file_list.append(
                            f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/samtools_stats/{individual}_{reference}_final.bam.stats"
                        )
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary.tsv"
                    )
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_reads_processing_summary_stacked.tsv"
                    )
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_analysis.tsv"
                    )
                    # file_list.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_depth_coverage_avg.csv")
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_summary.tsv"
                    )

                if (
                    config.get("pipeline", {})
                    .get("reference_module", {})
                    .get("damage_rescaling", {})
                    .get("execute", True)
                    == True
                ):
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/3pGtoA_freq.txt"
                    )
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/5pCtoT_freq.txt"
                    )
                    file_list.append(
                        f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/mapdamage/{individual}_{reference}/lgdistribution.txt"
                    )

    logger.debug(f"MultiQC input files for species {species}: {file_list}")

    return file_list

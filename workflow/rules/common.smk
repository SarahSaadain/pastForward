####################################################
# Common Python helper functions for rules
####################################################
# Helper functions used by more than one caller, or too involved to express
# as an inline lambda, are collected here (per `snakemake --lint`'s "mixed
# rules and functions" guidance) so their originating rule files stay
# rules-only. Small one-off helpers stay inline as lambdas at their call site.

import glob
import os

# Version of the Snakemake wrapper repository every `wrapper:` directive is pinned to. Bump it
# here, in one place, so all wrappers move together. A bump changes tool versions and rebuilds
# the wrapper envs, so treat it as its own release and check a dry run afterwards.
WRAPPER_VERSION = "v9.3.0"


def _mapper_default_extra(mapper):
    """Default extra flags for a mapper, used when the config sets none."""
    if mapper == "bwa-aln":
        return "-n 0.01 -k 2 -l 1024 -o 2"  # Oliva et al. 2021 (10.1093/bib/bbab076)
    if mapper == "minimap2":
        return "-ax sr"
    return ""


def _mapper_extra(settings, mapper):
    """Configured extra flags for a mapper. Missing or empty ("") falls back to the default."""
    # `or`, not a .get() default: "" would drop minimap2's -ax sr and make it write PAF.
    return (settings.get("mapper_extra_params") or "").strip() or _mapper_default_extra(
        mapper
    )


def _scg_mapper_and_extra(scg_settings, mapping_settings):
    """Mapper and extra flags for SCG mapping. Unset values come from the mapping step."""
    mapping_mapper = mapping_settings.get("mapper", "bwa-mem2")
    mapper = scg_settings.get("mapper") or mapping_mapper
    # Borrow the mapping step's flags only when both steps use the same mapper.
    # Flags for one mapper break another (bwa-aln flags handed to minimap2).
    extra = (scg_settings.get("mapper_extra_params") or "").strip() or (
        _mapper_extra(mapping_settings, mapper)
        if mapper == mapping_mapper
        else _mapper_default_extra(mapper)
    )
    return mapper, extra


def _dedup_enabled():
    """True unless pipeline.reference_module.deduplication.execute is false."""
    return (
        (config.get("pipeline") or {})
        .get("reference_module", {})
        .get("deduplication", {})
        .get("execute", True)
    )


def _fastp_adapter_flags(paired):
    # Only set adapters get a flag. `adapters_sequences:` left empty in YAML is None, not {}.
    seqs = (config.get("pipeline") or {}).get("read_module", {}).get(
        "adapter_removal", {}
    ).get("settings", {}).get("adapters_sequences") or {}
    flags = [("--adapter_sequence", "r1")]
    if paired:
        flags.append(("--adapter_sequence_r2", "r2"))
    return " ".join(f"{flag} {seqs[key]}" for flag, key in flags if seqs.get(key))


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


def get_snp_divergence_methods(analysis_settings):
    """
    The SNP divergence methods to run, from analysis.settings.snp_divergence_method.

    "both" runs samtools_stats and bcftools side by side. Every species-level output
    carries the method in its filename, so the two never collide and a file written by
    an earlier method is never picked up as if the current one had produced it.
    Validation of the value lives in analyze_snp_divergence.smk.
    """
    method = analysis_settings.get("snp_divergence_method", "samtools_stats")
    if method == "both":
        return ["samtools_stats", "bcftools"]
    return [method]


def _multiqc_individual_input(species, individual, references, bcftools_stats=False):
    """MultiQC input files of one individual: its read-module results, then its results
    against each of `references`. Every MultiQC report is built from these blocks.

    bcftools_stats adds the SNP divergence bcftools stats file. Only the per-reference
    species report sets it: in reports spanning several references the same individual
    would appear once per reference under one sample name.
    """
    pipeline = config.get("pipeline", {})
    read_module = pipeline.get("read_module", {})
    reference_module = pipeline.get("reference_module", {})

    file_list = []

    if read_module.get("execute", True) == True:
        taxonomic_screening = read_module.get("taxonomic_screening", {})
        if taxonomic_screening.get("execute", True) == True:
            tools = taxonomic_screening.get("tools", {})
            if tools.get("centrifuge", {}).get("execute", True) == True:
                for sample in get_samples_for_species_individual(species, individual):
                    file_list.append(
                        f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_total_taxa.tsv"
                    )
            if tools.get("ecmsd", {}).get("execute", True) == True:
                file_list.append(
                    f"{species}/results/read_module/taxonomic_screening/ecmsd/{individual}_Mito_summary_hits_combined.tsv"
                )

        # merged reads fastqc
        read_analysis = read_module.get("analysis", {})
        if (
            read_analysis.get("execute", True) == True
            and read_analysis.get("settings", {}).get("multiqc_merged_reads", True)
            == True
        ):
            file_list.append(
                f"{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.zip"
            )

    if reference_module.get("execute", True) != True:
        return file_list

    analysis = reference_module.get("analysis", {})
    analysis_settings = analysis.get("settings", {})

    for reference in references:
        individual_dir = f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}"
        custom_content = f"{individual_dir}/multiqc_custom_content"

        if analysis.get("execute", True) == True:
            if analysis_settings.get("preseq_complexitiy_curve", True) == True:
                file_list.append(
                    f"{individual_dir}/preseq/{individual}_{reference}.c_curve.txt"
                )
            if analysis_settings.get("qualimap", True) == True:
                file_list.append(f"{custom_content}/qualimap/{individual}_{reference}")
            if analysis_settings.get("samtools_stats", True) == True:
                file_list.append(
                    f"{individual_dir}/samtools_stats/{individual}_{reference}_final.bam.stats"
                )
            # Only the bcftools method of the SNP divergence check produces a file
            # MultiQC can render. The samtools_stats method reuses the samtools stats
            # file already added above, so it needs nothing here.
            if (
                bcftools_stats
                and analysis_settings.get("snp_divergence_check", False) == True
                and "bcftools" in get_snp_divergence_methods(analysis_settings)
            ):
                file_list.append(
                    f"{individual_dir}/snp_divergence/{individual}_{reference}.bcftools_stats.txt"
                )
            file_list.append(
                f"{custom_content}/{individual}_{reference}_reads_processing_summary.tsv"
            )
            file_list.append(
                f"{custom_content}/{individual}_{reference}_reads_processing_summary_stacked.tsv"
            )
            file_list.append(
                f"{custom_content}/{individual}_{reference}_coverage_analysis.tsv"
            )
            file_list.append(
                f"{custom_content}/{individual}_{reference}_coverage_summary.tsv"
            )

        if reference_module.get("damage_rescaling", {}).get("execute", True) == True:
            mapdamage = f"{custom_content}/mapdamage/{individual}_{reference}"
            file_list.append(f"{mapdamage}/3pGtoA_freq.txt")
            file_list.append(f"{mapdamage}/5pCtoT_freq.txt")
            file_list.append(f"{mapdamage}/lgdistribution.txt")

    return file_list


def _references_for_multiqc(species):
    try:
        # Get all reference for the species
        return get_references_ids_for_species(species)
    except Exception as e:
        # Print error if reference files are missing or inaccessible
        logging.info(e)
        return []


def create_multiqc_bam_individual_input(wildcards):
    """Generate a list of input files for MultiQC report for one individual mapped to one reference."""
    return _multiqc_individual_input(
        wildcards.species, wildcards.individual, [wildcards.reference]
    )


def create_multiqc_reference_input(wildcards):
    """Generate a list of input files for MultiQC report for all individuals of a species mapped to one reference."""

    species = wildcards.species
    reference = wildcards.reference

    file_list = []
    for individual in get_individuals_for_species(species):
        file_list += _multiqc_individual_input(
            species, individual, [reference], bcftools_stats=True
        )

    logger.debug(
        f"MultiQC reference input files for species {species}, reference {reference}: {file_list}"
    )

    return file_list


def create_multiqc_species_individual_input(wildcards):
    """Generate a list of input files for MultiQC report for a given species and its individuals."""

    species = wildcards.species
    file_list = _multiqc_individual_input(
        species, wildcards.individual, _references_for_multiqc(species)
    )

    logger.debug(f"MultiQC input files for species {species}: {file_list}")

    return file_list


def create_multiqc_species_input(wildcards):
    """Generate a list of input files for MultiQC report for a given species and its individuals."""

    species = wildcards.species
    references = _references_for_multiqc(species)

    file_list = []
    for individual in get_individuals_for_species(species):
        file_list += _multiqc_individual_input(species, individual, references)

    logger.debug(f"MultiQC input files for species {species}: {file_list}")

    return file_list


def _dedup_cluster_ranges(wildcards):
    """
    (start, end) of every contig cluster file 'cluster_{start}_{end}.bed' written by
    the dedup_create_all_contig_clusters checkpoint.
    """
    # the checkpoint makes sure the files exist before we glob them
    # for more info see: https://snakemake.readthedocs.io/en/stable/snakefiles/rules.html#data-dependent-conditional-execution
    cluster_folder = checkpoints.dedup_create_all_contig_clusters.get(
        species=wildcards.species, reference=wildcards.reference
    ).output.cluster_folder

    group_files = sorted(glob.glob(os.path.join(cluster_folder, "cluster_*_*.bed")))
    logger.debug(f"Found {len(group_files)} contig cluster files for deduplication.")

    # "cluster_1_50.bed" -> (1, 50)
    return [
        tuple(map(int, os.path.splitext(os.path.basename(f))[0].split("_")[1:]))
        for f in group_files
    ]


def dedup_merge_split_bams_input(wildcards):
    """
    Get all dedup BAMs corresponding to the contig cluster files.
    """
    bam_files = [
        f"{wildcards.species}/processed/reference_module/{wildcards.reference}/dedup_cluster/"
        f"{wildcards.individual}/dedup_{start}_{end}/{wildcards.individual}_{wildcards.reference}_cluster_{start}_{end}_rmdup.bam"
        for start, end in _dedup_cluster_ranges(wildcards)
    ]

    # add unmapped reads bam file to the list of bams to merge
    bam_files.append(
        f"{wildcards.species}/processed/reference_module/{wildcards.reference}/mapped/{wildcards.individual}_{wildcards.reference}_unmapped_reads.bam"
    )

    logger.debug(f"Requesting {len(bam_files)} deduplicated BAM files for merging.")
    logger.debug(f"Deduplicated BAM files: {bam_files}")

    return bam_files


def dedup_merge_split_jsons_input(wildcards):
    """
    Get all DeDup JSON files corresponding to the contig cluster files.
    """
    json_files = [
        f"{wildcards.species}/processed/reference_module/{wildcards.reference}/dedup_cluster/"
        f"{wildcards.individual}/dedup_{start}_{end}/{wildcards.individual}_{wildcards.reference}_cluster_{start}_{end}.dedup.json"
        for start, end in _dedup_cluster_ranges(wildcards)
    ]

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
            f"pipeline.reveal_module.mapping.settings.competitive_mapping is true, but no competition "
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


# The files ECMSD reads from its database folder (REF, NODES and NAMES in ECMSD.sh). The first one
# sits at the top of the folder: ecmsd_database_setup takes the folder from its path.
_ECMSD_DB_FILES = [
    "mitochondrion_refseq_taxid_masked.fna.gz",
    "NCBI_taxdump/nodes.dmp",
    "NCBI_taxdump/names.dmp",
]
_ECMSD_DEFAULT_DB = "resources/ecmsd_database"


def _ecmsd_db_folder(wildcards=None):
    return (
        config.get("pipeline", {})
        .get("read_module", {})
        .get("taxonomic_screening", {})
        .get("tools", {})
        .get("ecmsd", {})
        .get("settings", {})
        .get("database")
        or _ECMSD_DEFAULT_DB
    )


def _ecmsd_database_input(wildcards):
    files = [os.path.join(_ecmsd_db_folder(), f) for f in _ECMSD_DB_FILES]
    # Snakemake only checks that a file exists, and ECMSD skips build steps whose file exists.
    empty = [f for f in files if os.path.isfile(f) and os.path.getsize(f) == 0]
    if empty:
        raise ValueError(
            f"ECMSD database file(s) are empty, probably left by an interrupted build: {', '.join(empty)}. "
            "Delete them and run again: pastForward then rebuilds the missing files."
        )
    # ancient(): newer database files alone do not rerun finished samples.
    return [ancient(f) for f in files]

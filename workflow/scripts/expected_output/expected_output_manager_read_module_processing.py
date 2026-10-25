# =================================================================================================
#     Input Manager Utility Functions for pastForward Pipeline
# =================================================================================================
# This script provides helper functions for managing input files and sample metadata in the pipeline.
# Functions include file discovery, reference handling, and sample identification.

import os
import logging

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for FastQC (raw reads)
def get_expected_output_fastqc_raw(species):

    if config.get("pipeline", {}).get("read_module", {}).get("analysis", {}).get("settings", {}).get("multiqc_raw_reads", True) == False:
        logging.info(f"Skipping FastQC for raw reads for {species}. Disabled in config.")
        return []

    files = get_r1_read_files_for_species(species)

    all_inputs = []
    for raw_file in files:
        filename = strip_raw_read_extension(os.path.basename(raw_file))
        all_inputs.append(f"{species}/results/read_module/reads_raw/fastqc/{filename}_raw_fastqc.html")
        # Add R2 if exists
        r2_path = get_read2_counterpart_path(raw_file)
        if os.path.exists(r2_path):
            r2_filename = strip_raw_read_extension(os.path.basename(r2_path))
            all_inputs.append(f"{species}/results/read_module/reads_raw/fastqc/{r2_filename}_raw_fastqc.html")
    return all_inputs

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for FastQC (adapter trimmed reads)
def get_expected_output_fastqc_trimmed(species):
    if config.get("pipeline", {}).get("read_module", {}).get("analysis", {}).get("settings", {}).get("multiqc_trimmed_reads", True) == False:
        logging.info(f"Skipping FastQC for trimmed reads for {species}. Disabled in config.")
        return []

    all_inputs = []
    for sample in get_sample_ids_for_species(species):
        all_inputs.append(f"{species}/results/read_module/reads_trimmed/fastqc/{sample}_trimmed_fastqc.html")
    return all_inputs

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for FastQC (adapter removed reads)
def get_expected_output_fastqc_quality_filtered(species):
    if config.get("pipeline", {}).get("read_module", {}).get("analysis", {}).get("settings", {}).get("multiqc_quality_filtered_reads", True) == False:
        logging.info(f"Skipping FastQC for quality filtered reads for {species}. Disabled in config.")
        return []

    all_inputs = []
    for sample in get_sample_ids_for_species(species):
        all_inputs.append(f"{species}/results/read_module/reads_quality_filtered/fastqc/{sample}_quality_filtered_fastqc.html")
    return all_inputs

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for FastQC (merged reads)
def get_expected_output_fastqc_merged(species):
    all_inputs = []
    for individual in get_individuals_for_species(species):
        all_inputs.append(f"{species}/results/read_module/reads_merged/fastqc/{individual}_merged_fastqc.html")
    return all_inputs

#-----------------------------------------------------------------------------------------------
# Get expected output file paths for taxonomic screening (ECMSD)
def get_expected_output_taxonomic_screening_ecmsd(species):  

    if config.get("pipeline", {}).get("read_module", {}).get("taxonomic_screening", {}).get("tools", {}).get("ecmsd", {}).get("execute", True) == False:
        logging.info(f"Skipping taxonomic screening with ECMSD for {species}. Disabled in config.")
        return []

    expected_outputs = []

    for individual in get_individuals_for_species(species):
        for sample in get_samples_for_species_individual(species, individual):
            expected_outputs.append(f"{species}/results/read_module/taxonomic_screening/ecmsd/{individual}/{sample}/mapping/{sample}_Mito_summary.txt")
    
    return expected_outputs

#-----------------------------------------------------------------------------------------------
# Get expected output file paths for taxonomic screening (Centrifuge)
def get_expected_output_taxonomic_screening_centrifuge(species):

    if config.get("pipeline", {}).get("read_module", {}).get("taxonomic_screening", {}).get("tools", {}).get("centrifuge", {}).get("execute", True) == False:
        logging.info(f"Skipping taxonomic screening with Centrifuge for {species}. Disabled in config.")
        return []

    expected_outputs = []

    for individual in get_individuals_for_species(species):
        for sample in get_samples_for_species_individual(species, individual):
            expected_outputs.append(f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_report.tsv")
            expected_outputs.append(f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_taxon_counts.tsv")
            expected_outputs.append(f"{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_output.tsv.gz")

    return expected_outputs

#-----------------------------------------------------------------------------------------------
# Get expected output file paths for taxonomic screening (all tools)
def get_expected_output_taxonomic_screening(species):  

    if config.get("pipeline", {}).get("read_module", {}).get("taxonomic_screening", {}).get("execute", True) == False:
        logging.info(f"Skipping taxonomic screening for {species}. Disabled in config.")
        return []

    expected_outputs = []

    # Add ECMSD taxonomic screening outputs
    expected_outputs += get_expected_output_taxonomic_screening_ecmsd(species)

    # Add Centrifuge taxonomic screening outputs
    expected_outputs += get_expected_output_taxonomic_screening_centrifuge(species)

    return expected_outputs

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for MultiQC reports
def get_expected_output_multiqc(species):

    expected_outputs = []
    analysis_settings = config.get("pipeline", {}).get("read_module", {}).get("analysis", {}).get("settings", {})

    # Add MultiQC reports for different read processing stages
    if analysis_settings.get("multiqc_raw_reads", True) == True:
        expected_outputs.append(f"{species}/results/read_module/{species}_multiqc_raw.html")
    else:
        logging.info(f"Skipping MultiQC report for raw reads for {species}. Disabled in config.")

    if analysis_settings.get("multiqc_trimmed_reads", True) == True:
        expected_outputs.append(f"{species}/results/read_module/{species}_multiqc_trimmed.html")
    else:
        logging.info(f"Skipping MultiQC report for trimmed reads for {species}. Disabled in config.")

    if analysis_settings.get("multiqc_quality_filtered_reads", True) == True:
        expected_outputs.append(f"{species}/results/read_module/{species}_multiqc_quality_filtered.html")
    else:
        logging.info(f"Skipping MultiQC report for quality filtered reads for {species}. Disabled in config.")

    if analysis_settings.get("multiqc_merged_reads", True) == True:
        expected_outputs.append(f"{species}/results/read_module/{species}_multiqc_merged.html")
    else:
        logging.info(f"Skipping MultiQC report for merged reads for {species}. Disabled in config.")

    return expected_outputs

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for read count plots
def get_expected_output_reads_plots(species):
    if config.get("pipeline", {}).get("read_module", {}).get("analysis", {}).get("settings", {}).get("create_plots", True) == False:
        logging.info(f"Skipping read plots generation for {species}. Disabled in config.")
        return []

    expected_outputs = []
    expected_outputs.append(f"{species}/results/read_module/plots/{species}_read_counts.png")
    expected_outputs.append(f"{species}/results/read_module/plots/{species}_read_counts_comparison_by_individual.png")
    return expected_outputs

# -----------------------------------------------------------------------------------------------
# Get expected output file paths for read merging
def get_expected_output_read_merging(species):
    
    # read merging is should always be the result of raw read processing, so we don't check config for this step.
    expected_outputs = []
    for individual in get_individuals_for_species(species):
        expected_outputs.append(f"{species}/results/read_module/reads_merged/{individual}.fastq.gz")

    return expected_outputs

def get_expected_output_analytics(species):

    if config.get("pipeline", {}).get("read_module", {}).get("analysis", {}).get("execute", True) == False:
        logging.info(f"Skipping analytics for {species}. Disabled in config.")
        return []

    expected_outputs = []

    # Add MultiQC reports for different read processing stages
    expected_outputs += get_expected_output_multiqc(species)

     # Summary plots (gated on analysis.settings.create_plots)
    expected_outputs += get_expected_output_reads_plots(species)

    return expected_outputs

# -----------------------------------------------------------------------------------------------
# Get all expected output file paths for raw read processing
def get_expected_output_read_module(species):

    if config.get("pipeline", {}).get("read_module", {}).get("execute", True) == False:
        logging.info(f"Skipping raw read processing for {species}. Disabled in config.")
        return []
    
    expected_outputs = []

    # Add merged reads to expected outputs since they are a product of raw read processing
    expected_outputs += get_expected_output_read_merging(species)

    # Add taxonomic screening outputs
    expected_outputs += get_expected_output_taxonomic_screening(species)

    # Read count statistics always run
    expected_outputs.append(f"{species}/results/read_module/statistics/{species}_reads_counts.csv")

    # Read composition (merged/unmerged/unpaired), also written when adapter removal is skipped
    expected_outputs.append(f"{species}/results/read_module/statistics/{species}_read_composition_by_sample.csv")
    expected_outputs.append(f"{species}/results/read_module/statistics/{species}_read_composition_by_individual.csv")

    # Add analytics outputs (MultiQC reports and read count plots)
    expected_outputs += get_expected_output_analytics(species)

    
    return expected_outputs
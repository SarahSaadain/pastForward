# =================================================================================================
#     Input Manager Utility Functions for pastForward Pipeline
# =================================================================================================
# This script provides helper functions for managing input files and sample metadata in the pipeline.
# Functions include file discovery, reference handling, and sample identification.

import os
import logging
# -----------------------------------------------------------------------------------------------
# Skip existing files based on configuration
def skip_existing_files(expected_outputs):

    # Filter out files that already exist if the skip_existing_files option is enabled.
    # Disabled by default so that Snakemake's own re-run logic stays in charge.
    if not config.get("pipeline", {}).get("global", {}).get("skip_existing_files", False):
        return expected_outputs

    logging.warning(
        "pipeline.global.skip_existing_files is enabled: existing output files are not "
        "requested from Snakemake, so changed input files will NOT propagate to outputs "
        "that already exist on disk. Results may be inconsistent. Set it to false (the "
        "default) to restore Snakemake's normal re-run behaviour."
    )
    logging.info("Checking for existing files to skip...")

    expected_outputs_existing = []
    expected_outputs_not_existing = []

    # Check for existing files and filter them out
    for output in expected_outputs:
        if os.path.exists(output):
            expected_outputs_existing.append(output)
        else:
            expected_outputs_not_existing.append(output)

    # Log existing files that will be skipped
    if len(expected_outputs_existing) > 0:
        logging.info("The following files already exist and will be skipped:")
        for existing_file in expected_outputs_existing:
            logging.info("\t- Skipping: %s", existing_file)
       
    return expected_outputs_not_existing

# -----------------------------------------------------------------------------------------------
# Generate all input file paths required for the 'all' rule in Snakemake
# This function collects all expected output files for each species and sample, ensuring that
# downstream rules have the correct input targets for completion. It is typically used to define
# the 'all' rule in the Snakefile, which triggers the entire workflow.
def get_expected_outputs_from_pipeline(wildcards):
    # An empty config means config/config.yaml is missing: initialize.smk only loads it when it
    # is there, so that the workflow still parses without one (see the comment there). Say so
    # here instead of quietly requesting nothing at all. This runs while Snakemake builds the
    # DAG, so `snakemake --lint`, which builds none, is unaffected.
    if not config:
        raise ConfigValidationError(
            "no configuration found. Copy config/min_config_sample.yaml to "
            "config/config.yaml and edit it, or generate one with "
            "config/config_designer.html, then run again."
        )

    # Initialize the list to hold all required input file paths
    expected_output = []

    # Loop over each species defined in the config (must be available in the global scope)
    for species in config.get("species", {}):
        if not config.get("species", {}).get(species, {}).get("execute", True):
            logging.info("Skipping species '%s' (execute: false)", species)
            continue
        # For each species, gather expected output file paths from all relevant processing stages
        expected_output += get_expected_output_read_module(species)
        expected_output += get_expected_output_reference_module(species)
        expected_output += get_expected_output_reveal_module_processing(species)
        expected_output += get_expected_output_summary_module(species)

    # Optionally skip files that already exist to avoid redundant processing
    expected_output = skip_existing_files(expected_output)

    # Log all determined inputs for debugging and traceability
    logging.info("Determined input for the 'all' rule:")
    for input in expected_output:
        logging.info("\t- Requesting: %s", input)

    # Return the complete list of input file paths
    return expected_output

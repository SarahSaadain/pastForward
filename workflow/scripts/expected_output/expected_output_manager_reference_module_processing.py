import logging

# -----------------------------------------------------------------------------------------------
# Get all expected output file paths for reference processing
def get_expected_output_reference_module(species):

    reference_module_cfg = config.get("pipeline", {}).get("reference_module", {})

    if reference_module_cfg.get("execute", True) == False:
        logging.info(f"Skipping reference processing for {species}. Disabled in config.")
        return []

    expected_outputs = []

    try:
    # Get all reference for the species
        references_list = get_references_ids_for_species(species)

    except Exception as e:
        # Print error if reference files are missing or inaccessible
        logging.error(e)
        return []

     # Get all individuals for the species
    individuals = get_individuals_for_species(species)

    analysis_cfg = reference_module_cfg.get("analysis", {})
    analysis_active = analysis_cfg.get("execute", True) == True
    analysis_settings = analysis_cfg.get("settings", {})

    filter_unmapped_reads_cfg = reference_module_cfg.get("filter_unmapped_reads", {})

    ref_mapper = index_mapper(config, "reference_module")

    for reference in references_list:

        # gzip copy of the mapping index (the index itself is temp(), see pack_index.smk)
        if individuals:
            ref_base = f"{species}/processed/reference_module/{reference}/reference/{reference}"
            expected_outputs += index_archives(f"{ref_base}.fa", ref_mapper, mmi=f"{ref_base}.mmi")

        # Endogenous reads data always generated
        expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/species_level/{species}/endogenous/{reference}_endogenous.csv")

        if analysis_active:
            if analysis_settings.get("create_plots", True) == True:
                expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/endogenous_reads/{species}_{reference}_endogenous_reads_bar_chart.png")
                expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/endogenous_reads/{species}_{reference}_raw_and_endogenous_reads_bar_chart.png")
                if analysis_settings.get("coverage_analysis", True) == True:
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_depth_coverage_violin.png")
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_depth_coverage_bar.png")
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_coverage_breadth_bar.png")
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/coverage/{species}_{reference}_individual_coverage_breadth_violin.png")
            else:
                logging.info(f"Skipping plots for species {species} and reference {reference}. Disabled in config.")

            if analysis_settings.get("species_multiqc", True) == True:
                expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/species_level/{species}_{reference}_multiqc.html")

            # Built only from files other steps already keep, so it never reruns anything.
            if analysis_settings.get("authenticity_summary", True) == True:
                expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/species_level/{species}/authenticity/{reference}_authenticity.tsv")

            # Opt-in, matching the reveal_module snp_analysis/indel_analysis precedent for
            # extra SNP-style analyses. Only the species-level combine target is requested
            # per method: Snakemake resolves backwards from it to whichever per-individual
            # inputs that method needs, so the method switch needs no branch here.
            if analysis_settings.get("snp_divergence_check", False) == True:
                for snp_divergence_method in get_snp_divergence_methods(analysis_settings):
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/species_level/{species}/snp_divergence/{reference}_combined_snp_divergence_{snp_divergence_method}.csv")
                    if analysis_settings.get("create_plots", True) == True:
                        expected_outputs.append(f"{species}/results/reference_module/{reference}/plots/snp_divergence/{species}_{reference}_snp_divergence_{snp_divergence_method}_bar.png")
        else:
            logging.info(f"Skipping analysis for species {species} and reference {reference}. Disabled in config.")

        for individual in individuals:

            expected_outputs.append(f"{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam")
            expected_outputs.append(f"{species}/results/reference_module/{reference}/mapped/{individual}_{reference}_final.bam.bai")

            # Sorted / deduplicated BAMs kept in results (opt-in). Dedup only when the step runs.
            mapped_dir = f"{species}/results/reference_module/{reference}/mapped/{individual}_{reference}"
            if reference_module_cfg.get("mapping", {}).get("settings", {}).get("keep_bam", False):
                expected_outputs += [f"{mapped_dir}_sorted.bam", f"{mapped_dir}_sorted.bam.bai"]
            dedup_cfg = reference_module_cfg.get("deduplication", {})
            if dedup_cfg.get("execute", True) and dedup_cfg.get("settings", {}).get("keep_bam", False):
                expected_outputs += [f"{mapped_dir}_sorted_dedupped.bam", f"{mapped_dir}_sorted_dedupped.bam.bai"]
            dr_cfg = reference_module_cfg.get("damage_rescaling", {})
            if dr_cfg.get("execute", True) and dr_cfg.get("settings", {}).get("keep_bam", False):
                expected_outputs += [f"{mapped_dir}_sorted_dedupped_rescaled.bam", f"{mapped_dir}_sorted_dedupped_rescaled.bam.bai"]

            if analysis_active:
                if analysis_settings.get("individual_multiqc", True) == True:
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}_{reference}_multiqc.html")

                if analysis_settings.get("damage_analysis", True) == True:
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/")
                    for mapdamage_table in ("misincorporation", "dnacomp"):
                        expected_outputs.append(f"{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/mapdamage/{individual}_{reference}.{mapdamage_table}.txt.gz")
                else:
                    logging.info(f"Skipping damage analysis for species {species} and individual {individual} to reference {reference}. Disabled in config.")
            else:
                logging.info(f"Skipping analysis for species {species} and individual {individual} to reference {reference}. Disabled in config.")

            if filter_unmapped_reads_cfg.get("execute", False) == True:
                action = filter_unmapped_reads_cfg.get("settings", {}).get("action", "keep")
                if action in ("keep", "remove"):
                    # keep: unmapped reads stay in the final BAM (no extra output)
                    # remove: _mapped_only.bam is a temp intermediate; get_final_bam copies to _final.bam
                    pass
                elif action == "extract_fastq":
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/unmapped/{individual}_{reference}_unmapped.fastq.gz")
                elif action == "extract_fasta":
                    expected_outputs.append(f"{species}/results/reference_module/{reference}/unmapped/{individual}_{reference}_unmapped.fasta.gz")
                else:
                    logging.warning(f"Unknown filter_unmapped_reads action '{action}' for {individual}/{reference}. Skipping.")
            else:
                logging.info(f"Skipping unmapped reads filtering for species {species}, individual {individual}, reference {reference}. Disabled in config.")

    return expected_outputs
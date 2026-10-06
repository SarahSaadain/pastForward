
import logging


def get_expected_output_reveal_module_processing(species):
    all_inputs = []

    if config.get("pipeline", {}).get("reveal_module", {}).get("execute", True) == False:
        logging.info(f"Skipping REVEAL processing for {species}. Disabled in config.")
        return []

    reveal_cfg = config.get("pipeline", {}).get("reveal_module", {})
    scg_sel_cfg = reveal_cfg.get("scg_selector", {})
    scg_sel_active = scg_sel_cfg.get("execute", True)

    # ── SCG selector outputs ──────────────────────────────────────────────────
    # Requested whenever scg_selector.execute is true AND no user-provided SCG
    # exists.  This supports "only create SCGs" workflows (no feature libraries
    # required) as well as the full REVEAL pipeline.
    if scg_sel_active and should_auto_determine_scg(species):
        all_inputs.append(f"{species}/results/reveal_module/scg/{species}_scg_ranked.tsv")
        all_inputs.append(f"{species}/results/reveal_module/scg/{species}_scg_ranked.json")

    # ── Feature-library / visualization outputs ───────────────────────────────
    try:
        feature_libraries = get_feature_library_ids_for_species(species)
    except Exception:
        logging.warning(
            f"No feature libraries found for {species}. "
            f"Skipping REVEAL analysis."
        )
        return all_inputs  # may still contain SCG ranking outputs

    # Determine whether an SCG library is available (user-provided or auto-determined)
    user_scgs = get_scg_library_file_list_for_species(species)
    has_scg = bool(user_scgs) or scg_sel_active

    if not has_scg:
        logging.warning(
            f"No SCG library available for {species} and scg_selector.execute is false. "
            f"Skipping REVEAL analysis. Provide a FASTA in "
            f"{species}/input/reveal_module/scg/ or set pipeline.reveal_module.scg_selector.execute: true."
        )
        return all_inputs

    # Only one user-provided SCG library is supported
    if len(user_scgs) > 1:
        raise ValueError(
            f"Multiple SCG libraries provided for {species}. "
            f"Only one SCG library is supported at a time."
        )

    visualization_settings = reveal_cfg.get("visualization", {}).get("settings", {})
    analysis_active = reveal_cfg.get("analysis", {}).get("execute", True)
    analysis_settings = reveal_cfg.get("analysis", {}).get("settings", {})
    individual_plots_mode = visualization_settings.get("individual_plots", "skip")
    comparison_plots_mode = visualization_settings.get("comparison_plots", "plot")
    coverage_analysis_active = analysis_active and analysis_settings.get("coverage_analysis", True)
    snp_analysis_active = analysis_active and analysis_settings.get("snp_analysis", False)
    indel_analysis_active = analysis_active and analysis_settings.get("indel_analysis", False)

    individuals = get_individuals_for_species(species)

    # REVEAL's covcompare/snpcompare/indelcompare all require at least two
    # stats files to compare, so cross-individual comparison outputs are only
    # meaningful (and only requested) when there is more than one individual.
    has_multiple_individuals = len(individuals) > 1
    if not has_multiple_individuals:
        logging.info(
            f"Only one individual found for {species}. "
            f"Skipping cross-individual comparison outputs (coverage/SNP/indel comparison)."
        )

    skip_low_coverage_individuals = (
        reveal_cfg.get("normalization", {})
        .get("settings", {})
        .get("skip_low_coverage_individuals", False)
    )

    if (
        reveal_cfg.get("visualization", {}).get("execute", True)
        and coverage_analysis_active
        and has_multiple_individuals
    ):
        all_inputs.append(f"{species}/results/reveal_module/{species}_reveal_coverage_comparison.tsv")

    keep_mapped_bam = reveal_cfg.get("mapping", {}).get("settings", {}).get("keep_mapped_bam", False)

    for feature_library in feature_libraries:

        if keep_mapped_bam:
            for individual in individuals:
                all_inputs.append(
                    f"{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam"
                )
                all_inputs.append(
                    f"{species}/processed/reveal_module/{feature_library}/mapped/{individual}_{feature_library}_and_scg.sorted.bam.bai"
                )

        if reveal_cfg.get("visualization", {}).get("execute", True):

            if coverage_analysis_active and has_multiple_individuals:
                # Species-level coverage stats
                all_inputs.append(
                    f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_coverage_comparison.tsv.gz"
                )
                all_inputs.append(
                    f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_flagged_seqids.tsv"
                )

            if coverage_analysis_active:
                if skip_low_coverage_individuals:
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_excluded_individuals.tsv"
                    )

                if comparison_plots_mode == "plot":
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plots_facet/"
                    )
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plotables_facet.tar.gz"
                    )
                elif comparison_plots_mode == "plotable_only":
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_plotables_facet.tar.gz"
                    )

            if snp_analysis_active and has_multiple_individuals:
                all_inputs.append(
                    f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_snp_comparison.tsv.gz"
                )

            if indel_analysis_active and has_multiple_individuals:
                all_inputs.append(
                    f"{species}/results/reveal_module/{feature_library}/visualization/species_level/{species}_{feature_library}_indel_comparison.tsv.gz"
                )

            for individual in individuals:
                if coverage_analysis_active:
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.tsv.gz"
                    )
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.tsv.gz"
                    )
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_coverage.normalized.stats.tsv"
                    )

                    if individual_plots_mode == "plot":
                        all_inputs.append(
                            f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable.tar.gz"
                        )
                        all_inputs.append(
                            f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plots/"
                        )
                    elif individual_plots_mode == "plotable_only":
                        all_inputs.append(
                            f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_plotable.tar.gz"
                        )

                if snp_analysis_active:
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_snpstats.tsv.gz"
                    )

                if indel_analysis_active:
                    all_inputs.append(
                        f"{species}/results/reveal_module/{feature_library}/visualization/individual_level/{individual}_indelstats.tsv.gz"
                    )

    return all_inputs

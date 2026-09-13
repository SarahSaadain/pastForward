# =================================================================================================
#     Species Check (discovered species/individuals/references/... — see `pastForward check`)
# =================================================================================================
# Included after file_manager.py so all file_manager functions are in the Snakemake namespace
# with config in scope — no imports required.

import logging

try:
    from snakemake_interface_executor_plugins.settings import ExecMode

    _is_snakemake_subprocess = workflow.exec_mode == ExecMode.SUBPROCESS
except ImportError:
    # `pastForward check` execs this file in-process (scripts/pipeline_namespace.py), where
    # there is no Snakemake and so no spawned subprocess to stay quiet for. Falling back
    # keeps check/preview working without Snakemake installed - the comparison above is the
    # only thing in the whole in-process path that needs it.
    _is_snakemake_subprocess = False

if not _is_snakemake_subprocess:

    species_section = config.get("species", {})
    species_lines = []
    for sname, sdata in species_section.items():
        display_name = f"{sdata.get('name', sname)} [{sname}]"
        if not sdata.get("execute", True):
            species_lines.append(f"- {display_name} [SKIPPED — execute: false]")
            continue
        lines = [f"- {display_name}"]

        try:
            all_refs = _discover_all_reference_file_list_for_species(sname)
            refs = get_reference_file_list_for_species(sname)
            ignored_refs = [(rid, rp) for rid, rp in all_refs if rid not in {r[0] for r in refs}]
            lines.append(f"    References ({len(refs)}):")
            for ref_id, ref_path in refs:
                lines.append(f"      - {ref_id}: {ref_path}")
            if ignored_refs:
                lines.append(f"    References ignored ({len(ignored_refs)}) [not selected in config]:")
                for ref_id, ref_path in ignored_refs:
                    lines.append(f"      - {ref_id}: {ref_path}")
        except ConfigValidationError:
            raise
        except Exception:
            lines.append("    References: (none found)")

        try:
            all_individuals = _discover_all_individuals_for_species(sname)
            individuals = get_individuals_for_species(sname)
            ignored_individuals = [ind for ind in all_individuals if ind not in set(individuals)]
            lines.append(f"    Individuals ({len(individuals)}):")
            for ind in individuals:
                lines.append(f"      - {ind}")
                try:
                    samples = get_samples_for_species_individual(sname, ind)
                    lines.append(f"        Samples ({len(samples)}):")
                    for s in samples:
                        lines.append(f"          - {s}")
                        try:
                            reads = get_raw_reads_for_sample(sname, s)
                            lines.append(f"            Reads ({len(reads)}):")
                            for r in reads:
                                lines.append(f"              {r}")
                        except ValueError as e:
                            lines.append(f"            Reads: (ERROR — {e})")
                        except Exception:
                            lines.append(f"            Reads: (reads not found)")
                except Exception:
                    lines.append(f"        Samples: (samples not found)")
            if ignored_individuals:
                lines.append(f"    Individuals ignored ({len(ignored_individuals)}) [not selected in config]:")
                for ind in ignored_individuals:
                    lines.append(f"      - {ind}")
        except ConfigValidationError:
            raise
        except ValueError as e:
            lines.append(f"    Individuals: (ERROR — {e})")
        except Exception:
            lines.append("    Individuals: (none found)")

        # Outside the try above on purpose: when every read name is bad, individual discovery
        # finds nothing (or raises), and these lists are exactly what explains why.
        unmatched_reads = _discover_unmatched_read_files_for_species(sname)
        if unmatched_reads:
            lines.append(f"    WARNING: reads not used ({len(unmatched_reads)}), names don't follow the raw read naming convention:")
            for r in unmatched_reads:
                lines.append(f"      - {r} ({get_read_name_problem(os.path.basename(r))})")
        uncompressed_reads = _discover_uncompressed_fastq_files_for_species(sname)
        if uncompressed_reads:
            lines.append(f"    Reads ignored ({len(uncompressed_reads)}) [uncompressed .fastq/.fq — pipeline only processes {' or '.join(RAW_READ_EXTENSIONS)}]:")
            for r in uncompressed_reads:
                lines.append(f"      - {r}")

        try:
            all_feat_libs = _discover_all_feature_library_file_list_for_species(sname)
            feat_libs = get_feature_library_file_list_for_species(sname)
            ignored_feat_libs = [(lid, lp) for lid, lp in all_feat_libs if lid not in {l[0] for l in feat_libs}]
            lines.append(f"    Feature Libraries ({len(feat_libs)}):")
            for lib_id, lib_path in feat_libs:
                lines.append(f"      - {lib_id}: {lib_path}")
            if ignored_feat_libs:
                lines.append(f"    Feature Libraries ignored ({len(ignored_feat_libs)}) [not selected in config]:")
                for lib_id, lib_path in ignored_feat_libs:
                    lines.append(f"      - {lib_id}: {lib_path}")
        except ConfigValidationError:
            raise
        except Exception:
            lines.append("    Feature Libraries: (none found)")

        scg_libs = get_scg_library_file_list_for_species(sname)
        if scg_libs:
            lines.append(f"    SCG Libraries ({len(scg_libs)}):")
            for lib_id, lib_path in scg_libs:
                lines.append(f"      - {lib_id}: {lib_path}")
        else:
            _scg_sel_active = config.get("pipeline", {}).get("reveal_module", {}).get("scg_selector", {}).get("execute", True)
            _lineage = config.get("species", {}).get(sname, {}).get("lineage")
            if not _scg_sel_active:
                lines.append("    SCG Libraries: (none provided; scg_selector disabled)")
            elif not _lineage:
                lines.append("    SCG Libraries: (none provided; skipping auto-determination — no lineage configured for this species)")
            else:
                _config_ref = config.get("species", {}).get(sname, {}).get("scg_reference")
                if _config_ref:
                    lines.append(f"    SCG Libraries: (will be auto-determined via BUSCO [{_lineage}]; reference: {_config_ref})")
                else:
                    try:
                        refs = get_reference_file_list_for_species(sname)
                        if len(refs) == 1:
                            lines.append(f"    SCG Libraries: (will be auto-determined via BUSCO [{_lineage}]; reference: {refs[0][1]})")
                        elif len(refs) > 1:
                            lines.append(
                                f"    SCG Libraries: (will be auto-determined via BUSCO [{_lineage}] — "
                                f"WARNING: {len(refs)} references found, set "
                                f"species.{sname}.scg_reference in config)"
                            )
                        else:
                            lines.append(
                                f"    SCG Libraries: (will be auto-determined via BUSCO [{_lineage}] — "
                                f"WARNING: no reference found in {sname}/input/reference_module/)"
                            )
                    except Exception as e:
                        lines.append(f"    SCG Libraries: (will be auto-determined via BUSCO [{_lineage}] — WARNING: {e})")

        _comp_enabled = config.get("pipeline", {}).get("reveal_module", {}).get("mapping", {}).get("settings", {}).get("competitive_mapping", False)
        if _comp_enabled:
            try:
                comp_fasta = get_competition_fasta_for_species(sname)
                if comp_fasta:
                    lines.append(f"    Competition FASTA: {comp_fasta}")
                else:
                    lines.append(f"    Competition FASTA: (MISSING — place a FASTA in {sname}/input/reveal_module/competition/)")
            except ValueError as e:
                lines.append(f"    Competition FASTA: (ERROR — {e})")

        species_lines.append("\n".join(lines))

    logging.info("Detected species (%d):\n%s", len(species_section), "\n\n".join(species_lines))

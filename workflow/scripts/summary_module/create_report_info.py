"""
Two MultiQC custom-content sections for every pastForward report:

* tool versions: pastForward, ECMSD (with its database), REVEAL
* raw results: where the files of each active step live on disk

Both are written as `*_mqc.json` files, which MultiQC picks up on its own. The
functions are pure so the unit tests need neither Snakemake nor MultiQC.
"""

import html
import json
import os
import sys
from datetime import datetime, timezone

DESCRIPTION_VERSIONS = (
    "Versions of pastForward, ECMSD (with the database it screened against) and REVEAL "
    "used for this report."
)
DESCRIPTION_RAW = (
    "Where to find the raw files of each step that was switched on in the config. "
    "Paths are relative to the project folder."
)

# ECMSD reads these three files. The first one is the reference sequences.
_ECMSD_DB_LABELS = {
    "mitochondrion_refseq_taxid_masked.fna.gz": "Mitochondrial reference sequences",
    "NCBI_taxdump/nodes.dmp": "NCBI taxonomy nodes",
    "NCBI_taxdump/names.dmp": "NCBI taxonomy names",
}


def _on(node, *keys, default=True):
    """config["pipeline"][keys...]; a missing or empty section on the way counts as missing."""
    for key in keys[:-1]:
        node = node.get(key) or {}
    return node.get(keys[-1], default)


def read_version(path):
    """First non-empty line of a `--version` output, e.g. 'ECMSD version 1.2.0'."""
    try:
        with open(path) as f:
            for line in f:
                if line.strip():
                    return line.strip()
    except OSError:
        pass
    return "unknown"


def _file_info(path):
    """(date, size in MB) of a file, or ('missing', '') when it is not there."""
    try:
        stat = os.stat(path)
    except OSError:
        return "missing", ""
    date = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    return date, f"{stat.st_size / 1e6:.1f} MB"


def tool_rows(
    pipeline_version, ecmsd=None, reveal=None, ecmsd_db=None, taxonomic_hierarchy=None
):
    """
    Rows of (name, value, note). `ecmsd` and `reveal` are dicts with `version` and
    `source`, or None when that tool is not part of the run. `ecmsd_db` is the database
    folder, or None.
    """
    rows = [("pastForward", pipeline_version, "")]
    if ecmsd:
        rows.append(("ECMSD", ecmsd["version"], ecmsd["source"]))
    if ecmsd and ecmsd_db:
        for relative, label in _ECMSD_DB_LABELS.items():
            date, size = _file_info(os.path.join(ecmsd_db, relative))
            rows.append((f"ECMSD database: {label}", f"file date {date}", size))
        rows.append(("ECMSD database folder", ecmsd_db, ""))
    if ecmsd and taxonomic_hierarchy:
        rows.append(("ECMSD taxonomic level", taxonomic_hierarchy, ""))
    if reveal:
        rows.append(("REVEAL", reveal["version"], reveal["source"]))
    return rows


def raw_result_rows(config, species, references):
    """
    (step, folder, what is in it) for each step that the config switches on.
    Mirrors the switches of the expected output managers, coarsely: a folder is listed
    when the step that fills it runs, not per file.
    """
    pipeline = config.get("pipeline") or {}
    rows = []

    if _on(pipeline, "read_module", "execute"):
        base = f"{species}/results/read_module"
        rows.append(
            ("Merged reads", f"{base}/reads_merged/", "One fastq per individual")
        )
        if _on(pipeline, "read_module", "adapter_removal", "execute") and _on(
            pipeline,
            "read_module",
            "adapter_removal",
            "settings",
            "keep_reads",
            default=False,
        ):
            rows.append(
                (
                    "Adapter-removed reads",
                    f"{base}/reads_trimmed_final/",
                    "Reads after adapter removal",
                )
            )
        # Same condition as the expected output manager: either step produces the final reads.
        if _on(
            pipeline,
            "read_module",
            "quality_filtering",
            "settings",
            "keep_reads",
            default=False,
        ) and (
            _on(pipeline, "read_module", "adapter_removal", "execute")
            or _on(pipeline, "read_module", "quality_filtering", "execute")
        ):
            rows.append(
                (
                    "Final reads",
                    f"{base}/reads_final/",
                    "Reads after adapter removal and quality filtering",
                )
            )
        rows.append(
            (
                "Read statistics",
                f"{base}/statistics/",
                "Read counts and merged/unmerged/unpaired composition (CSV)",
            )
        )
        if _on(pipeline, "read_module", "analysis", "execute"):
            rows.append(
                (
                    "Read QC",
                    f"{base}/reads_*/fastqc/ and {base}/{species}_multiqc_*.html",
                    "FastQC reports per read stage and one MultiQC report per stage",
                )
            )
            if _on(pipeline, "read_module", "analysis", "settings", "create_plots"):
                rows.append(("Read plots", f"{base}/plots/", "Read count plots (PNG)"))
        if _on(pipeline, "read_module", "taxonomic_screening", "execute"):
            tools = ("read_module", "taxonomic_screening", "tools")
            if _on(pipeline, *tools, "ecmsd", "execute"):
                rows.append(
                    (
                        "ECMSD",
                        f"{base}/taxonomic_screening/ecmsd/",
                        "Per sample: mitochondrial hit tables, PAF, coverage, plots",
                    )
                )
            if _on(pipeline, *tools, "centrifuge", "execute"):
                rows.append(
                    (
                        "Centrifuge",
                        f"{base}/taxonomic_screening/centrifuge/",
                        "Per sample: classification report, taxon counts, raw output",
                    )
                )

    if _on(pipeline, "reference_module", "execute"):
        analysis_on = _on(pipeline, "reference_module", "analysis", "execute")
        settings = (
            _on(pipeline, "reference_module", "analysis", "settings", default={}) or {}
        )
        for reference in references:
            base = f"{species}/results/reference_module/{reference}"
            tag = f" ({reference})"
            rows.append(
                (
                    f"Final BAM{tag}",
                    f"{base}/mapped/",
                    "Final BAM and index per individual (rescaled, deduplicated or sorted, "
                    "whichever steps ran); kept sorted/deduplicated BAMs sit next to it",
                )
            )
            rows.append(
                (
                    f"Endogenous reads{tag}",
                    f"{base}/analytics/species_level/{species}/endogenous/",
                    "Endogenous read counts per individual (CSV)",
                )
            )
            if analysis_on:
                rows.append(
                    (
                        f"Per-individual analyses{tag}",
                        f"{base}/analytics/individual_level/",
                        "Per individual: samtools stats, Qualimap, preseq, mapDamage, DeDup, coverage",
                    )
                )
                if settings.get("create_plots", True):
                    rows.append(
                        (
                            f"Reference plots{tag}",
                            f"{base}/plots/",
                            "Endogenous, coverage and SNP divergence plots (PNG)",
                        )
                    )
                if settings.get("authenticity_summary", True):
                    rows.append(
                        (
                            f"Authenticity table{tag}",
                            f"{base}/analytics/species_level/{species}/authenticity/",
                            "One row per individual with an ok/check verdict (TSV)",
                        )
                    )
                if settings.get("snp_divergence_check", False):
                    rows.append(
                        (
                            f"SNP divergence{tag}",
                            f"{base}/analytics/species_level/{species}/snp_divergence/",
                            "Combined SNP divergence tables (CSV)",
                        )
                    )
            if _on(
                pipeline,
                "reference_module",
                "filter_unmapped_reads",
                "execute",
                default=False,
            ) and (
                _on(
                    pipeline,
                    "reference_module",
                    "filter_unmapped_reads",
                    "settings",
                    "action",
                    default="keep",
                )
                in ("extract_fastq", "extract_fasta")
            ):
                rows.append(
                    (
                        f"Unmapped reads{tag}",
                        f"{base}/unmapped/",
                        "Unmapped reads per individual",
                    )
                )

    if _on(pipeline, "reveal_module", "execute"):
        base = f"{species}/results/reveal_module"
        if _on(pipeline, "reveal_module", "scg_selector", "execute"):
            rows.append(
                (
                    "Single-copy genes",
                    f"{base}/scg/",
                    "Ranked SCG table (TSV and JSON), when the pipeline picked the SCGs",
                )
            )
        rows.append(
            (
                "REVEAL feature copy number",
                f"{base}/",
                "Species comparison table, and per feature library: normalised coverage, SNP/indel stats and plots under <library>/visualization/",
            )
        )

    if _on(pipeline, "summary_module", "execute"):
        base = f"{species}/results/summary"
        rows.append(
            (
                "Summary reports",
                f"{base}/",
                "Species-level and per-individual MultiQC reports (HTML)",
            )
        )

    return rows


def _html_table(header, rows, code_columns=()):
    head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
    body = ""
    for row in rows:
        cells = ""
        for index, value in enumerate(row):
            text = html.escape(str(value))
            cells += (
                f"<td><code>{text}</code></td>"
                if index in code_columns and text
                else f"<td>{text}</td>"
            )
        body += f"<tr>{cells}</tr>"
    return f'<table class="table table-condensed"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def mqc_section(section_id, name, description, table_html):
    return {
        "id": section_id,
        "section_name": name,
        "description": description,
        "plot_type": "html",
        "data": table_html,
    }


def write_sections(versions_path, raw_path, versions, raw):
    with open(versions_path, "w") as f:
        json.dump(
            mqc_section(
                "pf_tool_versions",
                "Tool versions",
                DESCRIPTION_VERSIONS,
                _html_table(["Tool", "Version", "Note"], versions),
            ),
            f,
            indent=2,
        )
    with open(raw_path, "w") as f:
        json.dump(
            mqc_section(
                "pf_raw_results",
                "Where to find the raw results",
                DESCRIPTION_RAW,
                _html_table(["Step", "Folder", "Contents"], raw, code_columns=(1,)),
            ),
            f,
            indent=2,
        )


if __name__ == "__main__":
    sys.stdout = sys.stderr = open(snakemake.log[0], "w")
    params = snakemake.params
    ecmsd = reveal = None
    if "ecmsd_version" in snakemake.input.keys():
        ecmsd = {
            "version": read_version(snakemake.input.ecmsd_version),
            "source": params.ecmsd_source,
        }
    if "reveal_version" in snakemake.input.keys():
        reveal = {
            "version": read_version(snakemake.input.reveal_version),
            "source": params.reveal_source,
        }
    write_sections(
        snakemake.output.versions,
        snakemake.output.raw_results,
        tool_rows(
            params.pipeline_version,
            ecmsd,
            reveal,
            params.ecmsd_db if ecmsd else None,
            params.ecmsd_hierarchy if ecmsd else None,
        ),
        raw_result_rows(
            snakemake.config, snakemake.wildcards.species, list(params.references)
        ),
    )

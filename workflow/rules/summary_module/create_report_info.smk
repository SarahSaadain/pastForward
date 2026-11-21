####################################################
# Two extra MultiQC sections shared by every report: tool versions (pastForward, ECMSD and
# its database, REVEAL) and where the raw results of each active step live. Written as
# *_mqc.json custom content, see scripts/summary_module/create_report_info.py.
# A tool upgrade inside an existing conda env does not rerun these rules (mtime triggers
# only): delete resources/tool_versions/ to refresh the versions. Switching version_source
# uses a new file, so it never shows the old source's version.
####################################################


rule get_ecmsd_version:
    output:
        _ECMSD_VERSION_FILE,
    log:
        f"{_ECMSD_VERSION_FILE}.log",
    conda:
        ECMSD_CONDA_ENV
    message:
        "Reading the ECMSD version."
    shell:
        """
        # A tool without --version must not stop every report.
        ECMSD --version >"{output}" 2>"{log}" || echo unknown >"{output}"
        """


rule get_reveal_version:
    output:
        _REVEAL_VERSION_FILE,
    log:
        f"{_REVEAL_VERSION_FILE}.log",
    conda:
        REVEAL_CONDA_ENV
    message:
        "Reading the REVEAL version."
    shell:
        """
        REVEAL --version >"{output}" 2>"{log}" || echo unknown >"{output}"
        """


rule create_report_info:
    input:
        unpack(create_report_info_input),
    output:
        versions="{species}/results/summary/report_info/{species}_tool_versions_mqc.json",
        raw_results="{species}/results/summary/report_info/{species}_raw_results_mqc.json",
    log:
        "{species}/results/summary/report_info/{species}_report_info.log",
    conda:
        "../../envs/python_and_r.yaml"
    params:
        pipeline_version=__version__,
        ecmsd_source=_setting(
            "read_module",
            "taxonomic_screening",
            "tools",
            "ecmsd",
            "settings",
            "version_source",
            default="conda",
        ),
        reveal_source=_setting(
            "reveal_module", "settings", "version_source", default="conda"
        ),
        ecmsd_db=_ecmsd_db_folder,
        ecmsd_hierarchy=_ecmsd_taxonomic_hierarchy,
        references=lambda wildcards: _references_for_multiqc(wildcards.species),
    message:
        "Creating the tool version and raw results sections for the {wildcards.species} reports."
    script:
        "../../scripts/summary_module/create_report_info.py"

####################################################
# Module-level settings for rules
####################################################

_comp_execute = (
    config.get("pipeline", {})
    .get("reveal_module", {})
    .get("mapping", {})
    .get("settings", {})
    .get("competitive_mapping", False)
)

####################################################
# Snakemake rules
####################################################


rule clean_feature_library_name:
    input:
        clean_feature_library_name_input,
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}.clean.fasta"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}.clean.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Preparing TE library for {wildcards.species}"
    shell:
        # -s/--no-symlinks keeps this lexical (only "." / ".." are resolved, no symlink is
        # followed/flattened) so the link survives the whole pastForward project folder being
        # moved or renamed - it only breaks if the actual target (e.g. a configured
        # feature_library_dir) is itself moved.
        """
        ln -sf "$(realpath -s --relative-to="$(dirname "{output}")" "{input}")" "{output}" >"{log}" 2>&1
        """


rule prepare_feature_library:
    input:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}.clean.fasta",
    output:
        temp(
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}.suffixed.fasta"
        ),
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}.suffixed.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Preparing TE library for {wildcards.species}"
    shell:
        # remove trailing whitespace from headers and append _fle to each header
        """
        sed -E '/^>/ s/[[:space:]]//g; /^>/ s/(_fle)?$/_fle/' "{input}" >"{output}" 2>"{log}"
        """


rule clean_scg_library_name:
    input:
        clean_scg_library_name_input,
    output:
        # Deliberately not "{species}/processed/reveal_module/{scg_library}/library/...": that shape
        # is what rule clean_feature_library_name matches, and a user-provided SCG FASTA literally
        # named "scg.fasta" (a very natural choice) makes scg_library == "scg" too, which used to
        # make both rules produce the exact same output path (AmbiguousRuleException). The flattened
        # "scg_library/" folder here has one path segment fewer than that pattern, so the two can
        # never collide regardless of what the library file is named.
        temp("{species}/processed/reveal_module/scg_library/{scg_library}.clean.fasta"),
    log:
        "{species}/processed/reveal_module/scg_library/{scg_library}.clean.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Preparing SCG library for {wildcards.species}"
    shell:
        # -s/--no-symlinks: see clean_feature_library_name above.
        """
        ln -sf "$(realpath -s --relative-to="$(dirname "{output}")" "{input}")" "{output}" >"{log}" 2>&1
        """


rule prepare_scg_library:
    input:
        "{species}/processed/reveal_module/scg_library/{scg_library}.clean.fasta",
    output:
        temp(
            "{species}/processed/reveal_module/scg_library/{scg_library}.suffixed.fasta"
        ),
    log:
        "{species}/processed/reveal_module/scg_library/{scg_library}.suffixed.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Preparing SCG library for {wildcards.species}"
    shell:
        # remove trailing whitespace from headers and append _scg to each header
        """
        sed -E '/^>/ s/[[:space:]]//g; /^>/ s/(_scg)?$/_scg/' "{input}" >"{output}" 2>"{log}"
        """


if _comp_execute:

    rule create_no_comp_library:
        input:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
        output:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.no_comp.suffixed.fasta",
        log:
            "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.no_comp.suffixed.log",
        message:
            "Removing competition sequences from combined library for REVEAL ({wildcards.species})"
        shell:
            # Skip any FASTA entry whose header ends in _comp (header + its sequence lines)
            """
            awk -f workflow/scripts/reveal_module/mapping/filter_out_comp_fasta_entries.awk "{input}" >"{output}" 2>"{log}"
            """

    rule prepare_competition_library:
        input:
            get_competition_fasta_input,
        output:
            temp(
                "{species}/processed/reveal_module/competition/competition.suffixed.fasta"
            ),
        log:
            "{species}/processed/reveal_module/competition/competition.suffixed.log",
        message:
            "Preparing competition library for {wildcards.species}"
        shell:
            # remove trailing whitespace from headers and append _comp to each header
            """
            sed -E '/^>/ s/[[:space:]]//g; /^>/ s/(_comp)?$/_comp/' "{input}" >"{output}" 2>"{log}"
            """


rule combine_scg_and_ref_library:
    input:
        scg=lambda wildcards: f"{wildcards.species}/processed/reveal_module/scg_library/{get_effective_scg_library_id_for_species(wildcards.species)}.suffixed.fasta",
        fl="{species}/processed/reveal_module/{feature_library}/library/{feature_library}.suffixed.fasta",
        comp=lambda wildcards: (
            f"{wildcards.species}/processed/reveal_module/competition/competition.suffixed.fasta"
            if _comp_execute
            else []
        ),
    output:
        library="{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.fasta",
    log:
        "{species}/processed/reveal_module/{feature_library}/library/{feature_library}_and_scg.suffixed.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Concatenating SCG and Feature libraries for {wildcards.species}"
    shell:
        """
        cat "{input.scg}" "{input.fl}" {input.comp} >"{output.library}" 2>"{log}"
        """

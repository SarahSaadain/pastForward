####################################################
# Authenticity triage table: one row per individual, per species and reference.
#
# Collects numbers earlier steps already keep on disk (samtools stats, endogenous CSV,
# merged DeDup JSON, mapDamage tables, coverage CSV). Each input group is requested only
# when the step that makes it is switched on anyway (see
# create_authenticity_summary_input in common.smk), so adding the table to an existing
# project runs this one job and nothing else.
####################################################

_authenticity_settings = (
    config.get("pipeline", {})
    .get("reference_module", {})
    .get("analysis", {})
    .get("settings", {})
)


####################################################
# Snakemake rules
####################################################


# Rule: Combine per-individual authenticity numbers and give each individual a verdict
rule create_authenticity_summary:
    input:
        unpack(create_authenticity_summary_input),
    output:
        tsv="{species}/results/reference_module/{reference}/analytics/species_level/{species}/authenticity/{reference}_authenticity.tsv",
    log:
        "{species}/results/reference_module/{reference}/analytics/species_level/{species}/authenticity/{reference}_authenticity.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        # Same individual list and order as every input group above.
        individuals=lambda wildcards: get_individuals_for_species(wildcards.species),
        n_samples=lambda wildcards: [
            len(get_samples_for_species_individual(wildcards.species, individual))
            for individual in get_individuals_for_species(wildcards.species)
        ],
        # Only thresholds set in config. The defaults live in the script.
        threshold_overrides={
            key.removeprefix("authenticity_"): value
            for key, value in _authenticity_settings.items()
            if key.startswith("authenticity_") and key != "authenticity_summary"
        },
    message:
        "Creating authenticity summary for species {wildcards.species} and reference {wildcards.reference}"
    script:
        "../../../scripts/reference_module/analytics/statistics/create_authenticity_summary.py"

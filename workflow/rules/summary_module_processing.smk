# create_multiqc_species.smk
# Contains rules for generating MultiQC reports for each species.
include: "summary_module/create_multiqc_species.smk"
# create_multiqc_species_individual.smk
# Contains rules for generating MultiQC reports for each species and individual.
include: "summary_module/create_multiqc_species_individual.smk"
# create_report_info.smk
# Tool versions and raw result locations, added to every MultiQC report.
include: "summary_module/create_report_info.smk"

#
rule summarize_coverage:
    input:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/coverage/{individual}_{reference}_coverage_analysis.csv",
    output:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_summary.tsv",
    log:
        "{species}/results/reference_module/{reference}/analytics/individual_level/{individual}/multiqc_custom_content/{individual}_{reference}_coverage_summary.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        individual="{individual}",
        reference="{reference}",
    script:
        "../../../scripts/summary_module/summarize_coverage.py"

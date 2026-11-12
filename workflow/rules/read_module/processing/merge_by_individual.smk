####################################################
# Snakemake rules
####################################################


# Rule: Merge quality-filtered reads by individual
rule merge_reads_by_individual:
    input:
        merge_reads_by_individual_input,
    output:
        "{species}/results/read_module/reads_merged/{individual}.fastq.gz",
    log:
        "{species}/processed/read_module/reads_merged/{individual}_merge_reads.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Merging individual {wildcards.individual} of species {wildcards.species}."
    shell:
        """
        echo "Merging quality-filtered reads for individual {wildcards.individual} of species {wildcards.species}..." >"{log}"
        echo "Input files:" >>"{log}"
        for f in {input}; do
            echo "  $f" >>"{log}"
        done
        echo "Output file: {output}" >>"{log}"

        set -- {input}
        if [ $# -eq 1 ]; then
            """
        # a temp() file, or with keep_reads the results/ copy (merge_reads_by_individual_input)
        + _hardlink_or_copy("$1", "{output}", True)
        + """
        else
            cat "$@" >"{output}"
        fi
        echo "Merging completed for individual {wildcards.individual} of species {wildcards.species}." >>"{log}"
        """

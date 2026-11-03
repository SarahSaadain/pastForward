####################################################
# Snakemake rules
####################################################
# Determine index path: use config if provided, otherwise use downloaded
# We use the index from https://benlangmead.github.io/aws-indexes/centrifuge
# Refseq: bacteria, archaea, viral, human
_configured_index = _setting(
    "read_module", "taxonomic_screening", "tools", "centrifuge", "settings", "index"
)


rule download_centrifuge_index:
    output:
        expand("resources/centrifuge_index/p+h+v.{ext}.cf", ext=["1", "2", "3"]),
    log:
        "resources/centrifuge_index/download_centrifuge_index.log",
    conda:
        "../../../envs/wget.yaml"
    params:
        url="https://genome-idx.s3.amazonaws.com/centrifuge/p%2Bh%2Bv.tar.gz",
        outdir=lambda wildcards, output: os.path.dirname(output[0]),
    message:
        "Downloading Centrifuge index"
    shell:
        """
        echo "Downloading Centrifuge index from {params.url} to {params.outdir}" >"{log}" 2>&1
        echo "This may take a while depending on your internet connection..." >>"{log}" 2>&1

        mkdir -p "{params.outdir}"
        wget -O "{params.outdir}/p+h+v.tar.gz" "{params.url}" >>"{log}" 2>&1

        echo "Extracting Centrifuge index..." >>"{log}" 2>&1
        tar -xzf "{params.outdir}/p+h+v.tar.gz" -C "{params.outdir}" >>"{log}" 2>&1

        echo "Cleaning up downloaded archive..." >>"{log}" 2>&1
        rm "{params.outdir}/p+h+v.tar.gz"
        """


rule centrifuge_taxonomic_screening:
    input:
        fastq="{species}/processed/read_module/reads_quality_filtered/{sample}_quality_filtered_final.fastq.gz",
        index=lambda wildcards: (
            []
            if _configured_index
            else expand(
                "resources/centrifuge_index/p+h+v.{ext}.cf", ext=["1", "2", "3"]
            )
        ),
    output:
        output=temp(
            "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_output.tsv"
        ),
        report="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_report.tsv",
    log:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge.log",
    conda:
        _setting(
            "read_module",
            "taxonomic_screening",
            "tools",
            "centrifuge",
            "settings",
            "conda_env",
            default="../../../envs/centrifuge.yaml",
        )
    threads: 15
    params:
        index=lambda wildcards: (
            _configured_index
            if _configured_index
            else "resources/centrifuge_index/p+h+v"
        ),
    message:
        "Running Centrifuge taxonomic screening for {input.fastq}"
    shell:
        """
        centrifuge \
            -x "{params.index}" \
            -U "{input.fastq}" \
            -S "{output.output}" \
            --report-file "{output.report}" \
            --threads {threads} >"{log}" 2>&1
        """


rule analyze_centrifuge_report_taxon_counts:
    input:
        centrifuge_out="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_output.tsv",
    output:
        taxon_counts="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_taxon_counts.tsv",
    log:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_taxon_counts.log",
    conda:
        "../../../envs/python_and_r.yaml"
    message:
        "Counting taxon occurrences in {input.centrifuge_out}"
    shell:
        r"""
        awk '$3 != 0 {{print $3}}' "{input.centrifuge_out}" \
            | sort \
            | uniq -c \
            | sort -nr \
                >"{output.taxon_counts}" 2>"{log}"
        """


rule analyze_centrifuge_report_proportions:
    input:
        report="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_report.tsv",
        count_reads="{species}/processed/read_module/statistics/{sample}_quality_filtered.count",
    output:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_proportions.tsv",
    log:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_proportions.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        sample="{sample}",
    script:
        "../../../scripts/read_module/taxonomic_screening/check_taxonomic_screening_centrifuge_script_analyze_centrifuge_report_proportions.py"


rule analyze_centrifuge_report_top_taxa:
    input:
        report="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_report.tsv",
    output:
        top10_unique="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_unique_taxa.tsv",
        top10_total="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top10_total_taxa.tsv",
    log:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_top_taxa.log",
    conda:
        "../../../envs/python_and_r.yaml"
    params:
        sample="{sample}",
        include_human=_setting(
            "read_module",
            "taxonomic_screening",
            "tools",
            "centrifuge",
            "settings",
            "include_human_taxid",
            default=False,
        ),
    script:
        "../../../scripts/read_module/taxonomic_screening/check_taxonomic_screening_centrifuge_script_analyze_centrifuge_report_top_taxa.py"


rule compress_centrifuge_output:
    input:
        tsv="{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_output.tsv",
    output:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_output.tsv.gz",
    log:
        "{species}/results/read_module/taxonomic_screening/centrifuge/{individual}/{sample}/{sample}_centrifuge_output_compress.log",
    conda:
        "../../../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing Centrifuge output for {wildcards.sample}"
    shell:
        'pigz -p {threads} -c "{input.tsv}" > "{output}" 2> "{log}"'

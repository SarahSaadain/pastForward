####################################################
# Snakemake rules
####################################################
from scripts.index_compression import INDEX_REGEX


# Mapping indexes are temp(); this keeps a gzip copy. The mtime is copied from the index so
# that the unpacked index, at the next workflow load, looks as old as the original (see
# scripts/index_compression.py).
rule pack_index:
    input:
        "{index}",
    output:
        "{index}.gz",
    log:
        "{index}.pack.log",
    wildcard_constraints:
        index=INDEX_REGEX,
    conda:
        "../envs/pigz.yaml"
    threads: 4
    message:
        "Compressing mapping index {input}"
    shell:
        """
        pigz -p {threads} -c "{input}" >"{output}" 2>"{log}"
        touch -r "{input}" "{output}"
        """

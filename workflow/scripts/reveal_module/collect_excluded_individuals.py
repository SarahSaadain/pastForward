with open(snakemake.output.tsv, "w") as out:
    out.write("individual\treason\n")
    for individual, path in zip(snakemake.params.individuals, snakemake.input.reasons):
        reason = open(path).read().strip()
        if reason:
            out.write(f"{individual}\t{reason}\n")

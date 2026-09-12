import sys


def build_regions_bed(fai_file, bed_file, target_bases, min_contig_length):
    """
    Select a deterministic slice of the reference to call SNPs on.

    Contigs are taken largest first until `target_bases` is reached, so the same
    region set is produced for every individual of the cohort. That is what makes
    the divergence scores comparable: the statistic is cohort-relative, so all
    individuals have to be measured on the same genomic regions.

    Args:
        fai_file (str): Path to the reference `.fa.fai` index.
        bed_file (str): Path to the BED file to write.
        target_bases (int): Base budget. 0 means use the whole reference.
        min_contig_length (int): Contigs shorter than this are never selected.
    """
    contigs = []

    with open(fai_file) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                length = int(parts[1])
            except ValueError:
                print(
                    f"Warning: could not parse contig length from '{line.strip()}' in {fai_file}",
                    file=sys.stderr,
                )
                continue
            contigs.append((parts[0], length))

    if not contigs:
        raise Exception(f"No contigs found in {fai_file}")

    # Largest first, name as tie-breaker so the selection is reproducible
    # regardless of the order contigs happen to appear in the FAI.
    contigs.sort(key=lambda contig: (-contig[1], contig[0]))

    eligible = [contig for contig in contigs if contig[1] >= min_contig_length]

    if not eligible:
        # Every contig is below the minimum length. Rather than emit an empty BED
        # (which would silently produce zero calls for the whole cohort), fall
        # back to the full contig list.
        print(
            f"Warning: no contig in {fai_file} reaches min_contig_length "
            f"{min_contig_length}. Falling back to all contigs.",
            file=sys.stderr,
        )
        eligible = contigs

    selected = []
    selected_bases = 0

    for name, length in eligible:
        selected.append((name, length))
        selected_bases += length
        if target_bases > 0 and selected_bases >= target_bases:
            break

    if target_bases > 0 and selected_bases < target_bases:
        print(
            f"Warning: reference {fai_file} only offers {selected_bases} eligible bases, "
            f"less than the requested budget of {target_bases}. Using all of them.",
            file=sys.stderr,
        )

    with open(bed_file, "w") as out:
        for name, length in selected:
            out.write(f"{name}\t0\t{length}\n")

    print(
        f"Selected {len(selected)} contig(s) totalling {selected_bases} bases "
        f"for SNP divergence calling: {bed_file}"
    )

    return selected_bases


if __name__ == "__main__":
    build_regions_bed(
        snakemake.input.fai,
        snakemake.output.bed,
        int(snakemake.params.target_bases),
        int(snakemake.params.min_contig_length),
    )

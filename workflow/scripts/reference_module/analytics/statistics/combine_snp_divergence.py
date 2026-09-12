import os
import sys

# Consistency constant of the modified z-score (Iglewicz & Hoaglin 1993).
# 0.6745 is the 0.75 quantile of the standard normal, which makes the MAD a
# consistent estimator of the standard deviation for normally distributed data.
MODIFIED_Z_CONSTANT = 0.6745

# Scaling factor used when the MAD is zero and the mean absolute deviation is
# used instead, per the same reference.
MEAN_AD_CONSTANT = 1.253314

# Minimum number of usable individuals before a cohort-relative score means
# anything. Below this the median/MAD are not estimable in a useful way.
MIN_COHORT_SIZE = 3

STATUS_OK = "ok"
STATUS_OUTLIER = "outlier"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_INSUFFICIENT_COHORT = "insufficient_cohort"

COMBINED_COLUMNS = [
    "individual",
    "method",
    "divergence_rate",
    "variant_sites",
    "callable_bases",
    "het_ratio",
    "cohort_median",
    "cohort_mad",
    "modified_zscore",
    "outlier_threshold_rate",
    "status",
]

DETAILED_COLUMNS = [
    "individual",
    "method",
    "source_file",
    "variant_sites",
    "callable_bases",
    "heterozygous_sites",
    "homozygous_alt_sites",
    "transitions",
    "transversions",
    "average_depth",
]


def _median(values):
    """Median of a non-empty list of numbers."""
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def parse_samtools_stats(stats_file):
    """
    Read the divergence numbers out of a `samtools stats` file.

    `SN mismatches:` is the sum of the NM tag over mapped reads and
    `SN bases mapped (cigar):` is the number of aligned bases, so their ratio is
    a per-base divergence rate against the reference. This is edit distance, so
    it also carries residual damage, sequencing error and indels. That is good
    enough for the cohort-outlier signal this check exists to produce.
    """
    mismatches = 0
    bases_mapped = 0

    with open(stats_file) as f:
        for line in f:
            if not line.startswith("SN"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            if parts[1].startswith("mismatches:"):
                mismatches = _to_int(parts[2], stats_file)
            elif parts[1].startswith("bases mapped (cigar):"):
                bases_mapped = _to_int(parts[2], stats_file)

    return {
        "variant_sites": mismatches,
        "callable_bases": bases_mapped,
        "heterozygous_sites": "",
        "homozygous_alt_sites": "",
        "transitions": "",
        "transversions": "",
        "average_depth": "",
    }


def parse_bcftools_stats(stats_file):
    """
    Read the per-sample counts out of a `bcftools stats -s -` file.

    The PSC (per-sample counts) section carries the homozygous-alt and
    heterozygous call counts, transitions/transversions and average depth. The
    VCF this is computed on holds a single sample, so the first PSC row is the
    one wanted. If no PSC row is present (a VCF with zero variants can omit it)
    the SN section's `number of SNPs:` is used and the het counts stay unknown.
    """
    hom_alt = None
    hets = None
    transitions = ""
    transversions = ""
    average_depth = ""
    sn_snps = 0

    with open(stats_file) as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if not parts:
                continue
            if parts[0] == "PSC" and hom_alt is None and len(parts) >= 10:
                hom_alt = _to_int(parts[4], stats_file)
                hets = _to_int(parts[5], stats_file)
                transitions = _to_int(parts[6], stats_file)
                transversions = _to_int(parts[7], stats_file)
                average_depth = parts[9]
            elif parts[0] == "SN" and len(parts) >= 4:
                if parts[2].startswith("number of SNPs:"):
                    sn_snps = _to_int(parts[3], stats_file)

    if hom_alt is None:
        print(
            f"Warning: no PSC section in {stats_file}, falling back to the SN SNP count. "
            "Heterozygous ratio will not be available for this individual.",
            file=sys.stderr,
        )
        return {
            "variant_sites": sn_snps,
            "callable_bases": 0,
            "heterozygous_sites": "",
            "homozygous_alt_sites": "",
            "transitions": transitions,
            "transversions": transversions,
            "average_depth": average_depth,
        }

    return {
        "variant_sites": hom_alt + hets,
        "callable_bases": 0,
        "heterozygous_sites": hets,
        "homozygous_alt_sites": hom_alt,
        "transitions": transitions,
        "transversions": transversions,
        "average_depth": average_depth,
    }


def read_callable_bases(callable_file):
    """Read the single integer written by count_snp_divergence_callable_bases."""
    with open(callable_file) as f:
        content = f.read().strip()
    return _to_int(content, callable_file)


def _to_int(value, source_file):
    try:
        return int(value)
    except (TypeError, ValueError):
        print(
            f"Warning: could not parse '{value}' as an integer in {source_file}. Using 0.",
            file=sys.stderr,
        )
        return 0


def flag_outliers(records, outlier_zscore, min_callable_bases):
    """
    Score each individual against the cohort using a MAD-based modified z-score.

    The median and MAD are computed over the usable individuals only, so an
    individual with too little data neither gets a score nor drags the cohort
    baseline around. Only the high side is flagged: an unusually *low*
    divergence is not evidence of a wrong reference or contamination.
    """
    for record in records:
        record["cohort_median"] = ""
        record["cohort_mad"] = ""
        record["modified_zscore"] = ""
        record["outlier_threshold_rate"] = ""
        # Overwritten below for every individual that turns out to be usable.
        record["status"] = STATUS_INSUFFICIENT_DATA

    usable = [
        record
        for record in records
        if record["callable_bases"] > 0 and record["callable_bases"] >= min_callable_bases
    ]

    if len(usable) < MIN_COHORT_SIZE:
        print(
            f"Only {len(usable)} individual(s) have at least {min_callable_bases} callable bases. "
            f"A cohort-relative outlier score needs at least {MIN_COHORT_SIZE}, so no individual is flagged.",
            file=sys.stderr,
        )
        for record in usable:
            record["status"] = STATUS_INSUFFICIENT_COHORT
        return records

    rates = [record["divergence_rate"] for record in usable]
    median = _median(rates)
    mad = _median([abs(rate - median) for rate in rates])

    if mad > 0:
        scale = mad / MODIFIED_Z_CONSTANT
    else:
        # Every deviation is identical, so the MAD carries no information. Fall
        # back to the mean absolute deviation, as Iglewicz & Hoaglin prescribe.
        mean_ad = sum(abs(rate - median) for rate in rates) / len(rates)
        scale = mean_ad * MEAN_AD_CONSTANT

    threshold_rate = median + outlier_zscore * scale if scale > 0 else median

    for record in usable:
        if scale > 0:
            zscore = (record["divergence_rate"] - median) / scale
        else:
            # All individuals share the same rate, so nobody deviates.
            zscore = 0.0

        record["cohort_median"] = f"{median:.8f}"
        record["cohort_mad"] = f"{mad:.8f}"
        record["modified_zscore"] = f"{zscore:.4f}"
        record["outlier_threshold_rate"] = f"{threshold_rate:.8f}"
        record["status"] = STATUS_OUTLIER if zscore > outlier_zscore else STATUS_OK

        if record["status"] == STATUS_OUTLIER:
            print(
                f"WARNING: individual '{record['individual']}' has a divergence rate of "
                f"{record['divergence_rate']:.6f} against this reference, a modified z-score of "
                f"{zscore:.2f} versus the cohort median of {median:.6f}. That can mean a wrong "
                "reference genome, cross-species contamination, or a mislabeled individual. "
                "This is a warning only, the pipeline continues.",
                file=sys.stderr,
            )

    return records


def combine_snp_divergence(
    stats_files,
    callable_files,
    individuals,
    method,
    outlier_zscore,
    min_callable_bases,
    combined_file_path,
    detailed_file_path,
):
    """Build the species-level SNP divergence summary from per-individual inputs."""

    if not stats_files:
        raise Exception("No per-individual SNP divergence input files provided")

    if len(stats_files) != len(individuals):
        raise Exception(
            f"Got {len(stats_files)} stats file(s) for {len(individuals)} individual(s). "
            "These are expanded together, so they must line up."
        )

    if method == "bcftools" and len(callable_files) != len(individuals):
        raise Exception(
            f"Got {len(callable_files)} callable-bases file(s) for {len(individuals)} individual(s). "
            "These are expanded together, so they must line up."
        )

    records = []

    for index, individual in enumerate(individuals):
        stats_file = stats_files[index]

        if method == "bcftools":
            parsed = parse_bcftools_stats(stats_file)
            parsed["callable_bases"] = read_callable_bases(callable_files[index])
        else:
            parsed = parse_samtools_stats(stats_file)

        callable_bases = parsed["callable_bases"]
        divergence_rate = (
            parsed["variant_sites"] / callable_bases if callable_bases > 0 else 0.0
        )

        het_ratio = ""
        if parsed["heterozygous_sites"] != "" and parsed["variant_sites"] > 0:
            het_ratio = f"{parsed['heterozygous_sites'] / parsed['variant_sites']:.6f}"

        records.append(
            {
                "individual": individual,
                "method": method,
                "source_file": os.path.basename(stats_file),
                "divergence_rate": divergence_rate,
                "variant_sites": parsed["variant_sites"],
                "callable_bases": callable_bases,
                "heterozygous_sites": parsed["heterozygous_sites"],
                "homozygous_alt_sites": parsed["homozygous_alt_sites"],
                "transitions": parsed["transitions"],
                "transversions": parsed["transversions"],
                "average_depth": parsed["average_depth"],
                "het_ratio": het_ratio,
                "status": STATUS_OK,
            }
        )

    records = flag_outliers(records, outlier_zscore, min_callable_bases)

    records.sort(key=lambda record: record["individual"])

    _write_csv(combined_file_path, COMBINED_COLUMNS, records, {"divergence_rate": ".8f"})
    _write_csv(detailed_file_path, DETAILED_COLUMNS, records, {})

    flagged = [record["individual"] for record in records if record["status"] == STATUS_OUTLIER]
    if flagged:
        print(f"Flagged {len(flagged)} individual(s) as divergence outliers: {', '.join(flagged)}")
    else:
        print("No individual was flagged as a divergence outlier.")

    print(f"SNP divergence summary written to: {combined_file_path}")
    print(f"SNP divergence detail written to: {detailed_file_path}")


def _write_csv(path, columns, records, formats):
    with open(path, "w") as out:
        out.write(",".join(columns) + "\n")
        for record in records:
            values = []
            for column in columns:
                value = record.get(column, "")
                if column in formats and value != "":
                    value = format(value, formats[column])
                values.append(str(value))
            out.write(",".join(values) + "\n")


if __name__ == "__main__":
    combine_snp_divergence(
        list(snakemake.input.stats),
        list(snakemake.input.callable_bases),
        list(snakemake.params.individuals),
        snakemake.params.method,
        float(snakemake.params.outlier_zscore),
        int(snakemake.params.min_callable_bases),
        snakemake.output.combined,
        snakemake.output.detailed,
    )

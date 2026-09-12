#!/usr/bin/env python3
"""
Unit tests for the SNP-divergence-check helpers. Both are plain, importable functions
guarded by `if __name__ == "__main__":`, so they can be exercised without Snakemake
(see workflow/rules/reference_module/analytics/analyze_snp_divergence.smk for where
they are wired up as `script:` directives):

    workflow/scripts/reference_module/analytics/statistics/build_snp_divergence_regions.py
    workflow/scripts/reference_module/analytics/statistics/combine_snp_divergence.py

Pure Python, stdlib only, no Snakemake/conda required. Run with either:
    python3 tests/test_snp_divergence.py
    python3 -m unittest tests.test_snp_divergence -v          (from the repo root)
"""
import csv
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.analytics.statistics.build_snp_divergence_regions import (  # noqa: E402
    build_regions_bed,
)
from scripts.reference_module.analytics.statistics.combine_snp_divergence import (  # noqa: E402
    STATUS_INSUFFICIENT_COHORT,
    STATUS_INSUFFICIENT_DATA,
    STATUS_OK,
    STATUS_OUTLIER,
    combine_snp_divergence,
    flag_outliers,
    parse_bcftools_stats,
    parse_samtools_stats,
)


class SnpDivergenceTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pf_test_snp_divergence_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp_dir, name)

    def write(self, name, content):
        target = self.path(name)
        with open(target, "w") as f:
            f.write(content)
        return target

    def write_fai(self, name, contigs):
        lines = [f"{contig}\t{length}\t0\t60\t61\n" for contig, length in contigs]
        return self.write(name, "".join(lines))

    def read_bed(self, path):
        with open(path) as f:
            return [line.rstrip("\n").split("\t") for line in f if line.strip()]

    def read_csv_dicts(self, path):
        with open(path) as f:
            return list(csv.DictReader(f))

    def make_record(self, individual, rate, callable_bases=1000000):
        return {
            "individual": individual,
            "divergence_rate": rate,
            "callable_bases": callable_bases,
            "status": STATUS_OK,
        }


class BuildRegionsTests(SnpDivergenceTestCase):
    def test_takes_largest_contigs_until_budget_is_met(self):
        fai = self.write_fai(
            "ref.fa.fai", [("small", 100000), ("big", 900000), ("mid", 500000)]
        )
        bed = self.path("regions.bed")

        selected_bases = build_regions_bed(fai, bed, target_bases=1000000, min_contig_length=1000)

        rows = self.read_bed(bed)
        self.assertEqual([row[0] for row in rows], ["big", "mid"])
        self.assertEqual(selected_bases, 1400000)
        # Full contig intervals, so BED start is always 0 and end is the contig length.
        self.assertEqual(rows[0], ["big", "0", "900000"])

    def test_target_bases_zero_selects_every_eligible_contig(self):
        fai = self.write_fai("ref.fa.fai", [("a", 300), ("b", 200), ("c", 100)])
        bed = self.path("regions.bed")

        build_regions_bed(fai, bed, target_bases=0, min_contig_length=0)

        self.assertEqual([row[0] for row in self.read_bed(bed)], ["a", "b", "c"])

    def test_contigs_below_min_length_are_skipped(self):
        fai = self.write_fai("ref.fa.fai", [("keep", 50000), ("tiny", 10)])
        bed = self.path("regions.bed")

        build_regions_bed(fai, bed, target_bases=0, min_contig_length=1000)

        self.assertEqual([row[0] for row in self.read_bed(bed)], ["keep"])

    def test_falls_back_to_all_contigs_when_none_reach_min_length(self):
        fai = self.write_fai("ref.fa.fai", [("a", 100), ("b", 50)])
        bed = self.path("regions.bed")

        build_regions_bed(fai, bed, target_bases=0, min_contig_length=1000000)

        # An empty BED would silently produce zero calls for the whole cohort.
        self.assertEqual([row[0] for row in self.read_bed(bed)], ["a", "b"])

    def test_selection_is_deterministic_for_equal_length_contigs(self):
        fai = self.write_fai("ref.fa.fai", [("z", 1000), ("a", 1000), ("m", 1000)])
        bed = self.path("regions.bed")

        build_regions_bed(fai, bed, target_bases=1000, min_contig_length=0)

        # Ties broken by name, so every individual of the cohort is scored identically.
        self.assertEqual([row[0] for row in self.read_bed(bed)], ["a"])

    def test_empty_fai_raises(self):
        fai = self.write("ref.fa.fai", "")
        with self.assertRaises(Exception):
            build_regions_bed(fai, self.path("regions.bed"), 0, 0)


class ParseStatsTests(SnpDivergenceTestCase):
    def test_parses_samtools_stats_mismatches_and_bases(self):
        stats = self.write(
            "a.stats",
            "# comment\n"
            "SN\traw total sequences:\t1000\n"
            "SN\tmismatches:\t4200\n"
            "SN\tbases mapped (cigar):\t1400000\n",
        )

        parsed = parse_samtools_stats(stats)

        self.assertEqual(parsed["variant_sites"], 4200)
        self.assertEqual(parsed["callable_bases"], 1400000)
        self.assertEqual(parsed["heterozygous_sites"], "")

    def test_missing_samtools_fields_default_to_zero(self):
        stats = self.write("a.stats", "SN\traw total sequences:\t10\n")

        parsed = parse_samtools_stats(stats)

        self.assertEqual(parsed["variant_sites"], 0)
        self.assertEqual(parsed["callable_bases"], 0)

    def test_parses_bcftools_psc_section(self):
        stats = self.write(
            "a.bcftools_stats.txt",
            "# This file was produced by bcftools stats\n"
            "SN\t0\tnumber of records:\t120\n"
            "SN\t0\tnumber of SNPs:\t115\n"
            "# PSC\t[2]id\t[3]sample\t[4]nRefHom\t[5]nNonRefHom\t[6]nHets\n"
            "PSC\t0\tsampleA\t0\t80\t35\t70\t45\t0\t7.5\t0\t0\t0\t0\n",
        )

        parsed = parse_bcftools_stats(stats)

        self.assertEqual(parsed["variant_sites"], 115)
        self.assertEqual(parsed["heterozygous_sites"], 35)
        self.assertEqual(parsed["homozygous_alt_sites"], 80)
        self.assertEqual(parsed["transitions"], 70)
        self.assertEqual(parsed["transversions"], 45)
        self.assertEqual(parsed["average_depth"], "7.5")

    def test_bcftools_without_psc_falls_back_to_sn_snp_count(self):
        stats = self.write(
            "a.bcftools_stats.txt",
            "# This file was produced by bcftools stats\n"
            "SN\t0\tnumber of SNPs:\t7\n",
        )

        parsed = parse_bcftools_stats(stats)

        self.assertEqual(parsed["variant_sites"], 7)
        self.assertEqual(parsed["heterozygous_sites"], "")


class FlagOutliersTests(SnpDivergenceTestCase):
    def test_high_divergence_individual_is_flagged(self):
        records = [
            self.make_record("ind1", 0.0010),
            self.make_record("ind2", 0.0011),
            self.make_record("ind3", 0.0010),
            self.make_record("ind4", 0.0500),
        ]

        flag_outliers(records, outlier_zscore=3.5, min_callable_bases=1000)

        by_id = {record["individual"]: record for record in records}
        self.assertEqual(by_id["ind4"]["status"], STATUS_OUTLIER)
        self.assertEqual(by_id["ind1"]["status"], STATUS_OK)
        self.assertGreater(float(by_id["ind4"]["modified_zscore"]), 3.5)

    def test_unusually_low_divergence_is_not_flagged(self):
        records = [
            self.make_record("ind1", 0.0100),
            self.make_record("ind2", 0.0101),
            self.make_record("ind3", 0.0100),
            self.make_record("ind4", 0.0000),
        ]

        flag_outliers(records, outlier_zscore=3.5, min_callable_bases=1000)

        by_id = {record["individual"]: record for record in records}
        # A low divergence is not evidence of a wrong reference or contamination.
        self.assertEqual(by_id["ind4"]["status"], STATUS_OK)
        self.assertLess(float(by_id["ind4"]["modified_zscore"]), 0)

    def test_individual_below_callable_floor_is_not_scored(self):
        records = [
            self.make_record("ind1", 0.0010),
            self.make_record("ind2", 0.0011),
            self.make_record("ind3", 0.0010),
            self.make_record("thin", 0.9000, callable_bases=10),
        ]

        flag_outliers(records, outlier_zscore=3.5, min_callable_bases=1000)

        by_id = {record["individual"]: record for record in records}
        self.assertEqual(by_id["thin"]["status"], STATUS_INSUFFICIENT_DATA)
        self.assertEqual(by_id["thin"]["modified_zscore"], "")
        # The excluded individual must not drag the cohort baseline either.
        self.assertAlmostEqual(float(by_id["ind1"]["cohort_median"]), 0.0010)

    def test_small_cohort_is_not_scored(self):
        records = [self.make_record("ind1", 0.001), self.make_record("ind2", 0.5)]

        flag_outliers(records, outlier_zscore=3.5, min_callable_bases=1000)

        for record in records:
            self.assertEqual(record["status"], STATUS_INSUFFICIENT_COHORT)
            self.assertEqual(record["modified_zscore"], "")

    def test_identical_rates_flag_nobody(self):
        records = [self.make_record(f"ind{i}", 0.002) for i in range(1, 5)]

        flag_outliers(records, outlier_zscore=3.5, min_callable_bases=1000)

        for record in records:
            self.assertEqual(record["status"], STATUS_OK)
            self.assertEqual(float(record["modified_zscore"]), 0.0)

    def test_zero_mad_falls_back_to_mean_absolute_deviation(self):
        # Median 0.001 and MAD 0, so the MAD alone cannot separate the outlier.
        records = [
            self.make_record("ind1", 0.001),
            self.make_record("ind2", 0.001),
            self.make_record("ind3", 0.001),
            self.make_record("ind4", 0.001),
            self.make_record("ind5", 0.900),
        ]

        flag_outliers(records, outlier_zscore=3.5, min_callable_bases=1000)

        by_id = {record["individual"]: record for record in records}
        self.assertEqual(float(by_id["ind1"]["cohort_mad"]), 0.0)
        self.assertEqual(by_id["ind5"]["status"], STATUS_OUTLIER)


class CombineTests(SnpDivergenceTestCase):
    def samtools_stats_file(self, name, mismatches, bases_mapped):
        return self.write(
            name,
            f"SN\tmismatches:\t{mismatches}\n"
            f"SN\tbases mapped (cigar):\t{bases_mapped}\n",
        )

    def test_combines_samtools_stats_tier_and_flags_outlier(self):
        stats_files = [
            self.samtools_stats_file("ind1.stats", 1000, 1000000),
            self.samtools_stats_file("ind2.stats", 1100, 1000000),
            self.samtools_stats_file("ind3.stats", 1000, 1000000),
            self.samtools_stats_file("ind4.stats", 50000, 1000000),
        ]
        combined = self.path("combined.csv")
        detailed = self.path("detailed.csv")

        combine_snp_divergence(
            stats_files,
            [],
            ["ind1", "ind2", "ind3", "ind4"],
            "samtools_stats",
            3.5,
            100000,
            combined,
            detailed,
        )

        rows = {row["individual"]: row for row in self.read_csv_dicts(combined)}
        self.assertEqual(rows["ind4"]["status"], STATUS_OUTLIER)
        self.assertEqual(rows["ind1"]["status"], STATUS_OK)
        self.assertEqual(rows["ind1"]["method"], "samtools_stats")
        self.assertAlmostEqual(float(rows["ind1"]["divergence_rate"]), 0.001)
        self.assertEqual(rows["ind1"]["callable_bases"], "1000000")
        # No heterozygous-call rate is available on this tier.
        self.assertEqual(rows["ind1"]["het_ratio"], "")

        detail_rows = {row["individual"]: row for row in self.read_csv_dicts(detailed)}
        self.assertEqual(detail_rows["ind4"]["variant_sites"], "50000")
        self.assertEqual(detail_rows["ind4"]["source_file"], "ind4.stats")

    def test_combines_bcftools_tier_with_callable_bases_and_het_ratio(self):
        stats_files = []
        callable_files = []
        for index, (hom_alt, hets) in enumerate(
            [(60, 20), (62, 22), (60, 20), (600, 300)], start=1
        ):
            stats_files.append(
                self.write(
                    f"ind{index}.bcftools_stats.txt",
                    "# This file was produced by bcftools stats\n"
                    f"PSC\t0\tsample\t0\t{hom_alt}\t{hets}\t50\t30\t0\t6.1\t0\t0\t0\t0\n",
                )
            )
            callable_files.append(self.write(f"ind{index}.callable.txt", "800000\n"))

        combined = self.path("combined.csv")
        detailed = self.path("detailed.csv")

        combine_snp_divergence(
            stats_files,
            callable_files,
            ["ind1", "ind2", "ind3", "ind4"],
            "bcftools",
            3.5,
            100000,
            combined,
            detailed,
        )

        rows = {row["individual"]: row for row in self.read_csv_dicts(combined)}
        self.assertEqual(rows["ind4"]["status"], STATUS_OUTLIER)
        self.assertEqual(rows["ind1"]["method"], "bcftools")
        self.assertEqual(rows["ind1"]["callable_bases"], "800000")
        self.assertEqual(rows["ind1"]["variant_sites"], "80")
        self.assertAlmostEqual(float(rows["ind1"]["divergence_rate"]), 80 / 800000)
        self.assertAlmostEqual(float(rows["ind1"]["het_ratio"]), 20 / 80)

    def test_mismatched_input_lengths_raise(self):
        stats_files = [self.samtools_stats_file("ind1.stats", 1, 2)]

        with self.assertRaises(Exception):
            combine_snp_divergence(
                stats_files,
                [],
                ["ind1", "ind2"],
                "samtools_stats",
                3.5,
                100000,
                self.path("combined.csv"),
                self.path("detailed.csv"),
            )

    def test_empty_input_raises(self):
        with self.assertRaises(Exception):
            combine_snp_divergence(
                [],
                [],
                [],
                "samtools_stats",
                3.5,
                100000,
                self.path("combined.csv"),
                self.path("detailed.csv"),
            )

    def test_individual_with_no_mapped_bases_is_reported_not_fatal(self):
        stats_files = [
            self.samtools_stats_file("ind1.stats", 1000, 1000000),
            self.samtools_stats_file("ind2.stats", 1100, 1000000),
            self.samtools_stats_file("ind3.stats", 1000, 1000000),
            self.samtools_stats_file("empty.stats", 0, 0),
        ]
        combined = self.path("combined.csv")

        combine_snp_divergence(
            stats_files,
            [],
            ["ind1", "ind2", "ind3", "empty"],
            "samtools_stats",
            3.5,
            100000,
            combined,
            self.path("detailed.csv"),
        )

        rows = {row["individual"]: row for row in self.read_csv_dicts(combined)}
        self.assertEqual(rows["empty"]["status"], STATUS_INSUFFICIENT_DATA)
        self.assertEqual(rows["ind1"]["status"], STATUS_OK)


if __name__ == "__main__":
    unittest.main(verbosity=2)

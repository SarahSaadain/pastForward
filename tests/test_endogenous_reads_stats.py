#!/usr/bin/env python3
"""
Unit tests for the two endogenous-reads statistics helpers that are plain, importable
functions with no `snakemake` object dependency at import time (both are guarded by
`if __name__ == "__main__":` - see workflow/rules/reference_module_processing.smk for
where they're wired up as `script:` directives):

    workflow/scripts/reference_module/analytics/statistics/parse_endogenous_from_stats.py
    workflow/scripts/reference_module/analytics/statistics/combine_endogenous_reads.py

Pure Python, stdlib only, no Snakemake/conda required. Run with either:
    python3 tests/test_endogenous_reads_stats.py
    python3 -m unittest tests.test_endogenous_reads_stats -v          (from the repo root)
"""
import csv
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.analytics.statistics.parse_endogenous_from_stats import (  # noqa: E402
    determine_endogenous_reads_from_stats,
)
from scripts.reference_module.analytics.statistics.combine_endogenous_reads import (  # noqa: E402
    combine_endogenous_files,
)


def _read_csv_rows(path):
    with open(path) as f:
        return list(csv.reader(f))


class EndogenousStatsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pf_test_endogenous_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp_dir, name)

    def write_stats(self, name, raw_total=None, mapped=None):
        lines = ["# comment lines must be ignored\n"]
        if raw_total is not None:
            lines.append(f"SN\traw total sequences:\t{raw_total}\n")
        if mapped is not None:
            lines.append(f"SN\treads mapped:\t{mapped}\n")
        stats_path = self.path(name)
        with open(stats_path, "w") as f:
            f.writelines(lines)
        return stats_path


class TestDetermineEndogenousReadsFromStats(EndogenousStatsTestCase):
    def test_normal_proportion_computed(self):
        stats_path = self.write_stats("sample.stats", raw_total=1000, mapped=800)
        out_path = self.path("out.csv")
        determine_endogenous_reads_from_stats(stats_path, out_path, "IND001")

        rows = _read_csv_rows(out_path)
        self.assertEqual(rows[0], ["filename", "individual", "mapped_reads", "total_reads", "proportion"])
        self.assertEqual(rows[1], ["sample.stats", "IND001", "800", "1000", "80.0000"])

    def test_missing_stats_file_defaults_to_zero(self):
        out_path = self.path("out.csv")
        determine_endogenous_reads_from_stats(self.path("does_not_exist.stats"), out_path, "IND001")
        rows = _read_csv_rows(out_path)
        self.assertEqual(rows[1][2:], ["0", "0", "0.0000"])

    def test_zero_total_reads_gives_zero_proportion_without_division_error(self):
        stats_path = self.write_stats("sample.stats", raw_total=0, mapped=0)
        out_path = self.path("out.csv")
        determine_endogenous_reads_from_stats(stats_path, out_path, "IND001")
        rows = _read_csv_rows(out_path)
        self.assertEqual(rows[1][2:], ["0", "0", "0.0000"])

    def test_malformed_numeric_value_defaults_to_zero(self):
        stats_path = self.write_stats("sample.stats", raw_total="not_a_number", mapped=800)
        out_path = self.path("out.csv")
        determine_endogenous_reads_from_stats(stats_path, out_path, "IND001")
        rows = _read_csv_rows(out_path)
        # total_reads falls back to 0 -> proportion must also be 0, not a ZeroDivisionError
        self.assertEqual(rows[1][2:], ["800", "0", "0.0000"])

    def test_dedup_removed_reads_added_back_to_mapped_and_total(self):
        # stats come from the deduplicated BAM: 700 left, 600 mapped after 200 duplicates removed.
        # DeDup's mapped_reads (1500) includes secondary/supplementary alignments and must be ignored.
        stats_path = self.write_stats("sample.stats", raw_total=700, mapped=600)
        dedup_path = self.path("sample.dedup.json")
        with open(dedup_path, "w") as f:
            f.write('{"metrics": {"mapped_reads": 1500, "total_removed": 200}}')
        out_path = self.path("out.csv")
        determine_endogenous_reads_from_stats(stats_path, out_path, "IND001", dedup_path)
        rows = _read_csv_rows(out_path)
        self.assertEqual(rows[1][2:], ["800", "900", "88.8889"])


class TestCombineEndogenousFiles(EndogenousStatsTestCase):
    def _write_individual_csv(self, name, filename, individual, mapped, total, proportion):
        path = self.path(name)
        with open(path, "w") as f:
            f.write("filename,individual,mapped_reads,total_reads,proportion\n")
            f.write(f"{filename},{individual},{mapped},{total},{proportion}\n")
        return path

    def test_combines_multiple_files_with_single_header(self):
        f1 = self._write_individual_csv("a.csv", "a.stats", "IND001", 800, 1000, "80.0000")
        f2 = self._write_individual_csv("b.csv", "b.stats", "IND002", 400, 1000, "40.0000")
        combined_path = self.path("combined.csv")

        combine_endogenous_files([f2, f1], combined_path)  # deliberately out of order

        rows = _read_csv_rows(combined_path)
        self.assertEqual(rows[0], ["filename", "individual", "mapped_reads", "total_reads", "proportion"])
        self.assertEqual(len(rows), 3)
        # sorted() by file path inside combine_endogenous_files -> a.csv (IND001) before b.csv
        self.assertEqual(rows[1][1], "IND001")
        self.assertEqual(rows[2][1], "IND002")

    def test_missing_input_file_is_skipped_not_fatal(self):
        f1 = self._write_individual_csv("a.csv", "a.stats", "IND001", 800, 1000, "80.0000")
        combined_path = self.path("combined.csv")

        combine_endogenous_files([f1, self.path("missing.csv")], combined_path)

        rows = _read_csv_rows(combined_path)
        self.assertEqual(len(rows), 2)  # header + the one file that existed

    def test_empty_input_list_exits_nonzero(self):
        with self.assertRaises(SystemExit) as ctx:
            combine_endogenous_files([], self.path("combined.csv"))
        self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/read_module/analytics/statistics/read_composition.py,
which splits the adapter-removed reads of a sample into merged, unmerged and unpaired
reads from the fastp JSON plus the existing adapter-removed read count.

Pure Python, stdlib only, no Snakemake/conda required. Run with either:
    python3 tests/test_read_composition.py
    python3 -m unittest tests.test_read_composition -v          (from the repo root)
"""
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.read_module.analytics.statistics.read_composition import (  # noqa: E402
    by_individual,
    sample_composition,
)


def pe_json(passed, merged):
    return {
        "filtering_result": {"passed_filter_reads": passed},
        "merged_and_filtered": {"total_reads": merged},
    }


class TestSampleComposition(unittest.TestCase):
    def test_paired_end_split(self):
        # Real numbers from Tni15726_B_2_box-1-26 (fastp 1.1.0).
        row = sample_composition(
            "Tni15726_B_2_box-1-26", 80098028, pe_json(158341914, 78245724)
        )
        self.assertEqual(row["individual"], "Tni15726")
        self.assertEqual(row["layout"], "paired")
        self.assertEqual(row["merged_reads"], 78245724)
        self.assertEqual(row["unmerged_reads"], 1850466)
        self.assertEqual(row["unpaired_reads"], 1838)
        self.assertEqual(row["single_end_reads"], 0)
        self.assertEqual(
            row["merged_reads"] + row["unmerged_reads"] + row["unpaired_reads"],
            row["adapter_removed_reads"],
        )
        self.assertAlmostEqual(row["merged_percent"], 97.69, places=2)

    def test_single_end_is_all_single(self):
        row = sample_composition("S1_x", 100, {"filtering_result": {"passed_filter_reads": 100}})
        self.assertEqual(row["layout"], "single")
        self.assertEqual(row["single_end_reads"], 100)
        self.assertEqual(row["merged_reads"], 0)
        self.assertEqual(row["single_end_percent"], 100.0)

    def test_inconsistent_numbers_raise(self):
        # Unpaired would be negative: count file and JSON do not belong together.
        with self.assertRaises(ValueError):
            sample_composition("S1", 10, pe_json(passed=100, merged=40))
        # Odd unmerged read count cannot come from whole pairs.
        with self.assertRaises(ValueError):
            sample_composition("S1", 100, pe_json(passed=101, merged=40))

    def test_missing_merge_section_raises(self):
        with self.assertRaises(ValueError):
            sample_composition(
                "S1", 100, {"filtering_result": {"passed_filter_reads": 100}}, paired=True
            )

    def test_adapter_removal_skipped(self):
        pe = sample_composition("A_1", 200, None, paired=True)
        self.assertEqual((pe["merged_reads"], pe["unmerged_reads"]), (0, 200))
        se = sample_composition("A_2", 50, None, paired=False)
        self.assertEqual(se["single_end_reads"], 50)
        with self.assertRaises(ValueError):
            sample_composition("A_1", 200, None)

    def test_zero_reads_gives_zero_percent(self):
        row = sample_composition("S1", 0, pe_json(0, 0))
        self.assertEqual(row["merged_percent"], 0.0)


class TestByIndividual(unittest.TestCase):
    def test_sums_samples_and_recomputes_percent(self):
        rows = [
            sample_composition("A_1", 100, pe_json(passed=180, merged=80)),  # 80/20/0
            sample_composition("A_2", 100, {"filtering_result": {"passed_filter_reads": 100}}),
            sample_composition("B_1", 50, pe_json(passed=50, merged=0)),
        ]
        out = {r["individual"]: r for r in by_individual(rows)}
        self.assertEqual(sorted(out), ["A", "B"])
        a = out["A"]
        self.assertEqual(a["samples"], 2)
        self.assertEqual(a["layout"], "mixed")
        self.assertEqual(a["adapter_removed_reads"], 200)
        self.assertEqual(a["merged_reads"], 80)
        self.assertEqual(a["unmerged_reads"], 20)
        self.assertEqual(a["single_end_reads"], 100)
        self.assertEqual(a["merged_percent"], 40.0)
        self.assertEqual(out["B"]["layout"], "paired")


if __name__ == "__main__":
    unittest.main()

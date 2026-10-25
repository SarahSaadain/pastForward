#!/usr/bin/env python3
"""
Unit tests for the depth/coverage scripts:

    workflow/scripts/reference_module/analytics/statistics/analyze_samtools_depth_individual_file.py
    workflow/scripts/reference_module/analytics/statistics/combine_analyzed_depth_breadth_files.py
    workflow/scripts/summary_module/summarize_coverage.py

Needs pandas. Run with either:
    python3 tests/test_coverage_summary.py
    python3 -m unittest tests.test_coverage_summary -v          (from the repo root)
"""
import os
import runpy
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    import pandas as pd
except ImportError:
    raise unittest.SkipTest("pandas not installed")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.analytics.statistics import (  # noqa: E402
    analyze_samtools_depth_individual_file as depth_mod,
    combine_analyzed_depth_breadth_files as combine_mod,
)

SUMMARIZE = os.path.join(REPO_ROOT, "workflow", "scripts", "summary_module", "summarize_coverage.py")


class AnalyzeDepthTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pf_test_depth_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def analyze(self, lines, chunksize=2):
        depth = os.path.join(self.tmp, "depth.txt")
        out = os.path.join(self.tmp, "out.csv")
        with open(depth, "w") as f:
            f.writelines(f"{s}\t{p}\t{d}\n" for s, p, d in lines)
        real = pd.read_csv
        # Small chunks so each chunk guesses its own column type, as 1M-line chunks do on real data.
        with mock.patch.object(depth_mod.pd, "read_csv", lambda *a, **k: real(*a, **{**k, "chunksize": chunksize})):
            depth_mod.analyze_coverage_file(depth, out)
        return pd.read_csv(out, dtype={"scaffold": str}, keep_default_na=False).set_index("scaffold")

    def test_numeric_scaffold_name_is_one_row_across_chunks(self):
        # Chunk 1 mixes '2L' and '4' (read as text), chunk 2 holds only 4 (read as a number).
        lines = [("2L", 1, 1), ("4", 1, 2), ("4", 2, 0), ("4", 3, 2), ("4", 4, 0)]
        df = self.analyze(lines)
        self.assertEqual(sorted(df.index), ["2L", "4"])
        self.assertEqual(df.loc["4", "total_bases"], 4)
        self.assertEqual(df.loc["4", "covered_bases"], 2)

    def test_na_like_scaffold_names_are_kept(self):
        lines = [("NA", 1, 1), ("NA", 2, 0), ("nan", 1, 3), ("2L", 1, 1)]
        df = self.analyze(lines)
        self.assertEqual(sorted(df.index), ["2L", "NA", "nan"])
        self.assertEqual(df["total_bases"].sum(), 4)


class SummarizeCoverageTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pf_test_summarize_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def summarize(self, rows):
        inp = os.path.join(self.tmp, "in.csv")
        out = os.path.join(self.tmp, "out.tsv")
        pd.DataFrame(rows, columns=["scaffold", "avg_depth", "max_depth", "covered_bases", "total_bases", "percent_covered"]).to_csv(inp, index=False)
        sm = SimpleNamespace(input=[inp], output=[out], params=SimpleNamespace(individual="IND001", reference="dm6"))
        runpy.run_path(SUMMARIZE, init_globals={"snakemake": sm})
        return pd.read_csv(out, sep="\t").iloc[0]

    def test_average_depth_is_weighted_by_scaffold_length(self):
        rows = [("2L", 1.0, 5, 23_000_000, 23_000_000, 100.0)]
        rows += [(f"Un{i}", 0.0, 0, 0, 1_000, 0.0) for i in range(100)]
        row = self.summarize(rows)
        self.assertAlmostEqual(row["average_depth"], 23_000_000 / 23_100_000)

    def test_zero_length_input_gives_zero_depth(self):
        row = self.summarize([("2L", 0.0, 0, 0, 0, 0.0)])
        self.assertEqual(row["average_depth"], 0)


class CoverageChainTestCase(unittest.TestCase):
    """samtools depth file -> per-scaffold CSV -> combined CSV -> MultiQC summary."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pf_test_coverage_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scaffolds_4_na_2l_with_tiny_chunks(self):
        # Chunk size 2: chunk 2 holds only "4" (would be read as a number) and
        # chunk 3 holds only "NA" (would be read as missing and dropped).
        depth = os.path.join(self.tmp, "IND001_dm6.depth.txt")
        with open(depth, "w") as f:
            f.write("2L\t1\t3\n4\t1\t2\n"
                    "4\t2\t0\n4\t3\t4\n"
                    "NA\t1\t1\nNA\t2\t0\n"
                    "2L\t2\t0\n")
        analysis = os.path.join(self.tmp, "IND001_dm6_coverage_analysis.csv")
        real = pd.read_csv
        with mock.patch.object(depth_mod.pd, "read_csv", lambda *a, **k: real(*a, **{**k, "chunksize": 2})):
            depth_mod.analyze_coverage_file(depth, analysis)

        per_scaffold = pd.read_csv(analysis, dtype={"scaffold": str}, keep_default_na=False).set_index("scaffold")
        self.assertEqual(
            {s: (r.covered_bases, r.total_bases) for s, r in per_scaffold.iterrows()},
            {"2L": (1, 2), "4": (2, 3), "NA": (1, 2)},
        )

        combined = os.path.join(self.tmp, "combined.csv")
        detailed = os.path.join(self.tmp, "detailed.csv")
        combine_mod.combine_analysis_files([analysis], combined, detailed)
        overall = pd.read_csv(combined).iloc[0]
        self.assertEqual((overall["OverallCoveredBases"], overall["OverallTotalBases"]), (4, 7))
        # depth sum 3 + 6 + 1 = 10 over 7 bases; the plain mean of per-scaffold depths would be 4/3
        self.assertAlmostEqual(overall["OverallAvgDepth"], 10 / 7)
        self.assertEqual(sorted(pd.read_csv(detailed, dtype={"scaffold": str}, keep_default_na=False)["scaffold"]), ["2L", "4", "NA"])

        summary = os.path.join(self.tmp, "summary.tsv")
        sm = SimpleNamespace(input=[analysis], output=[summary], params=SimpleNamespace(individual="IND001", reference="dm6"))
        runpy.run_path(SUMMARIZE, init_globals={"snakemake": sm})
        row = pd.read_csv(summary, sep="\t").iloc[0]
        self.assertAlmostEqual(row["average_depth"], 10 / 7)
        self.assertEqual((row["total_covered_bases"], row["total_bases"]), (4, 7))

    def test_depth_file_read_once(self):
        # depth -aa writes one line per reference base (tens of GB on a 3 Gb genome), so read it in one pass only
        depth = os.path.join(self.tmp, "IND001_dm6.depth.txt")
        with open(depth, "w") as f:
            f.write("2L\t1\t3\n2L\t2\t0\n")
        opened = []
        real_open = open

        def counting_open(file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)) and os.fspath(file) == depth:
                opened.append(file)
            return real_open(file, *args, **kwargs)

        with mock.patch("builtins.open", counting_open):
            depth_mod.analyze_coverage_file(depth, os.path.join(self.tmp, "out.csv"))
        self.assertEqual(len(opened), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

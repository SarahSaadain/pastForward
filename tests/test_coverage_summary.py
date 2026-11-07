#!/usr/bin/env python3
"""
Unit tests for the depth/coverage scripts:

    workflow/scripts/reference_module/analytics/statistics/analyze_coverage_from_bam.py
    workflow/scripts/reference_module/analytics/statistics/combine_analyzed_depth_breadth_files.py
    workflow/scripts/summary_module/summarize_coverage.py

Needs pandas and numpy. No samtools or pysam: the depth text is fed in directly. Run with either:
    python3 tests/test_coverage_summary.py
    python3 -m unittest tests.test_coverage_summary -v          (from the repo root)
"""
import io
import os
import random
import runpy
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

try:
    import pandas as pd
except ImportError:
    raise unittest.SkipTest("pandas not installed")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.analytics.statistics import (  # noqa: E402
    analyze_coverage_from_bam as depth_mod,
    combine_analyzed_depth_breadth_files as combine_mod,
)

SUMMARIZE = os.path.join(REPO_ROOT, "workflow", "scripts", "summary_module", "summarize_coverage.py")


def depth_text(lines):
    return io.StringIO("".join(f"{s}\t{p}\t{d}\n" for s, p, d in lines))


def analyze(lines, header, out, chunksize=2):
    """header: (name, length) pairs in BAM header order. Small chunks so scaffolds span several."""
    names, lengths = zip(*header)
    rows = depth_mod.summarize_depth_stream(depth_text(lines), names, lengths, chunksize=chunksize)
    depth_mod.write_summary(rows, out)
    return pd.read_csv(out, dtype={"scaffold": str}, keep_default_na=False).set_index("scaffold")


class AnalyzeDepthTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pf_test_depth_")
        self.out = os.path.join(self.tmp, "out.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_numeric_scaffold_name_is_one_row_across_chunks(self):
        # Chunk 1 mixes '2L' and '4', chunk 2 holds only 4. Zero-depth bases are not printed.
        lines = [("2L", 1, 1), ("4", 1, 2), ("4", 3, 2)]
        df = analyze(lines, [("2L", 1), ("4", 4)], self.out)
        self.assertEqual(sorted(df.index), ["2L", "4"])
        self.assertEqual(df.loc["4", "total_bases"], 4)
        self.assertEqual(df.loc["4", "covered_bases"], 2)

    def test_na_like_scaffold_names_are_kept(self):
        lines = [("NA", 1, 1), ("nan", 1, 3), ("2L", 1, 1)]
        df = analyze(lines, [("NA", 2), ("nan", 1), ("2L", 1)], self.out)
        self.assertEqual(sorted(df.index), ["2L", "NA", "nan"])
        self.assertEqual(df["total_bases"].sum(), 4)

    def test_uncovered_scaffold_and_no_reads(self):
        df = analyze([("2L", 5, 7)], [("2L", 10), ("3R", 4)], self.out)
        self.assertEqual(tuple(df.loc["3R", ["max_depth", "covered_bases", "total_bases"]]), (0, 0, 4))
        self.assertEqual(df.loc["2L", "max_depth"], 7)
        # samtools depth prints nothing at all for a BAM without reads
        df = analyze([], [("2L", 10)], self.out)
        self.assertEqual((df.loc["2L", "avg_depth"], df.loc["2L", "total_bases"]), (0, 10))

    def test_scaffold_missing_from_header_fails(self):
        with self.assertRaises(RuntimeError):
            depth_mod.summarize_depth_stream(depth_text([("chrX", 1, 1)]), ["2L"], [5])

    def test_legacy_order_small_chunks(self):
        # Bases z z z | b b | a a a in chunks of 4: chunk 1 holds z, b (sorted: b, z), chunk 2 adds a
        rows = [(n, 0, 0, 0, L) for n, L in [("z", 3), ("b", 2), ("a", 3)]]
        self.assertEqual([r[0] for r in depth_mod.legacy_order(rows, chunk=4)], ["b", "z", "a"])

    def test_legacy_order_matches_old_chunked_groupby(self):
        # Old script: one line per base in header order, read in chunks, groupby sorts names per chunk
        rnd = random.Random(1)
        for _ in range(50):
            rows = [(f"s{rnd.randrange(1000)}_{i}", 0, 0, 0, rnd.randint(1, 30)) for i in range(rnd.randint(1, 12))]
            chunk = rnd.randint(1, 40)
            bases = [r[0] for r in rows for _ in range(r[4])]
            expected = []
            for k in range(0, len(bases), chunk):
                for n in sorted(set(bases[k:k + chunk])):
                    if n not in expected:
                        expected.append(n)
            self.assertEqual([r[0] for r in depth_mod.legacy_order(rows, chunk=chunk)], expected)


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
    """samtools depth lines -> per-scaffold CSV -> combined CSV -> MultiQC summary."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pf_test_coverage_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scaffolds_4_na_2l_with_tiny_chunks(self):
        # Chunk size 2: chunk 2 holds only "4" (would be read as a number) and
        # chunk 3 holds only "NA" (would be read as missing and dropped).
        analysis = os.path.join(self.tmp, "IND001_dm6_coverage_analysis.csv")
        lines = [("2L", 1, 3), ("4", 1, 2), ("4", 3, 4), ("NA", 1, 1)]
        per_scaffold = analyze(lines, [("2L", 2), ("4", 3), ("NA", 2)], analysis)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

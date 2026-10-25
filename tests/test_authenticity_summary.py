#!/usr/bin/env python3
"""
Unit tests for the authenticity summary table:

    workflow/scripts/reference_module/analytics/statistics/create_authenticity_summary.py

The fixture files below copy the real format of each pipeline output (values taken from a
historical Dmel individual). Pure Python, stdlib only, no Snakemake/conda required. Run with:
    python3 tests/test_authenticity_summary.py
"""
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.analytics.statistics.create_authenticity_summary import (  # noqa: E402
    create_authenticity_summary,
)

STATS = """# This file was produced by samtools stats
SN\traw total sequences:\t120870205\t# excluding supplementary and secondary reads
SN\treads mapped:\t49717344
# Mapping qualities for reads !(UNMAP|SECOND|SUPPL|QCFAIL|DUP).
MAPQ\t0\t10
MAPQ\t30\t30
"""
ENDOGENOUS = "filename,individual,mapped_reads,total_reads,proportion\nx.stats,IND1,49717344,120870205,41.1328\n"
DEDUP = {"metrics": {"total_reads": 100, "mapped_reads": 100, "total_removed": 13, "dup_rate": "0.1329", "clusterfactor": "1.1532"}}
CT5P = "pos\t5pC>T\n1\t0.0470795730502949\n2\t0.0347458409646485\n"
GA3P = "pos\t3pG>A\n1\t0.0500993852904526\n2\t0.00419414291790686\n"
# Two strands: lengths 40 (+3, -1), 50 (+2), 60 (-4) -> 10 reads, median 50, mean 50.
LENGTHS = """# table produced by mapDamage version 2.2.3
# Std: strand of reads
Std\tLength\tOccurences
+\t40\t3
-\t40\t1
+\t50\t2
-\t60\t4
"""
COVERAGE = """scaffold,avg_depth,max_depth,covered_bases,total_bases,percent_covered
chr1,10.0,50,900,1000,90.0
chr2,2.0,10,100,1000,10.0
"""


class AuthenticitySummaryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pf_test_authenticity_")
        self.output = os.path.join(self.tmp_dir, "out.tsv")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def full_inputs(self, individual="IND1", **overrides):
        files = {
            "stats": STATS, "endogenous": ENDOGENOUS, "dedup": DEDUP, "ct5p": CT5P,
            "ga3p": GA3P, "lengths": LENGTHS, "coverage": COVERAGE,
        }
        files.update(overrides)
        return {key: [self.write(f"{individual}.{key}", content)] for key, content in files.items()}

    def run_table(self, inputs, individuals=("IND1",), thresholds=None, n_samples=None):
        n_samples = n_samples or [1] * len(individuals)
        create_authenticity_summary(list(individuals), n_samples, inputs, thresholds or {}, self.output)
        with open(self.output) as f:
            return list(csv.DictReader(f, delimiter="\t"))


class TestCompleteIndividual(AuthenticitySummaryTestCase):
    def test_every_column_parsed_from_its_file(self):
        row = self.run_table(self.full_inputs(), n_samples=[2])[0]
        self.assertEqual(row["individual"], "IND1")
        self.assertEqual(row["n_samples"], "2")
        self.assertEqual(row["total_reads"], "120870205")
        self.assertEqual(row["mapped_reads"], "49717344")
        self.assertEqual(row["endogenous_percent"], "41.1328")
        self.assertEqual(row["duplicate_rate"], "0.1329")
        self.assertEqual(row["cluster_factor"], "1.1532")
        self.assertEqual(row["median_mapped_length"], "50")
        self.assertEqual(row["mean_mapped_length"], "50.00")
        self.assertEqual(row["ct_5p_pos1"], "0.0471")
        self.assertEqual(row["ga_3p_pos1"], "0.0501")
        self.assertEqual(row["mean_depth"], "6.0000")
        self.assertEqual(row["breadth_percent"], "50.0000")
        self.assertEqual(row["mean_mapq"], "22.50")
        self.assertEqual(row["verdict"], "ok")
        self.assertEqual(row["verdict_reason"], "")


class TestStepsSwitchedOff(AuthenticitySummaryTestCase):
    def test_empty_groups_give_na_but_stay_ok(self):
        # Dedup, mapDamage and coverage off: their groups arrive as empty lists.
        inputs = self.full_inputs()
        for group in ("dedup", "ct5p", "ga3p", "lengths", "coverage"):
            inputs[group] = []
        row = self.run_table(inputs)[0]
        for column in ("duplicate_rate", "cluster_factor", "median_mapped_length", "ct_5p_pos1", "mean_depth", "breadth_percent"):
            self.assertEqual(row[column], "NA", column)
        self.assertEqual(row["endogenous_percent"], "41.1328")
        self.assertEqual((row["verdict"], row["verdict_reason"]), ("ok", ""))

    def test_stats_without_mapq_lines_is_na_not_no_data(self):
        # Older samtools writes no MAPQ section. That is not a missing file.
        row = self.run_table(self.full_inputs(stats="SN\treads mapped:\t1\n"))[0]
        self.assertEqual(row["mean_mapq"], "NA")
        self.assertEqual(row["verdict"], "ok")


class TestMissingFiles(AuthenticitySummaryTestCase):
    def test_missing_file_gives_no_data_and_names_it(self):
        inputs = self.full_inputs()
        os.remove(inputs["ct5p"][0])
        row = self.run_table(inputs)[0]
        self.assertEqual(row["ct_5p_pos1"], "NA")
        self.assertEqual((row["verdict"], row["verdict_reason"]), ("no_data", "missing_ct5p"))

    def test_empty_file_gives_no_data(self):
        row = self.run_table(self.full_inputs(lengths=""))[0]
        self.assertEqual((row["verdict"], row["verdict_reason"]), ("no_data", "missing_lengths"))

    def test_one_incomplete_individual_does_not_block_others(self):
        good = self.full_inputs("IND1")
        bad = self.full_inputs("IND2", endogenous="")
        inputs = {group: good[group] + bad[group] for group in good}
        rows = self.run_table(inputs, individuals=("IND1", "IND2"))
        self.assertEqual([(r["individual"], r["verdict"]) for r in rows], [("IND1", "ok"), ("IND2", "no_data")])


class TestThresholds(AuthenticitySummaryTestCase):
    def test_low_damage_is_check_with_reason(self):
        # A modern control: 0.4% C-to-T at position 1.
        row = self.run_table(self.full_inputs(ct5p="pos\t5pC>T\n1\t0.0037\n"))[0]
        self.assertEqual((row["verdict"], row["verdict_reason"]), ("check", "ct_5p_pos1<0.01"))

    def test_every_threshold_named(self):
        thresholds = {
            "min_endogenous_percent": 50, "min_ct_5p_pos1": 0.1, "min_median_mapped_length": 60,
            "max_duplicate_rate": 0.1, "min_mean_depth": 10,
        }
        row = self.run_table(self.full_inputs(), thresholds=thresholds)[0]
        self.assertEqual(row["verdict"], "check")
        self.assertEqual(
            row["verdict_reason"],
            "endogenous_percent<50;ct_5p_pos1<0.1;median_mapped_length<60;duplicate_rate>0.1;mean_depth<10",
        )

    def test_partial_override_keeps_other_defaults(self):
        # Only the depth threshold set in config: the 1% damage default still applies.
        row = self.run_table(self.full_inputs(ct5p="pos\t5pC>T\n1\t0.0037\n"), thresholds={"min_mean_depth": 10})[0]
        self.assertEqual(row["verdict_reason"], "ct_5p_pos1<0.01;mean_depth<10")

    def test_check_wins_over_missing_and_both_reasons_kept(self):
        inputs = self.full_inputs(ct5p="pos\t5pC>T\n1\t0.0037\n")
        os.remove(inputs["coverage"][0])
        row = self.run_table(inputs)[0]
        self.assertEqual((row["verdict"], row["verdict_reason"]), ("check", "ct_5p_pos1<0.01;missing_coverage"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

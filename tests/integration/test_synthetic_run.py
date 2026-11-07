"""End-to-end checks on a finished run of the `tests/integration/synthetic_project/` synthetic project.

The `tests/integration/synthetic_project/` reads were simulated with known answers (damage, duplication,
contamination, TE copy numbers). These tests check that the pipeline output
reproduces them. Run the pipeline on `tests/integration/synthetic_project/` first, see tests/README.md.
Set PF_TEST_PROJECT to check a project directory other than `tests/integration/synthetic_project/`.
"""

import csv
import json
import os
import unittest
from pathlib import Path

PROJECT = Path(
    os.environ.get("PF_TEST_PROJECT") or Path(__file__).resolve().parent / "synthetic_project"
)
RESULTS = PROJECT / "Dmel" / "results"


def setUpModule():
    if not RESULTS.is_dir():
        raise unittest.SkipTest(
            f"{RESULTS} not found. Run the pipeline on tests/integration/synthetic_project/ first: "
            "snakemake --directory tests/integration/synthetic_project --cores 4 --software-deployment-method conda"
        )


REF = RESULTS / "reference_module" / "dmel_mini" / "analytics"
IND = REF / "individual_level"
SCREEN = RESULTS / "read_module" / "taxonomic_screening"
REVEAL = RESULTS / "reveal_module"


def read_tsv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def read_freq(path):
    """mapDamage *_freq.txt: header then `pos<TAB>freq`. Returns {pos: freq}."""
    with open(path, newline="") as fh:
        return {int(r[0]): float(r[1]) for r in list(csv.reader(fh, delimiter="\t"))[1:]}


class TestDamage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {}
        cls.freq = {}
        for ind in ("HistA", "ModB"):
            for end in ("5pCtoT", "3pGtoA"):
                p = IND / ind / "mapdamage" / f"{ind}_dmel_mini.{end}_freq.txt"
                cls.files[ind, end] = p
                cls.freq[ind, end] = read_freq(p)

    def test_hist_5p_ct_pos1(self):
        v = self.freq["HistA", "5pCtoT"][1]
        self.assertTrue(0.15 <= v <= 0.35, f"{self.files['HistA', '5pCtoT']}: pos1 {v}")

    def test_hist_3p_ga_pos1(self):
        v = self.freq["HistA", "3pGtoA"][1]
        self.assertTrue(0.15 <= v <= 0.35, f"{self.files['HistA', '3pGtoA']}: pos1 {v}")

    def test_hist_5p_decays_inward(self):
        f = self.freq["HistA", "5pCtoT"]
        self.assertTrue(f[1] > f[2] > f[3], f"{self.files['HistA', '5pCtoT']}: pos1-3 {f[1]}, {f[2]}, {f[3]}")

    def test_mod_no_damage(self):
        for end in ("5pCtoT", "3pGtoA"):
            v = self.freq["ModB", end][1]
            self.assertLess(v, 0.01, f"{self.files['ModB', end]}: pos1 {v}")


class TestAuthenticity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = REF / "species_level" / "Dmel" / "authenticity" / "dmel_mini_authenticity.tsv"
        cls.rows = {r["individual"]: r for r in read_tsv(cls.path)}

    def test_verdicts(self):
        self.assertEqual(self.rows["HistA"]["verdict"], "ok", f"{self.path}: HistA {self.rows['HistA']}")
        self.assertEqual(self.rows["ModB"]["verdict"], "check", f"{self.path}: ModB {self.rows['ModB']}")
        self.assertIn("ct_5p_pos1<0.01", self.rows["ModB"]["verdict_reason"], f"{self.path}: ModB reason")

    def test_hist_reads_shorter(self):
        h = float(self.rows["HistA"]["median_mapped_length"])
        m = float(self.rows["ModB"]["median_mapped_length"])
        self.assertLess(h, m, f"{self.path}: median_mapped_length HistA {h}, ModB {m}")
        self.assertLess(h, 60, f"{self.path}: HistA median_mapped_length {h}")

    def test_endogenous(self):
        for ind, row in self.rows.items():
            v = float(row["endogenous_percent"])
            self.assertGreater(v, 70, f"{self.path}: {ind} endogenous_percent {v}")


class TestDedup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {i: IND / i / "dedup" / f"{i}_dmel_mini_final.dedup.json" for i in ("HistA", "ModB")}
        cls.rate = {}
        for i, p in cls.files.items():
            with open(p) as fh:
                cls.rate[i] = float(json.load(fh)["metrics"]["dup_rate"])

    def test_hist_dup_rate(self):
        v = self.rate["HistA"]
        self.assertTrue(0.15 <= v <= 0.35, f"{self.files['HistA']}: dup_rate {v}")

    def test_mod_dup_rate(self):
        v = self.rate["ModB"]
        self.assertLess(v, 0.08, f"{self.files['ModB']}: dup_rate {v}")


class TestEcmsd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {i: SCREEN / "ecmsd" / f"{i}_Mito_summary_hits_combined.tsv" for i in ("HistA", "ModB")}
        cls.hits = {i: read_tsv(p)[0] for i, p in cls.files.items()}

    def test_hist_has_fly_and_human(self):
        h = self.hits["HistA"]
        self.assertGreater(float(h.get("Drosophila_melanogaster", 0)), 0, f"{self.files['HistA']}: {h}")
        self.assertGreater(float(h.get("Homo_sapiens", 0)), 0, f"{self.files['HistA']}: {h}")

    def test_mod_fly_only(self):
        m = self.hits["ModB"]
        self.assertGreater(float(m.get("Drosophila_melanogaster", 0)), 0, f"{self.files['ModB']}: {m}")
        self.assertEqual(float(m.get("Homo_sapiens") or 0), 0, f"{self.files['ModB']}: {m}")


class TestCentrifuge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {
            i: SCREEN / "centrifuge" / i / i / f"{i}_centrifuge_report.tsv" for i in ("HistA", "ModB")
        }
        cls.reads = {
            i: {r["taxID"]: int(r["numReads"]) for r in read_tsv(p)} for i, p in cls.files.items()
        }

    def test_fly_is_top_taxon(self):
        for ind, r in self.reads.items():
            self.assertEqual(max(r, key=r.get), "7227", f"{self.files[ind]}: numReads {r}")

    def test_wolbachia_in_both(self):
        for ind, r in self.reads.items():
            self.assertGreater(r.get("163164", 0), 0, f"{self.files[ind]}: numReads {r}")

    def test_hist_contaminants(self):
        r = self.reads["HistA"]
        self.assertGreater(r.get("9606", 0), 0, f"{self.files['HistA']}: human numReads {r.get('9606')}")
        self.assertGreater(r.get("562", 0), 500, f"{self.files['HistA']}: E. coli numReads {r.get('562')}")

    def test_mod_no_contaminants(self):
        r = self.reads["ModB"]
        for tax in ("9606", "562"):
            self.assertEqual(r.get(tax, 0), 0, f"{self.files['ModB']}: taxID {tax} numReads {r.get(tax)}")


class TestReveal(unittest.TestCase):
    # designed copy numbers (HistA, ModB)
    DESIGNED = {
        "opus_fle": (0, 4),
        "roo_fle": (2, 6),
        "jockey_fle": (1, 1),
        **{f"scg{i}_scg": (1, 1) for i in range(1, 5)},
    }

    @classmethod
    def setUpClass(cls):
        cls.path = REVEAL / "Dmel_reveal_coverage_comparison.tsv"
        cls.cov = {
            r["seqid"]: (float(r["median_cov__HistA"]), float(r["median_cov__ModB"]))
            for r in read_tsv(cls.path)
        }
        cls.flag_path = REVEAL / "te_mini" / "visualization" / "species_level" / "Dmel_te_mini_flagged_seqids.tsv"
        cls.flagged = {r["seqid"] for r in read_tsv(cls.flag_path)}

    def test_copy_numbers(self):
        for seqid, designed in self.DESIGNED.items():
            for ind, want, got in zip(("HistA", "ModB"), designed, self.cov[seqid]):
                with self.subTest(seqid=seqid, ind=ind):
                    msg = f"{self.path}: {seqid} median_cov__{ind} {got}, designed {want}"
                    if want == 0:
                        self.assertLess(got, 0.2, msg)
                    else:
                        self.assertAlmostEqual(got, want, delta=0.25 * want, msg=msg)

    def test_flagged(self):
        self.assertIn("opus_fle", self.flagged, f"{self.flag_path}: {sorted(self.flagged)}")
        self.assertNotIn("jockey_fle", self.flagged, f"{self.flag_path}: {sorted(self.flagged)}")


if __name__ == "__main__":
    unittest.main()

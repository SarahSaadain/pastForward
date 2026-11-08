import gzip
import os
import re
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workflow"))
from scripts.index_compression import (
    INDEX_REGEX,
    index_archives,
    is_dryrun,
    mapper,
    remove_unpacked_indexes,
    restore_indexes,
    unpack_needed,
)

OLD = 1_000_000_000


class IndexCompressionTest(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        self.ref = Path("Sp/processed/reference_module/R/reference")
        self.ref.mkdir(parents=True)
        self.raw = self.ref / "R.fa.0123"
        self.gz = self.ref / "R.fa.0123.gz"
        self.gz.write_bytes(gzip.compress(b"x" * 1000))
        os.utime(self.gz, (OLD, OLD))
        (self.ref / "R.fa").write_text(">a\nAC\n")
        self.cfg = {"species": {"Sp": {}, "Off": {"execute": False}}}

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_restore_makes_empty_placeholder_with_archive_mtime(self):
        restore_indexes(self.cfg, dryrun=False)
        self.assertEqual(self.raw.stat().st_size, 0)
        self.assertEqual(int(self.raw.stat().st_mtime), OLD)
        self.assertTrue(self.gz.exists())

    def test_unpack_needed_only_for_indexes_a_job_reads(self):
        restore_indexes(self.cfg, dryrun=False)
        unpack_needed(self.cfg, [SimpleNamespace(input=["Sp/other.txt"])])
        self.assertEqual(self.raw.stat().st_size, 0)  # no job reads it
        unpack_needed(self.cfg, [SimpleNamespace(input=["./" + str(self.raw)])])
        self.assertEqual(self.raw.read_bytes(), b"x" * 1000)
        self.assertEqual(int(self.raw.stat().st_mtime), OLD)

    def test_killed_run_placeholder_is_recreated_not_trusted(self):
        restore_indexes(self.cfg, dryrun=True)
        restore_indexes(self.cfg, dryrun=False)
        self.assertEqual(self.raw.stat().st_size, 0)

    def test_existing_raw_index_is_left_alone(self):
        self.raw.write_text("real")
        restore_indexes(self.cfg, dryrun=False)
        self.assertEqual(self.raw.read_text(), "real")

    def test_remove_only_drops_indexes_that_have_an_archive(self):
        self.raw.write_text("x")
        lone = self.ref / "R.fa.amb"
        lone.write_text("x")
        remove_unpacked_indexes(self.cfg)
        self.assertFalse(self.raw.exists())
        self.assertTrue(lone.exists())
        self.assertTrue((self.ref / "R.fa").exists())

    def test_real_run_removes_unpacked_index_at_exit(self):
        code = (
            "import sys; sys.path.insert(0, %r);"
            "from scripts.index_compression import restore_indexes;"
            "restore_indexes({'species': {'Sp': {}}}, dryrun=False);"
            "import os; print(os.path.exists(%r))"
        ) % (str(Path(__file__).resolve().parents[2] / "workflow"), str(self.raw))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "True")  # placeholder while the process ran
        self.assertFalse(self.raw.exists())  # gone after exit
        self.assertTrue(self.gz.exists())

    def test_archives_per_mapper(self):
        self.assertEqual(index_archives("a.fa", "minimap2"), ["a.fa.mmi.gz"])
        self.assertEqual(index_archives("a.fa", "minimap2", mmi="a.mmi"), ["a.mmi.gz"])
        self.assertIn("a.fa.sa.gz", index_archives("a.fa", "bwa-aln"))
        self.assertIn("a.fa.0123.gz", index_archives("a.fa", "bwa-mem2"))
        self.assertNotIn("a.fa.0123.gz", index_archives("a.fa", "bwa-mem3"))
        self.assertIn("a.fa.pac.gz", index_archives("a.fa", "bwa-mem3"))
        self.assertEqual(index_archives("a.fa", "minibwa"), ["a.fa.l2b.gz", "a.fa.mbw.gz"])
        self.assertIn("a.fa.rev.2.bt2.gz", index_archives("a.fa", "bowtie2"))
        self.assertIn("a.fa.4.ebwt.gz", index_archives("a.fa", "bowtie"))
        self.assertTrue(re.fullmatch(INDEX_REGEX + r"\.gz", "x/a.fa.rev.1.bt2.gz"))

    def test_dryrun_detection(self):
        for argv in (["--dryrun"], ["--dry-run"], ["-n"], ["-np"], ["-nq"], ["-pn"]):
            self.assertTrue(is_dryrun(["snakemake", "--cores", "4"] + argv), argv)
        for argv in (["--cores", "4"], ["-p"], ["--rerun-incomplete"], ["-c4"], ["--notemp"]):
            self.assertFalse(is_dryrun(["snakemake"] + argv), argv)

    def test_mapper_lookup_and_fallback(self):
        cfg = {"pipeline": {"reveal_module": {"mapping": {"settings": {"mapper": "minimap2"}}}}}
        self.assertEqual(mapper({}, "reference_module"), "bwa-mem3")
        self.assertEqual(mapper(cfg, "reveal_module"), "minimap2")
        self.assertEqual(mapper(cfg, "reveal_module", "scg_selector"), "minimap2")


if __name__ == "__main__":
    unittest.main()

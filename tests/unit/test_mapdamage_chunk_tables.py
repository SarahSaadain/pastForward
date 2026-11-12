#!/usr/bin/env python3
"""
Unit tests for summing per-chunk mapDamage count tables:

    workflow/scripts/reference_module/processing/analyze_damage_script_combine_chunk_tables.py

Pure Python, stdlib only, no Snakemake/conda required. Run with either:
    python3 tests/unit/test_mapdamage_chunk_tables.py
    python3 -m unittest discover tests/unit -v          (from the repo root)
"""

import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.processing.analyze_damage_script_combine_chunk_tables import (  # noqa: E402
    combine_chunk_tables,
)

MISINC_HEADER = "Chr\tEnd\tStd\tPos\tA\tC\tG\tT\tTotal\tG>A\tC>T\n"


class CombineChunkTablesTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pf_test_mapdamage_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write(self, name, text):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def _combine(self, paths, n_keys):
        out = os.path.join(self.tmp_dir, "out.txt")
        combine_chunk_tables(paths, out, n_keys)
        with open(out) as fh:
            return fh.read()

    def test_misincorporation_rows_of_different_contigs_are_kept_and_shared_keys_summed(
        self,
    ):
        # mapDamage writes zero rows for contigs a chunk does not hold, so keys repeat across chunks
        chunk_0 = self._write(
            "c0.txt",
            "# table produced by mapDamage version 2.2.3\n"
            "# using mapped file chunk_0.bam and ref.fa as reference file\n"
            "# Chr: reference from sam/bam header\n"
            + MISINC_HEADER
            + "chr4\t3p\t+\t1\t10\t20\t30\t40\t100\t5\t0\n"
            + "mito\t3p\t+\t1\t0\t0\t0\t0\t0\t0\t0\n",
        )
        chunk_1 = self._write(
            "c1.txt",
            "# table produced by mapDamage version 2.2.3\n"
            "# using mapped file chunk_1.bam and ref.fa as reference file\n"
            "# Chr: reference from sam/bam header\n"
            + MISINC_HEADER
            + "chr4\t3p\t+\t1\t0\t0\t0\t0\t0\t0\t0\n"
            + "mito\t3p\t+\t1\t1\t2\t3\t4\t10\t1\t0\n",
        )

        self.assertEqual(
            self._combine([chunk_0, chunk_1], n_keys=4),
            "# table produced by mapDamage version 2.2.3\n"
            "# Chr: reference from sam/bam header\n"
            "# summed over 2 per-contig chunk tables\n"
            + MISINC_HEADER
            + "chr4\t3p\t+\t1\t10\t20\t30\t40\t100\t5\t0\n"
            + "mito\t3p\t+\t1\t1\t2\t3\t4\t10\t1\t0\n",
        )

    def test_length_distribution_sums_counts_per_strand_and_length(self):
        header = "Std\tLength\tOccurences \n"
        chunk_0 = self._write("l0.txt", header + "+\t30\t5\n-\t30\t2\n")
        chunk_1 = self._write("l1.txt", header + "+\t52\t1\n+\t30\t3\n")

        self.assertEqual(
            self._combine([chunk_0, chunk_1], n_keys=2),
            "# summed over 2 per-contig chunk tables\n"
            + header
            + "+\t30\t8\n-\t30\t2\n+\t52\t1\n",
        )

    def test_different_headers_are_refused(self):
        chunk_0 = self._write("h0.txt", "Std\tLength\tOccurences \n+\t30\t5\n")
        chunk_1 = self._write("h1.txt", "Std\tLen\tCount\n+\t30\t5\n")
        with self.assertRaises(ValueError):
            self._combine([chunk_0, chunk_1], n_keys=2)


if __name__ == "__main__":
    unittest.main()

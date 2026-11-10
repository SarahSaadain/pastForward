#!/usr/bin/env python3
"""
Unit tests for the deduplication cluster helpers:

    workflow/scripts/reference_module/processing/deduplication_script_dedup_create_all_contig_clusters.py
    workflow/scripts/reference_module/processing/deduplication_script_dedup_merge_cluster_jsons.py

Pure Python, stdlib only, no Snakemake/conda required. Run with either:
    python3 tests/unit/test_dedup_clusters.py
    python3 -m unittest tests.test_dedup_clusters -v          (from the repo root)
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reference_module.processing.deduplication_script_dedup_create_all_contig_clusters import (  # noqa: E402
    create_contig_clusters,
)
from scripts.reference_module.processing.deduplication_script_dedup_merge_cluster_jsons import (  # noqa: E402
    merge_dedup_jsons,
)


class DedupClusterTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pf_test_dedup_")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _cluster(self, idxstats_rows, cores):
        """Write an idxstats table (name, length, mapped, unmapped), cluster it, return {file: lines}."""
        path = os.path.join(self.tmp_dir, "idxstats.tsv")
        with open(path, "w") as f:
            f.write("".join("\t".join(map(str, row)) + "\n" for row in idxstats_rows))
        folder = os.path.join(self.tmp_dir, f"clusters_{cores}")
        create_contig_clusters(path, folder, cores)
        clusters = {}
        for name in sorted(os.listdir(folder)):
            with open(os.path.join(folder, name)) as f:
                clusters[name] = [ln for ln in f.read().splitlines() if ln]
        return clusters

    def test_big_contigs_go_to_separate_clusters(self):
        # dm6-like: one contig per big arm, the small ones packed into the lightest cluster
        rows = [
            ("2L", 2300, 30, 0),
            ("small1", 10, 2, 0),
            ("3R", 3200, 40, 2),
            ("small2", 20, 3, 1),
            ("X", 2400, 20, 0),
            ("*", 0, 0, 50),
        ]
        clusters = self._cluster(rows, 3)
        self.assertEqual(
            clusters,
            {
                "cluster_1.bed": ["3R\t0\t3200"],
                "cluster_2.bed": ["2L\t0\t2300"],
                "cluster_3.bed": ["small1\t0\t10", "small2\t0\t20", "X\t0\t2400"],
            },
        )

    def test_contigs_without_reads_and_unplaced_line_are_left_out(self):
        rows = [("a", 100, 5, 0), ("empty", 100, 0, 0), ("*", 0, 0, 7)]
        clusters = self._cluster(rows, 4)
        self.assertEqual(clusters, {"cluster_1.bed": ["a\t0\t100"]})

    def test_placed_unmapped_reads_count_towards_the_contig(self):
        # 'b' has only unmapped reads with a mapped mate, so it still needs a cluster
        rows = [("a", 100, 10, 0), ("b", 100, 0, 9)]
        clusters = self._cluster(rows, 2)
        self.assertEqual(
            clusters,
            {"cluster_1.bed": ["a\t0\t100"], "cluster_2.bed": ["b\t0\t100"]},
        )

    def test_no_reads_at_all_gives_one_cluster_with_every_contig(self):
        rows = [("a", 100, 0, 0), ("b", 50, 0, 0), ("*", 0, 0, 0)]
        clusters = self._cluster(rows, 8)
        self.assertEqual(clusters, {"cluster_1.bed": ["a\t0\t100", "b\t0\t50"]})

    def test_every_contig_with_reads_in_exactly_one_cluster(self):
        for n_contigs in (1, 2, 7, 64, 1234):
            for cores in (1, 3, 16, 2000):
                with self.subTest(n=n_contigs, cores=cores):
                    rows = [
                        (f"c{i}", 100 + i, (i * 37) % 11, i % 2)
                        for i in range(n_contigs)
                    ]
                    clusters = self._cluster(rows, cores)
                    with_reads = sorted(
                        f"c{i}" for i, r in enumerate(rows) if r[2] + r[3]
                    )
                    seen = [
                        ln.split("\t")[0] for lines in clusters.values() for ln in lines
                    ]
                    if with_reads:
                        self.assertEqual(sorted(seen), with_reads)
                        self.assertLessEqual(len(clusters), cores)
                    self.assertTrue(all(lines for lines in clusters.values()))

    def test_merge_sums_counts_across_clusters(self):
        metrics = [
            {
                "total_reads": 100,
                "mapped_reads": 80,
                "merged_removed": 5,
                "forward_removed": 3,
                "reverse_removed": 2,
                "total_removed": 10,
            },
            {
                "total_reads": 50,
                "mapped_reads": 40,
                "merged_removed": 1,
                "forward_removed": 2,
                "reverse_removed": 3,
                "total_removed": 6,
            },
            {
                "total_reads": 0,
                "mapped_reads": 0,
                "merged_removed": 0,
                "forward_removed": 0,
                "reverse_removed": 0,
                "total_removed": 0,
            },
        ]
        paths = []
        for i, m in enumerate(metrics):
            p = os.path.join(self.tmp_dir, f"c{i}.dedup.json")
            with open(p, "w") as f:
                # DeDup writes numbers as strings in some versions
                json.dump({"metrics": {k: str(v) for k, v in m.items()}}, f)
            paths.append(p)

        merged = merge_dedup_jsons(paths, "ind1_ref1")
        out = merged["metrics"]
        for key in metrics[0]:
            self.assertEqual(out[key], sum(m[key] for m in metrics), key)
        self.assertEqual(out["dup_rate"], f"{16 / 120:.4f}")
        self.assertEqual(out["clusterfactor"], f"{150 / 134:.4f}")
        self.assertEqual(merged["metadata"]["sample_name"], "ind1_ref1")

    def test_merge_with_no_mapped_reads_has_zero_rates(self):
        p = os.path.join(self.tmp_dir, "empty.dedup.json")
        with open(p, "w") as f:
            json.dump(
                {
                    "metrics": {
                        k: 0
                        for k in (
                            "total_reads",
                            "mapped_reads",
                            "merged_removed",
                            "forward_removed",
                            "reverse_removed",
                            "total_removed",
                        )
                    }
                },
                f,
            )
        out = merge_dedup_jsons([p], "x")["metrics"]
        self.assertEqual(out["dup_rate"], "0.0000")
        self.assertEqual(out["clusterfactor"], "0.0000")


if __name__ == "__main__":
    unittest.main()

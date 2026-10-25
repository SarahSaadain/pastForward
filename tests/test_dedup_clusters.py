#!/usr/bin/env python3
"""
Unit tests for the deduplication cluster helpers:

    workflow/scripts/reference_module/processing/deduplication_script_dedup_create_all_contig_clusters.py
    workflow/scripts/reference_module/processing/deduplication_script_dedup_merge_cluster_jsons.py

Pure Python, stdlib only, no Snakemake/conda required. Run with either:
    python3 tests/test_dedup_clusters.py
    python3 -m unittest tests.test_dedup_clusters -v          (from the repo root)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

    def _cluster(self, n_contigs, cores, min_per=1, max_per=500):
        contigs = [f"contig{i}\t0\t{100 + i}" for i in range(n_contigs)]
        bed = os.path.join(self.tmp_dir, f"contigs_{n_contigs}_{cores}.bed")
        with open(bed, "w") as f:
            f.write("\n".join(contigs) + "\n")
        folder = os.path.join(self.tmp_dir, f"clusters_{n_contigs}_{cores}_{min_per}_{max_per}")
        create_contig_clusters(bed, folder, cores, min_per, max_per)
        return contigs, folder

    def test_every_contig_in_exactly_one_cluster(self):
        for n_contigs in (1, 2, 3, 7, 10, 64, 501, 1234):
            for cores in (1, 2, 3, 4, 8, 16, 2000):
                for min_per, max_per in ((1, 500), (5, 500), (1, 10)):
                    with self.subTest(n=n_contigs, cores=cores, min=min_per, max=max_per):
                        contigs, folder = self._cluster(n_contigs, cores, min_per, max_per)
                        seen = []
                        for name in os.listdir(folder):
                            start, end = map(int, name[len("cluster_"):-len(".bed")].split("_"))
                            with open(os.path.join(folder, name)) as f:
                                lines = [l for l in f.read().splitlines() if l]
                            # the 1-based range in the filename matches the contigs inside
                            self.assertEqual(lines, contigs[start - 1:end])
                            self.assertLessEqual(len(lines), max(max_per, 1))
                            seen.extend(lines)
                        self.assertEqual(sorted(seen), sorted(contigs))
                        self.assertEqual(len(seen), len(set(seen)))

    def test_cluster_count_follows_cores(self):
        _, folder = self._cluster(100, 4)
        self.assertEqual(len(os.listdir(folder)), 4)

    def test_merge_sums_counts_across_clusters(self):
        metrics = [
            {"total_reads": 100, "mapped_reads": 80, "merged_removed": 5,
             "forward_removed": 3, "reverse_removed": 2, "total_removed": 10},
            {"total_reads": 50, "mapped_reads": 40, "merged_removed": 1,
             "forward_removed": 2, "reverse_removed": 3, "total_removed": 6},
            {"total_reads": 0, "mapped_reads": 0, "merged_removed": 0,
             "forward_removed": 0, "reverse_removed": 0, "total_removed": 0},
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
            json.dump({"metrics": {k: 0 for k in (
                "total_reads", "mapped_reads", "merged_removed",
                "forward_removed", "reverse_removed", "total_removed")}}, f)
        out = merge_dedup_jsons([p], "x")["metrics"]
        self.assertEqual(out["dup_rate"], "0.0000")
        self.assertEqual(out["clusterfactor"], "0.0000")


if __name__ == "__main__":
    unittest.main()

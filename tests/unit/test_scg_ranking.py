#!/usr/bin/env python3
"""
Unit tests for SCG ranking (rank_scgs in
workflow/scripts/reveal_module/scg/determine_scg_ranking.py, wired up by
workflow/rules/reveal_module/scg_selector/rank_scg.smk).

Needs numpy. No Snakemake/conda required. Run with either:
    python3 tests/unit/test_scg_ranking.py
    python3 -m unittest tests.test_scg_ranking -v          (from the repo root)
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.reveal_module.scg.determine_scg_ranking import rank_scgs  # noqa: E402

N_INDIVIDUALS = 6
NORMAL_GENES = [f"normal_{i}" for i in range(8)]


def gene_stats(depth):
    return {
        "min_depth": int(depth * 0.5),
        "avg_depth": float(depth),
        "median_depth": float(depth),
        "max_depth": int(depth * 1.5),
        "length": 1000,
        "covered_bases": 1000,
        "breadth": 1.0,
    }


def fixture():
    """Each individual has its own baseline depth. Normal genes sit at 0.9x to 1.1x
    of it (some noise, so the MAD is not 0), `double` at 2x everywhere and
    `half_in_some` at 0.5x in half the individuals (1x in the rest)."""
    data = {}
    for i in range(N_INDIVIDUALS):
        base = 10 * (i + 1)
        stats = {
            g: gene_stats(base * (1 + 0.05 * ((n + i) % 5 - 2)))
            for n, g in enumerate(NORMAL_GENES)
        }
        stats["double"] = gene_stats(2 * base)
        stats["half_in_some"] = gene_stats(base * (0.5 if i % 2 else 1.0))
        data[f"ind{i}_scg_stats.json"] = stats
    return data


class ScgRankingTest(unittest.TestCase):
    def setUp(self):
        self.ranked = list(rank_scgs(fixture())["scgs"])

    def assert_below_all_normal(self, gene):
        worst_normal = max(self.ranked.index(g) for g in NORMAL_GENES)
        self.assertGreater(self.ranked.index(gene), worst_normal, self.ranked)

    def test_double_depth_gene_ranks_below_normal_genes(self):
        self.assert_below_all_normal("double")

    def test_half_depth_in_some_individuals_ranks_below_normal_genes(self):
        self.assert_below_all_normal("half_in_some")


if __name__ == "__main__":
    unittest.main()

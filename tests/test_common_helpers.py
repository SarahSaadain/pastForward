#!/usr/bin/env python3
"""
Unit tests for small config helpers in workflow/rules/common.smk:
_dedup_enabled, _mapper_extra and _scg_mapper_and_extra.

common.smk holds plain Python only, so it is exec'd into the shared namespace
workflow/scripts/pipeline_namespace.py builds.

Run with either:
    python3 tests/test_common_helpers.py
    python3 -m unittest tests.test_common_helpers -v          (from the repo root)
"""
import logging
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.pipeline_namespace import load_pipeline_namespace  # noqa: E402

COMMON_SMK = os.path.join(REPO_ROOT, "workflow", "rules", "common.smk")


def load(pipeline=None):
    ns = load_pipeline_namespace({"species": {}, "pipeline": pipeline or {}})
    ns["logger"] = logging.getLogger("test_common_helpers")  # Snakemake provides it
    with open(COMMON_SMK) as f:
        exec(compile(f.read(), COMMON_SMK, "exec"), ns)
    return ns


class DedupEnabledTest(unittest.TestCase):
    def test_default_on(self):
        self.assertTrue(load()["_dedup_enabled"]())

    def test_off(self):
        ns = load({"reference_module": {"deduplication": {"execute": False}}})
        self.assertFalse(ns["_dedup_enabled"]())


class MapperExtraTest(unittest.TestCase):
    def setUp(self):
        self.extra = load()["_mapper_extra"]

    def test_missing_uses_default(self):
        self.assertEqual(self.extra({}, "minimap2"), "-ax sr")

    def test_empty_string_uses_default(self):
        # "" would drop -ax sr and make minimap2 write PAF.
        self.assertEqual(self.extra({"mapper_extra_params": ""}, "minimap2"), "-ax sr")

    def test_whitespace_uses_default(self):
        self.assertEqual(self.extra({"mapper_extra_params": " "}, "minimap2"), "-ax sr")

    def test_set_value_wins(self):
        self.assertEqual(self.extra({"mapper_extra_params": "-ax map-ont"}, "minimap2"), "-ax map-ont")


class ScgMapperAndExtraTest(unittest.TestCase):
    def setUp(self):
        self.pick = load()["_scg_mapper_and_extra"]

    def test_defaults(self):
        self.assertEqual(self.pick({}, {}), ("bwa-mem2", ""))

    def test_inherits_mapper_and_flags_from_mapping(self):
        mapping = {"mapper": "bwa-aln", "mapper_extra_params": "-n 0.04"}
        self.assertEqual(self.pick({}, mapping), ("bwa-aln", "-n 0.04"))

    def test_same_mapper_borrows_flags(self):
        mapping = {"mapper": "minimap2", "mapper_extra_params": "-ax sr -k 15"}
        self.assertEqual(self.pick({"mapper": "minimap2"}, mapping), ("minimap2", "-ax sr -k 15"))

    def test_other_mapper_does_not_borrow_flags(self):
        mapping = {"mapper": "bwa-aln", "mapper_extra_params": "-n 0.04"}
        self.assertEqual(self.pick({"mapper": "minimap2"}, mapping), ("minimap2", "-ax sr"))

    def test_own_flags_win(self):
        mapping = {"mapper": "minimap2", "mapper_extra_params": "-ax sr -k 15"}
        scg = {"mapper": "minimap2", "mapper_extra_params": "-ax sr -k 21"}
        self.assertEqual(self.pick(scg, mapping), ("minimap2", "-ax sr -k 21"))

    def test_empty_flags_fall_back_to_default(self):
        mapping = {"mapper": "minimap2", "mapper_extra_params": ""}
        self.assertEqual(self.pick({"mapper_extra_params": ""}, mapping), ("minimap2", "-ax sr"))


if __name__ == "__main__":
    unittest.main()

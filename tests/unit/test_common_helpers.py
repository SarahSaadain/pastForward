#!/usr/bin/env python3
"""
Unit tests for small config helpers in workflow/rules/common.smk:
_dedup_enabled, _mapper_extra, _scg_mapper_and_extra, _split_threads,
_reference_mapping_job_count, _mapdamage_chunk_bam,
_mapdamage_split_source_bam and _hardlink_or_copy.

common.smk holds plain Python only, so it is exec'd into the shared namespace
workflow/scripts/pipeline_namespace.py builds.

Run with either:
    python3 tests/unit/test_common_helpers.py
    python3 -m unittest tests.test_common_helpers -v          (from the repo root)
"""

import logging
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def DR(**kw):
    return {"reference_module": {"damage_rescaling": {"settings": kw}}}


class MapdamageExtraTest(unittest.TestCase):
    def test_default_empty(self):
        self.assertEqual(
            load()["_mapdamage_extra"](),
            "--seq-length 12 --rescale-length-5p 12 --rescale-length-3p 12",
        )

    def test_rescale_lengths_follow_seqlength(self):
        self.assertEqual(
            load(DR(rescale_seqlength=20))["_mapdamage_extra"](),
            "--seq-length 20 --rescale-length-5p 20 --rescale-length-3p 20",
        )

    def test_flags(self):
        ns = load(
            DR(
                downsample=0.5,
                rescale_seqlength=20,
                rescale_length_5p=15,
                rescale_length_3p=10,
            )
        )
        self.assertEqual(
            ns["_mapdamage_extra"](),
            "--downsample 0.5 --seq-length 20 --rescale-length-5p 15 --rescale-length-3p 10",
        )

    def test_zero_rescale_length_is_passed(self):
        self.assertEqual(
            load(DR(rescale_length_5p=0, rescale_length_3p=None))["_mapdamage_extra"](),
            "--seq-length 12 --rescale-length-5p 0 --rescale-length-3p 12",
        )

    def test_rescale_length_above_default_seqlength_raises(self):
        with self.assertRaises(ValueError):
            load(DR(rescale_length_5p=13))["_mapdamage_extra"]()

    def test_rescale_length_above_seqlength_raises(self):
        with self.assertRaises(ValueError):
            load(DR(rescale_seqlength=20, rescale_length_3p=30))["_mapdamage_extra"]()


class BamFilterExtraTest(unittest.TestCase):
    def cfg(self, **kw):
        return {"reference_module": {"bam_filtering": {"settings": kw}}}

    def test_default_empty(self):
        self.assertEqual(load()["_bam_filter_extra"](), "")

    def test_mapq_and_length(self):
        ns = load(self.cfg(min_mapq=20, min_read_length=35))
        self.assertEqual(ns["_bam_filter_extra"](), "-q 20 -e 'length(seq)>=35'")

    def test_remove_unmapped_adds_flag(self):
        self.assertEqual(load()["_bam_filter_extra"](True), "-F 4")


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
        self.assertEqual(
            self.extra({"mapper_extra_params": "-ax map-ont"}, "minimap2"),
            "-ax map-ont",
        )


class ScgMapperAndExtraTest(unittest.TestCase):
    def setUp(self):
        self.pick = load()["_scg_mapper_and_extra"]

    def test_defaults(self):
        self.assertEqual(self.pick({}, {}), ("bwa-mem3", ""))

    def test_inherits_mapper_and_flags_from_mapping(self):
        mapping = {"mapper": "bwa-aln", "mapper_extra_params": "-n 0.04"}
        self.assertEqual(self.pick({}, mapping), ("bwa-aln", "-n 0.04"))

    def test_same_mapper_borrows_flags(self):
        mapping = {"mapper": "minimap2", "mapper_extra_params": "-ax sr -k 15"}
        self.assertEqual(
            self.pick({"mapper": "minimap2"}, mapping), ("minimap2", "-ax sr -k 15")
        )

    def test_other_mapper_does_not_borrow_flags(self):
        mapping = {"mapper": "bwa-aln", "mapper_extra_params": "-n 0.04"}
        self.assertEqual(
            self.pick({"mapper": "minimap2"}, mapping), ("minimap2", "-ax sr")
        )

    def test_own_flags_win(self):
        mapping = {"mapper": "minimap2", "mapper_extra_params": "-ax sr -k 15"}
        scg = {"mapper": "minimap2", "mapper_extra_params": "-ax sr -k 21"}
        self.assertEqual(self.pick(scg, mapping), ("minimap2", "-ax sr -k 21"))

    def test_empty_flags_fall_back_to_default(self):
        mapping = {"mapper": "minimap2", "mapper_extra_params": ""}
        self.assertEqual(
            self.pick({"mapper_extra_params": ""}, mapping), ("minimap2", "-ax sr")
        )


class SplitThreadsTest(unittest.TestCase):
    def test_cases(self):
        split = load()["_split_threads"]
        for cores, jobs, want in [
            (16, 1, 16),  # one job takes every core
            (16, 2, 8),
            (16, 5, 8),  # split evenly, 2 at a time
            (12, 5, 6),
            (24, 5, 8),
            (10, 5, 10),
            (4, 5, 4),
            (16, 0, 16),  # no jobs: no division by zero
            (None, 5, 10),  # cores unknown: fallback
        ]:
            self.assertEqual(split(cores, jobs), want, (cores, jobs))

    def test_target(self):
        split = load()["_split_threads"]
        self.assertEqual(split(16, 5, target=16), 16)  # one at a time
        self.assertEqual(split(32, 5, target=16), 16)  # 2 x 16
        self.assertEqual(split(64, 5, target=16), 16)  # 4 x 16


class ReferenceMappingJobCountTest(unittest.TestCase):
    def test_counts_only_open_pairs_and_skips_species_without_reference(self):
        ns = load()
        ns["config"]["species"] = {"Sp": {}, "NoRef": {}}

        def references(species):
            if species == "NoRef":
                raise Exception("No reference found for species NoRef.")
            return ["ref"]

        ns["get_references_ids_for_species"] = references
        ns["get_individuals_for_species"] = lambda species: ["Done", "Open"]
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                mapped = "Sp/results/reference_module/ref/mapped"
                os.makedirs(mapped)
                open(f"{mapped}/Done_ref_final.bam", "w").close()
                self.assertEqual(ns["_reference_mapping_job_count"](), 1)
            finally:
                os.chdir(old_cwd)


class MapdamageChunkBamTest(unittest.TestCase):
    MAPDAMAGE_SPLIT = "Dm/processed/reference_module/ref/analytics/I1/mapdamage/split/I1_ref_chunk_{}.bam"
    RMDUP = "Dm/processed/reference_module/ref/dedup_cluster/I1/dedup_0/I1_ref_cluster_0_rmdup.bam"

    def source_bam(self, **kw):
        return self.chunk_bam("0", helper="_mapdamage_split_source_bam", **kw)

    def chunk_bam(
        self, chunk, dedup_execute=True, keep_bam=False, helper="_mapdamage_chunk_bam"
    ):
        ns = load(
            {
                "reference_module": {
                    "deduplication": {
                        "execute": dedup_execute,
                        "settings": {"keep_bam": keep_bam},
                    }
                }
            }
        )
        wildcards = SimpleNamespace(
            species="Dm", reference="ref", individual="I1", chunk=chunk
        )
        return ns[helper](wildcards)

    def test_dedup_on_reads_the_dedup_cluster_bam(self):
        self.assertEqual(self.chunk_bam("0"), self.RMDUP)

    def test_dedup_off_reads_a_chunk_cut_from_the_sorted_bam(self):
        self.assertEqual(
            self.chunk_bam("0", dedup_execute=False), self.MAPDAMAGE_SPLIT.format(0)
        )

    def test_kept_dedup_bam_is_split_instead_so_dedup_never_reruns(self):
        # the cluster BAMs are temp(); with keep_bam a later mapDamage run must use the kept BAM
        self.assertEqual(
            self.chunk_bam("0", keep_bam=True), self.MAPDAMAGE_SPLIT.format(0)
        )

    def test_cut_source_is_the_sorted_bam_when_dedup_clusters_are_the_chunks(self):
        self.assertEqual(
            self.source_bam(),
            "Dm/processed/reference_module/ref/mapped/I1_ref_sorted.bam",
        )

    def test_cut_source_is_the_kept_dedup_bam_with_keep_bam(self):
        # the sorted BAM is temp() too; reading it would remap a finished project
        self.assertEqual(
            self.source_bam(keep_bam=True),
            "Dm/processed/reference_module/ref/mapped/I1_ref_sorted_dedupped.bam",
        )

    def test_unplaced_chunk_is_always_cut(self):
        self.assertEqual(
            self.chunk_bam("unplaced"), self.MAPDAMAGE_SPLIT.format("unplaced")
        )


class HardlinkOrCopyTest(unittest.TestCase):
    def test_temp_source_is_hard_linked(self):
        cmd = load()["_hardlink_or_copy"]("a.bam", "b.bam", True)
        self.assertTrue(cmd.startswith('ln -fL "a.bam" "b.bam"'))

    def test_kept_source_is_never_hard_linked(self):
        # a hard link would share Snakemake's post-job touch with the kept source
        cmd = load()["_hardlink_or_copy"]("a.bam", "b.bam", False)
        self.assertNotIn("ln ", cmd)
        self.assertIn('cp "a.bam" "b.bam"', cmd)


if __name__ == "__main__":
    unittest.main()

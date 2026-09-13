#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/file_manager.py - discovery of raw reads, reference
genomes, feature libraries, SCG libraries, and competition FASTAs from the on-disk
convention-based layout (see the "Species/file discovery" and "Raw read filenames"
sections of CLAUDE.md).

Pure Python, no Snakemake/conda required. Each test builds a small synthetic species
library on disk (via tests/pf_test_library.py) in a throwaway temp directory and exercises
file_manager.py's functions directly against it. Run with either:
    python3 tests/test_file_manager.py
    python3 -m unittest tests.test_file_manager -v          (from the repo root)
"""
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scripts.file_manager as fm  # noqa: E402
import pf_test_library as testlib  # noqa: E402


class FileManagerTestCase(unittest.TestCase):
    """Base class: runs each test inside its own throwaway project directory, with
    file_manager's module-level `config` reset (it's a bare global, set the way Snakemake's
    `include:` would set it - see file_manager.py's _get_species_config_list)."""

    # Subclasses override to customize the fixture; None means "don't build one".
    fixture_kwargs = {}

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_project_")
        os.chdir(self.project_dir)
        fm.config = {}
        if self.fixture_kwargs is not None:
            self.lib = testlib.build_species_library(self.project_dir, **self.fixture_kwargs)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def configure(self, species_overrides=None, pipeline_overrides=None):
        cfg = {}
        if species_overrides:
            cfg["species"] = {"Dmel": species_overrides}
        if pipeline_overrides:
            cfg["pipeline"] = pipeline_overrides
        fm.config = cfg


class TestReadDiscovery(FileManagerTestCase):
    def test_get_read_files_includes_all_fastq_gz_but_not_uncompressed(self):
        basenames = sorted(os.path.basename(f) for f in fm.get_read_files_for_species("Dmel"))
        expected = sorted([
            "IND001_R1.fastq.gz", "IND001_R2.fastq.gz",
            "IND002_lib1_1.fastq.gz", "IND002_lib1_2.fastq.gz",
            "IND002_lib2_1.fastq.gz", "IND002_lib2_2.fastq.gz",
            "IND003_R1.fastq.gz",
            "IND004_readme.fastq.gz",
        ])
        self.assertEqual(basenames, expected)

    def test_get_read_files_raises_when_none_found(self):
        os.makedirs("Empty/input/read_module")
        with self.assertRaises(Exception):
            fm.get_read_files_for_species("Empty")

    def test_unmatched_read_files_are_discovered_separately(self):
        unmatched = fm._discover_unmatched_read_files_for_species("Dmel")
        self.assertEqual([os.path.basename(f) for f in unmatched], ["IND004_readme.fastq.gz"])

    def test_read_name_problem_matches_discovery(self):
        for name in ("IND001_R1.fastq.gz", "IND002_lib1_2.fq.gz", "IND_1_box-3_R2.fastq.gz"):
            self.assertIsNone(fm.get_read_name_problem(name), name)
        self.assertIn("ignores", fm.get_read_name_problem("IND004_readme.fastq.gz"))
        # Discovery raises on these, so they must be reported, not silently accepted.
        for name in ("IND_R1_x_R1.fastq.gz", "IND_2_x_2.fq.gz"):
            self.assertIn("error", fm.get_read_name_problem(name), name)

    def test_unmatched_read_files_include_ambiguous_names_without_raising(self):
        open("Dmel/input/read_module/IND009_R1_L1_R1.fastq.gz", "w").close()
        unmatched = fm._discover_unmatched_read_files_for_species("Dmel")
        self.assertEqual(
            sorted(os.path.basename(f) for f in unmatched),
            ["IND004_readme.fastq.gz", "IND009_R1_L1_R1.fastq.gz"],
        )

    def test_uncompressed_fastq_is_discovered_but_not_processed(self):
        uncompressed = fm._discover_uncompressed_fastq_files_for_species("Dmel")
        self.assertEqual([os.path.basename(f) for f in uncompressed], ["IND005_R1.fastq"])
        all_read_files = [os.path.basename(f) for f in fm.get_read_files_for_species("Dmel")]
        self.assertNotIn("IND005_R1.fastq", all_read_files)

    def test_strip_raw_read_extension(self):
        self.assertEqual(fm.strip_raw_read_extension("IND001_R1.fastq.gz"), "IND001_R1")
        self.assertEqual(fm.strip_raw_read_extension("IND001_R1.fq.gz"), "IND001_R1")
        self.assertEqual(fm.strip_raw_read_extension("IND001_R1.bam"), "IND001_R1.bam")

    def test_get_raw_read_path_for_stem(self):
        path = fm.get_raw_read_path_for_stem("Dmel", "IND001_R1")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith("IND001_R1.fastq.gz"))
        with self.assertRaises(FileNotFoundError):
            fm.get_raw_read_path_for_stem("Dmel", "NOPE_R1")

    def test_get_read2_counterpart_path_r1_naming(self):
        r1 = os.path.join("Dmel/input/read_module", "IND001_R1.fastq.gz")
        r2 = fm.get_read2_counterpart_path(r1)
        self.assertEqual(os.path.basename(r2), "IND001_R2.fastq.gz")

    def test_get_read2_counterpart_path_standalone_naming(self):
        r1 = os.path.join("Dmel/input/read_module", "IND002_lib1_1.fastq.gz")
        r2 = fm.get_read2_counterpart_path(r1)
        self.assertEqual(os.path.basename(r2), "IND002_lib1_2.fastq.gz")

    def test_get_read2_counterpart_path_raises_without_marker(self):
        unmatched = os.path.join("Dmel/input/read_module", "IND004_readme.fastq.gz")
        with self.assertRaises(ValueError):
            fm.get_read2_counterpart_path(unmatched)


class TestIndividualsAndSamples(FileManagerTestCase):
    def test_individuals_discovered_sorted_excluding_unmatched(self):
        self.assertEqual(fm.get_individuals_for_species("Dmel"), ["IND001", "IND002", "IND003"])

    def test_individuals_config_filter(self):
        self.configure(species_overrides={"individuals": ["IND002"]})
        self.assertEqual(fm.get_individuals_for_species("Dmel"), ["IND002"])

    def test_individuals_config_filter_missing_raises(self):
        self.configure(species_overrides={"individuals": ["NOPE"]})
        with self.assertRaises(fm.ConfigValidationError) as ctx:
            fm.get_individuals_for_species("Dmel")
        self.assertIn("NOPE", str(ctx.exception))

    def test_sample_ids_discovered(self):
        self.assertEqual(
            set(fm.get_sample_ids_for_species("Dmel")),
            {"IND001", "IND002_lib1", "IND002_lib2", "IND003"},
        )

    def test_sample_ids_config_filtered_by_individual(self):
        self.configure(species_overrides={"individuals": ["IND002"]})
        self.assertEqual(set(fm.get_sample_ids_for_species("Dmel")), {"IND002_lib1", "IND002_lib2"})

    def test_samples_for_multi_sample_individual(self):
        self.assertEqual(sorted(fm.get_samples_for_species_individual("Dmel", "IND002")),
                          ["IND002_lib1", "IND002_lib2"])

    def test_samples_for_single_sample_individual(self):
        self.assertEqual(fm.get_samples_for_species_individual("Dmel", "IND001"), ["IND001"])

    def test_samples_for_unknown_individual_raises(self):
        with self.assertRaises(Exception):
            fm.get_samples_for_species_individual("Dmel", "NOPE")

    def test_raw_reads_for_paired_sample(self):
        reads = fm.get_raw_reads_for_sample("Dmel", "IND001")
        self.assertEqual([os.path.basename(r) for r in reads], ["IND001_R1.fastq.gz", "IND001_R2.fastq.gz"])

    def test_raw_reads_for_single_end_sample(self):
        reads = fm.get_raw_reads_for_sample("Dmel", "IND003")
        self.assertEqual([os.path.basename(r) for r in reads], ["IND003_R1.fastq.gz"])

    def test_raw_reads_for_unknown_sample_raises(self):
        with self.assertRaises(FileNotFoundError):
            fm.get_raw_reads_for_sample("Dmel", "NOPE")

    def test_individual_from_sample_and_filepath(self):
        self.assertEqual(fm.get_individual_from_sample("IND002_lib1"), "IND002")
        path = os.path.join("Dmel/input/read_module", "IND002_lib1_1.fastq.gz")
        self.assertEqual(fm.get_individual_from_filepath(path), "IND002")


class TestReferenceDiscovery(FileManagerTestCase):
    def test_references_discovered_with_dotted_ids_sanitized(self):
        refs = dict(fm.get_reference_file_list_for_species("Dmel"))
        self.assertEqual(set(refs.keys()), {"genome", "alt_assembly_v2"})

    def test_references_config_filter_preserves_requested_order(self):
        self.configure(species_overrides={"references": ["alt_assembly_v2", "genome"]})
        result = fm.get_reference_file_list_for_species("Dmel")
        self.assertEqual([r[0] for r in result], ["alt_assembly_v2", "genome"])

    def test_references_config_filter_missing_raises(self):
        self.configure(species_overrides={"references": ["NOPE"]})
        with self.assertRaises(fm.ConfigValidationError):
            fm.get_reference_file_list_for_species("Dmel")

    def test_references_paths_and_ids_helpers(self):
        self.assertEqual(set(fm.get_references_ids_for_species("Dmel")), {"genome", "alt_assembly_v2"})
        self.assertEqual(len(fm.get_references_paths_for_species("Dmel")), 2)


class TestReferenceDiscoveryEdgeCases(FileManagerTestCase):
    fixture_kwargs = None  # each test builds its own fixture

    def test_no_reference_files_raises(self):
        os.makedirs("Dmel/input/reference_module")
        with self.assertRaises(Exception):
            fm.get_reference_file_list_for_species("Dmel")

    def test_scg_determination_reference_auto_detected_when_single(self):
        testlib.build_species_library(self.project_dir, include_second_reference=False)
        path = fm.get_scg_determination_reference_path("Dmel")
        self.assertTrue(path.endswith("genome.fasta"))

    def test_scg_determination_reference_ambiguous_raises(self):
        testlib.build_species_library(self.project_dir, include_second_reference=True)
        with self.assertRaises(ValueError):
            fm.get_scg_determination_reference_path("Dmel")

    def test_scg_determination_reference_config_override_wins(self):
        testlib.build_species_library(self.project_dir, include_second_reference=True)
        self.configure(species_overrides={"scg_reference": "/some/explicit/path.fasta"})
        self.assertEqual(fm.get_scg_determination_reference_path("Dmel"), "/some/explicit/path.fasta")

    def test_scg_determination_reference_none_found_raises(self):
        # get_reference_file_list_for_species() itself raises (plain Exception, not
        # ValueError) when zero reference files are found on disk, before
        # get_scg_determination_reference_path()'s own "len(refs) == 0" ValueError check
        # ever runs - assert the behavior actually observed, not the dead-code branch.
        os.makedirs("Dmel/input/reference_module")
        fm.config = {}
        with self.assertRaises(Exception):
            fm.get_scg_determination_reference_path("Dmel")


class TestFeatureLibraryDiscovery(FileManagerTestCase):
    fixture_kwargs = {"include_second_feature_library": True}

    def test_feature_libraries_discovered(self):
        self.assertEqual(set(fm.get_feature_library_ids_for_species("Dmel")), {"te_features", "my_extra_lib"})

    def test_feature_library_config_filter_missing_raises(self):
        self.configure(species_overrides={"feature_libraries": ["NOPE"]})
        with self.assertRaises(fm.ConfigValidationError):
            fm.get_feature_library_file_list_for_species("Dmel")

    def test_get_feature_library_file_for_species_and_library(self):
        path = fm.get_feature_library_file_for_species_and_library("Dmel", "te_features")
        self.assertTrue(path.endswith("te_features.fasta"))
        with self.assertRaises(Exception):
            fm.get_feature_library_file_for_species_and_library("Dmel", "NOPE")


class TestFeatureLibraryMissing(FileManagerTestCase):
    fixture_kwargs = {"include_feature_library": False}

    def test_no_feature_library_files_raises(self):
        with self.assertRaises(Exception):
            fm.get_feature_library_file_list_for_species("Dmel")


class TestScgDiscovery(FileManagerTestCase):
    def test_scg_library_empty_by_default_no_exception(self):
        self.assertEqual(fm.get_scg_library_file_list_for_species("Dmel"), [])

    def test_get_scg_library_file_for_species_and_library_missing_raises(self):
        with self.assertRaises(ValueError):
            fm.get_scg_library_file_for_species_and_library("Dmel", "NOPE")

    def test_should_auto_determine_scg_true_by_default_with_lineage(self):
        self.configure(species_overrides={"lineage": "drosophilidae_odb12"})
        self.assertTrue(fm.should_auto_determine_scg("Dmel"))

    def test_should_auto_determine_scg_false_without_lineage(self):
        fm.config = {}
        self.assertFalse(fm.should_auto_determine_scg("Dmel"))

    def test_should_auto_determine_scg_false_when_selector_disabled(self):
        fm.config = {
            "pipeline": {"reveal_module": {"scg_selector": {"execute": False}}},
            "species": {"Dmel": {"lineage": "drosophilidae_odb12"}},
        }
        self.assertFalse(fm.should_auto_determine_scg("Dmel"))

    def test_effective_scg_id_and_path_when_none_provided(self):
        self.assertEqual(fm.get_effective_scg_library_id_for_species("Dmel"), "Dmel_determined_scg")
        self.assertEqual(
            fm.get_effective_scg_library_path_for_species("Dmel"),
            "Dmel/results/reveal_module/scg/Dmel_relevant_scg.fasta",
        )


class TestScgDiscoveryWithUserLibrary(FileManagerTestCase):
    fixture_kwargs = {"include_scg": True}

    def test_scg_library_discovered(self):
        scgs = fm.get_scg_library_file_list_for_species("Dmel")
        self.assertEqual([s[0] for s in scgs], ["scg_markers"])

    def test_should_auto_determine_scg_false_when_user_scg_present(self):
        self.configure(species_overrides={"lineage": "drosophilidae_odb12"})
        self.assertFalse(fm.should_auto_determine_scg("Dmel"))

    def test_effective_scg_id_and_path_prefer_user_provided(self):
        self.assertEqual(fm.get_effective_scg_library_id_for_species("Dmel"), "scg_markers")
        self.assertTrue(fm.get_effective_scg_library_path_for_species("Dmel").endswith("scg_markers.fasta"))


class TestCompetitionFasta(FileManagerTestCase):
    def test_none_when_absent(self):
        self.assertIsNone(fm.get_competition_fasta_for_species("Dmel"))

    def test_single_file_returned(self):
        testlib.write_fasta(os.path.join("Dmel/input/reveal_module/competition", "competitor.fasta"))
        path = fm.get_competition_fasta_for_species("Dmel")
        self.assertTrue(path.endswith("competitor.fasta"))

    def test_multiple_files_raises(self):
        comp_dir = "Dmel/input/reveal_module/competition"
        testlib.write_fasta(os.path.join(comp_dir, "one.fasta"))
        testlib.write_fasta(os.path.join(comp_dir, "two.fasta"))
        with self.assertRaises(ValueError):
            fm.get_competition_fasta_for_species("Dmel")


class TestFeatureLibraryIdCleaning(FileManagerTestCase):
    def test_dots_replaced_with_underscores(self):
        self.assertEqual(
            fm.get_cleaned_feature_library_id_for_library_path("/x/EquCab3.0.fna"),
            "EquCab3_0",
        )


class TestReadMarkerRPrefersOverBare(unittest.TestCase):
    """A bare replicate/box number elsewhere in the filename (e.g. "..._B_1_box-1-22_R1...")
    must not be mistaken for the read marker when an explicit R1/R2 token is present."""

    def test_r1_marker_used_even_with_earlier_bare_1(self):
        marker = fm._find_read_marker("Tni157_B_1_box-1-22_R1.fastq.gz", "1")
        self.assertEqual(marker.group(0), "_R1")

    def test_r2_marker_used_even_with_earlier_bare_2(self):
        marker = fm._find_read_marker("Tni157_B_2_box-1-26_R2.fastq.gz", "2")
        self.assertEqual(marker.group(0), "_R2")

    def test_r2_counterpart_of_r1_file_with_earlier_bare_digit(self):
        r1 = "Tni157_2_box-1-20_R1.fastq.gz"
        self.assertEqual(fm.get_read2_counterpart_path(r1), "Tni157_2_box-1-20_R2.fastq.gz")

    def test_multiple_bare_markers_raise(self):
        with self.assertRaises(ValueError):
            fm._find_read_marker("Sample_1_rep_1.fastq.gz", "1")

    def test_multiple_r_markers_raise(self):
        with self.assertRaises(ValueError):
            fm._find_read_marker("Sample_R1_dup_R1.fastq.gz", "1")

    def test_single_bare_marker_still_works(self):
        marker = fm._find_read_marker("IND002_lib1_1.fastq.gz", "1")
        self.assertEqual(marker.group(0), "_1")

    def test_no_r1_marker_when_only_r2_present_with_confusable_bare_1(self):
        # "DfunF2_B_1_box-3-227_R2.fastq.gz" is a real R2 file whose replicate/box number
        # (the "_1_") must not be mistaken for a bare R1 marker just because this
        # particular filename happens to have no explicit "_R1" of its own.
        self.assertIsNone(fm._find_read_marker("DfunF2_B_1_box-3-227_R2.fastq.gz", "1"))

    def test_no_r2_marker_when_only_r1_present_with_confusable_bare_2(self):
        self.assertIsNone(fm._find_read_marker("DfunF2_B_2_box-3-231_R1.fastq.gz", "2"))

    def test_sample_ids_not_confused_across_replicates(self):
        # Regression for the "DfunF2_B" phantom-sample incident: three replicates, each with
        # its own explicit R1/R2 pair, must yield three distinct sample IDs - not a spurious
        # extra "DfunF2_B" sample formed by cross-matching one replicate's R2 with another's R1.
        files = [
            "DfunF2_B_1_box-3-227_R1.fastq.gz",
            "DfunF2_B_1_box-3-227_R2.fastq.gz",
            "DfunF2_B_2_box-3-231_R1.fastq.gz",
            "DfunF2_B_2_box-3-231_R2.fastq.gz",
            "DfunF2_B_3_box-3-219_R1.fastq.gz",
            "DfunF2_B_3_box-3-219_R2.fastq.gz",
        ]
        r1_files = [f for f in files if fm._find_read_marker(f, "1")]
        samples = [f[: fm._find_read_marker(f, "1").start()] for f in r1_files]
        self.assertEqual(
            sorted(samples),
            sorted(["DfunF2_B_1_box-3-227", "DfunF2_B_2_box-3-231", "DfunF2_B_3_box-3-219"]),
        )


class TestOneReadFileOrPairPerSample(unittest.TestCase):
    """get_raw_reads_for_sample() must resolve exactly one R1 (and, if present, exactly one
    R2) per sample. Two physical files that both resolve to the same sample+read-number are
    two different specimens/libraries colliding under one name - that must error, never
    silently pick one and drop the other (see the box-22/box-26 "_B" incident)."""

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_dupreads_")
        os.chdir(self.project_dir)
        fm.config = {}
        self.reads_dir = os.path.join(self.project_dir, "Dmel", "input", "read_module")

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_single_r1_r2_pair_resolves_fine(self):
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R1.fastq.gz"))
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R2.fastq.gz"))
        r1, r2 = fm.get_raw_reads_for_sample("Dmel", "IND001")
        self.assertTrue(r1.endswith("IND001_R1.fastq.gz"))
        self.assertTrue(r2.endswith("IND001_R2.fastq.gz"))

    def test_two_r1_candidates_for_same_sample_raises(self):
        # Same sample, same read number, two extensions on disk - ambiguous, must not
        # silently pick one.
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R1.fastq.gz"))
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R1.fq.gz"))
        with self.assertRaisesRegex(ValueError, "Rename these files"):
            fm.get_raw_reads_for_sample("Dmel", "IND001")

    def test_two_r2_candidates_for_same_sample_raises(self):
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R1.fastq.gz"))
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R2.fastq.gz"))
        testlib.write_fastq_gz(os.path.join(self.reads_dir, "IND001_R2.fq.gz"))
        with self.assertRaisesRegex(ValueError, "Rename these files"):
            fm.get_raw_reads_for_sample("Dmel", "IND001")


if __name__ == "__main__":
    unittest.main(verbosity=2)

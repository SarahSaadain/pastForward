#!/usr/bin/env python3
"""
Unit tests for the DAG-target computation chain: workflow/scripts/expected_output_manager.py
and its four workflow/scripts/expected_output/expected_output_manager_<module>_processing.py
submodules. This is the "config.yaml execute: true/false flags -> list of files rule `all`
requests" logic described in CLAUDE.md's Architecture section - the piece most likely to be
wired wrong when a new pipeline step or config toggle is added, and the thing these tests
exist to catch quickly, without needing Snakemake, conda, or any bioinformatics tools.

Each test builds a small synthetic species library on disk (via tests/pf_test_library.py)
and loads the manager scripts into a shared namespace that mimics Snakemake's `include:`
(via workflow/scripts/pipeline_namespace.py), then calls get_expected_outputs_from_pipeline() with a
chosen config and asserts on which output paths are/aren't requested. Assertions target
representative, distinctive path fragments rather than exhaustive output lists, so they
track intent (e.g. "reference module outputs must disappear when reference_module.execute
is false") without being brittle to unrelated output additions elsewhere.

Run with either:
    python3 tests/test_expected_output_manager.py
    python3 -m unittest tests.test_expected_output_manager -v          (from the repo root)
"""
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pf_test_library as testlib  # noqa: E402
from scripts.pipeline_namespace import load_pipeline_namespace  # noqa: E402
from build_test_library import DEFAULT_TARGET as _PERSISTENT_LIBRARY_TARGET  # noqa: E402


def setUpModule():
    # Also materializes a persistent, inspectable copy under tests/fixtures/ (gitignored)
    # as a side effect of running the suite - see tests/build_test_library.py. The
    # assertions below use their own hermetic tempdir copies, not this one.
    try:
        testlib.materialize_reference_library(_PERSISTENT_LIBRARY_TARGET)
    except OSError:
        pass  # best-effort convenience artifact; must never fail the actual test run


class ExpectedOutputManagerTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_project_")
        os.chdir(self.project_dir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def get_all_outputs(self, config):
        ns = load_pipeline_namespace(config)
        return ns["get_expected_outputs_from_pipeline"](None)

    def load(self, config):
        return load_pipeline_namespace(config)


class TestCoreOutputsFromMinimalConfig(ExpectedOutputManagerTestCase):
    def setUp(self):
        super().setUp()
        self.lib = testlib.build_species_library(self.project_dir)
        self.config = {"species": {"Dmel": {"name": "Drosophila melanogaster", "lineage": "drosophilidae_odb12"}}}

    def test_representative_outputs_present_across_all_modules(self):
        outputs = self.get_all_outputs(self.config)
        expected_present = [
            "Dmel/results/read_module/reads_merged/IND001.fastq.gz",
            "Dmel/results/read_module/reads_merged/IND002.fastq.gz",
            "Dmel/results/read_module/statistics/Dmel_reads_counts.csv",
            "Dmel/results/reference_module/genome/mapped/IND001_genome_final.bam",
            "Dmel/results/reference_module/genome/mapped/IND001_genome_final.bam.bai",
            "Dmel/results/reference_module/alt_assembly_v2/mapped/IND003_alt_assembly_v2_final.bam",
            "Dmel/results/reveal_module/scg/Dmel_scg_ranked.tsv",
            "Dmel/results/reveal_module/scg/Dmel_scg_ranked.json",
            "Dmel/results/reveal_module/te_features/visualization/individual_level/IND001_coverage.tsv.gz",
            "Dmel/results/summary/species_level/Dmel_multiqc.overall.html",
            "Dmel/results/summary/individual_level/IND001_multiqc.html",
        ]
        for path in expected_present:
            self.assertIn(path, outputs, f"expected output missing: {path}")

    def test_unmapped_reads_filtering_absent_by_default(self):
        # filter_unmapped_reads.execute defaults to False (unlike almost every other switch,
        # which defaults True) - a regression here would silently start requesting BAM
        # post-processing nobody asked for.
        outputs = self.get_all_outputs(self.config)
        self.assertFalse(any("unmapped" in o for o in outputs))


class TestSpeciesExecuteFlag(ExpectedOutputManagerTestCase):
    def test_disabled_species_produces_no_outputs_but_others_still_run(self):
        testlib.build_species_library(self.project_dir, species="Dmel")
        testlib.build_species_library(self.project_dir, species="Equus")
        config = {
            "species": {
                "Dmel": {"lineage": "drosophilidae_odb12"},
                "Equus": {"lineage": "equidae_odb10", "execute": False},
            }
        }
        outputs = self.get_all_outputs(config)
        self.assertTrue(any(o.startswith("Dmel/") for o in outputs))
        self.assertFalse(any(o.startswith("Equus/") for o in outputs))


class TestModuleExecuteFlags(ExpectedOutputManagerTestCase):
    def setUp(self):
        super().setUp()
        testlib.build_species_library(self.project_dir)
        self.base_config = {"species": {"Dmel": {"lineage": "drosophilidae_odb12"}}}

    def test_read_module_disabled(self):
        config = dict(self.base_config, pipeline={"read_module": {"execute": False}})
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("results/read_module" in o for o in outputs))
        self.assertTrue(any("results/reference_module" in o for o in outputs))

    def test_reference_module_disabled(self):
        config = dict(self.base_config, pipeline={"reference_module": {"execute": False}})
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("results/reference_module" in o for o in outputs))
        self.assertTrue(any("results/read_module" in o for o in outputs))

    def test_reveal_module_disabled(self):
        config = dict(self.base_config, pipeline={"reveal_module": {"execute": False}})
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("results/reveal_module" in o for o in outputs))
        self.assertTrue(any("results/summary" in o for o in outputs))

    def test_summary_module_disabled(self):
        config = dict(self.base_config, pipeline={"summary_module": {"execute": False}})
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("results/summary" in o for o in outputs))
        self.assertTrue(any("results/read_module" in o for o in outputs))


class TestTaxonomicScreeningToolToggles(ExpectedOutputManagerTestCase):
    def setUp(self):
        super().setUp()
        testlib.build_species_library(self.project_dir)
        self.base_config = {"species": {"Dmel": {"lineage": "drosophilidae_odb12"}}}

    def test_centrifuge_disabled_leaves_ecmsd(self):
        config = dict(self.base_config, pipeline={
            "read_module": {"taxonomic_screening": {"tools": {"centrifuge": {"execute": False}}}}
        })
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("taxonomic_screening/centrifuge" in o for o in outputs))
        self.assertTrue(any("taxonomic_screening/ecmsd" in o for o in outputs))

    def test_ecmsd_disabled_leaves_centrifuge(self):
        config = dict(self.base_config, pipeline={
            "read_module": {"taxonomic_screening": {"tools": {"ecmsd": {"execute": False}}}}
        })
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("taxonomic_screening/ecmsd" in o for o in outputs))
        self.assertTrue(any("taxonomic_screening/centrifuge" in o for o in outputs))

    def test_deprecated_contamination_key_still_toggles_tools(self):
        """`taxonomic_screening` was previously called `contamination`; config_compat
        keeps the old key working, so a config written against the old name must still
        reach the same expected outputs."""
        config = dict(self.base_config, pipeline={
            "read_module": {"contamination": {"tools": {"centrifuge": {"execute": False}}}}
        })
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("taxonomic_screening/centrifuge" in o for o in outputs))
        self.assertTrue(any("taxonomic_screening/ecmsd" in o for o in outputs))

    def test_deprecated_contamination_key_still_disables_whole_step(self):
        config = dict(self.base_config, pipeline={
            "read_module": {"contamination": {"execute": False}}
        })
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("taxonomic_screening" in o for o in outputs))


class TestScgSelectorDefaults(ExpectedOutputManagerTestCase):
    """Regression coverage for the scg_selector.execute default, which drifted out of sync
    with file_manager.should_auto_determine_scg() (default True), check.py (default True)
    and the documented behavior (docs/FAQ.md, docs/process_overview.md: "true (the
    default)") - expected_output_manager_reveal_module_processing.py had defaulted it to
    False, which silently skipped SCG auto-determination for any config that (per the docs)
    correctly omits scg_selector.execute entirely."""

    def setUp(self):
        super().setUp()
        testlib.build_species_library(self.project_dir, include_second_reference=False)
        self.base_config = {"species": {"Dmel": {"lineage": "drosophilidae_odb12"}}}

    def test_scg_selector_omitted_still_auto_determines(self):
        outputs = self.get_all_outputs(self.base_config)  # no pipeline key at all
        self.assertIn("Dmel/results/reveal_module/scg/Dmel_scg_ranked.tsv", outputs)
        self.assertIn("Dmel/results/reveal_module/scg/Dmel_scg_ranked.json", outputs)
        # and REVEAL analysis itself must not be skipped for "no SCG library"
        self.assertTrue(any("visualization" in o for o in outputs))

    def test_scg_selector_explicitly_disabled_skips_reveal_entirely(self):
        config = dict(self.base_config, pipeline={"reveal_module": {"scg_selector": {"execute": False}}})
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("results/reveal_module" in o for o in outputs))

    def test_user_provided_scg_skips_auto_determination(self):
        testlib.build_species_library(self.project_dir, include_second_reference=False, include_scg=True)
        outputs = self.get_all_outputs(self.base_config)
        self.assertFalse(any("scg_ranked" in o for o in outputs))
        self.assertTrue(any("visualization" in o for o in outputs))

    def test_multiple_user_scg_libraries_raise(self):
        testlib.write_fasta("Dmel/input/reveal_module/scg/first.fasta")
        testlib.write_fasta("Dmel/input/reveal_module/scg/second.fasta")
        ns = self.load(self.base_config)
        with self.assertRaises(ValueError):
            ns["get_expected_output_reveal_module_processing"]("Dmel")

    def test_no_feature_library_returns_scg_outputs_only(self):
        testlib.build_species_library(
            self.project_dir, species="NoLib", include_second_reference=False, include_feature_library=False
        )
        config = {"species": {"NoLib": {"lineage": "drosophilidae_odb12"}}}
        ns = self.load(config)
        outputs = ns["get_expected_output_reveal_module_processing"]("NoLib")
        self.assertEqual(
            sorted(outputs),
            sorted([
                "NoLib/results/reveal_module/scg/NoLib_scg_ranked.tsv",
                "NoLib/results/reveal_module/scg/NoLib_scg_ranked.json",
            ]),
        )


    def test_skip_low_coverage_individuals_adds_excluded_report(self):
        outputs = self.get_all_outputs(self.base_config)
        self.assertFalse(any("excluded_individuals" in o for o in outputs))

        config = dict(
            self.base_config,
            pipeline={"reveal_module": {"normalization": {"settings": {"skip_low_coverage_individuals": True}}}},
        )
        outputs = self.get_all_outputs(config)
        self.assertTrue(any(o.endswith("_excluded_individuals.tsv") for o in outputs))


class TestSkipExistingFiles(ExpectedOutputManagerTestCase):
    def setUp(self):
        super().setUp()
        testlib.build_species_library(self.project_dir)
        self.config = {"species": {"Dmel": {"lineage": "drosophilidae_odb12"}}}
        self.existing_output = "Dmel/results/read_module/statistics/Dmel_reads_counts.csv"
        os.makedirs(os.path.dirname(self.existing_output))
        with open(self.existing_output, "w") as f:
            f.write("already computed")

    def test_existing_output_kept_by_default(self):
        outputs = self.get_all_outputs(self.config)
        self.assertIn(self.existing_output, outputs)

    def test_existing_output_kept_when_skip_disabled(self):
        config = dict(self.config, pipeline={"global": {"skip_existing_files": False}})
        outputs = self.get_all_outputs(config)
        self.assertIn(self.existing_output, outputs)

    def test_existing_output_skipped_when_skip_enabled(self):
        config = dict(self.config, pipeline={"global": {"skip_existing_files": True}})
        outputs = self.get_all_outputs(config)
        self.assertNotIn(self.existing_output, outputs)


class TestReferenceModuleToggles(ExpectedOutputManagerTestCase):
    def setUp(self):
        super().setUp()
        testlib.build_species_library(self.project_dir, include_second_reference=False)
        self.base_config = {"species": {"Dmel": {"lineage": "drosophilidae_odb12"}}}

    def test_create_plots_disabled(self):
        config = dict(self.base_config, pipeline={
            "reference_module": {"analysis": {"settings": {"create_plots": False}}}
        })
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("reference_module/genome/plots" in o for o in outputs))
        self.assertTrue(any("genome/mapped" in o for o in outputs))

    def test_damage_analysis_disabled(self):
        config = dict(self.base_config, pipeline={
            "reference_module": {"analysis": {"settings": {"damage_analysis": False}}}
        })
        outputs = self.get_all_outputs(config)
        self.assertFalse(any("mapdamage" in o for o in outputs))

    def test_filter_unmapped_reads_extract_fastq_adds_output(self):
        config = dict(self.base_config, pipeline={
            "reference_module": {"filter_unmapped_reads": {"execute": True, "settings": {"action": "extract_fastq"}}}
        })
        outputs = self.get_all_outputs(config)
        self.assertIn("Dmel/results/reference_module/genome/unmapped/IND001_genome_unmapped.fastq.gz", outputs)


if __name__ == "__main__":
    unittest.main(verbosity=2)

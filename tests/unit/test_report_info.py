#!/usr/bin/env python3
"""
Unit tests for the MultiQC report info sections (tool versions, raw result locations):

    workflow/scripts/summary_module/create_report_info.py
    create_report_info_input in workflow/rules/common.smk

Pure Python, stdlib only. Run with:
    python3 tests/unit/test_report_info.py
"""

import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pf_test_library as testlib  # noqa: E402
from scripts.pipeline_namespace import load_pipeline_namespace  # noqa: E402
from scripts.summary_module.create_report_info import (  # noqa: E402
    raw_result_rows,
    read_db_info,
    read_version,
    tool_rows,
    write_sections,
)

COMMON_SMK = os.path.join(REPO_ROOT, "workflow", "rules", "common.smk")


def steps(config, references=("genome",)):
    return {row[0] for row in raw_result_rows(config, "Dmel", list(references))}


class RawResultRowsTest(unittest.TestCase):
    def test_default_config_lists_the_default_steps(self):
        found = steps({})
        for step in (
            "ECMSD",
            "Centrifuge",
            "Read statistics",
            "Final BAM (genome)",
            "Authenticity table (genome)",
            "REVEAL feature copy number",
            "Summary reports",
        ):
            self.assertIn(step, found)
        self.assertNotIn("SNP divergence (genome)", found)
        self.assertNotIn("Final reads", found)

    def test_switched_off_steps_are_left_out(self):
        pipeline = {
            "read_module": {
                "taxonomic_screening": {"tools": {"ecmsd": {"execute": False}}}
            },
            "reveal_module": {"execute": False},
            "summary_module": {"execute": False},
        }
        found = steps({"pipeline": pipeline})
        self.assertNotIn("ECMSD", found)
        self.assertIn("Centrifuge", found)
        self.assertNotIn("REVEAL feature copy number", found)
        self.assertNotIn("Summary reports", found)

    def test_module_off_drops_all_its_steps(self):
        rows = raw_result_rows(
            {"pipeline": {"read_module": {"execute": False}}}, "Dmel", ["genome"]
        )
        self.assertFalse([r for r in rows if "/read_module/" in r[1]])
        self.assertTrue(rows)

    def test_opt_in_steps(self):
        found = steps(
            {
                "pipeline": {
                    "read_module": {
                        "quality_filtering": {"settings": {"keep_reads": True}}
                    },
                    "reference_module": {
                        "analysis": {"settings": {"snp_divergence_check": True}}
                    },
                }
            },
            references=("genome", "mt"),
        )
        self.assertIn("Final reads", found)
        self.assertIn("SNP divergence (genome)", found)
        self.assertIn("SNP divergence (mt)", found)

    def test_kept_reads_need_the_step_that_makes_them(self):
        pipeline = {
            "read_module": {
                "adapter_removal": {"execute": False, "settings": {"keep_reads": True}},
                "quality_filtering": {
                    "execute": False,
                    "settings": {"keep_reads": True},
                },
            }
        }
        found = steps({"pipeline": pipeline})
        self.assertNotIn("Adapter-removed reads", found)
        self.assertNotIn("Final reads", found)

    def test_paths_start_with_the_species_folder(self):
        for _, folder, _ in raw_result_rows({}, "Dmel", ["genome"]):
            self.assertTrue(folder.startswith("Dmel/results/"), folder)


class ToolRowsTest(unittest.TestCase):
    def test_pipeline_only(self):
        self.assertEqual(tool_rows("2.2.0"), [("pastForward", "2.2.0", "")])

    def test_database_rows_use_file_dates(self):
        with tempfile.TemporaryDirectory() as db:
            os.makedirs(os.path.join(db, "NCBI_taxdump"))
            for name in (
                "mitochondrion_refseq_taxid_masked.fna.gz",
                "NCBI_taxdump/nodes.dmp",
            ):
                with open(os.path.join(db, name), "w") as f:
                    f.write("x")
            os.utime(os.path.join(db, "NCBI_taxdump/nodes.dmp"), (0, 86400 * 365))
            rows = {
                r[0]: r
                for r in tool_rows(
                    "2.2.0",
                    ecmsd={"version": "ECMSD version 1.2.0", "source": "conda"},
                    reveal={"version": "REVEAL 1.0.1", "source": "conda"},
                    ecmsd_db=db,
                    taxonomic_hierarchy="species",
                )
            }
        self.assertEqual(rows["ECMSD"][1], "ECMSD version 1.2.0")
        self.assertEqual(rows["REVEAL"][1], "REVEAL 1.0.1")
        self.assertEqual(
            rows["ECMSD database: NCBI taxonomy nodes"][1], "file date 1971-01-01"
        )
        # A file that was never built is named, not skipped
        self.assertEqual(
            rows["ECMSD database: NCBI taxonomy names"][1], "file date missing"
        )

    def test_db_info_replaces_file_dates(self):
        with tempfile.TemporaryDirectory() as db:
            with open(os.path.join(db, "db_info.txt"), "w") as f:
                f.write(
                    "built\t2026-11-01\nrefseq_release\t230\nrefseq_downloaded\t2026-10-30\n"
                )
            self.assertEqual(read_db_info(db)["refseq_release"], "230")
            rows = {
                r[0]: r[1]
                for r in tool_rows(
                    "2.2.0",
                    ecmsd={"version": "v", "source": "dev"},
                    ecmsd_db=db,
                )
            }
        self.assertEqual(rows["ECMSD database: mitogenomes downloaded"], "2026-10-30")
        self.assertEqual(rows["ECMSD database: RefSeq release"], "230")
        self.assertNotIn("ECMSD database: NCBI taxonomy nodes", rows)

    def test_read_version(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v.txt")
            with open(path, "w") as f:
                f.write("\nREVEAL 1.0.1\n")
            self.assertEqual(read_version(path), "REVEAL 1.0.1")
            self.assertEqual(read_version(os.path.join(d, "none")), "unknown")

    def test_written_sections_are_valid_custom_content(self):
        with tempfile.TemporaryDirectory() as d:
            v, r = os.path.join(d, "v.json"), os.path.join(d, "r.json")
            write_sections(
                v, r, [("pastForward", "<2.2>", "")], [("A", "Dmel/x/", "b & c")]
            )
            with open(v) as f:
                versions = json.load(f)
            with open(r) as f:
                raw = json.load(f)
        for section in (versions, raw):
            self.assertEqual(section["plot_type"], "html")
            self.assertTrue(section["id"] and section["section_name"])
        self.assertIn("&lt;2.2&gt;", versions["data"])
        self.assertIn("<code>Dmel/x/</code>", raw["data"])
        self.assertIn("b &amp; c", raw["data"])


class ReportInfoInputTest(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.project = tempfile.mkdtemp(prefix="pf_test_report_info_")
        os.chdir(self.project)
        testlib.build_species_library(self.project)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self.project, ignore_errors=True)

    def inputs(self, pipeline=None):
        ns = load_pipeline_namespace(
            {
                "species": {"Dmel": {"lineage": "drosophilidae_odb12"}},
                "pipeline": pipeline or {},
            }
        )
        ns["logger"] = logging.getLogger("test_report_info")
        with open(COMMON_SMK) as f:
            exec(compile(f.read(), COMMON_SMK, "exec"), ns)
        return ns["create_report_info_input"](SimpleNamespace(species="Dmel"))

    def test_default_has_both_tools(self):
        got = self.inputs()
        self.assertEqual(set(got), {"ecmsd_version", "ecmsd_db", "reveal_version"})
        self.assertEqual(len(got["ecmsd_db"]), 3)

    def test_tools_that_are_off_get_no_input(self):
        got = self.inputs(
            {
                "reveal_module": {"execute": False},
                "read_module": {
                    "taxonomic_screening": {"tools": {"ecmsd": {"execute": False}}}
                },
            }
        )
        self.assertEqual(got, {})

    def test_read_module_off_drops_ecmsd(self):
        got = self.inputs({"read_module": {"execute": False}})
        self.assertNotIn("ecmsd_version", got)
        self.assertIn("reveal_version", got)


if __name__ == "__main__":
    unittest.main()

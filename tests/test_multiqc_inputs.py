#!/usr/bin/env python3
"""
Unit tests for the MultiQC input builders in workflow/rules/common.smk
(create_multiqc_{bam_individual,reference,species_individual,species}_input).

common.smk holds plain Python only, so it is exec'd into the same shared namespace
workflow/scripts/pipeline_namespace.py builds for the expected-output tests, after the
discovery helpers it calls. A synthetic species library comes from tests/pf_test_library.py.

Run with either:
    python3 tests/test_multiqc_inputs.py
    python3 -m unittest tests.test_multiqc_inputs -v          (from the repo root)
"""
import logging
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pf_test_library as testlib  # noqa: E402
from scripts.pipeline_namespace import load_pipeline_namespace  # noqa: E402

COMMON_SMK = os.path.join(REPO_ROOT, "workflow", "rules", "common.smk")
REF_DIR = "Dmel/results/reference_module/genome/analytics/individual_level/IND001"


class MultiqcInputsTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_multiqc_")
        os.chdir(self.project_dir)
        testlib.build_species_library(self.project_dir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def load(self, pipeline=None):
        ns = load_pipeline_namespace({"species": {"Dmel": {"lineage": "drosophilidae_odb12"}}, "pipeline": pipeline or {}})
        ns["logger"] = logging.getLogger("test_multiqc_inputs")  # Snakemake provides it
        with open(COMMON_SMK) as f:
            exec(compile(f.read(), COMMON_SMK, "exec"), ns)
        return ns

    def bam(self, ns, individual, reference):
        return ns["create_multiqc_bam_individual_input"](SimpleNamespace(species="Dmel", individual=individual, reference=reference))

    def reference(self, ns, reference):
        return ns["create_multiqc_reference_input"](SimpleNamespace(species="Dmel", reference=reference))

    def species_individual(self, ns, individual):
        return ns["create_multiqc_species_individual_input"](SimpleNamespace(species="Dmel", individual=individual))

    def species(self, ns):
        return ns["create_multiqc_species_input"](SimpleNamespace(species="Dmel"))

    def test_bam_individual_default_inputs(self):
        self.assertEqual(
            self.bam(self.load(), "IND001", "genome"),
            [
                "Dmel/results/read_module/taxonomic_screening/centrifuge/IND001/IND001/IND001_top10_total_taxa.tsv",
                "Dmel/results/read_module/taxonomic_screening/ecmsd/IND001_Mito_summary_hits_combined.tsv",
                "Dmel/results/read_module/reads_merged/fastqc/IND001_merged_fastqc.zip",
                f"{REF_DIR}/preseq/IND001_genome.c_curve.txt",
                f"{REF_DIR}/multiqc_custom_content/qualimap/IND001_genome",
                f"{REF_DIR}/samtools_stats/IND001_genome_final.bam.stats",
                f"{REF_DIR}/multiqc_custom_content/IND001_genome_reads_processing_summary.tsv",
                f"{REF_DIR}/multiqc_custom_content/IND001_genome_reads_processing_summary_stacked.tsv",
                f"{REF_DIR}/multiqc_custom_content/IND001_genome_coverage_analysis.tsv",
                f"{REF_DIR}/multiqc_custom_content/IND001_genome_coverage_summary.tsv",
                f"{REF_DIR}/multiqc_custom_content/mapdamage/IND001_genome/3pGtoA_freq.txt",
                f"{REF_DIR}/multiqc_custom_content/mapdamage/IND001_genome/5pCtoT_freq.txt",
                f"{REF_DIR}/multiqc_custom_content/mapdamage/IND001_genome/lgdistribution.txt",
            ],
        )

    def test_reports_combine_the_same_per_individual_inputs(self):
        for pipeline in (
            {},
            {"read_module": {"execute": False}},
            {"reference_module": {"analysis": {"execute": False}}},
            {"reference_module": {"damage_rescaling": {"execute": False}}},
            {"read_module": {"taxonomic_screening": {"tools": {"centrifuge": {"execute": False}}}}},
        ):
            with self.subTest(pipeline=pipeline):
                ns = self.load(pipeline)
                individuals = ns["get_individuals_for_species"]("Dmel")
                references = ns["get_references_ids_for_species"]("Dmel")
                # The per-reference BAM reports each repeat the read-module files, so compare as sets.
                for individual in individuals:
                    self.assertEqual(
                        set(self.species_individual(ns, individual)),
                        {f for ref in references for f in self.bam(ns, individual, ref)},
                    )
                for ref in references:
                    self.assertEqual(self.reference(ns, ref), [f for ind in individuals for f in self.bam(ns, ind, ref)])
                self.assertEqual(self.species(ns), [f for ind in individuals for f in self.species_individual(ns, ind)])

    def test_bcftools_stats_only_in_reference_report(self):
        bcftools = f"{REF_DIR}/snp_divergence/IND001_genome.bcftools_stats.txt"
        for method, expected in (("samtools_stats", False), ("bcftools", True), ("both", True)):
            with self.subTest(method=method):
                ns = self.load({"reference_module": {"analysis": {"settings": {"snp_divergence_check": True, "snp_divergence_method": method}}}})
                self.assertEqual(bcftools in self.reference(ns, "genome"), expected)
                self.assertNotIn(bcftools, self.bam(ns, "IND001", "genome"))
                self.assertNotIn(bcftools, self.species_individual(ns, "IND001"))
                self.assertNotIn(bcftools, self.species(ns))

    def test_reference_module_off_drops_reference_inputs(self):
        ns = self.load({"reference_module": {"execute": False}})
        for files in (self.bam(ns, "IND001", "genome"), self.reference(ns, "genome"), self.species(ns)):
            self.assertTrue(files)
            self.assertFalse([f for f in files if "/reference_module/" in f])

    def test_dedup_merge_inputs_share_cluster_ranges(self):
        ns = self.load()
        folder = os.path.join(self.project_dir, "clusters")
        os.makedirs(folder)
        for name in ("cluster_1_50.bed", "cluster_51_120.bed", "other.bed"):
            open(os.path.join(folder, name), "w").close()
        checkpoint = SimpleNamespace(get=lambda **kw: SimpleNamespace(output=SimpleNamespace(cluster_folder=folder)))
        ns["checkpoints"] = SimpleNamespace(dedup_create_all_contig_clusters=checkpoint)
        wc = SimpleNamespace(species="Dmel", reference="genome", individual="IND001")
        self.assertEqual(ns["_dedup_cluster_ranges"](wc), [(1, 50), (51, 120)])
        bams = ns["dedup_merge_split_bams_input"](wc)
        jsons = ns["dedup_merge_split_jsons_input"](wc)
        self.assertEqual(len(bams), 3)  # two clusters + unmapped reads
        self.assertTrue(bams[1].endswith("dedup_51_120/IND001_genome_cluster_51_120_rmdup.bam"))
        self.assertTrue(jsons[0].endswith("dedup_1_50/IND001_genome_cluster_1_50.dedup.json"))
        self.assertEqual(len(jsons), 2)


if __name__ == "__main__":
    unittest.main()

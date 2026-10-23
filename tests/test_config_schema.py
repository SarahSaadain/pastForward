#!/usr/bin/env python3
"""
Unit tests for validate_config() in workflow/scripts/config_schema.py, which checks
config.yaml against workflow/schemas/config.schema.yaml at startup.

The sample configs must always pass, with every commented-out setting switched on too, so
the schema cannot fall behind a documented key. Skipped when jsonschema is not installed.

Run with either:
    python3 tests/test_config_schema.py
    python3 -m unittest tests.test_config_schema -v          (from the repo root)
"""
import copy
import os
import re
import sys
import unittest

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

from scripts.config_schema import validate_config  # noqa: E402
from scripts.file_manager import ConfigValidationError  # noqa: E402

try:
    import jsonschema  # noqa: F401
except ImportError:
    jsonschema = None

SAMPLE_CONFIGS = ["min_config_sample.yaml", "max_config_sample.yaml", "max_config_modern_sample.yaml"]


def _load_sample(name, uncomment=False):
    with open(os.path.join(REPO_ROOT, "config", name)) as f:
        text = f.read()
    if uncomment:
        # "#key: value" lines are optional settings; prose comments have a space after "#".
        text = re.sub(r"^(\s*)#([a-z_0-9]+:)", r"\1\2", text, flags=re.MULTILINE)
    return yaml.safe_load(text)


@unittest.skipIf(jsonschema is None, "jsonschema not installed")
class TestValidateConfig(unittest.TestCase):
    def test_sample_configs_pass(self):
        for name in SAMPLE_CONFIGS:
            for uncomment in (False, True):
                with self.subTest(name=name, uncomment=uncomment):
                    validate_config(_load_sample(name, uncomment))

    def test_empty_config_passes(self):
        # `snakemake --lint` parses the workflow without any config file.
        validate_config({})

    def test_every_problem_is_reported(self):
        config = copy.deepcopy(_load_sample("max_config_sample.yaml"))
        config["pipeline"]["read_module"]["adapter_removal"]["exectue"] = False
        config["pipeline"]["reference_module"]["mapping"]["settings"]["mapper"] = "bwa"
        config["pipeline"]["summary_module"]["execute"] = "false"
        config["species"]["demo"]["individuals"] = "IND001"
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        message = str(ctx.exception)
        self.assertIn("4 problem(s)", message)
        self.assertIn(
            "pipeline.read_module.adapter_removal: unknown key 'exectue' (did you mean 'execute'?)",
            message,
        )
        self.assertIn("pipeline.reference_module.mapping.settings.mapper: 'bwa'", message)
        self.assertIn("pipeline.summary_module.execute: 'false' is not of type 'boolean'", message)
        self.assertIn("species.demo.individuals", message)

    def test_execute_on_always_on_step_is_rejected(self):
        # mapping has no execute switch; accepting one would silently ignore `false`.
        config = {"pipeline": {"reference_module": {"mapping": {"execute": False}}}}
        with self.assertRaisesRegex(ConfigValidationError, "unknown key 'execute'"):
            validate_config(config)

    def test_fully_commented_section_gets_clear_message(self):
        config = yaml.safe_load("pipeline:\n  reference_module:\n    deduplication:\n      settings:\n        #mem_mb: 1\n")
        with self.assertRaisesRegex(
            ConfigValidationError, r"deduplication\.settings: is empty\. Remove the line"
        ):
            validate_config(config)

    def test_empty_id_list_means_all(self):
        validate_config({"species": {"demo": {"individuals": None, "references": []}}})


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/config_compat.py - the deprecated-config-key rewriting that
initialize.smk applies right after the configfile is loaded, so that renamed config keys keep
working under their old name. The end-to-end effect on requested outputs is covered in
tests/unit/test_expected_output_manager.py; these tests pin the rewriting rules themselves.

Run with either:
    python3 tests/unit/test_config_compat.py
    python3 -m unittest tests.test_config_compat -v          (from the repo root)
"""
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "workflow", "scripts"
    ),
)

from config_compat import CONFIG_KEY_ALIASES, apply_config_key_aliases  # noqa: E402


class TestApplyConfigKeyAliases(unittest.TestCase):
    def test_deprecated_key_is_moved_to_current_name(self):
        config = {"pipeline": {"read_module": {"contamination": {"execute": False}}}}
        applied = apply_config_key_aliases(config)
        read_module = config["pipeline"]["read_module"]
        self.assertEqual(read_module, {"taxonomic_screening": {"execute": False}})
        self.assertEqual(
            applied,
            [
                (
                    "pipeline.read_module.contamination",
                    "pipeline.read_module.taxonomic_screening",
                )
            ],
        )

    def test_current_name_wins_when_both_are_set(self):
        config = {
            "pipeline": {
                "read_module": {
                    "contamination": {"execute": False},
                    "taxonomic_screening": {"execute": True},
                }
            }
        }
        apply_config_key_aliases(config)
        self.assertEqual(
            config["pipeline"]["read_module"], {"taxonomic_screening": {"execute": True}}
        )

    def test_config_without_the_deprecated_key_is_untouched(self):
        config = {"pipeline": {"read_module": {"taxonomic_screening": {"execute": True}}}}
        self.assertEqual(apply_config_key_aliases(config), [])
        self.assertEqual(
            config, {"pipeline": {"read_module": {"taxonomic_screening": {"execute": True}}}}
        )

    def test_missing_or_non_dict_parents_do_not_raise(self):
        for config in ({}, {"pipeline": None}, {"pipeline": {"read_module": None}}):
            with self.subTest(config=config):
                self.assertEqual(apply_config_key_aliases(config), [])

    def test_alias_table_targets_keys_that_are_not_also_deprecated(self):
        """A new alias must not point at a name that is itself aliased away - that would
        silently drop the value on the second pass."""
        deprecated = {(path, old) for path, old, _ in CONFIG_KEY_ALIASES}
        for path, _, new in CONFIG_KEY_ALIASES:
            self.assertNotIn((path, new), deprecated)


if __name__ == "__main__":
    unittest.main(verbosity=2)

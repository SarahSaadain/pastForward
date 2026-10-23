# Checks config.yaml against workflow/schemas/config.schema.yaml: unknown keys, wrong types and
# invalid values. Runs right after config_compat.apply_config_key_aliases(), so deprecated keys
# are already renamed. Called from initialize.smk (real runs), pipeline_namespace.py (unit
# tests) and cli/discover.py (`pastForward check`/`preview`, before any symlink is made).

import difflib
import os
import sys

import yaml

from scripts.file_manager import ConfigValidationError

CONFIG_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "schemas", "config.schema.yaml"
)

_warned_no_jsonschema = False


def _format_schema_error(error):
    path = ".".join(str(p) for p in error.absolute_path) or "(top level)"
    if error.validator == "additionalProperties" and error.validator_value is False:
        known = list(error.schema.get("properties", {}))
        lines = []
        for key in sorted(set(error.instance) - set(known)):
            hint = difflib.get_close_matches(str(key), known, n=1)
            lines.append(
                f"{path}: unknown key '{key}'"
                + (f" (did you mean '{hint[0]}'?)" if hint else "")
            )
        return lines
    if error.validator == "type" and error.validator_value == "object" and error.instance is None:
        # A section whose every line is commented out loads as null, not {}.
        return [f"{path}: is empty. Remove the line, or set at least one key under it."]
    if error.validator == "type" and error.instance is None:
        return [f"{path}: has no value. Remove the line, or set a value."]
    return [f"{path}: {error.message}"]


def validate_config(config):
    """Raises ConfigValidationError listing every problem at once.

    Skipped when jsonschema is not installed: Snakemake always brings it, but
    `pastForward check`/`preview` may run under a bare Python. The notice goes straight to
    stderr, not logging, because check/preview capture the log and print only the lines they
    parse. It is printed once, since check/preview validate twice.
    """
    global _warned_no_jsonschema
    try:
        import jsonschema
    except ImportError:
        if not _warned_no_jsonschema:
            print(
                "WARNING: jsonschema is not installed, so the config was not validated. "
                "Activate the Snakemake conda env to validate it.",
                file=sys.stderr,
            )
            _warned_no_jsonschema = True
        return
    with open(CONFIG_SCHEMA_PATH) as f:
        schema = yaml.safe_load(f)
    validator = jsonschema.Draft202012Validator(schema)
    problems = []
    for error in sorted(validator.iter_errors(config), key=lambda e: list(map(str, e.absolute_path))):
        problems.extend(_format_schema_error(error))
    if problems:
        raise ConfigValidationError(
            f"Invalid config ({len(problems)} problem(s)):\n  - "
            + "\n  - ".join(problems)
            + "\nSee config/parameters.md for every valid key, and CHANGELOG.md for keys "
            "renamed in v2.0."
        )

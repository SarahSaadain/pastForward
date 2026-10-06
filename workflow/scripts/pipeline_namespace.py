#!/usr/bin/env python3
"""
Loads workflow/scripts/file_manager.py, the expected_output_manager_*.py files and
(optionally) check.py into a single shared namespace, mimicking how Snakemake's `include:`
directive runs them (see the include order in workflow/Snakefile): all in the same globals
dict, seeing a shared `config` and each other's top-level functions with no imports between
them. That shared-namespace trick is also why
expected_output_manager_summary_module_processing.py can call `logging.info(...)` without
importing `logging` itself - it relies on an earlier included file having already done so
(reproduced here by loading the files in the same order).

This lets `pastForward check`/`preview` (workflow/scripts/cli/) and
tests/test_expected_output_manager.py run the real discovery / DAG-target-computation logic
without starting Snakemake or conda.

config_compat.apply_config_key_aliases() is applied to the config first, mirroring the call
initialize.smk makes right after the configfile is loaded, so callers see the same normalised
config a real run does (and deprecated config keys stay covered by the test suite).

Not a test module itself - has no tests of its own.
"""
import os
from types import SimpleNamespace

from scripts.config_compat import apply_config_key_aliases

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Mirrors the include: order in workflow/Snakefile.
_SOURCE_FILES = [
    "file_manager.py",
    os.path.join("expected_output", "expected_output_manager_reveal_module_processing.py"),
    os.path.join("expected_output", "expected_output_manager_read_module_processing.py"),
    os.path.join("expected_output", "expected_output_manager_reference_module_processing.py"),
    os.path.join("expected_output", "expected_output_manager_summary_module_processing.py"),
    "expected_output_manager.py",
]


def load_pipeline_namespace(config, include_check=False):
    """Returns a namespace dict with `config` bound and every manager function loaded,
    exactly as they'd see each other and `config` when run for real under Snakemake.

    include_check also loads check.py, which - unlike the other files - does its work at
    include time: it logs the per-species discovery summary as a side effect of being
    loaded. Its `snakemake_interface_executor_plugins` import is optional (see the try/except
    there), so this stays importable with nothing but the standard library plus PyYAML.
    """
    apply_config_key_aliases(config)
    namespace = {"config": config}
    sources = list(_SOURCE_FILES)
    if include_check:
        # check.py skips its scan when Snakemake runs it in a spawned subprocess. Outside
        # Snakemake there is no parent process to have already printed it, so a stub whose
        # exec_mode is never ExecMode.SUBPROCESS makes it always run.
        namespace["workflow"] = SimpleNamespace(exec_mode=None)
        sources.insert(1, "check.py")  # right after file_manager.py, as in the Snakefile
    for relpath in sources:
        path = os.path.join(_SCRIPTS_DIR, relpath)
        with open(path) as f:
            source = f.read()
        exec(compile(source, path, "exec"), namespace)
    return namespace

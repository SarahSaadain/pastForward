#!/usr/bin/env python3
"""
Materializes a small, ready-to-inspect synthetic pastForward project under
tests/fixtures/pf_test_library/ (gitignored) - a reference genome, a feature library, and
three individuals' worth of raw reads for one species ("Dmel" by default), wired up with a
config.yaml and a workflow/ symlink so it can be pointed at directly:

    python3 tests/build_test_library.py
    cd tests/fixtures/pf_test_library && snakemake --cores 2 --software-deployment-method conda --dryrun

Complements the hermetic tempdir-based fixtures used by test_file_manager.py and
test_expected_output_manager.py (which build/discard their own copies per test) - this one
is for manual poking, and is regenerated from scratch every time it's built, including once
per test suite run (see test_expected_output_manager.py's setUpModule).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pf_test_library import materialize_reference_library  # noqa: E402

DEFAULT_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pf_test_library")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    lib = materialize_reference_library(target)
    print(f"Built test library at {target}")
    print(f"  species: {lib.species}")
    print(f"  individuals: {lib.individuals}")
    print(f"  references: {lib.reference_ids}")
    print(f"  feature libraries: {lib.feature_library_ids}")

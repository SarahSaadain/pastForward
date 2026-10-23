#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/species_paths.py — the symlink + cross-project lock logic
behind the per-species data-location config overrides (species_dir, reads_dir, ...).

Pure Python, no Snakemake/conda required. Run with either:
    python3 tests/test_species_paths.py
    python3 -m unittest tests.test_species_paths -v          (from the repo root)

For an end-to-end check that the symlinks actually resolve correctly through a real
Snakemake DAG (dry runs), see tests/dryrun_scenarios.sh instead — that one does need the
`snakemake` conda environment.
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

import scripts.species_paths as sp  # noqa: E402


class SpeciesPathsTestCase(unittest.TestCase):
    """Base class: runs each test inside its own throwaway project directory."""

    def setUp(self):
        self._orig_cwd = os.getcwd()
        # realpath: os.getcwd() (used by species_paths.py for lock metadata) resolves
        # symlinks, and on macOS tempfile.mkdtemp()'s /var/folders/... is itself a symlink
        # into /private/var/folders/... — without this, comparisons against a raw mkdtemp()
        # path fail on macOS while passing on Linux.
        self.project_dir = os.path.realpath(tempfile.mkdtemp(prefix="pf_test_project_"))
        os.chdir(self.project_dir)
        sp._ACQUIRED_LOCKS.clear()
        self._extra_dirs = []

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)
        for d in self._extra_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def make_external_dir(self, prefix="pf_test_external_"):
        d = tempfile.mkdtemp(prefix=prefix)
        self._extra_dirs.append(d)
        return d

    def make_species_root(self, root):
        """Create the full conventional subfolder layout under `root`."""
        for sub in [
            "input/read_module", "input/reference_module", "input/reveal_module/scg",
            "input/reveal_module/feature_library", "input/reveal_module/competition",
            "processed", "results",
        ]:
            os.makedirs(os.path.join(root, sub), exist_ok=True)


class TestFallback(SpeciesPathsTestCase):
    def test_no_config_touches_nothing(self):
        config = {"species": {"Dmel": {"name": "Drosophila melanogaster"}}}
        sp.setup_species_data_locations(config)
        self.assertFalse(os.path.exists("Dmel"), "no override configured -> Dmel/ must not be created")
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 0)


class TestFreshSpeciesDir(SpeciesPathsTestCase):
    def setUp(self):
        super().setUp()
        self.species_root = self.make_external_dir("pf_test_species_root_")
        self.make_species_root(self.species_root)
        with open(os.path.join(self.species_root, "input/read_module", "IND001_R1.fastq.gz"), "w") as f:
            f.write("fake")
        self.config = {"species": {"Dmel": {"name": "Drosophila melanogaster", "species_dir": self.species_root}}}

    def expected_links(self):
        return {
            "Dmel/input/read_module": os.path.realpath(os.path.join(self.species_root, "input/read_module")),
            "Dmel/input/reference_module": os.path.realpath(os.path.join(self.species_root, "input/reference_module")),
            "Dmel/input/reveal_module/scg": os.path.realpath(os.path.join(self.species_root, "input/reveal_module/scg")),
            "Dmel/input/reveal_module/feature_library": os.path.realpath(os.path.join(self.species_root, "input/reveal_module/feature_library")),
            "Dmel/input/reveal_module/competition": os.path.realpath(os.path.join(self.species_root, "input/reveal_module/competition")),
            "Dmel/processed": os.path.realpath(os.path.join(self.species_root, "processed")),
            "Dmel/results": os.path.realpath(os.path.join(self.species_root, "results")),
        }

    def test_symlinks_created_with_correct_targets(self):
        sp.setup_species_data_locations(self.config)
        for link, target in self.expected_links().items():
            self.assertTrue(os.path.islink(link), f"missing symlink at {link}")
            self.assertEqual(os.readlink(link), target)

    def test_glob_discovery_follows_symlink(self):
        # Mirrors how file_manager.py's get_files_in_folder_matching_pattern works.
        import glob
        sp.setup_species_data_locations(self.config)
        files = glob.glob(os.path.join("Dmel/input/read_module", "*.fastq.gz"))
        self.assertEqual(len(files), 1)

    def test_locks_acquired_only_for_processed_and_results(self):
        sp.setup_species_data_locations(self.config)
        sp.acquire_pastforward_locks(self.config)
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 2)
        links = self.expected_links()
        processed_lock = os.path.join(links["Dmel/processed"], ".pastforward.lock")
        results_lock = os.path.join(links["Dmel/results"], ".pastforward.lock")
        self.assertTrue(os.path.exists(processed_lock))
        self.assertTrue(os.path.exists(results_lock))
        with open(processed_lock) as f:
            content = json.load(f)
        self.assertEqual(content["pid"], os.getpid())
        self.assertEqual(content["hostname"], socket.gethostname())
        self.assertEqual(content["working_directory"], self.project_dir)

    def test_setup_creates_symlinks_but_takes_no_lock(self):
        # setup runs at workflow load, also for --dryrun/--lint/--unlock, which never fire the
        # onsuccess:/onerror: hooks that release a lock. Locks are taken only in onstart:.
        sp.setup_species_data_locations(self.config)
        for link in self.expected_links():
            self.assertTrue(os.path.islink(link), f"missing symlink at {link}")
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 0)
        links = self.expected_links()
        self.assertFalse(os.path.exists(os.path.join(links["Dmel/processed"], ".pastforward.lock")))
        self.assertFalse(os.path.exists(os.path.join(links["Dmel/results"], ".pastforward.lock")))

    def test_idempotent_rerun(self):
        sp.setup_species_data_locations(self.config)
        sp.acquire_pastforward_locks(self.config)
        mtime_before = os.lstat("Dmel/input/read_module").st_mtime_ns
        sp.setup_species_data_locations(self.config)  # must not raise
        sp.acquire_pastforward_locks(self.config)
        mtime_after = os.lstat("Dmel/input/read_module").st_mtime_ns
        self.assertEqual(mtime_before, mtime_after, "symlink was recreated instead of left alone")
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 2, "second run must not double-acquire locks")


class TestConflictDetection(SpeciesPathsTestCase):
    def test_real_directory_preexisting_is_untouched(self):
        os.makedirs("Dmel/input/read_module")
        with open("Dmel/input/read_module/preexisting.txt", "w") as f:
            f.write("do not touch me")
        reads_target = self.make_external_dir("pf_test_reads_")
        config = {"species": {"Dmel": {"reads_dir": reads_target}}}

        with self.assertRaises(sp.SpeciesDataLocationError):
            sp.setup_species_data_locations(config)

        self.assertTrue(os.path.exists("Dmel/input/read_module/preexisting.txt"))
        self.assertFalse(os.path.islink("Dmel/input/read_module"))

    def test_symlink_to_different_target_is_untouched(self):
        os.makedirs("Dmel/input", exist_ok=True)
        somewhere_else = self.make_external_dir("pf_test_somewhere_else_")
        os.symlink(somewhere_else, "Dmel/input/read_module")
        reads_target = self.make_external_dir("pf_test_reads_")
        config = {"species": {"Dmel": {"reads_dir": reads_target}}}

        with self.assertRaises(sp.SpeciesDataLocationError):
            sp.setup_species_data_locations(config)

        self.assertEqual(os.readlink("Dmel/input/read_module"), somewhere_else)

    def test_missing_target_directory_raises_and_leaves_nothing(self):
        config = {"species": {"Dmel": {"reads_dir": "/does/not/exist/pf_test"}}}
        with self.assertRaises(sp.SpeciesDataLocationError):
            sp.setup_species_data_locations(config)
        self.assertFalse(os.path.exists("Dmel/input/read_module"))


class TestExecuteFalseSkipsSpecies(SpeciesPathsTestCase):
    def test_skipped_species_untouched(self):
        processed_target = self.make_external_dir("pf_test_processed_")
        config = {"species": {"Dmel": {"execute": False, "processed_dir": processed_target}}}
        sp.setup_species_data_locations(config)
        sp.acquire_pastforward_locks(config)
        self.assertFalse(os.path.exists("Dmel"))
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 0)


class TestCrossProjectLock(SpeciesPathsTestCase):
    def test_live_foreign_pid_same_host_raises(self):
        target = self.make_external_dir("pf_test_shared_target_")
        forged = {
            "working_directory": "/some/other/project",
            "pid": 1,  # pid 1 (init/systemd) is always alive and is never our own pid
            "hostname": socket.gethostname(),
            "start_timestamp": "2026-01-01T00:00:00",
        }
        with open(os.path.join(target, ".pastforward.lock"), "w") as f:
            json.dump(forged, f)

        with self.assertRaises(sp.CrossProjectLockError):
            sp._acquire_project_lock(target, "Dmel", "processed")

    def test_pid_alive_edge_cases(self):
        self.assertTrue(sp._pid_alive(os.getpid()))
        for bad in (0, -1, None):
            self.assertFalse(sp._pid_alive(bad))

    def test_dead_pid_same_host_is_taken_over(self):
        target = self.make_external_dir("pf_test_stale_target_")
        dead_pid = 999999
        while sp._pid_alive(dead_pid) and dead_pid > 2:
            dead_pid -= 1
        stale = {
            "working_directory": "/some/old/project",
            "pid": dead_pid,
            "hostname": socket.gethostname(),
            "start_timestamp": "2020-01-01T00:00:00",
        }
        lock_path = os.path.join(target, ".pastforward.lock")
        with open(lock_path, "w") as f:
            json.dump(stale, f)

        sp._acquire_project_lock(target, "Dmel", "processed")  # must not raise

        with open(lock_path) as f:
            content = json.load(f)
        self.assertEqual(content["pid"], os.getpid())

    def test_foreign_host_raises_and_leaves_file_untouched(self):
        target = self.make_external_dir("pf_test_foreign_host_target_")
        foreign = {
            "working_directory": "/remote/project",
            "pid": 12345,
            "hostname": "some-other-machine-" + socket.gethostname(),
            "start_timestamp": "2026-01-01T00:00:00",
        }
        lock_path = os.path.join(target, ".pastforward.lock")
        with open(lock_path, "w") as f:
            json.dump(foreign, f)

        with self.assertRaises(sp.CrossProjectLockError):
            sp._acquire_project_lock(target, "Dmel", "processed")

        with open(lock_path) as f:
            unchanged = json.load(f)
        self.assertEqual(unchanged, foreign)

    def test_release_only_removes_locks_this_run_acquired(self):
        t1 = self.make_external_dir("pf_test_rel1_")
        t2 = self.make_external_dir("pf_test_rel2_")
        config = {"species": {"Dmel": {"processed_dir": t1, "results_dir": t2}}}
        sp.acquire_pastforward_locks(config)
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 2)

        sp.release_pastforward_locks()

        self.assertFalse(os.path.exists(os.path.join(t1, ".pastforward.lock")))
        self.assertFalse(os.path.exists(os.path.join(t2, ".pastforward.lock")))
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 0)
        sp.release_pastforward_locks()  # must be safe to call again / when empty

    def test_failed_acquire_releases_locks_already_taken(self):
        # onerror: does not fire for an exception in onstart:, so a conflict on the second
        # target must release the first lock itself.
        t1 = self.make_external_dir("pf_test_rel1_")
        t2 = self.make_external_dir("pf_test_rel2_")
        foreign = {"working_directory": "/elsewhere", "pid": 1, "hostname": "other-host",
                   "start_timestamp": "2026-01-01T00:00:00"}
        with open(os.path.join(t2, ".pastforward.lock"), "w") as f:
            json.dump(foreign, f)
        config = {"species": {"Dmel": {"processed_dir": t1, "results_dir": t2}}}

        with self.assertRaises(sp.CrossProjectLockError):
            sp.acquire_pastforward_locks(config)

        self.assertFalse(os.path.exists(os.path.join(t1, ".pastforward.lock")))
        self.assertEqual(len(sp._ACQUIRED_LOCKS), 0)
        with open(os.path.join(t2, ".pastforward.lock")) as f:
            self.assertEqual(json.load(f), foreign)


if __name__ == "__main__":
    unittest.main(verbosity=2)

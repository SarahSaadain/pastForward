#!/usr/bin/env python3
"""
CLI tests that need the Snakemake environment. `run`, `resume`, `unlock` and
`doctor --rebuild-envs` refuse to start when no `snakemake` executable is on PATH, so these
tests skip themselves without it. Run them with the env on PATH:
    PATH=<snakemake-env>/bin:$PATH python3 -m unittest tests/test_cli_snakemake.py -v
"""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module, not the class: a TestCase name in this namespace would run its tests twice.
import test_cli  # noqa: E402
from test_cli import cli  # noqa: E402


@unittest.skipUnless(shutil.which("snakemake"), "needs the snakemake env on PATH")
class SnakemakeArgvTestCase(unittest.TestCase):
    """The ArgvValidationTestCase checks that get past the `snakemake` on PATH check."""

    setUp = test_cli.ArgvValidationTestCase.setUp
    tearDown = test_cli.ArgvValidationTestCase.tearDown

    def test_run_accepts_cores_with_equals(self):
        captured = {}
        orig = cli.run._run_background
        cli.run._run_background = lambda cmd, log_path: captured.setdefault("cmd", cmd)
        try:
            cli.run.cmd_run(["--cores=8"])
        finally:
            cli.run._run_background = orig
        self.assertIn("--cores=8", captured["cmd"])

    def test_resume_adds_rerun_incomplete(self):
        # cmd_resume only differs from cmd_run by this flag - confirm it lands in the built
        # command rather than actually spawning snakemake.
        captured = {}
        orig = cli.run._run_background
        cli.run._run_background = lambda cmd, log_path: captured.setdefault("cmd", cmd)
        try:
            cli.run.cmd_resume(["--cores", "4"])
        finally:
            cli.run._run_background = orig
        self.assertIn("--rerun-incomplete", captured["cmd"])

    def test_doctor_rebuild_refuses_while_a_tracked_run_is_alive(self):
        env_dir = Path(self.project_dir) / "env_in_use"
        env_dir.mkdir()
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.common.STATE_FILE.write_text(json.dumps({"pid": os.getpid()}))
        orig = cli.doctor._list_conda_envs
        cli.doctor._list_conda_envs = lambda: [{"env_file": "workflow/envs/x.yaml", "location": str(env_dir)}]
        try:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
                cli.doctor.cmd_doctor(["--rebuild-envs"])
        finally:
            cli.doctor._list_conda_envs = orig
        self.assertIn("a run is active", str(cm.exception))
        self.assertTrue(env_dir.is_dir())

    def test_unlock_passes_cores_one(self):
        # snakemake >= 9.9 requires --cores even for --unlock.
        captured = {}
        orig = cli.run.subprocess.call
        cli.run.subprocess.call = lambda cmd: captured.setdefault("cmd", cmd) or 0
        try:
            with self.assertRaises(SystemExit):
                cli.run.cmd_unlock([])
        finally:
            cli.run.subprocess.call = orig
        self.assertEqual(captured["cmd"], ["snakemake", "--unlock", "--cores", "1"])

    def test_run_accepts_configfile_without_default_config(self):
        # initialize.smk only loads config/config.yaml when it exists, so a run driven
        # entirely by --configfile is valid.
        os.remove(self.configfile)
        Path("other.yaml").write_text("project_name: other\n")
        captured = {}
        orig = cli.run._run_background
        cli.run._run_background = lambda cmd, log_path: captured.setdefault("cmd", cmd)
        try:
            cli.run.cmd_run(["--cores", "4", "--configfile", "other.yaml"])
        finally:
            cli.run._run_background = orig
        self.assertIn("other.yaml", captured["cmd"])

    def _stub_snakemake_unlock(self):
        orig = cli.run.subprocess.call
        cli.run.subprocess.call = lambda cmd: 0
        self.addCleanup(setattr, cli.run.subprocess, "call", orig)

    def _write_cross_project_lock(self, owner):
        target = os.path.join(self.project_dir, "elsewhere", "processed")
        os.makedirs(target)
        with open(self.configfile, "w") as f:
            f.write(f"project_name: test\nspecies:\n  Dmel:\n    processed_dir: {target}\n")
        lock = Path(target, ".pastforward.lock")
        lock.write_text(json.dumps(owner))
        return lock

    def test_unlock_lists_cross_project_locks_but_keeps_them(self):
        self._stub_snakemake_unlock()
        lock = self._write_cross_project_lock({"hostname": "other-host", "pid": 1})
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            cli.run.cmd_unlock([])
        self.assertIn(str(lock), out.getvalue())
        self.assertIn("--cross-project", out.getvalue())
        self.assertTrue(lock.exists())

    def test_unlock_cross_project_removes_dead_locks(self):
        self._stub_snakemake_unlock()
        lock = self._write_cross_project_lock({"hostname": "other-host", "pid": 1})
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            cli.run.cmd_unlock(["--cross-project"])
        self.assertFalse(lock.exists())

    def test_unlock_cross_project_never_removes_a_live_local_lock(self):
        self._stub_snakemake_unlock()
        lock = self._write_cross_project_lock({"hostname": cli.run.socket.gethostname(), "pid": os.getpid()})
        with contextlib.redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            cli.run.cmd_unlock(["--cross-project"])
        self.assertTrue(lock.exists())
        self.assertIn("owner still running", out.getvalue())


if __name__ == "__main__":
    unittest.main()

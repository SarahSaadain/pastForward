#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/cli/ (the `pastForward` CLI's command building and log
parsing). Pure Python, no Snakemake/conda required. Run with either:
    python3 tests/unit/test_cli.py
    python3 -m unittest tests.test_cli -v          (from the repo root)

Regex fixtures below mirror the real formats confirmed against snakemake 9.25.1's
snakemake/logging.py (_format_job_info, format_job_finished) and
snakemake/scheduling/job_scheduler.py ("Finished jobid: ..."), plus a real --dryrun run of
this repo's own initialize.smk/check.py/expected_output_manager.py.
"""

import contextlib
import io
import json
import os
import shutil
import signal
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

import scripts.cli as cli  # noqa: E402


class BuildCmdTestCase(unittest.TestCase):
    def test_run_cmd_adds_defaults(self):
        cmd = cli.run._build_run_cmd(["--cores", "8"])
        self.assertEqual(
            cmd,
            [
                "snakemake",
                "--software-deployment-method",
                "conda",
                "--keep-going",
                "--rerun-trigger",
                "mtime",
                "--cores",
                "8",
            ],
        )

    def test_run_cmd_does_not_duplicate_user_supplied_flags(self):
        cmd = cli.run._build_run_cmd(
            [
                "--software-deployment-method",
                "conda",
                "--cores",
                "4",
                "--forceall",
                "count_reads_raw",
            ]
        )
        self.assertEqual(cmd.count("--software-deployment-method"), 1)
        self.assertEqual(cmd.count("--cores"), 1)
        self.assertIn("--forceall", cmd)
        self.assertIn("count_reads_raw", cmd)

    def test_run_cmd_yields_to_any_spelling_of_the_deployment_flag(self):
        # Snakemake keeps only the LAST --software-deployment-method it sees, so appending our
        # own next to a user's would silently drop theirs. Every alias, plus the deprecated
        # --use-conda, has to count as an override.
        for user_flag in (
            "--sdm",
            "--deployment",
            "--deployment-method",
            "--software-deployment-method",
        ):
            with self.subTest(user_flag=user_flag):
                cmd = cli.run._build_run_cmd([user_flag, "apptainer", "--cores", "4"])
                self.assertNotIn(
                    "--software-deployment-method", cmd[: cmd.index(user_flag)]
                )
                self.assertNotIn("conda", cmd)
        cmd = cli.run._build_run_cmd(["--use-conda", "--cores", "4"])
        self.assertNotIn("--software-deployment-method", cmd)
        self.assertEqual(cmd.count("--use-conda"), 1)

    def test_dryrun_cmd_defaults_cores(self):
        cmd = cli.run._build_dryrun_cmd([])
        self.assertEqual(
            cmd,
            [
                "snakemake",
                "--software-deployment-method",
                "conda",
                "--keep-going",
                "--rerun-trigger",
                "mtime",
                "--cores",
                "1",
                "--dryrun",
            ],
        )

    def test_dryrun_cmd_respects_user_cores(self):
        cmd = cli.run._build_dryrun_cmd(["-j", "8"])
        self.assertEqual(
            cmd,
            [
                "snakemake",
                "--software-deployment-method",
                "conda",
                "--keep-going",
                "--rerun-trigger",
                "mtime",
                "-j",
                "8",
                "--dryrun",
            ],
        )

    def test_dryrun_cmd_respects_user_cores_with_equals(self):
        cmd = cli.run._build_dryrun_cmd(["--cores=8"])
        self.assertIn("--cores=8", cmd)
        self.assertNotIn("1", cmd)

    def test_dryrun_cmd_uses_same_rerun_trigger_as_run(self):
        # A dry run must predict what `run` does. Without --rerun-trigger mtime, Snakemake
        # falls back to its full default trigger set and reports reruns (e.g. "Code has
        # changed since last execution") that the real run would never perform.
        dryrun = cli.run._build_dryrun_cmd(["--cores", "8"])
        run = cli.run._build_run_cmd(["--cores", "8"])
        self.assertEqual([a for a in dryrun if a != "--dryrun"], run)

    def test_dryrun_cmd_does_not_duplicate_user_supplied_flags(self):
        cmd = cli.run._build_dryrun_cmd(["--rerun-trigger", "code", "--cores", "4"])
        self.assertEqual(cmd.count("--rerun-trigger"), 1)
        self.assertNotIn("mtime", cmd)

    def test_touch_cmd_defaults_cores_and_skips_conda(self):
        # Conda deployment would make Snakemake build every rule's environment before touching
        # anything, which a touch has no use for.
        cmd = cli.run._build_touch_cmd([])
        self.assertEqual(
            cmd, ["snakemake", "--rerun-trigger", "mtime", "--cores", "1", "--touch"]
        )

    def test_touch_cmd_passes_user_flags_through(self):
        cmd = cli.run._build_touch_cmd(
            ["--cores", "4", "--forcerun", "count_reads_raw"]
        )
        self.assertEqual(
            cmd,
            [
                "snakemake",
                "--rerun-trigger",
                "mtime",
                "--cores",
                "4",
                "--forcerun",
                "count_reads_raw",
                "--touch",
            ],
        )


class StatusHelpersTestCase(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(cli.common._format_duration(5), "5s")
        self.assertEqual(cli.common._format_duration(65), "1m 5s")
        self.assertEqual(cli.common._format_duration(3661), "1h 1m 1s")
        self.assertEqual(cli.common._format_duration(90000), "1d 1h 0m 0s")

    def test_elapsed_seconds(self):
        # str(timedelta) as Snakemake >= 9.26 logs it, with and without a day part.
        self.assertEqual(
            cli.monitor._elapsed_seconds("Elapsed time: 2:03:04.5\n"), 7384.5
        )
        self.assertEqual(
            cli.monitor._elapsed_seconds(
                "[x] [INFO] Elapsed time: 1 day, 0:00:01\nElapsed time: 2 days, 1:00:00.25"
            ),
            2 * 86400 + 3600.25,
        )
        self.assertIsNone(cli.monitor._elapsed_seconds("Finished jobid: 1 (Rule: all)"))
        self.assertIsNone(cli.monitor._elapsed_seconds(None))

    def test_conda_env_line(self):
        line = cli.monitor._conda_env_line
        a = "Creating conda environment my envs/a.yaml...\n"
        a_done = "Environment for /p q/my envs/a.yaml created (location: .snakemake/conda/1)\n"
        b = "Creating conda environment workflow/envs/b.yaml...\n"
        self.assertIsNone(line(True, "Finished jobid: 1 (Rule: all)"))
        self.assertIn("installing workflow/envs/b.yaml", line(True, a + a_done + b))
        self.assertIn("(1 done)", line(True, a + a_done + b))
        self.assertIn("1 installed", line(False, a + a_done))
        self.assertIn("workflow/envs/b.yaml not finished", line(False, a + a_done + b))

    def test__cores_from_args_forms(self):
        find = cli.common._cores_from_args
        self.assertEqual(find(["-c", "8"]), "8")
        self.assertEqual(find(["-c8"]), "8")
        self.assertEqual(find(["-j8"]), "8")
        self.assertEqual(find(["-jall"]), "all")
        self.assertEqual(find(["--jobs=4"]), "4")
        self.assertEqual(
            find(["--cores"]), ""
        )  # bare trailing flag still counts as present
        self.assertIsNone(find(["--cores-something", "8"]))
        self.assertIsNone(find(["-cfoo", "--configfile", "c.yaml"]))
        self.assertIsNone(find(["--c8"]))

    def test_dryrun_cmd_respects_attached_short_cores(self):
        cmd = cli.run._build_dryrun_cmd(["-c8"])
        self.assertNotIn("--cores", cmd)
        self.assertIn("-c8", cmd)

    def test_cores_from_cmd(self):
        self.assertEqual(
            cli.common._cores_from_args(
                [
                    "snakemake",
                    "--software-deployment-method",
                    "conda",
                    "--cores",
                    "8",
                    "--forceall",
                ]
            ),
            "8",
        )
        self.assertEqual(cli.common._cores_from_args(["snakemake", "-j", "all"]), "all")
        self.assertIsNone(cli.common._cores_from_args(["snakemake"]))
        self.assertEqual(cli.common._cores_from_args(["snakemake", "--cores=8"]), "8")

    def test_configfiles_from_cmd(self):
        self.assertEqual(
            cli.monitor._configfiles_from_cmd(
                ["snakemake", "--configfile", "other.yaml"]
            ),
            ["other.yaml"],
        )
        self.assertEqual(
            cli.monitor._configfiles_from_cmd(["snakemake", "--cores", "4"]),
            [cli.common.DEFAULT_CONFIGFILE],
        )

    def test_configfiles_from_args_follows_snakemake_parsing(self):
        parse = cli.common._configfiles_from_args
        # Several files per flag, up to the next flag.
        self.assertEqual(
            parse(["--configfile", "a.yaml", "b.yaml", "--cores", "4"]),
            ["a.yaml", "b.yaml"],
        )
        # The --flag=value form takes exactly one file, so a later word is a target.
        self.assertEqual(parse(["--configfiles=a.yaml", "target"]), ["a.yaml"])
        # Repeating the flag replaces, it does not add up (argparse keeps the last occurrence).
        self.assertEqual(
            parse(["--configfile", "a.yaml", "--configfile", "b.yaml"]), ["b.yaml"]
        )
        self.assertEqual(parse(["--cores", "4"]), [])

    def test_strip_configfile_args_keeps_everything_else(self):
        strip = cli.common._strip_configfile_args
        self.assertEqual(
            strip(["--configfile", "a.yaml", "b.yaml", "--foo", "x"]), ["--foo", "x"]
        )
        self.assertEqual(strip(["--configfile=a.yaml", "target"]), ["target"])
        self.assertEqual(strip([]), [])

    def test_load_config_merges_like_snakemake(self):
        with tempfile.TemporaryDirectory() as d:
            orig = os.getcwd()
            os.chdir(d)
            try:
                os.makedirs("config")
                Path(cli.common.DEFAULT_CONFIGFILE).write_text(
                    "project_name: base\nspecies:\n  Dmel:\n    name: fly\n    lineage: x\n"
                )
                Path("other.yaml").write_text("species:\n  Dmel:\n    lineage: y\n")
                config = cli.common._load_config(["other.yaml"])
            finally:
                os.chdir(orig)
        self.assertEqual(
            config,
            {
                "project_name": "base",
                "species": {"Dmel": {"name": "fly", "lineage": "y"}},
            },
        )

    def test_user_settings_corrupt_file_is_not_overwritten(self):
        us = cli.user_settings
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "cli.json"
            f.write_text('{"auto_activate": false,')  # a half-edited file
            with (
                unittest.mock.patch.object(us, "SETTINGS_FILE", f),
                contextlib.redirect_stderr(io.StringIO()) as err,
            ):
                us.update(snakemake_env="/envs/a")
            self.assertEqual(f.read_text(), '{"auto_activate": false,')
            self.assertIn("not a valid JSON object", err.getvalue())

    def test_user_settings_remember_env_and_auto_activate(self):
        us = cli.user_settings
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.object(us, "SETTINGS_FILE", Path(d) / "cli.json"):
                self.assertEqual(us.read(), {})
                self.assertTrue(us.auto_activate_enabled())
                us.update(snakemake_env="/envs/a")
                us.update(auto_activate=False)
                self.assertEqual(
                    us.read(), {"snakemake_env": "/envs/a", "auto_activate": False}
                )
                self.assertFalse(us.auto_activate_enabled())

    def test_read_project_name(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.yaml")
            with open(cfg, "w") as f:
                f.write('project_name: "Demo Project"\n')
            self.assertEqual(cli.monitor._read_project_name(cfg), "Demo Project")
            self.assertIsNone(
                cli.monitor._read_project_name(os.path.join(d, "missing.yaml"))
            )

    def test_run_state_covers_every_outcome(self):
        done = cli.monitor.PROGRESS_RE.search("177 of 177 steps (100%) done")
        partial = cli.monitor.PROGRESS_RE.search("31 of 210 steps (15%) done")
        aborting = "Will exit after finishing currently running jobs (scheduler)."
        cases = [
            # (alive, dryrun, log text, progress match) -> expected state key
            ((True, False, "", None), "running"),
            ((True, False, aborting, partial), "aborting"),
            ((True, False, None, None), "running"),  # log file not created yet
            ((False, False, None, None), "unknown"),
            ((False, True, "This was a dry-run (flag -n).", None), "dryrun_done"),
            ((False, False, "", done), "completed"),
            (
                (
                    False,
                    False,
                    "Nothing to be done (all requested files are present and up to date).",
                    None,
                ),
                "completed",
            ),
            (
                (
                    False,
                    False,
                    "At least one job did not complete successfully.",
                    partial,
                ),
                "failed",
            ),
            ((False, False, "[ERROR] LockException:", None), "locked"),
            # An abort leaves failed jobs behind too, but "you stopped it" is the better answer.
            (
                (
                    False,
                    False,
                    aborting + "\nAt least one job did not complete successfully.",
                    partial,
                ),
                "aborted",
            ),
            ((False, False, "", partial), "interrupted"),
        ]
        for args, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(cli.monitor._run_state(*args), expected)
                self.assertIn(expected, cli.monitor.STATE_DISPLAY)

    def test_progress_bar(self):
        full_char, empty_char = ("█", "░") if cli.monitor.UNICODE_OK else ("#", "-")
        bar = cli.monitor._progress_bar(50.0, width=10)
        self.assertIn("50.0%", bar)
        self.assertIn(full_char * 5, bar)
        self.assertIn(empty_char * 5, bar)
        full = cli.monitor._progress_bar(100.0, width=10)
        self.assertIn("100.0%", full)
        self.assertNotIn(empty_char, full)

    def test_job_log_paths_extracts_single_and_multiple(self):
        block = (
            "Error in rule fastqc:\n"
            "    jobid: 3\n"
            "    log: logs/fastqc/sample.log (check log file(s) for error message)\n"
        )
        self.assertEqual(cli.monitor._job_log_paths(block), ["logs/fastqc/sample.log"])

        multi_block = "Error in rule merge:\n    log: a.log, b.log (check log file(s) for error message)\n"
        self.assertEqual(cli.monitor._job_log_paths(multi_block), ["a.log", "b.log"])

        no_log_block = "Error in rule foo:\n    jobid: 1\n"
        self.assertEqual(cli.monitor._job_log_paths(no_log_block), [])

    def test_job_log_paths_handles_details_wording(self):
        # Newer Snakemake versions say "for error details" instead of "for error message" -
        # the suffix must still be stripped rather than captured as part of the path.
        block = (
            "Error in rule normalize_visualization_of_individual:\n"
            "    jobid: 52\n"
            "    log: demo/results/Dmel1959_coverage.normalized.log (check log file(s) for error details)\n"
        )
        self.assertEqual(
            cli.monitor._job_log_paths(block),
            ["demo/results/Dmel1959_coverage.normalized.log"],
        )


class ArgvValidationTestCase(unittest.TestCase):
    """Argument checks that must fail fast, before any subprocess is spawned: `run` (unlike
    `dryrun`) never guesses a thread count, and `check`/`preview` take no arguments at all
    (they run in-process and never invoke snakemake) - see README's "Using the pastForward
    CLI" section."""

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_cli_project_")
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        # The commands that build a DAG refuse to start without one (_ensure_project_root).
        self.configfile = os.path.join(self.project_dir, cli.common.DEFAULT_CONFIGFILE)
        with open(self.configfile, "w") as f:
            f.write("project_name: test\n")
        os.chdir(self.project_dir)
        # Tests below stand in for a live run with this test process's own PID, so make it
        # look like snakemake to the PID-reuse check.
        self._orig_command_line = cli.common._command_line
        cli.common._command_line = lambda pid: "python /env/bin/snakemake --cores 4"

    def tearDown(self):
        cli.common._command_line = self._orig_command_line
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_run_without_cores_exits_before_spawning_anything(self):
        with self.assertRaises(SystemExit):
            cli.run.cmd_run(["--forceall"])
        self.assertFalse(cli.common.STATE_FILE.exists())

    def test_resume_without_cores_exits_before_spawning_anything(self):
        with self.assertRaises(SystemExit):
            cli.run.cmd_resume(["--forceall"])
        self.assertFalse(cli.common.STATE_FILE.exists())

    def test_run_without_a_configfile_exits_before_spawning_anything(self):
        # config/config.yaml is the user's own file and not part of the repository, so a fresh
        # checkout has none - say so here rather than let snakemake fail while building the DAG.
        os.remove(self.configfile)
        with self.assertRaises(SystemExit) as cm:
            cli.run.cmd_run(["--cores", "4"])
        self.assertIn(cli.common.DEFAULT_CONFIGFILE, str(cm.exception))
        self.assertFalse(cli.common.STATE_FILE.exists())

    def test_run_refuses_when_a_tracked_run_is_still_alive(self):
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.common.STATE_FILE.write_text(json.dumps({"pid": os.getpid()}))
        with self.assertRaises(SystemExit):
            cli.run.cmd_run(["--cores", "4"])

    def test_unlock_rejects_arguments(self):
        with self.assertRaises(SystemExit):
            cli.run.cmd_unlock(["--foo"])

    def test_check_rejects_arguments(self):
        # check/preview run in-process - there is no Snakemake invocation left to forward
        # flags to, so only --configfile is accepted.
        with self.assertRaises(SystemExit) as cm:
            cli.discover.cmd_check(["--configfile", "other.yaml", "--forceall"])
        self.assertIn("--forceall", str(cm.exception))

    def test_check_dies_on_a_missing_configfile(self):
        with self.assertRaises(SystemExit) as cm:
            cli.discover.cmd_check(["--configfile", "missing.yaml"])
        self.assertIn("missing.yaml", str(cm.exception))

    def test_run_dies_on_a_missing_configfile(self):
        with self.assertRaises(SystemExit) as cm:
            cli.run.cmd_run(["--cores", "4", "--configfile", "missing.yaml"])
        self.assertIn("missing.yaml", str(cm.exception))
        self.assertFalse(cli.common.STATE_FILE.exists())

    def test_preview_rejects_arguments(self):
        with self.assertRaises(SystemExit):
            cli.discover.cmd_preview(["some_target"])

    def test_status_rejects_unknown_arguments(self):
        # --live/--tail moved to `print-log` - status must reject them, not silently ignore.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(cli.common.LOG_DIR / "run_missing.log"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with self.assertRaises(SystemExit):
            cli.monitor.cmd_status(["--live"])

    def test_status_headline_shows_project_and_config(self):
        with open(os.path.join("config", "config.yaml"), "w") as f:
            f.write('project_name: "Demo Project"\n')
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(cli.common.LOG_DIR / "run_missing.log"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertIn("Demo Project", output)
        self.assertIn("config/config.yaml", output)

    def test_status_shows_progress_bar(self):
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        log_path = cli.common.LOG_DIR / "run_progress.log"
        log_path.write_text("5 of 10 steps (50.0%) done\n")
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertIn("50.0%", output)
        self.assertIn("5/10 steps", output)
        self.assertIn("█" if cli.monitor.UNICODE_OK else "#", output)

    def test_status_last_finished_and_running_labels_say_jobs(self):
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        log_path = cli.common.LOG_DIR / "run_jobs.log"
        log_path.write_text("")
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertIn("Last finished jobs", output)
        self.assertIn("Currently running jobs", output)

    def test_watch_passes_tail_lines_to_print_status(self):
        # Stub _print_status: exercise cmd_status's watch wiring without looping forever.
        calls = []

        def fake_print_status(tail=None):
            calls.append(tail)
            print("line one")
            return False  # not alive -> loop exits after one iteration

        orig_print_status = cli.monitor._print_status
        cli.monitor._print_status = fake_print_status
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                cli.monitor.cmd_status(["--watch"])
                cli.monitor.cmd_status(["-w"])
        finally:
            cli.monitor._print_status = orig_print_status
        self.assertEqual(
            calls, [cli.monitor.WATCH_TAIL_LINES, cli.monitor.WATCH_TAIL_LINES]
        )
        # One frame per refresh, drawn over the old one rather than after clearing the screen.
        frame = "\033[Hline one\033[K\n\033[J"
        self.assertEqual(out.getvalue(), frame * 2)

    def test_abort_force_short_flag_kills_process_group(self):
        killed = []
        orig = (cli.monitor._read_state, cli.monitor._is_alive, cli.monitor.os.killpg)
        cli.monitor._read_state = lambda: {"pid": 12345}
        cli.monitor._is_alive = lambda pid, **kw: True
        cli.monitor.os.killpg = lambda pid, sig: killed.append((pid, sig))
        try:
            for flag in ("--force", "-f"):
                with contextlib.redirect_stdout(io.StringIO()):
                    cli.monitor.cmd_abort([flag])
        finally:
            cli.monitor._read_state, cli.monitor._is_alive, cli.monitor.os.killpg = orig
        self.assertEqual(killed, [(12345, signal.SIGKILL)] * 2)

    def test_print_log_tail_shows_only_last_n_lines(self):
        os.makedirs(cli.common.LOG_DIR)
        log = cli.common.LOG_DIR / "run_tail.log"
        log.write_text("\n".join(f"line{i}" for i in range(30)) + "\n")
        for flag in ("--tail", "-t"):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                cli.monitor.cmd_print_log([flag, "3"])
            output = out.getvalue()
            self.assertIn("line29", output)
            self.assertNotIn("line26", output)

    def test_print_log_tail_without_number_defaults(self):
        os.makedirs(cli.common.LOG_DIR)
        log = cli.common.LOG_DIR / "run_tail_default.log"
        log.write_text("\n".join(f"l{i}" for i in range(30)) + "\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_print_log(["--tail"])
        output = out.getvalue()
        self.assertIn("l29", output)
        self.assertNotIn("l9\n", output)

    def test_print_log_live_uses_tail_dash_f(self):
        os.makedirs(cli.common.LOG_DIR)
        log = cli.common.LOG_DIR / "run_live.log"
        log.write_text("hello\n")
        captured = []
        orig = cli.monitor.subprocess.run
        cli.monitor.subprocess.run = lambda cmd, **kw: captured.append(cmd)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cli.monitor.cmd_print_log(["--live"])
                cli.monitor.cmd_print_log(["-l", "-t", "5"])
        finally:
            cli.monitor.subprocess.run = orig
        self.assertIn("-f", captured[0])
        self.assertIn(str(log), captured[0])
        self.assertEqual(captured[1], ["tail", "-n", "5", "-f", str(log)])

    def test_status_flags_force_kill_when_dead_without_failure_or_completion(self):
        # Process not running, log has partial progress and no "did not complete successfully"
        # marker (Snakemake never got to log a reason) - most likely a force-kill.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_path = cli.common.LOG_DIR / "run_forcekilled.log"
        os.makedirs(cli.common.LOG_DIR)
        log_path.write_text("31 of 210 steps (15%) done\n")
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        self.assertIn("Interrupted", out.getvalue())

    def test_status_not_interrupted_when_nothing_to_be_done(self):
        # Process not running, log has no progress line at all because the DAG's targets were
        # already present and up to date - Snakemake's normal no-op success, must not be
        # misread as a force-kill just because there's no "100%" line to match.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        log_path = cli.common.LOG_DIR / "run_nothing_to_do.log"
        log_path.write_text(
            "Nothing to be done (all requested files are present and up to date).\n"
        )
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        self.assertNotIn("Interrupted", out.getvalue())

    def test_status_reports_dry_run_instead_of_force_kill(self):
        # `run`/`resume` pass unknown snakemake flags through, so `run --cores N -n` is tracked
        # in the state file like a real run. A dry run executes nothing and exits in seconds, so
        # it has no progress line and no failure marker - it must not be reported as a force-kill.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        log_path = cli.common.LOG_DIR / "run_dryrun.log"
        log_path.write_text(
            "This was a dry-run (flag -n). The order of jobs does not reflect the order of execution.\n"
        )
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "40", "-n"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertNotIn("Interrupted", output)
        self.assertNotIn("Resume with", output)
        self.assertIn("dry run", output)

    def test_status_flags_lock_exception(self):
        # Process not running, log has a LockException (stale lock from a killed run or
        # power loss) - must be reported as "Locked", not misread as a force-kill.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_path = cli.common.LOG_DIR / "run_locked.log"
        os.makedirs(cli.common.LOG_DIR)
        log_path.write_text(
            "[2026-08-16 12:49:14 (CEST)] [ERROR] LockException:\n"
            "Error: Directory cannot be locked. Please make sure that no other Snakemake "
            "process is trying to create the same files in the following directory:\n"
            "/mnt/data5/sarah/snakemake_demo_pipelines/demo_adna_pipeline\n"
        )
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertIn("Locked", output)
        self.assertIn("pastForward unlock", output)
        self.assertNotIn("Interrupted", output)

    def test_status_hides_job_lists_when_process_is_dead(self):
        # Process finished (not running anymore) - "Last finished jobs"/"Currently running
        # jobs" describe live progress and are meaningless once the run has stopped.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        log_path = cli.common.LOG_DIR / "run_finished.log"
        log_path.write_text("210 of 210 steps (100.0%) done\n")
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertNotIn("Last finished jobs", output)
        self.assertNotIn("Currently running jobs", output)

    def test_status_not_interrupted_when_progress_percent_has_no_decimal(self):
        # Snakemake only prints a decimal for non-round percentages, so a clean 100% finish
        # can log "(100%)" instead of "(100.0%)" - must not be misread as a force-kill.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        log_path = cli.common.LOG_DIR / "run_finished_no_decimal.log"
        log_path.write_text(
            "177 of 177 steps (100%) done\nWorkflow finished, no error\n"
        )
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(log_path),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        self.assertNotIn("Interrupted", out.getvalue())

    def test_status_prints_tail_of_failed_job_log(self):
        # On a dead+failed run, status should surface the actual error message from each
        # failed job's own log file - not just Snakemake's "check log file(s)" pointer.
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.common.LOG_DIR)
        main_log = cli.common.LOG_DIR / "run_failed.log"
        job_log = cli.common.LOG_DIR / "bwa_mem2_sample.log"
        job_log.write_text("bwa-mem2: error: index file not found\nAborting.\n")
        main_log.write_text(
            "12 of 210 steps (5.7%) done\n"
            "Error in rule map_reads_to_reference_bwa_mem2:\n"
            "    jobid: 12\n"
            "    input: sample.fastq.gz, ref.fasta\n"
            "    output: sample.bam\n"
            f"    log: {job_log} (check log file(s) for error message)\n"
            "    shell:\n"
            "        bwa-mem2 mem ref.fasta sample.fastq.gz > sample.bam\n"
            "        (one of the commands exited with non-zero exit code; note that "
            "snakemake uses bash strict mode!)\n"
            "\n"
            "At least one job did not complete successfully.\n"
        )
        cli.common.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": 999999,
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(main_log),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_status([])
        output = out.getvalue()
        self.assertIn("index file not found", output)
        self.assertIn(str(job_log), output)

    def test_print_log_rejects_arguments(self):
        with self.assertRaises(SystemExit):
            cli.monitor.cmd_print_log(["--foo"])

    def test_print_log_dies_without_logs_dir(self):
        with self.assertRaises(SystemExit):
            cli.monitor.cmd_print_log([])

    def test_print_log_prefers_the_live_tracked_run(self):
        os.makedirs(cli.common.LOG_DIR)
        run_log = cli.common.LOG_DIR / "run_20260101_000000.log"
        dryrun_log = cli.common.LOG_DIR / "dryrun_20260101_000001.log"
        run_log.write_text("run log\n")
        dryrun_log.write_text("dryrun log\n")
        os.utime(run_log, (1, 1))
        os.utime(dryrun_log, (2, 2))
        cli.common.STATE_DIR.mkdir(parents=True, exist_ok=True)
        state = {"pid": os.getpid(), "log_file": str(run_log.resolve())}
        cli.common.STATE_FILE.write_text(json.dumps(state))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_print_log([])
        self.assertIn("run log", out.getvalue())
        # Once that run is over, the newest log wins again.
        cli.common.STATE_FILE.write_text(json.dumps({**state, "pid": 2**22 + 1}))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_print_log([])
        self.assertIn("dryrun log", out.getvalue())

    def test_print_log_prints_most_recently_modified_file(self):
        os.makedirs(cli.common.LOG_DIR)
        old = cli.common.LOG_DIR / "dryrun_20260101_000000.log"
        new = cli.common.LOG_DIR / "run_20260101_000001.log"
        old.write_text("old log\n")
        new.write_text("new log\n")
        os.utime(old, (1, 1))
        os.utime(new, (2, 2))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.monitor.cmd_print_log([])
        self.assertIn("new log", out.getvalue())
        self.assertNotIn("old log", out.getvalue())


class TrackedPidTestCase(unittest.TestCase):
    """Linux reuses PIDs, so a saved PID only counts as the tracked run while `ps` still
    shows a snakemake command line for it."""

    def _ps(self, stdout="", returncode=0, missing=False):
        def fake_run(cmd, **kw):
            self.assertEqual(cmd[:3], ["ps", "-o", "command="])
            if missing:
                raise FileNotFoundError("ps")
            return cli.common.subprocess.CompletedProcess(cmd, returncode, stdout, "")

        return fake_run

    def setUp(self):
        self._orig = (cli.common.subprocess.run, cli.common._pid_alive)
        cli.common._pid_alive = lambda pid: True

    def tearDown(self):
        cli.common.subprocess.run, cli.common._pid_alive = self._orig

    def test_snakemake_command_line_is_alive(self):
        cli.common.subprocess.run = self._ps(
            "/env/bin/python3 /env/bin/snakemake --cores 8\n"
        )
        self.assertTrue(cli.common._is_alive(4242))

    def test_foreign_command_line_is_not_alive(self):
        cli.common.subprocess.run = self._ps("vim notes.txt\n")
        self.assertFalse(cli.common._is_alive(4242))

    def test_dead_pid_is_not_alive(self):
        cli.common._pid_alive = lambda pid: False
        cli.common.subprocess.run = self._ps(missing=True)  # must not even be asked
        self.assertFalse(cli.common._is_alive(4242))
        # Died between the two checks: ps exits 1 with no output.
        cli.common._pid_alive = lambda pid: True
        cli.common.subprocess.run = self._ps(returncode=1)
        self.assertFalse(cli.common._is_alive(4242))

    def test_missing_ps_uses_the_callers_safe_default(self):
        cli.common.subprocess.run = self._ps(missing=True)
        self.assertTrue(cli.common._is_alive(4242))
        self.assertFalse(cli.common._is_alive(4242, if_unknown=False))

    def test_abort_does_not_kill_a_foreign_process(self):
        killed = []
        orig = (cli.monitor._read_state, cli.monitor.os.kill, cli.monitor.os.killpg)
        cli.monitor._read_state = lambda: {"pid": 4242}
        cli.monitor.os.kill = lambda pid, sig: killed.append(pid)
        cli.monitor.os.killpg = lambda pid, sig: killed.append(pid)
        try:
            for stub in (self._ps("bash\n"), self._ps(missing=True)):
                cli.common.subprocess.run = stub
                for argv in ([], ["--force"]):
                    with self.assertRaises(SystemExit):
                        cli.monitor.cmd_abort(argv)
        finally:
            cli.monitor._read_state, cli.monitor.os.kill, cli.monitor.os.killpg = orig
        self.assertEqual(killed, [])

    def test_foreign_tracked_pid_does_not_block_a_new_run(self):
        project = tempfile.mkdtemp(prefix="pf_test_cli_pid_")
        cwd = os.getcwd()
        os.chdir(project)
        try:
            cli.common.STATE_DIR.mkdir()
            cli.common.STATE_FILE.write_text(json.dumps({"pid": 4242}))
            cli.common.subprocess.run = self._ps("zsh\n")
            self.assertIsNone(cli.common._live_tracked_pid())
            cli.common.subprocess.run = self._ps(
                "python /env/bin/snakemake --cores 2\n"
            )
            self.assertEqual(cli.common._live_tracked_pid(), 4242)
        finally:
            os.chdir(cwd)
            shutil.rmtree(project, ignore_errors=True)


class ParseLastStepsTestCase(unittest.TestCase):
    # One finished job (id 3, a plain rule with no `message:`) and one still-running job
    # (id 7, a wrapper rule with a `message:` directive - so it has no "rule X:"/"jobid:"
    # block at all, only the "Rule: X, Jobid: N" line that initialize.smk's root
    # logging.basicConfig duplicates for every job regardless of `message:`).
    LOG = """\
[2026-08-16 10:00:00 (CEST)] [INFO] Building DAG of jobs...
[2026-08-16 10:00:00 (CEST)] [INFO]  Rule: fastqc, Jobid: 3
rule fastqc:
    input: reads.fastq.gz
    output: reads_fastqc.html
    jobid: 3
    reason: Missing output files

[2026-08-16 10:00:05 (CEST)] [INFO] Finished jobid: 3 (Rule: fastqc)
[2026-08-16 10:00:05 (CEST)]
Finished jobid: 3 (Rule: fastqc)
3 of 10 steps (30%) done
[2026-08-16 10:00:06 (CEST)] [INFO]  Rule: map_reads_to_reference_bwa_mem2, Jobid: 7
[2026-08-16 10:00:06 (CEST)]
Job 7: Mapping reads.fastq.gz to ref.fasta with BWA-MEM2
Reason: Missing output files
"""

    def test_progress_takes_last_match(self):
        m = None
        for m in cli.monitor.PROGRESS_RE.finditer(self.LOG):
            pass
        self.assertEqual(m.groups(), ("3", "10", "30"))

    def test_last_steps_status(self):
        finished, running = cli.monitor._parse_last_steps(self.LOG)
        self.assertEqual(finished, [("fastqc", "3")])
        self.assertEqual(running, [("map_reads_to_reference_bwa_mem2", "7")])

    def test_last_steps_caps_at_n(self):
        many = "\n".join(
            f"[2026-08-16 10:00:00 (CEST)] [INFO]  Rule: r{i}, Jobid: {i}\n"
            f"[2026-08-16 10:00:01 (CEST)] [INFO] Finished jobid: {i} (Rule: r{i})"
            for i in range(8)
        )
        finished, running = cli.monitor._parse_last_steps(many, n=5)
        self.assertEqual(len(finished), 5)
        self.assertEqual(running, [])


class CheckPreviewParsingTestCase(unittest.TestCase):
    # Trimmed real output from `snakemake --dryrun` against a throwaway fixture project.
    LOG = """\
[2026-08-16 09:53:15 (CEST)] [INFO] Loaded configuration:
{}

[2026-08-16 09:53:15 (CEST)] [INFO] Detected species (1):
- TestSpecies [TestSpecies]
    References (1):
      - genome: TestSpecies/input/reference_module/genome.fasta
    SCG Libraries: (none provided; skipping auto-determination)
Workflow defines that rule index_reference_for_mapping_bwa_mem2 is eligible for caching.
[2026-08-16 09:53:17 (CEST)] [WARNING] Workflow defines that rule index_reference_for_mapping_bwa_mem2 is eligible for caching.
[2026-08-16 09:53:17 (CEST)] [INFO] Skipping species 'OtherSpecies' (execute: false)
[2026-08-16 09:53:17 (CEST)] [INFO] The following files already exist and will be skipped:
[2026-08-16 09:53:17 (CEST)] [INFO] \t- Skipping: TestSpecies/results/read_module/reads_merged/IND001.fastq.gz
[2026-08-16 09:53:17 (CEST)] [INFO] Determined input for the 'all' rule:
[2026-08-16 09:53:17 (CEST)] [INFO] \t- Requesting: TestSpecies/results/summary/species_level/TestSpecies_multiqc.overall.html
[2026-08-16 09:53:17 (CEST)] [INFO] \t- Requesting: TestSpecies/results/summary/individual_level/IND001_multiqc.html
"""

    def test_check_block_stops_before_unrelated_warning(self):
        m = cli.discover.DETECTED_SPECIES_RE.search(self.LOG)
        lines = self.LOG[m.start() :].splitlines()
        block = [lines[0]]
        for line in lines[1:]:
            if line == "" or line.startswith("-") or line[:1].isspace():
                block.append(line)
            else:
                break
        block_text = "\n".join(block)
        self.assertIn("SCG Libraries", block_text)
        self.assertNotIn("Workflow defines", block_text)

    def test_preview_extracts_requested_skipped_and_disabled_species(self):
        import re

        skipped_species = re.findall(
            r"Skipping species '(.+?)' \(execute: false\)", self.LOG
        )
        existing = re.findall(r"- Skipping: (.+)", self.LOG)
        requested = re.findall(r"- Requesting: (.+)", self.LOG)
        self.assertEqual(skipped_species, ["OtherSpecies"])
        self.assertEqual(
            existing, ["TestSpecies/results/read_module/reads_merged/IND001.fastq.gz"]
        )
        self.assertEqual(len(requested), 2)


class ListCondaEnvsTestCase(unittest.TestCase):
    # Real `snakemake --list-conda-envs` output shape: one row per rule, so an env used by
    # several rules repeats with the same location (the crash in `doctor --rebuild-envs` was
    # rmtree() on that same directory twice).
    OUT = """\
[2026-09-07 10:00:00 (CEST)] [INFO] Building DAG of jobs...
environment\tsource\tlocation
workflow/envs/python_and_r.yaml\t-\t.snakemake/conda/3f83c79_
workflow/envs/python_and_r.yaml\t-\t.snakemake/conda/3f83c79_
workflow/envs/read_module/environment.yaml\t-\t.snakemake/conda/2844fb9_
workflow/envs/reference_module/environment.yaml\t-\t.snakemake/conda/1c817e9_
"""

    def test_rows_are_deduplicated_by_location(self):
        class FakeProc:
            returncode = 0
            stdout = ListCondaEnvsTestCase.OUT

        real_run = cli.doctor.subprocess.run
        cli.doctor.subprocess.run = lambda *a, **kw: FakeProc()
        try:
            envs = cli.doctor._list_conda_envs()
        finally:
            cli.doctor.subprocess.run = real_run
        self.assertEqual(
            [e["location"] for e in envs],
            [
                ".snakemake/conda/3f83c79_",
                ".snakemake/conda/2844fb9_",
                ".snakemake/conda/1c817e9_",
            ],
        )
        self.assertEqual(envs[0]["env_file"], "workflow/envs/python_and_r.yaml")


class BenchmarkRecordTestCase(unittest.TestCase):
    """Aggregation of the *.benchmark.jsonl files workflow/rules/benchmark.smk attaches to every
    rule. Field names and the "NA" placeholder mirror snakemake/benchmark.py's extended JSONL
    format (BenchmarkRecord.to_json with extended_fmt=True)."""

    @staticmethod
    def _record(rule, seconds, max_rss="NA", threads=1, input_size_mb=None):
        return {
            "s": seconds,
            "h:m:s": "0:00:00",
            "max_rss": max_rss,
            "max_vms": "NA",
            "cpu_time": "NA",
            "jobid": 1,
            "rule_name": rule,
            "wildcards": {},
            "params": {},
            "threads": threads,
            "resources": {"_cores": threads},
            "input_size_mb": {"in.bam": input_size_mb}
            if input_size_mb is not None
            else {},
        }

    def test_benchmark_number_treats_na_as_missing(self):
        # Snakemake writes "NA", not 0, for anything it could not sample - reporting it as 0 MB
        # would read as "this rule needs no memory", which is the opposite of the truth.
        self.assertIsNone(cli.benchmark._benchmark_number("NA"))
        self.assertIsNone(cli.benchmark._benchmark_number(None))
        self.assertIsNone(cli.benchmark._benchmark_number("-"))
        self.assertEqual(cli.benchmark._benchmark_number(12), 12.0)
        self.assertEqual(cli.benchmark._benchmark_number("3.5"), 3.5)

    def test_summarize_groups_per_rule_and_sorts_by_core_hours(self):
        records = [
            self._record("slow_rule", 3600, max_rss=1000, threads=4),
            self._record("slow_rule", 1800, max_rss=2000, threads=4),
            self._record("quick_rule", 10, max_rss=50, threads=1),
        ]
        rows = cli.benchmark._summarize_benchmarks(records)
        self.assertEqual([row["rule"] for row in rows], ["slow_rule", "quick_rule"])
        slow = rows[0]
        self.assertEqual(slow["jobs"], 2)
        self.assertEqual(slow["median_s"], 2700)
        self.assertEqual(slow["max_s"], 3600)
        self.assertEqual(slow["max_rss_mb"], 2000)
        self.assertAlmostEqual(slow["core_hours"], (3600 * 4 + 1800 * 4) / 3600)

    def test_summarize_reports_no_memory_rather_than_zero(self):
        rows = cli.benchmark._summarize_benchmarks([self._record("mac_rule", 42)])
        self.assertIsNone(rows[0]["max_rss_mb"])
        self.assertEqual(rows[0]["max_s"], 42)

    def test_summarize_takes_largest_total_input_size(self):
        records = [
            self._record("map", 10, input_size_mb=100),
            self._record("map", 10, input_size_mb=250),
        ]
        self.assertEqual(
            cli.benchmark._summarize_benchmarks(records)[0]["max_input_mb"], 250
        )

    def test_summarize_labels_records_without_a_rule_name(self):
        # Pre-extended-format files (or a run where benchmark.smk could not switch the extended
        # format on) have no rule_name at all. They must not be dropped silently.
        rows = cli.benchmark._summarize_benchmarks([{"s": 5, "max_rss": "NA"}])
        self.assertEqual(rows[0]["rule"], "(unknown rule)")

    def test_emit_profile_skips_mem_mb_when_memory_was_never_measured(self):
        rows = cli.benchmark._summarize_benchmarks(
            [
                self._record("measured", 60, max_rss=1000),
                self._record("wall_time_only", 60),
            ]
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.benchmark._emit_benchmark_profile(rows)
        out = buffer.getvalue()
        self.assertIn("set-resources:", out)
        # runtime is in minutes at 2x the observed max, mem_mb at 1.5x the observed peak.
        self.assertIn("    runtime: 2\n", out)
        self.assertIn("    mem_mb: 1500\n", out)
        self.assertEqual(out.count("mem_mb:"), 1)


class FindBenchmarkFilesTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_cli_benchmark_")
        os.chdir(self.project_dir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def _touch(self, relative_path):
        path = os.path.join(self.project_dir, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        return path

    def test_finds_benchmark_files_and_ignores_everything_else(self):
        self._touch("Dmel/processed/reference_module/IND001_sorted.benchmark.jsonl")
        self._touch("Dmel/processed/reference_module/IND001_sorted.log")
        self._touch("Dmel/results/summary/Dmel_multiqc.benchmark.jsonl")
        found = [os.path.basename(p) for p in cli.benchmark._find_benchmark_files()]
        self.assertEqual(
            found, ["IND001_sorted.benchmark.jsonl", "Dmel_multiqc.benchmark.jsonl"]
        )

    def test_skips_the_pipeline_code_and_dot_directories(self):
        # .snakemake holds its own copies of a lot of things, and workflow/ is pipeline code that
        # travels between machines - neither ever holds a benchmark belonging to this project.
        self._touch("workflow/rules/leftover.benchmark.jsonl")
        self._touch(".snakemake/leftover.benchmark.jsonl")
        self.assertEqual(cli.benchmark._find_benchmark_files(), [])

    def test_follows_a_symlinked_processed_directory(self):
        # species_paths.py turns a configured processed_dir/results_dir into a symlink at the
        # conventional in-project path, so every benchmark file can sit behind one.
        external = os.path.join(self.project_dir, "external_store")
        os.makedirs(external)
        open(os.path.join(external, "IND001.benchmark.jsonl"), "w").close()
        os.makedirs(os.path.join(self.project_dir, "Dmel"))
        os.symlink(external, os.path.join(self.project_dir, "Dmel/processed"))
        found = cli.benchmark._find_benchmark_files("Dmel")
        self.assertEqual(
            [os.path.basename(p) for p in found], ["IND001.benchmark.jsonl"]
        )

    def test_survives_a_symlink_cycle(self):
        # Following symlinks means a loop is possible; it must not hang the command.
        os.makedirs(os.path.join(self.project_dir, "Dmel/processed"))
        os.symlink(
            os.path.join(self.project_dir, "Dmel"),
            os.path.join(self.project_dir, "Dmel/processed/loop"),
        )
        self._touch("Dmel/processed/IND001.benchmark.jsonl")
        self.assertEqual(len(cli.benchmark._find_benchmark_files()), 1)

    def test_benchmark_command_explains_an_empty_project(self):
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        with self.assertRaises(SystemExit) as caught:
            cli.benchmark.cmd_benchmark([])
        self.assertIn("no", str(caught.exception).lower())

    def test_benchmark_command_rejects_unknown_arguments(self):
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        with self.assertRaises(SystemExit):
            cli.benchmark.cmd_benchmark(["--emit-profile", "--nonsense"])

    def test_benchmark_command_skips_unreadable_files_instead_of_failing(self):
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        good = self._touch("Dmel/processed/good.benchmark.jsonl")
        Path(good).write_text(
            json.dumps({"s": 3, "max_rss": 10, "threads": 1, "rule_name": "good"})
            + "\n"
        )
        Path(self._touch("Dmel/processed/bad.benchmark.jsonl")).write_text(
            "{not json\n"
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.benchmark.cmd_benchmark([])
        self.assertIn("good", buffer.getvalue())


class ToolsTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_cli_tools_")
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        os.chdir(self.project_dir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def _run(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.main(["tools", "create-species", *argv])
        return buffer.getvalue()

    def test_creates_every_input_folder_and_prints_a_loadable_config(self):
        import yaml

        output = self._run(["Dmel", "Dsim"])
        for key in ("Dmel", "Dsim"):
            for sub in cli.tools.SPECIES_INPUT_DIRS:
                self.assertTrue(Path(key, sub).is_dir(), f"{key}/{sub}")
            # Left for the pipeline, see SPECIES_INPUT_DIRS.
            self.assertFalse(Path(key, "processed").exists())
        snippet = output[output.index("\nspecies:") :]
        self.assertEqual(set(yaml.safe_load(snippet)["species"]), {"Dmel", "Dsim"})

    def test_is_idempotent_and_keeps_existing_files(self):
        self._run(["Dmel"])
        reads = Path("Dmel/input/read_module/IND001_R1.fastq.gz")
        reads.write_text("x")
        self._run(["Dmel"])
        self.assertEqual(reads.read_text(), "x")

    def test_rejects_unsafe_names_before_creating_anything(self):
        for bad in (["../Dmel"], ["Dm el"], ["workflow"], ["Dmel", ".hidden"], []):
            with self.assertRaises(SystemExit):
                self._run(bad)
        self.assertFalse(Path("Dmel").exists())

    def test_link_reads_links_only_reads_by_absolute_path(self):
        self._run(["Dmel"])
        source = Path(tempfile.mkdtemp(prefix="pf_test_cli_reads_"))
        self.addCleanup(shutil.rmtree, source, ignore_errors=True)
        for name in (
            "IND1_R1.fastq.gz",
            "IND1_R2.fq.gz",
            "notes.txt",
            "._IND1_R1.fastq.gz",
        ):
            (source / name).write_text("x")
        (source / "sub").mkdir()
        (source / "sub" / "IND2_R1.fastq.gz").write_text("x")
        reads_dir = Path("Dmel/input/read_module")
        (reads_dir / "IND1_R2.fq.gz").write_text("mine")

        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(
                ["tools", "link-reads", "--source", str(source), "--species", "Dmel"]
            )
            cli.main(
                ["tools", "link-reads", "-s", "Dmel", "-d", str(source)]
            )  # rerun is harmless, any order

        self.assertEqual(
            sorted(p.name for p in reads_dir.iterdir()),
            ["IND1_R1.fastq.gz", "IND1_R2.fq.gz"],
        )
        link = reads_dir / "IND1_R1.fastq.gz"
        self.assertEqual(
            Path(os.readlink(link)), (source / "IND1_R1.fastq.gz").resolve()
        )
        self.assertTrue(Path(os.readlink(link)).is_absolute())
        self.assertEqual((reads_dir / "IND1_R2.fq.gz").read_text(), "mine")

    def test_link_reads_warns_about_names_the_pipeline_would_not_use(self):
        self._run(["Dmel"])
        source = Path(tempfile.mkdtemp(prefix="pf_test_cli_reads_"))
        self.addCleanup(shutil.rmtree, source, ignore_errors=True)
        names = (
            "IND1_R1.fastq.gz",
            "IND2_1.fq.gz",
            "IND3.fastq.gz",
            "IND4_R1_x_R1.fastq.gz",
        )
        for name in names:
            (source / name).write_text("x")

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.main(["tools", "link-reads", f"--source={source}", "--species=Dmel"])
        warning = buffer.getvalue().split("Warning:")[1]

        self.assertNotIn("IND1_R1", warning)
        self.assertNotIn("IND2_1", warning)
        self.assertIn("IND3.fastq.gz", warning)
        self.assertIn("IND4_R1_x_R1.fastq.gz", warning)
        # Still linked, so the links can be renamed in place.
        self.assertEqual(
            len(list(Path("Dmel/input/read_module").iterdir())), len(names)
        )

    def test_check_warns_about_read_names_even_when_no_individual_is_found(self):
        Path("config/config.yaml").write_text(
            "project_name: demo\nspecies:\n  Dmel:\n    name: Dmel\n"
        )
        self._run(["Dmel"])
        Path("Dmel/input/read_module/IND1.fastq.gz").write_text("x")

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.main(["check"])
        output = buffer.getvalue()

        self.assertIn("Individuals: (none found)", output)
        self.assertIn("WARNING: reads not used (1)", output)
        self.assertIn("IND1.fastq.gz (no read marker", output)

    def test_link_reads_needs_the_species_folder_and_reads(self):
        source = tempfile.mkdtemp(prefix="pf_test_cli_reads_")
        self.addCleanup(shutil.rmtree, source, ignore_errors=True)
        for argv in (
            ["-d", source, "-s", "Dmel"],
            ["-d", source],
            ["-d", "/no/such/dir", "-s", "Dmel"],
        ):
            with self.assertRaises(SystemExit):
                cli.main(["tools", "link-reads", *argv])
        self._run(["Dmel"])
        with self.assertRaises(SystemExit):  # no reads in source
            cli.main(["tools", "link-reads", "-d", source, "-s", "Dmel"])

    def test_link_reads_rejects_bad_arguments(self):
        self._run(["Dmel"])
        source = tempfile.mkdtemp(prefix="pf_test_cli_reads_")
        self.addCleanup(shutil.rmtree, source, ignore_errors=True)
        (Path(source) / "IND1_R1.fastq.gz").write_text("x")
        bad = (
            [source, "Dmel"],  # positional arguments are not accepted
            ["-d", source, "-s"],  # flag without a value
            ["-d", source, "-s", "Dmel", "-s", "Dsim"],  # repeated flag
            ["-d", source, "-s", "Dmel", "--force"],  # unknown flag
        )
        for argv in bad:
            with (
                self.assertRaises(SystemExit),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                cli.main(["tools", "link-reads", *argv])
        self.assertEqual(list(Path("Dmel/input/read_module").iterdir()), [])

    def _fasta_source(self, *names):
        source = Path(tempfile.mkdtemp(prefix="pf_test_cli_fa_"))
        self.addCleanup(shutil.rmtree, source, ignore_errors=True)
        for name in names:
            (source / name).write_text(">x\n")
        return source

    def test_link_reference_and_feature_library_default_to_the_only_species(self):
        self._run(["Dmel"])
        src = self._fasta_source("ref.fna", "notes.txt", "lib.fa", "comp.fasta")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["tools", "link-reference", "-d", str(src)])
            cli.main(
                ["tools", "link-reference", "-d", str(src / "ref.fna")]
            )  # file, rerun
            cli.main(
                [
                    "tools",
                    "link-feature-library",
                    "-d",
                    str(src / "lib.fa"),
                    "-c",
                    str(src / "comp.fasta"),
                ]
            )

        def names(sub):
            return sorted(p.name for p in Path("Dmel/input", sub).iterdir())

        self.assertEqual(names("reference_module"), ["comp.fasta", "lib.fa", "ref.fna"])
        self.assertEqual(names("reveal_module/feature_library"), ["lib.fa"])
        self.assertEqual(names("reveal_module/competition"), ["comp.fasta"])

    def test_link_tools_need_species_flag_with_several_species(self):
        self._run(["Dmel", "Dsim"])
        src = self._fasta_source("ref.fna")
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            cli.main(["tools", "link-reference", "-d", str(src)])
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["tools", "link-reference", "-d", str(src), "-s", "Dsim"])
        self.assertTrue(Path("Dsim/input/reference_module/ref.fna").is_symlink())
        self.assertEqual(list(Path("Dmel/input/reference_module").iterdir()), [])

    def test_link_feature_library_refuses_a_second_competition_file(self):
        self._run(["Dmel"])
        src = self._fasta_source("lib.fa", "a.fa", "b.fa")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(
                [
                    "tools",
                    "link-feature-library",
                    "-d",
                    str(src / "lib.fa"),
                    "-c",
                    str(src / "a.fa"),
                ]
            )
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            cli.main(
                [
                    "tools",
                    "link-feature-library",
                    "-d",
                    str(src / "lib.fa"),
                    "-c",
                    str(src / "b.fa"),
                ]
            )

    def test_link_fasta_tools_reject_bad_arguments(self):
        src = self._fasta_source("ref.fna")
        empty = self._fasta_source("notes.txt")
        for tool, argv in [
            ("link-reference", ["-d", str(src)]),  # no species folder yet
            ("link-reference", []),  # no source
            ("link-reference", ["-d", "/no/such/file.fa"]),
            ("link-reference", ["-d", str(empty)]),  # no FASTA inside
            ("link-feature-library", ["-d", str(src), "-c"]),  # flag without value
            ("link-feature-library", ["-d", str(src), "-c", str(empty)]),
        ]:
            with (
                self.subTest(tool=tool, argv=argv),
                self.assertRaises(SystemExit),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                cli.main(["tools", tool, *argv])

    def test_species_guess_ignores_reserved_folder_names(self):
        self._run(["Dmel"])
        (Path("docs") / "input").mkdir(parents=True)
        src = self._fasta_source("ref.fna")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["tools", "link-reference", "-d", str(src)])
        self.assertTrue(Path("Dmel/input/reference_module/ref.fna").is_symlink())

    def test_unknown_tool_exits(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
            cli.main(["tools", "nonsense"])


class SnakemakeEnvTestCase(unittest.TestCase):
    """_use_snakemake_env and _validate_config_or_die: the paths a user hits before any run."""

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self.dir = tempfile.mkdtemp(prefix="pf_test_env_")
        self.env = os.path.join(self.dir, "envs", "snakemake")
        os.makedirs(os.path.join(self.env, "bin"))
        Path(self.env, "bin", "snakemake").touch()
        self.settings = Path(self.dir, "cli.json")
        for patcher in (
            unittest.mock.patch.object(
                cli.user_settings, "SETTINGS_FILE", self.settings
            ),
            unittest.mock.patch.dict(os.environ, {}),
            unittest.mock.patch.object(cli.common.shutil, "which", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.dir, ignore_errors=True)

    def record(self, **extra):
        self.settings.write_text(json.dumps({"snakemake_env": self.env, **extra}))

    def die_message(self):
        with self.assertRaises(SystemExit) as cm:
            cli.common._use_snakemake_env()
        return str(cm.exception.code)

    def test_snakemake_on_path_is_remembered(self):
        with unittest.mock.patch.object(
            cli.common.shutil,
            "which",
            return_value=os.path.join(self.env, "bin", "snakemake"),
        ):
            cli.common._use_snakemake_env()
        self.assertEqual(
            json.loads(self.settings.read_text())["snakemake_env"], self.env
        )

    def test_recorded_env_is_used_without_activate(self):
        self.record()
        with contextlib.redirect_stderr(io.StringIO()):
            cli.common._use_snakemake_env()
        self.assertTrue(os.environ["PATH"].startswith(os.path.join(self.env, "bin")))
        self.assertEqual(os.environ["CONDA_PREFIX"], self.env)
        self.assertEqual(os.environ["CONDA_DEFAULT_ENV"], "snakemake")

    def test_auto_activate_off_stops_with_hint(self):
        self.record(auto_activate=False)
        self.assertIn("conda activate snakemake", self.die_message())

    def test_no_record_stops(self):
        self.assertIn("no env is recorded", self.die_message())

    def test_deleted_env_is_named_in_message(self):
        self.record()
        shutil.rmtree(self.env)
        self.assertIn(f"recorded env {self.env} has no snakemake", self.die_message())

    def test_validate_config_or_die_reports_check_failure(self):
        os.makedirs(os.path.join(self.dir, "config"))
        os.chdir(self.dir)
        with (
            unittest.mock.patch.object(
                cli.common, "check_config", side_effect=ValueError("boom")
            ),
            self.assertRaises(SystemExit) as cm,
        ):
            cli.common._validate_config_or_die([])
        self.assertIn("ValueError: boom", str(cm.exception.code))


class InstallTestCase(unittest.TestCase):
    real_ensure_jsonschema = staticmethod(cli.install._ensure_jsonschema)

    def setUp(self):
        # Stubbed here: the env folders in these tests have no python to ask for jsonschema.
        patcher = unittest.mock.patch.object(cli.install, "_ensure_jsonschema")
        patcher.start()
        self.addCleanup(patcher.stop)
        self._orig_cwd = os.getcwd()
        self.project_dir = tempfile.mkdtemp(prefix="pf_test_cli_install_")
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        os.chdir(self.project_dir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_ensure_jsonschema_installs_only_when_missing(self):
        prefix = os.path.join(self.project_dir, "envs", "pastforward")
        os.makedirs(os.path.join(prefix, "bin"))
        real = self.real_ensure_jsonschema  # the setUp stub hides the real one
        with (
            unittest.mock.patch.object(
                cli.install.subprocess,
                "run",
                return_value=unittest.mock.Mock(returncode=0),
            ) as check,
            unittest.mock.patch.object(cli.install.subprocess, "call") as call,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            real("conda", prefix, "pastforward")
        call.assert_not_called()
        self.assertIn("import jsonschema", check.call_args[0][0])
        with (
            unittest.mock.patch.object(
                cli.install.subprocess,
                "run",
                return_value=unittest.mock.Mock(returncode=1),
            ),
            unittest.mock.patch.object(
                cli.install.subprocess, "call", return_value=0
            ) as call,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            real("conda", prefix, "pastforward")
        self.assertEqual(call.call_args[0][0][-1], "jsonschema")

    def test_parse_version(self):
        self.assertEqual(cli.install._parse_version("conda 24.7.1\n"), (24, 7, 1))
        self.assertEqual(cli.install._parse_version("9.26"), (9, 26, 0))
        self.assertIsNone(cli.install._parse_version(""))

    def test_env_prefix_matches_folder_name_only(self):
        listing = json.dumps(
            {
                "envs": [
                    "/opt/miniforge3",
                    "/opt/miniforge3/envs/snakemake_old",
                    "/opt/miniforge3/envs/snakemake",
                ]
            }
        )
        with unittest.mock.patch.object(
            cli.install.subprocess,
            "run",
            return_value=unittest.mock.Mock(stdout=listing),
        ):
            self.assertEqual(
                cli.install._env_prefix("conda", "snakemake"),
                "/opt/miniforge3/envs/snakemake",
            )
            self.assertIsNone(cli.install._env_prefix("conda", "reveal"))

    def test_no_conda_points_to_miniforge(self):
        with (
            unittest.mock.patch.object(cli.install, "_conda_exe", return_value=None),
            self.assertRaises(SystemExit) as cm,
        ):
            cli.main(["install"])
        self.assertIn("Miniforge", str(cm.exception.code))

    def test_missing_env_is_created(self):
        prefix = os.path.join(self.project_dir, "envs", "pastforward")
        os.makedirs(os.path.join(prefix, "bin"))
        Path(prefix, "bin", "snakemake").touch()
        lookups = {"snakemake": [None], "pastforward": [None, prefix]}
        with (
            unittest.mock.patch.object(
                cli.install,
                "_env_prefix",
                side_effect=lambda conda, name: lookups[name].pop(0),
            ),
            unittest.mock.patch.object(
                cli.install, "_tool_version", return_value=(9, 26, 1)
            ),
            unittest.mock.patch.object(
                cli.install.subprocess, "call", return_value=0
            ) as call,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                cli.install._snakemake_exe("conda"),
                os.path.join(prefix, "bin", "snakemake"),
            )
        self.assertEqual(
            call.call_args[0][0][:5], ["conda", "create", "-y", "-n", "pastforward"]
        )
        self.assertEqual(call.call_args[0][0][-1], "snakemake>=9.26.1")

    def test_new_enough_snakemake_env_is_reused(self):
        prefix = os.path.join(self.project_dir, "envs", "snakemake")
        os.makedirs(os.path.join(prefix, "bin"))
        Path(prefix, "bin", "snakemake").touch()
        with (
            unittest.mock.patch.object(
                cli.install,
                "_env_prefix",
                side_effect=lambda conda, name: prefix if name == "snakemake" else None,
            ),
            unittest.mock.patch.object(
                cli.install, "_tool_version", return_value=(9, 26, 1)
            ),
            unittest.mock.patch.object(cli.install.subprocess, "call") as call,
        ):
            self.assertEqual(
                cli.install._snakemake_exe("conda"),
                os.path.join(prefix, "bin", "snakemake"),
            )
        call.assert_not_called()

    def test_too_old_snakemake_env_is_left_alone(self):
        old_prefix = os.path.join(self.project_dir, "envs", "snakemake")
        new_prefix = os.path.join(self.project_dir, "envs", "pastforward")
        for prefix in (old_prefix, new_prefix):
            os.makedirs(os.path.join(prefix, "bin"))
            Path(prefix, "bin", "snakemake").touch()
        lookups = {"snakemake": [old_prefix], "pastforward": [None, new_prefix]}
        versions = iter([(9, 9, 0), (9, 26, 1)])
        with (
            unittest.mock.patch.object(
                cli.install,
                "_env_prefix",
                side_effect=lambda conda, name: lookups[name].pop(0),
            ),
            unittest.mock.patch.object(
                cli.install, "_tool_version", side_effect=lambda *a: next(versions)
            ),
            unittest.mock.patch.object(
                cli.install.subprocess, "call", return_value=0
            ) as call,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                cli.install._snakemake_exe("conda"),
                os.path.join(new_prefix, "bin", "snakemake"),
            )
        self.assertEqual(call.call_count, 1)
        self.assertEqual(
            call.call_args[0][0][:5], ["conda", "create", "-y", "-n", "pastforward"]
        )

    def test_too_old_env_is_upgraded(self):
        prefix = os.path.join(self.project_dir, "envs", "pastforward")
        os.makedirs(os.path.join(prefix, "bin"))
        Path(prefix, "bin", "snakemake").touch()
        versions = iter([(9, 9, 0), (9, 26, 1)])
        with (
            unittest.mock.patch.object(cli.install, "_env_prefix", return_value=prefix),
            unittest.mock.patch.object(
                cli.install, "_tool_version", side_effect=lambda *a: next(versions)
            ),
            unittest.mock.patch.object(
                cli.install.subprocess, "call", return_value=0
            ) as call,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                cli.install._snakemake_exe("conda"),
                os.path.join(prefix, "bin", "snakemake"),
            )
        self.assertEqual(
            call.call_args[0][0][:5], ["conda", "install", "-y", "-n", "pastforward"]
        )

    def test_failed_upgrade_stops(self):
        prefix = os.path.join(self.project_dir, "envs", "pastforward")
        os.makedirs(os.path.join(prefix, "bin"))
        Path(prefix, "bin", "snakemake").touch()
        with (
            unittest.mock.patch.object(cli.install, "_env_prefix", return_value=prefix),
            unittest.mock.patch.object(
                cli.install, "_tool_version", return_value=(9, 9, 0)
            ),
            unittest.mock.patch.object(cli.install.subprocess, "call", return_value=1),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            cli.install._snakemake_exe("conda")
        self.assertIn("could not get snakemake>=9.26.1", str(cm.exception.code))

    def test_without_config_stops_before_building_tools(self):
        with (
            unittest.mock.patch.object(
                cli.install, "_conda_exe", return_value="/opt/conda/bin/conda"
            ),
            unittest.mock.patch.object(
                cli.install, "_tool_version", return_value=(25, 1, 0)
            ),
            unittest.mock.patch.object(
                cli.install,
                "_snakemake_exe",
                return_value="/opt/conda/envs/pastforward/bin/snakemake",
            ),
            unittest.mock.patch.object(cli.install.subprocess, "call") as call,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            cli.main(["install"])
        call.assert_not_called()
        self.assertIn("No config/config.yaml yet", out.getvalue())
        self.assertIn(
            "cp config/min_config_sample.yaml config/config.yaml", out.getvalue()
        )
        self.assertIn("tools create-species", out.getvalue())

    def test_with_config_builds_envs_with_snakemake_on_path(self):
        Path("config/config.yaml").touch()
        sm = "/opt/conda/envs/pastforward/bin/snakemake"
        with (
            unittest.mock.patch.object(
                cli.install, "_conda_exe", return_value="/opt/conda/bin/conda"
            ),
            unittest.mock.patch.object(
                cli.install, "_tool_version", return_value=(25, 1, 0)
            ),
            unittest.mock.patch.object(cli.install, "_snakemake_exe", return_value=sm),
            unittest.mock.patch.object(
                cli.install.subprocess, "call", return_value=0
            ) as call,
            contextlib.redirect_stdout(io.StringIO()) as out,
            self.assertRaises(SystemExit) as cm,
        ):
            cli.main(["install", "--conda-prefix", "/x"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("Next steps:", out.getvalue())
        self.assertIn("conda activate pastforward", out.getvalue())
        self.assertIn("./pastForward run --cores <N>", out.getvalue())
        cmd = call.call_args[0][0]
        self.assertEqual(cmd[0], sm)
        self.assertIn("--conda-create-envs-only", cmd)
        self.assertEqual(cmd[-2:], ["--conda-prefix", "/x"])
        self.assertTrue(
            call.call_args[1]["env"]["PATH"].startswith(
                "/opt/conda/envs/pastforward/bin" + os.pathsep
            )
        )


class MainDispatchTestCase(unittest.TestCase):
    def test_unknown_command_suggests_the_closest_one(self):
        with (
            contextlib.redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit),
        ):
            cli.main(["stauts"])
        self.assertIn("Did you mean `status`?", err.getvalue())

    def test_help_after_a_command_shows_only_that_command(self):
        # Must not reach cmd_run, which would die on the missing --cores.
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.main(["run", "--help"])
            cli.main(["check", "-h"])
        self.assertIn("--cores <N>", out.getvalue())
        self.assertIn("check [--configfile", out.getvalue())
        self.assertNotIn("print-log", out.getvalue())


class _FakeTty(io.StringIO):
    def isatty(self):
        return True


class QuipsTestCase(unittest.TestCase):
    def test_every_quip_used_in_the_cli_exists(self):
        import re

        # Every quoted word on a line that calls _quip(...) or passes quip=... to _die().
        used = set()
        for path in Path(REPO_ROOT, "workflow/scripts/cli").glob("*.py"):
            for line in path.read_text().splitlines():
                if "_quip(" in line or "quip=" in line:
                    used |= set(re.findall(r'"(\w+)"', line))
        self.assertGreater(len(used), 10)
        self.assertEqual(used - set(cli.common.QUIPS), set())

    def test_quip_prints_one_of_the_pool_on_a_terminal(self):
        out = _FakeTty()
        with unittest.mock.patch.dict(os.environ, {"PASTFORWARD_QUIET": ""}):
            cli.common._quip("unlock", out)
        self.assertIn(out.getvalue().strip(), cli.common.QUIPS["unlock"])

    def test_quip_is_stable_for_a_seed(self):
        picks = set()
        for _ in range(10):
            out = _FakeTty()
            with unittest.mock.patch.dict(os.environ, {"PASTFORWARD_QUIET": ""}):
                cli.common._quip("done", out, seed=1234)
            picks.add(out.getvalue())
        self.assertEqual(len(picks), 1)

    def test_quip_silent_when_quiet_or_not_a_terminal(self):
        out = _FakeTty()
        with unittest.mock.patch.dict(os.environ, {"PASTFORWARD_QUIET": "1"}):
            cli.common._quip("unlock", out)
        self.assertEqual(out.getvalue(), "")
        plain = io.StringIO()
        cli.common._quip("unlock", plain)
        self.assertEqual(plain.getvalue(), "")

    def test_ctrl_c_in_foreground_run_logs_shutdown_and_hints_resume(self):
        class FakeProc:
            def __init__(self, *a, **k):
                lines = iter(["Job started\n", None, "Shutting down\n"])

                class Out:
                    def __iter__(self):
                        return self

                    def __next__(self):
                        line = next(lines)
                        if line is None:
                            raise KeyboardInterrupt
                        return line

                self.stdout = Out()

            def wait(self):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "run.log")
            with (
                unittest.mock.patch("subprocess.Popen", FakeProc),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()) as err,
            ):
                code = cli.run._run_foreground(["snakemake"], log, resumable=True)
            self.assertEqual(code, 130)
            self.assertEqual(log.read_text(), "Job started\nShutting down\n")
        self.assertIn("Interrupted.", err.getvalue())
        self.assertIn("./pastForward resume", err.getvalue())

    def test_die_with_quip_still_exits_1(self):
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as ctx,
        ):
            cli.common._die("boom", quip="typo")
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

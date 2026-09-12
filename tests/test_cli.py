#!/usr/bin/env python3
"""
Unit tests for workflow/scripts/cli.py (the `pastForward` CLI's command building and log
parsing). Pure Python, no Snakemake/conda required. Run with either:
    python3 tests/test_cli.py
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
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "workflow"))

import scripts.cli as cli  # noqa: E402


class BuildCmdTestCase(unittest.TestCase):
    def test_run_cmd_adds_defaults(self):
        cmd = cli._build_run_cmd(["--cores", "8"])
        self.assertEqual(
            cmd,
            ["snakemake", "--use-conda", "--keep-going", "--rerun-trigger", "mtime", "--cores", "8"],
        )

    def test_run_cmd_does_not_duplicate_user_supplied_flags(self):
        cmd = cli._build_run_cmd(["--use-conda", "--cores", "4", "--forceall", "count_reads_raw"])
        self.assertEqual(cmd.count("--use-conda"), 1)
        self.assertEqual(cmd.count("--cores"), 1)
        self.assertIn("--forceall", cmd)
        self.assertIn("count_reads_raw", cmd)

    def test_dryrun_cmd_defaults_cores(self):
        cmd = cli._build_dryrun_cmd([])
        self.assertEqual(
            cmd,
            ["snakemake", "--use-conda", "--keep-going", "--rerun-trigger", "mtime", "--cores", "1", "--dryrun"],
        )

    def test_dryrun_cmd_respects_user_cores(self):
        cmd = cli._build_dryrun_cmd(["-j", "8"])
        self.assertEqual(
            cmd,
            ["snakemake", "--use-conda", "--keep-going", "--rerun-trigger", "mtime", "-j", "8", "--dryrun"],
        )

    def test_dryrun_cmd_uses_same_rerun_trigger_as_run(self):
        # A dry run must predict what `run` does. Without --rerun-trigger mtime, Snakemake
        # falls back to its full default trigger set and reports reruns (e.g. "Code has
        # changed since last execution") that the real run would never perform.
        dryrun = cli._build_dryrun_cmd(["--cores", "8"])
        run = cli._build_run_cmd(["--cores", "8"])
        self.assertEqual([a for a in dryrun if a != "--dryrun"], run)

    def test_dryrun_cmd_does_not_duplicate_user_supplied_flags(self):
        cmd = cli._build_dryrun_cmd(["--rerun-trigger", "code", "--cores", "4"])
        self.assertEqual(cmd.count("--rerun-trigger"), 1)
        self.assertNotIn("mtime", cmd)

    def test_touch_cmd_defaults_cores_and_skips_conda(self):
        # --use-conda would make Snakemake build every rule's environment before touching
        # anything, which a touch has no use for.
        cmd = cli._build_touch_cmd([])
        self.assertEqual(cmd, ["snakemake", "--rerun-trigger", "mtime", "--cores", "1", "--touch"])

    def test_touch_cmd_passes_user_flags_through(self):
        cmd = cli._build_touch_cmd(["--cores", "4", "--forcerun", "count_reads_raw"])
        self.assertEqual(
            cmd,
            ["snakemake", "--rerun-trigger", "mtime", "--cores", "4", "--forcerun", "count_reads_raw", "--touch"],
        )


class StatusHelpersTestCase(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(cli._format_duration(5), "5s")
        self.assertEqual(cli._format_duration(65), "1m 5s")
        self.assertEqual(cli._format_duration(3661), "1h 1m 1s")
        self.assertEqual(cli._format_duration(90000), "1d 1h 0m 0s")

    def test_cores_from_cmd(self):
        self.assertEqual(cli._cores_from_cmd(["snakemake", "--use-conda", "--cores", "8", "--forceall"]), "8")
        self.assertEqual(cli._cores_from_cmd(["snakemake", "-j", "all"]), "all")
        self.assertIsNone(cli._cores_from_cmd(["snakemake"]))

    def test_configfile_from_cmd(self):
        self.assertEqual(
            cli._configfile_from_cmd(["snakemake", "--configfile", "other.yaml"]), "other.yaml"
        )
        self.assertEqual(cli._configfile_from_cmd(["snakemake", "--cores", "4"]), cli.DEFAULT_CONFIGFILE)

    def test_read_project_name(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.yaml")
            with open(cfg, "w") as f:
                f.write('project_name: "Demo Project"\n')
            self.assertEqual(cli._read_project_name(cfg), "Demo Project")
            self.assertIsNone(cli._read_project_name(os.path.join(d, "missing.yaml")))

    def test_progress_bar(self):
        bar = cli._progress_bar(50.0, width=10)
        self.assertIn("50.0%", bar)
        self.assertIn("#####", bar)
        full = cli._progress_bar(100.0, width=10)
        self.assertIn("100.0%", full)

    def test_job_log_paths_extracts_single_and_multiple(self):
        block = (
            "Error in rule fastqc:\n"
            "    jobid: 3\n"
            "    log: logs/fastqc/sample.log (check log file(s) for error message)\n"
        )
        self.assertEqual(cli._job_log_paths(block), ["logs/fastqc/sample.log"])

        multi_block = "Error in rule merge:\n    log: a.log, b.log (check log file(s) for error message)\n"
        self.assertEqual(cli._job_log_paths(multi_block), ["a.log", "b.log"])

        no_log_block = "Error in rule foo:\n    jobid: 1\n"
        self.assertEqual(cli._job_log_paths(no_log_block), [])

    def test_job_log_paths_handles_details_wording(self):
        # Newer Snakemake versions say "for error details" instead of "for error message" -
        # the suffix must still be stripped rather than captured as part of the path.
        block = (
            "Error in rule normalize_visualization_of_individual:\n"
            "    jobid: 52\n"
            "    log: demo/results/Dmel1959_coverage.normalized.log (check log file(s) for error details)\n"
        )
        self.assertEqual(cli._job_log_paths(block), ["demo/results/Dmel1959_coverage.normalized.log"])


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
        os.chdir(self.project_dir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_run_without_cores_exits_before_spawning_anything(self):
        with self.assertRaises(SystemExit):
            cli.cmd_run(["--forceall"])
        self.assertFalse(cli.STATE_FILE.exists())

    def test_resume_without_cores_exits_before_spawning_anything(self):
        with self.assertRaises(SystemExit):
            cli.cmd_resume(["--forceall"])
        self.assertFalse(cli.STATE_FILE.exists())

    def test_resume_adds_rerun_incomplete(self):
        # cmd_resume only differs from cmd_run by this flag - confirm it lands in the built
        # command rather than actually spawning snakemake.
        captured = {}
        orig = cli._run_background
        cli._run_background = lambda cmd, log_path: captured.setdefault("cmd", cmd)
        try:
            cli.cmd_resume(["--cores", "4"])
        finally:
            cli._run_background = orig
        self.assertIn("--rerun-incomplete", captured["cmd"])

    def test_run_refuses_when_a_tracked_run_is_still_alive(self):
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.STATE_FILE.write_text(json.dumps({"pid": os.getpid()}))
        with self.assertRaises(SystemExit):
            cli.cmd_run(["--cores", "4"])

    def test_unlock_rejects_arguments(self):
        with self.assertRaises(SystemExit):
            cli.cmd_unlock(["--foo"])

    def test_unlock_passes_cores_one(self):
        # snakemake >= 9.9 requires --cores even for --unlock.
        captured = {}
        orig = cli.subprocess.call
        cli.subprocess.call = lambda cmd: captured.setdefault("cmd", cmd) or 0
        try:
            with self.assertRaises(SystemExit):
                cli.cmd_unlock([])
        finally:
            cli.subprocess.call = orig
        self.assertEqual(captured["cmd"], ["snakemake", "--unlock", "--cores", "1"])

    def test_check_rejects_arguments(self):
        # check/preview always read config/config.yaml as-is - there is no Snakemake
        # invocation left to forward flags to.
        with self.assertRaises(SystemExit):
            cli.cmd_check(["--configfile", "other.yaml"])

    def test_preview_rejects_arguments(self):
        with self.assertRaises(SystemExit):
            cli.cmd_preview(["some_target"])

    def test_status_rejects_unknown_arguments(self):
        # --live/--tail moved to `print-log` - status must reject them, not silently ignore.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(cli.LOG_DIR / "run_missing.log"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with self.assertRaises(SystemExit):
            cli.cmd_status(["--live"])

    def test_status_headline_shows_project_and_config(self):
        with open(os.path.join("config", "config.yaml"), "w") as f:
            f.write('project_name: "Demo Project"\n')
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        cli.STATE_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "cmd": ["snakemake", "--cores", "4"],
                    "log_file": str(cli.LOG_DIR / "run_missing.log"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.cmd_status([])
        output = out.getvalue()
        self.assertIn("Demo Project", output)
        self.assertIn("config/config.yaml", output)

    def test_status_shows_progress_bar(self):
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        log_path = cli.LOG_DIR / "run_progress.log"
        log_path.write_text("5 of 10 steps (50.0%) done\n")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        output = out.getvalue()
        self.assertIn("50.0%", output)
        self.assertIn("[", output)

    def test_status_last_finished_and_running_labels_say_jobs(self):
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        log_path = cli.LOG_DIR / "run_jobs.log"
        log_path.write_text("")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        output = out.getvalue()
        self.assertIn("Last finished jobs", output)
        self.assertIn("Currently running jobs", output)

    def test_watch_passes_tail_lines_to_print_status(self):
        # Stub both the terminal clear and _print_status: exercise cmd_status's watch wiring
        # without actually clearing the real terminal or looping forever.
        calls = []

        def fake_print_status(tail=None):
            calls.append(tail)
            return False  # not alive -> loop exits after one iteration

        orig_print_status = cli._print_status
        orig_system = cli.os.system
        cli._print_status = fake_print_status
        cli.os.system = lambda *_: None
        try:
            cli.cmd_status(["--watch"])
        finally:
            cli._print_status = orig_print_status
            cli.os.system = orig_system
        self.assertEqual(calls, [cli.WATCH_TAIL_LINES])

    def test_print_log_tail_shows_only_last_n_lines(self):
        os.makedirs(cli.LOG_DIR)
        log = cli.LOG_DIR / "run_tail.log"
        log.write_text("\n".join(f"line{i}" for i in range(30)) + "\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.cmd_print_log(["--tail", "3"])
        output = out.getvalue()
        self.assertIn("line29", output)
        self.assertNotIn("line26", output)

    def test_print_log_tail_without_number_defaults(self):
        os.makedirs(cli.LOG_DIR)
        log = cli.LOG_DIR / "run_tail_default.log"
        log.write_text("\n".join(f"l{i}" for i in range(30)) + "\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.cmd_print_log(["--tail"])
        output = out.getvalue()
        self.assertIn("l29", output)
        self.assertNotIn("l9\n", output)

    def test_print_log_live_uses_tail_dash_f(self):
        os.makedirs(cli.LOG_DIR)
        log = cli.LOG_DIR / "run_live.log"
        log.write_text("hello\n")
        captured = {}
        orig = cli.subprocess.run
        cli.subprocess.run = lambda cmd, **kw: captured.setdefault("cmd", cmd)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                cli.cmd_print_log(["--live"])
        finally:
            cli.subprocess.run = orig
        self.assertIn("-f", captured["cmd"])
        self.assertIn(str(log), captured["cmd"])

    def test_status_flags_force_kill_when_dead_without_failure_or_completion(self):
        # Process not running, log has partial progress and no "did not complete successfully"
        # marker (Snakemake never got to log a reason) - most likely a force-kill.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_path = cli.LOG_DIR / "run_forcekilled.log"
        os.makedirs(cli.LOG_DIR)
        log_path.write_text("31 of 210 steps (15%) done\n")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        self.assertIn("Interrupted", out.getvalue())

    def test_status_not_interrupted_when_nothing_to_be_done(self):
        # Process not running, log has no progress line at all because the DAG's targets were
        # already present and up to date - Snakemake's normal no-op success, must not be
        # misread as a force-kill just because there's no "100%" line to match.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        log_path = cli.LOG_DIR / "run_nothing_to_do.log"
        log_path.write_text("Nothing to be done (all requested files are present and up to date).\n")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        self.assertNotIn("Interrupted", out.getvalue())

    def test_status_reports_dry_run_instead_of_force_kill(self):
        # `run`/`resume` pass unknown snakemake flags through, so `run --cores N -n` is tracked
        # in the state file like a real run. A dry run executes nothing and exits in seconds, so
        # it has no progress line and no failure marker - it must not be reported as a force-kill.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        log_path = cli.LOG_DIR / "run_dryrun.log"
        log_path.write_text("This was a dry-run (flag -n). The order of jobs does not reflect the order of execution.\n")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        output = out.getvalue()
        self.assertNotIn("Interrupted", output)
        self.assertNotIn("Resume with", output)
        self.assertIn("dry run", output)

    def test_status_flags_lock_exception(self):
        # Process not running, log has a LockException (stale lock from a killed run or
        # power loss) - must be reported as "Locked", not misread as a force-kill.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        log_path = cli.LOG_DIR / "run_locked.log"
        os.makedirs(cli.LOG_DIR)
        log_path.write_text(
            "[2026-08-16 12:49:14 (CEST)] [ERROR] LockException:\n"
            "Error: Directory cannot be locked. Please make sure that no other Snakemake "
            "process is trying to create the same files in the following directory:\n"
            "/mnt/data5/sarah/snakemake_demo_pipelines/demo_adna_pipeline\n"
        )
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        output = out.getvalue()
        self.assertIn("Locked", output)
        self.assertIn("pastForward unlock", output)
        self.assertNotIn("Interrupted", output)

    def test_status_hides_job_lists_when_process_is_dead(self):
        # Process finished (not running anymore) - "Last finished jobs"/"Currently running
        # jobs" describe live progress and are meaningless once the run has stopped.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        log_path = cli.LOG_DIR / "run_finished.log"
        log_path.write_text("210 of 210 steps (100.0%) done\n")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        output = out.getvalue()
        self.assertNotIn("Last finished jobs", output)
        self.assertNotIn("Currently running jobs", output)

    def test_status_not_interrupted_when_progress_percent_has_no_decimal(self):
        # Snakemake only prints a decimal for non-round percentages, so a clean 100% finish
        # can log "(100%)" instead of "(100.0%)" - must not be misread as a force-kill.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        log_path = cli.LOG_DIR / "run_finished_no_decimal.log"
        log_path.write_text("177 of 177 steps (100%) done\nWorkflow finished, no error\n")
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        self.assertNotIn("Interrupted", out.getvalue())

    def test_status_prints_tail_of_failed_job_log(self):
        # On a dead+failed run, status should surface the actual error message from each
        # failed job's own log file - not just Snakemake's "check log file(s)" pointer.
        cli.STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.makedirs(cli.LOG_DIR)
        main_log = cli.LOG_DIR / "run_failed.log"
        job_log = cli.LOG_DIR / "bwa_mem2_sample.log"
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
        cli.STATE_FILE.write_text(
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
            cli.cmd_status([])
        output = out.getvalue()
        self.assertIn("index file not found", output)
        self.assertIn(str(job_log), output)

    def test_print_log_rejects_arguments(self):
        with self.assertRaises(SystemExit):
            cli.cmd_print_log(["--foo"])

    def test_print_log_dies_without_logs_dir(self):
        with self.assertRaises(SystemExit):
            cli.cmd_print_log([])

    def test_print_log_prints_most_recently_modified_file(self):
        os.makedirs(cli.LOG_DIR)
        old = cli.LOG_DIR / "dryrun_20260101_000000.log"
        new = cli.LOG_DIR / "run_20260101_000001.log"
        old.write_text("old log\n")
        new.write_text("new log\n")
        os.utime(old, (1, 1))
        os.utime(new, (2, 2))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cli.cmd_print_log([])
        self.assertIn("new log", out.getvalue())
        self.assertNotIn("old log", out.getvalue())


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
        for m in cli.PROGRESS_RE.finditer(self.LOG):
            pass
        self.assertEqual(m.groups(), ("3", "10", "30"))

    def test_last_steps_status(self):
        finished, running = cli._parse_last_steps(self.LOG)
        self.assertEqual(finished, [("fastqc", "3")])
        self.assertEqual(running, [("map_reads_to_reference_bwa_mem2", "7")])

    def test_last_steps_caps_at_n(self):
        many = "\n".join(
            f"[2026-08-16 10:00:00 (CEST)] [INFO]  Rule: r{i}, Jobid: {i}\n"
            f"[2026-08-16 10:00:01 (CEST)] [INFO] Finished jobid: {i} (Rule: r{i})"
            for i in range(8)
        )
        finished, running = cli._parse_last_steps(many, n=5)
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
        m = cli.DETECTED_SPECIES_RE.search(self.LOG)
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

        skipped_species = re.findall(r"Skipping species '(.+?)' \(execute: false\)", self.LOG)
        existing = re.findall(r"- Skipping: (.+)", self.LOG)
        requested = re.findall(r"- Requesting: (.+)", self.LOG)
        self.assertEqual(skipped_species, ["OtherSpecies"])
        self.assertEqual(existing, ["TestSpecies/results/read_module/reads_merged/IND001.fastq.gz"])
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

        real_run = cli.subprocess.run
        cli.subprocess.run = lambda *a, **kw: FakeProc()
        try:
            envs = cli._list_conda_envs()
        finally:
            cli.subprocess.run = real_run
        self.assertEqual(
            [e["location"] for e in envs],
            [".snakemake/conda/3f83c79_", ".snakemake/conda/2844fb9_", ".snakemake/conda/1c817e9_"],
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
            "input_size_mb": {"in.bam": input_size_mb} if input_size_mb is not None else {},
        }

    def test_benchmark_number_treats_na_as_missing(self):
        # Snakemake writes "NA", not 0, for anything it could not sample - reporting it as 0 MB
        # would read as "this rule needs no memory", which is the opposite of the truth.
        self.assertIsNone(cli._benchmark_number("NA"))
        self.assertIsNone(cli._benchmark_number(None))
        self.assertIsNone(cli._benchmark_number("-"))
        self.assertEqual(cli._benchmark_number(12), 12.0)
        self.assertEqual(cli._benchmark_number("3.5"), 3.5)

    def test_summarize_groups_per_rule_and_sorts_by_core_hours(self):
        records = [
            self._record("slow_rule", 3600, max_rss=1000, threads=4),
            self._record("slow_rule", 1800, max_rss=2000, threads=4),
            self._record("quick_rule", 10, max_rss=50, threads=1),
        ]
        rows = cli._summarize_benchmarks(records)
        self.assertEqual([row["rule"] for row in rows], ["slow_rule", "quick_rule"])
        slow = rows[0]
        self.assertEqual(slow["jobs"], 2)
        self.assertEqual(slow["median_s"], 2700)
        self.assertEqual(slow["max_s"], 3600)
        self.assertEqual(slow["max_rss_mb"], 2000)
        self.assertAlmostEqual(slow["core_hours"], (3600 * 4 + 1800 * 4) / 3600)

    def test_summarize_reports_no_memory_rather_than_zero(self):
        rows = cli._summarize_benchmarks([self._record("mac_rule", 42)])
        self.assertIsNone(rows[0]["max_rss_mb"])
        self.assertEqual(rows[0]["max_s"], 42)

    def test_summarize_takes_largest_total_input_size(self):
        records = [
            self._record("map", 10, input_size_mb=100),
            self._record("map", 10, input_size_mb=250),
        ]
        self.assertEqual(cli._summarize_benchmarks(records)[0]["max_input_mb"], 250)

    def test_summarize_labels_records_without_a_rule_name(self):
        # Pre-extended-format files (or a run where benchmark.smk could not switch the extended
        # format on) have no rule_name at all. They must not be dropped silently.
        rows = cli._summarize_benchmarks([{"s": 5, "max_rss": "NA"}])
        self.assertEqual(rows[0]["rule"], "(unknown rule)")

    def test_emit_profile_skips_mem_mb_when_memory_was_never_measured(self):
        rows = cli._summarize_benchmarks(
            [self._record("measured", 60, max_rss=1000), self._record("wall_time_only", 60)]
        )
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli._emit_benchmark_profile(rows)
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
        found = [os.path.basename(p) for p in cli._find_benchmark_files()]
        self.assertEqual(found, ["IND001_sorted.benchmark.jsonl", "Dmel_multiqc.benchmark.jsonl"])

    def test_skips_the_pipeline_code_and_dot_directories(self):
        # .snakemake holds its own copies of a lot of things, and workflow/ is pipeline code that
        # travels between machines - neither ever holds a benchmark belonging to this project.
        self._touch("workflow/rules/leftover.benchmark.jsonl")
        self._touch(".snakemake/leftover.benchmark.jsonl")
        self.assertEqual(cli._find_benchmark_files(), [])

    def test_follows_a_symlinked_processed_directory(self):
        # species_paths.py turns a configured processed_dir/results_dir into a symlink at the
        # conventional in-project path, so every benchmark file can sit behind one.
        external = os.path.join(self.project_dir, "external_store")
        os.makedirs(external)
        open(os.path.join(external, "IND001.benchmark.jsonl"), "w").close()
        os.makedirs(os.path.join(self.project_dir, "Dmel"))
        os.symlink(external, os.path.join(self.project_dir, "Dmel/processed"))
        found = cli._find_benchmark_files("Dmel")
        self.assertEqual([os.path.basename(p) for p in found], ["IND001.benchmark.jsonl"])

    def test_survives_a_symlink_cycle(self):
        # Following symlinks means a loop is possible; it must not hang the command.
        os.makedirs(os.path.join(self.project_dir, "Dmel/processed"))
        os.symlink(os.path.join(self.project_dir, "Dmel"), os.path.join(self.project_dir, "Dmel/processed/loop"))
        self._touch("Dmel/processed/IND001.benchmark.jsonl")
        self.assertEqual(len(cli._find_benchmark_files()), 1)

    def test_benchmark_command_explains_an_empty_project(self):
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        with self.assertRaises(SystemExit) as caught:
            cli.cmd_benchmark([])
        self.assertIn("no", str(caught.exception).lower())

    def test_benchmark_command_rejects_unknown_arguments(self):
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        with self.assertRaises(SystemExit):
            cli.cmd_benchmark(["--emit-profile", "--nonsense"])

    def test_benchmark_command_skips_unreadable_files_instead_of_failing(self):
        os.makedirs(os.path.join(self.project_dir, "workflow"))
        os.makedirs(os.path.join(self.project_dir, "config"))
        good = self._touch("Dmel/processed/good.benchmark.jsonl")
        Path(good).write_text(json.dumps({"s": 3, "max_rss": 10, "threads": 1, "rule_name": "good"}) + "\n")
        Path(self._touch("Dmel/processed/bad.benchmark.jsonl")).write_text("{not json\n")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.cmd_benchmark([])
        self.assertIn("good", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

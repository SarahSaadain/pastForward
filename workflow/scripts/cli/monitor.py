"""status, abort, print-log: watching and stopping a run, and reading its logs."""
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .common import (
    ABORTING_RE,
    CONFIGFILE_FLAGS,
    CORES_FLAGS,
    CYAN,
    DEFAULT_CONFIGFILE,
    DIM,
    DRYRUN_FLAGS,
    GREEN,
    LOG_DIR,
    RED,
    SNAKEMAKE_LINE_RULES,
    STATE_FILE,
    YELLOW,
    _color,
    _colorize,
    _die,
    _ensure_project_root,
    _format_duration,
    _is_alive,
)


DEFAULT_TAIL_LINES = 20
WATCH_TAIL_LINES = 10
FAILED_JOB_LOG_TAIL_LINES = 20


PROGRESS_RE = re.compile(r"(\d+) of (\d+) steps \(([\d.]+)%\) done")
# Both lines below come from Snakemake's own per-job log records (jobs.py Job.log_info /
# scheduling/job_scheduler.py), duplicated onto stdout by initialize.smk's root
# logging.basicConfig - unlike the "rule X:" block Snakemake also prints, these two are
# emitted for every job regardless of whether the rule has a `message:` directive.
JOB_STARTED_RE = re.compile(r"^\[.*?\]\s*\[INFO\]\s+Rule:\s*(\S+),\s*Jobid:\s*(\d+)\s*$", re.MULTILINE)
JOB_FINISHED_RE = re.compile(r"Finished jobid:\s*(\d+)\s*\(Rule:\s*(\S+)\)")


FAILED_RE = re.compile(r"At least one job did not complete successfully\.")
LOCK_RE = re.compile(r"LockException")
# Printed instead of a "N of N steps" progress line when the DAG's targets were already all
# present and up to date - a legitimate no-op success, not a sign the run never started.
NOTHING_TO_DO_RE = re.compile(r"^Nothing to be done \(all requested files are present and up to date\)\.", re.MULTILINE)
PROJECT_NAME_RE = re.compile(r'^project_name:\s*["\']?([^"\'\n]+?)["\']?\s*$', re.MULTILINE)
JOB_ERROR_BLOCK_RE = re.compile(r"^Error in rule \S+:\n(?:[ \t]+.*\n?)*", re.MULTILINE)
# The `log:` line Snakemake prints inside an "Error in rule" block - points at the rule's own
# log file (from its `log:` directive), which holds the actual command output/error message.
# That's distinct from the main pipeline log (LOG_DIR/*.log) this module otherwise parses -
# the "Error in rule" block itself only ever says "check log file(s) for error <message/details>".
# The exact wording has changed across Snakemake versions (seen: "message", "details"), so match
# either rather than hardcoding one - a mismatch here means the suffix gets captured as part of
# the path instead of stripped, breaking the tail-the-failed-log lookup.
JOB_LOG_PATH_RE = re.compile(r"^\s*log:\s*(.+?)(?:\s*\(check log file\(s\) for error \w+\))?\s*$", re.MULTILINE)


def _read_state():
    if not STATE_FILE.exists():
        _die("pastForward: no tracked run in this directory (start one with `./pastForward run`).")
    return json.loads(STATE_FILE.read_text())


def _parse_last_steps(text, n=5):
    """Returns (finished, running): the last n jobs to finish (ordered by finish time) and
    every job that has started but not finished (order irrelevant - typically several run
    concurrently under --cores). Each entry is (rule_name, jobid)."""
    started = {jobid: rule for rule, jobid in JOB_STARTED_RE.findall(text)}
    # Every finish is logged twice (root-propagated line + Snakemake's own block-style line);
    # setdefault keeps the first occurrence so ordering still reflects finish time.
    finished_seen = {}
    for jobid, rule in JOB_FINISHED_RE.findall(text):
        finished_seen.setdefault(jobid, rule)
    finished = [(rule, jobid) for jobid, rule in finished_seen.items()]
    finished_ids = set(finished_seen)
    running = [(rule, jobid) for jobid, rule in started.items() if jobid not in finished_ids]
    return finished[-n:], running


def _parse_job_errors(text, n=3):
    # Dedupe by rule name, keeping each rule's last (i.e. most recent) failure block.
    by_rule = {}
    for block in JOB_ERROR_BLOCK_RE.findall(text):
        by_rule[block.splitlines()[0]] = block.rstrip("\n")
    return list(by_rule.values())[-n:]


def _job_log_paths(error_block):
    """Log file path(s) declared on an "Error in rule" block's own `log:` line - a rule can
    declare more than one, comma-separated."""
    m = JOB_LOG_PATH_RE.search(error_block)
    if not m:
        return []
    return [p.strip() for p in m.group(1).split(",") if p.strip()]


def _print_failed_job_log(path, tail=FAILED_JOB_LOG_TAIL_LINES):
    p = Path(path)
    print(_color(DIM, f"    --- tail -n {tail} {path} ---"))
    if not p.exists():
        print(_color(DIM, "    (log file not found)"))
        return
    lines = p.read_text(errors="replace").splitlines()[-tail:]
    for line in lines:
        print(f"    {_colorize(line, SNAKEMAKE_LINE_RULES)}")


def _cores_from_cmd(cmd):
    for i, a in enumerate(cmd):
        if a in CORES_FLAGS and i + 1 < len(cmd):
            return cmd[i + 1]
    return None


def _configfile_from_cmd(cmd):
    for i, a in enumerate(cmd):
        if a in CONFIGFILE_FLAGS and i + 1 < len(cmd):
            return cmd[i + 1]
    return DEFAULT_CONFIGFILE


def _read_project_name(configfile):
    try:
        text = Path(configfile).read_text()
    except OSError:
        return None
    m = PROJECT_NAME_RE.search(text)
    return m.group(1) if m else None


def _progress_bar(percent, width=30):
    filled = round(width * percent / 100)
    bar = "#" * filled + "-" * (width - filled)
    return f"{_color(GREEN if percent >= 100 else CYAN, '[' + bar + ']')} {percent:.1f}%"


def cmd_status(argv):
    watch = any(a in ("--watch", "-w") for a in argv)
    rest = [a for a in argv if a not in ("--watch", "-w")]
    if rest:
        _die(
            f"pastForward status: unknown argument(s): {' '.join(rest)}. "
            "--live/--tail moved to `./pastForward print-log`."
        )
    if watch:
        try:
            while True:
                os.system("clear")
                alive = _print_status(tail=WATCH_TAIL_LINES)
                if not alive:
                    break
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        return
    _print_status()


def _print_log_tail(text, log_path, tail):
    if not tail:
        return
    print(_color(DIM, f"\n--- tail -n {tail} {log_path} ---"))
    for line in text.splitlines()[-tail:]:
        sys.stdout.write(_colorize(line + "\n", SNAKEMAKE_LINE_RULES))


def _print_status(tail=None):
    state = _read_state()
    pid = state["pid"]
    alive = _is_alive(pid)
    started = datetime.fromisoformat(state["started_at"])
    log_path = Path(state["log_file"])
    configfile = _configfile_from_cmd(state["cmd"])
    project_name = _read_project_name(configfile) or _color(DIM, "(unknown)")
    # Once the process has died, "now" no longer reflects its runtime - use the log file's
    # last write instead, so runtime freezes at whenever it actually stopped.
    end = datetime.now() if alive else (
        datetime.fromtimestamp(log_path.stat().st_mtime) if log_path.exists() else started
    )
    runtime = _format_duration((end - started).total_seconds())
    cores = _cores_from_cmd(state["cmd"]) or "?"
    # `run`/`resume` pass unknown flags straight through to Snakemake, so `run --cores N -n`
    # tracks a dry run in the state file. A dry run executes nothing, so none of the progress
    # or exit-classification reporting below applies to it.
    dryrun = any(a in DRYRUN_FLAGS for a in state["cmd"])
    print(f"{_color(CYAN, 'Project:')}   {project_name}")
    print(f"{_color(CYAN, 'Config:')}    {configfile}")
    print(f"{_color(CYAN, 'PID:')}       {pid} ({_color(GREEN, 'running') if alive else _color(RED, 'not running')})")
    print(f"{_color(CYAN, 'Started:')}   {state['started_at']}")
    print(f"{_color(CYAN, 'Runtime:')}   {runtime}")
    print(f"{_color(CYAN, 'Cores:')}     {cores}")
    print(f"{_color(CYAN, 'Log:')}       {state['log_file']}")

    if dryrun:
        print(f"{_color(CYAN, 'Mode:')}      {_color(YELLOW, 'dry run (--dryrun) - no jobs are executed')}")

    if not log_path.exists():
        print(_color(DIM, "(log file not found yet)"))
        return alive
    text = log_path.read_text(errors="replace")

    if dryrun:
        print(_color(DIM, "(dry run in progress)") if alive else _color(GREEN, "Dry run finished. Nothing was executed, so there is nothing to resume."))
        _print_log_tail(text, log_path, tail)
        return alive

    progress = None
    for progress in PROGRESS_RE.finditer(text):
        pass
    progress_str = f"{progress.group(1)}/{progress.group(2)} steps ({progress.group(3)}%)" if progress else _color(DIM, "(not available yet)")
    print(_progress_bar(float(progress.group(3))) if progress else _color(DIM, "[" + "-" * 30 + "] (no progress yet)"))

    if alive and ABORTING_RE.search(text):
        print(_color(YELLOW, "Aborting:   will exit after finishing currently running jobs (scheduler)."))
    elif not alive and FAILED_RE.search(text):
        print(_color(RED, "Failed:     at least one job did not complete successfully."))
        errors = _parse_job_errors(text)
        if errors:
            print(_color(RED, f"\nErrors ({len(errors)}):"))
            for block in errors:
                lines = block.splitlines()
                print(f"  {_color(RED, lines[0])}")
                for line in lines[1:]:
                    print(f"  {_color(DIM, line)}")
                for job_log_path in _job_log_paths(block):
                    _print_failed_job_log(job_log_path)
        print(_color(DIM, "Resume with: ./pastForward resume --cores <N>"))
    elif not alive and LOCK_RE.search(text):
        print(_color(RED, "Locked:     directory is locked (stale lock from a killed run or power loss)."))
        print(_color(DIM, "Fix with: ./pastForward unlock, then ./pastForward resume --cores <N>"))
    elif not alive and (progress is None or float(progress.group(3)) != 100.0) and not NOTHING_TO_DO_RE.search(text):
        # Died before 100% with no "did not complete successfully" marker either - Snakemake
        # never got the chance to log a reason, so this is most likely a force-kill (SIGKILL,
        # `abort --force`, OOM-killer) rather than a graceful failure. Exception: a DAG with
        # nothing left to run prints "Nothing to be done" instead of a progress line at all,
        # which would otherwise look identical to a run that never got going.
        print(_color(YELLOW, "Interrupted: not running, and the log shows neither success nor a recorded failure - likely force-killed (SIGKILL/OOM) rather than a normal error exit."))
        print(_color(DIM, "Resume with: ./pastForward resume --cores <N>"))

    print(f"{_color(CYAN, 'Progress:')}  {progress_str}")

    # Once the process is dead, "currently running" is meaningless and "last finished" is a
    # stale snapshot rather than live progress - the Failed/Locked/Interrupted messaging above
    # (plus the failed-job logs) already covers what matters for a finished run.
    if alive:
        finished, running = _parse_last_steps(text)
        print(_color(CYAN, "Last finished jobs:") if finished else _color(DIM, "Last finished jobs: (none yet)"))
        for rule_name, jobid in finished:
            print(f"  - {rule_name} (jobid {jobid}) [{_color(GREEN, 'done')}]")
        print(_color(CYAN, f"Currently running jobs ({len(running)}):") if running else _color(DIM, "Currently running jobs: (none)"))
        for rule_name, jobid in running:
            print(f"  - {rule_name} (jobid {jobid})")

    _print_log_tail(text, log_path, tail)

    return alive


def cmd_abort(argv):
    state = _read_state()
    pid = state["pid"]
    if not _is_alive(pid):
        _die("pastForward: tracked process is not running.")
    if any(a in ("--force", "-f") for a in argv):
        os.killpg(pid, signal.SIGKILL)
        print(_color(RED, f"Force-killed process group {pid} (main process + subprocesses)."))
    else:
        os.kill(pid, signal.SIGTERM)
        print(_color(YELLOW, f"Sent SIGTERM to PID {pid}. Snakemake will shut its subprocesses down itself."))
        print(_color(DIM, "Use --force (-f) to kill the whole process group immediately instead."))


def cmd_print_log(argv):
    _ensure_project_root(require_snakemake=False)
    live = any(a in ("--live", "-l") for a in argv)
    rest = [a for a in argv if a not in ("--live", "-l")]
    tail_n = None
    if rest[:1] in (["--tail"], ["-t"]):
        rest = rest[1:]
        if rest[:1] and rest[0].isdigit():
            tail_n = int(rest[0])
            rest = rest[1:]
        else:
            tail_n = DEFAULT_TAIL_LINES
    if rest:
        _die(f"pastForward print-log: unknown argument(s): {' '.join(rest)}")
    if not LOG_DIR.is_dir():
        _die("pastForward: no logs/ directory found — run `./pastForward run` or `./pastForward dryrun` first.")
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        _die("pastForward: no log files found in logs/.")
    latest = logs[-1]

    if live:
        cmd = ["tail", "-n", str(tail_n or DEFAULT_TAIL_LINES), "-f", str(latest)]
        print(_color(DIM, f"$ {' '.join(cmd)}"))
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass
        return

    print(_color(DIM, f"$ cat {latest}"))
    lines = latest.read_text(errors="replace").splitlines(keepends=True)
    if tail_n is not None:
        lines = lines[-tail_n:]
    for line in lines:
        sys.stdout.write(_colorize(line, SNAKEMAKE_LINE_RULES))

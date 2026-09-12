#!/usr/bin/env python3
"""
pastForward CLI — thin wrapper around the `snakemake` command.

Shells out to `snakemake` for everything that actually runs the workflow. `check`/`preview`
skip Snakemake entirely: they load check.py and expected_output_manager.py in-process (via
scripts/pipeline_namespace.py, the same shared-namespace trick Snakemake's `include:` uses)
and parse the provenance logging those files emit — same output as a --dryrun, without the
DAG build or conda resolution, so they return in well under a second.

Entry point: ./pastForward (project root) — a tiny shim that imports main() from here.

Dispatch below is a hand-rolled `sys.argv` split rather than argparse subparsers: argparse's
REMAINDER positional (needed to pass arbitrary snakemake flags through untouched) errors out
on any "-"-looking token - like a genuine snakemake flag, e.g. --forceall - that appears
before the parser has committed to consuming positionals. Splitting on the command name
ourselves sidesteps that entirely.
"""
import io
import json
import logging
import math
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(".pastforward")
LOG_DIR = Path("logs")
STATE_FILE = STATE_DIR / "run_state.json"

CORES_FLAGS = ("--cores", "-c", "-j", "--jobs")
DRYRUN_FLAGS = ("--dryrun", "--dry-run", "-n")
CONFIGFILE_FLAGS = ("--configfile", "--configfiles")
DEFAULT_CONFIGFILE = "config/config.yaml"  # matches initialize.smk's `configfile:` directive

# Must match initialize.smk's logging.basicConfig, so the regexes below parse in-process
# check/preview output exactly like they parse a real run's log file.
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S (%Z)"

# Written by every rule, via workflow/rules/benchmark.smk. One JSON line per job.
BENCHMARK_SUFFIX = ".benchmark.jsonl"
# Snakemake writes "NA" wherever it could not sample a value: a job that finished before the
# first sample, or any job at all on macOS, where psutil is denied a child process's memory.
BENCHMARK_MISSING = "NA"
# `runtime` is in minutes and `mem_mb` in MB, both at the observed maximum plus headroom.
BENCHMARK_RUNTIME_FACTOR = 2.0
BENCHMARK_MEM_FACTOR = 1.5

DEFAULT_TAIL_LINES = 20
WATCH_TAIL_LINES = 10
FAILED_JOB_LOG_TAIL_LINES = 20

# Matches CLAUDE.md's documented "real run" command.
DEFAULT_RUN_FLAGS = [("--use-conda", None), ("--keep-going", None), ("--rerun-trigger", "mtime")]

PROGRESS_RE = re.compile(r"(\d+) of (\d+) steps \(([\d.]+)%\) done")
# Both lines below come from Snakemake's own per-job log records (jobs.py Job.log_info /
# scheduling/job_scheduler.py), duplicated onto stdout by initialize.smk's root
# logging.basicConfig - unlike the "rule X:" block Snakemake also prints, these two are
# emitted for every job regardless of whether the rule has a `message:` directive.
JOB_STARTED_RE = re.compile(r"^\[.*?\]\s*\[INFO\]\s+Rule:\s*(\S+),\s*Jobid:\s*(\d+)\s*$", re.MULTILINE)
JOB_FINISHED_RE = re.compile(r"Finished jobid:\s*(\d+)\s*\(Rule:\s*(\S+)\)")
DETECTED_SPECIES_RE = re.compile(r"^\[.*?Detected species", re.MULTILINE)
ABORTING_RE = re.compile(r"Will exit after finishing currently running jobs \(scheduler\)\.")
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


RED, GREEN, YELLOW, CYAN, DIM, BOLD_GREEN = 31, 32, 33, 36, 90, "1;32"


def _color(code, text):
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


# Line-level highlighting for raw snakemake/check output. First matching pattern wins.
# Applied to the terminal copy only - the log file on disk always stays plain text so the
# regexes elsewhere in this file (PROGRESS_RE, JOB_STARTED_RE, ...) keep working on it.
SNAKEMAKE_LINE_RULES = [
    (ABORTING_RE, YELLOW),
    (re.compile(r"Workflow finished, no error"), GREEN),
    (re.compile(r"error", re.IGNORECASE), RED),
    (re.compile(r"^WARNING"), YELLOW),
    (re.compile(r"^Finished jobid:"), GREEN),
    (re.compile(r"^\d+ of \d+ steps \([\d.]+%\) done$"), YELLOW),
    (re.compile(r"^(?:local)?(?:rule|checkpoint) \S+:\s*$"), CYAN),
    (re.compile(r"^Nothing to be done"), DIM),
]

CHECK_LINE_RULES = [
    (re.compile(r"error|missing", re.IGNORECASE), RED),
    (re.compile(r"warning", re.IGNORECASE), YELLOW),
    (re.compile(r"\[SKIPPED|ignored \(\d+\)|\(none found\)|not found\)|\(none provided", re.IGNORECASE), DIM),
    (re.compile(r"^- .+\[.+\]\s*$"), CYAN),
    (re.compile(r"^    [A-Za-z].*:\s*$|^    [A-Za-z].*\(\d+\):$"), CYAN),
]


def _colorize(line, rules):
    body = line.rstrip("\n")
    for pattern, code in rules:
        if pattern.search(body):
            return _color(code, body) + ("\n" if line.endswith("\n") else "")
    return line


def _die(msg):
    sys.exit(_color(RED, msg))


def _ensure_project_root(require_snakemake=True):
    if not Path("workflow").is_dir() or not Path("config").is_dir():
        _die(
            "pastForward: this isn't a project root (needs workflow/ and config/ in the "
            "current directory). cd into your project folder first."
        )
    # check/preview/version/print-log never spawn snakemake. check/preview still need PyYAML to
    # read config.yaml, so they fail later on ImportError instead; version and print-log need
    # neither (print-log only reads files back out of logs/).
    if require_snakemake and shutil.which("snakemake") is None:
        _die("pastForward: `snakemake` not found on PATH. Activate its conda env first.")


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_run_cmd(extra_args, defaults=DEFAULT_RUN_FLAGS):
    cmd = ["snakemake"]
    for flag, value in defaults:
        if flag not in extra_args:
            cmd.append(flag)
            if value is not None:
                cmd.append(value)
    cmd += extra_args
    return cmd


def _with_default_cores(extra_args):
    extra_args = list(extra_args)
    if not any(a in CORES_FLAGS for a in extra_args):
        extra_args += ["--cores", "1"]
    return extra_args


def _build_dryrun_cmd(extra_args):
    # Reuses _build_run_cmd so a dry run predicts what `run` will actually do. Without
    # --rerun-trigger mtime a dry run falls back to Snakemake's default trigger set (mtime,
    # params, input, code, software-env) and reports reruns - e.g. "Code has changed since
    # last execution" - that the real run would never perform. --keep-going is a no-op here.
    return _build_run_cmd(_with_default_cores(extra_args)) + ["--dryrun"]


def _build_touch_cmd(extra_args):
    # Deliberately not --use-conda: snakemake builds every rule's conda env before the touch
    # executor ever runs (workflow.py calls dag.create_conda_envs() whenever conda deployment
    # is on, touch or not), which is a long detour for a command that only stamps mtimes on
    # files that already exist. --rerun-trigger mtime stays, so "out of date" means the same
    # here as it does for `run`.
    return _build_run_cmd(_with_default_cores(extra_args), defaults=[("--rerun-trigger", "mtime")]) + ["--touch"]


def _run_foreground(cmd, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(_color(DIM, f"$ {' '.join(cmd)}"))
    print(_color(DIM, f"Logging to {log_path}"))
    with open(log_path, "w") as logf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            sys.stdout.write(_colorize(line, SNAKEMAKE_LINE_RULES))
            logf.write(line)
        return proc.wait()


def _run_background(cmd, log_path):
    if STATE_FILE.exists():
        try:
            old_pid = json.loads(STATE_FILE.read_text())["pid"]
        except (json.JSONDecodeError, KeyError):
            old_pid = None
        if old_pid is not None and _is_alive(old_pid):
            _die(
                f"pastForward: a run is already tracked here (PID {old_pid}, still running). "
                "Use `./pastForward status` to check it or `./pastForward abort` to stop it first."
            )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "w")
    proc = subprocess.Popen(
        cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True
    )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": proc.pid,
                "cmd": cmd,
                "log_file": str(log_path.resolve()),
                "started_at": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
        )
    )
    print(_color(GREEN, f"Started pastForward run (PID {proc.pid})"))
    print(_color(DIM, f"Log: {log_path}"))
    print(_color(DIM, "Check progress with: ./pastForward status"))


def cmd_run(argv, extra_flags=(), name="run"):
    _ensure_project_root()
    # --fg/--foreground is pastForward's own flag, not snakemake's - pulled out here rather
    # than by argparse so it can sit anywhere among the passed-through snakemake args.
    extra = [a for a in argv if a not in ("--fg", "--foreground")]
    foreground = len(extra) != len(argv)
    if not any(a in CORES_FLAGS for a in extra):
        _die(f"pastForward {name}: pass --cores <N> (e.g. --cores 8, or --cores all).")
    for flag in extra_flags:
        if flag not in extra:
            extra.append(flag)
    cmd = _build_run_cmd(extra)
    log_path = LOG_DIR / f"run_{_timestamp()}.log"
    if foreground:
        sys.exit(_run_foreground(cmd, log_path))
    _run_background(cmd, log_path)


def cmd_resume(argv):
    # Same as `run`, plus --rerun-incomplete - for continuing after a crash/kill, per
    # CLAUDE.md's documented resume command.
    cmd_run(argv, extra_flags=("--rerun-incomplete",), name="resume")


def cmd_dryrun(argv):
    _ensure_project_root()
    cmd = _build_dryrun_cmd(argv)
    log_path = LOG_DIR / f"dryrun_{_timestamp()}.log"
    sys.exit(_run_foreground(cmd, log_path))


def cmd_touch(argv):
    _ensure_project_root()
    cmd = _build_touch_cmd(argv)
    log_path = LOG_DIR / f"touch_{_timestamp()}.log"
    sys.exit(_run_foreground(cmd, log_path))


def _read_state():
    if not STATE_FILE.exists():
        _die("pastForward: no tracked run in this directory (start one with `./pastForward run`).")
    return json.loads(STATE_FILE.read_text())


def _is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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


def _format_duration(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = [f"{days}d"] if days else []
    if days or hours:
        parts.append(f"{hours}h")
    if days or hours or minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


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
    watch = "--watch" in argv
    rest = [a for a in argv if a != "--watch"]
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
    if "--force" in argv:
        os.killpg(pid, signal.SIGKILL)
        print(_color(RED, f"Force-killed process group {pid} (main process + subprocesses)."))
    else:
        os.kill(pid, signal.SIGTERM)
        print(_color(YELLOW, f"Sent SIGTERM to PID {pid}. Snakemake will shut its subprocesses down itself."))
        print(_color(DIM, "Use --force to kill the whole process group immediately instead."))


def cmd_unlock(argv):
    _ensure_project_root()
    if argv:
        _die("pastForward unlock: takes no arguments.")
    sys.exit(subprocess.call(["snakemake", "--unlock", "--cores", "1"]))


def _known_env_names():
    # workflow/envs/<name>.yaml -> "<name>", e.g. "ecmsd", "reveal".
    return sorted(p.stem for p in Path("workflow/envs").glob("*.yaml"))


def _list_conda_envs():
    # `--list-conda-envs` never creates anything on disk, but - unlike the doc comment this
    # replaces used to claim - it does NOT set workflow.output_settings.dryrun on its own
    # (verified against Snakemake 9.25.1: that flag is only true when --dryrun is literally
    # passed). initialize.smk reads exactly that attribute to decide whether to skip acquiring
    # the cross-project .pastforward.lock; without an explicit --dryrun here, `pastForward
    # doctor` would try to acquire that lock for real and fail whenever a real run already
    # holds it. --dryrun is required, not just belt-and-suspenders.
    # --nolock: read-only, like check/preview - must not be blocked by, or block, a real run.
    proc = subprocess.run(
        ["snakemake", "--dryrun", "--use-conda", "--list-conda-envs", "--cores", "1", "--nolock"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        print(_color(RED, "snakemake --list-conda-envs failed:"), file=sys.stderr)
        print("\n".join(proc.stdout.splitlines()[-20:]), file=sys.stderr)
        sys.exit(proc.returncode)
    # The env table is the only tab-separated, 3-column output on the whole stream - everything
    # else is the usual startup logging (see initialize.smk), which never looks like that.
    # One row per rule, so an env shared by several rules is listed several times with the
    # same location. Deduplicate on location: the table would otherwise repeat it, and
    # --rebuild-envs would rmtree() the same directory twice and crash on the second try.
    envs = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] != "environment":
            envs.setdefault(parts[2], {"env_file": parts[0], "location": parts[2]})
    return list(envs.values())


def cmd_doctor(argv):
    _ensure_project_root()
    rebuild = "--rebuild-envs" in argv
    names = [a for a in argv if a != "--rebuild-envs"]
    if not rebuild and names:
        _die(f"pastForward doctor: unknown argument(s): {' '.join(names)} (did you mean --rebuild-envs?)")
    known = _known_env_names()
    unknown = [n for n in names if n not in known]
    if unknown:
        _die(f"pastForward doctor: unknown env name(s): {', '.join(unknown)}\nKnown envs: {', '.join(known)}")

    print(_color(DIM, "Resolving conda environments (snakemake --list-conda-envs)..."))
    envs = _list_conda_envs()
    if not envs:
        _die("pastForward doctor: no conda environments found for the current config.")

    targets = [e for e in envs if Path(e["env_file"]).stem in names] if names else envs

    print(f"{'ENV FILE':<28}{'STATUS':<10}LOCATION")
    for e in envs:
        built = Path(e["location"]).is_dir()
        # Pad the plain text first, then colorize - _color()'s ANSI codes would otherwise count
        # toward the width and throw off alignment.
        status = _color(GREEN if built else YELLOW, f"{'built' if built else 'missing':<10}")
        marker = _color(CYAN, " (rebuilding)") if rebuild and e in targets else ""
        print(f"{Path(e['env_file']).name:<28}{status}{e['location']}{marker}")

    if not rebuild:
        print()
        print(_color(DIM, "Add --rebuild-envs [name ...] to force one or more of these to be recreated."))
        return

    print()
    removed = [e for e in targets if Path(e["location"]).is_dir()]
    for e in removed:
        shutil.rmtree(e["location"])
        print(_color(YELLOW, f"Removed {e['location']}"))
    if not removed:
        print(_color(DIM, "Nothing to remove - target environment(s) not yet built."))

    print()
    print(_color(DIM, "Recreating via snakemake --use-conda --conda-create-envs-only..."))
    sys.exit(subprocess.call(["snakemake", "--use-conda", "--conda-create-envs-only", "--cores", "1"]))


def _capture_pipeline_log(include_check):
    """Runs the pipeline's own discovery / expected-output code in-process and returns the log
    output it produces, formatted exactly as initialize.smk formats it for a real run - so the
    parsing in cmd_check/cmd_preview is the same either way.

    include_check=True loads check.py (the per-species "Detected species" tree);
    include_check=False calls get_expected_outputs_from_pipeline() (the Requesting/Skipping
    lines). Neither needs Snakemake: no DAG, no conda envs, no directory lock.
    """
    _ensure_project_root(require_snakemake=False)
    if not Path(DEFAULT_CONFIGFILE).is_file():
        _die(f"pastForward: no {DEFAULT_CONFIGFILE} found in this project root.")
    sys.path.insert(0, "workflow")
    try:
        import yaml
        from scripts.pipeline_namespace import load_pipeline_namespace
        from scripts.species_paths import setup_species_data_locations
    except ImportError as e:
        _die(f"pastForward: {e}. Activate the pipeline's conda env first.")

    config = yaml.safe_load(Path(DEFAULT_CONFIGFILE).read_text()) or {}
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.INFO)
    try:
        # dry_run=True: resolve the per-species data-location symlinks (discovery reads through
        # them) but never take the cross-project .pastforward.lock - check/preview are
        # read-only and must not block, or be blocked by, a real run. Same reason initialize.smk
        # skips it on --dryrun.
        setup_species_data_locations(config, dry_run=True)
        namespace = load_pipeline_namespace(config, include_check=include_check)
        if not include_check:
            namespace["get_expected_outputs_from_pipeline"](None)
    except Exception as e:
        _die(f"pastForward: {type(e).__name__}: {e}")
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    return buffer.getvalue()


def cmd_check(argv):
    if argv:
        _die("pastForward check: takes no arguments (it always reads config/config.yaml).")
    text = _capture_pipeline_log(include_check=True)
    m = DETECTED_SPECIES_RE.search(text)
    if not m:
        _die("pastForward: no species found — check config.yaml.")
    # check.py's tree lines all start with "-" or indentation (or are blank, between species) -
    # the first line that starts with anything else is the next, unrelated log message.
    lines = text[m.start() :].splitlines()
    block = [lines[0]]
    for line in lines[1:]:
        if line == "" or line.startswith("-") or line[:1].isspace():
            block.append(line)
        else:
            break
    print("\n".join(_colorize(line, CHECK_LINE_RULES) for line in "\n".join(block).strip().splitlines()))


def cmd_preview(argv):
    if argv:
        _die("pastForward preview: takes no arguments (it always reads config/config.yaml).")
    text = _capture_pipeline_log(include_check=False)
    skipped_species = re.findall(r"Skipping species '(.+?)' \(execute: false\)", text)
    existing = re.findall(r"- Skipping: (.+)", text)
    requested = re.findall(r"- Requesting: (.+)", text)

    if skipped_species:
        print(_color(YELLOW, f"Skipped species ({len(skipped_species)}, execute: false):"))
        for s in skipped_species:
            print(_color(DIM, f"  - {s}"))
        print()
    if existing:
        print(_color(YELLOW, f"Already produced ({len(existing)}, will be skipped):"))
        for f in existing:
            print(_color(DIM, f"  - {f}"))
        print()
    print(_color(GREEN, f"Expected output ({len(requested)}):"))
    for f in requested:
        print(f"  - {f}")
    if not requested:
        print(_color(DIM, "  (none — check config.yaml, or run `./pastForward check` to see what was discovered)"))


def cmd_print_log(argv):
    _ensure_project_root(require_snakemake=False)
    live = "--live" in argv
    rest = [a for a in argv if a != "--live"]
    tail_n = None
    if rest[:1] == ["--tail"]:
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


def _find_benchmark_files(root="."):
    # os.walk rather than Path.rglob because rglob never descends into a symlinked directory,
    # and a species' processed/ or results/ folder is a symlink whenever the config points it
    # outside the project (see workflow/scripts/species_paths.py) - which is exactly the setup
    # where all the benchmark files live behind one.
    files = []
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        # followlinks=True can otherwise walk forever around a symlink cycle.
        real = os.path.realpath(dirpath)
        if real in seen:
            dirnames[:] = []
            continue
        seen.add(real)
        # Skip the pipeline's own code and every dot-directory (.snakemake, .git, .pastforward):
        # no run ever writes a benchmark file there.
        dirnames[:] = [d for d in dirnames if d != "workflow" and not d.startswith(".")]
        files += [os.path.join(dirpath, f) for f in filenames if f.endswith(BENCHMARK_SUFFIX)]
    return sorted(files)


def _benchmark_number(value):
    """A benchmark field as a float, or None if Snakemake could not measure it."""
    if value is None or value == BENCHMARK_MISSING:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_benchmark_records(paths):
    """Parse benchmark files into records. Returns (records, unreadable_paths)."""
    records, unreadable = [], []
    for path in paths:
        try:
            lines = Path(path).read_text().splitlines()
        except OSError:
            unreadable.append(path)
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                unreadable.append(path)
                break
    return records, unreadable


def _summarize_benchmarks(records):
    """Group benchmark records per rule. Returns rows sorted by total core-hours, descending."""
    by_rule = {}
    for record in records:
        # rule_name is an extended-format field. benchmark.smk turns the extended format on for
        # the whole workflow, so it is only missing for files written before that landed.
        by_rule.setdefault(record.get("rule_name") or "(unknown rule)", []).append(record)

    rows = []
    for rule_name, group in by_rule.items():
        seconds = [s for s in (_benchmark_number(r.get("s")) for r in group) if s is not None]
        memory = [m for m in (_benchmark_number(r.get("max_rss")) for r in group) if m is not None]
        core_seconds = sum(
            (_benchmark_number(r.get("s")) or 0) * (_benchmark_number(r.get("threads")) or 1) for r in group
        )
        input_sizes = [
            sum(r["input_size_mb"].values()) for r in group if isinstance(r.get("input_size_mb"), dict)
        ]
        rows.append(
            {
                "rule": rule_name,
                "jobs": len(group),
                "median_s": statistics.median(seconds) if seconds else None,
                "max_s": max(seconds) if seconds else None,
                "max_rss_mb": max(memory) if memory else None,
                "core_hours": core_seconds / 3600,
                "max_input_mb": max(input_sizes) if input_sizes else None,
            }
        )
    return sorted(rows, key=lambda row: row["core_hours"], reverse=True)


def _emit_benchmark_profile(rows):
    print("# Snakemake resource settings derived from the benchmarks above. Paste into")
    print("# workflow/profiles/default/config.yaml, below its `default-resources:` block, or")
    print("# pass individual entries as `--set-resources <rule>:<resource>=<value>`.")
    print(
        f"# runtime is in minutes at {BENCHMARK_RUNTIME_FACTOR:g}x the longest job observed; mem_mb is "
        f"{BENCHMARK_MEM_FACTOR:g}x the highest peak memory observed."
    )
    print("# These are starting points measured on one dataset on one machine, not limits.")
    print("set-resources:")
    for row in rows:
        if row["max_s"] is None:
            continue
        print(f"  {row['rule']}:")
        print(f"    runtime: {max(1, math.ceil(BENCHMARK_RUNTIME_FACTOR * row['max_s'] / 60))}")
        if row["max_rss_mb"] is not None:
            print(f"    mem_mb: {max(1, math.ceil(BENCHMARK_MEM_FACTOR * row['max_rss_mb']))}")


def _print_benchmark_table(rows):
    headers = ("Rule", "Jobs", "Median", "Max", "Max RSS", "Core-h", "Max input")
    body = [
        (
            row["rule"],
            str(row["jobs"]),
            _format_duration(row["median_s"]) if row["median_s"] is not None else "-",
            _format_duration(row["max_s"]) if row["max_s"] is not None else "-",
            f"{row['max_rss_mb']:.0f} MB" if row["max_rss_mb"] is not None else "-",
            f"{row['core_hours']:.2f}",
            f"{row['max_input_mb']:.0f} MB" if row["max_input_mb"] is not None else "-",
        )
        for row in rows
    ]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *body)]

    def _row(cells):
        # Rule names left, every measured number right, so the columns line up on the decimal.
        return cells[0].ljust(widths[0]) + "  " + "  ".join(c.rjust(w) for c, w in zip(cells[1:], widths[1:]))

    print(_color(CYAN, _row(headers)))
    for cells in body:
        print(_row(cells))


def cmd_benchmark(argv):
    _ensure_project_root(require_snakemake=False)
    emit_profile = "--emit-profile" in argv
    rest = [a for a in argv if a != "--emit-profile"]
    if rest:
        _die(f"pastForward benchmark: unknown argument(s): {' '.join(rest)}")

    paths = _find_benchmark_files()
    if not paths:
        _die(
            f"pastForward: no {BENCHMARK_SUFFIX} files found here. They are written as jobs run, "
            "so a finished project has none until something actually re-runs."
        )
    records, unreadable = _load_benchmark_records(paths)
    if not records:
        _die(f"pastForward: found {len(paths)} benchmark file(s), but none of them held a usable record.")
    rows = _summarize_benchmarks(records)

    print(
        _color(CYAN, "Benchmarks:")
        + f" {len(records)} job(s) across {len(rows)} rule(s), from {len(paths)} file(s)."
    )
    print()
    _print_benchmark_table(rows)

    no_memory = [row for row in rows if row["max_rss_mb"] is None]
    print()
    if no_memory:
        print(
            _color(
                YELLOW,
                f"No memory was recorded for {len(no_memory)} of {len(rows)} rule(s).",
            )
        )
        print(
            _color(
                DIM,
                "  Snakemake cannot read a child process's memory on macOS, and a job shorter than\n"
                "  about half a second finishes before the first sample either way. For usable memory\n"
                "  numbers, measure on Linux.",
            )
        )
    print(
        _color(
            DIM,
            "Peak memory is sampled every 0.5s for the first 15s and every 30s after that, so it is\n"
            "an estimate to size a request from, not an exact peak. A job that failed wrote no\n"
            "benchmark at all, so a rule that ran out of memory is missing from this table.",
        )
    )
    if unreadable:
        print(_color(YELLOW, f"{len(unreadable)} file(s) could not be read and were skipped."))
    if emit_profile:
        print()
        _emit_benchmark_profile(rows)


def cmd_version(argv):
    # Only reads workflow/scripts/version.py - no snakemake needed, on PATH or as an import.
    _ensure_project_root(require_snakemake=False)
    sys.path.insert(0, str(Path("workflow")))
    from scripts.version import __version__

    print(__version__)


COMMANDS = {
    "run": cmd_run,
    "resume": cmd_resume,
    "dryrun": cmd_dryrun,
    "status": cmd_status,
    "abort": cmd_abort,
    "unlock": cmd_unlock,
    "touch": cmd_touch,
    "doctor": cmd_doctor,
    "check": cmd_check,
    "preview": cmd_preview,
    "print-log": cmd_print_log,
    "benchmark": cmd_benchmark,
    "version": cmd_version,
}

HELP = """pastForward — CLI wrapper around the pastForward Snakemake pipeline.

Usage: ./pastForward <command> [args...]

Commands:
  run --cores <N> [snakemake-args...]
                                Run the pipeline. --cores (or -j/--jobs) is
                                required. Backgrounded by default; add
                                --fg/--foreground anywhere to run in the
                                foreground instead. Refuses to start if a
                                tracked run is still alive - `abort` it first.
  resume --cores <N> [snakemake-args...]
                                Same as `run`, plus --rerun-incomplete -
                                continue after a crash/kill.
  dryrun [snakemake-args...]    Run `snakemake --dryrun` in the foreground.
  status [--watch]              Show progress of the tracked background run:
                                project name, config file, PID, runtime, a
                                progress bar, and (while still running) the
                                last/currently running jobs. If the process
                                has stopped and at least one job failed, prints
                                the failing rule(s) plus a tail of each
                                failed job's own log file. --watch reprints
                                the formatted status (with a short log tail)
                                every 5s until the run ends (Ctrl-C to stop
                                early).
  abort [--force]               Stop the tracked background run: SIGTERM by
                                default (Snakemake shuts its own subprocesses
                                down); --force kills the whole process group
                                immediately.
  unlock                        Run `snakemake --unlock` to clear a stale
                                Snakemake lock left by a crashed run.
  touch [snakemake-args...]     Mark existing output files as up to date
                                (`snakemake --touch`), so the next run skips
                                the steps that made them instead of redoing
                                them. Nothing is recomputed - only the files'
                                timestamps change. Useful after copying
                                results in from elsewhere, or when a file was
                                touched by hand. Outputs that do not exist yet
                                are skipped with a warning. Add
                                --forcerun/--forceall to touch files Snakemake
                                already considers up to date.
  doctor [--rebuild-envs [name ...]]
                                List the pipeline's conda environments
                                (workflow/envs/*.yaml) and whether each is
                                currently built. Add --rebuild-envs to force
                                one or more back to a not-yet-built state and
                                immediately recreate them - e.g. after bumping
                                an ecmsd/reveal_module version_source setting,
                                which only takes effect on the next env build.
                                With no names, rebuilds every environment.
  check                         Show what pastForward discovers on disk for
                                the current config
                                (species/individuals/references/...).
  preview                       Show expected output files for the current
                                config, including skipped ones.
  print-log [--live] [--tail [N]]
                                Print the most recently written log from
                                logs/. --tail shows only the last N lines
                                (default 20) instead of the whole file. --live
                                follows the log with `tail -f` (Ctrl-C to
                                stop); combine with --tail to seed how many
                                lines it starts from.
  benchmark [--emit-profile]    Summarize how long each rule took and how much memory it
                                used, from the benchmark files every run writes
                                (*.benchmark.jsonl, next to each step's log file).
                                One row per rule, ordered by total core-hours.
                                --emit-profile additionally prints a Snakemake
                                `set-resources:` block derived from those numbers,
                                as a starting point for cluster resource requests.
  version                       Print the pastForward pipeline version.

Run from a project root: the folder containing workflow/ and config/.
Logs for `run`/`dryrun`/`touch` are written to logs/<command>_<timestamp>.log.
"""


def _print_help():
    for line in HELP.splitlines():
        if line.startswith("pastForward") or line in ("Usage: ./pastForward <command> [args...]", "Commands:"):
            print(_color(CYAN, line))
            continue
        stripped = line[2:] if line.startswith("  ") else line
        cmd = stripped.split(" ", 1)[0]
        if line.startswith("  ") and cmd in COMMANDS:
            print("  " + _color(BOLD_GREEN, cmd) + stripped[len(cmd):])
        else:
            print(line)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        _print_help()
        return
    command, rest = argv[0], argv[1:]
    func = COMMANDS.get(command)
    if func is None:
        print(_color(RED, f"pastForward: unknown command '{command}'"))
        print()
        _print_help()
        sys.exit(1)
    func(rest)


if __name__ == "__main__":
    main()

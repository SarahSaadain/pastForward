"""run, resume, dryrun, touch, unlock: the commands that shell out to `snakemake`."""
import json
import subprocess
import sys
from datetime import datetime

from .common import (
    CORES_FLAGS,
    DIM,
    GREEN,
    LOG_DIR,
    SDM_FLAG,
    SNAKEMAKE_LINE_RULES,
    STATE_DIR,
    STATE_FILE,
    _color,
    _colorize,
    _die,
    _ensure_project_root,
    _is_alive,
)


# Every spelling Snakemake accepts for that same setting. `--deployment-method`/`--deployment`/
# `--sdm` are its documented aliases; `--use-conda` is the deprecated flag, which just adds conda
# to the same set. Repeating the option does NOT union: argparse keeps only the last occurrence,
# so passing ours alongside a user's `--sdm apptainer` would silently drop their choice.
DEPLOYMENT_FLAGS = (SDM_FLAG, "--deployment-method", "--deployment", "--sdm", "--use-conda")

# Matches CLAUDE.md's documented "real run" command.
DEFAULT_RUN_FLAGS = [(SDM_FLAG, "conda"), ("--keep-going", None), ("--rerun-trigger", "mtime")]


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_run_cmd(extra_args, defaults=DEFAULT_RUN_FLAGS):
    cmd = ["snakemake"]
    for flag, value in defaults:
        # Any spelling of the deployment flag counts as the user overriding our default, so we
        # step aside rather than append a second, conflicting one (see DEPLOYMENT_FLAGS).
        overrides = DEPLOYMENT_FLAGS if flag == SDM_FLAG else (flag,)
        if not any(a in extra_args for a in overrides):
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
    # Deliberately no conda deployment: snakemake builds every rule's conda env before the touch
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
    _ensure_project_root(require_config=True)
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
    _ensure_project_root(require_config=True)
    cmd = _build_dryrun_cmd(argv)
    log_path = LOG_DIR / f"dryrun_{_timestamp()}.log"
    sys.exit(_run_foreground(cmd, log_path))


def cmd_touch(argv):
    _ensure_project_root(require_config=True)
    cmd = _build_touch_cmd(argv)
    log_path = LOG_DIR / f"touch_{_timestamp()}.log"
    sys.exit(_run_foreground(cmd, log_path))


def cmd_unlock(argv):
    _ensure_project_root()
    if argv:
        _die("pastForward unlock: takes no arguments.")
    sys.exit(subprocess.call(["snakemake", "--unlock", "--cores", "1"]))

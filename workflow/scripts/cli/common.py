"""Shared by every command: project/state paths, colors, error exit, project-root check."""
import os
import re
import shutil
import sys
from pathlib import Path


STATE_DIR = Path(".pastforward")
LOG_DIR = Path("logs")
STATE_FILE = STATE_DIR / "run_state.json"

CORES_FLAGS = ("--cores", "-c", "-j", "--jobs")
DRYRUN_FLAGS = ("--dryrun", "--dry-run", "-n")
CONFIGFILE_FLAGS = ("--configfile", "--configfiles")
DEFAULT_CONFIGFILE = "config/config.yaml"  # matches initialize.smk's `configfile:` directive


# Snakemake 8 replaced `--use-conda` with `--software-deployment-method conda`. The old spelling
# still works in 9.x and is not warned about, but the migration guide calls it deprecated, so the
# new one is what we pass and what the docs teach.
SDM_FLAG = "--software-deployment-method"


ABORTING_RE = re.compile(r"Will exit after finishing currently running jobs \(scheduler\)\.")


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


def _colorize(line, rules):
    body = line.rstrip("\n")
    for pattern, code in rules:
        if pattern.search(body):
            return _color(code, body) + ("\n" if line.endswith("\n") else "")
    return line


def _die(msg):
    sys.exit(_color(RED, msg))


def _ensure_project_root(require_snakemake=True, require_config=False):
    if not Path("workflow").is_dir() or not Path("config").is_dir():
        _die(
            "pastForward: this isn't a project root (needs workflow/ and config/ in the "
            "current directory). cd into your project folder first."
        )
    # Only for the commands that read the config. The workflow itself no longer insists on
    # config/config.yaml being there (see the `configfile:` comment in initialize.smk), so
    # without this a missing config would surface as a Snakemake traceback instead.
    if require_config and not Path(DEFAULT_CONFIGFILE).is_file():
        _die(
            f"pastForward: no {DEFAULT_CONFIGFILE} found in this project root. Copy "
            "config/min_config_sample.yaml there and edit it, or generate one with "
            "config/config_designer.html."
        )
    # check/preview/version/print-log never spawn snakemake. check/preview still need PyYAML to
    # read config.yaml, so they fail later on ImportError instead; version and print-log need
    # neither (print-log only reads files back out of logs/).
    if require_snakemake and shutil.which("snakemake") is None:
        _die("pastForward: `snakemake` not found on PATH. Activate its conda env first.")


def _is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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

"""
pastForward CLI — thin wrapper around the `snakemake` command.

Shells out to `snakemake` for everything that actually runs the workflow. `check`/`preview`
skip Snakemake entirely: they load check.py and expected_output_manager.py in-process (via
scripts/pipeline_namespace.py, the same shared-namespace trick Snakemake's `include:` uses)
and parse the provenance logging those files emit — same output as a --dryrun, without the
DAG build or conda resolution, so they return in well under a second.

Entry point: ./pastForward (project root) — a tiny shim that imports main() from here.

One module per command area: run.py (snakemake invocations), monitor.py (status/abort/logs),
discover.py (check/preview), benchmark.py, doctor.py, tools.py, and common.py for what they
share. This file holds only the command table, the help text built from it, and dispatch.

Dispatch below is a hand-rolled `sys.argv` split rather than argparse subparsers: argparse's
REMAINDER positional (needed to pass arbitrary snakemake flags through untouched) errors out
on any "-"-looking token - like a genuine snakemake flag, e.g. --forceall - that appears
before the parser has committed to consuming positionals. Splitting on the command name
ourselves sidesteps that entirely.
"""
import sys
import textwrap
from pathlib import Path

from .benchmark import cmd_benchmark
from .common import BOLD_GREEN, CYAN, RED, _color, _ensure_project_root
from .discover import cmd_check, cmd_preview
from .doctor import cmd_doctor
from .monitor import cmd_abort, cmd_print_log, cmd_status
from .run import cmd_dryrun, cmd_resume, cmd_run, cmd_touch, cmd_unlock
from .tools import cmd_tools


def cmd_version(argv):
    # Only reads workflow/scripts/version.py - no snakemake needed, on PATH or as an import.
    _ensure_project_root(require_snakemake=False)
    sys.path.insert(0, str(Path("workflow")))
    from scripts.version import __version__

    print(__version__)


# Drives both dispatch and `--help`. Sections follow the order you use them in a project.
# Each command: name -> (function, arguments, description). Descriptions are wrapped on print.
SECTIONS = {
    "Set up a project": {
        "tools": (
            cmd_tools,
            "<tool> [args...]",
            "Helper tools for setting up a project. `tools create-species <species> ...` makes "
            "a species' input folders and prints a config snippet for it. `tools link-reads "
            "-d <folder> -s <species>` symlinks a folder of reads into a species' read folder. "
            "Run `./pastForward tools` for details.",
        ),
    },
    "Before a run": {
        "check": (
            cmd_check,
            "",
            "Show what pastForward discovers on disk for the current config "
            "(species/individuals/references/...).",
        ),
        "preview": (cmd_preview, "", "Show expected output files for the current config, including skipped ones."),
        "dryrun": (cmd_dryrun, "[snakemake-args...]", "Run `snakemake --dryrun` in the foreground."),
    },
    "Run the pipeline": {
        "run": (
            cmd_run,
            "--cores <N> [snakemake-args...]",
            "Run the pipeline. --cores (or -j/--jobs) is required. Backgrounded by default. Add "
            "--fg/--foreground anywhere to run in the foreground instead. Refuses to start if a "
            "tracked run is still alive, so `abort` it first.",
        ),
        "resume": (
            cmd_resume,
            "--cores <N> [snakemake-args...]",
            "Same as `run`, plus --rerun-incomplete. Continues after a crash or kill.",
        ),
    },
    "Watch or stop a run": {
        "status": (
            cmd_status,
            "[--watch/-w]",
            "Show progress of the tracked background run: project name, config file, PID, "
            "runtime, a progress bar, and (while still running) the last/currently running jobs. "
            "If the process has stopped and at least one job failed, prints the failing rule(s) "
            "plus a tail of each failed job's own log file. --watch reprints the status (with a "
            "short log tail) every 5s until the run ends (Ctrl-C to stop early).",
        ),
        "print-log": (
            cmd_print_log,
            "[--live/-l] [--tail/-t [N]]",
            "Print the most recently written log from logs/. --tail shows only the last N lines "
            "(default 20) instead of the whole file. --live follows the log with `tail -f` "
            "(Ctrl-C to stop). Combine with --tail to seed how many lines it starts from.",
        ),
        "abort": (
            cmd_abort,
            "[--force/-f]",
            "Stop the tracked background run. Sends SIGTERM by default, so Snakemake shuts its "
            "own subprocesses down. --force kills the whole process group immediately.",
        ),
    },
    "Fix problems": {
        "unlock": (cmd_unlock, "", "Run `snakemake --unlock` to clear a stale Snakemake lock left by a crashed run."),
        "touch": (
            cmd_touch,
            "[snakemake-args...]",
            "Mark existing output files as up to date (`snakemake --touch`), so the next run "
            "skips the steps that made them instead of redoing them. Nothing is recomputed, only "
            "the files' timestamps change. Useful after copying results in from elsewhere, or "
            "when a file was touched by hand. Outputs that do not exist yet are skipped with a "
            "warning. Add --forcerun/--forceall to touch files Snakemake already considers up "
            "to date.",
        ),
        "doctor": (
            cmd_doctor,
            "[--rebuild-envs [name ...]]",
            "List the pipeline's conda environments (workflow/envs/*.yaml) and whether each is "
            "currently built. Add --rebuild-envs to force one or more back to a not-yet-built "
            "state and immediately recreate them, e.g. after bumping an ecmsd/reveal_module "
            "version_source setting, which only takes effect on the next env build. With no "
            "names, rebuilds every environment.",
        ),
    },
    "After a run": {
        "benchmark": (
            cmd_benchmark,
            "[--emit-profile]",
            "Summarize how long each rule took and how much memory it used, from the benchmark "
            "files every run writes (*.benchmark.jsonl, next to each step's log file). One row "
            "per rule, ordered by total core-hours. --emit-profile additionally prints a "
            "Snakemake `set-resources:` block derived from those numbers, as a starting point "
            "for cluster resource requests.",
        ),
    },
    "Other": {
        "version": (cmd_version, "", "Print the pastForward pipeline version."),
    },
}

COMMANDS = {name: spec[0] for commands in SECTIONS.values() for name, spec in commands.items()}

HELP_INDENT = 32
HELP_WIDTH = 80


def _print_help():
    print(_color(CYAN, "pastForward — CLI wrapper around the pastForward Snakemake pipeline."))
    print()
    print(_color(CYAN, "Usage: ./pastForward <command> [args...]"))
    for section, commands in SECTIONS.items():
        print()
        print(_color(CYAN, f"{section}:"))
        for name, (_, args, description) in commands.items():
            usage = f"  {_color(BOLD_GREEN, name)} {args}".rstrip()
            lines = textwrap.wrap(description, HELP_WIDTH - HELP_INDENT, break_on_hyphens=False)
            plain_len = len(f"  {name} {args}".rstrip())
            # Short usage: description starts on the same line. Long usage: on the next one.
            if plain_len < HELP_INDENT:
                print(usage + " " * (HELP_INDENT - plain_len) + lines.pop(0))
            else:
                print(usage)
            for line in lines:
                print(" " * HELP_INDENT + line)
    print()
    print("Run from a project root: the folder containing workflow/ and config/.")
    print("Logs for `run`/`dryrun`/`touch` are written to logs/<command>_<timestamp>.log.")


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

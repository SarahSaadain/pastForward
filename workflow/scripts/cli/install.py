"""install: check conda, create or upgrade the `pastforward` env, then build the pipeline's tool envs."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .common import (
    CYAN,
    CONFIGFILE_FLAGS,
    DEFAULT_CONFIGFILE,
    DIM,
    GREEN,
    SDM_FLAG,
    YELLOW,
    _color,
    _die,
    _ensure_project_root,
    _live_tracked_pid,
)

MIN_SNAKEMAKE = (
    9,
    26,
    1,
)  # keep in sync with min_version() in workflow/rules/initialize.smk
MIN_CONDA = (24, 7, 1)  # recommended in docs/FAQ.md, not enforced
ENV_NAME = "pastforward"  # pastForward's own env: install may create and upgrade it
USER_ENV_NAME = (
    "snakemake"  # the env the setup guide has users make: reused, never changed
)
CHANNELS = ["-c", "conda-forge", "-c", "bioconda", "-c", "nodefaults"]
MINIFORGE_URL = "https://github.com/conda-forge/miniforge"


def _parse_version(text):
    """First "X.Y[.Z]" in text as a tuple of ints, or None."""
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


def _dotted(version):
    return ".".join(map(str, version))


def _tool_version(exe):
    try:
        return _parse_version(
            subprocess.run([exe, "--version"], capture_output=True, text=True).stdout
        )
    except OSError:
        return None


def _conda_exe():
    # `conda` on PATH, or CONDA_EXE, which conda's shell hook sets even when only the function exists.
    return shutil.which("conda") or os.environ.get("CONDA_EXE")


def _env_prefix(conda, name):
    """Prefix of the conda env called name, or None. `conda env list --json` lists paths only,
    and a named env's folder is its name."""
    out = subprocess.run(
        [conda, "env", "list", "--json"], capture_output=True, text=True, check=True
    ).stdout
    return next((p for p in json.loads(out)["envs"] if Path(p).name == name), None)


def _snakemake_exe(conda):
    """snakemake from the `pastforward` env if it exists, else from a `snakemake` env that is new
    enough, else from a newly created `pastforward` env. Only `pastforward` is ever upgraded."""
    spec = f"snakemake>={_dotted(MIN_SNAKEMAKE)}"
    prefix = _env_prefix(conda, ENV_NAME)
    if prefix is None:
        user_prefix = _env_prefix(conda, USER_ENV_NAME)
        if user_prefix is not None:
            user_exe = Path(user_prefix) / "bin" / "snakemake"
            found = _tool_version(str(user_exe)) if user_exe.exists() else None
            if found is not None and found >= MIN_SNAKEMAKE:
                return str(user_exe)
            have = f"snakemake {_dotted(found)}" if found else "no snakemake"
            print(
                _color(
                    DIM,
                    f"`{USER_ENV_NAME}` env has {have}, needs {spec}. Leaving it as is.",
                )
            )
        print(
            _color(
                DIM, f"No `{ENV_NAME}` conda env yet. Creating it (a few minutes)..."
            ),
            flush=True,
        )
        rc = subprocess.call([conda, "create", "-y", "-n", ENV_NAME, *CHANNELS, spec])
        if rc != 0:
            _die(
                f"pastForward install: `conda create -n {ENV_NAME}` failed (exit {rc})."
            )
        prefix = _env_prefix(conda, ENV_NAME)
        if prefix is None:
            _die(
                f"pastForward install: created `{ENV_NAME}` but conda does not list it."
            )
    exe = Path(prefix) / "bin" / "snakemake"
    found = _tool_version(str(exe)) if exe.exists() else None
    if found is None or found < MIN_SNAKEMAKE:
        have = f"snakemake {_dotted(found)}" if found else "no snakemake"
        print(_color(DIM, f"`{ENV_NAME}` has {have}. Installing {spec}..."), flush=True)
        rc = subprocess.call([conda, "install", "-y", "-n", ENV_NAME, *CHANNELS, spec])
        found = _tool_version(str(exe)) if exe.exists() else None
        if rc != 0 or found is None or found < MIN_SNAKEMAKE:
            _die(
                f"pastForward install: could not get {spec} into {prefix} (conda exit {rc})."
            )
    return str(exe)


def _print_next_steps(snakemake, steps):
    """Numbered (command, comment) steps, led by `conda activate` when snakemake is not on PATH."""
    if shutil.which("snakemake") != snakemake:
        steps = [
            (
                f"conda activate {Path(snakemake).parent.parent.name}",
                "every new terminal, before other ./pastForward commands",
            )
        ] + steps
    print()
    print(_color(CYAN, "Next steps:"))
    width = max(len(cmd) for cmd, _ in steps)
    for i, (cmd, comment) in enumerate(steps, 1):
        print(f"  {i}. {cmd:<{width}}  {_color(DIM, '# ' + comment)}")


def cmd_install(argv):
    _ensure_project_root(require_snakemake=False)

    conda = _conda_exe()
    if conda is None:
        _die(
            "pastForward install: conda not found. Install Miniforge first "
            f"({MINIFORGE_URL}), open a new shell, then rerun `./pastForward install`."
        )
    version = _tool_version(conda)
    print(
        f"{_color(GREEN, 'conda:')} {conda} ({_dotted(version) if version else 'unknown version'})"
    )
    if version and version < MIN_CONDA:
        print(
            _color(
                YELLOW,
                f"  conda {_dotted(MIN_CONDA)} or newer is recommended. Update with `conda update -n base conda`.",
            )
        )

    snakemake = _snakemake_exe(conda)
    print(
        f"{_color(GREEN, 'snakemake:')} {snakemake} ({_dotted(_tool_version(snakemake))})"
    )

    # Which tool envs are needed depends on the config, so they can only be built once one exists.
    if not Path(DEFAULT_CONFIGFILE).is_file() and not any(
        a.split("=")[0] in CONFIGFILE_FLAGS for a in argv
    ):
        print()
        print(
            _color(
                YELLOW,
                f"No {DEFAULT_CONFIGFILE} yet, so the pipeline's tools were not installed.",
            )
        )
        _print_next_steps(
            snakemake,
            [
                (
                    f"cp config/min_config_sample.yaml {DEFAULT_CONFIGFILE}",
                    "or open config/config_designer.html in a browser",
                ),
                (
                    "./pastForward tools create-species <species>",
                    "make its input folders, print a config snippet to paste",
                ),
                (
                    "./pastForward install",
                    "again, to install the tools the config needs",
                ),
            ],
        )
        return

    pid = _live_tracked_pid()
    if pid is not None:
        _die(
            f"pastForward install: a run is active here (PID {pid}). Wait for it or `./pastForward abort` it, then retry."
        )

    print()
    print(
        _color(
            DIM,
            f"Installing the pipeline's tools (snakemake {SDM_FLAG} conda --conda-create-envs-only)...",
        )
    )
    # flush: keeps these lines ahead of Snakemake's when output goes to a pipe or log.
    print(
        _color(DIM, "Envs already built are skipped. The first time takes a while."),
        flush=True,
    )
    # Snakemake calls `conda` itself, and may not find either tool on PATH without this.
    path = os.pathsep.join(
        [
            str(Path(snakemake).parent),
            str(Path(conda).parent),
            os.environ.get("PATH", ""),
        ]
    )
    rc = subprocess.call(
        [
            snakemake,
            SDM_FLAG,
            "conda",
            "--conda-create-envs-only",
            "--cores",
            "1",
            *argv,
        ],
        env=dict(os.environ, PATH=path),
    )
    if rc == 0:
        print()
        print(
            _color(
                GREEN,
                "Tools installed. Steps you switch on later get their tools on the next run.",
            )
        )
        _print_next_steps(
            snakemake,
            [
                (
                    "./pastForward tools create-species <species>",
                    "make its input folders, print a config snippet to paste",
                ),
                (
                    "./pastForward tools link-reads -d <folder> -s <species>",
                    "link your reads into the species' read folder",
                ),
                (
                    "./pastForward tools link-reference -d <fasta>",
                    "link your reference genome (also: link-feature-library)",
                ),
                ("./pastForward check", "what the config finds on disk"),
                ("./pastForward dryrun", "what a run would do"),
                ("./pastForward run --cores <N>", "start the pipeline"),
            ],
        )
    sys.exit(rc)

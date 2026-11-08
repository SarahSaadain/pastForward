"""Per-machine CLI settings in ~/.config/pastforward/cli.json (stdlib only, no PyYAML needed).

snakemake_env: the conda env prefix that has snakemake. `install` sets it; any other command
    that finds snakemake on PATH updates it to that env (the last one used).
auto_activate: false turns off using snakemake_env when snakemake is not on PATH. Default true.
"""

import json
import os
import sys
from pathlib import Path

SETTINGS_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    / "pastforward"
    / "cli.json"
)


def _load():
    """(settings, ok). ok is False when the file exists but cannot be read as a JSON object."""
    try:
        text = SETTINGS_FILE.read_text()
    except FileNotFoundError:
        return {}, True
    except OSError:
        return {}, False
    try:
        data = json.loads(text)
    except ValueError:
        return {}, False
    return (data, True) if isinstance(data, dict) else ({}, False)


def read():
    return _load()[0]


def update(**changes):
    data, ok = _load()
    if not ok:
        # Never overwrite a file the user may be editing: that would drop their settings.
        print(
            f"pastForward: {SETTINGS_FILE} is not a valid JSON object, so it was left "
            "unchanged. Fix it or delete it.",
            file=sys.stderr,
        )
        return
    if all(data.get(k) == v for k, v in changes.items()):
        return
    data.update(changes)
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Write a temp file, then rename: a run that writes at the same moment cannot leave half a file.
        tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(tmp, SETTINGS_FILE)
    except OSError:
        pass  # a convenience record: never fail a command over it


def auto_activate_enabled():
    return read().get("auto_activate", True) is not False

"""doctor: list the pipeline's conda environments and rebuild them."""
import shutil
import subprocess
import sys
from pathlib import Path

from .common import CYAN, DIM, GREEN, RED, SDM_FLAG, YELLOW, _color, _die, _ensure_project_root


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
        ["snakemake", "--dryrun", SDM_FLAG, "conda", "--list-conda-envs", "--cores", "1", "--nolock"],
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
    print(_color(DIM, f"Recreating via snakemake {SDM_FLAG} conda --conda-create-envs-only..."))
    sys.exit(subprocess.call(["snakemake", SDM_FLAG, "conda", "--conda-create-envs-only", "--cores", "1"]))

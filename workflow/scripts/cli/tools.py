"""tools: helpers for setting up a project (create-species, link-reads)."""
import os
import re
import sys
from pathlib import Path

from .common import CYAN, DEFAULT_CONFIGFILE, DIM, GREEN, RED, STATE_DIR, YELLOW, _color, _die, _ensure_project_root


# The input folders file_manager.py scans. processed/ and results/ are left out on purpose:
# the pipeline creates them itself, and a real folder there would block a later
# processed_dir/results_dir override (species_paths.py refuses to replace a real directory).
SPECIES_INPUT_DIRS = (
    "input/read_module",
    "input/reference_module",
    "input/reveal_module/scg",
    "input/reveal_module/feature_library",
    "input/reveal_module/competition",
)
# The species key becomes a folder name and a path component in every output, so no
# separators, spaces, or leading dot/dash.
SPECIES_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# Top-level project folders a species folder must not land in.
RESERVED_SPECIES_KEYS = {"workflow", "config", "logs", "docs", "tests", STATE_DIR.name}


def _species_config_snippet(species_keys):
    lines = ["species:"]
    for key in species_keys:
        lines += [
            f"  {key}:",
            f'    name: "{key}"  # full species name, e.g. "Drosophila melanogaster"',
            "    # BUSCO lineage, only needed for REVEAL SCG auto-determination.",
            "    # Find yours at https://busco.ezlab.org/, e.g. drosophilidae_odb12",
            '    #lineage: ""',
        ]
    return "\n".join(lines)


def tool_create_species(argv):
    if not argv or any(a.startswith("-") for a in argv):
        _die("Usage: ./pastForward tools create-species <species> [<species> ...]")
    _ensure_project_root(require_snakemake=False)
    for key in argv:
        if not SPECIES_KEY_RE.match(key) or key.lower() in RESERVED_SPECIES_KEYS:
            _die(
                f"pastForward: '{key}' can't be used as a species name. Use letters, digits, "
                "'_', '.' or '-', start with a letter or digit, and don't reuse a project "
                "folder name like workflow or config."
            )
    for key in argv:
        print(_color(CYAN, f"{key}/"))
        for sub in SPECIES_INPUT_DIRS:
            path = Path(key) / sub
            state = _color(DIM, "exists") if path.is_dir() else _color(GREEN, "created")
            path.mkdir(parents=True, exist_ok=True)
            print(f"  {sub + '/':<40}{state}")
    print()
    print("Put raw reads in <species>/input/read_module/ and reference genomes in")
    print("<species>/input/reference_module/. The reveal_module folders are optional.")
    print()
    print(_color(CYAN, f"Add this to {DEFAULT_CONFIGFILE} (merge into an existing species: block):"))
    print()
    print(_species_config_snippet(argv))


LINK_READS_FLAGS = {"--source": "source", "-d": "source", "--species": "species", "-s": "species"}


def tool_link_reads(argv):
    usage = "Usage: ./pastForward tools link-reads --source/-d <folder> --species/-s <species>"
    opts = {}
    args = iter(argv)
    for arg in args:
        flag, eq, value = arg.partition("=")  # accepts both `--species Dmel` and `--species=Dmel`
        name = LINK_READS_FLAGS.get(flag)
        if name is None or name in opts:
            _die(f"pastForward tools link-reads: unexpected argument '{arg}'. {usage}")
        opts[name] = value if eq else next(args, "")
        if not opts[name]:
            _die(f"pastForward tools link-reads: {flag} needs a value. {usage}")
    if len(opts) != 2:
        _die(usage)
    _ensure_project_root(require_snakemake=False)
    sys.path.insert(0, "workflow")
    from scripts import file_manager  # stdlib-only at import time, no conda env needed

    extensions = file_manager.RAW_READ_EXTENSIONS
    source, key = Path(opts["source"]).expanduser(), opts["species"]
    if not source.is_dir():
        _die(f"pastForward: source folder '{source}' not found.")
    reads_dir = Path(key) / "input/read_module"
    if not SPECIES_KEY_RE.match(key) or not reads_dir.is_dir():
        _die(
            f"pastForward: '{reads_dir}/' not found. Create it first with "
            f"./pastForward tools create-species {key}"
        )
    # Hidden files are skipped, e.g. the ._name AppleDouble copies macOS leaves on external drives.
    reads = sorted(
        p
        for p in source.resolve().iterdir()
        if p.is_file() and p.name.endswith(extensions) and not p.name.startswith(".")
    )
    if not reads:
        _die(f"pastForward: no {' or '.join('*' + e for e in extensions)} files in '{source}'.")
    counts = {"linked": 0, "exists": 0, "skipped": 0}
    print(_color(CYAN, f"{reads_dir}/"))
    for read in reads:
        link = reads_dir / read.name
        if link.is_symlink() and Path(os.readlink(link)) == read:
            state, label = "exists", _color(DIM, "exists")
        elif link.exists() or link.is_symlink():
            state, label = "skipped", _color(YELLOW, "skipped, a different file with this name is already there")
        else:
            link.symlink_to(read)
            state, label = "linked", _color(GREEN, "linked")
        counts[state] += 1
        print(f"  {read.name:<50}{label}")
    print()
    print(", ".join(f"{n} {state}" for state, n in counts.items()))

    problems = [(r.name, why) for r in reads if (why := file_manager.get_read_name_problem(r.name))]
    if problems:
        print()
        print(_color(YELLOW, f"Warning: {len(problems)} file name(s) don't match the raw read naming convention:"))
        for name, why in problems:
            print(_color(YELLOW, f"  {name:<50}{why}"))
        print(
            f"Expected {file_manager._RAW_READ_PATTERN_HINT}. The links were still made. "
            "Rename the links (not the source files) to fix this."
        )


TOOLS = {
    "create-species": tool_create_species,
    "link-reads": tool_link_reads,
}

TOOLS_HELP = """Usage: ./pastForward tools <tool> [args...]

Tools:
  create-species <species> [<species> ...]
                                Create the input folder structure for one or
                                more species in the project root, and print a
                                config snippet to paste into config.yaml.
                                Existing folders are left untouched.
  link-reads --source/-d <folder> --species/-s <species>
                                Symlink every *.fastq.gz / *.fq.gz file in
                                the source folder into the species'
                                input/read_module/ folder, using absolute
                                paths and the original file names. Files
                                already there are left untouched.
"""


def cmd_tools(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(TOOLS_HELP)
        return
    func = TOOLS.get(argv[0])
    if func is None:
        print(_color(RED, f"pastForward: unknown tool '{argv[0]}'"))
        print()
        print(TOOLS_HELP)
        sys.exit(1)
    func(argv[1:])

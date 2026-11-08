"""tools: helpers for setting up a project (create-species, link-reads, link-reference, link-feature-library)."""

import os
import re
import sys
from pathlib import Path

from .common import (
    CYAN,
    DEFAULT_CONFIGFILE,
    DIM,
    GREEN,
    RED,
    STATE_DIR,
    YELLOW,
    _color,
    _die,
    _ensure_project_root,
)


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
    print(
        _color(
            CYAN,
            f"Add this to {DEFAULT_CONFIGFILE} (merge into an existing species: block):",
        )
    )
    print()
    print(_species_config_snippet(argv))


SPECIES_FLAGS = {"--species": "species", "-s": "species"}
SOURCE_FLAGS = {"--source": "source", "-d": "source"}
FASTA_EXTENSIONS = (".fna", ".fasta", ".fa")


def _parse_flags(tool, flags, argv, usage):
    """Parse `--flag value` / `--flag=value` pairs. Each flag may appear once."""
    opts = {}
    args = iter(argv)
    for arg in args:
        flag, eq, value = arg.partition(
            "="
        )  # accepts both `--species Dmel` and `--species=Dmel`
        name = flags.get(flag)
        if name is None or name in opts:
            _die(f"pastForward tools {tool}: unexpected argument '{arg}'. {usage}")
        opts[name] = value if eq else next(args, "")
        if not opts[name]:
            _die(f"pastForward tools {tool}: {flag} needs a value. {usage}")
    return opts


def _resolve_species(opts, tool):
    """The --species value, or the project's only species when the flag is left out."""
    if "species" in opts:
        return opts["species"]
    found = sorted(
        d.name
        for d in Path(".").iterdir()
        if d.is_dir()
        and SPECIES_KEY_RE.match(d.name)
        and d.name.lower() not in RESERVED_SPECIES_KEYS
        and (d / "input").is_dir()
    )
    if len(found) == 1:
        return found[0]
    if not found:
        _die(
            f"pastForward tools {tool}: no species folder found. Create one with "
            "./pastForward tools create-species <species>"
        )
    _die(
        f"pastForward tools {tool}: several species found ({', '.join(found)}). "
        "Pick one with --species/-s."
    )


def _species_dir(key, sub):
    folder = Path(key) / sub
    if not SPECIES_KEY_RE.match(key) or not folder.is_dir():
        _die(
            f"pastForward: '{folder}/' not found. Create it first with "
            f"./pastForward tools create-species {key}"
        )
    return folder


def _link_into(files, dest):
    """Symlink each file into dest by absolute path and original name. Never overwrites."""
    counts = {"linked": 0, "exists": 0, "skipped": 0}
    print(_color(CYAN, f"{dest}/"))
    for file in files:
        link = dest / file.name
        if link.is_symlink() and Path(os.readlink(link)) == file:
            state, label = "exists", _color(DIM, "exists")
        elif link.exists() or link.is_symlink():
            state, label = (
                "skipped",
                _color(
                    YELLOW, "skipped, a different file with this name is already there"
                ),
            )
        else:
            link.symlink_to(file)
            state, label = "linked", _color(GREEN, "linked")
        counts[state] += 1
        print(f"  {file.name:<50}{label}")
    print()
    print(", ".join(f"{n} {state}" for state, n in counts.items()))


def _fasta_sources(source):
    """A FASTA file, or every FASTA directly inside a folder (hidden files skipped)."""
    source = Path(source).expanduser()
    if source.is_file():
        files = [source.resolve()]
    elif source.is_dir():
        files = sorted(
            p
            for p in source.resolve().iterdir()
            if p.is_file() and not p.name.startswith(".")
        )
    else:
        _die(f"pastForward: source '{source}' not found.")
    files = [f for f in files if f.name.endswith(FASTA_EXTENSIONS)]
    if not files:
        _die(
            f"pastForward: no {' or '.join('*' + e for e in FASTA_EXTENSIONS)} files in '{source}'."
        )
    return files


def tool_link_reads(argv):
    usage = "Usage: ./pastForward tools link-reads --source/-d <folder> [--species/-s <species>]"
    opts = _parse_flags("link-reads", {**SOURCE_FLAGS, **SPECIES_FLAGS}, argv, usage)
    if "source" not in opts:
        _die(usage)
    _ensure_project_root(require_snakemake=False)
    sys.path.insert(0, "workflow")
    from scripts import file_manager  # stdlib-only at import time, no conda env needed

    extensions = file_manager.RAW_READ_EXTENSIONS
    source = Path(opts["source"]).expanduser()
    if not source.is_dir():
        _die(f"pastForward: source folder '{source}' not found.")
    reads_dir = _species_dir(_resolve_species(opts, "link-reads"), "input/read_module")
    # Hidden files are skipped, e.g. the ._name AppleDouble copies macOS leaves on external drives.
    reads = sorted(
        p
        for p in source.resolve().iterdir()
        if p.is_file() and p.name.endswith(extensions) and not p.name.startswith(".")
    )
    if not reads:
        _die(
            f"pastForward: no {' or '.join('*' + e for e in extensions)} files in '{source}'."
        )
    _link_into(reads, reads_dir)

    problems = [
        (r.name, why)
        for r in reads
        if (why := file_manager.get_read_name_problem(r.name))
    ]
    if problems:
        print()
        print(
            _color(
                YELLOW,
                f"Warning: {len(problems)} file name(s) don't match the raw read naming convention:",
            )
        )
        for name, why in problems:
            print(_color(YELLOW, f"  {name:<50}{why}"))
        print(
            f"Expected {file_manager._RAW_READ_PATTERN_HINT}. The links were still made. "
            "Rename the links (not the source files) to fix this."
        )


def tool_link_reference(argv):
    usage = (
        "Usage: ./pastForward tools link-reference --source/-d <fasta or folder> "
        "[--species/-s <species>]"
    )
    opts = _parse_flags(
        "link-reference", {**SOURCE_FLAGS, **SPECIES_FLAGS}, argv, usage
    )
    if "source" not in opts:
        _die(usage)
    _ensure_project_root(require_snakemake=False)
    files = _fasta_sources(opts["source"])
    dest = _species_dir(
        _resolve_species(opts, "link-reference"), "input/reference_module"
    )
    _link_into(files, dest)


def tool_link_feature_library(argv):
    usage = (
        "Usage: ./pastForward tools link-feature-library --source/-d <fasta or folder> "
        "[--competition/-c <fasta>] [--species/-s <species>]"
    )
    flags = {
        **SOURCE_FLAGS,
        **SPECIES_FLAGS,
        "--competition": "competition",
        "-c": "competition",
    }
    opts = _parse_flags("link-feature-library", flags, argv, usage)
    if "source" not in opts:
        _die(usage)
    _ensure_project_root(require_snakemake=False)
    files = _fasta_sources(opts["source"])
    competition = _fasta_sources(opts["competition"]) if "competition" in opts else []
    if len(competition) > 1:
        _die("pastForward: --competition takes exactly one FASTA file.")
    key = _resolve_species(opts, "link-feature-library")
    library_dir = _species_dir(key, "input/reveal_module/feature_library")
    competition_dir = _species_dir(key, "input/reveal_module/competition")
    # The pipeline stops on more than one competition FASTA, so refuse to add a second.
    present = [
        p for p in competition_dir.iterdir() if p.name.endswith(FASTA_EXTENSIONS)
    ]
    if competition and any(p.name != competition[0].name for p in present):
        _die(
            f"pastForward: '{competition_dir}/' already holds a different FASTA. "
            "The pipeline accepts exactly one competition file. Remove it first."
        )
    _link_into(files, library_dir)
    if competition:
        print()
        _link_into(competition, competition_dir)


TOOLS = {
    "create-species": tool_create_species,
    "link-reads": tool_link_reads,
    "link-reference": tool_link_reference,
    "link-feature-library": tool_link_feature_library,
}

TOOLS_HELP = """Usage: ./pastForward tools <tool> [args...]

Tools:
  create-species <species> [<species> ...]
                                Create the input folder structure for one or
                                more species in the project root, and print a
                                config snippet to paste into config.yaml.
                                Existing folders are left untouched.
  link-reads --source/-d <folder> [--species/-s <species>]
                                Symlink every *.fastq.gz / *.fq.gz file in
                                the source folder into the species'
                                input/read_module/ folder, using absolute
                                paths and the original file names. Files
                                already there are left untouched.
  link-reference --source/-d <fasta or folder> [--species/-s <species>]
                                Same, for reference genomes (*.fna, *.fasta,
                                *.fa) into input/reference_module/.
  link-feature-library --source/-d <fasta or folder> [--competition/-c <fasta>]
                       [--species/-s <species>]
                                Same, for feature libraries into
                                input/reveal_module/feature_library/. With
                                --competition, the one competition FASTA is
                                linked into input/reveal_module/competition/.

--species/-s can be left out when the project has only one species.
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

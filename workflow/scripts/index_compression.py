"""Mapping indexes live as temp() files; the pack_index rule keeps a .gz of each.

At workflow load the .gz is unpacked again (real run) or stood in for by an empty placeholder
(dry run), both with the archive's mtime. The index then looks untouched, so Snakemake neither
rebuilds it nor remaps finished individuals. A rule cannot do this: any job that produces the
index in the plan flags every mapping job as "input updated by another job".
"""

import atexit
import os
import re
import shutil
import subprocess
from pathlib import Path

# bwa-aln (.bwt .sa), bwa-mem2 (.0123 .bwt.2bit.64) and minimap2 (.mmi) index files.
# Also the wildcard_constraint of the pack_index rule.
INDEX_REGEX = r".+(?:\.(?:fa|fasta)\.(?:0123|amb|ann|bwt\.2bit\.64|bwt|pac|sa)|\.mmi)"
_INDEX = re.compile(INDEX_REGEX + r"\.gz$")

_SUFFIXES = {
    "bwa-aln": (".amb", ".ann", ".bwt", ".pac", ".sa"),
    "bwa-mem2": (".0123", ".amb", ".ann", ".bwt.2bit.64", ".pac"),
}

# Folders that hold mapping indexes: reference, SCG library, feature library.
_GLOBS = (
    "processed/reference_module/*/reference/*.gz",
    "processed/reveal_module/scg/*.gz",
    "processed/reveal_module/*/library/*.gz",
)


def index_archives(fasta: str, mapper: str, mmi: str = None) -> list:
    """The .gz archives to request for the index of `fasta` (minimap2: `mmi`, default fasta + .mmi)."""
    if mapper == "minimap2":
        return [(mmi or fasta + ".mmi") + ".gz"]
    return [fasta + s + ".gz" for s in _SUFFIXES.get(mapper, _SUFFIXES["bwa-mem2"])]


def is_dryrun(argv: list) -> bool:
    """--dryrun / --dry-run, or -n alone or inside a short-flag cluster (-np, -nq).

    workflow.dryrun is not set yet while the Snakefile loads, so the command line is read.
    """
    return any(
        a in ("--dryrun", "--dry-run") or re.fullmatch(r"-[A-Za-z]*n[A-Za-z]*", a)
        for a in argv
    )


def mapper(config: dict, module: str, step: str = "mapping") -> str:
    """Configured mapper of a step; the SCG selector falls back to the mapping step's mapper."""
    mod = (config.get("pipeline") or {}).get(module) or {}
    own = ((mod.get(step) or {}).get("settings") or {}).get("mapper")
    if own or step == "mapping":
        return own or "bwa-mem2"
    return mapper(config, module)


def _archives(config: dict):
    for species, sp_cfg in (config.get("species", {}) or {}).items():
        if (sp_cfg or {}).get("execute", True):
            for g in _GLOBS:
                for gz in sorted(Path(species).glob(g)):
                    if _INDEX.match(gz.name) and gz.is_file():
                        yield gz


def _remove(paths) -> None:
    for p in paths:
        p.unlink(missing_ok=True)


def restore_indexes(config: dict, dryrun: bool) -> None:
    """Bring back every index that only exists as .gz. Dry run: empty placeholders, removed at exit."""
    placeholders = []
    for gz in _archives(config):
        raw = gz.with_suffix("")
        # An empty raw file is a placeholder left by a killed dry run.
        if raw.exists() and raw.stat().st_size > 0:
            continue
        mtime = gz.stat().st_mtime
        if dryrun:
            raw.touch()
            os.utime(raw, (mtime, mtime))
            placeholders.append(raw)
        else:
            # -k keeps the .gz; gzip/pigz restore the mtime stored in the archive.
            subprocess.run([shutil.which("pigz") or "gzip", "-d", "-k", "-f", str(gz)], check=True)
    if placeholders:
        atexit.register(_remove, placeholders)


def remove_unpacked_indexes(config: dict) -> None:
    """End of a run: drop raw indexes that have an archive (unpacked but never consumed)."""
    for gz in _archives(config):
        gz.with_suffix("").unlink(missing_ok=True)

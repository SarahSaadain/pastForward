# =================================================================================================
#     Species Data Location Setup
# =================================================================================================
# Resolves optional per-species data-location overrides (species.<key>.species_dir /
# reads_dir / reference_dir / scg_dir / feature_library_dir / competition_dir / processed_dir /
# results_dir) into symlinks at the conventional "<species>/..." locations pastForward's rules
# already reference as literal strings. Called once from initialize.smk, before Snakemake parses
# any rule, so every existing "{species}/input/..." / "{species}/processed/..." /
# "{species}/results/..." path in the rule files resolves through the symlink transparently.
#
# When nothing is configured for a species/category, none of this runs for it — the directory
# entry (or its absence) is left exactly as pastForward has always expected it.
#
# Imported (not `include`d) from initialize.smk/Snakefile, the same way initialize.smk already
# does `from scripts.version import __version__` — this keeps helper/internal names out of the
# shared rule-file namespace that file_manager.py populates via `include:`.

import json
import logging
import os
import socket
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------------------------
# Category -> conventional path, relative to a species root (either "<project_root>/<species>"
# or a configured "species_dir").
CATEGORY_RELPATHS = {
    "reads":           "input/read_module",
    "reference":       "input/reference_module",
    "scg":             "input/reveal_module/scg",
    "feature_library": "input/reveal_module/feature_library",
    "competition":     "input/reveal_module/competition",
    "processed":       "processed",
    "results":         "results",
}

# Category -> the species.<key>.<...> config key that can override it explicitly.
CATEGORY_CONFIG_KEYS = {
    "reads":           "reads_dir",
    "reference":       "reference_dir",
    "scg":             "scg_dir",
    "feature_library": "feature_library_dir",
    "competition":     "competition_dir",
    "processed":       "processed_dir",
    "results":         "results_dir",
}

# The two categories that are written to during a run, and therefore need the cross-project
# collision lock (see acquire_project_lock below). Read-only categories (reads/reference/scg/
# feature_library/competition) never need it.
WRITE_CATEGORIES = {"processed", "results"}

LOCK_FILENAME = ".pastforward.lock"


class SpeciesDataLocationError(Exception):
    """Raised when a configured species data location can't be safely symlinked."""


class CrossProjectLockError(Exception):
    """Raised when a processed_dir/results_dir target is (or may be) in use by another run."""


# -----------------------------------------------------------------------------------------------
# Resolve the configured target for a given species/category, following the priority order
# explicit key > species_dir-derived > None (nothing configured -> today's default applies and
# the caller must not touch the filesystem for this category at all).
def _resolve_category_target(config: dict, species: str, category: str) -> str | None:
    sp_cfg = config.get("species", {}).get(species, {}) or {}

    explicit = sp_cfg.get(CATEGORY_CONFIG_KEYS[category])
    if explicit:
        return os.path.realpath(explicit)

    species_dir = sp_cfg.get("species_dir")
    if species_dir:
        return os.path.realpath(os.path.join(species_dir, CATEGORY_RELPATHS[category]))

    return None


# -----------------------------------------------------------------------------------------------
# Ensure a symlink exists at `link_path` pointing at `target_abspath`.
#
# Safety invariant for any code that might ever REMOVE a symlink this function created: verify
# BOTH os.path.islink(path) is True AND os.readlink(path) equals the exact target that would
# currently be created here, before removing anything, and remove with a plain os.remove()/
# os.unlink() — never a recursive delete (rm -rf on a symlink-with-trailing-slash can wipe out
# the *target's* contents on some systems). No teardown logic exists yet; this function itself
# never removes anything (see step 1/2 below) — this note is for future code that might.
def _ensure_symlink(link_path: Path, target_abspath: str, *, species: str, category: str) -> None:
    # 1. Idempotency / conflict check for an existing symlink.
    if link_path.is_symlink():
        current_target = os.readlink(link_path)
        if current_target == target_abspath:
            logger.debug(
                f"[species_paths] {link_path} already links to {target_abspath} "
                f"(species '{species}', category '{category}') — no-op."
            )
            return
        raise SpeciesDataLocationError(
            f"Cannot set up '{category}' for species '{species}': {link_path} is already a "
            f"symlink pointing to {current_target}, but the config resolves it to "
            f"{target_abspath}. Remove the existing symlink manually if it's stale, or fix the "
            f"config if it points where you actually want."
        )

    # 2. A real file/directory already exists there — never overwrite. This is exactly the
    # case of a pre-existing default-layout folder, or a symlink to an individual file the user
    # placed by hand (see config/README.md "Providing Raw Data").
    if link_path.exists():
        raise SpeciesDataLocationError(
            f"Cannot set up '{category}' for species '{species}': {link_path} already exists as "
            f"a real file/directory. Refusing to replace it with a symlink to {target_abspath}. "
            f"Move or remove {link_path} manually, or remove the {CATEGORY_CONFIG_KEYS[category]} "
            f"(or species_dir) override from the config if this location is intentional."
        )

    # 3. Nothing there yet — create it. Guard against a typo'd/missing configured target instead
    # of silently creating a dangling symlink.
    if not os.path.isdir(target_abspath):
        raise SpeciesDataLocationError(
            f"Cannot set up '{category}' for species '{species}': configured target "
            f"{target_abspath} does not exist or is not a directory."
        )

    link_path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target_abspath, link_path, target_is_directory=True)
    logger.info(
        f"[species_paths] Linked {link_path} -> {target_abspath} "
        f"(species '{species}', category '{category}')."
    )


# -----------------------------------------------------------------------------------------------
# Cross-project collision lock
# -----------------------------------------------------------------------------------------------
# Snakemake's own lock lives in this project's .snakemake/ folder, so it can't see a collision
# originating from a *different* working directory/config that happens to resolve processed_dir
# or results_dir to the same real target. This lock is written inside the resolved target itself,
# keyed purely by that absolute real path, so it catches the collision regardless of project name
# or config identity. It is a separate, additional mechanism from Snakemake's own lock —
# `snakemake --unlock` does not clear it; see docs/FAQ.md.

# Resolved target dir (str) -> identity dict this run wrote there. Only ever contains locks
# *this* run acquired, so release_pastforward_locks() can't touch anyone else's lock.
_ACQUIRED_LOCKS: dict[str, dict] = {}


def _lock_file_path(target_dir: str) -> Path:
    return Path(target_dir) / LOCK_FILENAME


def _current_identity() -> dict:
    return {
        "working_directory": os.getcwd(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "start_timestamp": datetime.now().isoformat(),
    }


def _read_lock(lock_path: Path) -> dict | None:
    try:
        with open(lock_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _pid_alive(pid) -> bool:
    # pid <= 0 would make os.kill signal a process group; a missing/garbled lock pid is not alive.
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else - definitely still alive.
        return True
    except OSError:
        return False
    return True


# -----------------------------------------------------------------------------------------------
# Acquire the cross-project lock for a processed_dir/results_dir target. Raises
# CrossProjectLockError if another (live, or unverifiable) run appears to hold it.
def _acquire_project_lock(target_dir: str, species: str, category: str) -> None:
    if target_dir in _ACQUIRED_LOCKS:
        # Already held by this run (e.g. two species/categories resolving to the same dir).
        return

    lock_path = _lock_file_path(target_dir)
    my_identity = _current_identity()

    existing = _read_lock(lock_path)
    if existing is not None:
        if existing.get("hostname") != my_identity["hostname"]:
            raise CrossProjectLockError(
                f"'{category}' for species '{species}' resolves to {target_dir}, which is "
                f"locked by pastForward on a different host ({existing.get('hostname')}, pid "
                f"{existing.get('pid')}, project {existing.get('working_directory')}, started "
                f"{existing.get('start_timestamp')}). This can't be verified remotely. If you are "
                f"certain that run is no longer active, remove {lock_path} manually before "
                f"re-running."
            )

        if _pid_alive(existing.get("pid")):
            raise CrossProjectLockError(
                f"'{category}' for species '{species}' resolves to {target_dir}, which is "
                f"already locked by another pastForward run: project "
                f"{existing.get('working_directory')}, pid {existing.get('pid')}, started "
                f"{existing.get('start_timestamp')}. Wait for that run to finish, or if it "
                f"crashed without cleaning up, remove {lock_path} manually."
            )

        logger.warning(
            f"[species_paths] Found a stale pastForward lock at {lock_path} (pid "
            f"{existing.get('pid')} is no longer running on this host) — taking it over."
        )

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(my_identity, indent=2))
    _ACQUIRED_LOCKS[target_dir] = my_identity
    logger.debug(f"[species_paths] Acquired lock {lock_path} for '{category}' of species '{species}'.")


# -----------------------------------------------------------------------------------------------
# Release every cross-project lock this run acquired. Called from onsuccess:/onerror: in
# workflow/Snakefile. Safe to call when nothing was acquired (e.g. no processed_dir/results_dir
# overrides configured).
def release_pastforward_locks() -> None:
    for target_dir, identity in list(_ACQUIRED_LOCKS.items()):
        lock_path = _lock_file_path(target_dir)
        current = _read_lock(lock_path)
        if current == identity:
            try:
                lock_path.unlink()
                logger.debug(f"[species_paths] Released lock {lock_path}.")
            except FileNotFoundError:
                pass
        else:
            logger.warning(
                f"[species_paths] Not releasing {lock_path}: its contents no longer match what "
                f"this run wrote (changed or removed externally)."
            )
        del _ACQUIRED_LOCKS[target_dir]


# -----------------------------------------------------------------------------------------------
# Entry point, called at workflow load: for every species (that isn't execute: false) and every
# data-location category, set up the configured symlink (if any). Categories with nothing
# configured are skipped entirely - not "run but no-op". Takes no lock: every snakemake call
# (--dryrun, --lint, --unlock, --conda-create-envs-only, ...) loads the workflow, but only real
# runs fire the onsuccess:/onerror: hooks that release it. See acquire_pastforward_locks.
def setup_species_data_locations(config: dict) -> None:
    for species, category, target in _configured_targets(config):
        _ensure_symlink(
            Path(species) / CATEGORY_RELPATHS[category], target, species=species, category=category
        )


# -----------------------------------------------------------------------------------------------
# Take the cross-project lock for every processed_dir/results_dir override. Called from onstart:
# in workflow/Snakefile, which Snakemake fires only for real runs (not --dryrun, --lint, --unlock,
# --conda-create-envs-only or spawned job subprocesses), exactly the runs whose onsuccess:/
# onerror: release it. If one lock is held elsewhere, the locks already taken are released before
# re-raising: onerror: does not fire for an exception in onstart:.
def acquire_pastforward_locks(config: dict) -> None:
    try:
        for species, category, target in _configured_targets(config):
            if category in WRITE_CATEGORIES:
                _acquire_project_lock(target, species, category)
    except CrossProjectLockError:
        release_pastforward_locks()
        raise


def _configured_targets(config: dict):
    for species, sp_cfg in (config.get("species", {}) or {}).items():
        if not (sp_cfg or {}).get("execute", True):
            continue
        for category in CATEGORY_RELPATHS:
            target = _resolve_category_target(config, species, category)
            if target is not None:
                yield species, category, target

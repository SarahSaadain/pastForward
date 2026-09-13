# =================================================================================================
#     Dependencies and Environment Setup
# =================================================================================================
# Import required Python modules for system, platform, logging, and workflow management
import os
import sys
import pwd
import re
import socket, platform
import subprocess
from datetime import datetime
import logging
from pathlib import Path
import yaml
import json

# import version from workflow/scripts/version.py
from scripts.version import __version__

# import species data-location symlink/lock setup from workflow/scripts/species_paths.py
from scripts.species_paths import setup_species_data_locations

# import deprecated-config-key handling from workflow/scripts/config_compat.py
from scripts.config_compat import apply_config_key_aliases

# Import Snakemake plugin settings for executor modes
from snakemake_interface_executor_plugins.settings import ExecMode

# --- Logging Setup (EARLY) ---
# Configure logging format and output for workflow debugging and status reporting
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S (%Z)"

logging.basicConfig(  # Basic config ASAP (for fallback)
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[logging.StreamHandler()],  # Only console for now
)


envvars:
    "CONDA_DEFAULT_ENV",
    "CONDA_PREFIX",


# =================================================================================================
#     Snakemake Version Check
# =================================================================================================
# Ensure the minimum required Snakemake version is available for compatibility
snakemake.utils.min_version("9.9.0")


# =================================================================================================
#     Configuration Files and Reporting
# =================================================================================================
# Specify the main configuration file for the workflow.
# config/config.yaml belongs to the project, not to the repository (see docs/update.md), so a
# fresh checkout of pastForward has none. Load it only when it is there, so parsing the
# workflow still works without it - that is what `snakemake --lint` does, and it is what the
# Snakemake workflow catalog runs on every clone. A real run without a config stops with a
# clear message from get_expected_outputs_from_pipeline() instead.
if os.path.exists("config/config.yaml"):

    configfile: "config/config.yaml"


# Rewrite deprecated config keys onto their current names before any other file reads
# config, so every read site only has to know the current key. Runs unconditionally
# (subprocess Snakemake runs re-read the config file too, so they need it as well).
apply_config_key_aliases(config)


# =================================================================================================
#     External tool version source (ECMSD / REVEAL)
# =================================================================================================
# ECMSD and REVEAL can each be pinned (the default) or side-loaded straight from GitHub. Each
# version_source maps to its own dedicated conda env file (workflow/envs/<tool>[_git_<source>].yaml),
# with a matching <same-name>.post-deploy.sh that does exactly the one thing that env file needs --
# see those scripts and scripts/config_validation.py (validates version_source, resolves the env
# filename). Rule files reference ECMSD_CONDA_ENV / REVEAL_CONDA_ENV (set below) as their `conda:`
# directive instead of a literal path, so switching version_source switches which env file a rule
# depends on and Snakemake (re)creates/reuses envs accordingly, same as any other conda env.
from scripts.config_validation import resolve_ecmsd_conda_env, resolve_reveal_conda_env

_ENVS_DIR = os.path.join(workflow.basedir, "envs")
ECMSD_CONDA_ENV = os.path.join(_ENVS_DIR, resolve_ecmsd_conda_env(config))
REVEAL_CONDA_ENV = os.path.join(_ENVS_DIR, resolve_reveal_conda_env(config))


# =================================================================================================
#     Workflow Header Logging
# =================================================================================================
PASTFORWARD_BANNER = r"""
                 _   ___                           _
   _ __  __ _ __| |_| __|__ _ ___ __ ____ _ _ _ __| |
  | '_ \/ _` (_-<  _| _/ _ \ '_\ V  V / _` | '_/ _` |
  | .__/\__,_/__/\__|_|\___/_|  \_/\_/\__,_|_| \__,_|
  |_|
"""

# Skip all info gathering and output when running as a subprocess
# (spawned by a parent Snakemake process — the parent already printed this)
if workflow.exec_mode != ExecMode.SUBPROCESS:

    # Printed directly (not via logger) so it isn't broken up by the per-line
    # timestamp/level prefix; written to stderr to stay in the same stream as
    # the logging handler so ordering is preserved when stdout+stderr are
    # redirected to one log file.
    print(PASTFORWARD_BANNER, file=sys.stderr)

    # Resolve optional per-species data-location overrides (species_dir, reads_dir, ...) into
    # symlinks at the conventional locations, and acquire the cross-project collision lock for
    # any processed_dir/results_dir override, before anything else (including file_manager.py's
    # folder discovery) touches a species path. A subprocess spawned by a parent Snakemake
    # process shares the parent's already-set-up filesystem state and lock, so it must not redo
    # this - re-acquiring here would see the parent's own live lock and fail.
    # dry_run is passed through so the lock (but not the symlinks) is skipped on --dryrun - see
    # setup_species_data_locations's docstring in species_paths.py for why.
    _pastforward_dryrun = getattr(
        getattr(workflow, "output_settings", None), "dryrun", False
    )
    setup_species_data_locations(config, dry_run=_pastforward_dryrun)

    pastForward_version = __version__

    try:
        # --dirty appends "-dirty" if the working tree has uncommitted changes,
        # so local edits ahead of the last CI-stamped version.py are still visible
        process = subprocess.Popen(
            ["git", "describe", "--always", "--dirty"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workflow.basedir,
        )
        out, err = process.communicate()
        out = out.decode("ascii")
        pastForward_git_state = out.strip()
        pastForward_git_hash = (
            pastForward_git_state[: -len("-dirty")]
            if pastForward_git_state.endswith("-dirty")
            else pastForward_git_state
        )
        if pastForward_git_state and (
            pastForward_git_hash not in pastForward_version
            or pastForward_git_state.endswith("-dirty")
        ):
            pastForward_version += f" (git: {pastForward_git_state})"
        del process, out, err, pastForward_git_state, pastForward_git_hash
    except Exception:
        pass

    pltfrm = f"{platform.platform()}; {platform.version()}"
    try:
        ld = platform.linux_distribution()
        if len(ld):
            pltfrm = f"{pltfrm}; {ld}"
        del ld
    except:
        pass

    try:

        def merge_osx_tuple(x, bases=(tuple, list)):
            for e in x:
                if type(e) in bases:
                    for e in merge_osx_tuple(e, bases):
                        yield e
                else:
                    yield e

        mv = " ".join(merge_osx_tuple(platform.mac_ver()))
        if not mv.isspace():
            pltfrm = f"{pltfrm}; {mv}"
        del mv, merge_osx_tuple
    except:
        pass

    username = pwd.getpwuid(os.getuid())[0]
    hostname = socket.gethostname()
    node_name = platform.node()
    if node_name != hostname:
        hostname = f"{hostname}; {node_name}"

    try:
        process = subprocess.Popen(
            ["conda", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        out, err = process.communicate()
        out = out.decode("ascii")
        conda_ver = out[out.startswith("conda") and len("conda") :].strip()
        del process, out, err
        if not conda_ver:
            conda_ver = "n/a"
    except:
        conda_ver = "n/a"

    _conda_default_env = os.environ["CONDA_DEFAULT_ENV"]
    _conda_prefix = os.environ["CONDA_PREFIX"]
    conda_env = f"{_conda_default_env} ({_conda_prefix})"
    if conda_env == " ()":
        conda_env = "n/a"

    cmdline = " ".join(sys.argv)

    # --- Config file paths ---
    cfgfiles = []
    for cfg in workflow.configfiles:
        cfgfiles.append(os.path.abspath(cfg))
    cfgfiles = "\n                        ".join(cfgfiles)

    # --- Output ---
    logger.info(f"pastForward {pastForward_version} run:")
    logger.info(f"\tDate:               {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"\tProcess ID:         {os.getpid()}")
    logger.info(f"\tPlatform:           {pltfrm}")
    logger.info(f"\tHost:               {hostname}")
    logger.info(f"\tUser:               {username}")
    logger.info(f"\tConda:              {conda_ver}")
    logger.info(f"\tPython:             {sys.version.split(' ')[0]}")
    logger.info(f"\tSnakemake:          {snakemake.__version__}")
    logger.info(f"\tConda env:          {conda_env}")
    logger.info(f"\tCommand:            {cmdline}")
    logger.info(f"\tBase directory:     {workflow.basedir}")
    logger.info(f"\tWorking directory:  {os.getcwd()}")
    logger.info(f"\tConfig file(s):     {cfgfiles}")

    config_str = yaml.dump(
        config.get("pipeline", {}), sort_keys=False, default_flow_style=False
    )
    logging.info("Loaded configuration:\n%s", config_str)
# =================================================================================================
# End of initialize.smk
# =================================================================================================

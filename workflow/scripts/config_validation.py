# Validates cross-cutting config settings that aren't owned by a single module's own
# expected-output/rule logic, and resolves them to concrete values callers can use directly.

from scripts.file_manager import ConfigValidationError

# version_source -> conda env yaml (workflow/envs/<file>), one file per source so each gets its
# own conda env and matching <same-name>.post-deploy.sh doing exactly that source's one step.
ECMSD_ENV_FILES = {
    "conda": "ecmsd.yaml",
    "latest_release": "ecmsd_git_release.yaml",
    "dev": "ecmsd_git_development.yaml",
}
REVEAL_ENV_FILES = {
    "conda": "reveal.yaml",
    "latest_release": "reveal_git_release.yaml",
    "dev": "reveal_git_development.yaml",
}


def resolve_ecmsd_conda_env(config):
    version_source = (
        config.get("pipeline", {})
        .get("read_module", {})
        .get("taxonomic_screening", {})
        .get("tools", {})
        .get("ecmsd", {})
        .get("settings", {})
        .get("version_source", "conda")
    )
    if version_source not in ECMSD_ENV_FILES:
        raise ConfigValidationError(
            "pipeline.read_module.taxonomic_screening.tools.ecmsd.settings.version_source must be "
            f"one of {tuple(ECMSD_ENV_FILES)}, got {version_source!r}"
        )
    return ECMSD_ENV_FILES[version_source]


def resolve_reveal_conda_env(config):
    version_source = (
        config.get("pipeline", {})
        .get("reveal_module", {})
        .get("settings", {})
        .get("version_source", "conda")
    )
    if version_source not in REVEAL_ENV_FILES:
        raise ConfigValidationError(
            "pipeline.reveal_module.settings.version_source must be "
            f"one of {tuple(REVEAL_ENV_FILES)}, got {version_source!r}"
        )
    return REVEAL_ENV_FILES[version_source]

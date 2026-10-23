"""
Backwards compatibility for renamed config keys.

When a config key is renamed, the old name keeps working: apply_config_key_aliases()
moves the old key's value onto the new name before anything else reads the config, so
the rest of the pipeline only ever sees current key names and no `.get("<old name>", {})`
fallback chains are needed at the read sites. Called once from workflow/rules/initialize.smk,
directly after the configfile is loaded, and mirrored by workflow/scripts/pipeline_namespace.py so
`pastForward check`/`preview` and the unit tests see the same normalised config the real run
does. config_schema.validate_config() runs right after it, so the schema only lists current
key names.
"""

import logging

# (path of dict keys leading to the parent, deprecated key, current key)
CONFIG_KEY_ALIASES = [
    (("pipeline", "read_module"), "contamination", "taxonomic_screening"),
]


def apply_config_key_aliases(config, aliases=CONFIG_KEY_ALIASES):
    """Rename deprecated config keys in place, returning the (old, new) renames applied.

    An explicitly set current key always wins: if both names are present, the deprecated
    one is dropped with a warning rather than merged, so a config that was half-migrated
    by hand can't silently resurrect stale settings.
    """
    applied = []

    for parent_path, old_key, new_key in aliases:
        parent = config
        for step in parent_path:
            if not isinstance(parent, dict):
                break
            parent = parent.get(step)

        if not isinstance(parent, dict) or old_key not in parent:
            continue

        old_value = parent.pop(old_key)
        full_old = ".".join(parent_path + (old_key,))
        full_new = ".".join(parent_path + (new_key,))

        if new_key in parent:
            logging.warning(
                "Config key '%s' is deprecated and '%s' is also set - ignoring '%s'.",
                full_old,
                full_new,
                full_old,
            )
            continue

        parent[new_key] = old_value
        applied.append((full_old, full_new))
        logging.warning(
            "Config key '%s' is deprecated, please rename it to '%s'. "
            "Using it as '%s' for this run.",
            full_old,
            full_new,
            full_new,
        )

    return applied

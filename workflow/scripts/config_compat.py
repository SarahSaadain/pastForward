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
# A current key of None means the key was removed: it is dropped with a warning.
_DEDUP_SETTINGS = ("pipeline", "reference_module", "deduplication", "settings")
CONFIG_KEY_ALIASES = [
    (("pipeline", "read_module"), "contamination", "taxonomic_screening"),
    # dedup clusters are now balanced by reads per contig, not by contig count
    (_DEDUP_SETTINGS, "min_contigs_per_cluster", None),
    (_DEDUP_SETTINGS, "max_contigs_per_cluster", None),
]


def apply_config_key_aliases(config, aliases=CONFIG_KEY_ALIASES):
    """Rename deprecated config keys in place, returning the (old, new) renames applied.

    A key whose current name is None was removed: it is dropped with a warning and is not
    part of the returned list.

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

        if new_key is None:
            logging.warning(
                "Config key '%s' is no longer used and is ignored. Please remove it.",
                full_old,
            )
            continue

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

"""check, preview: run the pipeline's discovery code in-process, no Snakemake needed."""
import io
import logging
import re
import sys
from pathlib import Path

from .common import CYAN, DEFAULT_CONFIGFILE, DIM, GREEN, RED, YELLOW, _color, _colorize, _die, _ensure_project_root


# Must match initialize.smk's logging.basicConfig, so the regexes below parse in-process
# check/preview output exactly like they parse a real run's log file.
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S (%Z)"


DETECTED_SPECIES_RE = re.compile(r"^\[.*?Detected species", re.MULTILINE)


CHECK_LINE_RULES = [
    (re.compile(r"error|missing", re.IGNORECASE), RED),
    (re.compile(r"warning", re.IGNORECASE), YELLOW),
    (re.compile(r"\[SKIPPED|ignored \(\d+\)|\(none found\)|not found\)|\(none provided", re.IGNORECASE), DIM),
    (re.compile(r"^- .+\[.+\]\s*$"), CYAN),
    (re.compile(r"^    [A-Za-z].*:\s*$|^    [A-Za-z].*\(\d+\):$"), CYAN),
]


def _capture_pipeline_log(include_check):
    """Runs the pipeline's own discovery / expected-output code in-process and returns the log
    output it produces, formatted exactly as initialize.smk formats it for a real run - so the
    parsing in cmd_check/cmd_preview is the same either way.

    include_check=True loads check.py (the per-species "Detected species" tree);
    include_check=False calls get_expected_outputs_from_pipeline() (the Requesting/Skipping
    lines). Neither needs Snakemake: no DAG, no conda envs, no directory lock.
    """
    _ensure_project_root(require_snakemake=False, require_config=True)
    sys.path.insert(0, "workflow")
    try:
        import yaml
        from scripts.pipeline_namespace import load_pipeline_namespace
        from scripts.species_paths import setup_species_data_locations
    except ImportError as e:
        _die(f"pastForward: {e}. Activate the pipeline's conda env first.")

    config = yaml.safe_load(Path(DEFAULT_CONFIGFILE).read_text()) or {}
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.INFO)
    try:
        # dry_run=True: resolve the per-species data-location symlinks (discovery reads through
        # them) but never take the cross-project .pastforward.lock - check/preview are
        # read-only and must not block, or be blocked by, a real run. Same reason initialize.smk
        # skips it on --dryrun.
        setup_species_data_locations(config, dry_run=True)
        namespace = load_pipeline_namespace(config, include_check=include_check)
        if not include_check:
            namespace["get_expected_outputs_from_pipeline"](None)
    except Exception as e:
        _die(f"pastForward: {type(e).__name__}: {e}")
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    return buffer.getvalue()


def cmd_check(argv):
    if argv:
        _die("pastForward check: takes no arguments (it always reads config/config.yaml).")
    text = _capture_pipeline_log(include_check=True)
    m = DETECTED_SPECIES_RE.search(text)
    if not m:
        _die("pastForward: no species found — check config.yaml.")
    # check.py's tree lines all start with "-" or indentation (or are blank, between species) -
    # the first line that starts with anything else is the next, unrelated log message.
    lines = text[m.start() :].splitlines()
    block = [lines[0]]
    for line in lines[1:]:
        if line == "" or line.startswith("-") or line[:1].isspace():
            block.append(line)
        else:
            break
    print("\n".join(_colorize(line, CHECK_LINE_RULES) for line in "\n".join(block).strip().splitlines()))


def cmd_preview(argv):
    if argv:
        _die("pastForward preview: takes no arguments (it always reads config/config.yaml).")
    text = _capture_pipeline_log(include_check=False)
    skipped_species = re.findall(r"Skipping species '(.+?)' \(execute: false\)", text)
    existing = re.findall(r"- Skipping: (.+)", text)
    requested = re.findall(r"- Requesting: (.+)", text)

    if skipped_species:
        print(_color(YELLOW, f"Skipped species ({len(skipped_species)}, execute: false):"))
        for s in skipped_species:
            print(_color(DIM, f"  - {s}"))
        print()
    if existing:
        print(_color(YELLOW, f"Already produced ({len(existing)}, will be skipped):"))
        for f in existing:
            print(_color(DIM, f"  - {f}"))
        print()
    print(_color(GREEN, f"Expected output ({len(requested)}):"))
    for f in requested:
        print(f"  - {f}")
    if not requested:
        print(_color(DIM, "  (none — check config.yaml, or run `./pastForward check` to see what was discovered)"))

#!/usr/bin/env python3
"""
Builds a small synthetic species data library (raw reads, reference genome(s), a feature
library, and an SCG library) on disk, following the on-disk naming conventions
workflow/scripts/file_manager.py discovers (see the "Raw read filenames" section of
CLAUDE.md and docs/FAQ.md).

Used by tests/unit/test_file_manager.py and tests/unit/test_expected_output_manager.py to exercise
pipeline discovery / DAG-target logic against real files instead of mocks, without needing
Snakemake or conda. Also used by tests/unit/build_test_library.py to materialize a persistent,
ready-to-inspect copy under tests/unit/fixtures/ (gitignored) for manual `snakemake --dryrun`
sanity checks.

Not a test module itself - has no tests of its own.
"""

import gzip
import os
import shutil

_FASTQ_READ = "@read\nACGTACGTACGTACGTACGTACGTACGT\n+\nIIIIIIIIIIIIIIIIIIIIIIIIIIII\n"
_FASTA_SEQ = "ACGT" * 20

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def write_fastq_gz(path, n_reads=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt") as f:
        f.write(_FASTQ_READ * n_reads)


def write_plain_fastq(path, n_reads=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(_FASTQ_READ * n_reads)


def write_fasta(path, record_names=("seq1",)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for name in record_names:
            f.write(f">{name}\n{_FASTA_SEQ}\n")


class SpeciesLibrary:
    """Records what build_species_library() wrote, so tests can assert against it instead
    of hard-coding the fixture's contents a second time."""

    def __init__(self, species, species_dir):
        self.species = species
        self.species_dir = species_dir
        self.individuals = []
        self.samples = {}  # individual -> [sample_id, ...]
        self.reference_ids = []
        self.feature_library_ids = []
        self.scg_ids = []
        self.unmatched_read_files = []
        self.uncompressed_read_files = []


def build_species_library(
    project_root,
    species="Dmel",
    include_scg=False,
    include_competition=False,
    include_second_reference=True,
    include_feature_library=True,
    include_second_feature_library=False,
    include_unmatched_and_uncompressed=True,
):
    """
    Creates <project_root>/<species>/input/{read_module,reference_module,reveal_module/*}/
    populated with a small, varied set of synthetic files:

      - IND001: one paired-end sample, R1/R2 naming
      - IND002: two paired-end samples ("lib1"/"lib2"), standalone _1/_2 naming
      - IND003: one single-end sample (R1 only, no R2)

    plus (by default) a read file with no recognizable R1/R2 marker and an uncompressed
    .fastq file, both of which the pipeline must discover-but-ignore.

    Returns a SpeciesLibrary describing exactly what was created, for use in assertions.
    """
    species_dir = os.path.join(project_root, species)
    reads_dir = os.path.join(species_dir, "input", "read_module")
    ref_dir = os.path.join(species_dir, "input", "reference_module")
    lib_dir = os.path.join(species_dir, "input", "reveal_module", "feature_library")
    scg_dir = os.path.join(species_dir, "input", "reveal_module", "scg")
    comp_dir = os.path.join(species_dir, "input", "reveal_module", "competition")

    lib = SpeciesLibrary(species, species_dir)

    # IND001: paired-end, R1/R2 naming
    write_fastq_gz(os.path.join(reads_dir, "IND001_R1.fastq.gz"))
    write_fastq_gz(os.path.join(reads_dir, "IND001_R2.fastq.gz"))
    lib.individuals.append("IND001")
    lib.samples["IND001"] = ["IND001"]

    # IND002: two samples, standalone _1/_2 naming
    for tag in ("lib1", "lib2"):
        write_fastq_gz(os.path.join(reads_dir, f"IND002_{tag}_1.fastq.gz"))
        write_fastq_gz(os.path.join(reads_dir, f"IND002_{tag}_2.fastq.gz"))
    lib.individuals.append("IND002")
    lib.samples["IND002"] = ["IND002_lib1", "IND002_lib2"]

    # IND003: single-end only
    write_fastq_gz(os.path.join(reads_dir, "IND003_R1.fastq.gz"))
    lib.individuals.append("IND003")
    lib.samples["IND003"] = ["IND003"]

    if include_unmatched_and_uncompressed:
        # No recognizable R1/R2/1/2 marker -> ignored by pairing, but still a *.fastq.gz match
        unmatched = os.path.join(reads_dir, "IND004_readme.fastq.gz")
        write_fastq_gz(unmatched)
        lib.unmatched_read_files.append(unmatched)

        # Uncompressed - the pipeline only picks up RAW_READ_EXTENSIONS (.fastq.gz/.fq.gz)
        uncompressed = os.path.join(reads_dir, "IND005_R1.fastq")
        write_plain_fastq(uncompressed)
        lib.uncompressed_read_files.append(uncompressed)

    # Reference genome(s)
    write_fasta(os.path.join(ref_dir, "genome.fasta"))
    lib.reference_ids.append("genome")
    if include_second_reference:
        write_fasta(os.path.join(ref_dir, "alt.assembly.v2.fa"))
        lib.reference_ids.append("alt_assembly_v2")

    # Feature library
    if include_feature_library:
        write_fasta(os.path.join(lib_dir, "te_features.fasta"))
        lib.feature_library_ids.append("te_features")
        if include_second_feature_library:
            write_fasta(os.path.join(lib_dir, "my.extra.lib.fa"))
            lib.feature_library_ids.append("my_extra_lib")

    if include_scg:
        write_fasta(os.path.join(scg_dir, "scg_markers.fasta"))
        lib.scg_ids.append("scg_markers")

    if include_competition:
        write_fasta(os.path.join(comp_dir, "competitor.fasta"))

    return lib


def materialize_reference_library(
    target_dir, species="Dmel", lineage="drosophilidae_odb12"
):
    """
    Builds a persistent, ready-to-run copy of the fixture under `target_dir` (a project
    root: config/ + a workflow/ symlink into this repo + <species>/), for a developer to
    manually point `snakemake --dryrun` at. Rebuilt from scratch on every call - not meant
    to be edited by hand. See tests/unit/build_test_library.py.
    """
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(os.path.join(target_dir, "config"))
    os.symlink(
        os.path.join(REPO_ROOT, "workflow"), os.path.join(target_dir, "workflow")
    )

    lib = build_species_library(
        target_dir, species=species, include_scg=False, include_competition=True
    )

    config_yaml = f"""# Auto-generated by tests/unit/build_test_library.py - do not edit by hand, it is rebuilt
# from scratch on every test run.
project_name: "pastForward_Test_Library"
species:
  {species}:
    name: "{species} (synthetic test library)"
    lineage: "{lineage}"
"""
    with open(os.path.join(target_dir, "config", "config.yaml"), "w") as f:
        f.write(config_yaml)

    return lib

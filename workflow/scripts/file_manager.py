
import os
import glob
import re
import logging

logger = logging.getLogger(__name__)

# Raised when the config requests individuals or references that do not exist on disk.
# Unlike generic discovery failures, these must not be silently caught.
class ConfigValidationError(Exception):
    pass

# -----------------------------------------------------------------------------------------------
# Read the config filter lists for a given species and key (e.g. "individuals", "references").
# Returns None when the key is absent/empty (meaning "use all").
def _get_species_config_list(species, key):
    try:
        value = config.get("species", {}).get(species, {}).get(key)
    except NameError:
        return None
    if not value:
        return None
    return list(value)

# -----------------------------------------------------------------------------------------------
# Get all files in a folder matching a specific pattern (e.g., *.fastq.gz)
def get_files_in_folder_matching_pattern(folder: str, pattern: str) -> list:
    # Check if the folder exists
    if not os.path.exists(folder):
        logger.warning(f"Invalid folder: {folder}")
        raise Exception(f"Invalid folder: {folder}")
    # Read all files matching the pattern into a list
    files = glob.glob(os.path.join(folder, pattern))
    return files

# -----------------------------------------------------------------------------------------------
# Get all FASTA-like files (.fna, .fasta, .fa) in a folder. Used wherever a reference/feature
# library/SCG/competition folder is scanned for its sequence files.
def _get_fasta_files_in_folder(folder: str) -> list:
    files = []
    for pattern in ("*.fna", "*.fasta", "*.fa"):
        files += get_files_in_folder_matching_pattern(folder, pattern)
    return files

# -----------------------------------------------------------------------------------------------
# Supported raw read file extensions, checked in this order wherever a raw file needs to be
# matched or resolved by its filename stem.
RAW_READ_EXTENSIONS = (".fastq.gz", ".fq.gz")

# -----------------------------------------------------------------------------------------------
# Human-readable description of the accepted raw read naming pattern, for use in error messages.
_RAW_READ_PATTERN_HINT = " or ".join(f"<Individual>*_R1*{ext} or <Individual>*_1*{ext}" for ext in RAW_READ_EXTENSIONS)

# -----------------------------------------------------------------------------------------------
# Get all raw read files for a given species
def get_read_files_for_species(species: str) -> list[str]:

    read_folder = f"{species}/input/read_module"

    try:
        logger.debug(f"Looking for read files in {read_folder} for species {species}.")
        read_files = []
        for ext in RAW_READ_EXTENSIONS:
            read_files += get_files_in_folder_matching_pattern(read_folder, f"*{ext}")
    except Exception as e:
        # Try looking in species folder directly as fallback.
        logger.debug(f"Read folder not found for species {species}. Trying species folder directly.")
        read_files = []
        for ext in RAW_READ_EXTENSIONS:
            read_files += get_files_in_folder_matching_pattern(species, f"*{ext}")

    if len(read_files) == 0:
        logger.warning(f"No read files found for species {species}. Make sure the files are named with the pattern {_RAW_READ_PATTERN_HINT} and are located in either {read_folder} or {species}.")
        raise Exception(f"No read files found for species {species}. Make sure the files are named with the pattern {_RAW_READ_PATTERN_HINT} and are located in either {read_folder} or {species}.")

    logger.debug(f"Read files for species {species}: {read_files}")

    return read_files

# -----------------------------------------------------------------------------------------------
# Strip a raw read file's compressed-FASTQ extension (see RAW_READ_EXTENSIONS) from a filename.
def strip_raw_read_extension(filename: str) -> str:
    for ext in RAW_READ_EXTENSIONS:
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return filename

# -----------------------------------------------------------------------------------------------
# Resolve the on-disk path of a raw read file given its filename stem (the filename with its
# compressed-FASTQ extension removed, see strip_raw_read_extension), trying each of
# RAW_READ_EXTENSIONS in turn.
def get_raw_read_path_for_stem(species: str, stem: str) -> str:
    reads_dir = f"{species}/input/read_module"
    for ext in RAW_READ_EXTENSIONS:
        candidate = os.path.join(reads_dir, f"{stem}{ext}")
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        f"No raw read file found for '{stem}' in {reads_dir} (tried extensions: {', '.join(RAW_READ_EXTENSIONS)})."
    )

# -----------------------------------------------------------------------------------------------
# (internal) Discover uncompressed *.fastq/*.fq files in a species' raw read folder (or the
# species folder directly, as a fallback - mirrors get_read_files_for_species). The pipeline only
# picks up the compressed extensions in RAW_READ_EXTENSIONS, so any bare uncompressed files found
# here are silently skipped during processing.
def _discover_uncompressed_fastq_files_for_species(species: str) -> list[str]:
    read_folder = f"{species}/input/read_module"
    uncompressed_patterns = ["*.fastq", "*.fq"]

    try:
        files = []
        for pattern in uncompressed_patterns:
            files += get_files_in_folder_matching_pattern(read_folder, pattern)
    except Exception:
        try:
            files = []
            for pattern in uncompressed_patterns:
                files += get_files_in_folder_matching_pattern(species, pattern)
        except Exception:
            files = []

    logger.debug(f"Uncompressed .fastq/.fq files found for species {species}: {files}")
    return files

# -----------------------------------------------------------------------------------------------
# Regexes matching the "read number" marker in a raw read filename: the conventional R1/R2
# token, or a bare 1/2 that stands alone as its own segment - bounded by underscores
# (e.g. "..._1_001.fastq.gz") or immediately preceding the extension (e.g. "..._1.fastq.gz").
# The lookahead boundary keeps a bare digit from matching inside a longer number, e.g.
# "_10_" or "_21.fastq.gz" are correctly ignored. Kept as two separate regexes (R-form vs.
# bare-form) rather than one combined pattern so the R-form can be preferred outright - sample
# names here often carry a bare replicate/box number (e.g. "..._B_1_box-1-22_R1.fastq.gz"),
# which must not be mistaken for the read marker when an explicit R1/R2 token exists.
_EXT_ALTERNATION = "|".join(re.escape(ext) for ext in RAW_READ_EXTENSIONS)
_READ_R_MARKER_RE = {
    "1": re.compile(rf"_R1(?=_|(?:{_EXT_ALTERNATION})$)"),
    "2": re.compile(rf"_R2(?=_|(?:{_EXT_ALTERNATION})$)"),
}
_READ_BARE_MARKER_RE = {
    "1": re.compile(rf"_1(?=_|(?:{_EXT_ALTERNATION})$)"),
    "2": re.compile(rf"_2(?=_|(?:{_EXT_ALTERNATION})$)"),
}

# -----------------------------------------------------------------------------------------------
# Find the read-number marker in a filename. Prefers an explicit R1/R2 token; only falls back
# to a bare 1/2 segment if no R-token is present *anywhere* in the filename - not just for the
# requested read_num. Otherwise a file like "..._1_box-3-227_R2.fastq.gz" (explicit R2, plus an
# unrelated bare "_1_" replicate/box number) would spuriously match a bare-form R1 marker on
# the replicate number, since checking read_num "1" alone never sees the "_R2" token that marks
# this file as already using the R-form convention. Raises ValueError if either form occurs more
# than once, since the marker position would then be ambiguous rather than just guessable.
# Returns the match object, or None if the filename has no marker for that read number.
def _find_read_marker(filename: str, read_num: str):
    r_matches = list(_READ_R_MARKER_RE[read_num].finditer(filename))
    if len(r_matches) > 1:
        raise ValueError(f"File '{filename}' has multiple R{read_num} markers; cannot determine read number unambiguously.")
    if r_matches:
        return r_matches[0]

    other_read_num = "2" if read_num == "1" else "1"
    if _READ_R_MARKER_RE[other_read_num].search(filename):
        return None

    bare_matches = list(_READ_BARE_MARKER_RE[read_num].finditer(filename))
    if len(bare_matches) > 1:
        raise ValueError(f"File '{filename}' has multiple standalone '{read_num}' markers; cannot determine read number unambiguously.")
    return bare_matches[0] if bare_matches else None

# -----------------------------------------------------------------------------------------------
# Why the pipeline can't use a raw read file name, or None if the name is fine. Shared by
# `pastForward check` (check.py) and `pastForward tools link-reads` (cli/tools.py), so both report
# exactly what discovery above does with the file.
def get_read_name_problem(filename: str):
    try:
        if _find_read_marker(filename, "1") or _find_read_marker(filename, "2"):
            return None
    except ValueError:
        return "more than one read marker, the pipeline stops with an error"
    return "no read marker, the pipeline ignores it"

# -----------------------------------------------------------------------------------------------
# (internal) Discover all R1 raw read files from disk without applying any config filter
def _discover_all_r1_read_files_for_species(species: str) -> list[str]:
    files = get_read_files_for_species(species)

    # since R1 and R2 files should always come in pairs, if there are no R1 files,
    # then there is probably something wrong with the file structure or naming.
    # Besides R1/R2, the name of the read files should be the same,
    # so we can just check for R1 files to build the list of samples and
    # individuals for a species.

    r1_files = [f for f in files if _find_read_marker(os.path.basename(f), "1")]

    if len(r1_files) == 0:
        logger.warning(f"No R1 read files found for species {species}. Make sure the files are named with the pattern {_RAW_READ_PATTERN_HINT}.")
        logger.warning(f"Available read files for species {species}: {files}")
        raise Exception(f"No R1 read files found for species {species}. Make sure the files are named with the pattern {_RAW_READ_PATTERN_HINT}.")

    logger.debug(f"Discovered R1 read files for species {species}: {r1_files}")

    return r1_files

# -----------------------------------------------------------------------------------------------
# (internal) Discover raw read files on disk whose names the pipeline can't use (see
# get_read_name_problem): no R1/R2 or standalone 1/2 marker, so they are ignored instead of
# being paired into a sample's reads, or more than one marker, which stops discovery with an error.
def _discover_unmatched_read_files_for_species(species: str) -> list[str]:
    try:
        files = get_read_files_for_species(species)
    except Exception:
        return []

    unmatched = [f for f in files if get_read_name_problem(os.path.basename(f))]

    logger.debug(f"Read files ignored (naming convention) for species {species}: {unmatched}")
    return unmatched

# -----------------------------------------------------------------------------------------------
# Get R1 raw read files for a given species, restricted to the individuals selected in the config
# (see get_individuals_for_species). Use _discover_all_r1_read_files_for_species when the
# unfiltered on-disk list is needed.
def get_r1_read_files_for_species(species: str) -> list[str]:
    all_r1_files = _discover_all_r1_read_files_for_species(species)

    selected_individuals = set(get_individuals_for_species(species))
    r1_files = [f for f in all_r1_files if get_individual_from_filepath(f) in selected_individuals]

    logger.debug(f"Config-filtered R1 read files for species {species}: {r1_files}")

    return r1_files

# -----------------------------------------------------------------------------------------------
# (internal) Discover all sample IDs from disk without applying any config filter
def _discover_all_sample_ids_for_species(species):
    files = _discover_all_r1_read_files_for_species(species)

    samples = []
    for raw_file in files:
        filename = os.path.basename(raw_file)
        marker = _find_read_marker(filename, "1")
        samples.append(filename[:marker.start()])

    logger.debug(f"Discovered sample IDs for species {species}: {samples}")

    if len(samples) == 0:
        logger.warning(f"No sample IDs found for species {species}.")
        raise Exception(f"No sample IDs found for species {species}.")

    return samples

# -----------------------------------------------------------------------------------------------
# Get sample IDs for a species based on raw read filenames, restricted to the individuals
# selected in the config (see get_individuals_for_species).
def get_sample_ids_for_species(species):
    all_samples = _discover_all_sample_ids_for_species(species)

    selected_individuals = set(get_individuals_for_species(species))
    samples = [s for s in all_samples if get_individual_from_sample(s) in selected_individuals]

    logger.debug(f"Config-filtered sample IDs for species {species}: {samples}")

    if len(samples) == 0:
        logger.warning(f"No sample IDs found for species {species} after applying the config individuals filter.")
        raise Exception(f"No sample IDs found for species {species} after applying the config individuals filter.")

    return samples

# -----------------------------------------------------------------------------------------------
# (internal) Filter read_files down to those belonging to `sample` for the given read number,
# i.e. files where the read marker (see _READ_R_MARKER_RE/_READ_BARE_MARKER_RE) is immediately preceded by `sample`.
def _read_files_for_sample(read_files, sample, read_num):
    matches = []
    for f in read_files:
        marker = _find_read_marker(f, read_num)
        if marker and f[:marker.start()] == sample:
            matches.append(f)
    return matches

def get_raw_reads_for_sample(species, sample):

    read_files = get_read_files_for_species(species)

    # turn read paths into file names only
    read_files = [os.path.basename(f) for f in read_files]

    reads_dir = f"{species}/input/read_module"

    # R1
    candidates_r1 = _read_files_for_sample(read_files, sample, "1")

    if not candidates_r1:
        logger.warning(f"No R1 found for {sample}. Expected pattern: {sample}_R1* or {sample}_1*, with extension {' or '.join(RAW_READ_EXTENSIONS)}, in {reads_dir}. Found files: {read_files}")
        raise FileNotFoundError(f"No R1 found for {sample}. Expected pattern: {sample}_R1* or {sample}_1*, with extension {' or '.join(RAW_READ_EXTENSIONS)}, in {reads_dir}. Found files: {read_files}")
    if len(candidates_r1) > 1:
        # Silently picking one (e.g. via sorted()[0]) would mean two different physical
        # files - almost certainly two different specimens/libraries - get merged into one
        # sample, with the other one silently dropped.
        raise ValueError(
            f"Sample {sample} has more than one R1 candidate, cannot pick unambiguously: {sorted(candidates_r1)}. "
            f"Rename these files so each individual/library has a distinct sample prefix "
            f"(e.g. append the box/replicate number to the individual ID) and re-run."
        )

    r1 = os.path.join(reads_dir, candidates_r1[0])

    # R2
    candidates_r2 = _read_files_for_sample(read_files, sample, "2")

    if not candidates_r2:
        return [r1]      # Single-end
    if len(candidates_r2) > 1:
        raise ValueError(
            f"Sample {sample} has more than one R2 candidate, cannot pick unambiguously: {sorted(candidates_r2)}. "
            f"Rename these files so each individual/library has a distinct sample prefix "
            f"(e.g. append the box/replicate number to the individual ID) and re-run."
        )

    r2 = os.path.join(reads_dir, candidates_r2[0])
    return [r1, r2]  # Paired-end

# -----------------------------------------------------------------------------------------------
# Given the path to a read 1 file, return the path its read 2 counterpart would have
# (whether or not that file actually exists on disk), by swapping the read-number marker
# (R1->R2, or a standalone 1->2).
def get_read2_counterpart_path(read1_path):
    directory = os.path.dirname(read1_path)
    filename = os.path.basename(read1_path)
    marker = _find_read_marker(filename, "1")
    if not marker:
        raise ValueError(f"File '{filename}' does not contain a recognizable read 1 marker (R1 or a standalone 1).")
    replacement = "_R2" if marker.group(0) == "_R1" else "_2"
    filename2 = filename[:marker.start()] + replacement + filename[marker.end():]
    return os.path.join(directory, filename2)

# -----------------------------------------------------------------------------------------------
# (internal) Discover all individuals from disk without applying any config filter
def _discover_all_individuals_for_species(species):
    # Must use the unfiltered sample list: get_sample_ids_for_species() filters by the
    # individuals computed here, which would otherwise recurse.
    samples = _discover_all_sample_ids_for_species(species)
    if len(samples) == 0:
        logger.warning(f"No samples found for species {species}.")
        raise Exception(f"No samples found for species {species}.")
    individuals = set()
    for s in samples:
        individuals.add(get_individual_from_sample(s))
    logger.debug(f"Discovered individuals for species {species}: {individuals}")
    return sorted(list(individuals))

# -----------------------------------------------------------------------------------------------
# Get individual sample IDs for a given species based on raw read filenames.
# If config specifies an 'individuals' list for this species, only those are returned.
# Raises ConfigValidationError when a requested individual is not found on disk.
def get_individuals_for_species(species):
    all_individuals = _discover_all_individuals_for_species(species)

    requested = _get_species_config_list(species, "individuals")
    if requested is None:
        return all_individuals

    all_set = set(all_individuals)
    missing = [ind for ind in requested if ind not in all_set]
    if missing:
        raise ConfigValidationError(
            f"Species '{species}': the following individuals were requested in the config "
            f"but not found on disk: {missing}. "
            f"Available individuals: {sorted(all_set)}"
        )

    selected = [ind for ind in all_individuals if ind in set(requested)]
    logger.debug(f"Config-filtered individuals for species {species}: {selected}")
    return selected

# -----------------------------------------------------------------------------------------------
# (internal) Discover all reference files from disk without applying any config filter
def _discover_all_reference_file_list_for_species(species: str) -> list[tuple[str, str]]:
    species_folder = species
    reference_folder = f"{species}/input/reference_module"
    try:
        logger.debug(f"Looking for reference files in {reference_folder} for species {species}.")
        reference_files = _get_fasta_files_in_folder(reference_folder)
    except Exception:
        logger.debug(f"Reference folder not found for species {species}. Trying species folder directly.")
        reference_files = _get_fasta_files_in_folder(species_folder)

    if len(reference_files) == 0:
        raise Exception(f"No reference found for species {species}.")

    result = [(os.path.splitext(os.path.basename(f))[0].replace('.', '_'), f) for f in reference_files]
    logger.debug(f"Discovered reference files for species {species}: {result}")
    return result

# -----------------------------------------------------------------------------------------------
# Get reference files for a given species (supports .fna, .fasta, .fa).
# If config specifies a 'references' list for this species, only those are returned.
# Reference IDs are the filename stem with dots replaced by underscores
# (e.g. 'genome.fna' → 'genome', 'EquCab3.0.fna' → 'EquCab3_0').
# Raises ConfigValidationError when a requested reference ID is not found on disk.
def get_reference_file_list_for_species(species: str) -> list[tuple[str, str]]:
    all_refs = _discover_all_reference_file_list_for_species(species)

    requested = _get_species_config_list(species, "references")
    if requested is None:
        return all_refs

    all_map = {ref_id: ref_path for ref_id, ref_path in all_refs}
    missing = [ref_id for ref_id in requested if ref_id not in all_map]
    if missing:
        raise ConfigValidationError(
            f"Species '{species}': the following references were requested in the config "
            f"but not found on disk: {missing}. "
            f"Available reference IDs: {sorted(all_map.keys())}"
        )

    selected = [(ref_id, all_map[ref_id]) for ref_id in requested]
    logger.debug(f"Config-filtered references for species {species}: {selected}")
    return selected

# -----------------------------------------------------------------------------------------------
# Extract individual ID from a given file path or sample name
def get_individual_from_filepath(filepath):
    basename = os.path.basename(filepath)
    return get_individual_from_sample(basename)

# -----------------------------------------------------------------------------------------------
# Extract individual ID from a sample name
def get_individual_from_sample(sample):
    return sample.split("_")[0]

# -----------------------------------------------------------------------------------------------
# Get only reference file paths for a species
def get_references_paths_for_species(species):
    refs = get_reference_file_list_for_species(species)
    return [ref[1] for ref in refs]

# -----------------------------------------------------------------------------------------------
# Get only reference IDs for a species
def get_references_ids_for_species(species):
    refs = get_reference_file_list_for_species(species)
    return [ref[0] for ref in refs]

# -----------------------------------------------------------------------------------------------
# Get sample IDs for a specific individual within a species
def get_samples_for_species_individual(species, individual):
    # Unfiltered on purpose: the caller already names the individual, so the config
    # individuals filter is redundant here and would only turn an explicitly requested
    # (but unselected) individual into an error.
    samples = _discover_all_sample_ids_for_species(species)

    # Currently, a sample is everything before the first read-number marker (see _READ_R_MARKER_RE/_READ_BARE_MARKER_RE)
    # in the filename, e.g. _R1/_R2 or a standalone _1/_2.
    # The first part of the sample name (before the first "_") is considered the individual ID.
    # The sample might contain additional information after the individual ID, 
    # but we only want to match the samples with the individual ID at the start of the sample name.
    samples_of_individual = [f for f in samples if f.startswith(f"{individual}_")]

    # in case there is no additional information after the individual ID, 
    # the sample name will be the same as the individual ID.
    samples_of_individual += [f for f in samples if f == individual]

    logger.debug(f"Samples for individual {individual} in species {species}: {samples_of_individual}")

    if len(samples_of_individual) == 0:
        logger.warning(f"No samples found for individual {individual} in species {species}. Available samples: {samples}")
        raise Exception(f"No samples found for individual {individual} in species {species}.")
    
    return samples_of_individual

# -----------------------------------------------------------------------------------------------
# (internal) Discover all feature library files from disk without applying any config filter
def _discover_all_feature_library_file_list_for_species(species: str) -> list[tuple[str, str]]:
    species_folder = species
    feature_library_folder = f"{species_folder}/input/reveal_module/feature_library"
    library_files = []
    try:
        logger.debug(f"Looking for feature library files in {feature_library_folder} for species {species}.")
        library_files = _get_fasta_files_in_folder(feature_library_folder)
    except Exception as e:
        logger.warning(f"Failed to find feature library files in {feature_library_folder} for species {species}. Exception: {e}")

    if len(library_files) == 0:
        raise Exception(f"No feature library files found for species {species}.")

    result = [(os.path.splitext(os.path.basename(f))[0].replace('.', '_'), f) for f in library_files]
    logger.debug(f"Discovered feature library files for species {species}: {result}")
    return result

# -----------------------------------------------------------------------------------------------
# Get feature library files for a given species (supports .fna, .fasta, .fa).
# If config specifies a 'feature_libraries' list for this species, only those are returned.
# Library IDs are the filename stem with dots replaced by underscores
# (e.g. 'genes.fna' → 'genes', 'my.lib.fna' → 'my_lib').
# Raises ConfigValidationError when a requested library ID is not found on disk.
def get_feature_library_file_list_for_species(species: str) -> list[tuple[str, str]]:
    all_libs = _discover_all_feature_library_file_list_for_species(species)

    requested = _get_species_config_list(species, "feature_libraries")
    if requested is None:
        return all_libs

    all_map = {lib_id: lib_path for lib_id, lib_path in all_libs}
    missing = [lib_id for lib_id in requested if lib_id not in all_map]
    if missing:
        raise ConfigValidationError(
            f"Species '{species}': the following feature libraries were requested in the config "
            f"but not found on disk: {missing}. "
            f"Available feature library IDs: {sorted(all_map.keys())}"
        )

    selected = [(lib_id, all_map[lib_id]) for lib_id in requested]
    logger.debug(f"Config-filtered feature libraries for species {species}: {selected}")
    return selected

# -----------------------------------------------------------------------------------------------
# Get only reference file paths for a species
def get_feature_library_paths_for_species(species):
    refs = get_feature_library_file_list_for_species(species)
    return [ref[1] for ref in refs]

# -----------------------------------------------------------------------------------------------
# Get only reference IDs for a species
def get_feature_library_ids_for_species(species):
    refs = get_feature_library_file_list_for_species(species)
    return [ref[0] for ref in refs]

# -----------------------------------------------------------------------------------------------
# Get scg library files for a given species (supports .fna, .fasta, .fa)
# Returns an empty list when nothing is found (no exception) so callers can
# distinguish "user provided none" from an unexpected error.
def get_scg_library_file_list_for_species(species: str) -> list[tuple[str, str]]:
    # Construct reference folder path
    species_folder = species

    scg_library_folder = os.path.join(f"{species_folder}/input/reveal_module/scg")
    library_files = []
    try:
        # Collect all supported reference files
        logger.debug(f"Looking for SCG library files in {scg_library_folder} for species {species}.")

        library_files = _get_fasta_files_in_folder(scg_library_folder)
    except Exception as e:
        logger.debug(f"Failed to find SCG library files in {scg_library_folder} for species {species}. Exception: {e}")

    if len(library_files) == 0:
        logger.debug(f"No user-provided SCG library files found for species {species}.")
        return []

    # Return as list of tuples: (filename without extension, full path)
    library_files_with_filename = [(get_cleaned_feature_library_id_for_library_path(f), f) for f in library_files]

    logger.debug(f"SCG library files for species {species}: {library_files_with_filename}")

    return library_files_with_filename

# -----------------------------------------------------------------------------------------------
# Get only scg library file paths for a species
def get_scg_library_paths_for_species(species):
    refs = get_scg_library_file_list_for_species(species)
    return [ref[1] for ref in refs] 

# -----------------------------------------------------------------------------------------------
# Get only scg library IDs for a species  
def get_scg_library_ids_for_species(species):
    refs = get_scg_library_file_list_for_species(species)
    return [ref[0] for ref in refs]

# -----------------------------------------------------------------------------------------------
# Get cleaned feature library ID for a given feature library path
def get_cleaned_feature_library_id_for_library_path(feature_library_path):
    return os.path.splitext(os.path.basename(feature_library_path))[0].replace('.', '_')

# -----------------------------------------------------------------------------------------------
# Get feature library file for a given species and library ID
def get_feature_library_file_for_species_and_library(species, library_id):
    libraries = get_feature_library_file_list_for_species(species)
    for lib in libraries:
        if lib[0] == library_id:
            return lib[1]
    logger.error(f"Feature library with ID {library_id} not found for species {species}. Available libraries: {libraries}")
    raise Exception(f"Feature library with ID {library_id} not found for species {species}.")

# -----------------------------------------------------------------------------------------------
# Get scg library file for a given species and library ID
def get_scg_library_file_for_species_and_library(species, library_id):
    libraries = get_scg_library_file_list_for_species(species)
    for lib in libraries:
        if lib[0] == library_id:
            return lib[1]
    logger.warning(f"SCG library with ID {library_id} not found for species {species}. Available libraries: {libraries}")
    raise ValueError(f"SCG library with ID {library_id} not found for species {species}.")

# -----------------------------------------------------------------------------------------------
# Resolve the reference genome path that SCG determination (BUSCO) will use.
# Priority: species.{species}.scg_reference → auto-detect from {species}/input/reference_module/
# Raises ValueError when 0 or >1 references are found without an explicit config override.
def get_scg_determination_reference_path(species):
    import logging as _log
    config_ref = config.get("species", {}).get(species, {}).get("scg_reference")
    if config_ref:
        return config_ref

    refs = get_reference_file_list_for_species(species)

    if len(refs) == 0:
        raise ValueError(
            f"No reference genome found for SCG determination of species '{species}'. "
            f"Place a FASTA in {species}/input/reference_module/ or set "
            f"species.{species}.scg_reference in config."
        )

    if len(refs) > 1:
        ref_paths = ", ".join(r[1] for r in refs)
        raise ValueError(
            f"Multiple reference genomes found for species '{species}' ({ref_paths}). "
            f"SCG determination requires exactly one reference. "
            f"Please set species.{species}.scg_reference in config."
        )

    _log.info(f"[SCG Selector] Auto-detected reference for '{species}': {refs[0][1]}")
    return refs[0][1]

# -----------------------------------------------------------------------------------------------
# Return True when all of the following hold:
#   1. scg_selector.execute is true in pipeline config
#   2. No user-provided SCG FASTA exists in {species}/input/reveal_module/scg/
#   3. A BUSCO lineage is configured for the species (required to run BUSCO)
def should_auto_determine_scg(species):
    if not config.get("pipeline", {}).get("reveal_module", {}).get("scg_selector", {}).get("execute", True):
        return False
    if get_scg_library_file_list_for_species(species):
        return False
    lineage = config.get("species", {}).get(species, {}).get("lineage")
    return bool(lineage)

# -----------------------------------------------------------------------------------------------
# Return the SCG library ID to use: user-provided ID or the auto-determined sentinel.
def get_effective_scg_library_id_for_species(species):
    user_scgs = get_scg_library_file_list_for_species(species)
    if user_scgs:
        return user_scgs[0][0]
    return f"{species}_determined_scg"

# -----------------------------------------------------------------------------------------------
# Return the FASTA path for the SCG library: user-provided or auto-determined.
def get_effective_scg_library_path_for_species(species):
    user_scgs = get_scg_library_file_list_for_species(species)
    if user_scgs:
        return user_scgs[0][1]
    return f"{species}/results/reveal_module/scg/{species}_relevant_scg.fasta"

# -----------------------------------------------------------------------------------------------
# Get the competition FASTA file for a species from {species}/input/reveal_module/competition/.
# Returns None when no file is found (competitive mapping not configured).
# Raises ValueError when more than one FASTA is found.
def get_competition_fasta_for_species(species):
    competition_folder = f"{species}/input/reveal_module/competition"
    files = []
    try:
        logger.debug(f"Looking for competition FASTA in {competition_folder} for species {species}.")
        files = _get_fasta_files_in_folder(competition_folder)
    except Exception as e:
        logger.debug(f"No competition folder found for species {species}: {e}")
        return None

    if len(files) == 0:
        logger.debug(f"No competition FASTA found for species {species}.")
        return None

    if len(files) > 1:
        raise ValueError(
            f"Multiple competition FASTA files found for species '{species}' in {competition_folder}. "
            f"Please provide exactly one FASTA file: {files}"
        )

    logger.debug(f"Competition FASTA for species {species}: {files[0]}")
    return files[0]
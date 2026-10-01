import os
import sys
import logging
from typing import List, Tuple
import pysam
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)


def extract_busco_sequences(df, reference_fasta, min_length_scg, max_length_scg) -> List[Tuple[str, str]]:
    fasta_entries = []

    with pysam.FastaFile(reference_fasta) as fasta:
        for i, row in df.iterrows():
            try:
                busco_id = row["Busco_id"]
                chrom = row["Sequence"]
                start = int(row["Gene_Start"])
                end = int(row["Gene_End"])
                strand = row["Strand"]

                if pd.isna(chrom) or pd.isna(start) or pd.isna(end):
                    logger.warning(f"Skipping {busco_id}: missing coordinates.")
                    continue

                if strand == "-":
                    start, end = end, start

                if end - start <= min_length_scg:
                    logger.warning(f"Skipping {busco_id}: length {end - start} is less than minimum length ({min_length_scg}).")
                    continue

                if end - start >= max_length_scg:
                    logger.warning(f"Skipping {busco_id}: length {end - start} exceeds maximum length ({max_length_scg}).")
                    continue

                seq = extract_sequence(fasta, chrom, start, end)
                header = f"{busco_id}_{chrom}_{start}_{end}_scg"
                fasta_entries.append((header, seq))

            except Exception as e:
                logger.error(f"Error processing {busco_id}: {e}")

    return fasta_entries


def extract_sequence(fasta: pysam.FastaFile, chrom: str, start: int, end: int) -> str:
    try:
        sequence = fasta.fetch(chrom, start, end)
    except Exception as e:
        raise RuntimeError(f"Could not extract {chrom}:{start}-{end} from FASTA: {e}")
    return sequence


def write_multi_fasta(out_file: str, entries: List[Tuple[str, str]]):
    with open(out_file, "w") as f:
        for header, seq in entries:
            f.write(f">{header}\n{seq}\n")


full_table_path = snakemake.input.busco_full_table
# ref_genome may be a string (single file) or a list — handle both
ref_genome = snakemake.input.ref_genome
reference_fasta = ref_genome[0] if isinstance(ref_genome, (list, tuple)) else ref_genome
min_length_scg = snakemake.params.min_length_scg
max_length_scg = snakemake.params.max_length_scg
out_file = snakemake.output.scg

if not os.path.isfile(full_table_path):
    raise ValueError(f"full_table.tsv not found: {full_table_path}")

if not os.path.isfile(reference_fasta):
    raise ValueError(f"Reference FASTA not found: {reference_fasta}")

# Read BUSCO full_table.tsv, skipping comment lines
df = pd.read_csv(
    full_table_path,
    sep='\t',
    comment='#',
    header=None,
    names=[
        "Busco_id", "Status", "Sequence", "Gene_Start", "Gene_End",
        "Strand", "Score", "Length", "OrthoDB_url", "Description"
    ],
    dtype=str
)

df = df[df["Status"].str.contains("Complete", na=False)]

fasta_entries = extract_busco_sequences(df, reference_fasta, min_length_scg, max_length_scg)

logger.info(f"Extracted {len(fasta_entries)} SCG sequences from BUSCO results.")

write_multi_fasta(out_file, fasta_entries)
logger.info(f"Sequences written to: {out_file}")

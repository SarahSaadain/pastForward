import pysam
import numpy as np
import logging
import sys
import json

bam_file = snakemake.input.bam
log_filename = snakemake.log[0]
stats_file = snakemake.output.stats

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(log_filename)],
)
logger = logging.getLogger(__name__)


def stats_from_array(depths: np.ndarray, length: int, contig: str) -> dict:
    if len(depths) != length:
        logger.warning(
            f"Contig {contig}: expected {length} positions, got {len(depths)}"
        )

    return {
        "min_depth": int(depths.min()),
        "avg_depth": float(depths.mean()),
        "median_depth": float(np.median(depths)),
        "max_depth": int(depths.max()),
        "length": length,
        "covered_bases": int(np.count_nonzero(depths)),
        "breadth": float(np.count_nonzero(depths) / length),
    }


def compute_all_contig_stats(bam_path: str) -> dict:
    """Compute coverage stats for every contig in the BAM using count_coverage()."""
    scg_stats = {}

    with pysam.AlignmentFile(bam_path, "rb") as bam:
        contig_lengths = dict(zip(bam.references, bam.lengths))
        contig_count = len(contig_lengths)
        logger.info(f"Processing {contig_count} contigs")

        for i, (contig, length) in enumerate(contig_lengths.items(), start=1):
            logger.info(f"[{i}/{contig_count}] Processing contig {contig}")

            if length == 0:
                logger.warning(
                    f"[{i}/{contig_count}] Contig {contig} has length 0, skipping"
                )
                scg_stats[contig] = {
                    "min_depth": 0,
                    "avg_depth": 0.0,
                    "median_depth": 0.0,
                    "max_depth": 0,
                    "length": 0,
                    "covered_bases": 0,
                    "breadth": 0.0,
                }
                continue

            # quality_threshold=0 disables base quality filtering, consistent with samtools depth -q 0
            a, c, g, t = bam.count_coverage(
                contig, start=0, stop=length, quality_threshold=0, read_callback="all"
            )
            depths = np.array(a) + np.array(c) + np.array(g) + np.array(t)
            scg_stats[contig] = stats_from_array(depths, length, contig)
            logger.info(
                f"[{i}/{contig_count}] {contig}: "
                f"min={scg_stats[contig]['min_depth']}, "
                f"avg={scg_stats[contig]['avg_depth']:.2f}, "
                f"median={scg_stats[contig]['median_depth']:.2f}, "
                f"max={scg_stats[contig]['max_depth']}, "
                f"breadth={scg_stats[contig]['breadth']:.4f}"
            )

    return scg_stats


logger.info(f"Processing BAM: {bam_file}")
scg_stats = compute_all_contig_stats(bam_file)

with open(stats_file, "w") as f:
    json.dump(scg_stats, f, indent=2)

logger.info(f"SCG stats for {bam_file} saved to {stats_file}")

import json
import numpy as np
import logging
import sys
from collections import defaultdict

logger = logging.getLogger(__name__)


def rank_scgs(scg_stats_per_individual):
    """Rank SCGs across individuals (steps 2 to 5).

    scg_stats_per_individual: {stats_file: {scg: per-BAM stats dict}}, in input order.
    Returns the ranking JSON dict; its "scgs" entries are in rank order (best first).
    """
    stats_files = list(scg_stats_per_individual)
    scg_stats_per_bam = list(scg_stats_per_individual.values())

    # ─────────────────────────────────────────────────────────────────────────────
    # STEP 2: Aggregate stats across all individuals
    # ─────────────────────────────────────────────────────────────────────────────
    logger.info("Aggregating SCG stats across individuals...")

    scg_aggregated = defaultdict(list)
    for stats_file, scg_stats in zip(stats_files, scg_stats_per_bam):
        for scg, stats in scg_stats.items():
            stats["source_file"] = stats_file
            scg_aggregated[scg].append(stats)

    # ─────────────────────────────────────────────────────────────────────────────
    # STEP 2.5: Compute per-individual depth baselines
    # Each individual's baseline = median depth across all SCGs for that individual.
    # Using the median (not mean) keeps multi-copy gene outliers from inflating the
    # baseline, so normalization targets the single-copy majority.
    # ─────────────────────────────────────────────────────────────────────────────
    logger.info("Computing per-individual depth baselines...")

    individual_baselines = {}
    for stats_file, scg_stats in zip(stats_files, scg_stats_per_bam):
        depths = [s["median_depth"] for s in scg_stats.values()]
        baseline = float(np.median(depths)) if depths else 1.0
        if baseline == 0:
            baseline = 1.0
        individual_baselines[stats_file] = baseline
        logger.info(f"Individual baseline [{stats_file}]: {baseline:.4f}")

    # ─────────────────────────────────────────────────────────────────────────────
    # STEP 3: Compute summary metrics per SCG across all individuals
    # Depths are normalized by each individual's baseline before aggregation so
    # that coverage differences across individuals do not bias the comparison.
    # A depth_ratio of 1.0 means "covered at the expected SCG level."
    # ─────────────────────────────────────────────────────────────────────────────
    logger.info("Computing metrics across individuals...")
    scg_summary = {}
    for scg, values in scg_aggregated.items():
        logger.info(f"Processing SCG: {scg}; Number of individuals: {len(values)}")

        samples_min_depths    = [v["min_depth"] for v in values]
        samples_median_depths = [v["median_depth"] for v in values]
        samples_avg_depths    = [v["avg_depth"] for v in values]
        samples_max_depths    = [v["max_depth"] for v in values]
        length                = values[0]["length"]
        samples_covered_bases = [v["covered_bases"] for v in values]
        samples_breadths      = [v["breadth"] for v in values]
        source_files          = [v["source_file"] for v in values]

        samples_baselines    = [individual_baselines[v["source_file"]] for v in values]
        samples_depth_ratios = [v["median_depth"] / b for v, b in zip(values, samples_baselines)]
        samples_norm_maxes   = [v["max_depth"]    / b for v, b in zip(values, samples_baselines)]

        mean_avg_depth    = np.mean(samples_avg_depths)
        mean_median_depth = np.mean(samples_median_depths)
        mean_depth_ratio  = float(np.mean(samples_depth_ratios))
        # max_variation is now the ratio of the worst per-individual peak to the
        # mean normalized depth — computed entirely in normalized space.
        max_variation     = max(samples_norm_maxes) / mean_depth_ratio if mean_depth_ratio > 0 else 99
        mean_breadth      = np.mean(samples_breadths)

        scg_summary[scg] = {
            "samples": len(values),
            "source_files": source_files,
            "per_sample": {
                source_files[i]: {
                    "min_depth":     samples_min_depths[i],
                    "median_depth":  samples_median_depths[i],
                    "avg_depth":     samples_avg_depths[i],
                    "max_depth":     samples_max_depths[i],
                    "covered_bases": samples_covered_bases[i],
                    "breadth":       samples_breadths[i],
                    "baseline":      round(samples_baselines[i], 4),
                    "depth_ratio":   round(samples_depth_ratios[i], 4),
                }
                for i in range(len(values))
            },
            "length":           length,
            "min_depth":        min(samples_min_depths),
            "max_depth":        max(samples_max_depths),
            "mean_depth":       round(mean_avg_depth, 4),
            "median_depth":     round(mean_median_depth, 4),
            "mean_depth_ratio": round(mean_depth_ratio, 4),
            "per_sample_min_depths":    samples_min_depths,
            "per_sample_avg_depths":    samples_avg_depths,
            "per_sample_max_depths":    samples_max_depths,
            "per_sample_median_depths": samples_median_depths,
            "per_sample_depth_ratios":  [round(r, 4) for r in samples_depth_ratios],
            "per_sample_baselines":     [round(b, 4) for b in samples_baselines],
            "per_sample_breadths":      samples_breadths,
            "per_sample_covered_bases": samples_covered_bases,
            "max_variation":  round(max_variation, 4),
            "mean_breadth":   round(mean_breadth, 4),
        }

        logger.info(
            f"SCG metrics computed. Min depth: {scg_summary[scg]['min_depth']}; "
            f"Mean depth ratio: {mean_depth_ratio:.4f}; "
            f"Breadth: {scg_summary[scg]['mean_breadth']}"
        )

    # ─────────────────────────────────────────────────────────────────────────────
    # STEP 4: Compute MAD of normalized depth ratios
    # The reference is 1.0 by construction (individual baselines derived from all
    # SCGs via median, so true SCGs cluster at 1.0; multi-copy genes sit above).
    # MAD is computed relative to 1.0 to calibrate the consistency penalty.
    # ─────────────────────────────────────────────────────────────────────────────
    logger.info("Computing MAD of normalized depth ratios...")

    all_depth_ratios = np.array([v["mean_depth_ratio"] for v in scg_summary.values()])
    mad_ratio = float(np.median(np.abs(all_depth_ratios - 1.0)))

    logger.info(f"Depth ratio reference: 1.0 (MAD: {mad_ratio:.4f})")

    # ─────────────────────────────────────────────────────────────────────────────
    # STEP 5: Score each SCG
    # ─────────────────────────────────────────────────────────────────────────────
    depth_variance_decay   = 0.15
    depth_consistency_decay = 4

    scg_scores = {}
    for scg, vals in scg_summary.items():
        logger.info(f"Scoring SCG: {scg}")

        score_breadth = vals["mean_breadth"]
        score_depth_variation = np.exp(-vals["max_variation"] * depth_variance_decay)
        depth_deviation = abs(vals["mean_depth_ratio"] - 1.0) / (mad_ratio + 1e-9)
        score_depth_consistency = np.exp(-depth_deviation / depth_consistency_decay)
        score = score_breadth + score_depth_variation + score_depth_consistency

        logger.info(
            f"SCG: {scg}; Breadth: {score_breadth:.3f}; "
            f"Depth variation: {score_depth_variation:.3f}; "
            f"Depth consistency: {score_depth_consistency:.3f}; "
            f"Total: {score:.3f}"
        )

        scg_scores[scg] = score
        scg_summary[scg]["scoring"] = {
            "normalization_reference": 1.0,
            "global_mad_ratio":        round(float(mad_ratio), 4),
            "depth_variance_decay":    depth_variance_decay,
            "depth_consistency_decay": depth_consistency_decay,
            "depth_deviation":         round(float(depth_deviation), 4),
            "score_breadth":           round(float(score_breadth), 4),
            "score_depth_variation":   round(float(score_depth_variation), 4),
            "score_depth_consistency": round(float(score_depth_consistency), 4),
            "score_scg":               round(float(score), 4),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6a: Rank SCGs
    # ─────────────────────────────────────────────────────────────────────────
    top_scgs = sorted(scg_scores.items(), key=lambda x: x[1], reverse=True)

    return {
        "global_stats": {
            "normalization":           "per_individual_median",
            "normalization_reference": 1.0,
            "mad_ratio":               round(float(mad_ratio), 4),
            "decay":                   depth_variance_decay,
            "n_scgs":                  len(scg_summary),
            "n_individuals":           len(stats_files),
            "individual_baselines":    {f: round(b, 4) for f, b in individual_baselines.items()},
        },
        "scgs": {scg: scg_summary[scg] for scg, _ in top_scgs}
    }


if __name__ == "__main__":
    stats_files = snakemake.input.stats
    summary_file = snakemake.output.ranked_tsv
    json_file = snakemake.output.ranked_json
    log_filename = snakemake.log[0]

    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(log_filename)]
    )

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: Load per-individual SCG stats
    # ─────────────────────────────────────────────────────────────────────────
    logger.info(f"Loading SCG stats from {len(stats_files)} files...")

    scg_stats_per_individual = {}
    for stats_file in stats_files:
        with open(stats_file) as f:
            scg_stats_per_individual[stats_file] = json.load(f)

    json_output = rank_scgs(scg_stats_per_individual)

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6b: Write outputs
    # ─────────────────────────────────────────────────────────────────────────
    logger.info("Writing TSV ranking...")
    with open(summary_file, "w") as f:
        f.write("scg_name\tsamples\tmean_depth_ratio\tdepth_variation\tmean_breadth\tscore_breadth\tscore_depth_variation\tscore_depth_consistency\tscore\n")
        for scg, stats in json_output["scgs"].items():
            s = stats["scoring"]
            f.write(
                f"{scg}\t{stats['samples']}\t{stats['mean_depth_ratio']:.4f}\t"
                f"{stats['max_variation']:.2f}\t{stats['mean_breadth']:.3f}\t"
                f"{s['score_breadth']:.3f}\t{s['score_depth_variation']:.3f}\t"
                f"{s['score_depth_consistency']:.3f}\t{s['score_scg']:.3f}\n"
            )

    logger.info("Writing JSON ranking...")
    with open(json_file, "w") as f:
        json.dump(json_output, f, indent=2)

    logger.info("Done.")

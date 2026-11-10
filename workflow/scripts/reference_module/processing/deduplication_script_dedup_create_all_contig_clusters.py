import heapq
import os
import logging

# The Snakemake script preamble injects `logger`; fall back to stdlib logging when imported.
if "logger" not in globals():
    logger = logging.getLogger(__name__)


def create_contig_clusters(idxstats_path, cluster_folder, cores=1):
    """
    Pack whole contigs into at most `cores` clusters with about the same number of reads.

    Reads per contig come from `samtools idxstats` (mapped + unmapped; unmapped reads with a
    mapped mate are listed under their mate's contig). Greedy largest-first: each contig goes
    into the cluster with the fewest reads so far, so big contigs end up in separate clusters
    and small ones fill the gaps. Contigs without reads and the '*' line (unplaced reads) are
    left out. A contig is never split, so the largest contig sets the lower bound for the
    slowest cluster.

    Writes cluster_1.bed .. cluster_N.bed (name, 0, length; contigs in idxstats order).
    """
    logger.info("Starting contig clustering for deduplication...")

    contigs = []  # (index, name, length, reads)
    with open(idxstats_path) as f:
        for index, line in enumerate(f):
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 4 or fields[0] == "*":
                continue
            name, length, mapped, unmapped = fields[:4]
            contigs.append((index, name, int(length), int(mapped) + int(unmapped)))

    if not contigs:
        raise ValueError(f"No contigs in {idxstats_path}, is the BAM header empty?")

    with_reads = [c for c in contigs if c[3] > 0]
    logger.info(
        f"Contigs: {len(contigs)}, with reads: {len(with_reads)}, cores: {cores}"
    )

    if with_reads:
        num_clusters = min(cores, len(with_reads))
        clusters = [[] for _ in range(num_clusters)]
        heap = [(0, i) for i in range(num_clusters)]  # (reads so far, cluster)
        # ties broken by idxstats order and cluster number, so every run gives the same result
        for contig in sorted(with_reads, key=lambda c: (-c[3], c[0])):
            reads, i = heapq.heappop(heap)
            clusters[i].append(contig)
            heapq.heappush(heap, (reads + contig[3], i))
    else:
        # no reads at all: one cluster with every contig, so dedup still runs once
        clusters = [contigs]

    os.makedirs(cluster_folder, exist_ok=True)
    for i, cluster in enumerate(clusters, start=1):
        group_file = os.path.join(cluster_folder, f"cluster_{i}.bed")
        reads = sum(c[3] for c in cluster)
        logger.info(f"Writing {group_file}: {len(cluster)} contigs, {reads} reads")
        with open(group_file, "w") as out:
            out.writelines(
                f"{name}\t0\t{length}\n" for _, name, length, _ in sorted(cluster)
            )

    logger.info("Contig clustering completed successfully.")


if __name__ == "__main__":
    create_contig_clusters(
        snakemake.input.idxstats,
        snakemake.output.cluster_folder,
        cores=snakemake.params.get("cores", 1),
    )

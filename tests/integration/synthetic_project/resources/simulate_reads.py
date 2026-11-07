#!/usr/bin/env python3
"""Simulate the tier-1 paired-end test reads (fixed seed, stdlib only).

Usage: simulate_reads.py <reference.fa> <te_library.fa> <human_mito.fa> <ecoli.fa> <out_dir>

Two individuals with known answers:
  HistA  historical: short fragments (mean ~45 bp), C>T at 5' and G>A at 3' ends (~28% at the
         terminal base, decaying inward), ~20% PCR duplicates, ~2% human mito and ~2% E. coli reads.
  ModB   modern: 150-250 bp fragments, no damage, ~2% duplicates, no spike-ins.
Every reference contig is covered at DEPTH; each TE at copies x DEPTH (copies in TE_COPIES).
"""
import gzip
import math
import random
import sys

SEED = 20261107
DEPTH = 6
READ_LEN = 100
ERROR_RATE = 0.001
# TruSeq adapters followed by the rest of the read-through, as fastp sees them.
ADAPTER = {1: "AGATCGGAAGAGCACACGTCTGAACTCCAGTCACATCACGATCTCGTATGCCGTCTTCTGCTTG" + "A" * 40,
           2: "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGTAGATCTCGGTGGTCGCCGTATCATT" + "A" * 50}
TE_COPIES = {"jockey": {"HistA": 1, "ModB": 1},
             "opus": {"HistA": 0, "ModB": 4},
             "roo": {"HistA": 2, "ModB": 6}}
SAMPLES = {
    "HistA": dict(frag=lambda r: min(150, max(30, round(r.lognormvariate(math.log(45) - 0.045, 0.3)))),
                  damage=0.28, dup=0.20, spikes={"human": 0.02, "ecoli": 0.02}),
    "ModB": dict(frag=lambda r: r.randint(150, 250), damage=0.0, dup=0.02, spikes={}),
}
COMP = str.maketrans("ACGTN", "TGCAN")


def read_fasta(path):
    seqs, name = {}, None
    for line in open(path):
        line = line.strip()
        if line.startswith(">"):
            name = line[1:].split()[0]
            seqs[name] = []
        elif line:
            seqs[name].append(line.upper())
    return {k: "".join(v) for k, v in seqs.items()}


def rc(s):
    return s.translate(COMP)[::-1]


def damage(frag, rate, r):
    """C>T near the 5' end and G>A near the 3' end of the double-stranded molecule."""
    if not rate:
        return frag
    s = list(frag)
    for i in range(min(15, len(s))):
        p = rate * 0.55 ** i
        if s[i] == "C" and r.random() < p:
            s[i] = "T"
        j = len(s) - 1 - i
        if s[j] == "G" and r.random() < p:
            s[j] = "A"
    return "".join(s)


def sequence(read, r):
    return "".join(r.choice("ACGT".replace(b, "")) if r.random() < ERROR_RATE else b for b in read)


def molecules(seq, n, cfg, r):
    for _ in range(n):
        length = min(cfg["frag"](r), len(seq))
        start = r.randint(0, len(seq) - length)
        frag = seq[start:start + length]
        if r.random() < 0.5:
            frag = rc(frag)
        yield damage(frag, cfg["damage"], r)


def simulate(name, cfg, ref, tes, spikes, out_dir, r):
    rng = random.Random(1)
    mean_frag = sum(cfg["frag"](rng) for _ in range(2000)) / 2000
    mols = []
    for seq in ref.values():
        mols += molecules(seq, round(DEPTH * len(seq) / mean_frag), cfg, r)
    for te, seq in tes.items():
        mols += molecules(seq, round(TE_COPIES[te][name] * DEPTH * len(seq) / mean_frag), cfg, r)
    base = len(mols)
    for spike, frac in cfg["spikes"].items():
        mols += molecules(spikes[spike], round(base * frac), cfg, r)
    mols += [r.choice(mols) for _ in range(round(len(mols) * cfg["dup"] / (1 - cfg["dup"])))]
    r.shuffle(mols)
    outs = {m: gzip.GzipFile(f"{out_dir}/{name}_R{m}.fastq.gz", "wb", mtime=0) for m in (1, 2)}
    qual = "F" * READ_LEN
    for i, frag in enumerate(mols, 1):
        for mate, strand in ((1, frag), (2, rc(frag))):
            read = sequence((strand + ADAPTER[mate])[:READ_LEN], r)
            outs[mate].write(f"@{name}_{i} {mate}:N:0:1\n{read}\n+\n{qual}\n".encode())
    for fh in outs.values():
        fh.close()
    print(f"{name}: {len(mols)} read pairs ({base} genome/TE molecules)", file=sys.stderr)


def main(ref_fa, te_fa, human_fa, ecoli_fa, out_dir):
    r = random.Random(SEED)
    ref, tes = read_fasta(ref_fa), read_fasta(te_fa)
    assert set(tes) == set(TE_COPIES), f"TE library must hold exactly {sorted(TE_COPIES)}"
    spikes = {"human": "".join(read_fasta(human_fa).values()), "ecoli": "".join(read_fasta(ecoli_fa).values())}
    for name, cfg in SAMPLES.items():
        simulate(name, cfg, ref, tes, spikes, out_dir, r)


if __name__ == "__main__":
    main(*sys.argv[1:])

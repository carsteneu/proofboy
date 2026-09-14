#!/usr/bin/env python3
"""Rank chain of the orbit-specific linear compression (L) for Antihydra.

The candidate (L) of the Astra lemma loop postulates i-independent rational
coefficients c_0, ..., c_{d-1} with

    D(i,4+d) = sum_{r<d} c_r D(i,4+r)   for all i >= 4,

where D(i,k) = C(i,k+2) - 4*C(i,k) is the scale defect and C(i,k) =
5*E(i,k) - 2*L_k the reserve of the L_k = 1024*2^k step block
[i*L_k, (i+1)*L_k) (E = number of even steps).  (L) holds iff the matrix
H_{i,m} = D(i,4+m)/5, i = 4..4+d, m = 0..d, is singular; a nonzero
determinant - certified by a nonzero residue modulo one prime - excludes
it for the tested window of rows.

The block counters come from the deep divide-and-conquer engine
(bemyself/experiments/antihydra_deep.py, the mxdys block method with
GMP/ctypes), which reaches all checkpoints n <= (5+d)*2^(k+12) exactly,
without parity bits.  Output: one rank line per d (full rank over Q plus
the ranks modulo 2, 3, 7, 11, 13); with --out-dir the used C(i,k) values
are dumped as deep-Cvalues-d{d}.json.

Usage::

    python3 yesdocs/formal-conjectures/tools/deep_rank_chain.py --d 9 --d 10 --d 11 --d 12
    python3 yesdocs/formal-conjectures/tools/deep_rank_chain.py --d 12 --out-dir .
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from fractions import Fraction as F
from math import ceil, log2
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bemyself.experiments.antihydra_deep import deep_lines, make_backend  # noqa: E402

MOD_PRIMES = (2, 3, 7, 11, 13)
BLOCK = 1024


def rank_mod(rows, p):
    """Column rank over F_p (Gauss elimination on the rows)."""
    m = [[int(v) % p for v in row] for row in rows]
    rank = 0
    for col in range(len(m[0])):
        pivot = None
        for i in range(rank, len(m)):
            if m[i][col] % p:
                pivot = i
                break
        if pivot is None:
            continue
        m[rank], m[pivot] = m[pivot], m[rank]
        inv = pow(m[rank][col] % p, p - 2, p)
        m[rank] = [(x * inv) % p for x in m[rank]]
        for i in range(len(m)):
            if i != rank and m[i][col] % p:
                f = m[i][col]
                m[i] = [(a - f * b) % p for a, b in zip(m[i], m[rank])]
        rank += 1
    return rank


def rank_q(rows):
    """Column rank over Q (Gauss elimination with exact fractions)."""
    m = [[F(v) for v in row] for row in rows]
    rank = 0
    for col in range(len(m[0])):
        pivot = None
        for i in range(rank, len(m)):
            if m[i][col] != 0:
                pivot = i
                break
        if pivot is None:
            continue
        m[rank], m[pivot] = m[pivot], m[rank]
        pv = m[rank][col]
        m[rank] = [x / pv for x in m[rank]]
        for i in range(len(m)):
            if i != rank and m[i][col] != 0:
                f = m[i][col]
                m[i] = [a - f * b for a, b in zip(m[i], m[rank])]
        rank += 1
    return rank


def rank_chain(d, out_dir=None):
    """One rank test of order d, printed as a single result line."""
    depth = 16 + d + ceil(log2(d + 5))
    targets = sorted({m * (BLOCK << k) for i in range(0, 25) for k in range(0, 8 + d)
                      for m in (i, i + 1) if 0 < m * (BLOCK << k) <= (1 << depth)})
    t0 = time.time()
    backend, _ = make_backend("auto")
    lines = deep_lines(depth, backend, extra_targets=targets)
    e = {}
    for line in lines:
        if line.startswith("steps="):
            parts = dict(x.split("=") for x in line.split())
            n = int(parts["steps"])
            e[n] = (int(parts["counter"]) + n) // 3

    def c_value(i, k):
        l = BLOCK << k
        lo, hi = e.get(i * l), e.get((i + 1) * l)
        return None if lo is None or hi is None else 5 * (hi - lo) - 2 * l

    def d_value(i, k):
        lo, hi = c_value(i, k), c_value(i, k + 2)
        return None if lo is None or hi is None else hi - 4 * lo

    rows = [[d_value(i, 4 + m) for m in range(d + 1)] for i in range(4, 5 + d)]
    complete = all(v is not None for row in rows for v in row)
    print(f"d={d} (depth {depth}, {time.time() - t0:.0f}s, targets {len(targets)},"
          f" komplett {complete}): ", end="", flush=True)
    if not complete:
        print("UNVOLLSTAENDIG")
        return
    rq = rank_q(rows)
    mods = {p: rank_mod(rows, p) for p in MOD_PRIMES}
    verdict = "AUSGESCHLOSSEN" if rq == d + 1 else "NICHT ausgeschlossen"
    print(f"Rang_Q={rq}/{d + 1} | {{{', '.join(f'{p}: {mods[p]}' for p in MOD_PRIMES)}}}"
          f" -> {verdict}", flush=True)
    if out_dir:
        out = Path(out_dir) / f"deep-Cvalues-d{d}.json"
        out.write_text(json.dumps({f"{i},{k}": c_value(i, k) for i in range(0, 25)
                                   for k in range(0, 8 + d) if c_value(i, k) is not None}))
        print(f"C-Werte: {out}", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Rank chain of the orbit-specific linear compression (L).")
    ap.add_argument("--d", type=int, action="append", default=None,
                    help="order to test (repeatable; default 9 10 11 12)")
    ap.add_argument("--out-dir", default=None,
                    help="directory for the deep-Cvalues-d{d}.json dumps")
    args = ap.parse_args(argv)
    for d in (args.d if args.d else [9, 10, 11, 12]):
        rank_chain(d, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

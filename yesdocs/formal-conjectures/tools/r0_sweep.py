#!/usr/bin/env python3
"""Five-block parity sweep of the orbit-specific candidate relation R0.

The relation under test is

    R0(i) = E(i,8) + E(i,9) + E(i,10) + E(i,12) + E(i,14)  (mod 2) = 0

for all i >= 4, with E(i,k) the number of even steps in the 1024*2^k step
block [i*L_k, (i+1)*L_k).  It holds on the rows i <= 15 of the rank tests,
but it is a candidate, not a consequence of the block tree.  The sweep
computes all R0(i) for i = 4..255 from exact block counters of the deep
divide-and-conquer engine (bemyself/experiments/antihydra_deep.py, depth
32 by default); the relation is refuted from i = 16 on (135 of 252 tested
rows).  With --out the hit list is dumped as JSON.

Usage::

    python3 yesdocs/formal-conjectures/tools/r0_sweep.py --out r0-sweep-result.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bemyself.experiments.antihydra_deep import deep_lines, make_backend  # noqa: E402

BLOCK = 1024
R0_SKALES = (8, 9, 10, 12, 14)


def run_sweep(depth=32, max_i=255):
    """Compute R0(i) for i = 4..max_i; returns {"tested", "zeros", "hits"}."""
    targets = set()
    for k in R0_SKALES:
        block = BLOCK << k
        for m in range(0, max_i + 2):
            t = m * block
            if 0 < t <= (1 << depth):
                targets.add(t)
    print(f"targets: {len(targets)} (max {max(targets)})", flush=True)
    t0 = time.time()
    backend, _ = make_backend("auto")
    lines = deep_lines(depth, backend, extra_targets=sorted(targets))
    evens = {}
    for line in lines:
        if line.startswith("steps="):
            parts = dict(x.split("=") for x in line.split())
            n = int(parts["steps"])
            evens[n] = (int(parts["counter"]) + n) // 3
    print(f"done {time.time() - t0:.0f}s, E-Werte {len(evens)}", flush=True)
    hits = []
    zeros = 0
    tested = 0
    for i in range(4, max_i + 1):
        total = 0
        ok = True
        for k in R0_SKALES:
            block = BLOCK << k
            lo, hi = evens.get(i * block), evens.get((i + 1) * block)
            if lo is None or hi is None:
                ok = False
                break
            total ^= (hi - lo) & 1
        if not ok:
            break
        tested += 1
        if total:
            hits.append(i)
        else:
            zeros += 1
    print(f"R0(i)=0 fuer {zeros}/{tested} getestete i | Treffer R0=1: {hits[:20]}",
          flush=True)
    return {"tested": tested, "zeros": zeros, "hits": hits}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Sweep the five-block parity candidate R0(i) = 0.")
    ap.add_argument("--depth", type=int, default=32,
                    help="D&C depth of the counter run (default 32)")
    ap.add_argument("--max-i", type=int, default=255,
                    help="last row index to test (default 255)")
    ap.add_argument("--out", default=None,
                    help="write the sweep result as JSON to this path")
    args = ap.parse_args(argv)
    result = run_sweep(depth=args.depth, max_i=args.max_i)
    if args.out:
        Path(args.out).write_text(json.dumps(result))
        print(f"Ergebnis: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

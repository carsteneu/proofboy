"""Tests for the deep rank-chain data of the V22 Nachtrag (attack-02.md).

The rank chain excludes the orbit-specific linear compression

    D(i,4+d) = sum_{r<d} c_r D(i,4+r)   for all i >= 4

by full column ranks of the matrices H_{i,m} = D(i,4+m)/5, built from the
exact block counters of the deep divide-and-conquer engine
(bemyself/experiments/antihydra_deep.py).  The frozen C(i,k) values in
data/deep-Cvalues-d12.json carry the d <= 12 witnesses.

Tests cover: the counter-engine E extraction against an independent direct
walk (T1), the d=12 rank certificates over F_3 (T2) and over F_2 with the
completion rows {16,20} (T3), the refuted five-block parity R0 (T4) and the
nonlinear invariant (N) with the frozen exact radius R^2 (T5).
"""

from __future__ import annotations

import json
import sys
import unittest
from fractions import Fraction as F
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[2]
for path in (str(REPO_ROOT),):
    if path not in sys.path:
        sys.path.insert(0, path)

from bemyself.experiments.antihydra_deep import PythonBackend, deep_lines  # noqa: E402

DATA = TOOLS.parent / "data"
C_VALUES = DATA / "deep-Cvalues-d12.json"
R0_SWEEP = DATA / "r0-sweep-result.json"

R2 = F(1309875575, 347892350976)  # frozen exact fit radius of (N), (14,4)
BLOCK = 1024  # L_k = 1024 * 2^k


def load_c_values():
    with open(C_VALUES) as fh:
        raw = json.load(fh)
    return {tuple(map(int, key.split(","))): value for key, value in raw.items()}


def d_value(c, i, k):
    """D(i,k) = C(i,k+2) - 4*C(i,k), or None if an input is missing."""
    lo, hi = c.get((i, k)), c.get((i, k + 2))
    if lo is None or hi is None:
        return None
    return hi - 4 * lo


def h_row(c, i, d):
    """Row (H_{i,0}, ..., H_{i,d}) with H = D/5, or None if incomplete."""
    row = []
    for m in range(d + 1):
        value = d_value(c, i, 4 + m)
        if value is None:
            return None
        row.append(value // 5)
    return row


def rank_mod(rows, p):
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


def nullspace_mod2(rows):
    """Basis of {c in F_2^n : c . row = 0 for every row}."""
    a = [row[:] for row in rows]
    pivots = []
    rank = 0
    for col in range(len(a[0])):
        pivot = None
        for i in range(rank, len(a)):
            if a[i][col] % 2:
                pivot = i
                break
        if pivot is None:
            continue
        a[rank], a[pivot] = a[pivot], a[rank]
        for i in range(len(a)):
            if i != rank and a[i][col] % 2:
                a[i] = [(x - y) % 2 for x, y in zip(a[i], a[rank])]
        pivots.append(col)
        rank += 1
    free = [col for col in range(len(a[0])) if col not in pivots]
    basis = []
    for fc in free:
        x = [0] * len(a[0])
        x[fc] = 1
        for pi, pc in enumerate(pivots):
            x[pc] = sum(a[pi][j] & x[j] for j in range(len(a[0]))) % 2
        basis.append(x)
    return basis


class CounterExtractionTest(unittest.TestCase):
    """T1: E(n) = (counter + n)/3 from the D&C engine equals a direct walk."""

    def test_e_values_match_direct_walk(self):
        depth = 14
        extras = [3000, 5000, 12288]
        lines = deep_lines(depth, PythonBackend(), extra_targets=extras)
        got = {}
        for line in lines:
            if line.startswith("steps="):
                parts = dict(p.split("=") for p in line.split())
                n = int(parts["steps"])
                got[n] = (int(parts["counter"]) + n) // 3
        h = 8
        evens = 0
        targets = {1 << k for k in range(0, depth + 1)} | set(extras)
        want = {}
        for n in range(1, (1 << depth) + 1):
            if h & 1:
                pass
            else:
                evens += 1
            h += h >> 1
            if n in targets:
                want[n] = evens
        self.assertEqual(set(got), set(want))
        self.assertEqual(got, want)


class RankChainTest(unittest.TestCase):
    """T2/T3: the frozen d=12 certificates of the rank chain."""

    @classmethod
    def setUpClass(cls):
        cls.c = load_c_values()

    def test_d12_full_rank_mod_3(self):
        rows = [h_row(self.c, i, 12) for i in range(4, 17)]
        self.assertTrue(all(row is not None for row in rows))
        self.assertEqual(rank_mod(rows, 3), 13)

    def test_d12_mod_2_completion_rows(self):
        base = [h_row(self.c, i, 12) for i in range(4, 16)]
        self.assertEqual(rank_mod(base, 2), 11)
        with_20 = [h_row(self.c, i, 12) for i in list(range(4, 16)) + [20]]
        self.assertEqual(rank_mod(with_20, 2), 12)
        pair = [h_row(self.c, i, 12) for i in list(range(4, 15)) + [16, 20]]
        self.assertEqual(rank_mod(pair, 2), 13)
        same = [h_row(self.c, i, 12) for i in list(range(4, 16)) + [16, 21]]
        self.assertEqual(rank_mod(same, 2), 12)
        # The quotient picture of Astra R27/R28: c0 is the old R0 relation,
        # {16,20} carry two different nonzero signatures, {16,21} do not.
        basis = nullspace_mod2([[v % 2 for v in row] for row in base])
        self.assertEqual(len(basis), 2)
        signatures = {}
        for i in (16, 20, 21):
            row = [v % 2 for v in h_row(self.c, i, 12)]
            signatures[i] = tuple(sum(c_ * v for c_, v in zip(b, row)) % 2
                                  for b in basis)
        self.assertEqual(sorted(signatures[16]), [1, 1])
        self.assertEqual(sorted(signatures[20]), [0, 1])
        self.assertNotEqual(signatures[16], signatures[20])
        self.assertEqual(signatures[16], signatures[21])


class R0SweepTest(unittest.TestCase):
    """T4: the five-block parity E(i,8)+E(i,9)+E(i,10)+E(i,12)+E(i,14) mod 2."""

    def test_r0_zero_upto_15_then_refuted(self):
        c = load_c_values()
        r0 = {}
        for i in range(4, 25):
            total = 0
            for k in (8, 9, 10, 12, 14):
                total ^= c[(i, k)] & 1  # C = 5E - 2L = E (mod 2)
            r0[i] = total
        self.assertEqual([i for i in range(4, 16) if r0[i]], [])
        self.assertEqual([i for i in (16, 20, 21, 23) if r0[i] == 1],
                         [16, 20, 21, 23])
        with open(R0_SWEEP) as fh:
            sweep = json.load(fh)
        self.assertEqual(sweep["tested"], 252)
        self.assertEqual(sweep["zeros"], 117)
        self.assertEqual(sweep["hits"][:4], [16, 20, 21, 23])
        self.assertEqual(len(sweep["hits"]), 135)
        self.assertEqual(sweep["zeros"] + len(sweep["hits"]), sweep["tested"])
        self.assertEqual([r0[i] for i in range(4, 25)],
                         [0] * 12 + [1, 0, 0, 0, 1, 1, 0, 1, 0])


class NonlinearInvariantTest(unittest.TestCase):
    """T5: (N) with the frozen exact R^2 on the frozen C values."""

    @staticmethod
    def z(c, i, k):
        value = d_value(c, i, k)
        if value is None:
            return None
        return F(4, 3) ** (k - 4) * F(value, 4 * (BLOCK << k))

    def count_cells(self, c, depth):
        cells = 0
        violations = 0
        best = None
        arg = None
        for i in range(4, 16):
            for k in range(4, 17):
                if (i + 1) * BLOCK * (1 << (k + 4)) > (1 << depth):
                    continue
                a, b, cc = (self.z(c, i, k), self.z(c, i, k + 1),
                            self.z(c, i, k + 2))
                if a is None or b is None or cc is None:
                    continue
                cells += 1
                t = -a * a + b * b + 2 * cc * cc
                if t > R2:
                    violations += 1
                if best is None or t > best:
                    best, arg = t, (i, k)
        return cells, violations, best, arg

    def test_n_holds_with_exact_radius(self):
        c = load_c_values()
        cells, violations, best, arg = self.count_cells(c, 28)
        self.assertEqual((cells, violations), (88, 0))
        self.assertEqual(best, R2)
        self.assertEqual(arg, (14, 4))
        cells33, violations33, best33, _ = self.count_cells(c, 33)
        self.assertEqual((cells33, violations33), (144, 0))
        self.assertEqual(best33, R2)


if __name__ == "__main__":
    unittest.main()

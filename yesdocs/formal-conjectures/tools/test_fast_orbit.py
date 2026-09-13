"""Tests for the generalized fast Antihydra orbit generator.

Core mechanism: the exact W-step transfer identity

    T^w(2^w * q + r) = 3^w * q + T^w(r),   T(x) = 3*x // 2,

and the fact that the parity bits of the next w steps depend only on
r = x mod 2^w.  The generator advances the orbit in W-step blocks and
streams one parity byte per step, so it needs no per-step x storage.

Tests cover: the transfer identity (small w, random and exhaustive q/r),
fast-vs-naive bit-identity (N = 2^14, W = 16 and 18, plus a non-multiple
tail), the exact x_end (hand value N=8 and equality against naive), the
statistics (E/H/A, dyadic checkpoints, 8-step block drawdown) and a CLI
smoke test.
"""

from __future__ import annotations

import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[2]
for path in (str(TOOLS), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import fast_orbit as FO  # noqa: E402

X0 = 8  # x = b + 4 for the Antihydra blank-tape orbit (b_0 = 4)


def naive_steps(n, x0=X0):
    """Naive reference: parity bits (1 = x even) and x after n steps."""
    x = x0
    bits = bytearray(n)
    for i in range(n):
        bits[i] = 0 if (x & 1) else 1
        x = 3 * x // 2
    return bytes(bits), x


def t_pow(x, w):
    for _ in range(w):
        x = 3 * x // 2
    return x


class TransferIdentityTest(unittest.TestCase):
    def test_identity_random_q_small_w(self):
        rng = random.Random(20260914)
        for w in range(1, 9):
            for _ in range(20):
                q = rng.randrange(0, 1 << 40)
                r = rng.randrange(0, 1 << w)
                lhs = t_pow((1 << w) * q + r, w)
                rhs = 3 ** w * q + t_pow(r, w)
                self.assertEqual(lhs, rhs, f"w={w} q={q} r={r}")

    def test_identity_exhaustive_small(self):
        for w in (1, 2, 3, 4):
            for q in range(8):
                for r in range(1 << w):
                    self.assertEqual(
                        t_pow((1 << w) * q + r, w),
                        3 ** w * q + t_pow(r, w),
                    )

    def test_table_matches_naive(self):
        for w in (1, 2, 4, 8):
            table = FO.transfer_table(w)
            self.assertEqual(len(table), 1 << w)
            for r in range(1 << w):
                self.assertEqual(table[r], t_pow(r, w))


class OrbitTest(unittest.TestCase):
    def test_matches_naive_2p14(self):
        for w in (16, 18):
            bits, xend = FO.orbit_bits(1 << 14, w=w)
            ref_bits, ref_x = naive_steps(1 << 14)
            self.assertEqual(bits, ref_bits)
            self.assertEqual(xend, ref_x)

    def test_tail_not_multiple_of_w(self):
        for w in (16, 18):
            bits, xend = FO.orbit_bits(1000, w=w)
            ref_bits, ref_x = naive_steps(1000)
            self.assertEqual(bits, ref_bits)
            self.assertEqual(xend, ref_x)

    def test_x_end_hand_value(self):
        # 8 -> 12 -> 18 -> 27 -> 40 -> 60 -> 90 -> 135 -> 202; parities of
        # the eight step starts are even,even,even,odd,even,even,even,odd.
        bits, xend = FO.orbit_bits(8, w=16)
        self.assertEqual(xend, 202)
        self.assertEqual(bits, bytes([1, 1, 1, 0, 1, 1, 1, 0]))

    def test_zero_length(self):
        bits, xend = FO.orbit_bits(0, w=16)
        self.assertEqual(bits, b"")
        self.assertEqual(xend, X0)


class StatsTest(unittest.TestCase):
    def test_stats_formulas(self):
        bits, _ = FO.orbit_bits(4096, w=16)
        st = FO.stats(bits)
        E = sum(bits)
        self.assertEqual(st["n"], 4096)
        self.assertEqual(st["E"], E)
        self.assertEqual(st["H"], 5 * E - 2 * 4096)
        self.assertEqual(st["A"], 3 * E - 4096)
        self.assertEqual(st["H_dyadic"][12], 5 * sum(bits[:4096]) - 2 * 4096)

    def test_block_drawdown_matches_naive(self):
        n = 1 << 13
        bits, _ = FO.orbit_bits(n, w=16)
        st = FO.stats(bits)
        best = 0
        cum = 0
        peak = 0
        for i in range(0, n - 7, 8):
            g = 5 * sum(bits[i:i + 8]) - 16
            cum += g
            peak = max(peak, cum)
            best = max(best, peak - cum)
        self.assertEqual(st["block_drawdown_8"], best)
        self.assertEqual(st["gsum"], 5 * sum(bits) - 2 * n)


class CliTest(unittest.TestCase):
    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bits.bin"
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "fast_orbit.py"), "256",
                 "--w", "16", "-o", str(out)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(out.stat().st_size, 256)
            ref_bits, ref_x = naive_steps(256)
            self.assertEqual(out.read_bytes(), ref_bits)
            self.assertIn("x_end", proc.stdout)

    def test_cli_quiet_deterministic(self):
        # --quiet --no-bits output is byte-deterministic (used as a [COMPUTE]
        # anchor in the report); it must not contain timings or paths.
        cmd = [sys.executable, str(TOOLS / "fast_orbit.py"), "4096",
               "--w", "16", "--quiet", "--no-bits"]
        first = subprocess.run(cmd, capture_output=True, text=True)
        second = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertNotIn("walk_s", first.stdout)
        self.assertNotIn(" bits=", first.stdout)
        self.assertNotIn(str(TOOLS), first.stdout)

    def test_cli_rejects_invalid_arguments(self):
        cases = [
            (["4096", "--w", "3"], b"w must be in"),
            (["4096", "--w", "21"], b"w must be in"),
            (["-1", "--w", "16"], b"n must be >= 0"),
            ([str(FO.MAX_N + 1), "--w", "16"], b"n exceeds the supported maximum"),
        ]
        for argv, needle in cases:
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "fast_orbit.py")] + argv,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 2, (argv, proc.stderr))
            self.assertIn(needle, proc.stderr, argv)

    def test_orbit_bits_rejects_negative_n(self):
        with self.assertRaises(ValueError):
            FO.orbit_bits(-1)


if __name__ == "__main__":
    unittest.main()

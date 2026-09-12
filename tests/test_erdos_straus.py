"""Tests for the bounded Erdős–Straus experiment.

The experiment is finite and exhaustive per ``n``: every printed witness must
be exact, the witness is the lexicographically smallest triple, the output is
deterministic (two runs under different hash seeds print identical bytes),
and a search window without a witness must never be skipped silently -- the
``n`` appears as ``gap n`` and the run exits non-zero.
"""

import contextlib
import io
import os
import subprocess
import sys
import unittest
from fractions import Fraction

from bemyself.experiments import erdos_straus

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SMALL_EXPECTED = (
    "2 1 2 2\n"
    "3 1 4 12\n"
    "4 2 3 6\n"
    "5 2 4 20\n"
    "6 2 7 42\n"
    "7 2 15 210\n"
    "8 3 7 42\n"
    "9 3 10 90\n"
    "10 3 16 240\n"
    "ok 10 9\n"
)


def brute_min(n):
    """Lexicographically smallest witness by direct Fraction search.

    Independent of the divisor criterion used by the module: ``a`` runs over
    the whole feasible window, and for a fixed ``a`` the minimal valid ``b``
    has ``b <= c``, so the complete candidate interval is (1/r, 2/r].
    """
    for a in range(1, 3 * n // 4 + 1):
        remainder = Fraction(4, n) - Fraction(1, a)
        if remainder <= 0:
            continue
        b = int(Fraction(1, remainder)) + 1
        limit = int(2 / remainder) + 2
        while b <= limit:
            c = Fraction(1) / (remainder - Fraction(1, b))
            if c.denominator == 1 and c > 0:
                return (a, b, int(c))
            b += 1
    return None


class WitnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spf = erdos_straus.smallest_prime_factors(10000)

    def test_small_limit_output_is_pinned(self):
        out = io.StringIO()
        code = erdos_straus.run(10, out, spf=erdos_straus.smallest_prime_factors(20))
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), SMALL_EXPECTED)

    def test_witnesses_solve_the_equation(self):
        for n in range(2, 2001):
            with self.subTest(n=n):
                a, b, c = erdos_straus.witness(n, self.spf)
                self.assertEqual(
                    Fraction(1, a) + Fraction(1, b) + Fraction(1, c), Fraction(4, n)
                )
                self.assertGreater(a, n // 4)
                self.assertLessEqual(a, 3 * n // 4)
                self.assertGreaterEqual(min(a, b, c), 1)

    def test_witness_is_lexicographically_smallest(self):
        for n in range(2, 121):
            with self.subTest(n=n):
                self.assertEqual(erdos_straus.witness(n, self.spf), brute_min(n))

    def test_every_n_appears_exactly_once_in_order(self):
        out = io.StringIO()
        code = erdos_straus.run(1000, out)
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertEqual([int(line.split()[0]) for line in lines[:-1]], list(range(2, 1001)))
        self.assertEqual(lines[-1], "ok 1000 999")


class GapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spf = erdos_straus.smallest_prime_factors(100)

    def test_a_restricted_window_finds_no_witness(self):
        # 17 has the witness a = 5; a window cut at 4 cannot see it.
        self.assertIsNone(erdos_straus.witness(17, self.spf, a_limit=4))
        self.assertEqual(erdos_straus.witness(17, self.spf), (5, 30, 510))

    def test_gap_line_and_nonzero_exit(self):
        # a_limit=4 cuts the window below 16's smallest witness a = 5; every
        # other n <= 16 still finds its witness inside the cut window.
        out = io.StringIO()
        code = erdos_straus.run(16, out, spf=erdos_straus.smallest_prime_factors(32), a_limit=4)
        self.assertEqual(code, 1)
        lines = out.getvalue().splitlines()
        self.assertIn("gap 16", lines)
        self.assertEqual(lines[-1], "gaps 16 14 1")
        # No silent skipping: every n shows up exactly once, in order.
        seen = [
            int(line.split()[1] if line.startswith("gap ") else line.split()[0])
            for line in lines[:-1]
        ]
        self.assertEqual(seen, list(range(2, 17)))


class CliTest(unittest.TestCase):
    def test_determinism_across_hash_seeds(self):
        outputs = []
        for seed in ("0", "1"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run(
                (sys.executable, "-m", "bemyself.experiments.erdos_straus", "500"),
                cwd=REPO_ROOT,
                capture_output=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.append(proc.stdout)
        self.assertGreater(len(outputs[0]), 0)
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(outputs[0].endswith(b"ok 500 499\n"))

    def test_usage_errors_exit_2(self):
        for argv in (
            (),
            ("1",),
            ("x",),
            ("-1",),
            ("1.5",),
            ("2", "3"),
            ("1_0",),
            ("9" * 5000,),  # above CPython's int() digit cap
            ("9" * 4300,),  # int() passes, the factor table cannot be sized
        ):
            with self.subTest(argv=argv[:1]):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code = erdos_straus.main(list(argv))
                self.assertEqual(code, 2)
                self.assertTrue(err.getvalue().strip())


if __name__ == "__main__":
    unittest.main()

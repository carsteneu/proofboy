#!/usr/bin/env python3
"""Tests for catalog_probe.py — bounded probes on shortlisted catalog problems.

Run:
    python3 yesdocs/formal-conjectures/tools/test_catalog_probe.py
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import catalog_probe as cp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class Bmo1Test(unittest.TestCase):
    def test_first_ten_pairs_match_docstring(self):
        # The docstring of beaver_math_olympiad_problem_1 lists the first ten
        # (a, b) pairs; the recurrence must reproduce them exactly.
        pairs, _ = cp.bmo1_sequence(10)
        self.assertEqual(
            pairs,
            [(1, 2), (3, 1), (2, 6), (5, 4), (1, 18), (3, 17), (7, 14), (15, 7), (8, 30), (17, 22)],
        )

    def test_no_equality_in_small_budget(self):
        _, equality_index = cp.bmo1_sequence(1000)
        self.assertIsNone(equality_index)


class Bmo2Test(unittest.TestCase):
    def test_antihydra_min_b(self):
        # a_0 = 8, a_{n+1} = 3a_n/2 (nat), b counts +2 on even, -1 on odd.
        # The conjecture is b_n >= 0 for all n.
        stats = cp.antihydra(1000)
        self.assertGreaterEqual(stats["min_b"], 0)
        self.assertEqual(stats["steps"], 1000)

    def test_antihydra_first_values(self):
        stats = cp.antihydra(3)
        # a: 8, 12, 18, 27 -> even, even, even; b: 0, 2, 4, 6
        self.assertEqual(stats["min_b"], 0)


class Bmo3Test(unittest.TestCase):
    def test_first_values(self):
        values, hit = cp.bmo3_sequence(5)
        self.assertEqual(values[:5], [2, 9, 12, 27, 30])
        self.assertIsNone(hit)

    def test_no_power_of_four(self):
        _, hit = cp.bmo3_sequence(200)
        self.assertIsNone(hit)


class Bmo4Test(unittest.TestCase):
    def test_first_values_match_wiki(self):
        values, one = cp.bmo4_sequence(10)
        self.assertEqual(values[:10], [2, 0, 3, 6, 11, 18, 39, 78, 155, 306])
        self.assertIsNone(one)

    def test_closed_form_matches_recurrence(self):
        values, _ = cp.bmo4_sequence(200)
        for n, value in enumerate(values):
            self.assertEqual(value, cp.bmo4_closed_form(n), f"n={n}")

    def test_never_mod3_one(self):
        _, one = cp.bmo4_sequence(500)
        self.assertIsNone(one)


class SmallestKPrimeTest(unittest.TestCase):
    def test_reference_values_from_repo(self):
        # The repo's own test theorems: a 2 = 1, a 3 = 2, a 7 = 4.
        self.assertEqual(cp.smallest_k_prime(2), 1)
        self.assertEqual(cp.smallest_k_prime(3), 2)
        self.assertEqual(cp.smallest_k_prime(7), 4)

    def test_k_lt_n_sweep(self):
        stats = cp.smallest_k_prime_sweep(200)
        self.assertGreaterEqual(stats["checked"], 199)
        self.assertLess(stats["max_k"], stats["max_k_n"])  # k < n held at the maximum
        self.assertEqual(stats["not_found"], [])
        self.assertIsNone(stats["violation_k_lt_n"])
        self.assertIsNone(stats["violation_three_quarter"])

    def test_capped_search_miss_is_not_a_violation(self):
        # A cap that is far too small must surface as not_found, never as a
        # claimed counterexample of the conjecture.
        stats = cp.smallest_k_prime_sweep(10, cap=1)
        self.assertIn(3, stats["not_found"])  # 3*1+1=4 is composite -> miss
        self.assertIsNone(stats["violation_k_lt_n"])
        self.assertIsNone(stats["violation_three_quarter"])
        self.assertEqual(cp.smallest_k_prime(3, cap=1), None)


class MachineProbeTest(unittest.TestCase):
    def test_bmo1_machine_no_halt_small(self):
        result = cp.machine_probe("1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE", 1000)
        self.assertFalse(result["halts"])
        self.assertEqual(result["steps"], 1000)

    def test_machine_error_is_reported(self):
        result = cp.machine_probe("NOT_A_MACHINE", 10)
        self.assertIn("error", result)


class ReportTest(unittest.TestCase):
    def test_report_is_deterministic_and_key_value(self):
        first = cp.report(small_iterations=50, sweep=50, machine_steps=1000,
                          big_iterations=1000, antihydra_iterations=1000)
        second = cp.report(small_iterations=50, sweep=50, machine_steps=1000,
                           big_iterations=1000, antihydra_iterations=1000)
        self.assertEqual(first, second)
        lines = [line for line in first.splitlines() if line and not line.startswith("#")]
        for line in lines:
            self.assertIn("=", line)

    def test_cli(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "catalog_probe.py"),
             "--sweep", "50", "--machine-steps", "1000", "--small-iterations", "50",
             "--big-iterations", "1000", "--antihydra-iterations", "1000"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("bmo1.first_ten_ok=true", proc.stdout)
        self.assertIn("a34693.violation_k_lt_n=none", proc.stdout)
        self.assertIn("bmo8.machine.halts=False", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

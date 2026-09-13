"""Tests for the both-direction reduction checks.

The expected values are the externally documented ones (BusyBeaverWiki pages
for BMO#1 and Antihydra, sligocki.com 2024 for the Antihydra rules) and OEIS
A385902 for the Antihydra counter sequence (first 200 terms, fetched
2026-09-13 from https://oeis.org/A385902/b385902.txt).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO_ROOT = TOOLS.parents[3]
for path in (str(TOOLS), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import reductions as R  # noqa: E402
from bemyself.turing import parse  # noqa: E402

# OEIS A385902, a(0)..a(199): Antihydra counter values (the "b" of the wiki).
OEIS_A385902_PREFIX = [
    0, 2, 4, 6, 5, 7, 9, 11, 10, 12, 11, 13, 12, 11, 10, 12, 14, 16, 15, 14,
    16, 15, 17, 16, 18, 17, 19, 21, 20, 19, 21, 20, 19, 21, 23, 25, 24, 23,
    22, 21, 20, 22, 21, 20, 19, 18, 17, 19, 21, 23, 25, 27, 29, 31, 30, 29,
    31, 30, 32, 31, 33, 32, 31, 33, 35, 37, 36, 35, 37, 36, 35, 37, 39, 38,
    40, 39, 38, 40, 42, 44, 43, 42, 41, 43, 42, 44, 46, 48, 47, 46, 48, 47,
    49, 48, 47, 46, 48, 47, 49, 51, 53, 52, 54, 53, 52, 51, 53, 55, 54, 53,
    52, 54, 56, 55, 54, 56, 58, 60, 59, 58, 57, 56, 55, 54, 56, 58, 57, 59,
    61, 63, 62, 64, 63, 65, 67, 69, 68, 70, 72, 71, 73, 72, 74, 76, 78, 77,
    79, 78, 77, 79, 78, 77, 79, 81, 83, 85, 84, 86, 88, 90, 89, 91, 93, 92,
    94, 96, 98, 97, 99, 98, 97, 96, 95, 94, 93, 95, 97, 99, 101, 100, 99, 98,
    100, 102, 104, 103, 102, 104, 106, 105, 104, 106, 108, 110, 109, 111, 110,
    109, 108, 110,
]


class StepperTest(unittest.TestCase):
    def test_cross_check_bmo1(self):
        machine = parse(R.BMO1_MACHINE)
        result = R.cross_check_stepper(machine, [0, 1, 5, 23, 45, 113, 249, 1000], 1000)
        self.assertEqual(result["mismatches"], [])
        self.assertFalse(result["reference_run"]["halts"])

    def test_cross_check_antihydra(self):
        machine = parse(R.ANTIHYDRA_MACHINE)
        result = R.cross_check_stepper(machine, [0, 1, 11, 58, 169, 1000], 1000)
        self.assertEqual(result["mismatches"], [])


class Bmo1Test(unittest.TestCase):
    def test_trajectory_matches_documented_configurations(self):
        # @-d's documented visited list on the BusyBeaverWiki BMO#1 page.
        machine = parse(R.BMO1_MACHINE)
        result = R.machine_to_map(
            machine, R.read_bmo1, R.bmo1_next, R.bmo1_cells, max_configs=8, max_steps=5000
        )
        pairs = [tuple(pair) for _, pair in result["configurations"]]
        self.assertEqual(
            pairs,
            [(0, 3), (2, 2), (1, 7), (4, 5), (0, 19), (2, 18), (6, 15), (14, 8)],
        )
        self.assertEqual(result["mismatches"], [])

    def test_window_successors_match(self):
        machine = parse(R.BMO1_MACHINE)
        window = range(0, 8)
        outcomes = R.window_outcomes(
            machine, R.bmo1_cells, R.read_bmo1, R.bmo1_next, R.BMO1_STATE_D,
            window, range(2, 12), step_cap=20000,
        )
        expected = [(a, b) for a in window for b in range(2, 12) if b != a + 2]
        self.assertEqual([(a, b) for a, b, _ in outcomes["successors"]], expected)
        # b = a+2 is the documented halt case: the machine moves one
        # renormalisation on instead (and then halts there, checked below).
        self.assertEqual(len(outcomes["mismatches"]), len(window))
        for a, b, message in outcomes["mismatches"]:
            self.assertEqual((a, b), (a, a + 2))
            self.assertIn("machine continues to", message)

    def test_b_equals_one_exits_the_domain(self):
        # b = 1 is never visited by the trajectory; the raw machine halts
        # there although the documented rule would continue the walk.
        machine = parse(R.BMO1_MACHINE)
        outcomes = R.window_outcomes(
            machine, R.bmo1_cells, R.read_bmo1, R.bmo1_next, R.BMO1_STATE_D,
            range(0, 6), [1], step_cap=20000,
        )
        self.assertEqual(outcomes["successors"], [])
        self.assertEqual(len(outcomes["mismatches"]), 6)
        for _, _, message in outcomes["mismatches"]:
            self.assertIn("machine halts", message)

    def test_halt_condition_after_the_extra_rename(self):
        machine = parse(R.BMO1_MACHINE)
        for a in range(0, 5):
            halted, reason = R.halts_from(
                machine, R.bmo1_cells, R.read_bmo1, R.BMO1_STATE_D, 2 * a + 2, 1, 20000
            )
            self.assertTrue(halted, f"a={a}: {reason}")

    def test_coordinate_change_to_the_A_model(self):
        self.assertEqual(R.f_to_A((0, 3)), (1, 2))  # start configuration
        self.assertEqual(R.A_to_f((1, 2)), (0, 3))
        self.assertEqual(R.rules_equivalent_on_window(range(0, 10), range(1, 15)), [])

    def test_first_ten_A_pairs_of_the_shortlist(self):
        pair = (1, 2)
        pairs = [pair]
        for _ in range(9):
            pair = R.A_next(*pair)
            pairs.append(pair)
        self.assertEqual(
            pairs,
            [(1, 2), (3, 1), (2, 6), (5, 4), (1, 18),
             (3, 17), (7, 14), (15, 7), (8, 30), (17, 22)],
        )


class AntihydraTest(unittest.TestCase):
    def test_trajectory_matches_wiki(self):
        machine = parse(R.ANTIHYDRA_MACHINE)
        result = R.machine_to_map(
            machine, R.read_antihydra, R.antihydra_next, R.antihydra_cells,
            max_configs=7, max_steps=10 ** 6,
        )
        pairs = [tuple(pair) for _, pair in result["configurations"]]
        self.assertEqual(pairs, [(0, 4), (2, 8), (4, 14), (6, 23), (5, 36), (7, 56), (9, 86)])
        # The wiki's rule step deltas 47, 111, 250, 500, 1209, 2713 ...
        self.assertEqual(result["steps_between"][:6], [47, 111, 250, 500, 1209, 2713])
        self.assertEqual(result["mismatches"], [])

    def test_window_successors_and_halts(self):
        machine = parse(R.ANTIHYDRA_MACHINE)
        window_a = range(0, 8)
        window_b = range(2, 16)
        outcomes = R.window_outcomes(
            machine, R.antihydra_cells, R.read_antihydra, R.antihydra_next,
            R.ANTIHYDRA_STATE_E, window_a, window_b, step_cap=20000,
        )
        expected_halts = [(a, b) for a in window_a for b in window_b if a == 0 and b % 2]
        self.assertEqual(outcomes["halts"], expected_halts)
        self.assertEqual(outcomes["mismatches"], [])
        self.assertEqual(
            len(outcomes["successors"]),
            len(list(window_a)) * len(list(window_b)) - len(expected_halts),
        )

    def test_b_equals_one_exits_the_domain(self):
        # The documented derivation needs b >= 2 (even) / b >= 3 (odd); b = 1
        # is outside the domain and the raw machine does not follow the rule.
        machine = parse(R.ANTIHYDRA_MACHINE)
        outcomes = R.window_outcomes(
            machine, R.antihydra_cells, R.read_antihydra, R.antihydra_next,
            R.ANTIHYDRA_STATE_E, range(0, 4), [1], step_cap=20000,
        )
        self.assertEqual(outcomes["successors"], [])
        self.assertEqual(len(outcomes["mismatches"]), 4)

    def test_hydra_alignment(self):
        self.assertEqual(R.hydra_alignment(2000), [])

    def test_hydra_counter_matches_oeis_prefix(self):
        _, _, counters = R.hydra_walk(len(OEIS_A385902_PREFIX) - 1)
        self.assertEqual([0] + counters, OEIS_A385902_PREFIX)

    def test_shift_lemma(self):
        for n in range(0, 5000):
            self.assertEqual((3 * (n + 4)) // 2, (3 * n) // 2 + 6)


if __name__ == "__main__":
    unittest.main()

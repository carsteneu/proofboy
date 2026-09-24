"""Tests for the [SEARCHED: <machine> -> <n>] claim type.

A SEARCHED claim asserts one bounded observation: the machine ran n steps
without halting. The type must never be readable as a proof that the machine
never halts -- the verdict text says so explicitly, and the tests below pin
that wording.
"""

import time
import unittest
from unittest import mock

from proofboy import claimtypes
from proofboy.claimtypes import search
from proofboy.checks import Ctx, kind_needs_repo, run_claim
from proofboy.model import Verdict
from proofboy.report import parse_report

# Hand trace in tests/test_turing.py: halts after exactly three steps.
SMALL = "1RB1RZ_0LA0LA"
# Never halts: writes 1 and walks right forever.
WALKER = "1RA1RA"
# BB(6) record holder (mxdys, June 2025); halts only after 2 arrow-up 5 steps,
# far beyond any searched range.
BB6_RECORD = "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE"
# BB(6) Cryptid Antihydra (wiki.bbchallenge.org/wiki/Antihydra): includes the
# undefined F0 transition and is believed to never halt.
ANTIHYDRA = "1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA"

BOUNDED = "a bounded search of {n} steps found no halt; " \
    "this does not prove that the machine never halts"


class SearchParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report(f"[DONE] [SEARCHED: {WALKER} -> 1000]\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "searched")
        self.assertEqual(claim.fields["machine"], WALKER)
        self.assertEqual(claim.fields["steps"], "1000")

    def test_unicode_arrow_parses(self):
        claims = parse_report(f"[SEARCHED: {WALKER} \u2192 1000]\n")
        self.assertEqual(claims[0].fields["steps"], "1000")

    def test_marker_without_arrow_is_no_claim(self):
        self.assertEqual(parse_report(f"[SEARCHED: {WALKER}]\n"), [])

    def test_empty_fields_still_parse(self):
        claims = parse_report("[SEARCHED: -> ]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["machine"], "")
        self.assertEqual(claims[0].fields["steps"], "")

    def test_absurdly_long_line_is_ignored(self):
        line = f"[SEARCHED: {WALKER} -> 1000] " + "x" * 9000 + "\n"
        self.assertEqual(parse_report(line), [])

    def test_unterminated_marker_stays_linear(self):
        start = time.perf_counter()
        claims = parse_report("[SEARCHED:" + " " * 2000 + "\n")
        elapsed = time.perf_counter() - start
        self.assertEqual(claims, [])
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for a hostile line")


class SearchRegistryTest(unittest.TestCase):
    def test_searched_is_registered(self):
        self.assertIn(search.SEARCHED, claimtypes.CLAIM_TYPES)
        self.assertEqual(search.SEARCHED.kind, "searched")

    def test_the_checker_needs_no_repository(self):
        self.assertFalse(kind_needs_repo("searched"))

    def test_default_limit_is_bounded(self):
        # Deliberately below the HALT limit (47,176,870): a SEARCHED run is an
        # honest bounded observation, not a record attempt by default.
        self.assertEqual(search.DEFAULT_SEARCH_LIMIT, 10_000_000)


class SearchCheckTest(unittest.TestCase):
    def ctx(self, **kw):
        return Ctx(repo=".", tmp_dir=".", **kw)

    def check_report(self, text, ctx=None):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx or self.ctx())

    def test_no_halt_within_the_claim_is_confirmed(self):
        result = self.check_report(f"[SEARCHED: {WALKER} -> 1000]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("halts=False steps=1000 score=1000", result.output)
        self.assertEqual(result.command, f"simulate {WALKER} for at most 1000 steps")
        self.assertIsNone(result.sandboxed)

    def test_wording_states_the_bounded_boundary(self):
        result = self.check_report(f"[SEARCHED: {WALKER} -> 1000]")
        self.assertEqual(result.reason, BOUNDED.format(n=1000))
        self.assertIn("bounded search", result.reason)
        self.assertIn("does not prove", result.reason)
        # The phrase "never halts" may appear only inside the negation.
        without_negation = result.reason.replace(
            "does not prove that the machine never halts", ""
        )
        self.assertNotIn("never halts", without_negation)

    def test_halt_within_the_claim_refutes_with_the_witness(self):
        result = self.check_report(f"[SEARCHED: {SMALL} -> 5]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("halted after 3 steps", result.reason)
        self.assertIn("within the claimed 5 steps", result.reason)
        self.assertIn("halts=True steps=3 score=1", result.output)

    def test_halt_exactly_at_the_claimed_count_refutes(self):
        result = self.check_report(f"[SEARCHED: {SMALL} -> 3]")
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_bb6_record_does_not_halt_in_a_bounded_run(self):
        result = self.check_report(f"[SEARCHED: {BB6_RECORD} -> 1000]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_antihydra_survives_a_bounded_run(self):
        # The canonical string carries the undefined F0 transition; a bounded
        # run confirms the observation without claiming anything about halting.
        result = self.check_report(f"[SEARCHED: {ANTIHYDRA} -> 10000]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_bad_machines_are_unverifiable(self):
        for machine in ("", "1RB", "1rb1rz_1lc1rb", "1RB1LC"):
            with self.subTest(machine=machine):
                result = self.check_report(f"[SEARCHED: {machine} -> 3]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_bad_step_counts_are_unverifiable(self):
        for steps in ("three", "-1", "3.0", "1e3", "4 7", "", "４２"):
            with self.subTest(steps=steps):
                result = self.check_report(f"[SEARCHED: {WALKER} -> {steps}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
                self.assertEqual(result.command, "")

    def test_a_zero_step_search_is_unverifiable(self):
        # A zero-step run observes nothing, so it certifies nothing.
        result = self.check_report(f"[SEARCHED: {WALKER} -> 0]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("observes nothing", result.reason)

    def test_huge_integer_is_unverifiable(self):
        result = self.check_report(f"[SEARCHED: {WALKER} -> {'9' * 5000}]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_steps_beyond_the_limit_are_unverifiable(self):
        result = self.check_report(
            f"[SEARCHED: {WALKER} -> 3]", ctx=self.ctx(search_limit=2)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("exceed the executable limit of 2", result.reason)
        self.assertEqual(result.command, "")

    def test_steps_exactly_at_the_limit_run(self):
        result = self.check_report(
            f"[SEARCHED: {WALKER} -> 3]", ctx=self.ctx(search_limit=3)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_check_needs_no_repository(self):
        result = self.check_report(
            f"[SEARCHED: {WALKER} -> 100]", ctx=Ctx(repo="/nonexistent", tmp_dir=".")
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_check_starts_no_subprocess(self):
        with mock.patch(
            "subprocess.run", side_effect=AssertionError("subprocess")
        ), mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess")):
            result = self.check_report(f"[SEARCHED: {WALKER} -> 100]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)


if __name__ == "__main__":
    unittest.main()

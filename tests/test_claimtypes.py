"""Tests for the claim-type registry and the [HALT]/[SCORE] claim type."""

import re
import time
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.claimtypes import halt
from bemyself.checks import Ctx, run_claim
from bemyself.model import ClaimType, Result, Verdict
from bemyself.report import parse_report

# Hand trace in tests/test_turing.py: three steps, score 1.
SMALL = "1RB1RZ_0LA0LA"
# Never halts: writes 1 and walks right forever.
WALKER = "1RA1RA"
# BB(6) record holder (mxdys, June 2025); far beyond any executable limit.
BB6_RECORD = "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE"


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.ctx = Ctx(repo=".", tmp_dir=".")

    def test_halt_is_registered(self):
        self.assertIn(halt.HALT, claimtypes.CLAIM_TYPES)
        self.assertEqual(halt.HALT.kind, "halt")

    def test_checker_lookup(self):
        self.assertIs(claimtypes.checker_for("halt"), halt.check)
        self.assertIsNone(claimtypes.checker_for("nothing-registered"))

    def test_a_new_type_needs_no_parser_or_cli_change(self):
        # The documented recipe: one new module and one registration entry.
        # Here the entry is injected into the registry; parse_report and
        # run_claim are used unmodified, so the type flows end to end.
        def check(claim, ctx):
            value = int(claim.fields["value"])
            if value % 2 == 0:
                return Result(Verdict.CONFIRMED, reason=f"{value} is even")
            return Result(Verdict.REFUTED, reason=f"{value} is odd")

        def parse(match, raw):
            return {"value": match.group(1)}

        even = ClaimType(
            kind="even",
            pattern=re.compile(r"\[EVEN:[ \t]*(\d+)[ \t]*\]"),
            parse=parse,
            check=check,
        )
        with mock.patch.object(claimtypes, "CLAIM_TYPES", claimtypes.CLAIM_TYPES + (even,)):
            claims = parse_report("[EVEN: 42]\n")
            self.assertEqual([claim.kind for claim in claims], ["even"])
            self.assertIs(
                run_claim(claims[0], self.ctx).verdict, Verdict.CONFIRMED
            )


class HaltParseTest(unittest.TestCase):
    def test_halt_marker_parses(self):
        claims = parse_report(f"[DONE] [HALT: {SMALL} -> 3]\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "halt")
        self.assertEqual(claim.fields["machine"], SMALL)
        self.assertEqual(claim.fields["steps"], "3")
        self.assertIsNone(claim.fields["score"])
        self.assertFalse(claim.fields["score_conflict"])

    def test_unicode_arrow_parses(self):
        claims = parse_report(f"[HALT: {SMALL} \u2192 3]\n")
        self.assertEqual(claims[0].fields["steps"], "3")

    def test_same_line_score_is_attached(self):
        claims = parse_report(f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> 1]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["score"], "1")
        self.assertFalse(claims[0].fields["score_conflict"])

    def test_duplicate_identical_scores_attach(self):
        claims = parse_report(
            f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> 1] [SCORE: {SMALL} -> 1]\n"
        )
        self.assertEqual(claims[0].fields["score"], "1")
        self.assertFalse(claims[0].fields["score_conflict"])

    def test_conflicting_scores_are_flagged(self):
        claims = parse_report(
            f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> 1] [SCORE: {SMALL} -> 2]\n"
        )
        self.assertIsNone(claims[0].fields["score"])
        self.assertTrue(claims[0].fields["score_conflict"])

    def test_score_for_another_machine_is_not_attached(self):
        claims = parse_report(f"[HALT: {SMALL} -> 3] [SCORE: {WALKER} -> 1]\n")
        self.assertIsNone(claims[0].fields["score"])

    def test_score_on_another_line_does_not_attach(self):
        claims = parse_report(f"[HALT: {SMALL} -> 3]\n[SCORE: {SMALL} -> 1]\n")
        self.assertEqual(len(claims), 1)
        self.assertIsNone(claims[0].fields["score"])

    def test_score_without_halt_is_no_claim(self):
        self.assertEqual(parse_report(f"[SCORE: {SMALL} -> 1]\n"), [])

    def test_halt_without_arrow_is_no_claim(self):
        self.assertEqual(parse_report(f"[HALT: {SMALL}]\n"), [])

    def test_empty_machine_and_empty_steps_still_parse(self):
        # A broken claim must become a claim with a verdict, not silence.
        empty_machine = parse_report("[HALT: -> 5]\n")
        self.assertEqual(len(empty_machine), 1)
        self.assertEqual(empty_machine[0].fields["machine"], "")
        empty_steps = parse_report(f"[HALT: {SMALL} -> ]\n")
        self.assertEqual(len(empty_steps), 1)
        self.assertEqual(empty_steps[0].fields["steps"], "")

    def test_absurdly_long_line_is_ignored(self):
        line = f"[HALT: {SMALL} -> 3] " + "x" * 9000 + "\n"
        self.assertEqual(parse_report(line), [])


class HaltCheckTest(unittest.TestCase):
    def ctx(self, **kw):
        return Ctx(repo=".", tmp_dir=".", **kw)

    def check_report(self, text, ctx=None):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx or self.ctx())

    def test_exact_step_count_confirms(self):
        result = self.check_report(f"[HALT: {SMALL} -> 3]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("3 steps", result.reason)
        self.assertEqual(result.command, f"simulate {SMALL} for at most 3 steps")
        self.assertIn("halts=True steps=3 score=1", result.output)
        self.assertIsNone(result.sandboxed)

    def test_exact_steps_and_score_confirm(self):
        result = self.check_report(f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> 1]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("score 1", result.reason)

    def test_wrong_step_count_refutes(self):
        result = self.check_report(f"[HALT: {SMALL} -> 5]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("halted after 3 steps, not 5", result.reason)

    def test_earlier_halt_than_claimed_refutes(self):
        result = self.check_report(f"[HALT: {SMALL} -> 2]")
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_machine_that_does_not_halt_within_the_claim_refutes(self):
        result = self.check_report(f"[HALT: {WALKER} -> 4]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("did not halt within the claimed 4 steps", result.reason)

    def test_wrong_score_refutes(self):
        result = self.check_report(f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> 2]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("score 1, not 2", result.reason)

    def test_non_integer_score_is_unverifiable(self):
        result = self.check_report(f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> one]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_conflicting_scores_are_unverifiable(self):
        result = self.check_report(
            f"[HALT: {SMALL} -> 3] [SCORE: {SMALL} -> 1] [SCORE: {SMALL} -> 2]"
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("ambiguous", result.reason)

    def test_bad_step_counts_are_unverifiable(self):
        for steps in ("three", "-1", "3.0", "1e3", "4 7", "4_2", "４２", ""):
            with self.subTest(steps=steps):
                result = self.check_report(f"[HALT: {SMALL} -> {steps}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
                self.assertEqual(result.command, "")

    def test_number_beyond_the_interpreter_limit_is_unverifiable(self):
        # CPython caps int(text) at a few thousand digits; the claim must not
        # crash the checker.
        result = self.check_report(f"[HALT: {SMALL} -> {'9' * 5000}]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_steps_beyond_the_executable_limit_are_unverifiable(self):
        result = self.check_report(f"[HALT: {SMALL} -> 3]", ctx=self.ctx(halt_limit=2))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("exceed the executable limit of 2", result.reason)
        self.assertEqual(result.command, "")

    def test_steps_exactly_at_the_limit_run(self):
        result = self.check_report(f"[HALT: {SMALL} -> 3]", ctx=self.ctx(halt_limit=3))
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_huge_integer_steps_are_unverifiable(self):
        result = self.check_report(f"[HALT: {SMALL} -> {'1' + '0' * 39}]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_up_arrow_steps_are_unverifiable(self):
        result = self.check_report(f"[HALT: {BB6_RECORD} -> 2\u2191\u2191\u21915]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("not a non-negative integer", result.reason)

    def test_bb6_record_claim_is_unverifiable(self):
        result = self.check_report(f"[HALT: {BB6_RECORD} -> 100000000000000000000000000000000000]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_bad_machines_are_unverifiable(self):
        for machine in ("", "1RB", "1rb1rz_1lc1rb", "1RB1LC"):
            with self.subTest(machine=machine):
                result = self.check_report(f"[HALT: {machine} -> 3]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_the_check_needs_no_repository(self):
        result = self.check_report(
            f"[HALT: {SMALL} -> 3]", ctx=Ctx(repo="/nonexistent", tmp_dir=".")
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_check_starts_no_subprocess(self):
        with mock.patch("subprocess.run", side_effect=AssertionError("subprocess")), mock.patch(
            "subprocess.Popen", side_effect=AssertionError("subprocess")
        ):
            result = self.check_report(f"[HALT: {SMALL} -> 3]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)


class CaptureCostTest(unittest.TestCase):
    """A hostile report must not make the parser burn minutes on one line.

    A whitespace run behind an unterminated marker used to send the regex
    engine into cubic backtracking (measured: ~7s for a 2000-character run,
    growing 8x per doubling). The patterns must not overlap that way: the
    budget below is many orders of magnitude above linear scanning time and
    far below the old cubic cost.
    """

    BUDGET = 0.5
    RUN = 2000

    def parsed_within_budget(self, line):
        start = time.perf_counter()
        claims = parse_report(line + "\n")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, self.BUDGET, f"{elapsed:.3f}s for a {len(line)}-char line")
        return claims

    def test_unterminated_halt_marker(self):
        self.assertEqual(self.parsed_within_budget("[HALT:" + " " * self.RUN), [])

    def test_unterminated_score_marker(self):
        self.assertEqual(self.parsed_within_budget("[SCORE:" + " " * self.RUN), [])

    def test_unterminated_score_behind_a_halt_claim(self):
        # halt.parse re-scans the line for SCORE markers, so this path has to
        # stay linear as well.
        claims = self.parsed_within_budget(f"[HALT: {SMALL} -> 3] [SCORE:" + " " * (self.RUN - 30))
        self.assertEqual(len(claims), 1)
        self.assertIsNone(claims[0].fields["score"])

    def test_unterminated_halt_marker_with_tabs(self):
        self.assertEqual(self.parsed_within_budget("[HALT:" + "\t" * self.RUN), [])

    def test_arrow_without_terminator(self):
        self.assertEqual(self.parsed_within_budget("[HALT: M ->" + " " * self.RUN), [])

    def test_repeated_arrows_without_terminator(self):
        self.assertEqual(self.parsed_within_budget("[HALT: M " + "->" * 700 + " "), [])


if __name__ == "__main__":
    unittest.main()

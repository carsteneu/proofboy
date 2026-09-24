"""Tests for the [CYCLE: <machine> -> t1,t2,d] claim type.

A CYCLE claim asserts a translated cycle: the configuration at step t2 is
the configuration at step t1 translated by d cells. Together with a halt-free
window up to t2 that is a complete non-halting proof -- for this machine with
this certificate, checked in finitely many steps. The type must never be
readable as a general non-halting decision procedure, and a [SEARCHED] run
must never turn into a [CYCLE] certificate: the tests below pin both the
proof sentence and the boundary.
"""

import os
import time
import unittest
from unittest import mock

from proofboy import claimtypes, turing
from proofboy.claimtypes import cycle
from proofboy.checks import Ctx, kind_needs_repo, run_claim
from proofboy.model import Verdict
from proofboy.report import parse_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The annotated example machine of the bbchallenge wiki page "Translated
# cycler" (figure machine 44394115): cycle start time 6 steps, cycle period 10
# steps, cycle offset 2 cells to the right. The certificate (t1=6, t2=16,
# d=2) was re-derived with the simulator of this repository: at both steps the
# state is D and the tape pattern (a single 1 two cells left of the head) is
# identical, the head sitting at 2 and 4 respectively; no halt occurs within
# the window. Source: wiki.bbchallenge.org/wiki/Translated_cycler.
WIKI_CYCLER = "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC"
# Hand trace in tests/test_turing.py: halts after exactly three steps.
SMALL_HALTER = "1RB1RZ_0LA0LA"
# Writes 0 and walks left forever: every single step translates the
# configuration by -1 on a blank tape, so (0, 1, -1) is a true certificate.
ZERO_WALKER = "0LA0LA"
# Writes 1 and walks right forever: the tape grows at the tail, no step is a
# translation of an earlier configuration.
WALKER = "1RA1RA"
# Two states that walk right on a blank tape, alternating A and B: the
# configuration after step 1 (state B) and after step 2 (state A) share the
# head displacement under d=1 but not the state.
TWO_STATE_WALKER = "0RB1LA_0RA1LA"

PROVEN = (
    "the configuration at step {t2} equals the configuration at step {t1} "
    "translated by {d} on every cell the machine can still reach "
    "(it never goes more than {excursion} cells {side} of the head at "
    "step {t1}); therefore by determinism the machine never halts"
)


class CycleParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "cycle")
        self.assertEqual(claim.fields["machine"], WIKI_CYCLER)
        self.assertEqual(claim.fields["t1"], "6")
        self.assertEqual(claim.fields["t2"], "16")
        self.assertEqual(claim.fields["d"], "2")

    def test_unicode_arrow_and_spaces_parse(self):
        claims = parse_report(f"[CYCLE: {WIKI_CYCLER} \u2192 6, 16, 2]\n")
        self.assertEqual(claims[0].fields["t2"], "16")
        self.assertEqual(claims[0].fields["d"], "2")

    def test_negative_translation_parses(self):
        claims = parse_report(f"[CYCLE: {ZERO_WALKER} -> 0,1,-1]\n")
        self.assertEqual(claims[0].fields["d"], "-1")

    def test_marker_without_arrow_is_no_claim(self):
        self.assertEqual(parse_report(f"[CYCLE: {WIKI_CYCLER}]\n"), [])

    def test_missing_values_keep_an_empty_certificate(self):
        claims = parse_report("[CYCLE: -> ]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["machine"], "")
        self.assertEqual(claims[0].fields["t1"], "")
        self.assertEqual(claims[0].fields["values"], "")

    def test_wrong_arity_keeps_the_raw_values(self):
        claims = parse_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["values"], "6,16")
        self.assertEqual(claims[0].fields["t1"], "")

    def test_absurdly_long_line_is_ignored(self):
        line = f"[CYCLE: {WIKI_CYCLER} -> 6,16,2] " + "x" * 9000 + "\n"
        self.assertEqual(parse_report(line), [])

    def test_unterminated_marker_stays_linear(self):
        start = time.perf_counter()
        claims = parse_report("[CYCLE:" + " " * 2000 + "\n")
        elapsed = time.perf_counter() - start
        self.assertEqual(claims, [])
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for a hostile line")


class CycleRegistryTest(unittest.TestCase):
    def test_cycle_is_registered(self):
        self.assertIn(cycle.CYCLE, claimtypes.CLAIM_TYPES)
        self.assertEqual(cycle.CYCLE.kind, "cycle")

    def test_the_checker_needs_no_repository(self):
        self.assertFalse(kind_needs_repo("cycle"))

    def test_the_default_limit_is_bounded(self):
        # Like the SEARCHED limit, not the HALT limit: an honest bound that a
        # larger certificate can raise explicitly with --cycle-limit.
        self.assertEqual(cycle.DEFAULT_CYCLE_LIMIT, 10_000_000)

    def test_the_tape_bound_is_documented_and_finite(self):
        self.assertEqual(cycle.TAPE_LIMIT, 1 << 24)


class CycleCheckTest(unittest.TestCase):
    def ctx(self, **kw):
        return Ctx(repo=".", tmp_dir=".", **kw)

    def check_report(self, text, ctx=None):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx or self.ctx())

    def test_the_wiki_certificate_is_confirmed_with_the_proof_sentence(self):
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.reason, PROVEN.format(t1=6, t2=16, d=2, excursion=2, side="left")
        )
        self.assertIn("never halts", result.reason)
        self.assertEqual(
            result.command,
            f"simulate {WIKI_CYCLER} up to 16 steps and compare the "
            "configurations at steps 6 and 16",
        )
        self.assertEqual(result.output, "halts=False steps=16 score=2")
        self.assertIsNone(result.sandboxed)

    def test_the_reachable_window_ignores_the_memory_left_behind(self):
        # The wiki machine leaves a 1 behind at cell -1 that is *not* shifted
        # by the cycle: the full relative patterns differ. It sits further
        # left than the head ever goes during the cycle, so the future can
        # never reach it and the proof stands on the reachable window alone.
        _, snapshots = turing.run_checkpoints(turing.parse(WIKI_CYCLER), 16, (6, 16))
        self.assertNotEqual(
            cycle._pattern(snapshots[6]), cycle._pattern(snapshots[16])
        )
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_a_later_cycle_of_the_same_machine_confirms(self):
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 7,17,2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.reason, PROVEN.format(t1=7, t2=17, d=2, excursion=1, side="left")
        )

    def test_the_proof_sentence_is_the_only_never_halts_claim(self):
        # The sentence carries its own justification ("therefore by
        # determinism"); nothing else in the verdict may promise non-halting.
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]")
        self.assertEqual(result.reason.count("never halts"), 1)
        self.assertIn("therefore by determinism", result.reason)

    def test_a_single_step_translation_of_a_blank_machine_proves_non_halting(self):
        # 0LA0LA writes 0 and walks left: step 1 is step 0 shifted by -1.
        result = self.check_report(f"[CYCLE: {ZERO_WALKER} -> 0,1,-1]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.reason, PROVEN.format(t1=0, t2=1, d=-1, excursion=0, side="right")
        )

    def test_a_wrong_translation_refutes_on_the_head(self):
        # The examples's real offset is +2: with d=1 the head at step 16 sits
        # at 4, not at 2 + 1 = 3.
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,1]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("the head at step 16 is at cell 4, not at cell 2 + 1 = 3", result.reason)

    def test_a_matching_head_with_a_different_tape_refutes_on_the_tape(self):
        # At step 3 the machine is in state A with the head at -1 and a single
        # 1 at cell 0; at step 13 it is in state A with the head at 1 -- the
        # claimed shift +2 fits the head, but the tape carries a second 1.
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 3,13,2]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn(
            "the tape at step 13 differs from the tape at step 3 at relative position 0",
            result.reason,
        )

    def test_a_machine_that_only_moves_away_confirms_with_a_zero_excursion(self):
        # WALKER only ever moves right: its interval fold still includes the
        # head at step 3 itself, so the excursion is 0 -- never negative --
        # and the proof sentence says so.
        result = self.check_report(f"[CYCLE: {WALKER} -> 3,5,2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.reason, PROVEN.format(t1=3, t2=5, d=2, excursion=0, side="left")
        )

    def test_the_mirrored_machine_confirms_with_a_zero_excursion(self):
        # 1LA1LA writes 1 and walks left forever: the same clamp on the
        # d < 0 side.
        result = self.check_report("[CYCLE: 1LA1LA -> 3,5,-2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.reason, PROVEN.format(t1=3, t2=5, d=-2, excursion=0, side="right")
        )

    def test_a_state_mismatch_refutes_on_the_state(self):
        result = self.check_report(f"[CYCLE: {TWO_STATE_WALKER} -> 1,2,1]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("the state at step 2 is A, not the state at step 1 (B)", result.reason)

    def test_halt_inside_the_window_refutes_with_the_witness(self):
        result = self.check_report(f"[CYCLE: {SMALL_HALTER} -> 1,5,1]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("halted after 3 steps, inside the certificate window of 5 steps", result.reason)
        self.assertEqual(result.output, "halts=True steps=3 score=1")

    def test_halt_exactly_at_t2_refutes(self):
        result = self.check_report(f"[CYCLE: {SMALL_HALTER} -> 1,3,1]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("halted after 3 steps", result.reason)

    def test_a_halt_before_t1_refutes(self):
        result = self.check_report(f"[CYCLE: {SMALL_HALTER} -> 2,5,1]")
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("halted after 3 steps", result.reason)

    def test_t2_not_greater_than_t1_is_unverifiable(self):
        for t1, t2 in (("6", "6"), ("16", "6"), ("16", "16")):
            with self.subTest(t1=t1, t2=t2):
                result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> {t1},{t2},2]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
                self.assertIn("needs t2 > t1", result.reason)
                self.assertEqual(result.command, "")

    def test_a_zero_translation_is_unverifiable(self):
        for d in ("0", "-0"):
            with self.subTest(d=d):
                result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,{d}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
                self.assertIn("non-zero translation", result.reason)

    def test_bad_machines_are_unverifiable(self):
        for machine in ("", "1RB", "1rb1rz_1lc1rb", "1RB1LC"):
            with self.subTest(machine=machine):
                result = self.check_report(f"[CYCLE: {machine} -> 6,16,2]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_bad_certificate_numbers_are_unverifiable(self):
        bad = (("three", "16", "2"), ("-1", "16", "2"), ("6", "3.0", "2"),
               ("6", "16", "x"), ("6", "16", "2.0"), ("6", "16", "+2"),
               ("６", "16", "2"))
        for t1, t2, d in bad:
            with self.subTest(t1=t1, t2=t2, d=d):
                result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> {t1},{t2},{d}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
                self.assertEqual(result.command, "")

    def test_a_missing_value_names_the_three_values(self):
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("three comma-separated values", result.reason)

    def test_huge_numbers_are_unverifiable(self):
        result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,{'9' * 5000},2]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_steps_beyond_the_limit_are_unverifiable(self):
        result = self.check_report(
            f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]", ctx=self.ctx(cycle_limit=15)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("exceed the executable limit of 15", result.reason)
        self.assertEqual(result.command, "")

    def test_steps_exactly_at_the_limit_run(self):
        result = self.check_report(
            f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]", ctx=self.ctx(cycle_limit=16)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_a_tape_beyond_the_bound_stays_unverifiable(self):
        # 1RA1RA has written five cells by step 5: with a bound of four the
        # configuration at step 5 is not materialized, so the comparison
        # cannot be performed -- no confirmation by omission.
        with mock.patch.object(cycle, "TAPE_LIMIT", 4):
            result = self.check_report(f"[CYCLE: {WALKER} -> 0,5,1]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("the configuration at step 5 does not materialize", result.reason)
        self.assertIn("4 cells", result.reason)

    def test_the_bound_does_not_reject_the_wiki_certificate(self):
        with mock.patch.object(cycle, "TAPE_LIMIT", 16):
            result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_a_comparison_window_beyond_the_tape_bound_stays_unverifiable(self):
        # The bound holds for the comparison itself, not only for the single
        # snapshot: a wider window is not compared, and no performed
        # comparison means no confirmation.
        with mock.patch.object(
            cycle, "_comparison_window", return_value=(0, cycle.TAPE_LIMIT + 1)
        ):
            result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("comparison window", result.reason)
        self.assertIn("tape bound", result.reason)

    def test_the_check_needs_no_repository(self):
        result = self.check_report(
            f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]", ctx=Ctx(repo="/nonexistent", tmp_dir=".")
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_check_starts_no_subprocess(self):
        with mock.patch(
            "subprocess.run", side_effect=AssertionError("subprocess")
        ), mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess")):
            result = self.check_report(f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]")
        self.assertIs(result.verdict, Verdict.CONFIRMED)


class CycleWindowTest(unittest.TestCase):
    """The pure window arithmetic: the union of the written extents, clipped
    to the reachable region (relative to the head at t1)."""

    def snapshot(self, head, right=b"", left=b""):
        return turing.Snapshot(0, head, right, left, head, head)

    def test_the_window_is_the_union_of_the_written_extents(self):
        first = self.snapshot(0, right=b"\x01\x01")
        second = self.snapshot(2, right=b"\x01")
        self.assertEqual(cycle._comparison_window(first, second, None, None), (-2, 2))

    def test_the_window_is_clipped_to_the_reachable_region(self):
        first = self.snapshot(0, right=b"\x01\x01")
        second = self.snapshot(2, right=b"\x01")
        self.assertEqual(cycle._comparison_window(first, second, -1, None), (-1, 2))
        self.assertEqual(cycle._comparison_window(first, second, None, 0), (-2, 1))

    def test_an_empty_window_compares_as_equal(self):
        first = self.snapshot(0, right=b"\x01\x01")
        second = self.snapshot(2, right=b"\x01")
        start, end = cycle._comparison_window(first, second, 5, None)
        self.assertGreater(start, end)
        self.assertIsNone(cycle._tape_difference(first, second, start, end))

    def test_the_first_difference_is_reported(self):
        # The second snapshot still carries its 1 at relative -2 (the union
        # covers it), so the first difference sits there.
        first = self.snapshot(0, right=b"\x01\x00")
        second = self.snapshot(2, right=b"\x01")
        start, end = cycle._comparison_window(first, second, None, None)
        self.assertEqual(cycle._tape_difference(first, second, start, end), -2)


class CycleBoundaryTest(unittest.TestCase):
    """[CYCLE] proves non-halting for this machine with this certificate --
    it is no general non-halting checker, and a [SEARCHED] run never becomes a
    [CYCLE] certificate. The docs carry that boundary; this test keeps it
    from being edited away."""

    def docs(self):
        for name in ("README.de.md", "SPEC.md"):
            with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as handle:
                yield name, handle.read()

    def test_the_docs_pin_the_scope_of_the_proof(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("fuer diese Maschine mit diesem Zertifikat", text)
                self.assertIn("kein allgemeiner Nicht-Halte-Pruefer", text)

    def test_the_docs_keep_the_searched_boundary(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("wird nie zu einem CYCLE-Zertifikat aufgewertet", text)

    def test_a_searched_run_over_a_translated_cycler_stays_a_bounded_observation(self):
        # The same machine, the same window -- but a SEARCHED claim says
        # nothing about halting and knows nothing about cycles.
        claims = parse_report(f"[SEARCHED: {WIKI_CYCLER} -> 100]\n")
        self.assertEqual([claim.kind for claim in claims], ["searched"])
        result = run_claim(claims[0], Ctx(repo=".", tmp_dir="."))
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertNotIn("CYCLE", result.reason)
        self.assertNotIn("translated", result.reason)
        without_negation = result.reason.replace(
            "does not prove that the machine never halts", ""
        )
        self.assertNotIn("never halts", without_negation)


if __name__ == "__main__":
    unittest.main()

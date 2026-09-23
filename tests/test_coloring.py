"""Tests for the [COLORING: k=<k> ; <digits>] claim type.

A COLORING claim asserts that one explicit coloring of 1..N with k colors
contains no monochromatic solution of x + y = z. The checker re-enumerates
every triple with x <= y and x + y <= N, in process: no repository, no
subprocess. A CONFIRMED verdict certificates the lower bound S(k) >= N
only -- it does not prove equality and says nothing about the upper bound
(S(k) is the largest N that admits a Schur coloring; the matching upper
bound has no compact certificate). The tests below pin the marker grammar,
the verdict boundaries (REFUTED with the first violation in canonical
order, UNVERIFIABLE for malformed, out-of-range or oversized
certificates) and the boundary wording.
"""

import os
import time
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.claimtypes import coloring
from bemyself.checks import Ctx, kind_needs_repo, run_claim
from bemyself.model import Verdict
from bemyself.report import parse_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A two-coloring of 1..4: 1,4 / 2,3. S(2) is exactly 4.
TWO_COLOR_4 = "[COLORING: k=2 ; 1221]"
# One color, one number: there is no triple at all. S(1) is exactly 1.
ONE_COLOR_1 = "[COLORING: k=1 ; 1]"
# A three-coloring of 1..13 found by this repository's deterministic search
# (python3 -m bemyself.experiments.schur 3 13). S(3) is exactly 13.
THREE_COLOR_13 = "[COLORING: k=3 ; 1221331331221]"
# The Golomb-Baumert partition of 1..44 (Baumert & Golomb 1965, as listed in
# OEIS A045652): the sets A,B,C,D joined into one color string, A=1..D=4.
# S(4) is exactly 44.
GOLOMB_BAUMERT_44 = (
    "[COLORING: k=4 ; 12131322444434141213233231214343444422313121]"
)
# All in color 1: the very first triple fails.
ALL_ONE = "[COLORING: k=2 ; 1111]"
# A manipulated certificate: the valid 1221 with position 2 flipped to 1;
# now 1+1=2 is monochromatic in color 1.
MANIPULATED = "[COLORING: k=2 ; 1121]"
# The first violation is not the first triple: 1+1=2 and 1+2=3 are fine,
# 1+3=4 is not (all in color 2).
LATE_VIOLATION = "[COLORING: k=2 ; 2122]"

CONFIRMED_REASON = (
    "all {count} triples x + y = z with x <= y and x + y <= {n} are checked: "
    "no monochromatic solution in the {k}-coloring of 1..{n}; this certificates "
    "the lower bound S({k}) >= {n} only -- it does not prove equality and says "
    "nothing about the upper bound"
)


class ColoringParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report(TWO_COLOR_4 + "\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "coloring")
        self.assertEqual(claim.fields["body"], "k=2 ; 1221")

    def test_two_markers_on_one_line(self):
        claims = parse_report(TWO_COLOR_4 + " " + ONE_COLOR_1 + "\n")
        self.assertEqual([claim.kind for claim in claims], ["coloring", "coloring"])

    def test_a_malformed_marker_stays_a_claim(self):
        # Like [IDENT]: a malformed marker is a claim attempt and must stay
        # visible as unverifiable, never be silently dropped.
        claims = parse_report("[COLORING: k=2 1221]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].kind, "coloring")

    def test_lowercase_marker_is_not_the_marker(self):
        self.assertEqual(parse_report("[coloring: k=2 ; 1221]\n"), [])

    def test_unterminated_marker_is_no_claim(self):
        self.assertEqual(parse_report("[COLORING: k=2 ; 1221\n"), [])

    def test_unterminated_marker_stays_linear(self):
        start = time.perf_counter()
        claims = parse_report("[COLORING:" + " " * 2000 + "\n")
        elapsed = time.perf_counter() - start
        self.assertEqual(claims, [])
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for a hostile line")

    def test_absurdly_long_line_is_ignored(self):
        self.assertEqual(parse_report("[COLORING: " + "1" * 9000 + "]\n"), [])

    def test_the_marker_may_appear_inside_prose(self):
        # The documented use: certificates live in documentation prose.
        text = f"Die Faerbung lautet: {TWO_COLOR_4} und sie ist gueltig.\n"
        claims = parse_report(text)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].kind, "coloring")


class ColoringRegistryTest(unittest.TestCase):
    def test_coloring_is_registered(self):
        self.assertIn(coloring.COLORING, claimtypes.CLAIM_TYPES)
        self.assertEqual(coloring.COLORING.kind, "coloring")
        self.assertIs(claimtypes.checker_for("coloring"), coloring.check)

    def test_the_checker_needs_no_repository(self):
        self.assertFalse(kind_needs_repo("coloring"))

    def test_the_type_binds_no_commit(self):
        claims = parse_report("[COMMIT: " + "a" * 40 + "]\n" + TWO_COLOR_4 + "\n")
        coloring_claims = [claim for claim in claims if claim.kind == "coloring"]
        self.assertEqual(len(coloring_claims), 1)
        self.assertIsNone(coloring_claims[0].fields.get("commit"))


class ColoringCheckTest(unittest.TestCase):
    def ctx(self, **kw):
        return Ctx(repo=".", tmp_dir=".", **kw)

    def check_report(self, text, ctx=None):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx or self.ctx())

    def test_two_color_four_confirms(self):
        result = self.check_report(TWO_COLOR_4)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.command,
            "check every triple x + y = z with x <= y, x + y <= 4 in the 2-coloring",
        )
        self.assertEqual(result.output, "checked 4 triples; first violation: none")
        self.assertIsNone(result.sandboxed)

    def test_the_boundary_wording_is_pinned(self):
        result = self.check_report(TWO_COLOR_4)
        self.assertEqual(result.reason, CONFIRMED_REASON.format(count=4, n=4, k=2))
        self.assertIn("the lower bound S(2) >= 4 only", result.reason)
        self.assertIn(
            "it does not prove equality and says nothing about the upper bound",
            result.reason,
        )
        lowered = result.reason.lower()
        self.assertNotIn("proves equality", lowered)
        self.assertNotIn("proves the upper bound", lowered)
        self.assertNotIn("is the exact value", lowered)

    def test_every_valid_certificate_carries_the_boundary(self):
        for marker, k, n in (
            (ONE_COLOR_1, 1, 1),
            (TWO_COLOR_4, 2, 4),
            (THREE_COLOR_13, 3, 13),
            (GOLOMB_BAUMERT_44, 4, 44),
        ):
            with self.subTest(marker=marker):
                result = self.check_report(marker)
                self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
                self.assertIn(f"the lower bound S({k}) >= {n} only", result.reason)
                self.assertIn("nothing about the upper bound", result.reason)

    def test_one_color_one_confirms(self):
        result = self.check_report(ONE_COLOR_1)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(result.output, "checked 0 triples; first violation: none")

    def test_three_color_thirteen_confirms(self):
        result = self.check_report(THREE_COLOR_13)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("the lower bound S(3) >= 13 only", result.reason)

    def test_golomb_baumert_fortyfour_confirms(self):
        result = self.check_report(GOLOMB_BAUMERT_44)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("the lower bound S(4) >= 44 only", result.reason)

    def test_all_one_refutes_with_the_first_violation(self):
        result = self.check_report(ALL_ONE)
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertEqual(
            result.output, "first violation: 1 + 1 = 2 with 1, 1, 2 all in color 1"
        )
        self.assertIn("1 + 1 = 2 with 1, 1, 2 all in color 1", result.reason)
        self.assertIn("not Schur", result.reason)

    def test_a_manipulated_certificate_refutes(self):
        # The acceptance case: one flipped digit turns the valid 1221 into a
        # certificate with a witness; the first violation is named.
        result = self.check_report(MANIPULATED)
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("1 + 1 = 2 with 1, 1, 2 all in color 1", result.output)

    def test_the_first_violation_is_canonical(self):
        # 1+1=2 and 1+2=3 are not monochromatic; the first violation in the
        # canonical order (x ascending, then y ascending) is 1+3=4.
        result = self.check_report(LATE_VIOLATION)
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertEqual(
            result.output, "first violation: 1 + 3 = 4 with 1, 3, 4 all in color 2"
        )

    def test_the_violation_search_matches_a_brute_force_scan(self):
        # The canonical first violation must be the lexicographically first
        # (x, y) pair over all colorings of small size.
        for digits in ("1", "11", "12", "111", "121", "122", "1122", "2122", "1111"):
            n = len(digits)
            with self.subTest(digits=digits):
                expected = None
                for x in range(1, n + 1):
                    for y in range(x, n + 1):
                        z = x + y
                        if z > n:
                            break
                        if digits[x - 1] == digits[y - 1] == digits[z - 1]:
                            expected = (x, y, z, int(digits[x - 1]))
                            break
                    if expected is not None:
                        break
                result = self.check_report(f"[COLORING: k=2 ; {digits}]")
                if expected is None:
                    self.assertIs(result.verdict, Verdict.CONFIRMED)
                else:
                    x, y, z, c = expected
                    self.assertIs(result.verdict, Verdict.REFUTED)
                    self.assertEqual(
                        result.output,
                        f"first violation: {x} + {y} = {z} with {x}, {y}, {z} "
                        f"all in color {c}",
                    )

    def test_the_check_needs_no_repository(self):
        result = self.check_report(TWO_COLOR_4, ctx=Ctx(repo="/nonexistent", tmp_dir="."))
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_check_starts_no_subprocess(self):
        with mock.patch(
            "subprocess.run", side_effect=AssertionError("subprocess")
        ), mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess")):
            result = self.check_report(GOLOMB_BAUMERT_44)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_a_custom_limit_is_honored(self):
        # N == limit is executable; the claim is still checked.
        result = self.check_report("[COLORING: k=1 ; 111]", ctx=self.ctx(coloring_limit=3))
        self.assertIs(result.verdict, Verdict.REFUTED)
        # N > limit is not executed at all.
        result = self.check_report(TWO_COLOR_4, ctx=self.ctx(coloring_limit=3))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("limit", result.reason)

    def test_the_default_limit_boundary(self):
        # Exactly the limit: executed (and refuted at the very first triple).
        at_limit = "[COLORING: k=1 ; " + "1" * coloring.DEFAULT_COLORING_LIMIT + "]"
        result = self.check_report(at_limit)
        self.assertIs(result.verdict, Verdict.REFUTED)
        # One past the limit: not executed, no scan starts.
        past_limit = "[COLORING: k=1 ; " + "1" * (coloring.DEFAULT_COLORING_LIMIT + 1) + "]"
        result = self.check_report(past_limit)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn(str(coloring.DEFAULT_COLORING_LIMIT), result.reason)


class ColoringRobustnessTest(unittest.TestCase):
    def check_report(self, text):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], Ctx(repo=".", tmp_dir="."))

    def test_malformed_bodies_are_unverifiable(self):
        for body in (
            "k=2 1221",
            "1221",
            "k=2 ; 11 ; 22",
            "k= ; 1221",
            "k=x ; 1221",
            "k=0 ; 1",
            "k=-2 ; 1",
            "",
            "k=2 ;",
            "k=2 ; ",
            "1221 ; k=2",
        ):
            with self.subTest(body=body):
                result = self.check_report(f"[COLORING: {body}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_more_than_nine_colors_are_unverifiable(self):
        # The colors are encoded as single digits 1..9; a claim with more
        # colors cannot be expressed and stays unverifiable.
        result = self.check_report("[COLORING: k=10 ; 1234567891]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_zero_is_not_a_color_digit(self):
        result = self.check_report("[COLORING: k=2 ; 1201]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_a_digit_beyond_k_is_unverifiable(self):
        result = self.check_report("[COLORING: k=2 ; 123]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("color", result.reason)

    def test_huge_digit_runs_are_unverifiable_not_slow(self):
        # A hostile certificate beyond the executable limit must not start a
        # quadratic scan: the verdict comes from the limit, immediately.
        marker = "[COLORING: k=5 ; " + "1" * 8000 + "]"
        start = time.perf_counter()
        result = self.check_report(marker)
        elapsed = time.perf_counter() - start
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for an oversized certificate")

    def test_a_marker_with_inner_brackets_is_no_marker(self):
        # A deliberate boundary, like the other types: the marker regex
        # excludes brackets to stay linear.
        self.assertEqual(parse_report("[COLORING: k=2 ; 12[21]]\n"), [])

    def test_a_nul_byte_is_unverifiable(self):
        result = self.check_report("[COLORING: k=2 ; 1221\x00]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("NUL", result.reason)


class ColoringBoundaryTest(unittest.TestCase):
    """[COLORING] proves a lower bound -- S(k) >= N -- and nothing else. The
    docs carry that boundary; this test keeps it from being edited away."""

    def docs(self):
        for name in ("README.md", "SPEC.md"):
            with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as handle:
                yield name, handle.read()

    def test_the_docs_pin_the_lower_bound(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("untere Schranke", text)

    def test_the_docs_pin_the_equality_boundary(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("keine Gleichheit", text)

    def test_the_docs_pin_the_upper_bound(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("obere Schranke", text)

if __name__ == "__main__":
    unittest.main()

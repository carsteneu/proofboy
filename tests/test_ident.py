"""Tests for the [IDENT: ...] claim type.

An IDENT claim asserts that 1/a(t) + 1/b(t) + 1/c(t) = 4/n(t) holds as a
rational identity in the parameter t, with affine n, a, b, c and a declared
range t >= bound (default 1). A CONFIRMED verdict covers the whole
progression n(t) for every parameter -- and it is NOT a proof of the
Erdos-Straus conjecture: one progression is covered, not all of them. The
tests below pin the marker grammar, the verdict boundaries (REFUTED for a
false identity, UNVERIFIABLE for a range that is not soundly covered, for
non-affine input, and for hostile lines) and the proof wording.
"""

import os
import time
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.claimtypes import ident
from bemyself.checks import Ctx, kind_needs_repo, run_claim
from bemyself.model import Verdict
from bemyself.report import parse_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The identity of the briefing: for n = 3t, 1/t + 1/(4t) + 1/(12t) = 4/(3t).
THREE_T = "[IDENT: n=3t ; a=t, b=4t, c=12t]"
# The even class via the two-term split: 1/t + 1/(2t) + 1/(2t) = 2/t = 4/(2t).
EVEN_T = "[IDENT: n=2t ; a=t, b=2t, c=2t]"
# Scaled classes: 4/5 = 1/2 + 1/4 + 1/20, 4/7 = 1/3 + 1/6 + 1/14,
# 4/11 = 1/3 + 1/66 + 1/66.
FIVE_T = "[IDENT: n=5t ; a=2t, b=4t, c=20t]"
SEVEN_T = "[IDENT: n=7t ; a=3t, b=6t, c=14t]"
ELEVEN_T = "[IDENT: n=11t ; a=3t, b=66t, c=66t]"
# An explicit range: n = 3(t+1) covers n = 3, 6, 9, ... from t >= 0.
SHIFTED = "[IDENT: n=3t+3 ; a=t+1, b=4t+4, c=12t+12 ; t >= 0]"
# A faked coefficient: the identity fails for all but finitely many t.
FALSIFIED = "[IDENT: n=3t ; a=t, b=4t+1, c=12t]"
# The identity holds, but a(t) = t is zero at t = 0: the range is not sound.
ZERO_RANGE = "[IDENT: n=3t ; a=t, b=4t, c=12t ; t >= 0]"
# The even family with m = -t + 51: the identity holds as a rational
# function, but every denominator reaches zero at t = 51.
NEGATIVE_SLOPE = "[IDENT: n=-2t+102 ; a=-t+51, b=-2t+102, c=-2t+102]"

PROOF = (
    "4/n(t) = 1/a(t) + 1/b(t) + 1/c(t) holds as a rational identity in t "
    "for every t >= {bound} with n = {n}, a = {a}, b = {b}, c = {c}; every "
    "integer t >= {bound} has n >= 2 and positive denominators, so the "
    "progression n = {n} is covered for every parameter -- one progression, "
    "not all of them: this is not a proof of the conjecture"
)


class IdentParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report(THREE_T + "\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "ident")
        self.assertEqual(claim.fields["body"], "n=3t ; a=t, b=4t, c=12t")

    def test_range_parses_into_the_body(self):
        claims = parse_report(SHIFTED + "\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(
            claims[0].fields["body"], "n=3t+3 ; a=t+1, b=4t+4, c=12t+12 ; t >= 0"
        )

    def test_two_markers_on_one_line(self):
        claims = parse_report(THREE_T + " " + EVEN_T + "\n")
        self.assertEqual([claim.kind for claim in claims], ["ident", "ident"])

    def test_a_malformed_marker_stays_a_claim(self):
        # Unlike [HALT] without an arrow, a malformed IDENT marker must not
        # disappear: the marker is a claim attempt and has to stay visible as
        # unverifiable, never be silently dropped.
        claims = parse_report("[IDENT: n=3t ; a=t, b=4t]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].kind, "ident")

    def test_lowercase_marker_is_not_the_marker(self):
        self.assertEqual(parse_report("[ident: n=3t ; a=t, b=4t, c=12t]\n"), [])

    def test_unterminated_marker_is_no_claim(self):
        self.assertEqual(parse_report("[IDENT: n=3t ; a=t, b=4t, c=12t\n"), [])

    def test_unterminated_marker_stays_linear(self):
        start = time.perf_counter()
        claims = parse_report("[IDENT:" + " " * 2000 + "\n")
        elapsed = time.perf_counter() - start
        self.assertEqual(claims, [])
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for a hostile line")

    def test_absurdly_long_line_is_ignored(self):
        self.assertEqual(parse_report("[IDENT: " + "a" * 9000 + "]\n"), [])


class IdentRegistryTest(unittest.TestCase):
    def test_ident_is_registered(self):
        self.assertIn(ident.IDENT, claimtypes.CLAIM_TYPES)
        self.assertEqual(ident.IDENT.kind, "ident")
        self.assertIs(claimtypes.checker_for("ident"), ident.check)

    def test_the_checker_needs_no_repository(self):
        self.assertFalse(kind_needs_repo("ident"))

    def test_the_type_binds_no_commit(self):
        claims = parse_report("[COMMIT: " + "a" * 40 + "]\n" + THREE_T + "\n")
        ident_claims = [claim for claim in claims if claim.kind == "ident"]
        self.assertEqual(len(ident_claims), 1)
        self.assertIsNone(ident_claims[0].fields.get("commit"))


class IdentCheckTest(unittest.TestCase):
    def ctx(self, **kw):
        return Ctx(repo=".", tmp_dir=".", **kw)

    def check_report(self, text, ctx=None):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx or self.ctx())

    def test_three_t_identity_confirms(self):
        result = self.check_report(THREE_T)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(
            result.command,
            "expand 1/(t) + 1/(4t) + 1/(12t) - 4/(3t) as one rational function in t",
        )
        self.assertEqual(result.output, "numerator=0")
        self.assertIsNone(result.sandboxed)

    def test_the_proof_text_pins_the_boundary(self):
        result = self.check_report(THREE_T)
        self.assertEqual(
            result.reason,
            PROOF.format(bound=1, n="3t", a="t", b="4t", c="12t"),
        )
        self.assertIn("holds as a rational identity in t for every t >= 1", result.reason)
        self.assertIn("not a proof of the conjecture", result.reason)
        lowered = result.reason.lower()
        self.assertNotIn("the conjecture is proven", lowered)
        self.assertNotIn("proves the conjecture", lowered)
        self.assertNotIn("proof of erdos", lowered)

    def test_every_confirmed_class_carries_the_boundary(self):
        for marker in (THREE_T, EVEN_T, FIVE_T, SEVEN_T, ELEVEN_T):
            with self.subTest(marker=marker):
                result = self.check_report(marker)
                self.assertIs(result.verdict, Verdict.CONFIRMED)
                self.assertIn("not a proof of the conjecture", result.reason)
                self.assertIn("one progression", result.reason)

    def test_even_class_confirms(self):
        result = self.check_report(EVEN_T)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_five_class_confirms(self):
        result = self.check_report(FIVE_T)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_seven_class_confirms(self):
        result = self.check_report(SEVEN_T)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_eleven_class_confirms(self):
        result = self.check_report(ELEVEN_T)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_an_explicit_range_is_honored(self):
        result = self.check_report(SHIFTED)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("holds as a rational identity in t for every t >= 0", result.reason)

    def test_wrong_coefficient_refutes(self):
        result = self.check_report(FALSIFIED)
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertTrue(result.output.startswith("numerator="))
        self.assertNotEqual(result.output, "numerator=0")
        self.assertIn("differ", result.reason)

    def test_wrong_denominator_refutes(self):
        result = self.check_report("[IDENT: n=3t ; a=t, b=4t, c=12t+1]")
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_wrong_left_side_refutes(self):
        result = self.check_report("[IDENT: n=3t ; a=t, b=t, c=t]")
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_a_false_identity_is_refuted_even_with_a_bad_range(self):
        # A false identity fails for infinitely many t in any unbounded
        # range; it is REFUTED, not excused into UNVERIFIABLE by the range.
        result = self.check_report("[IDENT: n=3t ; a=t, b=4t+1, c=12t ; t >= 0]")
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_a_positive_slope_witness_is_the_first_violating_t(self):
        # slope > 0 violates on a prefix of the range: the first witness is
        # the bound itself, never the crossing (which lies above it).
        self.assertEqual(ident._first_violation(2, -3, 1, 0), (1, -1))
        result = self.check_report("[IDENT: n=4t-10 ; a=4t-10, b=4t-10, c=2t-5 ; t >= 1]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("at t = 1 it is -6", result.reason)

    def test_the_witness_matches_a_brute_force_scan(self):
        for slope in range(-4, 5):
            for offset in range(-5, 6):
                for bound in range(0, 4):
                    for threshold in (0, 1):
                        with self.subTest(
                            slope=slope, offset=offset, bound=bound, threshold=threshold
                        ):
                            expected = next(
                                (
                                    (t, slope * t + offset)
                                    for t in range(bound, bound + 30)
                                    if slope * t + offset <= threshold
                                ),
                                None,
                            )
                            self.assertEqual(
                                ident._first_violation(slope, offset, bound, threshold),
                                expected,
                            )

    def test_a_huge_falsified_coefficient_still_refutes(self):
        # A product beyond the interpreter's int-to-str cap must still yield
        # REFUTED with a readable (truncated) witness, not a generic failure.
        result = self.check_report(
            "[IDENT: n=3t ; a=" + "9" * 2200 + "t, b=" + "8" * 2200 + "t, c=12t]"
        )
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertTrue(result.output.startswith("numerator="))
        self.assertIn("...", result.output)

    def test_a_marker_with_inner_brackets_is_no_marker(self):
        # A deliberate boundary, like the halt.py pattern: the marker regex
        # excludes brackets to stay linear, so a bracket inside the body
        # makes the text no marker at all (nothing is silently half-parsed).
        self.assertEqual(parse_report("[IDENT: n=3t ; a=[t], b=4t, c=12t]\n"), [])

    def test_a_zero_in_the_range_is_unverifiable(self):
        result = self.check_report(ZERO_RANGE)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("t = 0", result.reason)
        self.assertIn("not positive", result.reason)

    def test_a_negative_slope_is_unverifiable(self):
        # The identity holds as a rational function, but a = -t+51 reaches
        # zero at t = 51: the declared range is not soundly covered.
        result = self.check_report(NEGATIVE_SLOPE)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("t = 51", result.reason)

    def test_the_check_needs_no_repository(self):
        result = self.check_report(THREE_T, ctx=Ctx(repo="/nonexistent", tmp_dir="."))
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_check_starts_no_subprocess(self):
        with mock.patch(
            "subprocess.run", side_effect=AssertionError("subprocess")
        ), mock.patch("subprocess.Popen", side_effect=AssertionError("subprocess")):
            result = self.check_report(THREE_T)
        self.assertIs(result.verdict, Verdict.CONFIRMED)


class IdentRobustnessTest(unittest.TestCase):
    def check_report(self, text):
        claims = parse_report(text + "\n")
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], Ctx(repo=".", tmp_dir="."))

    def test_non_affine_inputs_are_unverifiable(self):
        for body in (
            "n=3t*t ; a=t, b=4t, c=12t",
            "n=3t^2 ; a=t, b=4t, c=12t",
            "n=3/t ; a=t, b=4t, c=12t",
            "n=3 t ; a=t, b=4t, c=12t",
            "n=3.5t ; a=t, b=4t, c=12t",
            "n=t ; a=t/2, b=2t, c=2t",
            "n= ; a=t, b=4t, c=12t",
        ):
            with self.subTest(body=body):
                result = self.check_report(f"[IDENT: {body}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_unknown_parameters_are_unverifiable(self):
        result = self.check_report("[IDENT: n=3s ; a=s, b=4s, c=12s]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_missing_duplicate_or_unknown_keys_are_unverifiable(self):
        for body in (
            "n=3t ; a=t, b=4t",
            "n=3t ; a=t, b=4t, c=12t, d=5t",
            "n=3t ; a=t, a=2t, c=12t",
            "n=3t ; a=t, b=4t, c=12t ; t >= 1 ; extra=1",
            "a=t, b=4t, c=12t ; n=3t",
            "n=3t",
            "",
        ):
            with self.subTest(body=body):
                result = self.check_report(f"[IDENT: {body}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_bad_ranges_are_unverifiable(self):
        for tail in ("t >= -1", "t >= 1.5", "s >= 1", "t > 1", "t >= x", "t >= "):
            with self.subTest(tail=tail):
                result = self.check_report(f"[IDENT: n=3t ; a=t, b=4t, c=12t ; {tail}]")
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_huge_integers_are_unverifiable(self):
        result = self.check_report(f"[IDENT: n=3t ; a={'9' * 5000}t, b=4t, c=12t]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_a_nul_byte_is_unverifiable(self):
        result = self.check_report("[IDENT: n=3t ; a=t, b=4t, c=12t\x00]")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("NUL", result.reason)


class IdentBoundaryTest(unittest.TestCase):
    """[IDENT] proves one progression for all its parameters -- it is not a
    proof of the conjecture. The docs carry that boundary; this test keeps it
    from being edited away."""

    def docs(self):
        for name in ("README.md", "SPEC.md"):
            with open(os.path.join(REPO_ROOT, name), encoding="utf-8") as handle:
                yield name, handle.read()

    def test_the_docs_pin_the_conjecture_boundary(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("kein Beweis der Vermutung", text)

    def test_the_docs_pin_the_all_parameters_boundary(self):
        for name, text in self.docs():
            with self.subTest(doc=name):
                self.assertIn("fuer alle Parameter", text)

    def test_the_erdos_straus_evaluation_verifies_its_own_claims(self):
        # The evaluation under yesdocs/erdos-straus/ carries IDENT markers as
        # its machine-checked evidence: every claim it makes must verify, and
        # nothing but ident claims may sneak in.
        path = os.path.join(REPO_ROOT, "yesdocs", "erdos-straus", "README.md")
        with open(path, encoding="utf-8") as handle:
            claims = parse_report(handle.read())
        self.assertGreaterEqual(len(claims), 6)
        for claim in claims:
            with self.subTest(line=claim.line):
                self.assertEqual(claim.kind, "ident")
                result = run_claim(claim, Ctx(repo=None, tmp_dir=None))
                self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
                self.assertIn("not a proof of the conjecture", result.reason)


if __name__ == "__main__":
    unittest.main()

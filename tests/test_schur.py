"""Tests for the deterministic Schur coloring search
(``bemyself.experiments.schur``).

The search finds a coloring of 1..N with k colors without a monochromatic
solution of x + y = z, for a fixed seed and a fixed node budget: two runs
with the same arguments must produce the identical certificate. A found
certificate is not taken on faith -- it is re-checked with the [COLORING]
checker of this repository. Every certificate the search returns is an
own-search certificate, not a literature value.
"""

import io
import os
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bemyself.checks import Ctx, run_claim
from bemyself.experiments import schur
from bemyself.model import Verdict
from bemyself.report import parse_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The small Schur numbers the search must reproduce on its own: S(1)=1,
# S(2)=4, S(3)=13, S(4)=44.
SMALL_CASES = ((1, 1), (2, 4), (3, 13), (4, 44))

LINE_RE = re.compile(
    r"\Acoloring k=(?P<k>[1-9]) n=(?P<n>[0-9]+) "
    r"nodes=(?P<nodes>[0-9]+) (?P<digits>[1-9]+)\Z"
)


def checker_confirms(k, digits):
    marker = f"[COLORING: k={k} ; {digits}]"
    claims = parse_report(marker + "\n")
    assert len(claims) == 1, marker
    result = run_claim(claims[0], Ctx(repo=None, tmp_dir=None))
    return result.verdict


class SchurSearchTest(unittest.TestCase):
    def test_small_cases_are_found_and_verified(self):
        for k, n in SMALL_CASES:
            with self.subTest(k=k, n=n):
                digits = schur.search(k, n)
                self.assertIsNotNone(digits, f"no coloring found for k={k} n={n}")
                self.assertEqual(len(digits), n)
                self.assertIs(checker_confirms(k, digits), Verdict.CONFIRMED)

    def test_the_search_is_deterministic(self):
        for k, n in ((3, 13), (4, 44)):
            with self.subTest(k=k, n=n):
                first = schur.search(k, n)
                second = schur.search(k, n)
                self.assertEqual(first, second)

    def test_a_budget_limited_search_is_also_deterministic(self):
        # A budget far below what 4/44 needs: no randomness and no partial
        # state may leak -- both runs must agree exactly.
        first = schur.search(4, 44, max_nodes=500)
        second = schur.search(4, 44, max_nodes=500)
        self.assertEqual(first, second)

    def test_every_found_certificate_passes_the_checker(self):
        # Whatever the search returns must survive the independent checker:
        # the search has no licence to fabricate a certificate.
        for k, n in ((2, 4), (3, 13), (4, 44)):
            digits = schur.search(k, n)
            self.assertIsNotNone(digits)
            marker = f"[COLORING: k={k} ; {digits}]"
            claims = parse_report(marker + "\n")
            self.assertEqual(len(claims), 1)
            result = run_claim(claims[0], Ctx(repo=None, tmp_dir=None))
            self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)

    def test_the_documented_own_search_certificates_are_reproduced(self):
        # The evaluation yesdocs/schur/ carries the own-search certificates
        # of S(3) = 13 and S(4) = 44; the search must still produce exactly
        # those certificates -- the documentation and the search cannot drift
        # apart silently.
        path = os.path.join(REPO_ROOT, "yesdocs", "schur", "README.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for k, n in ((3, 13), (4, 44)):
            with self.subTest(k=k, n=n):
                digits = schur.search(k, n)
                self.assertIsNotNone(digits)
                self.assertIn(f"[COLORING: k={k} ; {digits}]", text)

    def test_an_exhausted_budget_is_deterministic_and_honest(self):
        # A tiny budget cannot find a 160/5 coloring; the outcome is None,
        # twice, and no partial or fabricated certificate appears.
        first = schur.search(5, 160, max_nodes=1)
        second = schur.search(5, 160, max_nodes=1)
        self.assertIsNone(first)
        self.assertIsNone(second)

    def test_invalid_arguments_are_rejected(self):
        for k, n in ((0, 4), (10, 4), (5, 0), (-1, 4)):
            with self.subTest(k=k, n=n):
                with self.assertRaises(ValueError):
                    schur.search(k, n)


class SchurCliTest(unittest.TestCase):
    def run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = schur.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_cli_prints_one_parseable_line(self):
        code, text, _ = self.run_cli(["4", "44"])
        self.assertEqual(code, 0, text)
        lines = text.splitlines()
        self.assertEqual(len(lines), 1, text)
        match = LINE_RE.match(lines[0])
        self.assertIsNotNone(match, text)
        self.assertEqual(match.group("k"), "4")
        self.assertEqual(match.group("n"), "44")
        self.assertEqual(len(match.group("digits")), 44)
        self.assertIs(
            checker_confirms(4, match.group("digits")), Verdict.CONFIRMED
        )

    def test_cli_is_deterministic(self):
        code_a, text_a, _ = self.run_cli(["4", "44", "--budget", "100"])
        code_b, text_b, _ = self.run_cli(["4", "44", "--budget", "100"])
        self.assertEqual(code_a, code_b)
        self.assertEqual(text_a, text_b)

    def test_cli_reports_a_miss_with_exit_one(self):
        code, text, _ = self.run_cli(["5", "160", "--budget", "1"])
        self.assertEqual(code, 1)
        self.assertIn("none k=5 n=160", text)
        self.assertIn("budget=1", text)

    def test_cli_usage_errors_exit_two(self):
        for argv in (["0", "4"], ["5"], ["5", "4", "extra"], ["x", "4"], ["5", "0"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(argv)
                self.assertEqual(code, 2, (argv, err))
                self.assertIn("usage", err.lower())


if __name__ == "__main__":
    unittest.main()

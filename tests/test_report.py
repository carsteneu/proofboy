import re
import time
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.checks import Ctx, run_claim
from bemyself.model import Cause, ClaimType, Result, Verdict
from bemyself.report import parse_report


FULL_REPORT = """\
### Phase 6: FINISH
**Status:** COMPLETE
**send_to payload:** `[DONE] [DEPLOY: yes] [COMMIT: 0123abc] [BRANCH: yesloop/demo] [MERGE: no] did the thing`
**Files in scope:** a.txt, b.txt
Tests run: python3 -m unittest test_ok -> exit 0
"""


class ParseReportTest(unittest.TestCase):
    def setUp(self):
        self.claims = parse_report(FULL_REPORT)

    def by_kind(self, kind):
        return [c for c in self.claims if c.kind == kind]

    def test_commit_claim(self):
        cs = self.by_kind("commit_exists")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["commit"], "0123abc")

    def test_branch_claim_pairs_with_commit(self):
        cs = self.by_kind("branch_pushed")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["branch"], "yesloop/demo")
        self.assertEqual(cs[0].fields["commit"], "0123abc")

    def test_tests_claim(self):
        cs = self.by_kind("tests_green")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["command"], "python3 -m unittest test_ok")
        self.assertEqual(cs[0].fields["claimed_exit"], 0)
        self.assertEqual(cs[0].fields["commit"], "0123abc")

    def test_diff_scope_claim(self):
        cs = self.by_kind("diff_scope")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["head"], "0123abc")
        self.assertEqual(list(cs[0].fields["planned"]), ["a.txt", "b.txt"])

    def test_merge_and_deploy_claims(self):
        self.assertEqual(len(self.by_kind("merge")), 1)
        self.assertEqual(len(self.by_kind("deploy")), 1)

    def test_merge_claim_binds_to_the_single_commit(self):
        claims = parse_report(
            "**send_to payload:** `[COMMIT: aaaa1111] [MERGE: yesloop/demo]`\n"
        )
        merge = [c for c in claims if c.kind == "merge"][0]
        self.assertEqual(merge.fields["value"], "yesloop/demo")
        self.assertEqual(merge.fields["commit"], "aaaa1111")

    def test_merge_claim_stays_unbound_with_several_distinct_commits(self):
        text = (
            "**send_to payload:** `[COMMIT: aaaa1111] [MERGE: yesloop/demo]`\n"
            "**send_to payload:** `[COMMIT: bbbb2222]`\n"
        )
        merge = [c for c in parse_report(text) if c.kind == "merge"][0]
        self.assertIsNone(merge.fields["commit"])

    def test_line_numbers(self):
        self.assertEqual(self.by_kind("commit_exists")[0].line, 3)
        self.assertEqual(self.by_kind("diff_scope")[0].line, 4)
        self.assertEqual(self.by_kind("tests_green")[0].line, 5)

    def test_raw_line_is_preserved(self):
        c = self.by_kind("commit_exists")[0]
        self.assertIn("[COMMIT: 0123abc]", c.raw)

    def test_no_markers_yields_no_claims(self):
        self.assertEqual(parse_report("nothing to see here\n"), [])

    def test_absurdly_long_line_is_ignored(self):
        self.assertEqual(parse_report("Tests run: " + "a" * 200000 + " -> exit 0\n"), [])

    def test_unicode_arrow(self):
        claims = parse_report("Tests run: go test ./... \u2192 exit 1\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].kind, "tests_exit")
        self.assertEqual(claims[0].fields["command"], "go test ./...")
        self.assertEqual(claims[0].fields["claimed_exit"], 1)
        self.assertIsNone(claims[0].fields["commit"])

    def test_zero_exit_is_a_green_claim(self):
        claims = parse_report("Tests run: go test ./... -> exit 0\n")
        self.assertEqual(claims[0].kind, "tests_green")

    def test_branch_without_commit(self):
        claims = parse_report("[BRANCH: yesloop/x]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["branch"], "yesloop/x")
        self.assertIsNone(claims[0].fields["commit"])

    def test_nonzero_exit_is_not_a_green_claim(self):
        claims = parse_report("Tests run: bash run.sh -> exit 137\n")
        self.assertEqual(claims[0].kind, "tests_exit")
        self.assertEqual(claims[0].fields["claimed_exit"], 137)

    def test_multiple_distinct_commits_leave_dependent_claims_unbound(self):
        text = (
            "**send_to payload:** `[COMMIT: aaaa1111] [BRANCH: yesloop/x]`\n"
            "**send_to payload:** `[COMMIT: bbbb2222]`\n"
            "**Files in scope:** a.txt\n"
            "Tests run: python3 -m unittest x -> exit 0\n"
        )
        claims = parse_report(text)
        tests = [c for c in claims if c.kind == "tests_green"][0]
        self.assertIsNone(tests.fields["commit"])
        diff = [c for c in claims if c.kind == "diff_scope"][0]
        self.assertIsNone(diff.fields["head"])
        branch = [c for c in claims if c.kind == "branch_pushed"][0]
        self.assertIsNone(branch.fields["commit"])

    def test_duplicate_commit_markers_still_bind(self):
        text = (
            "**send_to payload:** `[COMMIT: aaaa1111]`\n"
            "**send_to payload:** `[COMMIT: aaaa1111]`\n"
            "Tests run: python3 -m unittest x -> exit 0\n"
        )
        tests = [c for c in parse_report(text) if c.kind == "tests_green"][0]
        self.assertEqual(tests.fields["commit"], "aaaa1111")


class ClaimTypeCommitBindingTest(unittest.TestCase):
    """An optional claim type declaring ``binds_commit`` receives the report's
    single commit -- a registry declaration, not a parser special case."""

    def compute_claims(self, text):
        return [claim for claim in parse_report(text) if claim.kind == "compute"]

    def test_compute_binds_to_the_single_commit(self):
        claims = self.compute_claims(
            f"**send_to payload:** `[COMMIT: aaaa1111]`\n[COMPUTE: python3 emit.py -> {'a' * 64}]\n"
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["commit"], "aaaa1111")

    def test_compute_stays_unbound_with_several_distinct_commits(self):
        claims = self.compute_claims(
            "**send_to payload:** `[COMMIT: aaaa1111]`\n"
            "**send_to payload:** `[COMMIT: bbbb2222]`\n"
            f"[COMPUTE: python3 emit.py -> {'a' * 64}]\n"
        )
        self.assertIsNone(claims[0].fields["commit"])

    def test_a_placeholder_marker_does_not_block_the_binding(self):
        # A yesloop section template carries "[COMMIT: <hash>]" next to the
        # real hash; only hash-shaped values count as commits.
        claims = self.compute_claims(
            "**send_to payload:** `[DONE] [COMMIT: <hash>]`\n"
            "**send_to payload:** `[COMMIT: aaaa1111]`\n"
            f"[COMPUTE: python3 emit.py -> {'a' * 64}]\n"
        )
        self.assertEqual(claims[0].fields["commit"], "aaaa1111")

    def test_placeholders_alone_leave_the_claim_unbound(self):
        claims = self.compute_claims(
            "**send_to payload:** `[COMMIT: <hash>]`\n"
            f"[COMPUTE: python3 emit.py -> {'a' * 64}]\n"
        )
        self.assertIsNone(claims[0].fields["commit"])

    def test_any_registered_type_can_declare_the_binding(self):
        def parse(match, raw):
            return {"value": match.group(1)}

        def check(claim, ctx):
            return Result(Verdict.CONFIRMED, reason="stub")

        dummy = ClaimType(
            kind="dummy",
            pattern=re.compile(r"\[DUMMY: (\w+)\]"),
            parse=parse,
            check=check,
            binds_commit=True,
        )
        with mock.patch.object(claimtypes, "CLAIM_TYPES", claimtypes.CLAIM_TYPES + (dummy,)):
            claims = parse_report("[COMMIT: aaaa1111]\n[DUMMY: x]\n")
        bound = [claim for claim in claims if claim.kind == "dummy"]
        self.assertEqual(len(bound), 1)
        self.assertEqual(bound[0].fields["commit"], "aaaa1111")


class PlaceholderReportTest(unittest.TestCase):
    """A marker body that reads as a placeholder is a template, not an
    assertion: the claim is skipped like a line without the marker, never
    reported UNVERIFIABLE."""

    def test_every_marker_type_ignores_its_placeholder(self):
        placeholders = (
            "[COMMIT: <hash>]",
            "[BRANCH: <name>]",
            "[MERGE: <branch>]",
            "[DEPLOY: ...]",
            "[HALT: <machine> -> <steps>]",
            "[SEARCHED: <machine> -> <n>]",
            "[COMPUTE: <cmd> -> <sha256>]",
            "[CYCLE: <machine> -> <t1>,<t2>,<d>]",
            "[IDENT: n=<affine> ; a=<affine>, b=<affine>, c=<affine>]",
            "[COLORING: k=<k> ; <digits>]",
            "[ARTIFACT: <pfad> -> <sha256>]",
        )
        for line in placeholders:
            with self.subTest(line=line):
                self.assertEqual(parse_report(line + "\n"), [])

    def test_todo_value_is_a_placeholder(self):
        for line in ("[COMMIT: TODO]", "[COMMIT: todo]", "[DEPLOY: TODO]"):
            with self.subTest(line=line):
                self.assertEqual(parse_report(line + "\n"), [])

    def test_truncated_digest_ellipsis_is_a_placeholder(self):
        for line in (
            "[COMMIT: e5b68dd1\u2026]",
            "[COMMIT: e5b68dd1...]",
            "[COMPUTE: python3 emit.py -> e5b68dd1\u2026]",
            "[COMPUTE: python3 emit.py -> `e5b68dd1\u2026`]",
            "[COMPUTE: python3 emit.py -> docs/\u2026]",
        ):
            with self.subTest(line=line):
                self.assertEqual(parse_report(line + "\n"), [])

    def test_path_pattern_ellipses_are_not_placeholders(self):
        for line, kind in (
            ("Tests run: go test ./... -> exit 0\n", "tests_green"),
            ("Tests run: python3 -m pytest src/... -> exit 0\n", "tests_green"),
        ):
            with self.subTest(line=line):
                self.assertEqual([claim.kind for claim in parse_report(line)], [kind])

    def test_tests_claim_with_a_placeholder_command(self):
        self.assertEqual(parse_report("Tests run: <cmd> -> exit 0\n"), [])

    def test_diff_scope_with_placeholder_paths(self):
        for line in (
            "**Files in scope:** <pfad1>, <pfad2>\n",
            "**Files in scope:** good.txt, <pfad2>\n",
        ):
            with self.subTest(line=line):
                self.assertEqual(parse_report(line), [])

    def test_a_placeholder_score_makes_the_whole_claim_a_template(self):
        # The attached score is part of the HALT claim's fields: a placeholder
        # anywhere in them marks the line as a template (the uniform rule,
        # documented in README and SPEC).
        self.assertEqual(
            parse_report("[HALT: 1RB1RZ_0LA0LA -> 3] [SCORE: 1RB1RZ_0LA0LA -> <ones>]\n"),
            [],
        )

    def test_placeholder_markers_do_not_hide_literal_markers_on_the_same_line(self):
        claims = parse_report("[COMMIT: <hash>] [MERGE: no]\n")
        self.assertEqual([claim.kind for claim in claims], ["merge"])

    def test_a_placeholder_commit_does_not_bind_dependent_claims(self):
        claims = parse_report(
            "**send_to payload:** `[DONE] [COMMIT: <hash>]`\n"
            "**send_to payload:** `[COMMIT: aaaa1111]`\n"
            "Tests run: python3 -m unittest x -> exit 0\n"
        )
        self.assertEqual([claim.kind for claim in claims], ["commit_exists", "tests_green"])
        self.assertEqual(claims[0].fields["commit"], "aaaa1111")
        self.assertEqual(claims[1].fields["commit"], "aaaa1111")

    def test_go_package_patterns_are_not_placeholders(self):
        # "./..." is the tail of a Go package pattern, not a truncated token.
        claims = parse_report("Tests run: go test ./... -> exit 0\n")
        self.assertEqual([claim.kind for claim in claims], ["tests_green"])

    def test_real_values_are_not_placeholders(self):
        # The conservative side: values that merely look unusual stay claims
        # and keep their old verdicts.
        text = (
            "[COMMIT: e5b68dd1]\n"  # short, but hash-shaped
            "[COMMIT: HEAD]\n"  # no hash, still an assertion
            "[HALT: 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC -> 16]\n"
            "[HALT: M -> 3]\n"  # a machine name, not a placeholder
            "[MERGE: no]\n"
            "[DEPLOY: none]\n"
            "[BRANCH: yesloop/x]\n"
            "**Files in scope:** a<b.txt, c.txt\n"  # '<' without a closing '>'
            "[DEPLOY: <>]\n"  # an empty token is no template slot
        )
        kinds = [claim.kind for claim in parse_report(text)]
        self.assertEqual(
            kinds,
            [
                "commit_exists",
                "commit_exists",
                "halt",
                "halt",
                "merge",
                "deploy",
                "branch_pushed",
                "diff_scope",
                "deploy",
            ],
        )

    def test_angle_tokens_inside_real_values_are_the_documented_boundary(self):
        # Accepted loss (README, "Grenzen"): a value whose text contains an
        # angle token is indistinguishable from a template slot, so a real
        # command with one is skipped like a template.
        self.assertEqual(
            parse_report("Tests run: sed 's/<[^>]*>//g' data.html -> exit 0\n"), []
        )

    def test_exact_placeholder_words_are_the_documented_boundary(self):
        # Accepted loss (README, "Grenzen"): a branch or file literally named
        # TODO is indistinguishable from the template word.
        self.assertEqual(parse_report("[BRANCH: todo]\n"), [])
        self.assertEqual(parse_report("**Files in scope:** TODO\n"), [])


class PlaceholderCaptureCostTest(unittest.TestCase):
    """The placeholder scan must stay linear on hostile input: the angle
    token excludes brackets and whitespace, so a run of '<' cannot send the
    engine into backtracking."""

    BUDGET = 0.5
    RUN = 2000

    def parsed_within_budget(self, line):
        start = time.perf_counter()
        claims = parse_report(line + "\n")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, self.BUDGET, f"{elapsed:.3f}s for a {len(line)}-char line")
        return claims

    def test_angle_runs_without_a_closing_bracket_stay_a_claim(self):
        # "<" without ">" is no template slot: the conservative side keeps the
        # claim, so a hostile run must not make the parser drop it for free.
        claims = self.parsed_within_budget("[COMMIT: " + "<" * 4000 + "]")
        self.assertEqual(len(claims), 1)

    def test_many_angle_tokens(self):
        self.assertEqual(self.parsed_within_budget("[COMMIT: " + "<x>" * self.RUN + "]"), [])

    def test_truncation_ellipsis_behind_a_long_body(self):
        self.assertEqual(self.parsed_within_budget("[COMMIT: " + "a" * 4000 + "...]"), [])


class UnknownMarkerTest(unittest.TestCase):
    """A marker no registered claim type claims is a defect: silently
    ignoring it let a report smuggle a claim of an unknown shape past the
    verifier."""

    def test_unknown_marker_with_a_real_body_is_a_defect(self):
        claims = parse_report("**send_to payload:** `[DONE] [FROB: 1]`\n")
        self.assertEqual([claim.kind for claim in claims], ["unknown_marker"])
        self.assertEqual(claims[0].fields["token"], "FROB")
        self.assertEqual(claims[0].line, 1)
        self.assertIn("[FROB: 1]", claims[0].raw)

    def test_the_unknown_marker_checker_is_a_defect(self):
        claim = parse_report("[FROB: 1]\n")[0]
        result = run_claim(claim, Ctx(repo=None, tmp_dir=None))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIs(result.cause, Cause.DEFECT)
        self.assertIn("FROB", result.reason)

    def test_ordinary_bracket_text_is_not_a_marker(self):
        for text in (
            "[sic]",
            "[1]",
            "[12: 30]",
            "[foo: bar]",
            "[Foo: bar]",
            "[FOO]",
            "[FOO bar]",
            "[A-Z: x]",
            "[0-9: x]",
            "[:alpha:]",
            "[[:upper:]:]",
            "d = {'A': 1}",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_report(text + "\n"), [])

    def test_a_marker_body_without_a_leading_space_still_counts(self):
        claims = parse_report("[FROB:bar]\n")
        self.assertEqual([claim.kind for claim in claims], ["unknown_marker"])

    def test_an_empty_body_is_still_a_marker(self):
        claims = parse_report("[FROB:]\n")
        self.assertEqual([claim.kind for claim in claims], ["unknown_marker"])

    def test_a_placeholder_body_keeps_the_template_rule(self):
        # P15: a marker body that reads as a template names no assertion. An
        # unknown token must not turn a briefing template into a defect.
        for text in (
            "[FROB: <wert>]",
            "[FROB: ...]",
            "[FROB: \u2026]",
            "[FROB: TODO]",
            "[FROB: e5b68dd1\u2026]",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_report(text + "\n"), [])

    def test_every_registered_token_is_claimed(self):
        # The claimed set follows the live registry: a token of an optional
        # type (even with a body its own parse rejects) is no unknown marker.
        for text in (
            "[HALT: kaputt]",
            "[SCORE: 1RB1RZ_0LA0LA -> 1]",
            "[SEARCHED: kaputt]",
            "[COMPUTE: kaputt]",
            "[CYCLE: kaputt]",
            "[IDENT: kaputt]",
            "[COLORING: kaputt]",
            "[ARTIFACT: kaputt]",
            "[LEAN: kaputt]",
            "[COMMIT: kaputt]",
            "[BRANCH: kaputt]",
            "[MERGE: kaputt]",
            "[DEPLOY: kaputt]",
        ):
            with self.subTest(text=text):
                kinds = [claim.kind for claim in parse_report(text + "\n")]
                self.assertNotIn("unknown_marker", kinds)

    def test_two_unknown_markers_on_one_line_are_two_defects(self):
        claims = parse_report("[FROB: 1] [QUUX: 2]\n")
        self.assertEqual(
            [(claim.kind, claim.fields["token"]) for claim in claims],
            [("unknown_marker", "FROB"), ("unknown_marker", "QUUX")],
        )

    def test_unknown_marker_beside_a_real_claim_shares_the_line(self):
        # Within one line the parser emits the recognized claims first and the
        # unknown-marker findings after them (the scan is its own pass); both
        # carry the same line number, so the verdict lists them side by side.
        claims = parse_report("[FROB: 1] [COMMIT: aaaa1111]\n")
        self.assertEqual(
            [(claim.kind, claim.line) for claim in claims],
            [("commit_exists", 1), ("unknown_marker", 1)],
        )

    def test_an_absurdly_long_line_yields_no_marker_either(self):
        line = "[FROB: 1] " + "x" * 9000
        self.assertEqual(parse_report(line + "\n"), [])


class UnknownMarkerCaptureCostTest(unittest.TestCase):
    """The unknown-marker scan must stay linear on hostile input: its body
    class never crosses a bracket, so every attempt is bounded by the
    distance to the next one."""

    BUDGET = 0.5
    RUN = 2000

    def parsed_within_budget(self, line):
        start = time.perf_counter()
        claims = parse_report(line + "\n")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, self.BUDGET, f"{elapsed:.3f}s for a {len(line)}-char line")
        return claims

    def test_many_unterminated_unknown_markers(self):
        self.assertEqual(self.parsed_within_budget("[FROB:" + "x" * self.RUN), [])

    def test_a_long_token_without_a_colon(self):
        self.assertEqual(self.parsed_within_budget("[" + "A" * (self.RUN * 3)), [])

    def test_many_short_unknown_markers(self):
        claims = self.parsed_within_budget("[FOO: x]" * 800)
        self.assertEqual(len(claims), 800)


if __name__ == "__main__":
    unittest.main()

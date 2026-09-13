"""P19: report profiles, the missing class as a defect, and the negative space.

A profile declares which claim classes a report of its kind must contain; a
required class the report does not yield is a defect (Exit 5, with and without
``--strict``). Every run reports the negative space: which classes were
sought, found and missed, so "found nothing" and "sought nothing" stay
distinguishable.
"""

import re
import unittest
from unittest import mock

from bemyself import claimtypes, profiles
from bemyself.checks import Ctx, run_claim
from bemyself.model import Cause, Claim, ClaimType, Result, Verdict
from bemyself.report import parse_report

COMMIT = "a" * 40


def pairs(claims, ctx=None):
    ctx = ctx or Ctx(repo=None, tmp_dir=None)
    return [(claim, run_claim(claim, ctx)) for claim in claims]


class ProfileRegistryTest(unittest.TestCase):
    def test_yesloop_done_requires_commit_branch_and_a_test_claim(self):
        self.assertEqual(
            profiles.PROFILES["yesloop-done"],
            (
                ("commit_exists",),
                ("branch_pushed",),
                ("tests_green", "tests_exit"),
            ),
        )

    def test_names_come_from_the_registry(self):
        self.assertEqual(profiles.profile_names(), tuple(profiles.PROFILES))

    def test_requirement_label_joins_the_alternatives(self):
        self.assertEqual(
            profiles.requirement_label(("tests_green", "tests_exit")),
            "tests_green/tests_exit",
        )


class ProfileClaimTest(unittest.TestCase):
    def test_complete_report_yields_no_profile_claim(self):
        claims = parse_report(
            f"**send_to payload:** `[COMMIT: {COMMIT}] [BRANCH: main]`\n"
            "Tests run: python3 -m unittest test_ok -> exit 0\n"
        )
        self.assertEqual(profiles.profile_claims(claims, "yesloop-done"), claims)

    def test_missing_test_claim_is_one_defect_naming_profile_and_class(self):
        claims = parse_report(
            f"**send_to payload:** `[COMMIT: {COMMIT}] [BRANCH: main]`\n"
        )
        extended = profiles.profile_claims(claims, "yesloop-done")
        self.assertEqual(len(extended), len(claims) + 1)
        violation = extended[-1]
        self.assertEqual(violation.kind, "profile")
        result = run_claim(violation, Ctx(repo=None, tmp_dir=None))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIs(result.cause, Cause.DEFECT)
        self.assertIn("yesloop-done", result.reason)
        self.assertIn("tests_green/tests_exit", result.reason)

    def test_a_placeholder_commit_does_not_count_as_the_commit_class(self):
        # The template line of a briefing yields no claim at all (P15), so the
        # profile sees the commit class as missing -- exactly the hole the
        # profile closes against a report that hides behind placeholders.
        claims = parse_report(
            "**send_to payload:** `[COMMIT: <hash>] [BRANCH: main]`\n"
            "Tests run: python3 -m unittest test_ok -> exit 0\n"
        )
        violation = profiles.profile_claims(claims, "yesloop-done")[-1]
        self.assertEqual(violation.kind, "profile")
        result = run_claim(violation, Ctx(repo=None, tmp_dir=None))
        self.assertIn("commit_exists", result.reason)

    def test_missing_classes_are_named_in_one_claim(self):
        extended = profiles.profile_claims([], "yesloop-done")
        self.assertEqual(len(extended), 1)
        result = run_claim(extended[0], Ctx(repo=None, tmp_dir=None))
        self.assertIs(result.cause, Cause.DEFECT)
        self.assertIn("commit_exists", result.reason)
        self.assertIn("branch_pushed", result.reason)
        self.assertIn("tests_green/tests_exit", result.reason)
        self.assertIn("classes", result.reason)

    def test_a_test_run_with_exit_one_satisfies_the_test_requirement(self):
        # The profile demands a test claim, not a green one: an honest failure
        # report states the test run.
        claims = parse_report(
            f"**send_to payload:** `[COMMIT: {COMMIT}] [BRANCH: main]`\n"
            "Tests run: python3 -m unittest test_bad -> exit 1\n"
        )
        self.assertEqual(profiles.profile_claims(claims, "yesloop-done"), claims)

    def test_without_a_profile_nothing_is_added(self):
        claims = parse_report("[MERGE: no]\n")
        self.assertEqual(profiles.profile_claims(claims, None), claims)

    def test_a_claim_added_by_the_cli_counts_as_present(self):
        # The profile runs after the --files override, so a diff_scope claim
        # the CLI added satisfies a profile that requires that class (the
        # shipped yesloop-done profile does not name it; this pins the
        # mechanism). Presence is a question of the claim's kind only.
        override = Claim("diff_scope", 0, "--files override", {"planned": ("a.txt",)})
        with mock.patch.dict(profiles.PROFILES, {"scoped": (("diff_scope",),)}):
            claims = parse_report("[MERGE: no]\n") + [override]
            self.assertEqual(profiles.profile_claims(claims, "scoped"), claims)

    def test_unknown_profile_name_raises(self):
        with self.assertRaises(KeyError):
            profiles.profile_claims([], "no-such-profile")


class NegativeSpaceTest(unittest.TestCase):
    def test_sought_found_and_missing_per_class(self):
        claims = parse_report(
            f"**send_to payload:** `[COMMIT: {COMMIT}] [BRANCH: main]`\n"
        )
        space = profiles.negative_space(pairs(claims), "yesloop-done")
        self.assertEqual(
            space["sought"],
            [["commit_exists"], ["branch_pushed"], ["tests_green", "tests_exit"]],
        )
        self.assertEqual(space["found"], ["commit_exists", "branch_pushed"])
        self.assertEqual(space["missing"], [["tests_green", "tests_exit"]])
        self.assertEqual(space["profile"], "yesloop-done")

    def test_without_a_profile_nothing_is_sought(self):
        claims = parse_report(f"**send_to payload:** `[COMMIT: {COMMIT}]`\n")
        space = profiles.negative_space(pairs(claims), None)
        self.assertIsNone(space["profile"])
        self.assertEqual(space["sought"], [])
        self.assertEqual(space["missing"], [])
        self.assertEqual(space["found"], ["commit_exists"])

    def test_an_unknown_profile_name_raises_here_too(self):
        # Same caller error as profile_claims: a name nothing registered must
        # not read as "nothing was sought".
        with self.assertRaises(KeyError):
            profiles.negative_space([], "no-such-profile")

    def test_meta_findings_are_no_found_class(self):
        unknown = Claim("unknown_marker", 1, "[FROB: 1]", {"token": "FROB"})
        violation = Claim(
            "profile", 0, "--profile yesloop-done", {"profile": "yesloop-done"}
        )
        space = profiles.negative_space(pairs([unknown, violation]), "yesloop-done")
        self.assertEqual(space["found"], [])
        self.assertEqual(len(space["missing"]), 3)

    def test_nothing_found_and_nothing_sought_are_distinguishable(self):
        nothing_found = profiles.render_negative_space(profiles.negative_space([], None))
        nothing_sought = profiles.render_negative_space(
            profiles.negative_space([], "yesloop-done")
        )
        self.assertIn("gesucht: keine (ohne --profile)", nothing_found)
        self.assertIn("gefunden: keine", nothing_found)
        self.assertIn("gefehlt: keine", nothing_found)
        self.assertIn(
            "gesucht: commit_exists, branch_pushed, tests_green/tests_exit", nothing_sought
        )
        self.assertIn("gefunden: keine", nothing_sought)
        self.assertIn(
            "gefehlt: commit_exists, branch_pushed, tests_green/tests_exit", nothing_sought
        )
        self.assertNotIn("(ohne --profile)", nothing_sought)

    def test_render_names_the_three_parts(self):
        claims = parse_report(
            f"**send_to payload:** `[COMMIT: {COMMIT}] [BRANCH: main]`\n"
        )
        line = profiles.render_negative_space(
            profiles.negative_space(pairs(claims), "yesloop-done")
        )
        self.assertTrue(line.startswith("negativraum: "))
        self.assertIn("gesucht: commit_exists, branch_pushed, tests_green/tests_exit", line)
        self.assertIn("gefunden: commit_exists, branch_pushed", line)
        self.assertIn("gefehlt: tests_green/tests_exit", line)


class ClaimTypeMarkersTest(unittest.TestCase):
    def test_kind_upper_is_the_default_marker_token(self):
        def parse(match, raw):
            return {"value": match.group(1)}

        def check(claim, ctx):
            return Result(Verdict.CONFIRMED, reason="stub")

        even = ClaimType(
            kind="even",
            pattern=re.compile(r"\[EVEN: (\d+)\]"),
            parse=parse,
            check=check,
        )
        self.assertEqual(even.markers, ())
        self.assertEqual(claimtypes.marker_tokens(even), ("EVEN",))

    def test_a_type_can_declare_several_marker_tokens(self):
        self.assertEqual(claimtypes.marker_tokens(claimtypes.halt.HALT), ("HALT", "SCORE"))


if __name__ == "__main__":
    unittest.main()

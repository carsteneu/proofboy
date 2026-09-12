import re
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.model import ClaimType, Result, Verdict
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


if __name__ == "__main__":
    unittest.main()

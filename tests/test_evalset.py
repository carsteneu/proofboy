"""Tests for the deterministic fixture builder and the standard eval set."""

import os
import subprocess
import tempfile
import unittest

from bemyself import evalset
from bemyself.report import parse_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_PATH = os.path.join(REPO_ROOT, "tests", "data", "pruefset.json")
COMMIT_NAMES = ("base", "good", "bad", "scoped", "unpushed", "fixed")


def _git(*args):
    return subprocess.run(("git", *args), capture_output=True, text=True)


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.fixture = evalset.build_fixture(os.path.join(cls._tmp.name, "fixture"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_commits_are_reproducible(self):
        other = evalset.build_fixture(os.path.join(self._tmp.name, "fixture-again"))
        self.assertEqual(other.commits, self.fixture.commits)

    def test_fixture_commits_are_named_and_hashed(self):
        self.assertEqual(set(self.fixture.commits), set(COMMIT_NAMES))
        for sha in self.fixture.commits.values():
            self.assertRegex(sha, r"\A[0-9a-f]{40}\Z")

    def test_remote_holds_pushed_main_and_feature(self):
        main = _git("--git-dir", self.fixture.remote, "rev-parse", "refs/heads/main")
        self.assertEqual(main.stdout.strip(), self.fixture.commits["scoped"], main.stderr)
        feature = _git("--git-dir", self.fixture.remote, "rev-parse", "refs/heads/feature")
        self.assertEqual(feature.stdout.strip(), self.fixture.commits["bad"], feature.stderr)

    def test_tests_pass_at_fixed_and_not_before(self):
        passing = subprocess.run(
            ("python3", "-m", "unittest", "test_ok", "test_bad"),
            cwd=self.fixture.repo,
            capture_output=True,
            text=True,
        )
        self.assertEqual(passing.returncode, 0, passing.stderr)
        failing_source = _git(
            "-C", self.fixture.repo, "show", f"{self.fixture.commits['bad']}:test_bad.py"
        )
        self.assertIn("assertEqual(1, 2)", failing_source.stdout)
        fixed_source = _git(
            "-C", self.fixture.repo, "show", f"{self.fixture.commits['fixed']}:test_bad.py"
        )
        self.assertNotIn("assertEqual(1, 2)", fixed_source.stdout)


class StandardSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.fixture = evalset.build_fixture(os.path.join(cls._tmp.name, "fixture"))
        cls.document = evalset.standard_set(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def cases(self):
        return self.document["cases"]

    def by_name(self):
        return {case["name"]: case for case in self.cases()}

    def test_thirty_cases_half_false(self):
        cases = self.cases()
        self.assertEqual(len(cases), 30)
        groups = [case["group"] for case in cases]
        self.assertEqual(groups.count("genuine"), 15)
        self.assertEqual(groups.count("false"), 15)
        names = [case["name"] for case in cases]
        self.assertEqual(len(set(names)), 30)

    def test_every_case_carries_report_and_base(self):
        commits = set(self.fixture.commits.values())
        self.assertIn(self.document["fixture"]["base"], commits)
        self.assertIn(self.document["fixture"]["head"], commits)
        for case in self.cases():
            self.assertTrue(case["report"].strip(), case["name"])
            self.assertIn(case["base"], commits, case["name"])
            self.assertTrue(case["note"], case["name"])

    def test_false_cases_mark_their_targets(self):
        for case in self.cases():
            if case["group"] == "false" and case["name"] not in (
                "f11-report-without-claims",
                "f12-hostile-giant-line",
                "f13-hostile-huge-report",
            ):
                self.assertTrue(case["targets"], case["name"])
        for case in self.cases():
            if case["group"] == "genuine":
                self.assertFalse(case.get("targets"), case["name"])

    def test_mandatory_cases_are_present(self):
        present = self.by_name()
        for name in (
            "f06-diff-empty",
            "f07-diff-planned-but-unchanged",
            "f10-commit-non-hex-head",
            "f11-report-without-claims",
            "f12-hostile-giant-line",
            "f13-hostile-huge-report",
            "f14-hostile-control-characters",
        ):
            self.assertIn(name, present, name)

    def test_report_without_claims_stays_empty(self):
        case = self.by_name()["f11-report-without-claims"]
        self.assertEqual(parse_report(case["report"]), [])
        self.assertEqual(case["expect_claim_count"], 0)
        self.assertEqual(case["targets"], [])

    def test_diff_cases_demand_refutation(self):
        cases = self.by_name()
        for name in ("f06-diff-empty", "f07-diff-planned-but-unchanged", "f08-diff-extra-changed"):
            self.assertEqual(cases[name]["expect_verdicts"]["diff_scope"], "REFUTED", name)

    def test_non_hex_commit_claim_never_confirmed(self):
        case = self.by_name()["f10-commit-non-hex-head"]
        claims = parse_report(case["report"])
        commits = [claim for claim in claims if claim.kind == "commit_exists"]
        self.assertEqual(len(commits), 2)
        values = {claim.fields["commit"] for claim in commits}
        self.assertIn("HEAD", values)
        self.assertEqual(case["targets"], ["commit_exists"])
        self.assertEqual(case["expect_verdicts"]["commit_exists"], "UNVERIFIABLE")

    def test_hostile_reports_parse_to_nothing(self):
        cases = self.by_name()
        for name in ("f12-hostile-giant-line", "f13-hostile-huge-report"):
            self.assertEqual(parse_report(cases[name]["report"]), [], name)

    def test_control_character_report_has_nul_in_a_field(self):
        case = self.by_name()["f14-hostile-control-characters"]
        claims = parse_report(case["report"])
        self.assertTrue(any("\x00" in (claim.fields.get("commit") or "") for claim in claims))
        self.assertEqual(case["expect_verdicts"]["commit_exists"], "UNVERIFIABLE")

    def test_generation_is_byte_stable(self):
        again = evalset.standard_set(self.fixture)
        self.assertEqual(evalset.set_bytes(self.document), evalset.set_bytes(again))

    def test_committed_set_matches_the_generator(self):
        with open(SET_PATH, "rb") as handle:
            committed = handle.read()
        self.assertEqual(evalset.set_bytes(evalset.standard_set(self.fixture)), committed)


if __name__ == "__main__":
    unittest.main()

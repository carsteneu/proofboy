"""Tests for the deterministic fixture builder and the standard eval set."""

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from bemyself import evalset
from bemyself.report import parse_report

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_PATH = os.path.join(REPO_ROOT, "tests", "data", "pruefset.json")
COMMIT_NAMES = (
    "base",
    "good",
    "bad",
    "scoped",
    "unpushed",
    "fixed",
    "tool",
    "experiment",
    "topic",
    "merge",
)


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

    def test_fixture_pins_the_object_format(self):
        with mock.patch.dict(os.environ, {"GIT_DEFAULT_HASH": "sha256"}):
            fixture = evalset.build_fixture(os.path.join(self._tmp.name, "fixture-hash"))
        self.assertEqual(fixture.commits, self.fixture.commits)

    def test_fixture_ignores_ambient_global_config(self):
        config = os.path.join(self._tmp.name, "ambient.gitconfig")
        with open(config, "w", encoding="utf-8") as handle:
            handle.write("[commit]\n\tgpgsign = true\n[init]\n\tdefaultObjectFormat = sha256\n")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": config}):
            fixture = evalset.build_fixture(os.path.join(self._tmp.name, "fixture-globalcfg"))
        self.assertEqual(fixture.commits, self.fixture.commits)

    def test_fixture_drops_ambient_git_variables(self):
        with mock.patch.dict(os.environ, {"GIT_NAMESPACE": "evil"}):
            fixture = evalset.build_fixture(os.path.join(self._tmp.name, "fixture-namespace"))
        # A surviving namespace would move the pushed refs under
        # refs/namespaces/evil/...; the bare remote must hold refs/heads/main.
        main = _git("--git-dir", fixture.remote, "rev-parse", "refs/heads/main")
        self.assertEqual(main.stdout.strip(), fixture.commits["scoped"], main.stderr)
        self.assertEqual(fixture.commits, self.fixture.commits)

    def test_fixture_ignores_template_hooks_and_config_parameters(self):
        template = os.path.join(self._tmp.name, "template")
        os.makedirs(os.path.join(template, "hooks"), exist_ok=True)
        marker = os.path.join(self._tmp.name, "hook-ran")
        hook = os.path.join(template, "hooks", "pre-commit")
        with open(hook, "w", encoding="utf-8") as handle:
            handle.write(f"#!/bin/sh\ntouch {marker}\n")
        os.chmod(hook, 0o755)
        trace = os.path.join(self._tmp.name, "trace.log")
        hostile = {
            "GIT_TEMPLATE_DIR": template,
            "GIT_CONFIG_PARAMETERS": "'commit.gpgsign=true'",
            "GIT_TRACE": trace,
        }
        with mock.patch.dict(os.environ, hostile):
            fixture = evalset.build_fixture(os.path.join(self._tmp.name, "fixture-hostile"))
        self.assertEqual(fixture.commits, self.fixture.commits)
        self.assertFalse(os.path.exists(marker))
        self.assertFalse(os.path.exists(trace))


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

    def test_case_count_and_groups(self):
        cases = self.cases()
        self.assertEqual(len(cases), 50)
        groups = [case["group"] for case in cases]
        self.assertEqual(groups.count("genuine"), 25)
        self.assertEqual(groups.count("false"), 25)
        names = [case["name"] for case in cases]
        self.assertEqual(len(set(names)), 50)

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
            "f18-compute-wrong-hash",
            "f19-cycle-wrong-offset",
            "f20-cycle-halting-machine",
            "g18-searched-bounded",
            "g19-cycle-translated",
            "g20-cycle-unverifiable-certificate",
            "g21-compute-erdos-straus-stub",
            "g24-artifact-digest",
            "g25-merge-commit",
            "f23-artifact-wrong-digest",
            "f24-artifact-path-escapes-root",
            "f25-merge-wrong-branch",
        ):
            self.assertIn(name, present, name)

    def test_merge_and_artifact_cases_pin_their_evidence(self):
        cases = self.by_name()
        merge = cases["g25-merge-commit"]
        self.assertEqual(merge["expect_verdicts"]["merge"], "CONFIRMED")
        self.assertIn(self.fixture.commits["merge"], merge["report"])
        self.assertEqual(merge["expect_verdicts"]["commit_exists"], "CONFIRMED")
        wrong = cases["f25-merge-wrong-branch"]
        self.assertEqual(wrong["targets"], ["merge"])
        self.assertEqual(wrong["expect_verdicts"]["merge"], "REFUTED")
        artifact = cases["g24-artifact-digest"]
        self.assertEqual(artifact["expect_verdicts"]["artifact"], "CONFIRMED")
        self.assertIn("good.txt", artifact["report"])
        self.assertIn(hashlib.sha256(b"good\n").hexdigest(), artifact["report"])
        for name, verdict in (
            ("f23-artifact-wrong-digest", "REFUTED"),
            ("f24-artifact-path-escapes-root", "UNVERIFIABLE"),
        ):
            self.assertEqual(cases[name]["targets"], ["artifact"], name)
            self.assertEqual(cases[name]["expect_verdicts"]["artifact"], verdict, name)

    def test_experiment_case_pins_its_certificate(self):
        case = self.by_name()["g21-compute-erdos-straus-stub"]
        self.assertEqual(case["group"], "genuine")
        self.assertEqual(case["expect_verdicts"]["compute"], "CONFIRMED")
        self.assertIn("python3 -m bemyself.experiments.erdos_straus", case["report"])
        self.assertEqual(case["base"], self.fixture.commits["experiment"])

    def test_cycle_cases_pin_their_certificates(self):
        cases = self.by_name()
        genuine = cases["g19-cycle-translated"]
        self.assertEqual(genuine["expect_verdicts"]["cycle"], "CONFIRMED")
        self.assertIn("-> 6,16,2", genuine["report"])
        unverifiable = cases["g20-cycle-unverifiable-certificate"]
        self.assertEqual(unverifiable["expect_verdicts"]["cycle"], "UNVERIFIABLE")
        self.assertIn("-> 16,6,2", unverifiable["report"])
        for name in ("f19-cycle-wrong-offset", "f20-cycle-halting-machine"):
            self.assertEqual(cases[name]["targets"], ["cycle"], name)
            self.assertEqual(cases[name]["expect_verdicts"]["cycle"], "REFUTED", name)

    def test_report_without_claims_stays_empty(self):
        case = self.by_name()["f11-report-without-claims"]
        self.assertEqual(parse_report(case["report"]), [])
        self.assertEqual(case["expect_claim_count"], 0)
        self.assertEqual(case["targets"], [])

    def test_diff_cases_demand_refutation(self):
        cases = self.by_name()
        for name in ("f06-diff-empty", "f07-diff-planned-but-unchanged", "f08-diff-extra-changed"):
            self.assertEqual(cases[name]["expect_verdicts"]["diff_scope"], "REFUTED", name)

    def test_f03_pins_never_confirmed(self):
        # The exact verdict for an empty test run depends on the host Python
        # (exit 5 since 3.12, exit 0 before), so only "never CONFIRMED" is pinned.
        case = self.by_name()["f03-tests-claimed-green-without-tests"]
        self.assertEqual(case["expect_not_confirmed"], ["tests_green"])
        self.assertNotIn("tests_green", case.get("expect_verdicts", {}))

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


class EvalsetRegenerationTest(unittest.TestCase):
    def test_module_regeneration_matches_the_committed_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "pruefset.json")
            proc = subprocess.run(
                (sys.executable, "-m", "bemyself.evalset", out_path),
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out_path, "rb") as handle:
                regenerated = handle.read()
            with open(SET_PATH, "rb") as handle:
                committed = handle.read()
        self.assertEqual(regenerated, committed)


if __name__ == "__main__":
    unittest.main()

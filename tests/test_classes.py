"""P18: defect vs. boundary -- the machine-readable class of unconfirmed claims.

Every UNVERIFIABLE result carries exactly one class: ``defect`` (the report or
the checked thing violates a required form), ``environment`` (a capability is
missing), ``limit`` (a budget was exceeded) or ``unverifiable`` (the
residual). A defect fails the run in both modes; a limit gets its own exit
code under ``--strict``. The old exit-code matrix (0-4) is pinned unchanged.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from bemyself.checks import Ctx, run_claim
from bemyself.cli import (
    EXIT_DEFECT,
    EXIT_LIMIT,
    EXIT_NOTHING,
    EXIT_OK,
    EXIT_REFUTED,
    EXIT_STRICT,
    exit_code,
    render_text,
)
from bemyself.claimtypes import artifact
from bemyself.model import Cause, Claim, Result, Verdict
from bemyself.report import parse_report
from tests.fixtures import make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def results(*specs):
    """(verdict, cause) pairs into claim/result tuples."""
    pairs = []
    for index, (verdict, cause) in enumerate(specs, start=1):
        claim = Claim("kind", index, "raw", {})
        pairs.append((claim, Result(verdict, reason="reason", cause=cause)))
    return pairs


class CauseTest(unittest.TestCase):
    def test_unverifiable_defaults_to_the_residual_class(self):
        self.assertIs(Result(Verdict.UNVERIFIABLE).cause, Cause.UNVERIFIABLE)

    def test_explicit_class_is_kept(self):
        self.assertIs(Result(Verdict.UNVERIFIABLE, cause=Cause.LIMIT).cause, Cause.LIMIT)

    def test_confirmed_and_refuted_carry_no_class(self):
        self.assertIsNone(Result(Verdict.CONFIRMED).cause)
        self.assertIsNone(Result(Verdict.REFUTED).cause)


class ExitCodeTest(unittest.TestCase):
    def test_defect_fails_without_strict(self):
        pairs = results(
            (Verdict.CONFIRMED, None), (Verdict.UNVERIFIABLE, Cause.DEFECT)
        )
        self.assertEqual(exit_code(pairs), EXIT_DEFECT)
        self.assertEqual(exit_code(pairs, strict=True), EXIT_DEFECT)

    def test_defect_alone_fails_without_strict(self):
        pairs = results((Verdict.UNVERIFIABLE, Cause.DEFECT))
        self.assertEqual(exit_code(pairs), EXIT_DEFECT)

    def test_refuted_keeps_its_code_beside_a_defect(self):
        pairs = results(
            (Verdict.REFUTED, None), (Verdict.UNVERIFIABLE, Cause.DEFECT)
        )
        self.assertEqual(exit_code(pairs), EXIT_REFUTED)
        self.assertEqual(exit_code(pairs, strict=True), EXIT_REFUTED)

    def test_limit_needs_strict(self):
        pairs = results(
            (Verdict.CONFIRMED, None), (Verdict.UNVERIFIABLE, Cause.LIMIT)
        )
        self.assertEqual(exit_code(pairs), EXIT_OK)
        self.assertEqual(exit_code(pairs, strict=True), EXIT_LIMIT)

    def test_limit_alone_keeps_nothing_confirmed_without_strict(self):
        pairs = results((Verdict.UNVERIFIABLE, Cause.LIMIT))
        self.assertEqual(exit_code(pairs), EXIT_NOTHING)
        self.assertEqual(exit_code(pairs, strict=True), EXIT_LIMIT)

    def test_environment_and_residual_keep_the_strict_code(self):
        for cause in (Cause.ENVIRONMENT, Cause.UNVERIFIABLE):
            with self.subTest(cause=cause):
                pairs = results((Verdict.CONFIRMED, None), (Verdict.UNVERIFIABLE, cause))
                self.assertEqual(exit_code(pairs), EXIT_OK)
                self.assertEqual(exit_code(pairs, strict=True), EXIT_STRICT)

    def test_limit_precedes_the_soft_classes_under_strict(self):
        pairs = results(
            (Verdict.CONFIRMED, None),
            (Verdict.UNVERIFIABLE, Cause.LIMIT),
            (Verdict.UNVERIFIABLE, Cause.ENVIRONMENT),
            (Verdict.UNVERIFIABLE, Cause.UNVERIFIABLE),
        )
        self.assertEqual(exit_code(pairs), EXIT_OK)
        self.assertEqual(exit_code(pairs, strict=True), EXIT_LIMIT)

    def test_defect_precedes_a_limit(self):
        pairs = results(
            (Verdict.UNVERIFIABLE, Cause.DEFECT),
            (Verdict.UNVERIFIABLE, Cause.LIMIT),
        )
        self.assertEqual(exit_code(pairs), EXIT_DEFECT)
        self.assertEqual(exit_code(pairs, strict=True), EXIT_DEFECT)

    def test_baseline_matrix_is_unchanged(self):
        # Measured on base 1d7b070 before P18 (see .yesmem/tmp/baseline):
        # 0=confirmed, 1=refuted, 3=nothing confirmed, 4=strict+UNVERIFIABLE.
        scenarios = [
            ([(Verdict.CONFIRMED, None)], 0, 0),
            ([(Verdict.REFUTED, None)], 1, 1),
            (
                [(Verdict.REFUTED, None), (Verdict.UNVERIFIABLE, Cause.UNVERIFIABLE)],
                1,
                1,
            ),
            ([(Verdict.UNVERIFIABLE, Cause.UNVERIFIABLE)], 3, 3),
            (
                [(Verdict.CONFIRMED, None), (Verdict.UNVERIFIABLE, Cause.UNVERIFIABLE)],
                0,
                4,
            ),
        ]
        for specs, default, strict in scenarios:
            with self.subTest(specs=specs):
                pairs = results(*specs)
                self.assertEqual(exit_code(pairs), default)
                self.assertEqual(exit_code(pairs, strict=True), strict)

    def test_empty_results_are_nothing_confirmed(self):
        self.assertEqual(exit_code([]), EXIT_NOTHING)
        self.assertEqual(exit_code([], strict=True), EXIT_NOTHING)


class SummaryLineTest(unittest.TestCase):
    def test_summary_names_every_class_and_the_executed_counts(self):
        pairs = results(
            (Verdict.CONFIRMED, None),
            (Verdict.UNVERIFIABLE, Cause.DEFECT),
            (Verdict.UNVERIFIABLE, Cause.LIMIT),
            (Verdict.UNVERIFIABLE, Cause.ENVIRONMENT),
            (Verdict.UNVERIFIABLE, Cause.UNVERIFIABLE),
        )
        text = render_text(pairs)
        self.assertIn(
            "summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 4 "
            "(defect: 1, environment: 1, limit: 1, unverifiable: 1); "
            "executed: 3, not executed: 2",
            text,
        )

    def test_a_fully_confirmed_run_reports_zero_of_every_class(self):
        text = render_text(results((Verdict.CONFIRMED, None)))
        self.assertIn(
            "summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0 "
            "(defect: 0, environment: 0, limit: 0, unverifiable: 0); "
            "executed: 1, not executed: 0",
            text,
        )


class ClassEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "fixture"))
        cls.noremote = make_repo(
            os.path.join(cls._tmp.name, "noremote"), with_remote=False
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def write_report(self, text, name="report.txt"):
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def invoke(self, *args, repo=None):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "bemyself",
                "check",
                "--repo",
                repo or self.repo.path,
                "--tmp",
                os.path.join(self._tmp.name, "tmp"),
                *args,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def claims(self, stdout):
        return {claim["kind"]: claim for claim in json.loads(stdout)["claims"]}

    def test_unpinnable_report_fails_without_strict(self):
        # A tests claim whose report names no commit cannot be checked: that
        # is a defect in the report, so the run fails even without --strict.
        report = self.write_report("Tests run: python3 -m unittest test_ok -> exit 0\n")
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        claim = self.claims(proc.stdout)["tests_green"]
        self.assertEqual(claim["verdict"], "UNVERIFIABLE")
        self.assertEqual(claim["class"], "defect")

    def test_unpinnable_report_fails_with_strict_too(self):
        report = self.write_report("Tests run: python3 -m unittest test_ok -> exit 0\n")
        proc = self.invoke("--report", report, "--json", "--strict")
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)

    def test_defect_fails_beside_a_confirmed_claim(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: -bad]`\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        claims = self.claims(proc.stdout)
        self.assertEqual(claims["commit_exists"]["verdict"], "CONFIRMED")
        self.assertEqual(claims["branch_pushed"]["class"], "defect")

    def test_refuted_still_dominates_a_defect(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {'0' * 40}] [BRANCH: -bad]`\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_limit_fails_only_with_strict_and_gets_its_own_code(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            "[HALT: 1RB1RZ_0LA0LA -> 47176871]\n"
        )
        default = self.invoke("--report", report, "--json")
        self.assertEqual(default.returncode, 0, default.stdout + default.stderr)
        claim = self.claims(default.stdout)["halt"]
        self.assertEqual(claim["verdict"], "UNVERIFIABLE")
        self.assertEqual(claim["class"], "limit")
        strict = self.invoke("--report", report, "--json", "--strict")
        self.assertEqual(strict.returncode, 6, strict.stdout + strict.stderr)

    def test_environment_claim_stays_strict_only(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: main]`\n"
        )
        proc = self.invoke("--report", report, "--json", repo=self.noremote.path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claim = self.claims(proc.stdout)["branch_pushed"]
        self.assertEqual(claim["class"], "environment")
        strict = self.invoke(
            "--report", report, "--json", "--strict", repo=self.noremote.path
        )
        self.assertEqual(strict.returncode, 4, strict.stdout + strict.stderr)

    def test_residual_class_is_the_default(self):
        # A [DEPLOY] status has no checker: residual ignorance, not a defect.
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [DEPLOY: no]`\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claim = self.claims(proc.stdout)["deploy"]
        self.assertEqual(claim["class"], "unverifiable")

    def test_merge_claim_with_a_malformed_branch_is_a_defect(self):
        # "-bad" is neither a status token nor a valid branch name: the claim
        # cannot bind -- a defect in the report -- so the run fails without
        # --strict. ([MERGE: no] by contrast stays residual.)
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [MERGE: -bad]`\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        claim = self.claims(proc.stdout)["merge"]
        self.assertEqual(claim["verdict"], "UNVERIFIABLE")
        self.assertEqual(claim["class"], "defect")
        self.assertIn("not a valid branch name", claim["reason"])

    def test_merge_status_token_stays_residual(self):
        # [MERGE: no] carries nothing to check -- residual, strict-only.
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [MERGE: no]`\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claim = self.claims(proc.stdout)["merge"]
        self.assertEqual(claim["class"], "unverifiable")
        strict = self.invoke("--report", report, "--json", "--strict")
        self.assertEqual(strict.returncode, 4, strict.stdout + strict.stderr)

    def test_json_summary_carries_the_class_counts(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: -bad]`\n"
            "[HALT: 1RB1RZ_0LA0LA -> 47176871]\n"
        )
        proc = self.invoke("--report", report, "--json")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["classes"]["defect"], 1)
        self.assertEqual(payload["classes"]["limit"], 1)
        self.assertEqual(payload["classes"]["environment"], 0)
        self.assertEqual(payload["classes"]["unverifiable"], 0)

    def test_text_output_ends_with_the_class_summary(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: -bad]`\n"
            "[HALT: 1RB1RZ_0LA0LA -> 47176871]\n"
        )
        proc = self.invoke("--report", report)
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        self.assertIn(
            "summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 2 "
            "(defect: 1, environment: 0, limit: 1, unverifiable: 0); "
            "executed: 1, not executed: 2",
            proc.stdout,
        )


class ClaimSiteClassTest(unittest.TestCase):
    """Representative site per class, checked in-process (no subprocess)."""

    def ctx(self, **kwargs):
        return Ctx(repo=None, tmp_dir=None, **kwargs)

    def check_one(self, report, **kwargs):
        claims = parse_report(report)
        self.assertEqual(len(claims), 1, report)
        return run_claim(claims[0], self.ctx(**kwargs))

    def assert_budget_feedback(self, result, claimed, limit, option):
        self.assertIs(result.cause, Cause.LIMIT)
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn(str(claimed), result.reason)
        self.assertIn(str(limit), result.reason)
        self.assertIn(option, result.reason)

    def test_halt_limit_names_value_limit_and_option(self):
        result = self.check_one("[HALT: 1RB1RZ_0LA0LA -> 6]\n", halt_limit=5)
        self.assert_budget_feedback(result, 6, 5, "--halt-limit")

    def test_search_limit_names_value_limit_and_option(self):
        result = self.check_one("[SEARCHED: 1RB1RZ_0LA0LA -> 6]\n", search_limit=5)
        self.assert_budget_feedback(result, 6, 5, "--search-limit")

    def test_cycle_limit_names_value_limit_and_option(self):
        result = self.check_one("[CYCLE: 1RB1RZ_0LA0LA -> 1,6,2]\n", cycle_limit=5)
        self.assert_budget_feedback(result, 6, 5, "--cycle-limit")

    def test_coloring_limit_names_value_limit_and_option(self):
        result = self.check_one("[COLORING: k=1 ; 111111]\n", coloring_limit=5)
        self.assert_budget_feedback(result, 6, 5, "--coloring-limit")

    def test_artifact_without_root_is_environment_and_names_the_option(self):
        digest = "0" * 64
        result = self.check_one(f"[ARTIFACT: good.txt -> {digest}]\n")
        self.assertIs(result.cause, Cause.ENVIRONMENT)
        self.assertIn("--artifact-root", result.reason)

    def test_artifact_size_limit_is_a_builtin_budget(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "big.bin"), "wb") as handle:
                handle.write(b"12345")
            digest = "0" * 64
            with mock.patch.object(artifact, "MAX_ARTIFACT_BYTES", 4):
                result = self.check_one(
                    f"[ARTIFACT: big.bin -> {digest}]\n", artifact_root=root
                )
            self.assertIs(result.cause, Cause.LIMIT)
            self.assertIn("built-in limit", result.reason)

    def test_malformed_artifact_digest_is_a_defect(self):
        result = self.check_one("[ARTIFACT: good.txt -> nothex]\n")
        self.assertIs(result.cause, Cause.DEFECT)

    def test_malformed_ident_marker_is_a_defect(self):
        result = self.check_one("[IDENT: nonsense]\n")
        self.assertIs(result.cause, Cause.DEFECT)

    def test_unreadable_payload_number_stays_residual(self):
        # "2^^^5" is a prose number, not a defective claim: the report may be
        # honest, the tool just cannot interpret it (P7 doctrine).
        result = self.check_one("[HALT: 1RB1RZ_0LA0LA -> 2^^^5]\n")
        self.assertIs(result.cause, Cause.UNVERIFIABLE)

    def test_embedded_nul_is_a_defect(self):
        claim = Claim("commit_exists", 1, "raw", {"commit": "abc\x00def"})
        result = run_claim(claim, self.ctx())
        self.assertIs(result.cause, Cause.DEFECT)

    def test_checker_crash_stays_residual(self):
        def boom(claim, ctx):
            raise RuntimeError("boom")

        result = run_claim(Claim("boom", 1, "raw", {}), self.ctx(), registry={"boom": boom})
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIs(result.cause, Cause.UNVERIFIABLE)

    def test_unknown_kind_stays_residual(self):
        # A [DEPLOY] status has no checker: residual ignorance, not a defect.
        result = run_claim(Claim("deploy", 1, "raw", {"value": "no"}), self.ctx())
        self.assertEqual(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIs(result.cause, Cause.UNVERIFIABLE)


if __name__ == "__main__":
    unittest.main()

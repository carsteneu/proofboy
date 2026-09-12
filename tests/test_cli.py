import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from bemyself import claimtypes, cli
from bemyself.model import ClaimType, Result, Verdict
from tests.fixtures import make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BWRAP = shutil.which("bwrap")


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "fixture"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def write_report(self, text, name="report.txt"):
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def invoke(self, *args, repo=None, tmp=True, env=None):
        command = [
            sys.executable,
            "-m",
            "bemyself",
            "check",
            "--repo",
            repo or self.repo.path,
        ]
        if tmp:
            command += ["--tmp", os.path.join(self._tmp.name, "tmp")]
        return subprocess.run(
            command + list(args),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )

    def verdicts(self, stdout):
        return {c["kind"]: c["verdict"] for c in json.loads(stdout)["claims"]}

    def test_good_report_is_confirmed(self):
        report = self.write_report(
            "### Phase 6: FINISH\n"
            "**send_to payload:** `[DONE] [DEPLOY: yes] "
            f"[COMMIT: {self.repo['good']}] [BRANCH: main] [MERGE: no] done`\n"
            "**Files in scope:** good.txt, test_ok.py\n"
            "Tests run: python3 -m unittest test_ok -> exit 0\n"
        )
        proc = self.invoke("--report", report, "--json", "--base", self.repo["base"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["commit_exists"], "CONFIRMED")
        self.assertEqual(verdicts["branch_pushed"], "CONFIRMED")
        self.assertEqual(verdicts["diff_scope"], "CONFIRMED")
        self.assertEqual(verdicts["tests_green"], "CONFIRMED")
        self.assertEqual(verdicts["merge"], "UNVERIFIABLE")
        self.assertEqual(verdicts["deploy"], "UNVERIFIABLE")

    def test_nonexistent_commit_is_refuted(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {'0' * 40}] [BRANCH: main]`\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 1)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["commit_exists"], "REFUTED")
        self.assertEqual(verdicts["branch_pushed"], "UNVERIFIABLE")

    def test_wrong_diff_scope_and_failing_test_are_refuted(self):
        report = self.write_report(
            "**send_to payload:** `[DONE] "
            f"[COMMIT: {self.repo['bad']}] [BRANCH: main] [MERGE: no]`\n"
            "**Files in scope:** good.txt\n"
            "Tests run: python3 -m unittest test_bad -> exit 0\n"
        )
        proc = self.invoke("--report", report, "--json", "--base", self.repo["base"])
        self.assertEqual(proc.returncode, 1)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["commit_exists"], "CONFIRMED")
        self.assertEqual(verdicts["diff_scope"], "REFUTED")
        self.assertEqual(verdicts["tests_green"], "REFUTED")

    def test_files_option_adds_diff_scope_claim(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: main]`\n"
        )
        proc = self.invoke("--report", report, "--files", "good.txt", "--base", self.repo["base"], "--json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["diff_scope"], "REFUTED")

    def test_nothing_verified_is_not_success(self):
        report = self.write_report("**send_to payload:** `[MERGE: no]`\n")
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 3, proc.stdout)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["merge"], "UNVERIFIABLE")

    def test_strict_fails_when_any_claim_stays_unverifiable(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            'Tests run: python3 -c "import sys; sys.exit(3)" -> exit 0\n'
        )
        default = self.invoke("--report", report, "--json")
        self.assertEqual(default.returncode, 0, default.stderr)
        strict = self.invoke("--report", report, "--json", "--strict")
        self.assertEqual(strict.returncode, 4, strict.stderr)

    def test_strict_zero_claim_report_is_not_success(self):
        report = self.write_report(
            "Phase 6 report: everything went fine, all tests green, nothing to report.\n"
        )
        proc = self.invoke("--report", report, "--strict")
        self.assertEqual(proc.returncode, 3, proc.stdout)

    def test_strict_fully_confirmed_report_is_exit_zero(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: main]`\n"
            "**Files in scope:** good.txt, test_ok.py\n"
            "Tests run: python3 -m unittest test_ok -> exit 0\n"
        )
        proc = self.invoke(
            "--report", report, "--json", "--base", self.repo["base"], "--strict"
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["commit_exists"], "CONFIRMED")
        self.assertEqual(verdicts["branch_pushed"], "CONFIRMED")
        self.assertEqual(verdicts["diff_scope"], "CONFIRMED")
        self.assertEqual(verdicts["tests_green"], "CONFIRMED")

    def test_strict_keeps_refuted_reports_at_exit_one(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n"
        )
        proc = self.invoke("--report", report, "--strict")
        self.assertEqual(proc.returncode, 1)

    def test_strict_all_unverifiable_report_stays_exit_three(self):
        report = self.write_report("**send_to payload:** `[MERGE: no]`\n")
        proc = self.invoke("--report", report, "--strict")
        self.assertEqual(proc.returncode, 3)

    def test_diff_scope_without_base_is_unverifiable(self):
        report = self.write_report(
            "**send_to payload:** `[COMMIT: %s]`\n"
            "**Files in scope:** good.txt, test_ok.py\n" % self.repo["good"]
        )
        proc = self.invoke("--report", report, "--json")
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["diff_scope"], "UNVERIFIABLE")

    def test_human_output_marks_refutation(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n"
        )
        proc = self.invoke("--report", report)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("REFUTED", proc.stdout)

    def test_missing_report_is_an_error(self):
        proc = self.invoke("--report", os.path.join(self._tmp.name, "nope.txt"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("report", proc.stderr.lower())

    def test_missing_repo_is_an_error(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
        )
        proc = self.invoke("--report", report, repo=os.path.join(self._tmp.name, "no-such-repo"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("repo", proc.stderr.lower())

    def test_repo_subdirectory_is_resolved(self):
        sub = os.path.join(self.repo.path, "sub")
        os.makedirs(sub, exist_ok=True)
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            "Tests run: python3 -m unittest test_ok -> exit 0\n"
        )
        proc = self.invoke("--report", report, "--json", repo=sub)
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["tests_green"], "CONFIRMED", proc.stdout + proc.stderr)

    def test_oversized_report_is_an_error(self):
        report = self.write_report("x" * ((1 << 20) + 1))
        proc = self.invoke("--report", report)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("1 MiB", proc.stderr)

    def test_control_characters_are_sanitized_in_text_output(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            "Tests run: python3 -m unittest \x1b[2K\u202e\x9b\u200b\ufeff\u061cfake -> exit 0\n"
        )
        proc = self.invoke("--report", report)
        self.assertNotIn("\x1b", proc.stdout)
        for char in ("\u202e", "\x9b", "\u200b", "\ufeff", "\u061c"):
            self.assertNotIn(char, proc.stdout)

    def test_json_output_escapes_non_ascii_control_characters(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            "Tests run: python3 -m unittest \u202efake -> exit 0\n"
        )
        proc = self.invoke("--report", report, "--json")
        self.assertNotIn("\u202e", proc.stdout)

    def test_files_option_with_multiple_commits_stays_unverifiable(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}] [BRANCH: main]`\n"
            f"**send_to payload:** `[COMMIT: {self.repo['bad']}]`\n"
        )
        proc = self.invoke(
            "--report", report, "--files", "good.txt,test_ok.py", "--base", self.repo["base"], "--json"
        )
        verdicts = self.verdicts(proc.stdout)
        self.assertEqual(verdicts["diff_scope"], "UNVERIFIABLE")

    def test_committed_yesmem_symlink_is_refused_for_default_tmp(self):
        outside = os.path.join(self._tmp.name, "outside")
        os.makedirs(outside, exist_ok=True)
        os.symlink(outside, os.path.join(self.repo.path, ".yesmem"))
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
        )
        proc = self.invoke("--report", report, tmp=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("tmp", proc.stderr.lower())
        self.assertEqual(os.listdir(outside), [], "scratch files were written outside the repo")

    def test_committed_yesmem_symlink_with_json_reports_an_error(self):
        link = os.path.join(self.repo.path, ".yesmem")
        if not os.path.lexists(link):
            outside = os.path.join(self._tmp.name, "outside-json")
            os.makedirs(outside, exist_ok=True)
            os.symlink(outside, link)
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
        )
        proc = self.invoke("--report", report, "--json", tmp=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("tmp", proc.stderr.lower())
        self.assertIn("tmp", json.loads(proc.stdout)["error"].lower())

    # --- --sandbox ---------------------------------------------------------
    def env_without_bwrap(self):
        """A PATH that has git but no bwrap, like a host without bubblewrap."""
        shim = os.path.join(self._tmp.name, "bin-nobwrap")
        os.makedirs(shim, exist_ok=True)
        link = os.path.join(shim, "git")
        if not os.path.lexists(link):
            os.symlink(shutil.which("git"), link)
        return {**os.environ, "PATH": shim}

    def sandbox_report(self):
        return self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            "Tests run: python3 -m unittest test_ok -> exit 0\n"
        )

    def test_require_without_bwrap_leaves_the_test_claim_unverifiable(self):
        proc = self.invoke(
            "--report",
            self.sandbox_report(),
            "--json",
            "--strict",
            "--sandbox=require",
            env=self.env_without_bwrap(),
        )
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["commit_exists"]["verdict"], "CONFIRMED")
        self.assertEqual(claims["tests_green"]["verdict"], "UNVERIFIABLE")
        self.assertIn("bwrap is not available", claims["tests_green"]["reason"])
        self.assertIn("refusing to run the command unsandboxed", claims["tests_green"]["reason"])

    def test_require_without_bwrap_never_confirms_the_test_claim(self):
        proc = self.invoke(
            "--report",
            self.sandbox_report(),
            "--json",
            "--sandbox=require",
            env=self.env_without_bwrap(),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["tests_green"]["verdict"], "UNVERIFIABLE")

    def test_sandbox_off_runs_unsandboxed_and_names_it(self):
        proc = self.invoke("--report", self.sandbox_report(), "--json", "--sandbox=off")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        tests = [c for c in json.loads(proc.stdout)["claims"] if c["kind"] == "tests_green"]
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0]["verdict"], "CONFIRMED")
        self.assertIn("not sandboxed: --sandbox=off", tests[0]["reason"])
        self.assertNotIn("bwrap", tests[0]["command"])
        self.assertIs(tests[0]["sandboxed"], False)

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_default_auto_sandboxes_when_bwrap_is_available(self):
        proc = self.invoke("--report", self.sandbox_report(), "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        tests = [c for c in json.loads(proc.stdout)["claims"] if c["kind"] == "tests_green"]
        self.assertEqual(tests[0]["verdict"], "CONFIRMED")
        self.assertIn("sandboxed with bwrap", tests[0]["reason"])
        self.assertIn("bwrap", tests[0]["command"])
        self.assertIs(tests[0]["sandboxed"], True)

    def test_unknown_sandbox_mode_is_a_usage_error(self):
        proc = self.invoke("--report", self.sandbox_report(), "--sandbox=banana")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--sandbox", proc.stderr)

    # --- --halt-limit ------------------------------------------------------
    def halt_report(self, steps=3):
        # 1RB1RZ_0LA0LA halts after three steps (see tests/test_turing.py).
        return self.write_report(
            "### Phase 6: FINISH\n"
            "**Status:** COMPLETE\n"
            "**send_to payload:** `[DONE] "
            f"[HALT: 1RB1RZ_0LA0LA -> {steps}]`\n",
            name="halt-report.txt",
        )

    def test_halt_claim_confirms_end_to_end(self):
        proc = self.invoke("--report", self.halt_report(), "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["halt"]["verdict"], "CONFIRMED")
        self.assertIn("simulate 1RB1RZ_0LA0LA", claims["halt"]["command"])

    def test_halt_limit_leaves_larger_claims_unverifiable(self):
        proc = self.invoke("--report", self.halt_report(), "--json", "--halt-limit", "2")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["halt"]["verdict"], "UNVERIFIABLE")
        self.assertIn("executable limit of 2", claims["halt"]["reason"])

    def test_halt_limit_at_the_claim_still_runs(self):
        proc = self.invoke("--report", self.halt_report(), "--json", "--halt-limit", "3")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["halt"]["verdict"], "CONFIRMED")

    def test_negative_halt_limit_is_a_usage_error(self):
        proc = self.invoke("--report", self.halt_report(), "--halt-limit=-1")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--halt-limit", proc.stderr)

    def test_non_integer_halt_limit_is_a_usage_error(self):
        proc = self.invoke("--report", self.halt_report(), "--halt-limit=banana")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--halt-limit", proc.stderr)

    # --- --search-limit ----------------------------------------------------
    def searched_report(self, steps=1000):
        # 1RA1RA never halts: it writes 1 and walks right forever.
        return self.write_report(
            "### Phase 6: FINISH\n"
            "**Status:** COMPLETE\n"
            "**send_to payload:** `[DONE] "
            f"[SEARCHED: 1RA1RA -> {steps}]`\n",
            name="searched-report.txt",
        )

    def test_searched_claim_confirms_end_to_end(self):
        proc = self.invoke("--report", self.searched_report(), "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["searched"]["verdict"], "CONFIRMED")
        self.assertIn("bounded search", claims["searched"]["reason"])
        self.assertIn("does not prove that the machine never halts", claims["searched"]["reason"])

    def test_search_limit_leaves_larger_claims_unverifiable(self):
        proc = self.invoke(
            "--report", self.searched_report(), "--json", "--search-limit", "100"
        )
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["searched"]["verdict"], "UNVERIFIABLE")
        self.assertIn("executable limit of 100", claims["searched"]["reason"])

    def test_search_limit_at_the_claim_still_runs(self):
        proc = self.invoke(
            "--report", self.searched_report(), "--json", "--search-limit", "1000"
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["searched"]["verdict"], "CONFIRMED")

    def test_negative_search_limit_is_a_usage_error(self):
        proc = self.invoke("--report", self.searched_report(), "--search-limit=-1")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--search-limit", proc.stderr)

    def test_non_integer_search_limit_is_a_usage_error(self):
        proc = self.invoke("--report", self.searched_report(), "--search-limit=banana")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--search-limit", proc.stderr)

    # --- [CYCLE] -----------------------------------------------------------
    def cycle_report(self, t2=16):
        # The translated cycler of the bbchallenge wiki (the certificate is
        # re-derived in tests/test_cycle.py): step 16 is step 6 shifted by 2.
        machine = "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC"
        return self.write_report(
            "### Phase 6: FINISH\n"
            "**Status:** COMPLETE\n"
            "**send_to payload:** `[DONE] "
            f"[CYCLE: {machine} -> 6,{t2},2]`\n",
            name="cycle-report.txt",
        )

    def test_cycle_claim_confirms_end_to_end(self):
        proc = self.invoke("--report", self.cycle_report(), "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["cycle"]["verdict"], "CONFIRMED")
        self.assertIn("never halts", claims["cycle"]["reason"])
        self.assertIn("translated by 2", claims["cycle"]["reason"])

    def test_cycle_limit_leaves_larger_claims_unverifiable(self):
        proc = self.invoke(
            "--report", self.cycle_report(), "--json", "--cycle-limit", "15"
        )
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["cycle"]["verdict"], "UNVERIFIABLE")
        self.assertIn("executable limit of 15", claims["cycle"]["reason"])

    def test_cycle_limit_at_the_claim_still_runs(self):
        proc = self.invoke(
            "--report", self.cycle_report(), "--json", "--cycle-limit", "16"
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["cycle"]["verdict"], "CONFIRMED")

    def test_negative_cycle_limit_is_a_usage_error(self):
        proc = self.invoke("--report", self.cycle_report(), "--cycle-limit=-1")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--cycle-limit", proc.stderr)

    def test_non_integer_cycle_limit_is_a_usage_error(self):
        proc = self.invoke("--report", self.cycle_report(), "--cycle-limit=banana")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--cycle-limit", proc.stderr)

    # --- [COMPUTE] ---------------------------------------------------------
    def compute_report(self, digest_text, command='python3 -c "print(42)"'):
        return self.write_report(
            "### Phase 6: FINISH\n"
            "**Status:** COMPLETE\n"
            f"**send_to payload:** `[DONE] [COMMIT: {self.repo['good']}]`\n"
            f"[COMPUTE: {command} -> {digest_text}]\n",
            name="compute-report.txt",
        )

    def test_compute_claim_confirms_end_to_end_with_allow(self):
        correct = hashlib.sha256(b"42\n").hexdigest()
        proc = self.invoke(
            "--report", self.compute_report(correct), "--json", "--allow", "python3 -c"
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["compute"]["verdict"], "CONFIRMED")

    def test_compute_command_outside_the_allowlist_stays_unverifiable(self):
        correct = hashlib.sha256(b"42\n").hexdigest()
        proc = self.invoke("--report", self.compute_report(correct), "--json")
        # The commit claim still confirms (exit 0); the compute claim must not.
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["compute"]["verdict"], "UNVERIFIABLE")
        self.assertIn("compute allowlist", claims["compute"]["reason"])

    def test_compute_wrong_digest_is_refuted(self):
        proc = self.invoke(
            "--report", self.compute_report("a" * 64), "--json", "--allow", "python3 -c"
        )
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["compute"]["verdict"], "REFUTED")

    def test_compute_only_report_without_repo_is_a_usage_error(self):
        report = self.write_report(
            f"[COMPUTE: python3 -c \"print(42)\" -> {'a' * 64}]\n", name="compute-only.txt"
        )
        proc = self.invoke_without_repo("--report", report)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repo is required", proc.stderr)
        self.assertIn("compute", proc.stderr)

    # --- --repo: required only for claim kinds that need it ----------------
    def invoke_without_repo(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "bemyself", "check"] + list(args),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_halt_only_report_without_repo_confirms(self):
        proc = self.invoke_without_repo("--report", self.halt_report(), "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["halt"]["verdict"], "CONFIRMED")

    def test_searched_only_report_without_repo_confirms(self):
        proc = self.invoke_without_repo("--report", self.searched_report(), "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["searched"]["verdict"], "CONFIRMED")

    def test_commit_claim_without_repo_is_a_usage_error(self):
        report = self.write_report(
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n", name="commit-only.txt"
        )
        proc = self.invoke_without_repo("--report", report)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repo is required", proc.stderr)
        self.assertIn("commit_exists", proc.stderr)
        self.assertIn("usage", proc.stderr.lower())

    def test_mixed_report_without_repo_is_a_usage_error(self):
        report = self.write_report(
            f"**send_to payload:** `[DONE] [COMMIT: {self.repo['good']}] "
            "[HALT: 1RB1RZ_0LA0LA -> 3]`\n",
            name="mixed.txt",
        )
        proc = self.invoke_without_repo("--report", report)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repo is required", proc.stderr)

    def test_report_without_claims_needs_no_repo(self):
        report = self.write_report("Everything went fine, nothing to verify.\n", name="empty.txt")
        proc = self.invoke_without_repo("--report", report, "--json")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["claims"], [])
        self.assertNotIn("--repo is required", proc.stderr)

    def test_kind_without_checker_needs_no_repo(self):
        report = self.write_report("**send_to payload:** `[MERGE: no]`\n", name="merge-only.txt")
        proc = self.invoke_without_repo("--report", report, "--json")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["merge"]["verdict"], "UNVERIFIABLE")

    def test_artifact_only_report_without_repo_uses_the_configured_root(self):
        root = os.path.join(self._tmp.name, "artifact-root")
        os.makedirs(root, exist_ok=True)
        payload = b"artifact\n"
        with open(os.path.join(root, "app.bin"), "wb") as handle:
            handle.write(payload)
        digest = hashlib.sha256(payload).hexdigest()
        report = self.write_report(f"[ARTIFACT: app.bin -> {digest}]\n", name="artifact-only.txt")
        proc = self.invoke_without_repo("--report", report, "--artifact-root", root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["artifact"]["verdict"], "CONFIRMED")

    def test_artifact_without_any_root_stays_unverifiable(self):
        report = self.write_report(
            f"[ARTIFACT: app.bin -> {'a' * 64}]\n", name="artifact-noroot.txt"
        )
        proc = self.invoke_without_repo("--report", report, "--json")
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertNotIn("--repo is required", proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["artifact"]["verdict"], "UNVERIFIABLE")

    def test_artifact_root_overrides_the_repo(self):
        root = os.path.join(self._tmp.name, "override-root")
        os.makedirs(root, exist_ok=True)
        payload = b"override\n"
        with open(os.path.join(root, "app.bin"), "wb") as handle:
            handle.write(payload)
        digest = hashlib.sha256(payload).hexdigest()
        report = self.write_report(
            f"[ARTIFACT: app.bin -> {digest}]\n", name="artifact-override.txt"
        )
        proc = self.invoke("--report", report, "--artifact-root", root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        claims = {c["kind"]: c for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(claims["artifact"]["verdict"], "CONFIRMED")

    def test_files_override_needs_the_repo_of_its_diff_scope_claim(self):
        proc = self.invoke_without_repo("--report", self.halt_report(), "--files", "a.txt")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repo is required", proc.stderr)
        self.assertIn("diff_scope", proc.stderr)


class CliSectionTest(unittest.TestCase):
    """``check --section`` reads the message from a scratchpad database.

    Every test passes ``--db``; the live YesMem database is never touched.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "fixture"))
        cls.db = os.path.join(cls._tmp.name, "scratchpad.db")
        con = sqlite3.connect(cls.db)
        con.executescript(
            """
            CREATE TABLE scratchpad_entries (
                project TEXT NOT NULL,
                section TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                UNIQUE(project, section)
            );
            """
        )
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def add_section(self, section, content):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT OR REPLACE INTO scratchpad_entries (project, section, content) VALUES (?, ?, ?)",
            (self.repo.path, section, content),
        )
        con.commit()
        con.close()

    def invoke(self, section, *extra, project=None, db=None, tmp=True):
        command = [
            sys.executable,
            "-m",
            "bemyself",
            "check",
            "--section",
            section,
            "--project",
            project or self.repo.path,
            "--db",
            db or self.db,
        ]
        if tmp:
            command += ["--tmp", os.path.join(self._tmp.name, "tmp")]
        return subprocess.run(
            command + list(extra),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def invoke_raw(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "bemyself", "check"] + list(args),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def verdicts(self, stdout):
        return {c["kind"]: c["verdict"] for c in json.loads(stdout)["claims"]}

    def test_section_message_is_verified(self):
        self.add_section("report", f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n")
        proc = self.invoke("report", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(self.verdicts(proc.stdout)["commit_exists"], "CONFIRMED")

    def test_strict_section_with_unverifiable_claim_fails(self):
        self.add_section(
            "mixed",
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n"
            'Tests run: python3 -c "import sys; sys.exit(3)" -> exit 0\n',
        )
        proc = self.invoke("mixed", "--strict")
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)

    def test_json_names_the_scratchpad_source(self):
        self.add_section("merge-only", "[MERGE: no]\n")
        proc = self.invoke("merge-only", "--json")
        self.assertEqual(proc.returncode, 3)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["report"], f"scratchpad:merge-only@{self.repo.path}")

    def test_unknown_section_is_an_error(self):
        proc = self.invoke("missing", "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing", proc.stderr)
        self.assertIn("missing", json.loads(proc.stdout)["error"])

    def test_empty_section_is_nothing_to_verify(self):
        self.add_section("empty", "")
        proc = self.invoke("empty", "--json")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(proc.stdout)["claims"], [])

    def test_unreadable_database_is_an_error(self):
        proc = self.invoke("report", db=os.path.join(self._tmp.name, "no-such.db"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("database", proc.stderr.lower())

    def test_oversized_section_is_an_error(self):
        self.add_section("huge", "x" * ((1 << 20) + 1))
        proc = self.invoke("huge")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("1 MiB", proc.stderr)

    def test_section_and_report_are_mutually_exclusive(self):
        proc = self.invoke_raw(
            "--section",
            "report",
            "--project",
            self.repo.path,
            "--db",
            self.db,
            "--report",
            os.path.join(self._tmp.name, "report.txt"),
            "--repo",
            self.repo.path,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--section", proc.stderr)

    def test_one_of_report_and_section_is_required(self):
        proc = self.invoke_raw("--repo", self.repo.path)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--report", proc.stderr)

    def test_section_requires_project(self):
        proc = self.invoke_raw("--section", "report", "--db", self.db)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--project", proc.stderr)

    def test_section_mode_runs_repo_free_claims_without_repo(self):
        self.add_section("halt-only", "**send_to payload:** `[DONE] [HALT: 1RB1RZ_0LA0LA -> 3]`\n")
        proc = self.invoke("halt-only", "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.verdicts(proc.stdout)["halt"], "CONFIRMED")

    def test_report_with_a_repo_needing_claim_still_requires_repo(self):
        path = os.path.join(self._tmp.name, "commit-report.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n")
        proc = self.invoke_raw("--report", path)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repo", proc.stderr)


class RepoNeedRegistryTest(unittest.TestCase):
    """The ``--repo`` requirement must come from the claim-type registry.

    The CLI has no kind list: only a type's ``needs_repo`` declaration makes
    its claims demand a repository, and a report from repo-free types runs
    without one.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write_report(self, text):
        path = os.path.join(self._tmp.name, "report.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def dummy_type(self, needs_repo):
        def check(claim, ctx):
            return Result(Verdict.CONFIRMED, reason="the dummy claim holds")

        def parse(match, raw):
            return {"value": match.group(1)}

        return ClaimType(
            kind="dummy",
            pattern=re.compile(r"\[DUMMY:[ \t]*(\w+)[ \t]*\]"),
            parse=parse,
            check=check,
            needs_repo=needs_repo,
        )

    def test_a_type_declaring_a_repo_need_is_required_without_repo(self):
        report = self.write_report("[DUMMY: x]\n")
        stderr = io.StringIO()
        with mock.patch.object(claimtypes, "CLAIM_TYPES", (self.dummy_type(True),)):
            with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                cli.main(["check", "--report", report])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("--repo is required", stderr.getvalue())
        self.assertIn("dummy", stderr.getvalue())

    def test_a_type_without_repo_need_runs_without_repo(self):
        report = self.write_report("[DUMMY: x]\n")
        stdout = io.StringIO()
        with mock.patch.object(claimtypes, "CLAIM_TYPES", (self.dummy_type(False),)):
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["check", "--report", report, "--json"])
        self.assertEqual(code, 0)
        claims = json.loads(stdout.getvalue())["claims"]
        self.assertEqual(claims[0]["verdict"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.fixtures import make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


if __name__ == "__main__":
    unittest.main()

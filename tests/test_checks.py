import os
import subprocess
import tempfile
import unittest

from bemyself.checks import Ctx, run_claim
from bemyself.model import Claim, Verdict

from tests.fixtures import make_repo


def make_claim(kind, **fields):
    return Claim(kind, 1, "<fixture>", fields)


class CheckerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "withremote"))
        cls.noremote = make_repo(os.path.join(cls._tmp.name, "noremote"), with_remote=False)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def ctx(self, repo=None, **kw):
        work = os.path.join(self._tmp.name, "work", self._testMethodName)
        os.makedirs(work, exist_ok=True)
        kw.setdefault("tmp_dir", work)
        return Ctx(repo=repo or self.repo.path, **kw)

    def run_check(self, kind, ctx=None, **fields):
        return run_claim(make_claim(kind, **fields), ctx or self.ctx())

    # --- commit_exists -----------------------------------------------------
    def test_commit_exists_confirmed(self):
        result = self.run_check("commit_exists", commit=self.repo["good"])
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("rev-parse", result.command)

    def test_commit_exists_refuted(self):
        result = self.run_check("commit_exists", commit="0" * 40)
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_commit_exists_non_hash_is_unverifiable(self):
        result = self.run_check("commit_exists", commit="HEAD")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_commit_exists_resolves_short_hash(self):
        result = self.run_check("commit_exists", commit=self.repo["good"][:8])
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(result.output.strip(), self.repo["good"])

    def test_commit_exists_outside_git_repo_unverifiable(self):
        empty = os.path.join(self._tmp.name, "not-a-repo")
        os.makedirs(empty, exist_ok=True)
        result = self.run_check("commit_exists", ctx=self.ctx(repo=empty), commit=self.repo["good"])
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    # --- branch_pushed -----------------------------------------------------
    def test_branch_pushed_without_remote_unverifiable(self):
        result = self.run_check(
            "branch_pushed",
            ctx=self.ctx(repo=self.noremote.path),
            branch="main",
            commit=self.noremote["good"],
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_branch_pushed_confirmed_for_tip(self):
        result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_branch_pushed_confirmed_for_ancestor(self):
        result = self.run_check("branch_pushed", branch="main", commit=self.repo["good"])
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_branch_pushed_refuted_for_unpushed_commit(self):
        result = self.run_check("branch_pushed", branch="main", commit=self.repo["unpushed"])
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_branch_pushed_without_hash_unverifiable(self):
        result = self.run_check("branch_pushed", branch="main", commit=None)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_branch_pushed_not_confirmed_when_remote_branch_is_gone(self):
        repo = make_repo(os.path.join(self._tmp.name, "gone"))
        subprocess.run(
            ["git", "--git-dir", repo.remote, "update-ref", "-d", "refs/heads/main"],
            check=True,
            capture_output=True,
        )
        result = run_claim(
            make_claim("branch_pushed", branch="main", commit=repo["bad"]),
            self.ctx(repo=repo.path),
        )
        self.assertIsNot(result.verdict, Verdict.CONFIRMED)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    # --- diff_scope --------------------------------------------------------
    def test_diff_scope_confirmed(self):
        result = self.run_check(
            "diff_scope",
            ctx=self.ctx(base=self.repo["base"]),
            head=self.repo["good"],
            planned=("good.txt", "test_ok.py"),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_diff_scope_refuted_on_extra_file(self):
        result = self.run_check(
            "diff_scope",
            ctx=self.ctx(base=self.repo["base"]),
            head=self.repo["good"],
            planned=("good.txt",),
        )
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("test_ok.py", result.reason)

    def test_diff_scope_without_base_is_unverifiable(self):
        result = self.run_check(
            "diff_scope", head=self.repo["good"], planned=("good.txt", "test_ok.py")
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_diff_scope_refuted_on_planned_but_unchanged(self):
        result = self.run_check(
            "diff_scope",
            ctx=self.ctx(base=self.repo["base"]),
            head=self.repo["good"],
            planned=("good.txt", "test_ok.py", "never_touched.txt"),
        )
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("never_touched.txt", result.reason)

    def test_diff_scope_refuted_on_empty_diff(self):
        result = self.run_check(
            "diff_scope",
            ctx=self.ctx(base=self.repo["base"]),
            head=self.repo["base"],
            planned=("good.txt",),
        )
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_diff_scope_explicit_base(self):
        result = self.run_check(
            "diff_scope",
            ctx=self.ctx(base=self.repo["base"]),
            head=self.repo["bad"],
            planned=("good.txt", "test_ok.py", "test_bad.py"),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    # --- tests_green / tests_exit ------------------------------------------
    def test_tests_green_confirmed(self):
        result = self.run_check(
            "tests_green",
            command="python3 -m unittest test_ok",
            claimed_exit=0,
            commit=self.repo["good"],
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn("unittest", result.command)

    def test_tests_green_refuted_when_claimed_green_but_failing(self):
        result = self.run_check(
            "tests_green",
            command="python3 -m unittest test_bad",
            claimed_exit=0,
            commit=self.repo["bad"],
        )
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertTrue(result.output)

    def test_tests_green_unverifiable_when_command_runs_no_tests(self):
        result = self.run_check(
            "tests_green",
            command="python3 -m unittest --help",
            claimed_exit=0,
            commit=self.repo["good"],
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_exit_confirmed_for_matching_failure(self):
        result = self.run_check(
            "tests_exit",
            command="python3 -m unittest test_bad",
            claimed_exit=1,
            commit=self.repo["bad"],
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_tests_exit_refuted_for_wrong_code(self):
        result = self.run_check(
            "tests_exit",
            command="python3 -m unittest test_bad",
            claimed_exit=0,
            commit=self.repo["bad"],
        )
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_tests_green_unverifiable_when_command_not_allowlisted(self):
        result = self.run_check(
            "tests_green",
            command="curl http://example.invalid",
            claimed_exit=0,
            commit=self.repo["good"],
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_without_commit(self):
        result = self.run_check(
            "tests_green",
            command="python3 -m unittest test_ok",
            claimed_exit=0,
            commit=None,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_tmp_dir_unusable(self):
        blocker = os.path.join(self._tmp.name, "blocker-file")
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("x")
        ctx = Ctx(repo=self.repo.path, tmp_dir=blocker)
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unittest test_ok",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    # --- registry ----------------------------------------------------------
    def test_unknown_claim_kind_is_unverifiable(self):
        result = self.run_check("merge", value="no")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)


if __name__ == "__main__":
    unittest.main()

import os
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
        self.assertIn("cat-file", result.command)

    def test_commit_exists_refuted(self):
        result = self.run_check("commit_exists", commit="0" * 40)
        self.assertIs(result.verdict, Verdict.REFUTED)

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

    # --- diff_scope --------------------------------------------------------
    def test_diff_scope_confirmed(self):
        result = self.run_check(
            "diff_scope", head=self.repo["good"], planned=("good.txt", "test_ok.py")
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_diff_scope_refuted_on_extra_file(self):
        result = self.run_check("diff_scope", head=self.repo["good"], planned=("good.txt",))
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("test_ok.py", result.reason)

    def test_diff_scope_explicit_base(self):
        result = self.run_check(
            "diff_scope",
            head=self.repo["bad"],
            planned=("good.txt", "test_ok.py", "test_bad.py"),
            base=self.repo["base"],
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    # --- tests_green -------------------------------------------------------
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

    # --- registry ----------------------------------------------------------
    def test_unknown_claim_kind_is_unverifiable(self):
        result = self.run_check("merge", value="no")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)


if __name__ == "__main__":
    unittest.main()

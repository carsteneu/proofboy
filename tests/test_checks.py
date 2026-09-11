import os
import subprocess
import tempfile
import unittest
from unittest import mock

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
        # A temp dir inside a git checkout would let git discovery walk up and
        # find that repo; the ceiling keeps the fixture hermetic.
        previous = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = self._tmp.name
        try:
            result = self.run_check("commit_exists", ctx=self.ctx(repo=empty), commit=self.repo["good"])
        finally:
            if previous is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = previous
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

    # --- hostile report fields (review round 2) ----------------------------
    def test_branch_pushed_rejects_option_injection(self):
        script = os.path.join(self._tmp.name, "upload.sh")
        marker = os.path.join(self._tmp.name, "upload-marker")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\ntouch %s\n" % marker)
        os.chmod(script, 0o755)
        result = self.run_check(
            "branch_pushed",
            branch=f"--upload-pack={script}",
            commit=self.repo["good"],
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertFalse(os.path.exists(marker), "git executed the report-supplied upload-pack")

    def test_branch_pushed_rejects_refspec_injection(self):
        result = self.run_check(
            "branch_pushed",
            branch="main:refs/heads/pwned-by-report",
            commit=self.repo["bad"],
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        proc = subprocess.run(
            [
                "git",
                "-C",
                self.repo.path,
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/pwned-by-report",
            ],
            capture_output=True,
        )
        self.assertNotEqual(proc.returncode, 0, "the report created a local branch via refspec injection")

    def test_branch_pushed_refuted_after_remote_rewind_with_narrow_refspec(self):
        repo = make_repo(os.path.join(self._tmp.name, "rewound"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        # Remote feature branch exists at "bad"; the local tracking ref says
        # "bad" while the configured refspec no longer updates it. The remote
        # is then force-rewound to "base". A stale tracking ref would confirm
        # the claim; the freshly fetched FETCH_HEAD must not.
        git("push", "-q", "origin", f"{repo['bad']}:refs/heads/feature")
        git("update-ref", "refs/remotes/origin/feature", repo["bad"])
        git("config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")
        git("push", "-q", "--force", "origin", f"{repo['base']}:refs/heads/feature")
        result = run_claim(
            make_claim("branch_pushed", branch="feature", commit=repo["good"]),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_tests_green_unverifiable_when_discovery_points_outside_checkout(self):
        ctx = self.ctx()
        outside = os.path.join(ctx.tmp_dir, "outside")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "test_planted.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "import unittest\n\n\n"
                "class Planted(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n"
            )
        result = run_claim(
            make_claim(
                "tests_green",
                command=f"python3 -m unittest discover -s {outside}",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_command_uses_parent_path(self):
        ctx = self.ctx()
        outside = os.path.join(ctx.tmp_dir, "parent-outside")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "test_planted.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "import unittest\n\n\n"
                "class Planted(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n"
            )
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unittest discover -s ../parent-outside",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_output_reports_no_tests(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        for script in ("print('0 tests')", "print('Ran 0 tests in 0.01s')"):
            result = run_claim(
                make_claim(
                    "tests_green",
                    command=f'python3 -c "{script}"',
                    claimed_exit=0,
                    commit=self.repo["good"],
                ),
                ctx,
            )
            self.assertIs(result.verdict, Verdict.UNVERIFIABLE, script)

    @mock.patch("bemyself.checks.MAX_LOG_BYTES", 4096)
    def test_tests_green_unverifiable_when_output_exceeds_log_cap(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"import sys; sys.stdout.write('x' * 1000000)\"",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    @mock.patch("bemyself.checks.TEST_TIMEOUT", 1)
    def test_tests_green_timeout_leaves_no_files_behind(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"import time; time.sleep(30)\"",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertEqual(os.listdir(ctx.tmp_dir), [], "throwaway files were left behind")

    def test_tests_green_cannot_read_verifier_environment(self):
        os.environ["VERIFIER_SECRET"] = "supersecret-token"
        try:
            ctx = self.ctx(allowlist=("python3 -c",))
            result = run_claim(
                make_claim(
                    "tests_green",
                    command="python3 -c \"import os; print(os.environ.get('VERIFIER_SECRET', 'ABSENT'))\"",
                    claimed_exit=0,
                    commit=self.repo["good"],
                ),
                ctx,
            )
        finally:
            os.environ.pop("VERIFIER_SECRET", None)
        self.assertIn("ABSENT", result.output)
        self.assertNotIn("supersecret", result.output)

    def test_embedded_nul_is_unverifiable(self):
        result = self.run_check(
            "tests_green",
            command="python3 -m unittest ma\x00in",
            claimed_exit=0,
            commit=self.repo["good"],
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_checker_crash_becomes_unverifiable(self):
        def boom(claim, ctx):
            raise RuntimeError("exploded")

        result = run_claim(make_claim("boom"), self.ctx(), registry={"boom": boom})
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("exploded", result.reason)

    def test_unittest_summary_ignores_zero_tests(self):
        from bemyself.checks import _UNITTEST_SUMMARY_RE

        self.assertIsNone(_UNITTEST_SUMMARY_RE.search("Ran 0 tests in 0.1s"))
        self.assertIsNotNone(_UNITTEST_SUMMARY_RE.search("Ran 1 test in 0.0s"))
        self.assertIsNotNone(_UNITTEST_SUMMARY_RE.search("Ran 47 tests in 1.2s"))

    # --- round 3: runner evidence, shadowing, refs, environment -----------
    def test_branch_pushed_unverifiable_for_tag_name(self):
        repo = make_repo(os.path.join(self._tmp.name, "tagged"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        git("tag", "v1", repo["bad"])
        git("push", "-q", "origin", "v1")
        result = run_claim(
            make_claim("branch_pushed", branch="v1", commit=repo["bad"]),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_branch_pushed_leaves_no_private_ref(self):
        result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        proc = subprocess.run(
            [
                "git",
                "-C",
                self.repo.path,
                "for-each-ref",
                "--format=%(refname)",
                "refs/bemyself-verify/",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.stdout.strip(), "")

    def test_tests_green_unverifiable_when_runner_module_is_shadowed(self):
        repo = make_repo(os.path.join(self._tmp.name, "shadow"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "unittest.py"), "w", encoding="utf-8") as handle:
            handle.write("print('Ran 1 test in 0.001s')\nprint('OK')\n")
        git("add", "-A")
        git("commit", "-q", "-m", "shadow runner")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim(
                "tests_green", command="python3 -m unittest", claimed_exit=0, commit=head
            ),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_output_shows_no_test_evidence(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"print('build ok')\"",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_confirmed_when_positive_evidence_and_unrelated_phrase(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command=(
                    "python3 -c \"print('Ran 1 test in 0.01s'); "
                    "print('no tests were found in the target')\""
                ),
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_tests_green_unverifiable_when_argument_escapes_via_attached_parent(self):
        ctx = self.ctx()
        with open(os.path.join(ctx.tmp_dir, "test_planted.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "import unittest\n\n\n"
                "class Planted(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n"
            )
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unittest discover -s..",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_accepts_relative_option_paths(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"print('2 passed')\" --cov=src/pkg",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    @mock.patch("bemyself.checks.MAX_LOG_BYTES", 4096)
    def test_tests_green_unverifiable_when_child_hits_write_limit(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"open('big.bin', 'wb').write(b'x' * 1000000)\"",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_reads_output_through_the_descriptor(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        secret = os.path.join(ctx.tmp_dir, "secret.txt")
        with open(secret, "w", encoding="utf-8") as handle:
            handle.write("TOPSECRET\n")
        script = (
            "import glob, os; "
            "p = glob.glob('../run-*.log')[0]; "
            "os.unlink(p); "
            f"os.symlink({secret!r}, p); "
            "print('Ran 1 test in 0.01s')"
        )
        result = run_claim(
            make_claim(
                "tests_green",
                command=f'python3 -c "{script}"',
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertNotIn("TOPSECRET", result.output)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_tests_green_unverifiable_when_make_ran_no_tests(self):
        repo = make_repo(os.path.join(self._tmp.name, "makefile"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "Makefile"), "w", encoding="utf-8") as handle:
            handle.write("test:\n\t@true\n")
        git("add", "-A")
        git("commit", "-q", "-m", "empty test target")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim("tests_green", command="make test", claimed_exit=0, commit=head),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_git_env_ignores_caller_git_dir(self):
        other = make_repo(os.path.join(self._tmp.name, "gitdir-other"))
        with open(os.path.join(other.path, "unique.txt"), "w", encoding="utf-8") as handle:
            handle.write("unique\n")
        subprocess.run(["git", "-C", other.path, "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", other.path, "commit", "-q", "-m", "unique"],
            check=True,
            capture_output=True,
        )
        unique = subprocess.run(
            ["git", "-C", other.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        os.environ["GIT_DIR"] = os.path.join(other.path, ".git")
        try:
            result = self.run_check("commit_exists", commit=unique)
        finally:
            os.environ.pop("GIT_DIR", None)
        self.assertIs(result.verdict, Verdict.REFUTED)


if __name__ == "__main__":
    unittest.main()

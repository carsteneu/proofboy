import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

from bemyself.checks import Ctx, run_claim
from bemyself.model import Claim, Verdict

from tests.fixtures import commit_probe, make_repo


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
        # The attack needs the rights of an unsandboxed child (it rewrites the
        # log path outside the checkout); under the sandbox that step already
        # fails. The descriptor-read defense must hold without the sandbox.
        ctx = self.ctx(allowlist=("python3 -c",), sandbox="off")
        secret = os.path.join(ctx.tmp_dir, "secret.txt")
        with open(secret, "w", encoding="utf-8") as handle:
            handle.write("TOPSECRET\n")
        script = (
            "import os; "
            "d = os.path.dirname(os.getcwd()); "
            "p = os.readlink('/proc/self/fd/1'); "
            "os.unlink(p); "
            "os.symlink(os.path.join(d, 'secret.txt'), p); "
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

    # --- round 4: option values, symlinks, startup hooks, fetch hardening --
    def test_tests_green_unverifiable_for_code_bearing_option_value(self):
        marker = os.path.join(self._tmp.name, "pwned-by-eval")
        command = (
            'make test --eval="test: ;@touch %s; @printf \'Ran 5 tests in 1.0s\\nOK\\n\'"' % marker
        )
        result = run_claim(
            make_claim(
                "tests_green", command=command, claimed_exit=0, commit=self.repo["good"]
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertFalse(os.path.exists(marker), "make executed the option value")

    def test_tests_green_unverifiable_for_dangerous_option_name(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="cargo test --config=target.x.runner=sh",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_equals_glued_value_escapes(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="make test -C../x=y",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_symlink_escapes_checkout(self):
        repo = make_repo(os.path.join(self._tmp.name, "symlinked"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        outside = os.path.join(self._tmp.name, "outside")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "Makefile"), "w", encoding="utf-8") as handle:
            handle.write("test:\n\t@printf 'Ran 9 tests in 0.1s\\nOK\\n'\n")
        os.symlink(outside, os.path.join(repo.path, "link"))
        git("add", "-A")
        git("commit", "-q", "-m", "add symlink")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim("tests_green", command="make test -C link", claimed_exit=0, commit=head),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_usercustomize_hook_is_disabled(self):
        import sys

        repo = make_repo(os.path.join(self._tmp.name, "usercustomize"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        git("rm", "-q", "test_ok.py")
        version = f"python{sys.version_info[0]}.{sys.version_info[1]}"
        hook_dir = os.path.join(repo.path, ".local", "lib", version, "site-packages")
        os.makedirs(hook_dir, exist_ok=True)
        with open(os.path.join(hook_dir, "usercustomize.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "import os\n"
                "print('Ran 9 tests in 0.001s')\n"
                "print('OK')\n"
                "os._exit(0)\n"
            )
        git("add", "-A")
        git("commit", "-q", "-m", "home hook")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unittest discover -s .",
                claimed_exit=0,
                commit=head,
            ),
            self.ctx(repo=repo.path),
        )
        # The real runner ran (and reported no tests, non-zero) instead of the
        # hook fabricating a green "Ran 9 tests".
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertNotIn("Ran 9 tests", result.output)

    def test_branch_pushed_ignores_repo_config_uploadpack(self):
        script = os.path.join(self._tmp.name, "config-upload.sh")
        marker = os.path.join(self._tmp.name, "config-upload-marker")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\ntouch %s\nexit 1\n" % marker)
        os.chmod(script, 0o755)
        subprocess.run(
            [
                "git",
                "-C",
                self.repo.path,
                "config",
                "remote.origin.uploadpack",
                script,
            ],
            check=True,
            capture_output=True,
        )
        try:
            result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        finally:
            subprocess.run(
                [
                    "git",
                    "-C",
                    self.repo.path,
                    "config",
                    "--unset",
                    "remote.origin.uploadpack",
                ],
                capture_output=True,
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertFalse(os.path.exists(marker), "git executed the repo-configured upload-pack")

    def test_branch_pushed_does_not_write_fetch_head(self):
        fetch_head = os.path.join(self.repo.path, ".git", "FETCH_HEAD")
        existed_before = os.path.exists(fetch_head)
        result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertEqual(os.path.exists(fetch_head), existed_before)

    def test_tests_green_unverifiable_when_key_value_path_escapes(self):
        planted = os.path.join(self._tmp.name, "planted")
        os.makedirs(planted, exist_ok=True)
        with open(os.path.join(planted, "test_planted.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "import unittest\n\n\n"
                "class Planted(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n"
            )
        repo = make_repo(os.path.join(self._tmp.name, "mvar"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "Makefile"), "w", encoding="utf-8") as handle:
            handle.write("test:\n\tpython3 -m unittest discover -s $(TESTS)\n")
        git("add", "-A")
        git("commit", "-q", "-m", "makefile")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim(
                "tests_green",
                command=f"make test TESTS={planted}",
                claimed_exit=0,
                commit=head,
            ),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_evidence_rejects_zero_count_summaries(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        for script in (
            "print('0 passing (2ms)')",
            "print('Tests:       0 total')",
            "print('test result: ok. 0 passed; 0 failed; 0 ignored')",
        ):
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

    def test_evidence_accepts_decorated_node_spec_output(self):
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"print('\\u2139 tests 4'); print('\\u2139 pass 4')\"",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_diff_scope_normalizes_dot_slash_paths(self):
        result = self.run_check(
            "diff_scope",
            ctx=self.ctx(base=self.repo["base"]),
            head=self.repo["good"],
            planned=("./good.txt", "./test_ok.py"),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_missing_runner_module_is_unverifiable(self):
        ctx = self.ctx(allowlist=("python3 -m unlikely_missing_runner",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unlikely_missing_runner",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_wrapper_shadows_runner(self):
        repo = make_repo(os.path.join(self._tmp.name, "wrapped"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "unittest.py"), "w", encoding="utf-8") as handle:
            handle.write("print('Ran 9 tests in 0.001s')\nprint('OK')\n")
        with open(os.path.join(repo.path, "Makefile"), "w", encoding="utf-8") as handle:
            handle.write("test:\n\tpython3 -m unittest\n")
        git("add", "-A")
        git("commit", "-q", "-m", "shadow via wrapper")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim("tests_green", command="make test", claimed_exit=0, commit=head),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    # --- round 5: variable injection, git object forgeries, config programs --
    def test_tests_green_unverifiable_for_variable_shell_injection(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command='make test "TESTS=;echo Ran 1 test;echo OK;#"',
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_for_dollar_expansion_in_value(self):
        canary = os.path.join(self._tmp.name, "canary-dollar")
        result = run_claim(
            make_claim(
                "tests_green",
                command="make test 'TESTS=$$(touch$${IFS}%s)'" % canary,
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertFalse(os.path.exists(canary), "make executed the variable payload")

    def test_tests_green_unverifiable_for_abbreviated_nested_option(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="npm test --node-opt=--require=/tmp/anything.js",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_when_stdlib_module_is_shadowed(self):
        repo = make_repo(os.path.join(self._tmp.name, "difflib-shadow"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "difflib.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "import os\n"
                "print('Ran 1 test in 0.001s')\n"
                "print('OK')\n"
                "os._exit(0)\n"
            )
        git("add", "-A")
        git("commit", "-q", "-m", "shadow difflib")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unittest discover -s .",
                claimed_exit=0,
                commit=head,
            ),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_diff_scope_not_forged_by_replace_ref(self):
        repo = make_repo(os.path.join(self._tmp.name, "replaced"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        # Without neutralization the replacement makes base..good look empty.
        git("replace", repo["good"], repo["base"])
        try:
            result = self.run_check(
                "diff_scope",
                ctx=self.ctx(repo=repo.path, base=repo["base"]),
                head=repo["good"],
                planned=("good.txt", "test_ok.py"),
            )
        finally:
            git("replace", "-d", repo["good"])
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_branch_pushed_not_forged_by_grafts(self):
        repo = make_repo(os.path.join(self._tmp.name, "grafted"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "unpushed.txt"), "w", encoding="utf-8") as handle:
            handle.write("unpushed\n")
        git("add", "-A")
        git("commit", "-q", "-m", "unpushed")
        unpushed = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        tip = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "origin/main"], capture_output=True, text=True
        ).stdout.strip()
        grafts = os.path.join(repo.path, ".git", "info", "grafts")
        os.makedirs(os.path.dirname(grafts), exist_ok=True)
        with open(grafts, "w", encoding="utf-8") as handle:
            handle.write(f"{tip} {unpushed}\n")
        try:
            result = run_claim(
                make_claim("branch_pushed", branch="main", commit=unpushed),
                self.ctx(repo=repo.path),
            )
        finally:
            os.unlink(grafts)
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_branch_pushed_ignores_repo_hooks(self):
        marker = os.path.join(self._tmp.name, "hook-marker")
        hooks = os.path.join(self.repo.path, ".githooks")
        os.makedirs(hooks, exist_ok=True)
        hook = os.path.join(hooks, "reference-transaction")
        with open(hook, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\ntouch %s\n" % marker)
        os.chmod(hook, 0o755)
        subprocess.run(
            ["git", "-C", self.repo.path, "config", "core.hooksPath", ".githooks"],
            check=True,
            capture_output=True,
        )
        try:
            result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        finally:
            subprocess.run(
                ["git", "-C", self.repo.path, "config", "--unset", "core.hooksPath"],
                capture_output=True,
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertFalse(os.path.exists(marker), "a repo hook ran during verification")

    def test_branch_pushed_ignores_repo_fsmonitor(self):
        marker = os.path.join(self._tmp.name, "fsmonitor-marker")
        script = os.path.join(self._tmp.name, "fsmon.sh")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\ntouch %s\nexit 0\n" % marker)
        os.chmod(script, 0o755)
        subprocess.run(
            ["git", "-C", self.repo.path, "config", "core.fsmonitor", script],
            check=True,
            capture_output=True,
        )
        try:
            result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        finally:
            subprocess.run(
                ["git", "-C", self.repo.path, "config", "--unset", "core.fsmonitor"],
                capture_output=True,
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertFalse(os.path.exists(marker), "core.fsmonitor ran during verification")

    def test_branch_pushed_refuses_repo_gitproxy(self):
        marker = os.path.join(self._tmp.name, "gitproxy-marker")
        script = os.path.join(self._tmp.name, "proxy.sh")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\ntouch %s\nexit 1\n" % marker)
        os.chmod(script, 0o755)
        subprocess.run(
            ["git", "-C", self.repo.path, "config", "core.gitProxy", script],
            check=True,
            capture_output=True,
        )
        try:
            result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        finally:
            subprocess.run(
                ["git", "-C", self.repo.path, "config", "--unset", "core.gitProxy"],
                capture_output=True,
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertFalse(os.path.exists(marker), "core.gitProxy ran during verification")

    def test_missing_runner_behind_wrapper_is_refuted(self):
        # Child output is repo-controlled: a wrapper that merely prints a
        # "No module named ..." phrase must not downgrade the verdict.
        repo = make_repo(os.path.join(self._tmp.name, "wrapped-missing"))

        def git(*args):
            return subprocess.run(
                ["git", "-C", repo.path, *args], check=True, capture_output=True
            )

        with open(os.path.join(repo.path, "Makefile"), "w", encoding="utf-8") as handle:
            handle.write(
                "test:\n"
                "\t@printf 'No module named definitely_missing_runner_mod\\n'\n"
                "\t@exit 1\n"
            )
        git("add", "-A")
        git("commit", "-q", "-m", "wrapped runner")
        head = subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        result = run_claim(
            make_claim("tests_green", command="make test", claimed_exit=0, commit=head),
            self.ctx(repo=repo.path),
        )
        self.assertIs(result.verdict, Verdict.REFUTED)

    # --- round 6: metachar-free re-shelling, URLs, abbreviations, clusters --
    def test_tests_green_unverifiable_for_whitespace_payload(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="make test TESTS='echo Ran 1 test'",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_for_node_loader_url(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="node --test --experimental-loader=file:///tmp/anything.mjs",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_for_two_letter_abbreviation(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="make test --ev=X!=/tmp/pwn",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_for_clustered_short_options(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="make test -kf/tmp/outside.mk",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_tests_green_unverifiable_for_tilde_path(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="make test TESTS=~root/x",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_branch_pushed_ignores_ext_transport_config(self):
        marker = os.path.join(self._tmp.name, "ext-marker")
        original_url = subprocess.run(
            ["git", "-C", self.repo.path, "config", "--local", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            [
                "git",
                "-C",
                self.repo.path,
                "config",
                "protocol.ext.allow",
                "always",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                self.repo.path,
                "config",
                "remote.origin.url",
                f"ext::touch {marker} --",
            ],
            check=True,
            capture_output=True,
        )
        try:
            result = self.run_check("branch_pushed", branch="main", commit=self.repo["bad"])
        finally:
            subprocess.run(
                ["git", "-C", self.repo.path, "config", "--unset", "protocol.ext.allow"],
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", self.repo.path, "config", "remote.origin.url", original_url],
                capture_output=True,
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertFalse(os.path.exists(marker), "the ext transport executed a program")

    @mock.patch("bemyself.checks.TEST_TIMEOUT", 2)
    def test_tests_green_timeout_kills_the_process_group(self):
        # The marker must be unique per run: a shared "sleep <n>" makes
        # concurrent runs pgrep/pkill each other's grandchildren.
        seconds = f"5432{os.getpid()}"
        marker = f"sleep {seconds}"
        ctx = self.ctx(allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command=(
                    "python3 -c \"import subprocess, time; "
                    f"subprocess.Popen(['sleep', '{seconds}']); time.sleep(60)\""
                ),
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("timed out", result.reason)
        import time

        # The kill is asynchronous and load-dependent: poll for a bounded
        # window instead of assuming a fixed grace period is enough.
        deadline = time.monotonic() + 5
        probe = subprocess.run(["pgrep", "-xf", marker], capture_output=True, text=True)
        while probe.returncode == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
            probe = subprocess.run(["pgrep", "-xf", marker], capture_output=True, text=True)
        if probe.returncode == 0:
            subprocess.run(["pkill", "-xf", marker], capture_output=True)
        self.assertNotEqual(probe.returncode, 0, "the grandchild survived the timeout")

    def test_tests_green_unverifiable_for_abbreviated_dangerous_option(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command='make test --eva="test: ;@true"',
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_allowlist_tolerates_extra_whitespace(self):
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3  -m unittest test_ok",
                claimed_exit=0,
                commit=self.repo["good"],
            ),
            self.ctx(),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)


_BWRAP = shutil.which("bwrap")

# Probe tests are committed per test run because their content depends on the
# live test process: the network probe dials the test's own listener, the
# escape probe writes next to the throwaway checkout.
_NET_PROBE = (
    "import socket\n"
    "import unittest\n"
    "\n\n"
    "class TestNet(unittest.TestCase):\n"
    "    def test_dials_the_host_listener(self):\n"
    "        connection = socket.create_connection((\"127.0.0.1\", {port}), timeout=5)\n"
    "        connection.close()\n"
)
_ESCAPE_PROBE = (
    "import os\n"
    "import unittest\n"
    "\n\n"
    "class TestEscape(unittest.TestCase):\n"
    "    def test_writes_beside_the_checkout(self):\n"
    "        target = os.path.join(os.path.dirname(os.getcwd()), \"escape-probe.txt\")\n"
    "        with open(target, \"w\", encoding=\"utf-8\") as handle:\n"
    "            handle.write(\"escaped\\n\")\n"
)
_BROKEN_BWRAP = (
    "#!/bin/sh\n"
    "echo \"bwrap: Creating new namespace failed: Operation not permitted\" >&2\n"
    "exit 1\n"
)


class SandboxTest(unittest.TestCase):
    """The --sandbox contract of the test-green check.

    Sandboxed means: bwrap wraps the allowlisted command, the filesystem root
    is read-only except the throwaway checkout, and the command gets its own
    network, PID and UTS namespaces. Every run names its sandbox state, and
    ``require`` never falls back to running unsandboxed.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def ctx(self, repo, **kw):
        work = os.path.join(self._tmp.name, "work", self._testMethodName)
        os.makedirs(work, exist_ok=True)
        kw.setdefault("tmp_dir", work)
        return Ctx(repo=repo, **kw)

    def probe_repo(self, name, source):
        repo = make_repo(os.path.join(self._tmp.name, name))
        return repo, commit_probe(repo, "test_probe.py", source)

    def broken_bwrap(self, ctx):
        path = os.path.join(ctx.tmp_dir, "fake-bwrap")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_BROKEN_BWRAP)
        os.chmod(path, 0o755)
        return path

    def probe_claim(self, commit):
        return make_claim(
            "tests_green",
            command="python3 -m unittest test_probe",
            claimed_exit=0,
            commit=commit,
        )

    # --- acceptance (a): a network connection must fail sandboxed ----------
    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_sandbox_blocks_the_network_the_host_listener_is_reachable_for(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        repo, commit = self.probe_repo("net-probe", _NET_PROBE.format(port=port))
        claim = self.probe_claim(commit)

        open_run = run_claim(claim, self.ctx(repo.path, sandbox="off"))
        self.assertIs(open_run.verdict, Verdict.CONFIRMED, open_run.output)

        ctx_on = self.ctx(
            repo.path, sandbox="require", tmp_dir=os.path.join(self._tmp.name, "work", self._testMethodName, "sandboxed")
        )
        sandboxed = run_claim(claim, ctx_on)
        self.assertIs(sandboxed.verdict, Verdict.REFUTED, sandboxed.output)
        self.assertIn("errors=1", sandboxed.output.lower())
        self.assertIn("sandboxed with bwrap", sandboxed.reason)
        self.assertIn("bwrap", sandboxed.command)

    # --- acceptance (b): writing outside the checkout must fail sandboxed --
    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_sandbox_blocks_writes_outside_the_checkout(self):
        repo, commit = self.probe_repo("escape-probe", _ESCAPE_PROBE)
        claim = self.probe_claim(commit)
        ctx_off = self.ctx(repo.path, sandbox="off")
        marker = os.path.join(ctx_off.tmp_dir, "escape-probe.txt")

        open_run = run_claim(claim, ctx_off)
        self.assertIs(open_run.verdict, Verdict.CONFIRMED, open_run.output)
        self.assertTrue(os.path.exists(marker), "the probe must really escape unsandboxed")

        ctx_on = self.ctx(repo.path, sandbox="require", tmp_dir=os.path.join(ctx_off.tmp_dir, "sandboxed"))
        sandboxed = run_claim(claim, ctx_on)
        self.assertIs(sandboxed.verdict, Verdict.REFUTED, sandboxed.output)
        self.assertIn("errors=1", sandboxed.output.lower())
        self.assertIn("sandboxed with bwrap", sandboxed.reason)
        self.assertFalse(os.path.exists(os.path.join(ctx_on.tmp_dir, "escape-probe.txt")))

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_auto_sandboxes_when_bwrap_is_available(self):
        repo = make_repo(os.path.join(self._tmp.name, "auto-on"))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -m unittest test_ok",
                claimed_exit=0,
                commit=repo["good"],
            ),
            self.ctx(repo.path, sandbox="auto"),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIn("bwrap", result.command)

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    @mock.patch("bemyself.checks.TEST_TIMEOUT", 1)
    def test_sandboxed_timeout_still_kills_the_sandbox(self):
        repo = make_repo(os.path.join(self._tmp.name, "timeout"))
        ctx = self.ctx(repo.path, sandbox="require", allowlist=("python3 -c",))
        result = run_claim(
            make_claim(
                "tests_green",
                command="python3 -c \"import time; time.sleep(30)\"",
                claimed_exit=0,
                commit=repo["good"],
            ),
            ctx,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("timed out", result.reason)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertEqual(os.listdir(ctx.tmp_dir), [], "throwaway files were left behind")

    # --- acceptance (c): require without a usable bwrap never falls back ---
    def test_require_without_bwrap_never_runs_the_command(self):
        repo, commit = self.probe_repo("require-missing", _ESCAPE_PROBE)
        ctx = self.ctx(repo.path, sandbox="require")
        with mock.patch("bemyself.checks.find_bwrap", return_value=None):
            result = run_claim(self.probe_claim(commit), ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("bwrap is not available", result.reason)
        self.assertIn("refusing to run the command unsandboxed", result.reason)
        self.assertFalse(os.path.exists(os.path.join(ctx.tmp_dir, "escape-probe.txt")))

    def test_require_with_broken_bwrap_never_runs_the_command(self):
        repo, commit = self.probe_repo("require-broken", _ESCAPE_PROBE)
        ctx = self.ctx(repo.path, sandbox="require")
        with mock.patch("bemyself.checks.find_bwrap", return_value=self.broken_bwrap(ctx)):
            result = run_claim(self.probe_claim(commit), ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("could not start a sandbox", result.reason)
        self.assertIn("refusing to run the command unsandboxed", result.reason)
        self.assertFalse(os.path.exists(os.path.join(ctx.tmp_dir, "escape-probe.txt")))

    # --- auto: fall back only loudly, and say which mode ran ----------------
    def test_auto_falls_back_and_says_so_when_bwrap_is_missing(self):
        repo, commit = self.probe_repo("auto-missing", _ESCAPE_PROBE)
        ctx = self.ctx(repo.path, sandbox="auto")
        with mock.patch("bemyself.checks.find_bwrap", return_value=None):
            result = run_claim(self.probe_claim(commit), ctx)
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("not sandboxed", result.reason)
        self.assertIn("bwrap not available", result.reason)
        self.assertNotIn("bwrap ", result.command)
        self.assertTrue(os.path.exists(os.path.join(ctx.tmp_dir, "escape-probe.txt")))

    def test_auto_falls_back_and_says_so_when_bwrap_cannot_start(self):
        repo, commit = self.probe_repo("auto-broken", _ESCAPE_PROBE)
        ctx = self.ctx(repo.path, sandbox="auto")
        with mock.patch("bemyself.checks.find_bwrap", return_value=self.broken_bwrap(ctx)):
            result = run_claim(self.probe_claim(commit), ctx)
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("not sandboxed", result.reason)
        self.assertIn("bwrap cannot start a sandbox", result.reason)
        self.assertTrue(os.path.exists(os.path.join(ctx.tmp_dir, "escape-probe.txt")))

    def test_sandbox_off_is_named_in_the_output(self):
        repo, commit = self.probe_repo("off", _ESCAPE_PROBE)
        ctx = self.ctx(repo.path, sandbox="off")
        result = run_claim(self.probe_claim(commit), ctx)
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("not sandboxed", result.reason)
        self.assertIn("--sandbox=off", result.reason)
        self.assertNotIn("bwrap", result.command)


if __name__ == "__main__":
    unittest.main()

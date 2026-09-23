"""Build throwaway git repositories for the checker tests.

Everything is local: the optional ``remote`` is a bare repository on disk that
is pushed to, so the tests never touch the network and never read the live
YesMem database.

:class:`FixtureTestCase` carries the shared plumbing of the command-running
checker tests (tmp root, work dir per test, commit helper, evidence reading);
the checker test modules subclass it instead of copying it.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest

from bemyself.checks import Ctx

# The honest runtime shims under tests/data/shims/ (a PHP host is not
# guaranteed); tests copy them into fixture repos.
_SHIMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "shims")

# Fixed commit metadata: two fixtures built from the same content must end in
# identical hashes -- test classes hold a repository pair (the same history
# with and without a remote) and compare the commits across it. With the wall
# clock as timestamp the second fixture got different hashes whenever a
# second boundary fell between the two builds (measured: 4 of 20 runs of
# tests/test_classes.py::ClassEndToEndTest failed that way). A fixture must
# not depend on the clock.
_COMMIT_DATE = "2026-09-01T12:00:00+0000"


def _git(repo, *args, check=True, env=None):
    proc = subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, env=env
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def _commit_env():
    return dict(os.environ, GIT_AUTHOR_DATE=_COMMIT_DATE, GIT_COMMITTER_DATE=_COMMIT_DATE)


class FixtureRepo:
    def __init__(self, path, remote, commits):
        self.path = path
        self.remote = remote
        self.commits = commits

    def __getitem__(self, name):
        return self.commits[name]


def _write(repo, name, content):
    full = os.path.join(repo, name)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(content)


def _commit(repo, message):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message, env=_commit_env())
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def commit_probe(repo, name, source):
    """Commit a probe test file into ``repo`` and return the new commit hash.

    The sandbox tests need probe tests whose content depends on the running
    test (a live port number, a marker path), so they cannot live in the
    static commit chain of :func:`make_repo`.
    """
    _write(repo.path, name, source)
    return _commit(repo.path, name)


def merge_into_main(repo, from_commit="good", branch="topic"):
    """Merge a branch off ``from_commit`` into main with ``--no-ff``.

    Returns ``(branch_tip, merge_commit)``; main points at the merge commit
    afterwards. The branch tip stays where it is, so the merge parents are
    ``(previous main tip, branch tip)`` -- the shape the merge checker
    confirms.
    """
    _git(repo.path, "checkout", "-q", "-b", branch, repo[from_commit])
    _write(repo.path, branch + ".txt", branch + "\n")
    tip = _commit(repo.path, branch + " work")
    _git(repo.path, "checkout", "-q", "main")
    _git(repo.path, "merge", "-q", "--no-ff", "-m", "merge " + branch, branch, env=_commit_env())
    return tip, _git(repo.path, "rev-parse", "HEAD").stdout.strip()


def make_repo(root, with_remote=True):
    """Create a fixture repo under ``root``.

    Commits: ``base`` -> ``good`` (adds a passing test) -> ``bad`` (adds a
    failing test) -> ``unpushed``. When ``with_remote`` is set a bare origin is
    created and ``main`` is pushed at ``bad``, so ``unpushed`` stays local.
    """
    os.makedirs(root, exist_ok=True)
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    subprocess.run(
        ("git", "-c", "init.defaultBranch=main", "init", "-q", repo),
        check=True,
        capture_output=True,
    )
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.com")

    _write(repo, "base.txt", "base\n")
    commits = {"base": _commit(repo, "base")}

    _write(repo, "good.txt", "good\n")
    _write(
        repo,
        "test_ok.py",
        "import unittest\n\n\n"
        "class TestOk(unittest.TestCase):\n"
        "    def test_addition(self):\n"
        "        self.assertEqual(1 + 1, 2)\n",
    )
    commits["good"] = _commit(repo, "good")

    _write(
        repo,
        "test_bad.py",
        "import unittest\n\n\n"
        "class TestBad(unittest.TestCase):\n"
        "    def test_fails(self):\n"
        "        self.assertEqual(1, 2)\n",
    )
    commits["bad"] = _commit(repo, "bad tests")

    remote = None
    if with_remote:
        remote = os.path.join(root, "remote.git")
        subprocess.run(
            ("git", "init", "-q", "--bare", remote), check=True, capture_output=True
        )
        _git(repo, "remote", "add", "origin", remote)
        _git(repo, "push", "-q", "origin", "main")

    _write(repo, "after.txt", "after\n")
    commits["unpushed"] = _commit(repo, "unpushed")

    return FixtureRepo(repo, remote, commits)


class FixtureTestCase(unittest.TestCase):
    """Shared fixture plumbing for the command-running checker tests."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "fixture-base"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def ctx(self, repo=None, **kw):
        work = os.path.join(self._tmp.name, "work", self._testMethodName)
        os.makedirs(work, exist_ok=True)
        kw.setdefault("tmp_dir", work)
        return Ctx(repo=repo or self.repo.path, **kw)

    def commit_files(self, repo, files):
        for name, content in files.items():
            full = os.path.join(repo.path, name)
            os.makedirs(os.path.dirname(full) or repo.path, exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(content)
        subprocess.run(
            ["git", "-C", repo.path, "add", "-A"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", repo.path, "commit", "-q", "-m", "fixture"],
            check=True,
            capture_output=True,
        )
        return subprocess.run(
            ["git", "-C", repo.path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def evidence_text(reason):
        """The part of a reason after the explicit evidence marker.

        The reason quotes the report's command, and a hostile command can
        contain the very counters it never produced -- so the tests must
        read the evidence section, never the command echo.
        """
        marker = "evidence:"
        if marker not in reason:
            return ""
        return reason.split(marker, 1)[1]

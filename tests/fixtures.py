"""Build throwaway git repositories for the checker tests.

Everything is local: the optional ``remote`` is a bare repository on disk that
is pushed to, so the tests never touch the network and never read the live
YesMem database.
"""

from __future__ import annotations

import os
import subprocess


def _git(repo, *args, check=True):
    proc = subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


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
    _git(repo, "commit", "-q", "-m", message)
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
    _git(repo.path, "merge", "-q", "--no-ff", "-m", "merge " + branch, branch)
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

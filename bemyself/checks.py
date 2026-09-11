"""Checkers that re-derive each claim against the repository.

Every checker returns a :class:`~bemyself.model.Result` carrying the verdict
plus the command it ran and the raw output. The doctrine is strict: a verdict
is ``CONFIRMED`` only when the check actually ran and proved the claim, and a
claim that cannot be run is ``UNVERIFIABLE`` -- never ``CONFIRMED``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from bemyself.model import Claim, Result, Verdict

GIT_TIMEOUT = 60
TEST_TIMEOUT = 300
ORIGIN = "origin"
LAST_LINES = 5

# Only test-runner prefixes may be executed from a report. A report is a
# claim, not a trusted script, so anything outside this list stays unverifiable.
DEFAULT_COMMAND_ALLOWLIST = (
    "python3 -m unittest",
    "python3 -m pytest",
    "python -m unittest",
    "python -m pytest",
    "pytest",
    "go test",
    "cargo test",
    "npm test",
    "npm run test",
    "yarn test",
    "bun test",
    "make test",
    "make check",
)


@dataclass
class Ctx:
    repo: str
    tmp_dir: str
    base: str | None = None
    allowlist: tuple[str, ...] = DEFAULT_COMMAND_ALLOWLIST


def _repo_command(ctx, *args):
    return ["git", "-C", ctx.repo, *args]


def _format(cmd):
    return " ".join(shlex.quote(part) for part in cmd)


def _git(ctx, *args, timeout=GIT_TIMEOUT):
    return subprocess.run(
        _repo_command(ctx, *args), capture_output=True, text=True, timeout=timeout
    )


def _output(proc):
    return (proc.stdout + proc.stderr).strip()


def _last_lines(text, count=LAST_LINES):
    lines = text.rstrip("\n").splitlines()
    return "\n".join(lines[-count:])


def _repo_guard(ctx):
    """Return an UNVERIFIABLE result if the repo is unusable, else None."""
    if not os.path.isdir(ctx.repo):
        return Result(Verdict.UNVERIFIABLE, reason=f"repo path does not exist: {ctx.repo}")
    proc = _git(ctx, "rev-parse", "--git-dir")
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "rev-parse", "--git-dir")),
            output=_output(proc),
            reason=f"not a git repository: {ctx.repo}",
        )
    return None


def _is_allowed(command, allowlist):
    return any(command == prefix or command.startswith(prefix + " ") for prefix in allowlist)


def check_commit_exists(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    commit = claim.fields["commit"]
    revision = f"{commit}^{{commit}}"
    proc = _git(ctx, "cat-file", "-e", revision)
    command = _format(_repo_command(ctx, "cat-file", "-e", revision))
    output = _output(proc)
    if proc.returncode == 0:
        return Result(Verdict.CONFIRMED, command, output, f"commit {commit} exists")
    return Result(Verdict.REFUTED, command, output, f"commit {commit} does not exist in {ctx.repo}")


def check_branch_pushed(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    branch = claim.fields["branch"]
    commit = claim.fields.get("commit")
    if not commit:
        return Result(Verdict.UNVERIFIABLE, reason="report names a branch but no commit hash")

    remotes = _git(ctx, "remote").stdout.split()
    if not remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            reason="no git remote configured; cannot verify the branch was pushed",
        )
    if ORIGIN not in remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"no '{ORIGIN}' remote (found: {', '.join(remotes)})",
        )

    if _git(ctx, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"commit {commit} is not present locally; cannot verify reachability",
        )

    ref = f"{ORIGIN}/{branch}"
    proc = _git(ctx, "log", ref, "--format=%H")
    command = _format(_repo_command(ctx, "log", ref, "--format=%H"))
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            _output(proc),
            reason=f"{ref} is unknown locally (try git fetch)",
        )
    if commit in set(proc.stdout.split()):
        return Result(Verdict.CONFIRMED, command, "", f"{commit} is reachable from {ref}")
    return Result(Verdict.REFUTED, command, "", f"{commit} is not reachable from {ref}")


def check_diff_scope(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    head = claim.fields["head"]
    planned = set(claim.fields.get("planned") or ())
    if not planned:
        return Result(Verdict.UNVERIFIABLE, reason="no planned file list to compare against")

    base = ctx.base or f"{head}^"
    proc = _git(ctx, "diff", "--name-only", f"{base}..{head}")
    command = _format(_repo_command(ctx, "diff", "--name-only", f"{base}..{head}"))
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            _output(proc),
            reason=f"could not diff {base}..{head}",
        )
    changed = [line for line in proc.stdout.splitlines() if line.strip()]
    output = "\n".join(changed)
    extra = sorted(set(changed) - planned)
    if extra:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            "changed files outside the planned scope: " + ", ".join(extra),
        )
    return Result(
        Verdict.CONFIRMED,
        command,
        output,
        f"all {len(changed)} changed files are within the planned scope",
    )


def check_tests_green(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    command_str = claim.fields["command"]
    claimed_exit = claim.fields["claimed_exit"]
    commit = claim.fields.get("commit")
    if not commit:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="no commit hash to check out for the test run",
        )
    if not _is_allowed(command_str, ctx.allowlist):
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"command is not in the allowlist: {command_str!r}",
        )
    try:
        argv = shlex.split(command_str)
    except ValueError as exc:
        return Result(Verdict.UNVERIFIABLE, command=command_str, reason=f"could not parse command: {exc}")
    if not argv:
        return Result(Verdict.UNVERIFIABLE, command=command_str, reason="empty command")

    if _git(ctx, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"commit {commit} is not present locally; cannot check it out",
        )

    try:
        os.makedirs(ctx.tmp_dir, exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="checkout-", dir=ctx.tmp_dir)
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"cannot create a throwaway checkout under {ctx.tmp_dir}: {exc}",
        )
    command_desc = f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && {command_str}"
    try:
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", ctx.repo, checkout],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        if clone.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(clone),
                reason="could not create a clean checkout",
            )
        co = subprocess.run(
            ["git", "-C", checkout, "checkout", "--quiet", commit],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        if co.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(co),
                reason=f"could not check out {commit}",
            )
        try:
            proc = subprocess.run(
                argv,
                cwd=checkout,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=TEST_TIMEOUT,
            )
        except FileNotFoundError as exc:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", f"command not found: {exc}")
        except subprocess.TimeoutExpired:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command timed out after {TEST_TIMEOUT}s",
            )
    finally:
        shutil.rmtree(checkout, ignore_errors=True)

    output = _last_lines(proc.stdout)
    if proc.returncode == claimed_exit:
        return Result(
            Verdict.CONFIRMED,
            command_desc,
            output,
            f"{command_str!r} exited {proc.returncode} as claimed",
        )
    return Result(
        Verdict.REFUTED,
        command_desc,
        output,
        f"claimed exit {claimed_exit}, actually exited {proc.returncode}",
    )


REGISTRY = {
    "commit_exists": check_commit_exists,
    "branch_pushed": check_branch_pushed,
    "diff_scope": check_diff_scope,
    "tests_green": check_tests_green,
}


def run_claim(claim: Claim, ctx: Ctx, registry: dict | None = None) -> Result:
    """Run one claim through the checker registry."""
    registry = REGISTRY if registry is None else registry
    checker = registry.get(claim.kind)
    if checker is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"no checker registered for claim kind {claim.kind!r}",
        )
    return checker(claim, ctx)

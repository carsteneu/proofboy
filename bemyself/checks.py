"""Checkers that re-derive each claim against the repository.

Every checker returns a :class:`~bemyself.model.Result` carrying the verdict
plus the command it ran and the raw output. The doctrine is strict: a verdict
is ``CONFIRMED`` only when the check actually ran and proved the claim, and a
claim that cannot be run is ``UNVERIFIABLE`` -- never ``CONFIRMED``.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from bemyself.model import Claim, Result, Verdict

GIT_TIMEOUT = 60
FETCH_TIMEOUT = 30
TEST_TIMEOUT = 300
ORIGIN = "origin"
LAST_LINES = 5
MAX_OUTPUT_BYTES = 1 << 16

_COMMIT_HASH_RE = re.compile(r"\A[0-9a-fA-F]{4,64}\Z")
_RESOLVED_RE = re.compile(r"\A[0-9a-fA-F]{40,64}\Z")
_UNITTEST_SUMMARY_RE = re.compile(r"\bRan \d+ tests?\b")

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


def _git_env():
    # Never let a git command block on an interactive credential prompt.
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git(args, timeout):
    """Run git without a shell; a timeout becomes a non-zero result."""
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=_git_env()
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"timed out after {timeout}s")


def _git(ctx, *args, timeout=GIT_TIMEOUT):
    return _run_git(_repo_command(ctx, *args), timeout)


def _output(proc):
    return (proc.stdout + proc.stderr).strip()


def _last_lines(text, count=LAST_LINES):
    lines = text.rstrip("\n").splitlines()
    return "\n".join(lines[-count:])


def _tail_bytes(path, limit=MAX_OUTPUT_BYTES):
    """Read at most ``limit`` bytes from the end of a file (bounds memory)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > limit:
                handle.seek(size - limit)
            data = handle.read(limit)
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def _rev_parse(ctx, revision):
    """Resolve any revision to a concrete commit hash, else None."""
    if not revision or revision.startswith("-"):
        return None
    proc = _git(ctx, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
    resolved = proc.stdout.strip()
    if proc.returncode == 0 and _RESOLVED_RE.match(resolved):
        return resolved
    return None


def _resolve_commit(ctx, value):
    """Resolve a report-supplied commit: it must be a hex object id."""
    value = (value or "").strip()
    if not _COMMIT_HASH_RE.match(value):
        return None
    return _rev_parse(ctx, value)


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


def _is_unittest(argv):
    return len(argv) >= 3 and argv[0] in ("python", "python3") and argv[1] == "-m" and argv[2] == "unittest"


def check_commit_exists(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    value = (claim.fields.get("commit") or "").strip()
    if not _COMMIT_HASH_RE.match(value):
        return Result(Verdict.UNVERIFIABLE, reason=f"not a commit hash: {value!r}")
    revision = f"{value}^{{commit}}"
    command = _format(_repo_command(ctx, "rev-parse", "--verify", "--quiet", revision))
    resolved = _rev_parse(ctx, value)
    if resolved is not None:
        return Result(Verdict.CONFIRMED, command, resolved, f"commit {value} resolves to {resolved}")
    return Result(Verdict.REFUTED, command, "", f"commit {value} does not exist in {ctx.repo}")


def check_branch_pushed(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    branch = claim.fields["branch"]
    value = claim.fields.get("commit")
    if not value:
        return Result(Verdict.UNVERIFIABLE, reason="report names a branch but no commit hash")

    remotes_proc = _git(ctx, "remote")
    remotes = remotes_proc.stdout.split()
    if not remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            reason="no git remote configured; cannot verify the branch was pushed",
        )
    if ORIGIN not in remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            output=_output(remotes_proc),
            reason=f"no '{ORIGIN}' remote (found: {', '.join(remotes)})",
        )

    commit = _resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
        )

    # Refresh the remote-tracking ref first: a stale local ref would let a
    # deleted or force-pushed remote branch produce a false CONFIRMED.
    fetch_args = ["fetch", "--quiet", "--no-tags", ORIGIN, branch]
    fetch = _git(ctx, *fetch_args, timeout=FETCH_TIMEOUT)
    if fetch.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, *fetch_args)),
            output=_output(fetch),
            reason=f"could not fetch {ORIGIN}/{branch} to confirm the push",
        )

    ref = f"{ORIGIN}/{branch}"
    proc = _git(ctx, "log", ref, "--format=%H")
    command = _format(_repo_command(ctx, "log", ref, "--format=%H"))
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            _output(proc),
            reason=f"{ref} is unknown after fetch",
        )
    if commit in set(proc.stdout.split()):
        return Result(Verdict.CONFIRMED, command, "", f"{commit} is reachable from {ref}")
    return Result(Verdict.REFUTED, command, "", f"{commit} is not reachable from {ref}")


def check_diff_scope(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    if not ctx.base:
        # Without an explicit base, `head^` would compare only the last commit
        # and could confirm a branch-wide scope while missing earlier changes.
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no base revision given; pass --base to compare the diff scope",
        )
    planned = set(claim.fields.get("planned") or ())
    if not planned:
        return Result(Verdict.UNVERIFIABLE, reason="no planned file list to compare against")

    base = _rev_parse(ctx, ctx.base)
    if base is None:
        return Result(Verdict.UNVERIFIABLE, reason=f"base revision does not resolve: {ctx.base!r}")
    head = _resolve_commit(ctx, claim.fields.get("head"))
    if head is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"head {claim.fields.get('head')!r} does not resolve to a commit",
        )

    proc = _git(ctx, "diff", "--name-only", f"{base}..{head}")
    command = _format(_repo_command(ctx, "diff", "--name-only", f"{base}..{head}"))
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE, command, _output(proc), reason=f"could not diff {base}..{head}"
        )

    changed = {line for line in proc.stdout.splitlines() if line.strip()}
    output = "\n".join(sorted(changed))
    if not changed:
        return Result(
            Verdict.REFUTED,
            command,
            "",
            f"no changed files between {base} and {head}; nothing was changed in scope",
        )
    extra = sorted(changed - planned)
    missing = sorted(planned - changed)
    if extra or missing:
        details = []
        if extra:
            details.append("changed but not planned: " + ", ".join(extra))
        if missing:
            details.append("planned but unchanged: " + ", ".join(missing))
        return Result(Verdict.REFUTED, command, output, "diff scope mismatch; " + "; ".join(details))
    return Result(
        Verdict.CONFIRMED,
        command,
        output,
        f"the {len(changed)} changed files match the planned scope exactly",
    )


def check_tests_green(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    command_str = claim.fields["command"]
    claimed_exit = claim.fields["claimed_exit"]
    value = claim.fields.get("commit")
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="no commit hash to check out for the test run",
        )
    commit = _resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
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

    try:
        os.makedirs(ctx.tmp_dir, exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="checkout-", dir=ctx.tmp_dir)
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"cannot create a throwaway checkout under {ctx.tmp_dir}: {exc}",
        )
    log_path = checkout + ".log"
    command_desc = f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && {command_str}"
    try:
        clone = _run_git(
            ["git", "clone", "--quiet", "--no-hardlinks", ctx.repo, checkout], GIT_TIMEOUT
        )
        if clone.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(clone),
                reason="could not create a clean checkout",
            )
        co = _run_git(["git", "-C", checkout, "checkout", "--quiet", commit], GIT_TIMEOUT)
        if co.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(co),
                reason=f"could not check out {commit}",
            )
        # Write the command output to a file and read only the tail: an
        # unbounded pipe could exhaust memory.
        try:
            with open(log_path, "wb") as log:
                proc = subprocess.run(
                    argv,
                    cwd=checkout,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=TEST_TIMEOUT,
                    env=_git_env(),
                )
        except FileNotFoundError as exc:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", f"command not found: {exc}")
        except subprocess.TimeoutExpired:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _last_lines(_tail_bytes(log_path)),
                f"command timed out after {TEST_TIMEOUT}s",
            )
    finally:
        shutil.rmtree(checkout, ignore_errors=True)

    raw_output = _tail_bytes(log_path)
    os.unlink(log_path)
    output = _last_lines(raw_output)
    if proc.returncode == claimed_exit:
        if (
            claim.kind == "tests_green"
            and _is_unittest(argv)
            and not _UNITTEST_SUMMARY_RE.search(raw_output)
        ):
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                output,
                "the command exited 0 but ran no unittest tests (no 'Ran N tests' summary)",
            )
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
    "tests_exit": check_tests_green,
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

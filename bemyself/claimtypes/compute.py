"""The ``[COMPUTE: <command> -> <sha256>]`` claim type: a computation
certificate.

A COMPUTE claim asserts that the named command prints exactly the claimed
bytes on stdout. The verifier re-runs the command on a fresh throwaway
checkout of the report's pinned commit (``git clone --no-hardlinks`` +
``git checkout``) inside the existing bwrap sandbox of the test-run checker:
read-only root, writable checkout, its own network, PID and UTS namespaces.
It hashes stdout as it streams and compares the SHA-256. Any finite
computation becomes checkable this way, without new code per problem: the hash
covers the bytes, the commit pins the code, and the allowlist pins which
commands may run at all.

The sandbox helpers come from :mod:`bemyself.checks`; the orchestration lives
here so that the P6 test-run path stays untouched.

Verdicts: CONFIRMED when the digest of stdout matches the claim (the exit code
is recorded as evidence, not as the criterion -- the claim is about stdout);
REFUTED when the digest differs; UNVERIFIABLE when the command is not in the
COMPUTE allowlist, names no bindable commit, does not exist, cannot run in the
sandbox, times out, or printed more than the documented output limit (a larger
stream is refused, never truncated into a verdict).

Limits: ``COMPUTE_TIMEOUT`` bounds one run; ``MAX_COMPUTE_BYTES`` bounds the
stdout that is hashed (streamed, so memory stays constant and no disk is
used). The sandbox has no network: a command that tries to reach it fails.
"""

from __future__ import annotations

import hashlib
import os
import re
import select
import shlex
import shutil
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING

from bemyself.claimtypes.halt import _ARROW, _UNICODE_ARROW
from bemyself.model import ClaimType, Result, Verdict

if TYPE_CHECKING:
    from bemyself.checks import Ctx

# Command prefixes a [COMPUTE] claim may run. Deliberately minimal: by default
# only the simulator entry that ships with this repository; any other
# computation is opened explicitly (--allow, repeated).
DEFAULT_COMPUTE_ALLOWLIST = ("python3 -m bemyself.turing",)

# One compute run must finish within this many seconds.
COMPUTE_TIMEOUT = 300
# The largest stdout the verifier will hash. More is refused, never truncated
# into a verdict; the hash streams, so the limit bounds time, not memory.
MAX_COMPUTE_BYTES = 64 << 20
_CHUNK = 1 << 16
_POLL = 0.25

# The digest is written as hex; the canonical form is lowercase.
_SHA256_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")

# One lazy "anything but a bracket" capture, fields split out of it afterwards;
# the pattern stays linear (see bemyself/claimtypes/halt.py for the reasoning).
_COMPUTE_RE = re.compile(r"\[COMPUTE:(?P<body>[^\]\[]*?)\]")


def _split_body(match):
    """(command, digest) of one marker: the last arrow separates them."""
    body = match.group("body")
    index = max(body.rfind(_ARROW), body.rfind(_UNICODE_ARROW))
    if index < 0:
        return None
    arrow = _UNICODE_ARROW if index == body.rfind(_UNICODE_ARROW) else _ARROW
    return body[:index].strip(), body[index + len(arrow) :].strip()


def parse(match, raw):
    """Fields of one [COMPUTE] marker: the command and the claimed digest."""
    parts = _split_body(match)
    if parts is None:
        # An arrow-less marker names no claim.
        return None
    command, digest_text = parts
    # The commit stays None until the report parser binds the report's single
    # commit (ClaimType.binds_commit).
    return {"command": command, "sha256": digest_text, "commit": None}


def _missing_program(program, checkout):
    """The program cannot exist in the sandbox: return it, else None.

    The sandbox binds the host root read-only and passes PATH through, so the
    host lookup answers the same question the sandboxed exec would: a bare
    name needs a PATH entry, a path-form name must exist in the checkout.
    """
    if "/" in program:
        if os.path.isfile(os.path.join(checkout, program)):
            return None
        return program
    if shutil.which(program) is None:
        return program
    return None


def _stream_stdout(proc, limit, deadline):
    """Hash the child's stdout as it arrives, in constant memory.

    Returns ``(digest, total, status)``: status "eof" when stdout was closed,
    "limit" when more than ``limit`` bytes arrived, "timeout" when the
    deadline passed first. The reader is this process, so the child cannot
    block forever on a full pipe.
    """
    digest = hashlib.sha256()
    total = 0
    fd = proc.stdout.fileno()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return digest, total, "timeout"
        ready, _, _ = select.select([fd], [], [], min(remaining, _POLL))
        if not ready:
            continue
        chunk = os.read(fd, _CHUNK)
        if not chunk:
            return digest, total, "eof"
        total += len(chunk)
        if total > limit:
            return digest, total, "limit"
        digest.update(chunk)


def check(claim, ctx):
    from bemyself import checks  # lazy: checks imports the type registry

    guard = checks._repo_guard(ctx)
    if guard is not None:
        return guard
    command_text = (claim.fields.get("command") or "").strip()
    if not command_text:
        return Result(Verdict.UNVERIFIABLE, reason="the claim names no command")
    claimed = (claim.fields.get("sha256") or "").strip()
    if not _SHA256_RE.match(claimed):
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason=f"not a sha256 digest: {claimed!r}",
        )
    value = (claim.fields.get("commit") or "").strip()
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason="no commit hash to pin the compute run",
        )
    commit = checks._resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
        )
    if not checks._is_allowed(command_text, ctx.compute_allowlist):
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason=f"command is not in the compute allowlist: {command_text!r}",
        )
    try:
        argv = shlex.split(command_text)
    except ValueError as exc:
        return Result(
            Verdict.UNVERIFIABLE, command=command_text, reason=f"could not parse command: {exc}"
        )
    if not argv:
        return Result(Verdict.UNVERIFIABLE, command=command_text, reason="empty command")
    strict = checks._is_wrapper_command(argv)
    escaping = [arg for arg in argv if checks._arg_escapes_checkout(arg, strict=strict)]
    if escaping:
        # Only the cwd is confined; an argument pointing outside the fresh
        # checkout would run code the pinned commit never contained.
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason=f"unsafe command argument: {escaping[0]!r}",
        )

    # require is a hard gate, exactly like the test-run checker: without a
    # working sandbox the command is never run, not even unsandboxed.
    mode = ctx.sandbox
    if mode not in checks.SANDBOX_MODES:
        return Result(
            Verdict.UNVERIFIABLE, command=command_text, reason=f"unknown sandbox mode: {mode!r}"
        )
    bwrap = None if mode == "off" else checks.find_bwrap()
    if mode == "require" and bwrap is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason="sandbox required (--sandbox=require) but bwrap is not available in PATH; "
            "refusing to run the command unsandboxed",
        )

    try:
        os.makedirs(ctx.tmp_dir, exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="compute-", dir=ctx.tmp_dir)
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_text,
            reason=f"cannot create a throwaway checkout under {ctx.tmp_dir}: {exc}",
        )
    command_desc = (
        f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && {command_text}"
    )
    proc = None
    err = None
    err_path = None
    try:
        clone = checks._run_git(
            ["git", "clone", "--quiet", "--no-hardlinks", ctx.repo, checkout],
            checks.GIT_TIMEOUT,
        )
        if clone.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                checks._output(clone),
                reason="could not create a clean checkout",
            )
        co = checks._run_git(
            ["git", "-C", checkout, "checkout", "--quiet", commit], checks.GIT_TIMEOUT
        )
        if co.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                checks._output(co),
                reason=f"could not check out {commit}",
            )
        escape = checks._symlink_escape(argv, checkout, strict=strict)
        if escape is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                reason=f"command argument resolves outside the checkout: {escape!r}",
            )
        missing = _missing_program(argv[0], checkout)
        if missing is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                reason=f"command not found: {missing!r}",
            )
        # A bwrap that exists but cannot start a sandbox is not usable; the
        # probe separates that from a failing command (see checks.py).
        sandbox_error = checks._sandbox_probe(bwrap, checkout) if bwrap is not None else None
        if mode == "require" and sandbox_error is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                "sandbox required (--sandbox=require) but bwrap could not start a sandbox: "
                f"{sandbox_error}; refusing to run the command unsandboxed",
            )
        sandboxed = bwrap is not None and sandbox_error is None
        if sandboxed:
            run_argv = checks._sandbox_prefix(bwrap, checkout) + argv
            note = "sandboxed with bwrap"
            command_desc = (
                f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && "
                + checks._sandbox_display(command_text)
            )
        elif mode == "off":
            run_argv = argv
            note = "not sandboxed: --sandbox=off"
        elif bwrap is None:
            run_argv = argv
            note = "not sandboxed: bwrap not available"
        else:
            run_argv = argv
            note = "not sandboxed: bwrap cannot start a sandbox"
        note_suffix = f" ({note})"
        # stdout is hashed while it streams; stderr only feeds the report tail,
        # so it goes to a private, size-capped file.
        try:
            err_fd, err_path = tempfile.mkstemp(prefix="compute-", suffix=".err", dir=ctx.tmp_dir)
            err = os.fdopen(err_fd, "w+b")
        except OSError as exc:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"cannot create a log file under {ctx.tmp_dir}: {exc}",
            )
        try:
            proc = subprocess.Popen(
                run_argv,
                cwd=checkout,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=err,
                env=checks._test_env(checkout),
                preexec_fn=checks._child_preexec,
            )
        except FileNotFoundError as exc:
            # Only bwrap itself can be missing here (the probe ran the same
            # binary path moments ago); the command never executed.
            return Result(
                Verdict.UNVERIFIABLE, command_desc, "", f"command not found: {exc}" + note_suffix
            )
        deadline = time.monotonic() + COMPUTE_TIMEOUT
        digest, total, status = _stream_stdout(proc, MAX_COMPUTE_BYTES, deadline)
        if status != "eof":
            checks._kill_process_group(proc)
            proc.wait()
            if status == "timeout":
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"command timed out after {COMPUTE_TIMEOUT}s" + note_suffix,
                    sandboxed=sandboxed,
                )
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command stdout exceeded the limit of {MAX_COMPUTE_BYTES} bytes" + note_suffix,
                sandboxed=sandboxed,
            )
        try:
            returncode = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            checks._kill_process_group(proc)
            proc.wait()
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command timed out after {COMPUTE_TIMEOUT}s" + note_suffix,
                sandboxed=sandboxed,
            )
        actual = digest.hexdigest()
        output = f"sha256={actual} bytes={total} exit={returncode}"
        raw_err, _ = checks._tail_open(err)
        if raw_err.strip():
            output += "\nstderr:\n" + checks._last_lines(raw_err)
        if actual == claimed.lower():
            return Result(
                Verdict.CONFIRMED,
                command_desc,
                output,
                f"sha256 of stdout matches the claimed digest "
                f"(exit {returncode}, {total} bytes)" + note_suffix,
                sandboxed=sandboxed,
            )
        return Result(
            Verdict.REFUTED,
            command_desc,
            output,
            f"claimed sha256 {claimed.lower()}, stdout has {actual}" + note_suffix,
            sandboxed=sandboxed,
        )
    finally:
        if proc is not None and proc.stdout is not None:
            try:
                proc.stdout.close()
            except OSError:
                pass
        if err is not None:
            try:
                err.close()
            except OSError:
                pass
        shutil.rmtree(checkout, ignore_errors=True)
        if err_path is not None:
            try:
                os.unlink(err_path)
            except OSError:
                pass


COMPUTE = ClaimType(
    kind="compute",
    pattern=_COMPUTE_RE,
    parse=parse,
    check=check,
    needs_repo=True,
    binds_commit=True,
)

"""The ``[ARTIFACT: <path> -> <sha256>]`` claim type: a file digest.

An ARTIFACT claim asserts that the named file exists and that its content has
exactly the claimed SHA-256: the honest form of "the deploy artefact is the
one that was built". The file is read under the artifact root -- the
repository by default, ``--artifact-root <dir>`` overrides it -- and never
outside it. The path comes from an untrusted report, so it is resolved with
``realpath`` and refused unless the resolved path stays inside the root: that
covers a symlink inside the root pointing outside as well as an absolute path
that lands elsewhere. A ``..`` component is refused outright, even when it
would normalize back inside the root. A symlink whose target stays inside the
root is followed.

Verdicts: CONFIRMED only when the file was read completely and its digest
equals the claimed one. REFUTED when the file does not exist, is no regular
file (a directory, a named pipe, a device), or its digest differs -- absence
and deviation are findings, not ignorance, and the verdict names the path,
the actual digest and the byte count. UNVERIFIABLE when neither an artifact
root nor a repository is given, the root does not exist, the path escapes the
root, the claimed digest is not 64 hex digits, the file is larger than
:data:`MAX_ARTIFACT_BYTES`, or the file grew beyond the limit while hashing.
The claim reads no repository object and declares no repository need: a
report carrying only [ARTIFACT] runs without ``--repo`` (and stays
UNVERIFIABLE without a root).

The digest streams chunk by chunk, so memory stays constant whatever the file
size; :data:`MAX_ARTIFACT_BYTES` bounds the time one claim may spend, and a
larger file is refused instead of hashed into a verdict. The file is opened
once with ``O_NONBLOCK`` (a named pipe must not block the verifier), checked
with ``fstat`` for being a regular file, and hashed through that descriptor,
never through a path a second time. A hard link inside the root is
indistinguishable from a file of its own (same inode); the root's content is
the caller's trust domain -- a writer with access inside the root could swap
a file between the confinement check and the open, which is out of scope for
a checker that judges the file the root presents.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat

from bemyself.claimtypes.halt import _split_body
from bemyself.model import Cause, ClaimType, Result, Verdict

# The largest file the verifier will hash. Beyond it the claim stays
# UNVERIFIABLE: the digest streams, so memory stays constant, but the limit
# bounds the time one claim may spend (--artifact-root does not change it).
MAX_ARTIFACT_BYTES = 256 << 20
_CHUNK = 1 << 16

# The digest is written as hex; the canonical form is lowercase.
_SHA256_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")

# One lazy "anything but a bracket" capture, fields split out of it
# afterwards; the pattern stays linear (see bemyself/claimtypes/halt.py for
# the reasoning). The core marker regex of bemyself/report.py is untouched:
# this type brings its own pattern.
_ARTIFACT_RE = re.compile(r"\[ARTIFACT:(?P<body>[^\]\[]*?)\]")


def parse(match, raw):
    """Fields of one [ARTIFACT] marker: the path and the claimed digest."""
    parts = _split_body(match)
    if parts is None:
        # An arrow-less marker names no claim.
        return None
    path, digest = parts
    return {"path": path.strip().strip("`"), "sha256": digest.strip().strip("`")}


def _resolved_under_root(root_real, path_text):
    """The path resolved inside ``root_real``, or None when it leaves it.

    A ``..`` component is refused before any resolution, so the escape
    question is answered lexically and by ``realpath`` -- a symlink pointing
    outside the root fails the prefix check even though its own path is
    lexically clean. The root ``/`` is its own prefix (it is not made of
    components to descend into), so a root at the filesystem root contains
    every path.
    """
    if any(part == ".." for part in path_text.split("/")):
        return None
    candidate = path_text if os.path.isabs(path_text) else os.path.join(root_real, path_text)
    resolved = os.path.realpath(candidate)
    prefix = root_real if root_real.endswith(os.sep) else root_real + os.sep
    if resolved != root_real and not resolved.startswith(prefix):
        return None
    return resolved


def check(claim, ctx):
    path_text = (claim.fields.get("path") or "").strip().strip("`")
    claimed = (claim.fields.get("sha256") or "").strip().strip("`")
    if not _SHA256_RE.match(claimed):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a sha256 digest: {claimed!r}",
            cause=Cause.DEFECT,
        )
    if not path_text:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="the claim names no file",
            cause=Cause.DEFECT,
        )
    root = ctx.artifact_root or ctx.repo
    if not root:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no artifact root: pass --repo or --artifact-root to say where the path resolves",
            cause=Cause.ENVIRONMENT,
        )
    root_real = os.path.realpath(root)
    if not os.path.isdir(root_real):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"artifact root is not a directory: {root}",
            cause=Cause.ENVIRONMENT,
        )
    resolved = _resolved_under_root(root_real, path_text)
    if resolved is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the path escapes the artifact root (or is absolute outside it): {path_text!r}",
            cause=Cause.DEFECT,
        )
    command = f"sha256 of {path_text} under {root}"
    # O_NONBLOCK: a named pipe must not block the read; regular files ignore
    # the flag. The descriptor is the only handle used from here on.
    try:
        handle = os.open(resolved, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except (FileNotFoundError, NotADirectoryError):
        return Result(Verdict.REFUTED, command, "", reason=f"file does not exist: {path_text}")
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            "",
            reason=f"cannot open {path_text!r}: {exc.strerror or exc}",
        )
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            return Result(
                Verdict.REFUTED, command, "", reason=f"not a regular file: {path_text}"
            )
        if info.st_size > MAX_ARTIFACT_BYTES:
            return Result(
                Verdict.UNVERIFIABLE,
                command,
                "",
                reason=f"{path_text} is {info.st_size} bytes, beyond the limit of "
                f"{MAX_ARTIFACT_BYTES} bytes (built-in limit)",
                cause=Cause.LIMIT,
            )
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(handle, _CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ARTIFACT_BYTES:
                # The size check above can go stale for a file that grows
                # while it is read; the running count is the hard bound.
                return Result(
                    Verdict.UNVERIFIABLE,
                    command,
                    "",
                    reason=f"{path_text} grew beyond the limit of {MAX_ARTIFACT_BYTES} bytes "
                    "while it was hashed (built-in limit)",
                    cause=Cause.LIMIT,
                )
            digest.update(chunk)
    finally:
        os.close(handle)
    actual = digest.hexdigest()
    output = f"sha256={actual} bytes={total}"
    if actual == claimed.lower():
        return Result(
            Verdict.CONFIRMED,
            command,
            output,
            f"{path_text} has the claimed sha256 ({total} bytes)",
        )
    return Result(
        Verdict.REFUTED,
        command,
        output,
        f"claimed sha256 {claimed.lower()}, {path_text} has {actual} ({total} bytes)",
    )


ARTIFACT = ClaimType(kind="artifact", pattern=_ARTIFACT_RE, parse=parse, check=check)

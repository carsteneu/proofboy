"""Parse a plaintext agent report into a list of verifiable claims.

The report is a yesloop Phase-6 DONE report. Recognised claim sources:

- markers ``[COMMIT: <hash>]``, ``[BRANCH: <name>]``, ``[MERGE: ...]``,
  ``[DEPLOY: ...]`` (typically inside the ``send_to payload`` line)
- ``Tests run: <command> -> exit <n>`` lines. Exit 0 is the claim
  ``tests_green``; a non-zero exit is ``tests_exit`` (an honest failure
  report, verified against its own exit code -- not labelled "green").
- a ``Files in scope: a, b`` line, which becomes a diff-scope claim
- the markers of every registered optional claim type
  (:data:`bemyself.claimtypes.CLAIM_TYPES`), for example ``[HALT: ...]``

A marker whose body reads as a placeholder -- an angle token like ``<hash>``,
the literal ``TODO``, or an ellipsis (``...``/``…``, e.g. a truncated digest)
-- is a template, not an assertion: the claim is skipped like a line without
the marker and never reported UNVERIFIABLE (see
:func:`looks_like_placeholder`).

A marker whose token no registered claim type claims (an upper-case token,
a colon and a body, like ``[FROB: 1]``) is a defect: ignoring it silently let
a report smuggle a claim of an unknown shape past the verifier. The claimed
tokens are the core markers plus the registry's
(:func:`bemyself.claimtypes.marker_tokens`); a template body keeps the
placeholder rule, an unknown token with a placeholder body claims nothing.
One convention rides along: the yesmem citation form ``[ID: 97352]`` (the
platform mandates it in reports) is a citation, not a claim, and is
recognized without one -- a body outside that shape stays a defect.

Parsing is deliberately permissive: unknown lines are ignored, and a claim is
only emitted when its source is present. Absurdly long lines are skipped, and
the marker patterns are written to scan linearly (see their comments); the
worst case per line stays bounded.
"""

from __future__ import annotations

import re

from bemyself import claimtypes
from bemyself.model import Claim

_MAX_LINE = 8192
# The shape of a commit hash; bemyself/checks.py validates the same shape.
# The templates of a yesloop section carry placeholder markers like
# "[COMMIT: <hash>]" next to the real hash: a placeholder is not a commit and
# must not block the binding of the one real hash.
_COMMIT_SHAPE_RE = re.compile(r"\A[0-9a-fA-F]{4,64}\Z")

# The core markers and their pattern come from one source: a token added here
# is recognized and claimed at once.
CORE_MARKERS = ("COMMIT", "BRANCH", "MERGE", "DEPLOY")

# One lazy "anything but a bracket" capture, stripped in Python: overlapping
# whitespace runs around the capture would let the engine backtrack cubically
# on a hostile whitespace run behind an unterminated marker (see
# bemyself/claimtypes/halt.py for the same shape).
_MARKER_RE = re.compile(r"\[(" + "|".join(CORE_MARKERS) + r"):([^\]\[]*?)\]")

# The form of a marker for a token no claim type claims: an upper-case token
# (a letter first, then letters and digits, no separator), a colon and a
# bracket-free body. The body class keeps the scan linear -- it never crosses
# a bracket, so every attempt is bounded by the distance to the next one.
_UNKNOWN_MARKER_RE = re.compile(r"\[([A-Z][A-Z0-9]*):([^\[\]]*)\]")

# A citation is not a claim: the platform's output discipline mandates the
# yesmem form [ID: 97352] (several ids comma-separated) in reports, so the
# token is recognized without one. The exemption is exactly the citation
# shape, not the token -- [ID: foo] stays a defect.
_CITATION_RE = re.compile(r"\A\[ID:\s*\d+(?:\s*,\s*\d+)*\]\Z")
_TESTS_RE = re.compile(
    r"^[ \t]*(?:\*\*)?Tests? run:[ \t]*(?P<cmd>\S(?:.*\S)?)[ \t]+"
    r"(?:->|\u2192)[ \t]+exit[ \t]+(?P<code>-?\d+)[ \t]*$"
)
_FILES_RE = re.compile(
    r"^[ \t]*(?:\*\*)?Files in scope:[ \t]*(?:\*\*)?[ \t]*(?P<files>\S.*?)[ \t]*$"
)

# An angle token ("<hash>", "<machine>", "<pfad>") is a template slot. The
# class excludes the brackets themselves and whitespace and needs at least
# one character, so a bare "<>" (an operator in a shell command) stays a
# value; scanning a hostile run of "<" stays linear either way: each "<" can
# advance at most to the next delimiter (see bemyself/claimtypes/halt.py for
# the same reasoning).
_ANGLE_TOKEN_RE = re.compile(r"<[^<>\s]+>")
_ELLIPSES = ("...", "\u2026")  # "..." and the Unicode ellipsis


def _truncation_ellipsis(value: str) -> bool:
    """Whether ``value`` ends in an ellipsis that truncates a token.

    ``e5b68dd1…`` is a truncated digest and a bare ``...`` is a template
    slot -- both name no value. ``go test ./...`` is not a template: its
    ASCII ellipsis is the tail of a path pattern (like ``pkg/...``), and a
    real command must stay a claim. The path exception applies to ``...``
    only: a Unicode ``…`` never ends a path pattern.
    """
    stripped = value.strip()
    for ellipsis in _ELLIPSES:
        if not stripped.endswith(ellipsis):
            continue
        cut = len(stripped) - len(ellipsis)
        if cut == 0:
            return True
        if ellipsis == "..." and stripped[cut - 1] in "/.":
            return False
        return True
    return False


def looks_like_placeholder(value: str) -> bool:
    """Whether ``value`` reads as a template, not as a claimed value.

    A yesloop section carries the marker templates of its briefing next to
    real values (``[COMMIT: <hash>]``, ``[DEPLOY: ...]``): a placeholder
    names nothing, so the claim it appears in is not an assertion. True for
    an angle token anywhere in the value, for a truncating ellipsis (a
    truncated digest like ``e5b68dd1…``), and for the literal ``TODO``.
    Surrounding backticks are ignored, so a marker-quoted template
    (``[COMPUTE: x -> `e5b68dd1…`]``) is recognised like an unquoted one.
    Everything else is a value, however unusual it looks -- the parser must
    never silently drop a claim that some real world could satisfy; the
    shapes where that promise loses to the form alone are enumerated in the
    README (section "Grenzen").
    """
    value = value.strip().strip("`")
    if not value:
        return False
    if _ANGLE_TOKEN_RE.search(value):
        return True
    if _truncation_ellipsis(value):
        return True
    return value.strip().lower() == "todo"


def _split_list(value: str) -> tuple[str, ...]:
    parts = (p.strip().strip("`*") for p in value.split(","))
    return tuple(p for p in parts if p)


def _claimed_tokens() -> set[str]:
    """The marker tokens some registered claim type claims, read live.

    Read per parse (not at import time) so a type registered at runtime
    claims its token like a built-in one.
    """
    tokens = set(CORE_MARKERS)
    for claim_type in claimtypes.CLAIM_TYPES:
        tokens.update(claimtypes.marker_tokens(claim_type))
    return tokens


def parse_report(text: str) -> list[Claim]:
    claims: list[Claim] = []
    commit_values: list[str] = []
    tests_lines: list[tuple[int, str, str, int]] = []
    files_line: tuple[int, str, tuple[str, ...]] | None = None
    claimed = _claimed_tokens()

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if len(raw) > _MAX_LINE:
            continue
        for match in _MARKER_RE.finditer(raw):
            key = match.group(1).upper()
            value = match.group(2).strip().strip("`")
            if looks_like_placeholder(value):
                # A placeholder names no commit, no branch, no merge and no
                # deploy: the marker asserts nothing and must not even enter
                # the commit binding below.
                continue
            if key == "COMMIT":
                claims.append(Claim("commit_exists", lineno, raw, {"commit": value}))
                commit_values.append(value)
            elif key == "BRANCH":
                claims.append(
                    Claim("branch_pushed", lineno, raw, {"branch": value, "commit": None})
                )
            elif key == "MERGE":
                claims.append(Claim("merge", lineno, raw, {"value": value, "commit": None}))
            elif key == "DEPLOY":
                claims.append(Claim("deploy", lineno, raw, {"value": value}))

        for match in _UNKNOWN_MARKER_RE.finditer(raw):
            token = match.group(1)
            if token in claimed:
                continue
            if _CITATION_RE.match(match.group(0)):
                continue
            if looks_like_placeholder(match.group(2)):
                # The template rule holds for an unknown token too: a marker
                # body that reads as a placeholder asserts nothing, and the
                # briefing of a section carries such templates.
                continue
            claims.append(Claim("unknown_marker", lineno, raw, {"token": token}))

        tests_match = _TESTS_RE.match(raw)
        if tests_match:
            command = tests_match.group("cmd").strip()
            if not looks_like_placeholder(command):
                tests_lines.append(
                    (lineno, raw, command, int(tests_match.group("code")))
                )

        files_match = _FILES_RE.match(raw)
        if files_match:
            planned = _split_list(files_match.group("files"))
            if not any(looks_like_placeholder(part) for part in planned):
                files_line = (lineno, raw, planned)

        for claim_type in claimtypes.CLAIM_TYPES:
            for match in claim_type.pattern.finditer(raw):
                fields = claim_type.parse(match, raw)
                if fields is None:
                    continue
                if any(
                    looks_like_placeholder(value)
                    for value in fields.values()
                    if isinstance(value, str)
                ):
                    # One placeholder field ("<machine>", "e5b68dd1…", "TODO")
                    # makes the whole claim a template; it is skipped like an
                    # arrow-less marker instead of ending UNVERIFIABLE.
                    continue
                claims.append(Claim(claim_type.kind, lineno, raw, fields))

    # Dependent claims bind to the report's commit only when the report names
    # exactly one; several distinct commits make the binding a guess, and a
    # guess must never confirm anything. Only hash-shaped values count.
    candidates = {value for value in commit_values if _COMMIT_SHAPE_RE.match(value)}
    bound_commit = candidates.pop() if len(candidates) == 1 else None
    if bound_commit is not None:
        # A claim kind declares this at its registry entry (binds_commit), so
        # the parser stays free of per-kind branches; the built-in branch and
        # merge claims bind the same way.
        binders = {claim_type.kind for claim_type in claimtypes.CLAIM_TYPES if claim_type.binds_commit}
        for claim in claims:
            if claim.kind in ("branch_pushed", "merge") or claim.kind in binders:
                if claim.fields.get("commit") is None:
                    claim.fields["commit"] = bound_commit

    for lineno, raw, command, code in tests_lines:
        kind = "tests_green" if code == 0 else "tests_exit"
        claims.append(
            Claim(
                kind,
                lineno,
                raw,
                {"command": command, "claimed_exit": code, "commit": bound_commit},
            )
        )

    if files_line is not None:
        lineno, raw, planned = files_line
        claims.append(
            Claim("diff_scope", lineno, raw, {"head": bound_commit, "planned": planned})
        )

    claims.sort(key=lambda claim: claim.line)
    return claims

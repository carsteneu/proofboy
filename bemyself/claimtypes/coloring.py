"""The ``[COLORING: k=<k> ; <color digits>]`` claim type: one explicit
Schur coloring as a finite, independently checkable certificate.

A COLORING claim asserts that the color string of length N -- the digit at
position i is the color of the number i -- contains no monochromatic
solution of ``x + y = z``: no triple of numbers ``x <= y`` with
``x + y <= N`` shares one color. The checker re-enumerates every triple in
this process: no repository, no subprocess, no network, nothing to
sandbox. Cost: the enumeration is O(N^2) (about N^2/4 pairs), bounded by
the executable limit (default 4096, ``--coloring-limit`` changes it); a
violating certificate is REFUTED at its first violation and pays only the
scan up to that point.

What a CONFIRMED verdict says: the k-coloring of 1..N is sum-free in every
color, so it certificates the lower bound ``S(k) >= N``, where S(k) is the
largest N that admits such a coloring. What it does NOT say: it is no
proof of equality -- ``S(k) = N`` would in addition require that no valid
k-coloring of 1..N+1 exists, and that side has no compact certificate (an
exhaustive search or a SAT proof; the classical S(5) = 160 needs a
petabyte-scale refutation). The type checks the coloring only; the verdict
sentence names that boundary explicitly.

Verdicts: CONFIRMED when every triple was enumerated and none is
monochromatic; REFUTED when one is -- the first in the canonical order
(x ascending, then y ascending) stands in the verdict as the witness;
UNVERIFIABLE when the marker does not have the documented shape, the color
count is not a single digit 1..9, a digit is not a color of the claim, the
string holds no digit, or the coloring is longer than the executable
limit.
"""

from __future__ import annotations

import re

from bemyself.model import ClaimType, Result, Verdict

# The largest N a [COLORING] claim may ask the checker to enumerate.
# Deliberately bounded: N numbers give about N^2/4 triples, so 4096 keeps a
# single claim near a second in CPython (--coloring-limit changes it).
DEFAULT_COLORING_LIMIT = 4096

# One lazy "anything but a bracket" capture per marker, sections split out
# afterwards; the pattern stays linear (see bemyself/claimtypes/halt.py for
# the reasoning).
_COLORING_RE = re.compile(r"\[COLORING:(?P<body>[^\]\[]*?)\]")

# k=<one digit 1..9> ; <digits 0..9> -- the color count is one digit
# because the colors themselves are encoded as the digits 1..9.
_K_RE = re.compile(r"\Ak[ \t]*=[ \t]*(?P<k>[0-9]+)\Z")
_DIGITS_RE = re.compile(r"\A(?P<digits>[0-9]+)\Z")

_SHAPE = "the marker needs the shape k=<colors> ; <color digits>"


def parse(match, raw):
    """Fields of one [COLORING] marker: the body, verbatim.

    Like [IDENT], a malformed marker must not vanish: it stays a claim and
    ends UNVERIFIABLE in :func:`check` instead of disappearing unnoticed.
    """
    return {"body": match.group("body").strip()}


def _count_triples(n):
    """The number of pairs ``x <= y`` with ``x + y <= n`` -- exactly the
    triples the scan enumerates."""
    return sum(n - 2 * x + 1 for x in range(1, n // 2 + 1))


def _first_violation(colors, n):
    """The first monochromatic triple in canonical order, or None.

    ``colors`` is 1-indexed; the canonical order is x ascending, then y
    ascending. The witness is ``(x, y, z, color)``.
    """
    for x in range(1, n + 1):
        for y in range(x, n + 1):
            z = x + y
            if z > n:
                break
            if colors[x] == colors[y] == colors[z]:
                return x, y, z, colors[x]
    return None


def check(claim, ctx):
    body = claim.fields.get("body") or ""
    sections = [part.strip() for part in body.split(";")]
    if len(sections) != 2:
        return Result(Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}")

    k_match = _K_RE.match(sections[0])
    if k_match is None:
        return Result(Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}")
    k_text = k_match.group("k")
    if len(k_text) != 1 or k_text == "0":
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the color count is not a single digit 1..9: {k_text!r} "
            "(the colors are encoded as the digits 1..9)",
        )
    k = int(k_text)

    digits_match = _DIGITS_RE.match(sections[1])
    if digits_match is None or not digits_match.group("digits"):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"{_SHAPE}: {body!r}",
        )
    digits_text = digits_match.group("digits")

    for digit in digits_text:
        if digit == "0":
            return Result(
                Verdict.UNVERIFIABLE,
                reason="0 is not a color digit; the colors are numbered 1..k",
            )
        if int(digit) > k:
            return Result(
                Verdict.UNVERIFIABLE,
                reason=f"the coloring uses color {digit} but the claim declares "
                f"only {k} color{'s' if k != 1 else ''}",
            )

    n = len(digits_text)
    if n > ctx.coloring_limit:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the coloring of {n} numbers exceeds the executable limit "
            f"of {ctx.coloring_limit}",
        )

    colors = [0] + [int(digit) for digit in digits_text]
    command = (
        f"check every triple x + y = z with x <= y, x + y <= {n} "
        f"in the {k}-coloring"
    )
    violation = _first_violation(colors, n)
    if violation is not None:
        x, y, z, color = violation
        witness = f"{x} + {y} = {z} with {x}, {y}, {z} all in color {color}"
        return Result(
            Verdict.REFUTED,
            command,
            f"first violation: {witness}",
            f"the {k}-coloring of 1..{n} is not Schur: the first violation in "
            f"canonical order (x ascending, then y ascending) is {witness}",
        )
    count = _count_triples(n)
    return Result(
        Verdict.CONFIRMED,
        command,
        f"checked {count} triples; first violation: none",
        f"all {count} triples x + y = z with x <= y and x + y <= {n} are "
        f"checked: no monochromatic solution in the {k}-coloring of 1..{n}; "
        f"this certificates the lower bound S({k}) >= {n} only -- it does not "
        "prove equality and says nothing about the upper bound",
    )


COLORING = ClaimType(kind="coloring", pattern=_COLORING_RE, parse=parse, check=check)

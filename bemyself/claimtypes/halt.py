"""The ``[HALT: <machine> -> <steps>]`` claim type.

A HALT claim asserts that the named machine of the bbchallenge standard
notation halts after exactly the claimed number of steps. An optional
``[SCORE: <machine> -> <ones>]`` on the same line for the same machine
additionally asserts the number of ones on the tape when it halts. The
machine is re-run by :mod:`bemyself.turing`, in this process: no repository,
no subprocess, no network, nothing to sandbox.

Verdicts: CONFIRMED only when the machine halts after exactly the claimed
steps -- and with exactly the claimed score when one is given; REFUTED when
it halts earlier, does not halt within the claimed steps (a finite witness:
not having halted after n steps proves it cannot halt exactly at step n; it
is not a proof that the machine never halts), or halts with a different
score; UNVERIFIABLE when the machine does not parse, the step count is not a
plain non-negative integer, or it exceeds the executable limit. A [SCORE]
marker without a [HALT] marker for its machine is not a claim.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bemyself import turing
from bemyself.model import ClaimType, Result, Verdict

if TYPE_CHECKING:
    from bemyself.checks import Ctx

# The largest number of steps the checker will ever execute for one claim.
# It carries the BB(5) champion's 47,176,870 steps; a claim beyond it stays
# UNVERIFIABLE (--halt-limit changes it).
DEFAULT_HALT_LIMIT = 47_176_870

_ARROW = r"(?:->|\u2192)"
_HALT_RE = re.compile(
    r"\[HALT:[ \t]*(?P<machine>[^\]\[]*?)[ \t]*"
    + _ARROW
    + r"[ \t]*(?P<steps>[^\]\[]*?)[ \t]*\]"
)
_SCORE_RE = re.compile(
    r"\[SCORE:[ \t]*(?P<machine>[^\]\[]*?)[ \t]*"
    + _ARROW
    + r"[ \t]*(?P<ones>[^\]\[]*?)[ \t]*\]"
)
_COUNT_RE = re.compile(r"\A[0-9]+\Z")


def _count(text):
    """A claimed count: plain decimal digits, no sign, no underscores."""
    if not text or not _COUNT_RE.match(text):
        return None
    try:
        return int(text)
    except ValueError:
        # CPython caps int(text) at a few thousand digits by default; such a
        # claim is beyond any limit and must not crash the checker.
        return None


def parse(match, raw):
    """Fields of one [HALT] marker, plus its same-line [SCORE] if any."""
    machine = match.group("machine").strip()
    scores = {
        score.group("ones").strip()
        for score in _SCORE_RE.finditer(raw)
        if score.group("machine").strip() == machine
    }
    fields = {
        "machine": machine,
        "steps": match.group("steps").strip(),
        "score": None,
        "score_conflict": False,
    }
    if len(scores) == 1:
        fields["score"] = scores.pop()
    elif len(scores) > 1:
        fields["score_conflict"] = True
    return fields


def check(claim, ctx):
    machine_text = (claim.fields.get("machine") or "").strip()
    if not machine_text:
        return Result(Verdict.UNVERIFIABLE, reason="the claim names no machine")
    try:
        machine = turing.parse(machine_text)
    except turing.MachineError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a machine of the bbchallenge notation: {exc}",
        )
    claimed = _count(claim.fields.get("steps") or "")
    if claimed is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="the claimed step count is not a non-negative integer: "
            f"{claim.fields.get('steps')!r}",
        )
    if claim.fields.get("score_conflict"):
        return Result(
            Verdict.UNVERIFIABLE,
            reason="conflicting [SCORE] markers for this machine; the claim is ambiguous",
        )
    if claimed > ctx.halt_limit:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed {claimed} steps exceed the executable limit of {ctx.halt_limit}",
        )
    result = turing.run(machine, claimed)
    command = f"simulate {machine_text} for at most {claimed} steps"
    output = f"halts={result.halts} steps={result.steps} score={result.score}"
    if not result.halts:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the machine did not halt within the claimed {claimed} steps; "
            f"it cannot halt exactly at step {claimed}",
        )
    if result.steps != claimed:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the machine halted after {result.steps} steps, not {claimed}",
        )
    score_text = claim.fields.get("score")
    if score_text is not None:
        claimed_score = _count(score_text)
        if claimed_score is None:
            return Result(
                Verdict.UNVERIFIABLE,
                command,
                output,
                f"the claimed score is not a non-negative integer: {score_text!r}",
            )
        if claimed_score != result.score:
            return Result(
                Verdict.REFUTED,
                command,
                output,
                f"the machine halted after {claimed} steps with score "
                f"{result.score}, not {claimed_score}",
            )
    return Result(
        Verdict.CONFIRMED,
        command,
        output,
        f"the machine halted after {claimed} steps with score {result.score}",
    )


HALT = ClaimType(kind="halt", pattern=_HALT_RE, parse=parse, check=check)

"""The ``[SEARCHED: <machine> -> <n>]`` claim type: a bounded search run.

A SEARCHED claim asserts exactly one finite observation: the machine of the
bbchallenge standard notation was re-run from the standard start and did not
halt within the claimed number of steps. The machine is re-run by
:mod:`bemyself.turing`, in this process: no repository, no subprocess, no
network, nothing to sandbox.

What a CONFIRMED verdict does NOT say: it is no proof that the machine never
halts. A finite search can never prove non-halting; the verdict text names
that boundary explicitly, and the type must never be readable as a
non-halting proof. A machine that halts within the claimed steps makes the
claim REFUTED, with the halt as its witness; a machine that does not parse, a
step count that is not a plain non-negative integer, a step count of 0 (a
zero-step run observes nothing), or a claim beyond the executable limit stays
UNVERIFIABLE.

Cost: the default limit means roughly one second of simulation for one claim
at the limit; the limit bounds each claim, not the report.
"""

from __future__ import annotations

import re

from bemyself import turing
from bemyself.claimtypes.halt import _count, _split_body
from bemyself.model import ClaimType, Result, Verdict

# The largest step count a [SEARCHED] claim may ask the simulator to execute.
# Deliberately bounded and separate from the [HALT] limit: a search claim is
# an honest finite observation, not a record attempt (--search-limit changes
# it).
DEFAULT_SEARCH_LIMIT = 10_000_000

# One lazy "anything but a bracket" capture per marker, fields split out of it
# afterwards; the pattern stays linear (see bemyself/claimtypes/halt.py for
# the reasoning).
_SEARCHED_RE = re.compile(r"\[SEARCHED:(?P<body>[^\]\[]*?)\]")


def parse(match, raw):
    """Fields of one [SEARCHED] marker: the machine and the claimed steps."""
    parts = _split_body(match)
    if parts is None:
        # An arrow-less marker names no claim.
        return None
    machine, steps = parts
    return {"machine": machine, "steps": steps}


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
    if claimed == 0:
        # A zero-step run observes nothing, so it certifies nothing.
        return Result(
            Verdict.UNVERIFIABLE,
            reason="a search of 0 steps observes nothing; the claim needs at least one step",
        )
    if claimed > ctx.search_limit:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed {claimed} steps exceed the executable limit of {ctx.search_limit}",
        )
    result = turing.run(machine, claimed)
    command = f"simulate {machine_text} for at most {claimed} steps"
    output = f"halts={result.halts} steps={result.steps} score={result.score}"
    if result.halts:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the machine halted after {result.steps} steps, "
            f"within the claimed {claimed} steps without halt",
        )
    return Result(
        Verdict.CONFIRMED,
        command,
        output,
        f"a bounded search of {claimed} steps found no halt; "
        "this does not prove that the machine never halts",
    )


SEARCHED = ClaimType(kind="searched", pattern=_SEARCHED_RE, parse=parse, check=check)

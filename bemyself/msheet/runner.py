"""Execution of one sheet: verdicts by the runner, never by the model.

The runner executes the v-lines in order (each with its witness), then the
claims of the claim zone, and writes the compact verdict appendix
``#ok:``/``#xx:``/``#?:`` (05-07 §4). ``ref`` promotion is validated here:
a reference counts only when the target's last status is ``+`` and the last
v-line targeting it was ok -- otherwise UNVERIFIABLE with reason
``ref_unconfirmed``. The verdicts are the runner's; a sheet can only *declare*
its result via ``[HALT]``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bemyself.model import Verdict
from bemyself.msheet import witnesses
from bemyself.msheet.sheet import Sheet, parse_sheet
from bemyself.msheet.witnesses import WitnessContext, WitnessResult

_APPENDIX_MARKERS = (
    ("ok", Verdict.CONFIRMED),
    ("xx", Verdict.REFUTED),
    ("?", Verdict.UNVERIFIABLE),
)


@dataclass(frozen=True)
class VResult:
    """The verdict of one v-line."""

    vid: str
    target: str
    verdict: Verdict
    reason: str
    line: int
    sandboxed: bool | None = None


@dataclass(frozen=True)
class ClaimResult:
    """The verdict of one claim."""

    cid: str
    verdict: Verdict
    reason: str
    line: int
    sandboxed: bool | None = None


@dataclass
class SheetResult:
    """Everything one run produced: verdicts, format errors, the appendix."""

    v_results: list[VResult] = field(default_factory=list)
    claim_results: list[ClaimResult] = field(default_factory=list)
    format_errors: list[str] = field(default_factory=list)
    appendix: list[str] = field(default_factory=list)

    def to_json(self):
        return {
            "v": [
                {
                    "id": r.vid,
                    "target": r.target,
                    "verdict": r.verdict.value,
                    "reason": r.reason,
                    "line": r.line,
                    "sandboxed": r.sandboxed,
                }
                for r in self.v_results
            ],
            "claims": [
                {
                    "id": r.cid,
                    "verdict": r.verdict.value,
                    "reason": r.reason,
                    "line": r.line,
                    "sandboxed": r.sandboxed,
                }
                for r in self.claim_results
            ],
            "format_errors": list(self.format_errors),
            "appendix": list(self.appendix),
        }


def _format_error(error):
    message = str(error)
    return message


def _appendix(v_results, claim_results):
    lines = []
    for marker, wanted in _APPENDIX_MARKERS:
        ids = [r.vid for r in v_results if r.verdict == wanted]
        ids += [r.cid for r in claim_results if r.verdict == wanted]
        if ids:
            lines.append(f"#{marker}: " + " ".join(ids))
    return lines


def run_sheet(sheet, *, sandbox="auto", timeout=10.0, halt_limit=None, cycle_limit=None):
    """Run one parsed sheet to its verdicts."""
    result = SheetResult(format_errors=[_format_error(e) for e in sheet.errors])

    last_status = {}
    for status in sheet.statuses:
        last_status[status.target] = status.status
    last_v: dict[str, Verdict] = {}
    context = WitnessContext(
        defs=sheet.defs,
        machines=sheet.machines,
        status_of=lambda line_id: last_status.get(line_id),
        last_v=lambda line_id: last_v.get(line_id),
        sandbox=sandbox,
        timeout=timeout,
    )
    if halt_limit is not None:
        context.halt_limit = halt_limit
    if cycle_limit is not None:
        context.cycle_limit = cycle_limit

    for vline in sheet.vlines:
        if vline.spec is None:
            outcome = WitnessResult(Verdict.UNVERIFIABLE, f"witness_unparsable: {vline.error}")
        else:
            body = sheet.body_of(vline.target)
            if body is None:
                outcome = WitnessResult(
                    Verdict.UNVERIFIABLE, f"unknown target {vline.target!r}"
                )
            else:
                outcome = witnesses.execute(vline.spec, body, context, tolerant=True)
        last_v[vline.target] = outcome.verdict
        result.v_results.append(
            VResult(vline.vid, vline.target, outcome.verdict, outcome.reason, vline.line, outcome.sandboxed)
        )

    for claim in sheet.claims:
        witness = sheet.witness_for(claim.cid)
        if witness is None:
            outcome = WitnessResult(Verdict.UNVERIFIABLE, "witness: the claim has no witness")
        elif witness.spec is None:
            outcome = WitnessResult(Verdict.UNVERIFIABLE, f"witness: {witness.error}")
        elif witness.spec.kind in ("auto", "range") and claim.formula is None:
            # auto/range compile the claim text itself: without a parsed V1
            # formula there is nothing to execute. A py/ref/sim/cyc witness
            # stands on its own and does not need a V1 formula as claim text
            # (trace and cycle answers reuse the checkpoint/cycle text).
            outcome = WitnessResult(Verdict.UNVERIFIABLE, f"formula: {claim.error}")
        else:
            outcome = witnesses.execute(witness.spec, claim.text, context, tolerant=False)
        result.claim_results.append(
            ClaimResult(claim.cid, outcome.verdict, outcome.reason, claim.line, outcome.sandboxed)
        )

    result.appendix = _appendix(result.v_results, result.claim_results)
    return result


__all__ = ["ClaimResult", "SheetResult", "VResult", "parse_sheet", "run_sheet"]

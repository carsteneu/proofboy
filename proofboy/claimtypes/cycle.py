"""The ``[CYCLE: <machine> -> t1,t2,d]`` claim type: a translated cycler.

A CYCLE claim asserts that the configuration of the named machine of the
bbchallenge standard notation at step t2 is the configuration at step t1
translated by d cells: the same state, the head moved by exactly d, and the
same tape content modulo that shift on every cell the machine can still
reach. This is the Lin recurrence of the bbchallenge decider ("translated
cyclers"): a traveling pattern that repeats forever while an undisturbed
memory may stay behind far enough to the left (or right) of the head -- the
cells behind the head's maximal excursion are never read again, so their
difference cannot change the future.

With t2 > t1, d != 0, a window that does not halt up to t2, and that
reachable-window match, determinism closes a complete proof: the run from t2
repeats the run from t1 translated, segment by segment, so a halt after t2
would already require a halt inside the verified window. This is a
non-halting proof -- for this machine with this certificate, re-derived by
:mod:`proofboy.turing` in this process (no repository, no subprocess, no
network, nothing to sandbox). It is not a general non-halting decision
procedure: the type checks the certificate it is given, it does not search
for one, and a [SEARCHED] run never turns into a CYCLE certificate.

Verdicts: CONFIRMED only when the run reaches step t2 without halting, the
state matches, the head moved by exactly d, and the tapes agree inside the
reachable window; REFUTED when the machine halts inside the window (the halt
is the witness) or a compared part differs; UNVERIFIABLE when the machine
does not parse, a value is not a plain integer (t1 and t2 non-negative, d
signed), t2 <= t1, d is 0, the step count exceeds the executable limit, or a
configuration's tape (or the compared window itself) exceeds the comparison
bound of :data:`TAPE_LIMIT` cells -- the comparison must really have been
performed, there is no confirmation by omission.

Cost: one claim at the limit means a few seconds of simulation plus the
comparison; the limit bounds each claim, not the report.
"""

from __future__ import annotations

import re

from proofboy import turing
from proofboy.claimtypes.halt import _count, _split_body
from proofboy.model import Cause, ClaimType, Result, Verdict

# The largest step count a [CYCLE] claim may ask the simulator to execute.
# Deliberately bounded like the SEARCHED limit, not the HALT limit: a larger
# certificate is opened explicitly (--cycle-limit).
DEFAULT_CYCLE_LIMIT = 10_000_000

# The largest tape window a comparison may materialize: a snapshot carrying
# more cells (both halves together) does not materialize, and a comparison
# window wider than this stays UNVERIFIABLE. A verdict must rest on a really
# performed comparison; without a bound one claim could force an arbitrarily
# wide one.
TAPE_LIMIT = 1 << 24

# One lazy "anything but a bracket" capture per marker, fields split out of it
# afterwards; the pattern stays linear (see proofboy/claimtypes/halt.py for
# the reasoning).
_CYCLE_RE = re.compile(r"\[CYCLE:(?P<body>[^\]\[]*?)\]")

# A claimed translation: plain decimal digits with an optional minus sign.
_SIGNED_RE = re.compile(r"\A-?[0-9]+\Z")


def _signed_count(text):
    """A claimed integer: plain decimal digits, an optional minus, no sign."""
    if not text or not _SIGNED_RE.match(text):
        return None
    try:
        return int(text)
    except ValueError:
        # CPython caps int(text) at a few thousand digits by default; such a
        # claim is beyond any limit and must not crash the checker.
        return None


def parse(match, raw):
    """Fields of one [CYCLE] marker: the machine and its three values."""
    parts = _split_body(match)
    if parts is None:
        # An arrow-less marker names no claim.
        return None
    machine, values = parts
    fields = {"machine": machine, "values": values, "t1": "", "t2": "", "d": ""}
    triplet = [part.strip() for part in values.split(",")]
    if len(triplet) == 3:
        fields["t1"], fields["t2"], fields["d"] = triplet
    return fields


def _state_letter(index):
    return chr(ord("A") + index)


def _pattern(snapshot):
    """The tape relative to the head: ``(cells, lo)`` covering ``[lo, lo+len)``.

    The cells run from the lowest to the highest written one, so cells
    outside the window are zero by construction.
    """
    cells = snapshot.left[::-1] + snapshot.right
    return cells, -snapshot.head - len(snapshot.left)


def _window(cells, lo, start, end):
    """The cells for ``[start, end)`` of a pattern, zero outside its extent."""
    out = bytearray(end - start)
    first = max(start, lo)
    last = min(end, lo + len(cells))
    if first < last:
        out[first - start : last - start] = cells[first - lo : last - lo]
    return bytes(out)


def _first_difference(left, right):
    """The index of the first differing cell of two unequal windows.

    Binary search over equal prefixes: the windows can span millions of
    cells, and a byte-wise scan in Python would dominate the check.
    """
    lo, hi = 0, len(left)
    while lo < hi:
        mid = (lo + hi) // 2
        if left[: mid + 1] == right[: mid + 1]:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _comparison_window(first, second, low, high):
    """The relative index range to compare, as ``[start, end)``.

    Both patterns are compared over the union of their written extents (they
    cover every written cell, and outside them the tape is zero by
    construction), clipped to the reachable window: ``low`` and ``high``
    bound the relative indices the machine can still read (None for an open
    end). An empty range is allowed and compared as equal.
    """
    cells1, lo1 = _pattern(first)
    cells2, lo2 = _pattern(second)
    start = min(lo1, lo2)
    end = max(lo1 + len(cells1), lo2 + len(cells2))
    if low is not None and low > start:
        start = low
    if high is not None and high + 1 < end:
        end = high + 1
    return start, end


def _tape_difference(first, second, start, end):
    """The first relative position where the tapes differ in ``[start, end)``.

    An empty range is equal: the patterns cover every written cell, so both
    tapes are zero there.
    """
    if start >= end:
        return None
    cells1, lo1 = _pattern(first)
    cells2, lo2 = _pattern(second)
    window1 = _window(cells1, lo1, start, end)
    window2 = _window(cells2, lo2, start, end)
    if window1 == window2:
        return None
    return start + _first_difference(window1, window2)


def check(claim, ctx):
    machine_text = (claim.fields.get("machine") or "").strip()
    if not machine_text:
        return Result(
            Verdict.UNVERIFIABLE, reason="the claim names no machine", cause=Cause.DEFECT
        )
    try:
        machine = turing.parse(machine_text)
    except turing.MachineError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a machine of the bbchallenge notation: {exc}",
            cause=Cause.UNVERIFIABLE,
        )
    t1_text = claim.fields.get("t1") or ""
    t2_text = claim.fields.get("t2") or ""
    d_text = claim.fields.get("d") or ""
    if not t1_text or not t2_text or not d_text:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="the certificate needs three comma-separated values (t1,t2,d): "
            f"{claim.fields.get('values')!r}",
            cause=Cause.DEFECT,
        )
    t1 = _count(t1_text)
    if t1 is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed t1 is not a non-negative integer: {t1_text!r}",
            cause=Cause.UNVERIFIABLE,
        )
    t2 = _count(t2_text)
    if t2 is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed t2 is not a non-negative integer: {t2_text!r}",
            cause=Cause.UNVERIFIABLE,
        )
    d = _signed_count(d_text)
    if d is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed translation is not an integer: {d_text!r}",
            cause=Cause.UNVERIFIABLE,
        )
    if t2 <= t1:
        # An unsound certificate is not a defective report: the claim is
        # honestly unverifiable ("P10" design), it is not accused of lying.
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the certificate needs t2 > t1 (here t1={t1}, t2={t2})",
            cause=Cause.UNVERIFIABLE,
        )
    if d == 0:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="the certificate needs a non-zero translation d (here 0)",
            cause=Cause.UNVERIFIABLE,
        )
    if t2 > ctx.cycle_limit:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed {t2} steps exceed the executable limit of "
            f"{ctx.cycle_limit}; raise the limit with --cycle-limit",
            cause=Cause.LIMIT,
        )
    result, snapshots = turing.run_checkpoints(machine, t2, (t1, t2), max_cells=TAPE_LIMIT)
    command = (
        f"simulate {machine_text} up to {t2} steps and compare the "
        f"configurations at steps {t1} and {t2}"
    )
    output = f"halts={result.halts} steps={result.steps} score={result.score}"
    if result.halts:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the machine halted after {result.steps} steps, "
            f"inside the certificate window of {t2} steps",
        )
    first = snapshots.get(t1)
    second = snapshots.get(t2)
    if first is None or second is None:
        step = t1 if first is None else t2
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            output,
            f"the configuration at step {step} does not materialize within the "
            f"tape bound of {TAPE_LIMIT} cells; the comparison cannot be performed "
            "(built-in limit)",
            cause=Cause.LIMIT,
        )
    if first.state != second.state:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the state at step {t2} is {_state_letter(second.state)}, "
            f"not the state at step {t1} ({_state_letter(first.state)})",
        )
    if second.head != first.head + d:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the head at step {t2} is at cell {second.head}, "
            f"not at cell {first.head} + {d} = {first.head + d}",
        )
    # The Lin window: moving right (d > 0), the machine must not read below
    # the head's lowest position of the interval. The fold includes the head
    # at step t1 itself -- the cell the first transition after t1 reads -- so
    # the excursion is at least 0; the clamp keeps the window sound even if
    # that seeding ever changes. Cells further left are never read again and
    # stay out of the comparison; for d < 0 the mirror.
    if d > 0:
        excursion = max(0, first.head - second.min_head)
        low, high, side = -excursion, None, "left"
    else:
        excursion = max(0, second.max_head - first.head)
        low, high, side = None, excursion, "right"
    start, end = _comparison_window(first, second, low, high)
    if end - start > TAPE_LIMIT:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            output,
            f"the comparison window of {end - start} cells exceeds the tape "
            f"bound of {TAPE_LIMIT} cells; the comparison cannot be performed "
            "(built-in limit)",
            cause=Cause.LIMIT,
        )
    difference = _tape_difference(first, second, start, end)
    if difference is not None:
        return Result(
            Verdict.REFUTED,
            command,
            output,
            f"the tape at step {t2} differs from the tape at step {t1} at "
            f"relative position {difference} inside the reachable window; "
            f"so it is not the configuration at step {t1} translated by {d}",
        )
    return Result(
        Verdict.CONFIRMED,
        command,
        output,
        f"the configuration at step {t2} equals the configuration at step {t1} "
        f"translated by {d} on every cell the machine can still reach "
        f"(it never goes more than {excursion} cells {side} of the head at "
        f"step {t1}); therefore by determinism the machine never halts",
    )


CYCLE = ClaimType(kind="cycle", pattern=_CYCLE_RE, parse=parse, check=check)

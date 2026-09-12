"""An independent simulator for the two-symbol Turing machines of the Busy
Beaver hunt, in the bbchallenge standard notation.

A machine string is a sequence of state blocks separated by ``_``, for example
``1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA``. Block *i* belongs to state ``A + i``;
each block holds two transitions of the form ``<write><move><next>``, the
first for the symbol read as 0, the second for 1. ``Z`` means halt, ``L`` and
``R`` move the head left and right. A triple may also be ``---``: that pair
has no transition, and the machine halts when the head reads it -- before
executing anything, so that attempt is not counted as a step (an explicit
``Z`` transition is executed and counted, as above).

The simulator starts in state A on a blank (all-zero) tape with the head at
position 0. It is a reimplementation from the notation itself, not a port of
any community simulator.

Stepping semantics: every executed transition counts as one step, including
the transition into the halt state Z. The score is the number of ones on the
tape when the run stops; for a halting run that includes the write of the
final transition, which is the convention behind the published scores (the
BB(5) champion's 4098 ones).

The tape is two bytearrays growing outward from position 0 (one for positions
>= 0, one for positions < 0). A run of ``n`` steps writes at most ``n + 1``
cells, so memory stays proportional to the executed steps rather than to the
(unbounded) position index.

Run as a command, it prints one result line::

    python3 -m bemyself.turing <machine> <steps>   ->  halts=<b> steps=<n> score=<n>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import NamedTuple

MAX_STATES = 25
_TAPE_CHUNK = 1024
_TRIPLE = r"(?:[01][LR][A-Z]|---)"
_BLOCK_RE = re.compile(r"\A" + _TRIPLE + _TRIPLE + r"\Z")
_UNDEFINED_TRIPLE = "---"
# Table sentinel for an undefined transition; -1 is the explicit halt Z.
_UNDEFINED = -2


class MachineError(ValueError):
    """The machine string is not a valid machine of this notation."""


class RunResult(NamedTuple):
    """Outcome of a run: whether it halted, steps taken, ones on the tape."""

    halts: bool
    steps: int
    score: int


@dataclass(frozen=True)
class Machine:
    """A parsed machine: one (write, move, next) triple per state and symbol."""

    states: int
    table: tuple[tuple[int, int, int], ...]
    source: str


def parse(machine: str) -> Machine:
    """Parse a machine string; raises :class:`MachineError` on bad input."""
    if not isinstance(machine, str):
        raise MachineError("machine must be a string")
    text = machine.strip()
    if not text:
        raise MachineError("empty machine")
    blocks = text.split("_")
    if len(blocks) > MAX_STATES:
        # State letters run A..Y; Z is reserved for halting.
        raise MachineError(f"more than {MAX_STATES} states: {len(blocks)}")
    letters = [chr(ord("A") + index) for index in range(len(blocks))]
    table: list[tuple[int, int, int]] = []
    for index, block in enumerate(blocks):
        if not _BLOCK_RE.match(block):
            raise MachineError(f"bad block {block!r} for state {letters[index]}")
        for symbol in (0, 1):
            triple = block[symbol * 3 : symbol * 3 + 3]
            if triple == _UNDEFINED_TRIPLE:
                table.append((0, 0, _UNDEFINED))
                continue
            write = int(triple[0])
            move = 1 if triple[1] == "R" else -1
            target = triple[2]
            if target == "Z":
                next_state = -1
            elif target in letters:
                next_state = ord(target) - ord("A")
            else:
                raise MachineError(
                    f"state {target!r} in block {block!r} is not defined"
                )
            table.append((write, move, next_state))
    return Machine(states=len(blocks), table=tuple(table), source=text)


def run(machine: Machine, max_steps: int) -> RunResult:
    """Run the machine for at most ``max_steps`` transitions.

    Returns a :class:`RunResult`: ``halts`` is True when the run ended in the
    halt state (with ``steps`` counting that final transition), False when the
    limit was reached first.
    """
    if max_steps < 0:
        raise ValueError("max_steps must be non-negative")
    table = machine.table
    right = bytearray()
    left = bytearray()
    right_len = 0
    left_len = 0
    position = 0
    state = 0
    ones = 0
    step = 0
    while step < max_steps:
        if position >= 0:
            symbol = right[position] if position < right_len else 0
        else:
            index = -position - 1
            symbol = left[index] if index < left_len else 0
        write, move, target = table[state * 2 + symbol]
        if target == _UNDEFINED:
            # No transition for this pair: the machine halts before executing,
            # so the attempt is not a step.
            return RunResult(True, step, ones)
        step += 1
        if write != symbol:
            if position >= 0:
                if position >= right_len:
                    grow = max(_TAPE_CHUNK, right_len * 2, position + 1)
                    right.extend(bytes(grow - right_len))
                    right_len = grow
                right[position] = write
            else:
                index = -position - 1
                if index >= left_len:
                    grow = max(_TAPE_CHUNK, left_len * 2, index + 1)
                    left.extend(bytes(grow - left_len))
                    left_len = grow
                left[index] = write
            ones += 1 if write else -1
        if target < 0:
            return RunResult(True, step, ones)
        position += move
        state = target
    return RunResult(False, step, ones)


def _main(argv):
    """One result line for one bounded run; the command form COMPUTE uses."""
    if len(argv) != 3:
        print("usage: python3 -m bemyself.turing <machine> <steps>", file=sys.stderr)
        return 2
    try:
        machine = parse(argv[1])
    except MachineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    steps_text = argv[2]
    if not (steps_text.isascii() and steps_text.isdigit()):
        print(f"error: not a non-negative step count: {steps_text!r}", file=sys.stderr)
        return 2
    try:
        steps = int(steps_text)
    except ValueError:
        # CPython caps int(text) at a few thousand digits; such a run could
        # never finish anyway.
        print(f"error: step count too large: {len(steps_text)} digits", file=sys.stderr)
        return 2
    result = run(machine, steps)
    print(f"halts={result.halts} steps={result.steps} score={result.score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))

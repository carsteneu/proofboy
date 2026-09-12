"""An independent simulator for the two-symbol Turing machines of the Busy
Beaver hunt, in the bbchallenge standard notation.

A machine string is a sequence of state blocks separated by ``_``, for example
``1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA``. Block *i* belongs to state ``A + i``;
each block holds two transitions of the form ``<write><move><next>``, the
first for the symbol read as 0, the second for 1. ``Z`` means halt, ``L`` and
``R`` move the head left and right.

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
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

MAX_STATES = 25
_TAPE_CHUNK = 1024
_BLOCK_RE = re.compile(r"\A[01][LR][A-Z][01][LR][A-Z]\Z")


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
            write = int(block[symbol * 3])
            move = 1 if block[symbol * 3 + 1] == "R" else -1
            target = block[symbol * 3 + 2]
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

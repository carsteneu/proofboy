#!/usr/bin/env python3
"""Both-direction local verification of the documented machine <-> map
reductions for the two BB(6) holdouts of the formal-conjectures shortlist.

This closes the E2 section-4.4 gap (``README.md`` of this directory): the
machine<->reformulation equivalences were taken from external documentation
and only *both sides separately* had been reproduced on finite windows. Here
the raw machine is the oracle and the documented map is checked against it in
both directions on finite, exactly labelled windows.

Candidates
----------
BMO#1 ``1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE``
    Canonical tape shape ``0^inf (10)^a D> 1^b 0^inf`` and the map
    ``f(a,b) -> f(a-b+1, 4b-1)`` if ``b < a+2``, ``f(a,b) -> f(2a+2, b-a-1)``
    if ``b > a+2``, halt if ``b = a+2``
    (documented on the BusyBeaverWiki BMO#1 page as @-d's rules; the wiki's
    visited list f(0,3) f(2,2) f(1,7) ... is reproduced configuration by
    configuration).  The shortlist A-model ``A(a,c)`` (rules
    ``a>c -> (a-c, 4c+2)``, ``a<c -> (2a+1, c-a)``, ``a=c -> halt``, start
    ``A(1,2)``) is the same map under the coordinate change
    ``A(a,c) = f(a-1, c+1)`` -- checked here as an identity of the two rule
    sets on a window, not taken on faith.

BMO#2 Antihydra ``1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA``
    Canonical tape shape ``0^inf 1^a 0 1^b E> 0^inf`` and the rules
    ``b -> floor(3b/2)+2`` with ``a -> a+2`` for even ``b`` and ``a -> a-1``
    for odd ``b`` (``a>0``), halt iff ``a = 0`` and ``b`` odd
    (sligocki.com 2024 and the BusyBeaverWiki Antihydra page; the wiki's rule
    step deltas 47, 111, 250, 500, 1209, 2713 ... are reproduced).  The Hydra
    form ``h = b+4``, ``h -> h + h//2`` with the counter ``+2``/``-1`` is
    checked against the rule walk step by step.

Method
------
* ``bemyself.turing`` (this repository's simulator) is the raw-machine oracle
  for blank-tape runs.
* :class:`TapeStepper` below steps a parsed machine from an *arbitrary*
  configuration; it is cross-checked against ``run_checkpoints`` of
  ``bemyself.turing`` on the blank-tape run before it is used for the window
  checks (both must agree on state, head and every tape cell).
* ``machine_to_map`` follows the blank-tape run and compares every canonical
  configuration with the map chain; ``map_to_machine`` starts from a
  constructed canonical configuration for every (a, b) in a window and
  compares the successor (or the halt) with the map.

Every output line is a finite observation on a named window. Nothing here is
a proof about halting or non-halting of the two machines.

Usage::

    python3 reductions.py        # prints the deterministic report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from bemyself.turing import (  # noqa: E402
    Machine,
    parse as parse_machine,
    run_checkpoints,
)

BMO1_MACHINE = "1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE"
ANTIHYDRA_MACHINE = "1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA"

# State indices of the two machines (A=0 .. F=5).
BMO1_STATE_D = 3
ANTIHYDRA_STATE_E = 4
# Table sentinels of bemyself.turing: -1 is the explicit halt Z, -2 the
# undefined pair that halts before executing.
HALT = -1
UNDEFINED = -2


class TapeStepper:
    """Step a parsed machine from an arbitrary tape configuration.

    ``cells`` maps absolute positions to the non-zero cells only; every
    position not in the dict reads 0. The state/step/halt semantics are those
    of :mod:`bemyself.turing`: entering Z counts as a step, an undefined pair
    halts before executing and does not count.
    """

    def __init__(self, machine: Machine):
        self.table = machine.table

    def step(self, state, head, cells):
        """One transition; returns (state, head, cells, halted)."""
        symbol = cells.get(head, 0)
        write, move, target = self.table[state * 2 + symbol]
        if target == UNDEFINED:
            return state, head, cells, True
        cells[head] = write
        if target == HALT:
            return HALT, head, cells, True
        return target, head + move, cells, False

    def run(self, state, head, cells, max_steps):
        """At most ``max_steps`` transitions; returns (state, head, cells,
        steps, halted). ``cells`` is copied, never mutated in place."""
        cells = dict(cells)
        for taken in range(max_steps):
            state, head, cells, halted = self.step(state, head, cells)
            if halted:
                return state, head, cells, taken + 1, True
        return state, head, cells, max_steps, False

    def run_until(self, state, head, cells, predicate, max_steps):
        """Run until ``predicate(state, head, cells)`` holds, the machine
        halts, or ``max_steps`` transitions are spent.

        The predicate is tested after every transition (never on the start
        configuration) -- the "next canonical configuration" semantics of the
        documented maps. Returns (state, head, cells, steps, halted, matched).
        """
        cells = dict(cells)
        for taken in range(max_steps):
            state, head, cells, halted = self.step(state, head, cells)
            if halted:
                return state, head, cells, taken + 1, True, False
            if predicate(state, head, cells):
                return state, head, cells, taken + 1, False, True
        return state, head, cells, max_steps, False, False


# ---------------------------------------------------------------------------
# Configurations, readers and maps
# ---------------------------------------------------------------------------

def bmo1_cells(a, b):
    """Tape cells of the BMO#1 canonical shape ``0^inf (10)^a D> 1^b 0^inf``."""
    cells = {}
    for index in range(a):
        cells[-2 * index - 2] = 1  # the '1' of the index-th (10) pair
    for index in range(b):
        cells[index] = 1  # the 1^b block starts at the head
    return cells


def antihydra_cells(a, b):
    """Tape cells of the Antihydra shape ``0^inf 1^a 0 1^b E> 0^inf``.

    The head sits at position 0, the 1^b block directly left of it, then the
    separator zero, then the 1^a block; everything else is zero.
    """
    cells = {}
    for index in range(b):
        cells[-index - 1] = 1
    for index in range(a):
        cells[-b - 2 - index] = 1
    return cells


def read_bmo1(cells, state, head):
    """(a, b) when the configuration is ``0^inf (10)^a D> 1^b 0^inf``."""
    if state != BMO1_STATE_D or cells.get(head, 0) != 1:
        return None
    b = 0
    pos = head
    while cells.get(pos, 0) == 1:
        b += 1
        pos += 1
    if any(value for position, value in cells.items() if position >= pos):
        return None  # non-zero cell right of the 1^b block
    a = 0
    pos = head - 1
    while cells.get(pos, 0) == 0 and cells.get(pos - 1, 0) == 1:
        a += 1
        pos -= 2
    if any(value for position, value in cells.items() if position <= pos):
        return None  # non-zero cell left of the (10)^a prefix
    return a, b


def read_antihydra(cells, state, head):
    """(a, b) when the configuration is ``0^inf 1^a 0 1^b E> 0^inf``."""
    if state != ANTIHYDRA_STATE_E or cells.get(head, 0) != 0:
        return None
    if any(value for position, value in cells.items() if position > head):
        return None  # non-zero cell right of the head
    b = 0
    pos = head - 1
    while cells.get(pos, 0) == 1:
        b += 1
        pos -= 1
    if cells.get(pos, 0) != 0:
        return None  # no separator zero left of the 1^b block
    pos -= 1
    a = 0
    while cells.get(pos, 0) == 1:
        a += 1
        pos -= 1
    if any(value for position, value in cells.items() if position <= pos):
        return None  # non-zero cell left of the 1^a block
    return a, b


def bmo1_next(a, b):
    """@-d's documented BMO#1 f-map; None means halt (b = a+2)."""
    if b < a + 2:
        return a - b + 1, 4 * b - 1
    if b == a + 2:
        return None
    return 2 * a + 2, b - a - 1


def f_to_A(pair):
    """Coordinate change to the shortlist A-model: A(a, c) = f(a-1, c+1)."""
    a, b = pair
    return a + 1, b - 1


def A_to_f(pair):
    """Inverse coordinate change: f(a, b) = A(a+1, b-1)."""
    a, c = pair
    return a - 1, c + 1


def A_next(a, c):
    """The shortlist A-model of the wiki page; None means halt (a = c)."""
    if a > c:
        return a - c, 4 * c + 2
    if a < c:
        return 2 * a + 1, c - a
    return None


def antihydra_next(a, b):
    """Antihydra rule map; None means halt (a = 0 and b odd)."""
    if b % 2 == 0:
        return a + 2, 3 * b // 2 + 2
    if a > 0:
        return a - 1, (3 * b + 3) // 2
    return None


def hydra_walk(steps):
    """The Hydra form: h_0 = 8, h -> h + h//2, counter +2 even / -1 odd.

    Returns (minimum_counter, final_h, counters): the counter values after
    1..steps steps.
    """
    h = 8
    counter = 0
    minimum = 0
    counters = []
    for _ in range(steps):
        counter = counter + 2 if h % 2 == 0 else counter - 1
        if counter < minimum:
            minimum = counter
        counters.append(counter)
        h += h // 2
    return minimum, h, counters


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def cross_check_stepper(machine, steps, max_steps):
    """TapeStepper against bemyself.turing on the blank-tape trajectory.

    Returns a dict with the checked steps, the reference result and the
    mismatch list; an empty list means state, head and every tape cell agreed
    at every checked step.
    """
    stepper = TapeStepper(machine)
    state, head, cells = 0, 0, {}
    wanted = set(steps)
    local = {}
    taken = 0
    while taken <= max_steps:
        if taken in wanted:
            local[taken] = (state, head, dict(cells))
        if taken == max_steps:
            break
        state, head, cells, halted = stepper.step(state, head, cells)
        taken += 1
        if halted:
            break
    result, snapshots = run_checkpoints(machine, max_steps, sorted(wanted))
    mismatches = []
    for step in steps:
        here = local.get(step)
        reference = snapshots.get(step)
        if here is None or reference is None:
            mismatches.append(f"step {step}: not reached on both sides")
            continue
        state, head, cells = here
        if state != reference.state:
            mismatches.append(f"step {step}: state {state} != {reference.state}")
        if head != reference.head:
            mismatches.append(f"step {step}: head {head} != {reference.head}")
        reference_cells = {}
        for offset, value in enumerate(reference.right):
            if value:
                reference_cells[offset] = value
        for offset, value in enumerate(reference.left):
            if value:
                reference_cells[-offset - 1] = value
        for position in sorted(set(cells) | set(reference_cells)):
            if cells.get(position, 0) != reference_cells.get(position, 0):
                mismatches.append(
                    f"step {step}: cell {position} "
                    f"{cells.get(position, 0)} != {reference_cells.get(position, 0)}"
                )
    return {
        "steps": list(steps),
        "reference_run": {"halts": result.halts, "steps": result.steps, "score": result.score},
        "mismatches": mismatches,
    }


def machine_to_map(machine, read, next_map, make_cells, max_configs, max_steps):
    """Follow the blank-tape run and compare canonical configurations with the map.

    Runs from the initial blank tape, collects every canonical configuration
    on the way and checks that consecutive configurations follow the map (a
    skipped configuration shows up as a mismatch).
    """
    stepper = TapeStepper(machine)
    state, head, cells = 0, 0, {}
    chain = []
    taken = 0
    halted = False
    while taken < max_steps and len(chain) < max_configs:
        state, head, cells, halted = stepper.step(state, head, cells)
        taken += 1
        if halted:
            break
        found = read(cells, state, head)
        if found is not None:
            chain.append((taken, found))
    mismatches = []
    for index, (_, pair) in enumerate(chain):
        expected = next_map(*pair)
        if index + 1 < len(chain):
            actual = chain[index + 1][1]
            if expected is None:
                mismatches.append(f"{pair}: map halts, machine continues to {actual}")
            elif actual != expected:
                mismatches.append(f"{pair}: map -> {expected}, machine -> {actual}")
    deltas = [chain[i + 1][0] - chain[i][0] for i in range(len(chain) - 1)]
    return {
        "configurations": [(step, list(pair)) for step, pair in chain],
        "steps_between": deltas,
        "mismatches": mismatches,
        "machine_halted": halted,
        "steps_run": taken,
    }


def window_outcomes(machine, make_cells, read, next_map, state_index, window_a, window_b, step_cap):
    """Per-(a, b) outcome of the raw successor check on a window.

    Returns a dict of lists: ``successor`` entries (a, b, found), ``halt``
    entries (a, b) -- the machine halts and the map says halt --, and
    ``mismatch`` entries (a, b, message). A start configuration that does not
    read back as (a, b) is a mismatch as well.
    """
    stepper = TapeStepper(machine)
    successors = []
    halts = []
    mismatches = []
    for a in window_a:
        for b in window_b:
            cells = make_cells(a, b)
            if read(dict(cells), state_index, 0) != (a, b):
                mismatches.append((a, b, f"start ({a},{b}) does not read back"))
                continue

            def is_canonical(state, head, cells, _index=state_index):
                return state == _index and read(cells, state, head) is not None

            state, head, result_cells, _, halted, matched = stepper.run_until(
                state_index, 0, cells, is_canonical, step_cap
            )
            expected = next_map(a, b)
            if halted:
                if expected is None:
                    halts.append((a, b))
                else:
                    mismatches.append((a, b, f"machine halts, map -> {expected}"))
            elif not matched:
                mismatches.append((a, b, f"no canonical configuration within {step_cap} steps"))
            else:
                found = read(result_cells, state, head)
                if expected is None:
                    mismatches.append((a, b, f"machine continues to {found}, map halts"))
                elif found != expected:
                    mismatches.append((a, b, f"map -> {expected}, machine -> {found}"))
                else:
                    successors.append((a, b, found))
    return {"successors": successors, "halts": halts, "mismatches": mismatches}


def halts_from(machine, make_cells, read, state_index, a, b, step_cap):
    """Whether the raw machine halts from the constructed configuration."""
    stepper = TapeStepper(machine)
    cells = make_cells(a, b)
    if read(dict(cells), state_index, 0) != (a, b):
        raise ValueError(f"({a},{b}) does not read back")
    _, _, _, _, halted, matched = stepper.run_until(
        state_index, 0, cells,
        lambda state, head, cells, _index=state_index: (
            state == _index and read(cells, state, head) is not None
        ),
        step_cap,
    )
    if halted:
        return True, None
    if matched:
        return False, "reached another canonical configuration"
    return False, f"neither halt nor a canonical configuration within {step_cap} steps"


def rules_equivalent_on_window(window_a, window_b):
    """f-rules and A-rules agree under the coordinate change on a window."""
    mismatches = []
    for a in window_a:
        for b in window_b:
            f_next = bmo1_next(a, b)
            a_next = A_next(*f_to_A((a, b)))
            transported = A_to_f(a_next) if a_next is not None else None
            if f_next != transported:
                mismatches.append(f"f({a},{b}): f-rule {f_next} != A-rule {transported}")
    return mismatches


def hydra_alignment(steps):
    """The wiki's rule walk from A(0,4) against the Hydra form.

    At every step the rule pair (a, b) must equal (counter, h-4) of the Hydra
    walk, and the shift lemma floor(3(b+4)/2) = floor(3b/2)+6 must hold.
    """
    mismatches = []
    a, b = 0, 4
    h = 8
    counter = 0
    for index in range(steps):
        if h != b + 4:
            mismatches.append(f"step {index}: h {h} != b+4 {b + 4}")
            break
        if counter != a:
            mismatches.append(f"step {index}: counter {counter} != a {a}")
            break
        if (3 * (b + 4)) // 2 != (3 * b) // 2 + 6:
            mismatches.append(f"step {index}: shift lemma fails at b={b}")
            break
        counter = counter + 2 if h % 2 == 0 else counter - 1
        h += h // 2
        nxt = antihydra_next(a, b)
        if nxt is None:
            mismatches.append(f"step {index}: rule map halts at ({a},{b})")
            break
        a, b = nxt
    return mismatches


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report():
    """The deterministic report (one line per checked property)."""
    lines = ["# both-direction reduction checks (finite windows; no halting claims)"]
    machine_bmo1 = parse_machine(BMO1_MACHINE)
    machine_anti = parse_machine(ANTIHYDRA_MACHINE)

    cross1 = cross_check_stepper(
        machine_bmo1, [0, 1, 5, 23, 45, 113, 249, 1000, 100000], 100000
    )
    cross2 = cross_check_stepper(
        machine_anti, [0, 1, 11, 58, 169, 1000, 100000], 100000
    )
    for name, cross in (("bmo1", cross1), ("antihydra", cross2)):
        lines.append(
            f"stepper.cross_check.{name}.ok={str(not cross['mismatches']).lower()} "
            f"steps={cross['steps']} mismatches={cross['mismatches'] or 'none'}"
        )

    # --- BMO#1: trajectory and window -------------------------------------
    m2m = machine_to_map(
        machine_bmo1, read_bmo1, bmo1_next, bmo1_cells, max_configs=12, max_steps=20000
    )
    lines.append(
        f"bmo1.machine_to_map.configs={len(m2m['configurations'])} "
        f"first={m2m['configurations'][0][1]} last={m2m['configurations'][-1][1]} "
        f"deltas={m2m['steps_between']} mismatches={m2m['mismatches'] or 'none'}"
    )

    window_a = list(range(0, 25))
    window_b = list(range(1, 61))
    outcomes = window_outcomes(
        machine_bmo1, bmo1_cells, read_bmo1, bmo1_next, BMO1_STATE_D,
        window_a, window_b, step_cap=200000,
    )
    primary = [
        (a, b) for a, b, _ in outcomes["successors"] if b >= 2 and b != a + 2
    ]
    b1_halts = [
        pair for pair in outcomes["mismatches"]
        if pair[1] == 1 and "machine halts" in pair[2]
    ]
    b1_deviations = [
        pair for pair in outcomes["mismatches"] if pair[1] == 1 and pair not in b1_halts
    ]
    lines.append(
        f"bmo1.window.primary=a0..24 b2..60 without b=a+2 "
        f"successors={len(primary)} "
        f"mismatches={[f'{a},{b}:{msg}' for a, b, msg in outcomes['mismatches'] if b != 1 and b != a + 2] or 'none'}"
    )
    lines.append(
        f"bmo1.window.boundary_b1=a0..24 machine_halts={len(b1_halts)} "
        f"other_deviations={len(b1_deviations)} "
        f"(documented map predicts a continuation; b=1 is outside the verified domain)"
    )
    boundary = [pair for pair in outcomes["mismatches"] if pair[1] == pair[0] + 2]
    second_step = [
        halts_from(machine_bmo1, bmo1_cells, read_bmo1, BMO1_STATE_D, 2 * a + 2, 1, 100000)[0]
        for a in window_a
    ]
    lines.append(
        f"bmo1.window.boundary_b_equals_a_plus_2=a0..24 machine_moves_on={len(boundary)} "
        f"(documented map predicts halt); from f(2a+2,1) the machine halts="
        f"{str(all(second_step)).lower()} in {len(second_step)} cases"
    )

    eq = rules_equivalent_on_window(range(0, 25), range(1, 61))
    lines.append(
        f"bmo1.A_model_coordinate_change.window=a0..24 b1..60 "
        f"mismatches={eq or 'none'}"
    )

    # --- Antihydra: trajectory and window ---------------------------------
    m2m3 = machine_to_map(
        machine_anti, read_antihydra, antihydra_next, antihydra_cells,
        max_configs=12, max_steps=10 ** 6,
    )
    lines.append(
        f"antihydra.machine_to_map.configs={len(m2m3['configurations'])} "
        f"first={m2m3['configurations'][0][1]} last={m2m3['configurations'][-1][1]} "
        f"deltas={m2m3['steps_between']} mismatches={m2m3['mismatches'] or 'none'}"
    )

    window_a2 = list(range(0, 21))
    window_b2 = list(range(1, 41))
    outcomes2 = window_outcomes(
        machine_anti, antihydra_cells, read_antihydra, antihydra_next,
        ANTIHYDRA_STATE_E, window_a2, window_b2, step_cap=200000,
    )
    primary2 = [pair for pair in outcomes2["successors"] if pair[1] >= 2]
    documented_halts = [pair for pair in outcomes2["halts"] if pair[1] >= 2]
    expected_halts = [(a, b) for a in window_a2 for b in window_b2
                      if b >= 2 and a == 0 and b % 2 == 1]
    deviations_b2 = [pair for pair in outcomes2["mismatches"] if pair[1] >= 2]
    deviations_b1 = [pair for pair in outcomes2["mismatches"] if pair[1] == 1]
    lines.append(
        f"antihydra.window.primary=a0..20 b2..40 successors={len(primary2)} "
        f"halts={len(documented_halts)} halts_match_documented="
        f"{str(documented_halts == expected_halts).lower()} "
        f"mismatches={deviations_b2 or 'none'}"
    )
    lines.append(
        f"antihydra.window.boundary_b1=a0..20 deviations={len(deviations_b1)} "
        f"(documented rule conditions are b>=2 even / b>=3 odd; b=1 is outside "
        f"the verified domain)"
    )

    walk_mismatches = hydra_alignment(3000)
    minimum, final_h, _ = hydra_walk(2000)
    lines.append(
        f"antihydra.hydra_alignment.steps=3000 mismatches={walk_mismatches or 'none'} "
        f"hydra.min_counter_2000={minimum} hydra.bits_2000={final_h.bit_length()}"
    )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    sys.stdout.write(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

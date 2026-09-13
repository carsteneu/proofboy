#!/usr/bin/env python3
"""Bounded probes on shortlisted formal-conjectures candidates.

The probes are deliberately bounded and deterministic: they re-derive the
computational content of catalog statements on a finite budget with exact
integer arithmetic, and use this repository's own Turing-machine simulator
(``bemyself.turing``) for the machine side. Nothing here is a proof of an
open problem — every output line is a finite observation with a named bound.

Covered candidates (see the README for the shortlist rationale):
  * BMO#1  ``1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE`` (sequence + machine)
  * BMO#2  Antihydra                                     (sequence + machine)
  * BMO#3  sequence ``a_{n+1} = a_n + 2^(v2(a_n)+2) - 1`` (solved side)
  * BMO#4  sequence, closed form ``(3*2^n + c(n))/5``     (solved side)
  * BMO#5  ``1RB0LD_1LC0RA_1RA1LB_1LA1LE_1RF0LC_---0RE``  (sequence)
  * BMO#8  ``1RB0LD_0RC1RB_0RD0RA_1LE0RD_1LF---_0LA1LA``  (sequence)
  * OEIS A34693 smallest k with k*n + 1 prime            (sweep)

Usage:
    python3 catalog_probe.py [--small-iterations N] [--big-iterations N]
                             [--sweep N] [--machine-steps N]
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from bemyself.turing import MachineError, parse as parse_machine, run as run_machine  # noqa: E402

BMO1_MACHINE = "1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE"
BMO2_MACHINE = "1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA"
BMO5_MACHINE = "1RB0LD_1LC0RA_1RA1LB_1LA1LE_1RF0LC_---0RE"
BMO8_MACHINE = "1RB0LD_0RC1RB_0RD0RA_1LE0RD_1LF---_0LA1LA"
BMO1_FIRST_TEN = [
    (1, 2), (3, 1), (2, 6), (5, 4), (1, 18),
    (3, 17), (7, 14), (15, 7), (8, 30), (17, 22),
]


# ---------------------------------------------------------------------------
# BMO#1: (a, b) recurrence, question: does a_n = b_n ever hold?
# ---------------------------------------------------------------------------

def _bmo1_iter():
    a, b = 1, 2
    yield a, b
    while True:
        a, b = (a - b, 4 * b + 2) if b <= a else (2 * a + 1, b - a)
        yield a, b


def bmo1_sequence(count):
    """First ``count`` (a, b) pairs and the first equality index, if any."""
    pairs = list(itertools.islice(_bmo1_iter(), count))
    equality = next((i + 1 for i, (a, b) in enumerate(pairs) if a == b), None)
    return pairs, equality


def bmo1_no_equality(iterations):
    """Whether the recurrence avoids a = b in its first ``iterations`` values."""
    for index, (a, b) in enumerate(itertools.islice(_bmo1_iter(), 1, iterations + 1), start=1):
        if a == b:
            return index
    return None


# ---------------------------------------------------------------------------
# BMO#2 Antihydra: a_0 = 8, a_{n+1} = 3 a_n / 2; b counts +2 on even, -1 on odd
# ---------------------------------------------------------------------------

def antihydra(iterations):
    a, b = 8, 0
    min_b, n_at_min = 0, 0
    for n in range(iterations):
        b = b + 2 if a % 2 == 0 else b - 1
        if b < min_b:
            min_b, n_at_min = b, n + 1
        a = (3 * a) // 2
    return {"steps": iterations, "min_b": min_b, "n_at_min": n_at_min}


# ---------------------------------------------------------------------------
# BMO#3: a_0 = 2, a_{n+1} = a_n + 2^(v2(a_n)+2) - 1; never a power of 4?
# ---------------------------------------------------------------------------

def _v2(n):
    return (n & -n).bit_length() - 1


def _is_power_of_four(n):
    return n >= 4 and (n & (n - 1)) == 0 and (n.bit_length() - 1) % 2 == 0


def bmo3_sequence(count):
    values = [2]
    hit = None
    for _ in range(count - 1):
        a = values[-1]
        nxt = a + (1 << (_v2(a) + 2)) - 1
        values.append(nxt)
        if _is_power_of_four(nxt):
            hit = len(values) - 1
            break
    return values, hit


# ---------------------------------------------------------------------------
# BMO#4: a_0 = 2, recurrence by a_n mod 3; closed form (3*2^n + c(n))/5
# ---------------------------------------------------------------------------

def bmo4_sequence(count):
    """Values a_0..a_{count-1}; index of the first a_n % 3 == 1, if any."""
    values = [2]
    one = None
    for n in range(count - 1):
        a = values[-1]
        if a % 3 == 1:
            one = len(values) - 1
            break
        if a % 3 == 0:
            values.append(a // 3 + 2 ** n + 1)
        else:
            values.append((a - 2 if a >= 2 else 0) // 3 + 2 ** n - 1)
    if one is None and values[-1] % 3 == 1:
        one = len(values) - 1
    return values, one


def bmo4_closed_form(n):
    c = (7, -6, 3, 6)[n % 4]
    numerator = 3 * 2 ** n + c
    assert numerator % 5 == 0
    return numerator // 5


# ---------------------------------------------------------------------------
# BMO#5: (a, b) with f(x) = 10*2^x - 1; question: b_i = f(a_i) - 1 ever?
# ---------------------------------------------------------------------------

def _bmo5_iter(iterations):
    a, b = 0, 5
    for _ in range(iterations + 1):
        yield a, b
        f = 10 * 2 ** a - 1
        a, b = (a + 1, b - f) if f <= b else (a, 3 * b + a + 5)


def bmo5_hit(iterations):
    for index, (a, b) in enumerate(_bmo5_iter(iterations)):
        if b == 10 * 2 ** a - 2:
            return index
    return None


# ---------------------------------------------------------------------------
# BMO#8: (a, b) over the integers; question: a_i = floor(b_i/2) + 1 ever?
# ---------------------------------------------------------------------------

def _bmo8_iter(iterations):
    a, b = 10, 12
    for _ in range(iterations + 1):
        yield a, b
        half = b // 2  # floor division, matching Int division for divisor 2
        a, b = (
            (a - half - 3, 3 * ((b + 1) // 2) + 6)
            if half < a
            else (3 * a + 5, b - 2 * a)
        )


def bmo8_hit(iterations):
    for index, (a, b) in enumerate(_bmo8_iter(iterations)):
        if a == b // 2 + 1:
            return index
    return None


# ---------------------------------------------------------------------------
# OEIS A34693: smallest k with k*n + 1 prime; sweep and exact bound checks
# ---------------------------------------------------------------------------

def _is_prime(n):
    """Deterministic Miller-Rabin for n < 3.3 * 10^24."""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def smallest_k_prime(n, cap=100_000):
    """Smallest k with n*k + 1 prime; None when none found below ``cap``."""
    for k in range(1, cap + 1):
        if _is_prime(n * k + 1):
            return k
    return None


def smallest_k_prime_sweep(nmax, cap=100_000):
    """Sweep n = 2..nmax for the A34693 conjectures (exact integer checks).

    A search that finds no k below ``cap`` is recorded as ``not_found`` -- a
    bounded search miss, NOT a violation of either conjecture.
    """
    checked = 0
    max_k, max_k_n = 0, 0
    not_found = []
    violation_k_lt_n = None
    violation_three_quarter = None
    for n in range(2, nmax + 1):
        k = smallest_k_prime(n, cap=cap)
        if k is None:
            not_found.append(n)
            continue
        checked += 1
        if k > max_k:
            max_k, max_k_n = k, n
        if not k < n:
            violation_k_lt_n = violation_k_lt_n or n
        # k < 1 + n^(3/4) holds exactly when (k-1)^4 < n^3 (k >= 1).
        if not (k - 1) ** 4 < n ** 3:
            violation_three_quarter = violation_three_quarter or n
    return {
        "checked": checked,
        "max_k": max_k,
        "max_k_n": max_k_n,
        "not_found": not_found[:8],
        "violation_k_lt_n": violation_k_lt_n,
        "violation_three_quarter": violation_three_quarter,
    }


# ---------------------------------------------------------------------------
# Machine probe (this repository's simulator)
# ---------------------------------------------------------------------------

def machine_probe(machine_text, steps):
    try:
        machine = parse_machine(machine_text)
    except MachineError as exc:
        return {"error": str(exc)}
    result = run_machine(machine, steps)
    return {"halts": result.halts, "steps": result.steps, "score": result.score}


def _fmt(value):
    return "none" if value is None else str(value)


def report(small_iterations=10_000, big_iterations=1_000_000, sweep=10_000,
           machine_steps=2_000_000, antihydra_iterations=100_000):
    lines = ["# bounded probe of formal-conjectures shortlist candidates"]
    lines.append(f"# bounds: small_iterations={small_iterations} big_iterations={big_iterations} "
                 f"sweep={sweep} machine_steps={machine_steps} "
                 f"antihydra_iterations={antihydra_iterations}")

    pairs, _ = bmo1_sequence(10)
    lines.append(f"bmo1.first_ten_ok={str(pairs == BMO1_FIRST_TEN).lower()}")
    lines.append(f"bmo1.equality_index={_fmt(bmo1_no_equality(big_iterations))}")
    lines.append(f"bmo1.iterations={big_iterations}")
    probe = machine_probe(BMO1_MACHINE, machine_steps)
    lines.append(f"bmo1.machine.halts={probe['halts']} steps={probe['steps']} score={probe['score']}")

    stats = antihydra(antihydra_iterations)
    lines.append(f"bmo2.min_b={stats['min_b']} at n={stats['n_at_min']}")
    lines.append(f"bmo2.iterations={antihydra_iterations}")
    probe = machine_probe(BMO2_MACHINE, machine_steps)
    lines.append(f"bmo2.machine.halts={probe['halts']} steps={probe['steps']} score={probe['score']}")

    _, hit = bmo3_sequence(small_iterations)
    lines.append(f"bmo3.power_of_four_hit={_fmt(hit)}")
    lines.append(f"bmo3.iterations={small_iterations}")

    values, one = bmo4_sequence(small_iterations)
    closed_form_ok = all(value == bmo4_closed_form(n) for n, value in enumerate(values))
    lines.append(f"bmo4.closed_form_ok={str(closed_form_ok).lower()}")
    lines.append(f"bmo4.mod3_one_hit={_fmt(one)}")
    lines.append(f"bmo4.iterations={small_iterations}")

    lines.append(f"bmo5.hit={_fmt(bmo5_hit(small_iterations))}")
    lines.append(f"bmo5.iterations={small_iterations}")
    probe = machine_probe(BMO5_MACHINE, machine_steps)
    lines.append(f"bmo5.machine.halts={probe['halts']} steps={probe['steps']} score={probe['score']}")

    lines.append(f"bmo8.hit={_fmt(bmo8_hit(small_iterations))}")
    lines.append(f"bmo8.iterations={small_iterations}")
    probe = machine_probe(BMO8_MACHINE, machine_steps)
    lines.append(f"bmo8.machine.halts={probe['halts']} steps={probe['steps']} score={probe['score']}")
    lines.append("# bmo3/bmo4 machines are 5-symbol; bemyself.turing supports the 2-symbol notation only")

    stats = smallest_k_prime_sweep(sweep)
    lines.append(f"a34693.sweep=2..{sweep} checked={stats['checked']} "
                 f"max_k={stats['max_k']} at n={stats['max_k_n']}")
    lines.append(f"a34693.not_found={_fmt(stats['not_found'] or None)}")
    lines.append(f"a34693.violation_k_lt_n={_fmt(stats['violation_k_lt_n'])}")
    lines.append(f"a34693.violation_three_quarter={_fmt(stats['violation_three_quarter'])}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--small-iterations", type=int, default=10_000)
    parser.add_argument("--big-iterations", type=int, default=1_000_000)
    parser.add_argument("--antihydra-iterations", type=int, default=100_000)
    parser.add_argument("--sweep", type=int, default=10_000)
    parser.add_argument("--machine-steps", type=int, default=2_000_000)
    args = parser.parse_args(argv)
    sys.stdout.write(report(
        small_iterations=args.small_iterations,
        big_iterations=args.big_iterations,
        sweep=args.sweep,
        machine_steps=args.machine_steps,
        antihydra_iterations=args.antihydra_iterations,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

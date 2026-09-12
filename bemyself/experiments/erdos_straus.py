"""Erdős–Straus witnesses for every ``n`` up to a limit: a finite,
exhaustive computation -- and no proof of the conjecture.

The Erdős–Straus conjecture says that every integer ``n >= 2`` admits
positive integers ``a, b, c`` with ``4/n = 1/a + 1/b + 1/c``. The conjecture
is open; this module does not prove it. It recomputes, for every ``n`` up to
a caller-given limit, one witness and prints it. "Every n <= N has a
witness" is finite, deterministic and recheckable; it says nothing about
n > N, and it does not prove the conjecture.

Canonical witness order: the lexicographically smallest triple ``(a, b, c)``
in the natural order of integers. The search is exhaustive per ``n``:

* ``a`` runs over ``floor(n/4) + 1 .. floor(3n/4)``. A solution, sorted, has
  its smallest component in that window: ``1/a < 4/n`` because the remaining
  sum is positive and ``4/n <= 3/a`` because the component is the smallest.
  So the lexicographically smallest witness has its ``a`` in the window.
* For a fixed ``a``, write ``p/q = (4a - n)/(n a)``, reduced by
  ``g = gcd(4a - n, n a)``. ``1/b + 1/c = p/q`` has a solution exactly when
  a divisor ``X`` of ``q^2`` satisfies ``X == -q (mod p)``; then
  ``b = (X + q)/p`` and ``c = (q^2/X + q)/p``, because
  ``(pb - q)(pc - q) = q^2``. The smallest such ``X`` gives the smallest
  ``b``, hence the canonical triple.

If a window leaves an ``n`` without a witness, the run says so: the ``n``
appears as ``gap n`` where the witness line would be, the final line is
``gaps <N> <found> <missing>`` and the exit code is non-zero. No ``n`` is
skipped silently, and no witness is invented.

Output on stdout (deterministic: no randomness, no network, no stdin): one
line ``n a b c`` per ``n`` from 2 to N in ascending order, then either
``ok <N> <count>`` (``count`` = number of witnesses = ``N - 1``) or
``gaps <N> <found> <missing>``.

Exit codes: ``0`` complete run (every ``n`` has a witness), ``1`` at least
one gap, ``2`` usage error.

Runtime is empirical, not bounded: ``N = 100_000`` prints in about a second
and ``N = 1_000_000`` in about fifteen seconds on the development machine
(CPython, single process, stdlib only).
"""

from __future__ import annotations

import sys
from math import gcd


def smallest_prime_factors(limit):
    """Smallest-prime-factor table for values ``0 .. limit``.

    Enough to factor any value ``<= limit`` via :func:`_factor`; the search
    for ``n`` needs values up to ``2 * n``.
    """
    if limit < 2:
        raise ValueError("limit must be >= 2")
    table = list(range(limit + 1))
    candidate = 2
    while candidate * candidate <= limit:
        if table[candidate] == candidate:
            for multiple in range(candidate * candidate, limit + 1, candidate):
                if table[multiple] == multiple:
                    table[multiple] = candidate
        candidate += 1
    return table


def _factor(value, spf):
    """Prime factorization of ``value`` using the smallest-prime-factor table."""
    factors = []
    while value > 1:
        prime = spf[value]
        exponent = 0
        while value % prime == 0:
            value //= prime
            exponent += 1
        factors.append((prime, exponent))
    return factors


def _divisors_sorted(groups):
    """All divisors of ``prod(p ** (2e))`` for groups ``(p, [p^0..p^2e])``."""
    divisors = [1]
    for _, powers in groups:
        divisors = [divisor * power for divisor in divisors for power in powers]
    divisors.sort()
    return divisors


def witness(n, spf, a_limit=None):
    """The lexicographically smallest witness for ``n``, or ``None``.

    ``spf`` is a table from :func:`smallest_prime_factors` covering values up
    to ``2 * n``. ``a_limit`` caps the search window; it is used to exercise
    the gap path and never widens the window.
    """
    a_max = 3 * n // 4
    if a_limit is not None and a_limit < a_max:
        a_max = a_limit
    for a in range(n // 4 + 1, a_max + 1):
        d = 4 * a - n
        q = n * a
        g = gcd(d, q)
        p = d // g
        reduced = q // g
        if p == 1:
            # The remainder is 1/q: X = 1 gives b = q + 1, c = q(q + 1).
            return (a, reduced + 1, reduced * (reduced + 1))
        target = (-reduced) % p
        if target == 1:
            # X = 1 is the smallest divisor; b = (1 + q)/p.
            return (a, (1 + reduced) // p, (reduced * reduced + reduced) // p)
        exponents = {}
        for prime, exponent in _factor(n, spf):
            exponents[prime] = exponents.get(prime, 0) + exponent
        for prime, exponent in _factor(a, spf):
            exponents[prime] = exponents.get(prime, 0) + exponent
        for prime, exponent in _factor(g, spf):
            exponents[prime] -= exponent
        groups = []
        for prime in sorted(exponents):
            exponent = exponents[prime]
            if exponent > 0:
                groups.append((prime, [prime ** k for k in range(2 * exponent + 1)]))
        for candidate in _divisors_sorted(groups):
            if candidate % p == target:
                return (
                    a,
                    (candidate + reduced) // p,
                    (reduced * reduced // candidate + reduced) // p,
                )
    return None


def run(limit, out, spf=None, a_limit=None):
    """Write the canonical lines for ``n = 2 .. limit`` to ``out``.

    Returns ``0`` when every ``n`` found a witness, ``1`` when at least one
    gap was printed. ``spf`` may be reused across calls and must cover values
    up to ``2 * limit``; ``a_limit`` caps the per-``n`` search window.
    """
    if spf is None:
        spf = smallest_prime_factors(2 * limit)
    found = 0
    missing = 0
    for n in range(2, limit + 1):
        triple = witness(n, spf, a_limit=a_limit)
        if triple is None:
            missing += 1
            out.write(f"gap {n}\n")
        else:
            found += 1
            out.write(f"{n} {triple[0]} {triple[1]} {triple[2]}\n")
    if missing:
        out.write(f"gaps {limit} {found} {missing}\n")
        return 1
    out.write(f"ok {limit} {found}\n")
    return 0


def main(argv=None):
    """CLI: ``python3 -m bemyself.experiments.erdos_straus <N>``."""
    args = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: python3 -m bemyself.experiments.erdos_straus <N>"
    if len(args) != 1 or not (args[0].isascii() and args[0].isdigit()):
        print(usage, file=sys.stderr)
        return 2
    limit = int(args[0])
    if limit < 2:
        print(f"{usage}: limit must be >= 2, got {limit}", file=sys.stderr)
        return 2
    return run(limit, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())

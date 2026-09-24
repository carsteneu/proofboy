"""The V1 library of the notation: exact integer functions with guards.

The library is the checkable fragment of mathematics (05-02 §2): exact
integers, deterministic functions, and one documented guard limit per
function. A guard violation raises :class:`GuardError` -- it never becomes a
silent approximation; the witness runner turns it into UNVERIFIABLE. The ten
two-character aliases of 05-07 §5 resolve to the same callables.
"""

from __future__ import annotations

from math import comb, gcd as _math_gcd

# The default guard of the divisibility family, spelled out in 05-02 §2.
_LIMIT = 10**12


class GuardError(ValueError):
    """A library argument beyond its documented guard: no silent approximation."""


def _as_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise GuardError(f"{name} must be an integer, not {type(value).__name__}")
    return value


def isprime(n):
    """Primality by deterministic Miller-Rabin; guard n <= 10^12."""
    n = _as_int(n, "n")
    if n > _LIMIT:
        raise GuardError(f"isprime: n = {n} exceeds the guard of {_LIMIT}")
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    # Fixed bases are deterministic for n < 3.3 * 10^24, far beyond the guard.
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def powmod(a, b, m):
    """Modular power; guards b <= 10^12, m <= 10^12, b >= 0, m >= 1."""
    a = _as_int(a, "a")
    b = _as_int(b, "b")
    m = _as_int(m, "m")
    if b > _LIMIT:
        raise GuardError(f"powmod: b = {b} exceeds the guard of {_LIMIT}")
    if m > _LIMIT:
        raise GuardError(f"powmod: m = {m} exceeds the guard of {_LIMIT}")
    if b < 0:
        raise GuardError("powmod: b must be non-negative")
    if m < 1:
        raise GuardError("powmod: m must be at least 1")
    return pow(a, b, m)


def gcd(a, b):
    """Greatest common divisor; guards |a|, |b| <= 10^12."""
    a = _as_int(a, "a")
    b = _as_int(b, "b")
    if abs(a) > _LIMIT or abs(b) > _LIMIT:
        raise GuardError(f"gcd: |a| or |b| exceeds the guard of {_LIMIT}")
    return _math_gcd(a, b)


def divides(a, b):
    """Whether a divides b; guards |a|, |b| <= 10^12 and a != 0."""
    a = _as_int(a, "a")
    b = _as_int(b, "b")
    if abs(a) > _LIMIT or abs(b) > _LIMIT:
        raise GuardError(f"divides: |a| or |b| exceeds the guard of {_LIMIT}")
    if a == 0:
        raise GuardError("divides: a must not be 0")
    return b % a == 0


def divisors(n):
    """The sorted divisors of n; guard 1 <= n <= 10^12."""
    n = _as_int(n, "n")
    if n > _LIMIT:
        raise GuardError(f"divisors: n = {n} exceeds the guard of {_LIMIT}")
    if n < 1:
        raise GuardError("divisors: n must be at least 1")
    found = []
    i = 1
    while i * i <= n:
        if n % i == 0:
            found.append(i)
            if i != n // i:
                found.append(n // i)
        i += 1
    found.sort()
    return found


def factorial(n):
    """n! ; guards 0 <= n <= 10^4."""
    n = _as_int(n, "n")
    if n < 0 or n > 10**4:
        raise GuardError("factorial: n must be in 0..10^4")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def choose(n, k):
    """Binomial coefficient; guards 0 <= k <= n <= 10^4."""
    n = _as_int(n, "n")
    k = _as_int(k, "k")
    if n < 0 or n > 10**4 or k < 0 or k > n:
        raise GuardError("choose: need 0 <= k <= n <= 10^4")
    return comb(n, k)


def fib(n):
    """The n-th Fibonacci number; guards 0 <= n <= 10^6."""
    n = _as_int(n, "n")
    if n < 0 or n > 10**6:
        raise GuardError("fib: n must be in 0..10^6")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def collatz_steps(n):
    """Steps until 1; guards 1 <= n <= 10^7."""
    n = _as_int(n, "n")
    if n < 1 or n > 10**7:
        raise GuardError("collatz_steps: n must be in 1..10^7")
    steps = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        steps += 1
    return steps


def collatz_max(n):
    """The maximum of the orbit until 1; guards 1 <= n <= 10^7."""
    n = _as_int(n, "n")
    if n < 1 or n > 10**7:
        raise GuardError("collatz_max: n must be in 1..10^7")
    peak = n
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        if n > peak:
            peak = n
    return peak


# The canonical names of the V1 library.
LIBRARY = {
    "isprime": isprime,
    "powmod": powmod,
    "gcd": gcd,
    "divides": divides,
    "divisors": divisors,
    "factorial": factorial,
    "choose": choose,
    "fib": fib,
    "collatz_steps": collatz_steps,
    "collatz_max": collatz_max,
}

# The ten two-character aliases of 05-07 §5 (each measured as one token).
ALIASES = {
    "ip": "isprime",
    "st": "collatz_steps",
    "mx": "collatz_max",
    "pm": "powmod",
    "gc": "gcd",
    "dv": "divisors",
    "di": "divides",
    "fc": "factorial",
    "ch": "choose",
    "fb": "fib",
}

# Every name a formula may call: long form and alias, each to the same callable.
RESOLVED = dict(LIBRARY)
RESOLVED.update({alias: LIBRARY[canonical] for alias, canonical in ALIASES.items()})

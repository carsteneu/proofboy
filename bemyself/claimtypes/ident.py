"""The ``[IDENT: n=<affine> ; a=<affine>, b=<affine>, c=<affine>]`` claim
type: a parameterized identity as an exact rational function of t.

An IDENT claim asserts that ``4/n(t) = 1/a(t) + 1/b(t) + 1/c(t)`` holds for
every integer t in the declared range, where n, a, b and c are affine
functions of the parameter t with integer coefficients, and the range is
``t >= <bound>`` with a non-negative integer bound (default 1). The check is
exact: both sides are expanded as rational functions in t, their difference
is formed, and its numerator -- a polynomial in t -- must be identically
zero. In addition the range conditions must provably hold for every t >=
bound: the denominators a, b, c are positive and n >= 2. A range that is not
soundly covered (a zero in the parameter range, a negative slope, a bound
that exposes n < 2) makes the claim UNVERIFIABLE -- the checker never assumes
a condition it cannot show.

What a CONFIRMED verdict says: the identity is a true statement about the
parameter, so the arithmetic progression n(t) is covered by this explicit
witness for every parameter -- all of it, unlike the finite window of a
[SEARCHED] run. What it does NOT say: the conjecture is not proven. One
progression is covered; the conjecture needs every n >= 2, and the covered
progression is one proper subset of them. The proof sentence names that
boundary explicitly, and the type must never be readable as a proof of the
conjecture.

Verdicts: CONFIRMED when the numerator is identically zero and every range
condition provably holds for all t >= bound; REFUTED when the difference of
the two sides is not the zero rational function (the numerator, a nonzero
polynomial, is the witness -- a nonzero numerator has finitely many roots, so
the identity fails for infinitely many t of any unbounded range); UNVERIFIABLE
when the marker does not have the documented shape, an expression is not
affine in t (no quadratic or fractional terms, no other parameter, no
internal whitespace), a number exceeds the interpreter's integer conversion,
or the declared range is not soundly covered.

Cost: a handful of polynomial multiplications of degree <= 3, in this
process -- no repository, no subprocess, no network, nothing to sandbox.
"""

from __future__ import annotations

import re
from fractions import Fraction

from bemyself.model import Cause, ClaimType, Result, Verdict

# The lower bound of the parameter range without a "t >= <bound>" clause.
DEFAULT_BOUND = 1

# One lazy "anything but a bracket" capture per marker, the sections split
# out afterwards; the pattern stays linear (see bemyself/claimtypes/halt.py
# for the reasoning).
_IDENT_RE = re.compile(r"\[IDENT:(?P<body>[^\]\[]*?)\]")

# An affine expression in t: an optional signed integer coefficient of the
# parameter (default 1), optionally followed by a signed integer offset.
# ASCII digits only, no whitespace inside the expression, no other letters.
_T_TERM_RE = re.compile(r"\A(?P<coef>[+-]?[0-9]*)t(?P<offset>[+-][0-9]+)?\Z")
_CONSTANT_RE = re.compile(r"\A[+-]?[0-9]+\Z")
_RANGE_RE = re.compile(r"\At[ \t]*>=[ \t]*(?P<bound>[0-9]+)\Z")

_SHAPE = (
    "the marker needs the shape n=<affine> ; a=<affine>, b=<affine>, "
    "c=<affine> (optionally ; t >= <bound>)"
)

# A witness coefficient beyond this size (in bits; 4096 bits ~ 1233 decimal
# digits, comfortably below the interpreter's conversion cap) is shown with
# its leading digits only -- see _digits.
_DISPLAY_BITS = 4096
_DISPLAY_DIGITS = 120


def _int_or_none(text):
    """A plain integer, or None when the conversion is refused.

    CPython caps ``int(text)`` at a few thousand digits by default; such a
    number is beyond any use of the claim and must not crash the checker.
    """
    try:
        return int(text)
    except ValueError:
        return None


def _affine(text):
    """The ``(slope, offset)`` of an affine expression in t, or None."""
    text = (text or "").strip()
    match = _T_TERM_RE.match(text)
    if match is not None:
        coef = match.group("coef")
        if coef == "":
            slope = 1
        elif coef == "+":
            slope = 1
        elif coef == "-":
            slope = -1
        else:
            slope = _int_or_none(coef)
            if slope is None:
                return None
        offset_text = match.group("offset")
        if offset_text is None:
            return slope, 0
        offset = _int_or_none(offset_text)
        return None if offset is None else (slope, offset)
    if _CONSTANT_RE.match(text):
        value = _int_or_none(text)
        return None if value is None else (0, value)
    return None


def _format_affine(slope, offset):
    if slope == 0:
        return str(offset)
    if slope == 1:
        head = "t"
    elif slope == -1:
        head = "-t"
    else:
        head = f"{slope}t"
    if offset == 0:
        return head
    return head + ("+" if offset > 0 else "-") + str(abs(offset))


def _poly_mul(left, right):
    out = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        if a:
            for j, b in enumerate(right):
                out[i + j] += a * b
    return out


def _poly_add(left, right):
    out = [0] * max(len(left), len(right))
    for i, value in enumerate(left):
        out[i] += value
    for i, value in enumerate(right):
        out[i] += value
    return out


def _poly_scale(poly, factor):
    return [factor * value for value in poly]


def _difference_numerator(n, a, b, c):
    """The numerator of ``1/a + 1/b + 1/c - 4/n`` over ``a*b*c*n`` in t."""
    pair_sum = _poly_add(_poly_mul(a, b), _poly_add(_poly_mul(a, c), _poly_mul(b, c)))
    return _poly_add(_poly_mul(n, pair_sum), _poly_scale(_poly_mul(_poly_mul(a, b), c), -4))


def _digits(value):
    """Decimal digits of a non-negative int, truncated past a display bound.

    CPython refuses an int-to-string conversion beyond a few thousand digits;
    a witness beyond that is shown as its leading digits plus ``...``. The
    verdict only needs the coefficient to be visibly non-zero.
    """
    if value.bit_length() <= _DISPLAY_BITS:
        return str(value)
    head = value // 10 ** ((value.bit_length() - _DISPLAY_BITS) * 30103 // 100000)
    return str(head)[:_DISPLAY_DIGITS] + "..."


def _format_poly(coeffs):
    terms = []
    for power in range(len(coeffs) - 1, -1, -1):
        coef = coeffs[power]
        if coef == 0:
            continue
        digits = _digits(abs(coef))
        if power == 0:
            body = digits
        elif power == 1:
            body = "t" if digits == "1" else f"{digits}t"
        else:
            body = f"t^{power}" if digits == "1" else f"{digits}t^{power}"
        if not terms:
            terms.append(("-" if coef < 0 else "") + body)
        else:
            terms.append((" - " if coef < 0 else " + ") + body)
    return "".join(terms) if terms else "0"


def _first_violation(slope, offset, bound, threshold):
    """The first integer ``t >= bound`` with ``slope*t + offset <= threshold``.

    None when no such t exists. An affine function is monotone: a positive
    slope violates on a prefix of the range, so the bound itself is the first
    witness whenever it violates at all; a negative slope violates on a
    suffix, and the crossing decides; a zero slope violates everywhere or
    nowhere.
    """
    if slope == 0:
        return (bound, offset) if offset <= threshold else None
    if slope > 0:
        if slope * bound + offset > threshold:
            return None
        return bound, slope * bound + offset
    crossing = Fraction(offset - threshold, -slope)
    first = max(bound, -(-crossing.numerator // crossing.denominator))
    return first, slope * first + offset


def parse(match, raw):
    """Fields of one [IDENT] marker: the body, verbatim.

    Unlike an arrow-less [HALT] marker, a malformed IDENT marker must not
    vanish: the marker is a claim attempt, so it stays a claim and ends
    UNVERIFIABLE in :func:`check` instead of disappearing unnoticed.
    """
    return {"body": match.group("body").strip()}


def check(claim, ctx):
    body = claim.fields.get("body") or ""
    sections = [part.strip() for part in body.split(";")]
    if len(sections) not in (2, 3):
        return Result(
            Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}", cause=Cause.DEFECT
        )

    n_parts = sections[0].split("=")
    if len(n_parts) != 2 or n_parts[0].strip() != "n":
        return Result(
            Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}", cause=Cause.DEFECT
        )
    n = _affine(n_parts[1])
    if n is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claimed n is not affine in t: {n_parts[1].strip()!r}",
            cause=Cause.UNVERIFIABLE,
        )

    pieces = {}
    for item in sections[1].split(","):
        key_parts = item.split("=")
        if len(key_parts) != 2:
            return Result(
                Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}", cause=Cause.DEFECT
            )
        key = key_parts[0].strip()
        if key not in ("a", "b", "c") or key in pieces:
            return Result(
                Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}", cause=Cause.DEFECT
            )
        value = _affine(key_parts[1])
        if value is None:
            return Result(
                Verdict.UNVERIFIABLE,
                reason=f"the claimed {key} is not affine in t: {key_parts[1].strip()!r}",
                cause=Cause.UNVERIFIABLE,
            )
        pieces[key] = value
    if set(pieces) != {"a", "b", "c"}:
        return Result(
            Verdict.UNVERIFIABLE, reason=f"{_SHAPE}: {body!r}", cause=Cause.DEFECT
        )

    bound = DEFAULT_BOUND
    if len(sections) == 3:
        range_match = _RANGE_RE.match(sections[2])
        if range_match is None:
            return Result(
                Verdict.UNVERIFIABLE,
                reason="the range clause needs the shape t >= <non-negative integer>: "
                f"{sections[2]!r}",
                cause=Cause.DEFECT,
            )
        bound = _int_or_none(range_match.group("bound"))
        if bound is None:
            return Result(
                Verdict.UNVERIFIABLE,
                reason=f"the range bound is not usable: {sections[2]!r}",
                cause=Cause.UNVERIFIABLE,
            )

    a_text = _format_affine(*pieces["a"])
    b_text = _format_affine(*pieces["b"])
    c_text = _format_affine(*pieces["c"])
    n_text = _format_affine(*n)
    command = (
        f"expand 1/({a_text}) + 1/({b_text}) + 1/({c_text}) - 4/({n_text}) "
        "as one rational function in t"
    )

    numerator = _difference_numerator(
        [n[1], n[0]],
        [pieces["a"][1], pieces["a"][0]],
        [pieces["b"][1], pieces["b"][0]],
        [pieces["c"][1], pieces["c"][0]],
    )
    if any(numerator):
        return Result(
            Verdict.REFUTED,
            command,
            f"numerator={_format_poly(numerator)}",
            "the two sides differ as rational functions in t: the numerator of "
            f"1/a(t) + 1/b(t) + 1/c(t) - 4/n(t) is {_format_poly(numerator)}, not zero",
        )

    for key in ("a", "b", "c"):
        violation = _first_violation(pieces[key][0], pieces[key][1], bound, 0)
        if violation is not None:
            t, value = violation
            return Result(
                Verdict.UNVERIFIABLE,
                command,
                "numerator=0",
                f"the identity holds, but {key}(t) = {_format_affine(*pieces[key])} is not "
                f"positive for every t >= {bound}: at t = {t} it is {value}; the declared "
                "range is not soundly covered",
                # An unsound range is a boundary of what the checker can show,
                # not a defective report ("P12" design).
                cause=Cause.UNVERIFIABLE,
            )
    violation = _first_violation(n[0], n[1], bound, 1)
    if violation is not None:
        # Subsumed by the checks above: a zero numerator gives
        # n = 4abc/(ab+ac+bc), and positive a, b, c give ab+ac+bc <= 3abc,
        # so n >= 4/3, hence n >= 2. The guard stays as a cheap invariant on
        # the CONFIRMED path -- a future loosening of the denominator checks
        # must not silently lose it.
        t, value = violation
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            "numerator=0",
            f"the identity holds, but n(t) = {n_text} is below 2 for t = {t} "
            f"(it is {value}); the declared range is not soundly covered",
            cause=Cause.UNVERIFIABLE,
        )

    return Result(
        Verdict.CONFIRMED,
        command,
        "numerator=0",
        (
            "4/n(t) = 1/a(t) + 1/b(t) + 1/c(t) holds as a rational identity in t "
            "for every t >= {bound} with n = {n}, a = {a}, b = {b}, c = {c}; every "
            "integer t >= {bound} has n >= 2 and positive denominators, so the "
            "progression n = {n} is covered for every parameter -- one progression, "
            "not all of them: this is not a proof of the conjecture"
        ).format(bound=bound, n=n_text, a=a_text, b=b_text, c=c_text),
    )


IDENT = ClaimType(kind="ident", pattern=_IDENT_RE, parse=parse, check=check)

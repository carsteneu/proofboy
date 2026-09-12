"""The V1 formula fragment of the notation: parser and evaluator.

Deliberately small, fully parenthesized, exact (05-02 §2/§3): terms evaluate
to int or Fraction, formulas to bool. A free variable is never guessed, a
guard violation of the library propagates, and a top-level finite quantifier
over an empty range raises :class:`EmptyRangeError` -- the runner turns that
into UNVERIFIABLE/empty_range (no vacuous confirmations). Unbounded
quantifiers (``Z``/``N``/``Q``) raise :class:`UnboundedError`; the ``**``
synonym of ``^`` is the only tolerated surface variant (measured as one token,
01-03b).

Grammar (EBNF per 05-02 §3, metasprachlich)::

    term   = number | name | "-" term | "(" term op term ")" | "(" "-" term ")"
           | name "(" [term {"," term}] ")"
           | ("sum"|"prod") "(" name "=" range "," term ")"
           | "(" ("forall"|"exists") name "in" (range|set) ":" formula ")"
    range  = (number | name) ".." (number | name)
    set    = "{" term {"," term} "}" | "Z" | "N" | "Q"
    op     = "+" | "-" | "*" | "/" | "//" | "%" | "^"
    formula= term | "(" formula op formula ")" | "(" "!" formula ")"
           | "(" formula op_vgl term ")"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping

from bemyself.msheet.library import RESOLVED, GuardError

# The largest exponent a power may carry, and the largest number of elements a
# range may iterate: guards against computational bombs, not approximations.
POWER_GUARD = 10**6
RANGE_GUARD = 10**7
# The deepest chain of user-definition calls.
CALL_GUARD = 100


class FormulaError(ValueError):
    """The text is not a formula of the fragment (syntax, unknown name)."""


class EvaluationError(ValueError):
    """A formula that parses but cannot be evaluated as written."""


class UnboundedError(EvaluationError):
    """A quantifier over Z, N or Q: not executable on this machine."""


class EmptyRangeError(EvaluationError):
    """A top-level quantifier over an empty range: no vacuous confirmation."""


class NotAFormula(EvaluationError):
    """The evaluated expression is not a formula (no bool result)."""


@dataclass(frozen=True)
class Def:
    """A local definition ``def name(params...) = term``."""

    name: str
    params: tuple[str, ...]
    node: object


@dataclass(frozen=True)
class Formula:
    """A parsed formula, with the local definitions it may call."""

    text: str
    node: object
    defs: Mapping[str, "Def"]


# Reserved words (05-02 §3) plus the library names: neither may be a def name
# or a parameter (no shadowing).
_RESERVED = {
    "goal", "def", "S", "CLAIM", "WITNESS", "HALT", "calc", "forall", "exists",
    "sum", "prod", "in", "Z", "N", "Q", "auto", "py", "range", "True", "False",
} | set(RESOLVED)

_NUMBER_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_IDENT_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")
_NUMBER_PARTS_RE = re.compile(r"\A([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?\Z")

_BINOPS = {
    "+", "-", "*", "/", "//", "%", "^", "**",
    "=", "!=", "<", "<=", ">", ">=",
    "&", "|", "->", "<->",
}


def _number_value(text):
    match = _NUMBER_PARTS_RE.match(text)
    intpart, frac, exp = match.groups()
    exponent = int(exp) if exp else 0
    if frac:
        value = Fraction(int(intpart + frac), 10 ** len(frac))
    else:
        value = int(intpart)
    if exponent > 0:
        return value * 10**exponent
    if exponent < 0:
        return value / Fraction(10 ** (-exponent))
    return value


def _tokenize(text):
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch.isdigit():
            match = _NUMBER_RE.match(text, i)
            tokens.append(("num", match.group(0)))
            i = match.end()
            continue
        if ch.isalpha():
            match = _IDENT_RE.match(text, i)
            tokens.append(("name", match.group(0)))
            i = match.end()
            continue
        if text.startswith("<->", i):
            tokens.append(("<->", "<->"))
            i += 3
            continue
        if text.startswith("//", i) or text.startswith("**", i) or text.startswith("..", i) \
                or text.startswith("->", i) or text.startswith("<=", i) or text.startswith(">=", i) \
                or text.startswith("!=", i):
            tokens.append((text[i : i + 2], text[i : i + 2]))
            i += 2
            continue
        if ch in "(){}:,-+*/%^=<>!&|":
            tokens.append((ch, ch))
            i += 1
            continue
        raise FormulaError(f"unexpected character {ch!r} at position {i}")
    return tokens


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else ("eof", "eof")

    def next(self):
        token = self.peek()
        self.pos += 1
        return token

    def expect(self, kind):
        token = self.next()
        if token[0] != kind:
            raise FormulaError(f"expected {kind!r}, found {token[1]!r}")
        return token

    def parse_expr(self):
        kind, value = self.peek()
        if kind == "num":
            self.next()
            return ("num", _number_value(value))
        if kind == "-":
            self.next()
            return ("neg", self.parse_expr())
        if kind == "name":
            if value in ("sum", "prod") and self.tokens[self.pos + 1 : self.pos + 2] == [("(", "(")]:
                return self.parse_binder(value)
            self.next()
            if self.peek()[0] == "(":
                self.next()
                args = []
                if self.peek()[0] != ")":
                    args.append(self.parse_expr())
                    while self.peek()[0] == ",":
                        self.next()
                        args.append(self.parse_expr())
                self.expect(")")
                return ("call", value, tuple(args))
            return ("name", value)
        if kind == "(":
            return self.parse_paren()
        raise FormulaError(f"unexpected token {value!r}")

    def parse_paren(self):
        self.expect("(")
        kind, value = self.peek()
        if kind == "name" and value in ("forall", "exists"):
            self.next()
            var = self.expect("name")[1]
            self.expect("name")  # "in"
            if self.peek()[0] == "{":
                domain = self.parse_set()
            elif self.peek()[0] == "name" and self.peek()[1] in ("Z", "N", "Q"):
                domain = ("uset", self.next()[1])
            else:
                domain = self.parse_range()
            self.expect(":")
            body = self.parse_expr()
            self.expect(")")
            return (value, var, domain, body)
        if kind == "!":
            self.next()
            body = self.parse_expr()
            self.expect(")")
            return ("not", body)
        first = self.parse_expr()
        kind, value = self.peek()
        if kind in _BINOPS:
            self.next()
            second = self.parse_expr()
            self.expect(")")
            return (kind, first, second)
        if kind == ")":
            self.next()
            return ("paren", first)
        raise FormulaError(f"expected an operator or ')', found {value!r}")

    def parse_range(self):
        endpoints = []
        for _ in range(2):
            kind, value = self.peek()
            if kind == "num":
                self.next()
                endpoints.append(("num", _number_value(value)))
            elif kind == "name":
                self.next()
                endpoints.append(("name", value))
            else:
                raise FormulaError(f"expected a range endpoint, found {value!r}")
            if len(endpoints) == 1:
                self.expect("..")
        return ("range", endpoints[0], endpoints[1])

    def parse_set(self):
        self.expect("{")
        items = [self.parse_expr()]
        while self.peek()[0] == ",":
            self.next()
            items.append(self.parse_expr())
        self.expect("}")
        return ("set", tuple(items))

    def parse_binder(self, which):
        self.next()  # sum / prod
        self.expect("(")
        var = self.expect("name")[1]
        self.expect("=")
        range_node = self.parse_range()
        self.expect(",")
        body = self.parse_expr()
        self.expect(")")
        return (which, var, range_node, body)


def parse_formula(text, defs=None):
    """Parse one formula of the fragment; raises :class:`FormulaError`."""
    parser = _Parser(_tokenize(text))
    node = parser.parse_expr()
    if parser.peek()[0] != "eof":
        raise FormulaError(f"trailing text after the formula: {parser.peek()[1]!r}")
    return Formula(text, node, dict(defs) if defs else {})


def parse_def(text):
    """Parse one ``def name(params) = term`` line; raises :class:`FormulaError`."""
    parser = _Parser(_tokenize(text))
    head = parser.expect("name")
    if head[1] != "def":
        raise FormulaError(f"expected 'def', found {head[1]!r}")
    name = parser.expect("name")[1]
    if name in _RESERVED:
        raise FormulaError(f"reserved word as definition name: {name!r}")
    params = []
    parser.expect("(")
    if parser.peek()[0] != ")":
        params.append(parser.expect("name")[1])
        while parser.peek()[0] == ",":
            parser.next()
            params.append(parser.expect("name")[1])
    parser.expect(")")
    for param in params:
        if param in _RESERVED:
            raise FormulaError(f"reserved word as parameter name: {param!r}")
        if param in (name,):
            raise FormulaError(f"parameter {param!r} shadows the definition")
    parser.expect("=")
    node = parser.parse_expr()
    if parser.peek()[0] != "eof":
        raise FormulaError(f"trailing text after the definition: {parser.peek()[1]!r}")
    return Def(name, tuple(params), node)


class _Evaluator:
    def __init__(self, env, defs):
        self.env = env
        self.defs = defs or {}

    def eval(self, node, top_level=False, local=None, depth=0):
        local = local if local is not None else {}
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "name":
            name = node[1]
            if name in local:
                return local[name]
            if name in self.env:
                return self.env[name]
            raise FormulaError(f"free variable {name!r} in a closed formula")
        if kind == "neg":
            return -self.eval(node[1], False, local, depth)
        if kind == "paren":
            return self.eval(node[1], False, local, depth)
        if kind == "call":
            return self._call(node, local, depth)
        if kind in ("sum", "prod"):
            return self._fold(node, local, depth)
        if kind in ("forall", "exists"):
            return self._quantify(node, top_level, local, depth)
        if kind == "not":
            value = self.eval(node[1], False, local, depth)
            if not isinstance(value, bool):
                raise EvaluationError("'!' needs a formula")
            return not value
        if kind in ("&", "|", "->", "<->"):
            return self._logic(kind, node[1], node[2], local, depth)
        if kind in ("+", "-", "*", "/", "//", "%", "^", "**"):
            return self._arith(kind, node[1], node[2], local, depth)
        if kind in ("=", "!=", "<", "<=", ">", ">="):
            return self._compare(kind, node[1], node[2], local, depth)
        raise EvaluationError(f"unknown node kind {kind!r}")

    def _call(self, node, local, depth):
        name = node[1]
        args = [self.eval(arg, False, local, depth) for arg in node[2]]
        definition = self.defs.get(name)
        if definition is not None:
            if depth >= CALL_GUARD:
                raise EvaluationError(f"definition calls nested deeper than {CALL_GUARD}")
            if len(args) != len(definition.params):
                raise EvaluationError(
                    f"definition {name!r} takes {len(definition.params)} arguments, got {len(args)}"
                )
            inner = dict(zip(definition.params, args))
            return self.eval(definition.node, False, inner, depth + 1)
        function = RESOLVED.get(name)
        if function is None:
            raise FormulaError(f"unknown function {name!r}")
        return function(*args)

    def _endpoint(self, node, local):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "name":
            name = node[1]
            if name in local:
                return local[name]
            if name in self.env:
                return self.env[name]
            raise FormulaError(f"free variable {name!r} in a range")
        raise EvaluationError("a range endpoint must be a number or a name")

    def _range_values(self, node, local):
        if node[0] == "range":
            low = self._endpoint(node[1], local)
            high = self._endpoint(node[2], local)
            for value in (low, high):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise EvaluationError("range endpoints must be integers")
            if high < low:
                return []
            if high - low + 1 > RANGE_GUARD:
                raise EvaluationError(
                    f"range of {high - low + 1} elements exceeds the guard of {RANGE_GUARD}"
                )
            return list(range(low, high + 1))
        if node[0] == "set":
            return [self.eval(item, False, local) for item in node[1]]
        raise UnboundedError(
            "a quantifier over Z, N or Q is not executable on this machine (unbounded_claim)"
        )

    def _fold(self, node, local, depth):
        _, var, range_node, body = node
        total = 0 if node[0] == "sum" else 1
        for value in self._range_values(range_node, local):
            inner = dict(local)
            inner[var] = value
            term = self.eval(body, False, inner, depth)
            if isinstance(term, bool) or not isinstance(term, (int, Fraction)):
                raise EvaluationError("sum/prod bodies must be terms")
            total = total + term if node[0] == "sum" else total * term
        return total

    def _quantify(self, node, top_level, local, depth):
        kind, var, domain, body = node
        values = self._range_values(domain, local)
        if not values and top_level:
            raise EmptyRangeError(
                "the main claim quantifies over an empty range (empty_range)"
            )
        for value in values:
            inner = dict(local)
            inner[var] = value
            result = self.eval(body, False, inner, depth)
            if not isinstance(result, bool):
                raise EvaluationError("quantifier bodies must be formulas")
            if kind == "forall" and not result:
                return False
            if kind == "exists" and result:
                return True
        return kind == "forall"

    def _logic(self, kind, left_node, right_node, local, depth):
        left = self.eval(left_node, False, local, depth)
        if not isinstance(left, bool):
            raise EvaluationError("logic operates on formulas")
        if kind == "&":
            return left and self._expect_bool(right_node, local, depth)
        if kind == "|":
            return left or self._expect_bool(right_node, local, depth)
        right = self._expect_bool(right_node, local, depth)
        if kind == "->":
            return (not left) or right
        return left == right

    def _expect_bool(self, node, local, depth):
        value = self.eval(node, False, local, depth)
        if not isinstance(value, bool):
            raise EvaluationError("logic operates on formulas")
        return value

    def _arith(self, kind, left_node, right_node, local, depth):
        a = self.eval(left_node, False, local, depth)
        b = self.eval(right_node, False, local, depth)
        if isinstance(a, bool) or isinstance(b, bool):
            raise EvaluationError(f"{kind} needs terms, not formulas")
        if kind == "+":
            return a + b
        if kind == "-":
            return a - b
        if kind == "*":
            return a * b
        if kind == "/":
            if b == 0:
                raise EvaluationError("division by zero")
            return Fraction(a) / Fraction(b)
        if kind in ("//", "%"):
            if not isinstance(a, int) or not isinstance(b, int):
                raise EvaluationError(f"{kind} needs integers")
            if b == 0:
                raise EvaluationError("division by zero")
            return a // b if kind == "//" else a % b
        # kind in ("^", "**")
        if isinstance(b, int) and not isinstance(b, bool):
            if b > POWER_GUARD:
                raise EvaluationError(f"exponent {b} exceeds the guard of {POWER_GUARD}")
            if isinstance(a, int):
                if b >= 0:
                    return a**b
                if a == 0:
                    raise EvaluationError("zero to a negative power")
                return Fraction(a) ** b
            if isinstance(a, Fraction):
                return a**b
        raise EvaluationError("power needs an integer exponent")

    def _compare(self, kind, left_node, right_node, local, depth):
        a = self.eval(left_node, False, local, depth)
        b = self.eval(right_node, False, local, depth)
        if kind == "=":
            return a == b
        if kind == "!=":
            return a != b
        for value in (a, b):
            if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
                raise EvaluationError("order comparisons need numeric terms")
        if kind == "<":
            return a < b
        if kind == "<=":
            return a <= b
        if kind == ">":
            return a > b
        return a >= b


def evaluate(parsed, env=None, top_level=False):
    """Evaluate a parsed formula; ``top_level`` enables the empty-range error."""
    return _Evaluator(env or {}, parsed.defs).eval(parsed.node, top_level=top_level)


def evaluate_bool(parsed, env=None, top_level=True):
    """Evaluate a parsed formula and require a bool; else :class:`NotAFormula`."""
    value = evaluate(parsed, env=env, top_level=top_level)
    if not isinstance(value, bool):
        raise NotAFormula("the evaluated expression is not a formula (no bool result)")
    return value


__all__ = [
    "CALL_GUARD",
    "Def",
    "EmptyRangeError",
    "EvaluationError",
    "Formula",
    "FormulaError",
    "NotAFormula",
    "POWER_GUARD",
    "RANGE_GUARD",
    "UnboundedError",
    "evaluate",
    "evaluate_bool",
    "parse_def",
    "parse_formula",
    "GuardError",
]

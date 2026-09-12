"""Parser for one sheet of the notation (05-02 §3, 05-07 §§2–3).

A sheet has three parts: the thinking zone (line heads strictly
``<tag><n>:`` with the tags ``g d a c h q =`` and the V1 ``S<n>:`` lines of
arm B), the append-only status register (``h1+``, ``h2-``, ``h3?``,
``h4!``) and the claim zone (``CLAIM``/``WITNESS``/``[HALT]``, strict). The
parser never raises on sheet text: it collects :class:`SheetError` entries --
format errors are a measured quantity of the experiment (metric d), not an
exception.

``c:`` with an empty body opens a numeric-column block (V1 ``calc`` rules);
its continuation lines are layout and join the thinking zone. ``def`` lines
(V1 style or behind ``d:``) define local names; ``a:``/``d:`` lines of the
form ``NAME = <machine>`` bind a machine of the bbchallenge notation for
``sim``/``cyc`` witnesses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bemyself import turing
from bemyself.msheet import formula
from bemyself.msheet.formula import Def, Formula
from bemyself.msheet.witnesses import WitnessError, WitnessSpec, parse_witness

_HEAD_RE = re.compile(
    r"\A(?P<head>S[0-9]+|g[0-9]*|d[0-9]*|a[0-9]*|c[0-9]*|h[0-9]*|q[0-9]*|=[0-9]*):[ ]?(?P<body>.*)\Z"
)
_STATUS_RE = re.compile(r"\A([a-zA-Z=][a-zA-Z0-9]*[0-9])([+\-?!])\Z")
_VLINE_RE = re.compile(r"\Av([0-9]+)?\s+([a-zA-Z=][a-zA-Z0-9]*)\s*:\s*(.+)\Z")
_BINDING_RE = re.compile(r"\A([A-Za-z][A-Za-z0-9_]*)\s*=\s*(\S+)\Z")
_CALC_RE = re.compile(r"\A[+\-*/=]?\s*[0-9][0-9\s]*\Z")
_CLAIM_ID_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9_]*\Z")
_HALT_PREFIX = "[HALT]"


@dataclass(frozen=True)
class SheetError:
    """One format error of a sheet, with its line number."""

    line: int
    message: str

    def __str__(self):
        return f"line {self.line}: {self.message}"


@dataclass(frozen=True)
class ThinkLine:
    """One thinking-zone line: ``tag`` and optional counter plus the body."""

    tag: str
    counter: str | None
    body: str
    line: int

    @property
    def id(self):
        if self.counter is None:
            return None
        return f"{self.tag}{self.counter}"


@dataclass(frozen=True)
class StatusLine:
    """One status register entry (append-only; the last one counts)."""

    target: str
    status: str
    line: int


@dataclass(frozen=True)
class VLine:
    """One v-line: a witness targeting an earlier line or claim."""

    vid: str
    target: str
    witness_text: str
    spec: WitnessSpec | None
    error: str | None
    line: int


@dataclass(frozen=True)
class ClaimLine:
    """One claim of the claim zone."""

    cid: str
    text: str
    formula: Formula | None
    error: str | None
    line: int


@dataclass(frozen=True)
class WitnessLine:
    """One witness line of the claim zone."""

    cid: str
    text: str
    spec: WitnessSpec | None
    error: str | None
    line: int


@dataclass
class Sheet:
    """One parsed sheet: what the runner needs, plus its format errors."""

    defs: dict[str, Def] = field(default_factory=dict)
    goal: str | None = None
    think: list[ThinkLine] = field(default_factory=list)
    statuses: list[StatusLine] = field(default_factory=list)
    vlines: list[VLine] = field(default_factory=list)
    claims: list[ClaimLine] = field(default_factory=list)
    witnesses: list[WitnessLine] = field(default_factory=list)
    halt: list[str] | None = None
    errors: list[SheetError] = field(default_factory=list)
    machines: dict[str, turing.Machine] = field(default_factory=dict)

    def body_of(self, line_id):
        """The body of the line with this id, or None."""
        for think in self.think:
            if think.id == line_id:
                return think.body
        return None

    def witness_for(self, cid):
        for witness in self.witnesses:
            if witness.cid == cid:
                return witness
        return None


def _split_claim(line):
    """(cid, body) of a CLAIM/WITNESS line, or None when malformed."""
    head, sep, rest = line.partition(":")
    parts = head.split()
    if not sep or len(parts) != 2:
        return None
    return parts[1], rest.strip()


def parse_sheet(text):
    """Parse one sheet; never raises, collects :class:`SheetError` entries."""
    sheet = Sheet()
    claim_zone = False
    calc_block = False
    auto_vindex = 0
    seen_vids = set()
    seen_cids = set()
    raw_claims: list[tuple[str, str, int]] = []
    raw_witnesses: list[tuple[str, str, int]] = []

    def error(lineno, message):
        sheet.errors.append(SheetError(lineno, message))

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        # The HALT marker.
        if line == _HALT_PREFIX or line.startswith(_HALT_PREFIX + " "):
            if sheet.halt is not None:
                error(lineno, "a second [HALT] marker; one sheet declares its result once")
                continue
            ids = line[len(_HALT_PREFIX) :].split()
            sheet.halt = ids
            claim_zone = True
            calc_block = False
            continue
        # The claim zone.
        if line.startswith("CLAIM "):
            claim_zone = True
            calc_block = False
            parsed = _split_claim(line)
            if parsed is None:
                error(lineno, "malformed CLAIM line (expected 'CLAIM <id>: <formula>')")
                continue
            cid, body = parsed
            if not _CLAIM_ID_RE.match(cid):
                error(lineno, f"not a claim id: {cid!r}")
                continue
            if cid in seen_cids:
                error(lineno, f"duplicate claim id {cid!r}")
                continue
            seen_cids.add(cid)
            raw_claims.append((cid, body, lineno))
            continue
        if line.startswith("WITNESS "):
            claim_zone = True
            calc_block = False
            parsed = _split_claim(line)
            if parsed is None:
                error(lineno, "malformed WITNESS line (expected 'WITNESS <id>: <witness>')")
                continue
            cid, body = parsed
            raw_witnesses.append((cid, body, lineno))
            continue
        # The thinking zone.
        if calc_block and _CALC_RE.match(line):
            sheet.think.append(ThinkLine("c", None, line, lineno))
            continue
        calc_block = False
        if claim_zone:
            error(lineno, "a thinking line after the claim zone began")
            continue
        status = _STATUS_RE.match(line)
        if status:
            sheet.statuses.append(StatusLine(status.group(1), status.group(2), lineno))
            continue
        vline = _VLINE_RE.match(line)
        if vline or re.match(r"\Av(?:[0-9]+)?\b", line):
            if vline is None:
                error(lineno, "malformed v-line (expected 'v <target>: <witness>')")
                continue
            explicit, target, witness_text = vline.groups()
            if explicit is not None:
                vid = f"v{explicit}"
            else:
                auto_vindex += 1
                vid = f"v{auto_vindex}"
            if vid in seen_vids:
                error(lineno, f"duplicate v-line id {vid!r}")
                continue
            seen_vids.add(vid)
            spec, spec_error = None, None
            try:
                spec = parse_witness(witness_text)
            except WitnessError as exc:
                spec_error = str(exc)
            sheet.vlines.append(VLine(vid, target, witness_text, spec, spec_error, lineno))
            continue
        head = _HEAD_RE.match(line)
        if head:
            head_text = head.group("head")
            body = head.group("body")
            if head_text.startswith("S"):
                tag, counter = "S", head_text[1:]
            else:
                tag = head_text[0]
                counter = head_text[1:] or None
            sheet.think.append(ThinkLine(tag, counter, body, lineno))
            if tag == "c" and body == "":
                calc_block = True
            if tag in ("a", "d"):
                binding = _BINDING_RE.match(body)
                if binding:
                    name, value = binding.groups()
                    try:
                        machine = turing.parse(value)
                    except turing.MachineError:
                        machine = None
                    if machine is not None:
                        if name in sheet.machines:
                            error(lineno, f"machine {name!r} is bound twice")
                        else:
                            sheet.machines[name] = machine
            if tag == "d" and body.startswith("def "):
                try:
                    definition = formula.parse_def(body)
                except formula.FormulaError as exc:
                    error(lineno, f"malformed definition: {exc}")
                else:
                    if definition.name in sheet.defs:
                        error(lineno, f"definition {definition.name!r} is declared twice")
                    else:
                        sheet.defs[definition.name] = definition
            if tag == "g" and sheet.goal is None:
                sheet.goal = body
            continue
        if line.startswith("def "):
            try:
                definition = formula.parse_def(line)
            except formula.FormulaError as exc:
                error(lineno, f"malformed definition: {exc}")
            else:
                if definition.name in sheet.defs:
                    error(lineno, f"definition {definition.name!r} is declared twice")
                else:
                    sheet.defs[definition.name] = definition
            continue
        if line.startswith("goal:"):
            if sheet.goal is None:
                sheet.goal = line[len("goal:") :].strip()
            continue
        error(lineno, f"no valid line head: {line!r}")

    _finish_sheet(sheet, raw_claims, raw_witnesses, error)
    return sheet


def _finish_sheet(sheet, raw_claims, raw_witnesses, error):
    if not raw_claims:
        error(0, "the sheet has no claim zone (no CLAIM line)")
    if sheet.halt is None:
        error(0, "the sheet has no [HALT] marker")
    for cid, body, lineno in raw_claims:
        parsed, parse_error = None, None
        try:
            parsed = formula.parse_formula(body, defs=sheet.defs)
        except formula.FormulaError as exc:
            parse_error = str(exc)
        sheet.claims.append(ClaimLine(cid, body, parsed, parse_error, lineno))
    for cid, body, lineno in raw_witnesses:
        spec, spec_error = None, None
        try:
            spec = parse_witness(body)
        except WitnessError as exc:
            spec_error = str(exc)
        sheet.witnesses.append(WitnessLine(cid, body, spec, spec_error, lineno))
    known = {claim.cid for claim in sheet.claims}
    for witness in sheet.witnesses:
        if witness.cid not in known:
            error(witness.line, f"witness for unknown claim {witness.cid!r}")
    witnessed = {witness.cid for witness in sheet.witnesses}
    for claim in sheet.claims:
        if claim.cid not in witnessed:
            error(claim.line, f"claim {claim.cid!r} has no witness")
    if sheet.halt:
        for cid in sheet.halt:
            if cid not in known:
                error(0, f"[HALT] names unknown claim {cid!r}")

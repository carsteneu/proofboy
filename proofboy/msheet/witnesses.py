"""The witness kinds of the notation and their execution.

Witness forms (05-02 §4, 05-07 §4/§6): ``auto`` (the target body compiled as
a V1 formula), ``py:`` (a model-written Python expression, run as an isolated
and optionally bwrap-sandboxed subprocess), ``range n in a..b:`` (an explicit
finite forall), ``ref <id>`` (promotion of a line whose last status is ``+``
and whose last check was ok), ``sim(a..b)`` (checkpoints of the target body
against a reference simulation, via :mod:`proofboy.turing`) and
``cyc(t1,t2,d)`` (a translation-cycle certificate, checked through the
existing ``[CYCLE]`` machinery of :mod:`proofboy.claimtypes.cycle`).

The doctrine is exact: CONFIRMED only on the exact check; a guard violation,
a timeout, an unparsable target or an unreached checkpoint is UNVERIFIABLE,
never a silent approximation. The ``sim``/``cyc`` machine is resolved from the
sheet's bindings (``a: M = <machine>``): by name reference in the target body
when several bindings exist, otherwise the single binding.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from proofboy import turing
from proofboy.claimtypes import cycle
from proofboy.claimtypes.cycle import DEFAULT_CYCLE_LIMIT
from proofboy.checks import DEFAULT_HALT_LIMIT
from proofboy.model import Claim, Verdict
from proofboy.msheet import formula
from proofboy.msheet.formula import Def, EmptyRangeError, EvaluationError, FormulaError, UnboundedError
from proofboy.msheet.library import GuardError


class WitnessError(ValueError):
    """The witness text is not one of the known witness forms."""


@dataclass(frozen=True)
class WitnessSpec:
    """One parsed witness: its kind and its fields."""

    kind: str
    parts: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WitnessResult:
    """The outcome of executing one witness."""

    verdict: Verdict
    reason: str = ""
    # True/False when a py: expression ran (in bwrap / without), None when no
    # process was executed.
    sandboxed: bool | None = None


@dataclass(frozen=True)
class WitnessKind:
    """One witness kind: its name, its recognizer and its executor.

    A new kind is one recognizer plus one executor plus one entry in
    :data:`WITNESS_KINDS` -- see the README of this package for a worked
    example.
    """

    name: str
    parse: Callable[[str], "WitnessSpec | None"]
    execute: Callable[..., WitnessResult]


@dataclass
class WitnessContext:
    """Everything a witness may need beyond its own text."""

    defs: Mapping[str, Def] = field(default_factory=dict)
    machines: Mapping[str, turing.Machine] = field(default_factory=dict)
    status_of: Callable[[str], str | None] = field(default=lambda _id: None)
    last_v: Callable[[str], Verdict | None] = field(default=lambda _id: None)
    sandbox: str = "auto"
    timeout: float = 10.0
    halt_limit: int = DEFAULT_HALT_LIMIT
    cycle_limit: int = DEFAULT_CYCLE_LIMIT


# One capture per field, no overlapping quantifiers: the whitespace runs
# between fixed anchors cannot backtrack (the ReDoS lesson of the HALT/SCORE
# patterns).
_CP_RE = re.compile(
    r"cp\s*([0-9]+)\s*:\s*\(\s*([A-Za-z])\s*,\s*(-?[0-9]+)\s*,\s*([01]*)\s*\)"
)
_INT_RE = re.compile(r"\A-?[0-9]+\Z")
_NAT_RE = re.compile(r"\A[0-9]+\Z")
# range <name> in <a>..<b>: <formula> -- endpoints are numbers or names
# (05-02 §3); the built forall is validated by the formula parser itself.
_RANGE_WITNESS_RE = re.compile(
    r"\Arange\s+([A-Za-z][A-Za-z0-9_]*)\s+in\s+([^\s.:]+)\s*\.\.\s*([^\s.:]+)\s*:\s*(.+)\Z"
)


def _parse_auto(text):
    return WitnessSpec("auto") if text.strip() == "auto" else None


def _parse_py(text):
    stripped = text.strip()
    if not stripped.startswith("py:"):
        return None
    expr = stripped[3:].strip()
    if not expr:
        raise WitnessError("py: needs an expression")
    return WitnessSpec("py", {"expr": expr})


def _parse_ref(text):
    stripped = text.strip()
    if not stripped.startswith("ref "):
        return None
    target = stripped[4:].strip()
    if not target:
        raise WitnessError("ref needs a line id")
    return WitnessSpec("ref", {"id": target})


def _parse_range(text):
    stripped = text.strip()
    if not stripped.startswith("range "):
        return None
    match = _RANGE_WITNESS_RE.match(stripped)
    if match is None:
        raise WitnessError("range needs 'range <name> in <a>..<b>: <formula>'")
    var, low, high, body = match.groups()
    return WitnessSpec("range", {"var": var, "low": low, "high": high, "body": body.strip()})


def _parse_sim(text):
    stripped = text.strip()
    if not stripped.startswith("sim"):
        return None
    inner = stripped[3:].strip()
    if not (inner.startswith("(") and inner.endswith(")")):
        raise WitnessError("sim needs 'sim(a..b)'")
    bounds = inner[1:-1].split("..")
    if len(bounds) != 2:
        raise WitnessError("sim needs 'sim(a..b)'")
    low, high = bounds[0].strip(), bounds[1].strip()
    if not _NAT_RE.match(low) or not _NAT_RE.match(high):
        raise WitnessError("sim needs non-negative integer bounds")
    return WitnessSpec("sim", {"low": low, "high": high})


def _parse_cyc(text):
    stripped = text.strip()
    if not stripped.startswith("cyc"):
        return None
    inner = stripped[3:].strip()
    if not (inner.startswith("(") and inner.endswith(")")):
        raise WitnessError("cyc needs 'cyc(t1,t2,d)'")
    values = [part.strip() for part in inner[1:-1].split(",")]
    if len(values) != 3 or not all(_INT_RE.match(part) for part in values):
        raise WitnessError("cyc needs three integers 'cyc(t1,t2,d)'")
    return WitnessSpec("cyc", {"t1": values[0], "t2": values[1], "d": values[2]})


def parse_witness(text):
    """Parse one witness text through the registry; raises :class:`WitnessError`."""
    for kind in WITNESS_KINDS:
        spec = kind.parse(text)
        if spec is not None:
            return spec
    raise WitnessError(f"not a witness form: {text!r}")


def _execute_auto(spec, target_body, ctx, *, tolerant=False):
    return _run_formula(target_body, ctx, "auto", tolerant=tolerant)


def _execute_range(spec, target_body, ctx, *, tolerant=False):
    built = (
        f"(forall {spec.parts['var']} in {spec.parts['low']}..{spec.parts['high']}: "
        f"{spec.parts['body']})"
    )
    return _run_formula(built, ctx, "range", tolerant=tolerant)


def _execute_py(spec, target_body, ctx, *, tolerant=False):
    return _run_py(spec.parts["expr"], ctx)


def _execute_ref(spec, target_body, ctx, *, tolerant=False):
    return _run_ref(spec.parts["id"], ctx)


def _execute_sim(spec, target_body, ctx, *, tolerant=False):
    return _run_sim(spec, target_body, ctx)


def _execute_cyc(spec, target_body, ctx, *, tolerant=False):
    return _run_cyc(spec, target_body, ctx)


def execute(spec, target_body, ctx, *, tolerant=False):
    """Execute one parsed witness against its target body.

    ``tolerant`` is for thinking-zone targets: their body is free text (05-07
    §2 "Kopf strikt, Rumpf frei"), so a top-level comparison without its
    outer parentheses is retried wrapped in one. The claim zone stays strict.
    """
    for kind in WITNESS_KINDS:
        if kind.name == spec.kind:
            return kind.execute(spec, target_body, ctx, tolerant=tolerant)
    return WitnessResult(Verdict.UNVERIFIABLE, f"unknown witness kind {spec.kind!r}")


def _parse_target(text, ctx, tolerant):
    try:
        return formula.parse_formula(text, defs=ctx.defs)
    except FormulaError:
        if not tolerant:
            raise
        return formula.parse_formula(f"({text})", defs=ctx.defs)


def _run_formula(text, ctx, prefix, *, tolerant=False):
    try:
        parsed = _parse_target(text, ctx, tolerant)
        value = formula.evaluate_bool(parsed, top_level=True)
    except GuardError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: guard: {exc}")
    except EmptyRangeError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: empty_range: {exc}")
    except UnboundedError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: unbounded_claim: {exc}")
    except NotAFormulaError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: not a formula: {exc}")
    except FormulaError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: formula: {exc}")
    except EvaluationError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: evaluation: {exc}")
    except Exception as exc:  # noqa: BLE001 -- a witness failure is never a verdict
        return WitnessResult(Verdict.UNVERIFIABLE, f"{prefix}: exception: {type(exc).__name__}: {exc}")
    if value:
        return WitnessResult(Verdict.CONFIRMED, f"{prefix}: the evaluated formula is true")
    return WitnessResult(Verdict.REFUTED, f"{prefix}: the evaluated formula is false")


# ``NotAFormula`` is part of the formula module; alias it locally so the
# exception clauses above stay readable.
NotAFormulaError = formula.NotAFormula


def find_bwrap():
    """The bwrap binary on PATH, or None."""
    return shutil.which("bwrap")


def _pyexec_script():
    return str(Path(__file__).resolve().parent / "_pyexec.py")


def _sandbox_prefix(bwrap, repo_root):
    """The bwrap wrapper of one py witness run.

    Read-only system directories, the repository read-only (the library
    import), a tmpfs for temporary files, no network. A sandbox that cannot
    start must not fall back silently -- the caller decides.
    """
    argv = [bwrap]
    for path in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
        if Path(path).exists():
            argv += ["--ro-bind", path, path]
    argv += ["--ro-bind", repo_root, repo_root]
    argv += [
        "--tmpfs", "/tmp",
        "--proc", "/proc",
        "--dev", "/dev",
        "--unshare-net",
        "--die-with-parent",
        "--clearenv",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--chdir", "/",
    ]
    return argv


def _run_py(expr, ctx):
    repo_root = str(Path(__file__).resolve().parents[2])
    script = _pyexec_script()
    command = [sys.executable, "-S", script, expr, str(int(ctx.timeout) + 1)]
    sandboxed = None
    if ctx.sandbox == "require":
        bwrap = find_bwrap()
        if bwrap is None:
            return WitnessResult(
                Verdict.UNVERIFIABLE,
                "py: sandbox required (--sandbox=require) but bwrap is not available; "
                "refusing to run the expression unsandboxed",
            )
        command = _sandbox_prefix(bwrap, repo_root) + command
        sandboxed = True
    elif ctx.sandbox == "auto":
        bwrap = find_bwrap()
        if bwrap is not None:
            command = _sandbox_prefix(bwrap, repo_root) + command
            sandboxed = True
        else:
            sandboxed = False
            print(
                "warning: py: witness runs WITHOUT bwrap (sandbox=auto, bwrap not found); "
                "the restricted builtins are no containment -- use --sandbox require to refuse",
                file=sys.stderr,
            )
    elif ctx.sandbox == "off":
        sandboxed = False
    else:
        return WitnessResult(Verdict.UNVERIFIABLE, f"unknown sandbox mode {ctx.sandbox!r}")
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=ctx.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return WitnessResult(
            Verdict.UNVERIFIABLE,
            f"py: timeout after {ctx.timeout}s; the expression did not finish",
            sandboxed,
        )
    except OSError as exc:
        return WitnessResult(Verdict.UNVERIFIABLE, f"py: could not start the runner: {exc}", sandboxed)
    payload = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and "kind" in candidate:
                payload = candidate
    if payload is None:
        tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no output"
        return WitnessResult(
            Verdict.UNVERIFIABLE,
            f"py: the runner produced no result (exit {proc.returncode}): {tail}",
            sandboxed,
        )
    if payload.get("kind") == "bool" and isinstance(payload.get("value"), bool):
        if payload["value"]:
            return WitnessResult(Verdict.CONFIRMED, "py: the expression evaluated to True", sandboxed)
        return WitnessResult(Verdict.REFUTED, "py: the expression evaluated to False", sandboxed)
    if payload["kind"] == "nonbool":
        return WitnessResult(
            Verdict.UNVERIFIABLE,
            f"py: the expression is not a bool ({payload.get('type')}: {payload.get('value')})",
            sandboxed,
        )
    return WitnessResult(
        Verdict.UNVERIFIABLE,
        f"py: exception: {payload.get('error', 'unknown error')}",
        sandboxed,
    )


def _run_ref(target_id, ctx):
    status = ctx.status_of(target_id)
    verdict = ctx.last_v(target_id)
    if status == "+" and verdict == Verdict.CONFIRMED:
        return WitnessResult(Verdict.CONFIRMED, f"ref {target_id}: carries + and its check was ok")
    return WitnessResult(
        Verdict.UNVERIFIABLE,
        f"ref {target_id}: ref_unconfirmed (last status {status!r}, last verdict "
        f"{verdict.value if verdict is not None else 'none'})",
    )


def _machine_for(target_body, ctx):
    """(machine, error): resolve the machine of a sim/cyc witness."""
    machines = ctx.machines
    if not machines:
        return None, "no machine binding in the sheet (expected 'a: M = <machine>')"
    mentioned = [
        name
        for name in machines
        if re.search(r"\b" + re.escape(name) + r"\b", target_body)
    ]
    if len(mentioned) == 1:
        return machines[mentioned[0]], None
    if len(machines) == 1:
        return next(iter(machines.values())), None
    if len(mentioned) > 1:
        return None, f"several machine names appear in the target: {mentioned}"
    return None, "multiple machine bindings but none referenced in the target"


def _tape_key(tape):
    """The tape up to its leading and trailing zeros.

    A model may count a written zero cell at either end of the window or may
    omit it; both describe the same tape state (the value is zero there in
    every reading). The comparison is on the essential content, not on window
    bookkeeping (documented precision, pilot smoke of 2026-09-12).
    """
    return tape.strip("0")


def _run_sim(spec, target_body, ctx):
    machine, error = _machine_for(target_body, ctx)
    if machine is None:
        return WitnessResult(Verdict.UNVERIFIABLE, f"sim: {error}")
    low = int(spec.parts["low"])
    high = int(spec.parts["high"])
    if high > ctx.halt_limit:
        return WitnessResult(
            Verdict.UNVERIFIABLE,
            f"sim: the segment end {high} exceeds halt_limit {ctx.halt_limit}; "
            "the simulation would run unbounded",
        )
    checkpoints = _CP_RE.findall(target_body)
    if not checkpoints:
        return WitnessResult(
            Verdict.UNVERIFIABLE,
            "sim: the target carries no checkpoint 'cp t: (q,p,T)'",
        )
    outside = [int(step) for step, _q, _p, _tape in checkpoints if not (low <= int(step) <= high)]
    if outside:
        return WitnessResult(
            Verdict.UNVERIFIABLE,
            f"sim: checkpoint(s) at step(s) {outside} fall outside the segment "
            f"{low}..{high}; the segment must cover every checkpoint of the target",
        )
    wanted = tuple(sorted({int(step) for step, _q, _p, _tape in checkpoints}))
    result, snapshots = turing.run_checkpoints(machine, high, wanted)
    for step, want_state, want_head, want_tape in checkpoints:
        step = int(step)
        snapshot = snapshots.get(step)
        if snapshot is None:
            return WitnessResult(
                Verdict.UNVERIFIABLE,
                f"sim: the configuration at step {step} was not reached (halt before it) "
                f"or does not materialize",
            )
        state = chr(ord("A") + snapshot.state)
        if state != want_state:
            return WitnessResult(
                Verdict.REFUTED,
                f"sim: at step {step} the state is {state}, not {want_state}",
            )
        if snapshot.head != int(want_head):
            return WitnessResult(
                Verdict.REFUTED,
                f"sim: at step {step} the head is at {snapshot.head}, not {want_head}",
            )
        window = "".join(str(cell) for cell in snapshot.left[::-1] + snapshot.right)
        if _tape_key(window) != _tape_key(want_tape):
            return WitnessResult(
                Verdict.REFUTED,
                f"sim: at step {step} the written window is {window!r}, not {want_tape!r}",
            )
    return WitnessResult(
        Verdict.CONFIRMED,
        f"sim: all {len(checkpoints)} checkpoint(s) match the reference simulation",
    )


class _CycleCtx:
    """The [CYCLE] checker only reads ``cycle_limit``."""

    def __init__(self, cycle_limit):
        self.cycle_limit = cycle_limit


def _run_cyc(spec, target_body, ctx):
    machine, error = _machine_for(target_body, ctx)
    if machine is None:
        return WitnessResult(Verdict.UNVERIFIABLE, f"cyc: {error}")
    t1, t2, d = spec.parts["t1"], spec.parts["t2"], spec.parts["d"]
    claim = Claim(
        kind="cycle",
        line=0,
        raw=target_body,
        fields={"machine": machine.source, "values": f"{t1},{t2},{d}", "t1": t1, "t2": t2, "d": d},
    )
    result = cycle.check(claim, _CycleCtx(ctx.cycle_limit))
    if result.verdict == Verdict.CONFIRMED:
        return WitnessResult(Verdict.CONFIRMED, f"cyc: {result.reason}")
    if result.verdict == Verdict.REFUTED:
        return WitnessResult(Verdict.REFUTED, f"cyc: {result.reason}")
    return WitnessResult(Verdict.UNVERIFIABLE, f"cyc: {result.reason}")


# The witness registry. A new kind is one recognizer plus one executor plus
# one entry here -- the worked example lives in the package README
# (proofboy/msheet/README.md, "Einen neuen Zeugen-Typ hinzufuegen").
WITNESS_KINDS: tuple[WitnessKind, ...] = (
    WitnessKind("auto", _parse_auto, _execute_auto),
    WitnessKind("py", _parse_py, _execute_py),
    WitnessKind("range", _parse_range, _execute_range),
    WitnessKind("ref", _parse_ref, _execute_ref),
    WitnessKind("sim", _parse_sim, _execute_sim),
    WitnessKind("cyc", _parse_cyc, _execute_cyc),
)

#!/usr/bin/env python3
"""Baut die Aufgaben-Sets Tier A (Mikro-Bench) und Tier B (Testfeld-Fragmente).

Tier A (05-04 §2): deterministisch erzeugte Zahlenaufgaben ueber die
V1-Bibliothek; die Referenzwerte kommen aus der Bibliothek selbst (eine
Quelle der Wahrheit), der V1-Zeuge steht im Feld ``witness``.

Tier B (04-03/04-04): Trace-Aufgaben (T2) und Zyklus-Aufgaben auf
bbchallenge-Maschinen; die Referenz-Konfigurationen werden zur Bauzeit mit
``bemyself.turing`` re-derived und im Set eingefroren. Ein Teil der
Maschinen ist lokal generiert (deterministische Saat) -- kontaminationsfrei
(K7); kuratierte Maschinen tragen ihre Herkunft im Feld ``source``.

Sets sind unveraendert: jede Aenderung erzeugt eine neue ``set_version``;
der Harness protokolliert ``set_version`` + ``set_sha256`` (05-04/05-05).

v0.2 (2026-09-12, Runde 2): Inhalte wie v0.1; Aenderungen nur Hygiene --
generierte Tier-B-Maschinen tragen ihre eigene Lizenz (CC0-1.0), die
Memory-ID in der Quelle des BB(5)-Champions ist durch die externe Referenz
ersetzt. B-0011 (schwerer Uebersetzer-Zyklus) ist enthalten und wird im
Runde-2-Lauf ohne Shuffle-Ausschluss gefahren.

v0.3 (2026-09-12, Runde 3 "Haerte"): neue Aufgaben fuer die harten Zellen,
v0.1/v0.2 bleiben eingefroren und werden weiter byte-identisch geschrieben.

- Tier A-hard (16 Aufgaben): mehrstellige Arithmetik ohne Bibliotheks-Hilfe
  -- 12- bis 20-stellige Additionen/Multiplikationen, mod/mulmod auf grossen
  Zahlen, ein 12-stelliger ggT (Bibliotheks-Guard 10^12), sowie vier lange
  Ziffernlaeufe (fc(40), fb(300), ch(200,100), 2^200). Alle Referenzwerte
  kommen aus derselben Quelle wie der Bauzeuge: ``bemyself.msheet.library``
  bzw. Python-Ints; der Zeuge steht im Feld ``witness`` und wird zur Bauzeit
  unter dem Fragment ausgewertet (er muss True ergeben).
- Tier B-hard (8 Aufgaben): vier Trace-Aufgaben mit *tiefen* Checkpoints
  (t bis 150 auf langen bbchallenge-Laeufen) und vier Zyklus-Aufgaben, davon
  drei **ohne** vorgegebenes Zertifikat (``certificate_given: false``): das
  Zertifikat ist dort das Gesuchte, nicht das Gegebene; es wird nur zur
  Bauzeit verifiziert und nie in den Prompt geschrieben.

Aufruf: python3 build_sets.py [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from bemyself import turing  # noqa: E402
from bemyself.claimtypes import cycle  # noqa: E402
from bemyself.model import Claim  # noqa: E402
from bemyself.msheet.formula import evaluate_bool, parse_formula  # noqa: E402

TIER_A_VERSION = "v11-a-0.2"
TIER_B_VERSION = "v11-b-0.2"
SEED = 20260912

# Licenses of the Tier-B tasks: curated machines are public bbchallenge
# machines; generated ones are self-created (v0.2 hygiene, 05-08 section 8).
_LICENSE_CURATED = "oeffentliche bbchallenge-Maschine; Notation frei verwendbar"
_LICENSE_GENERATED = "CC0-1.0 (selbst erzeugt)"

# ---------------------------------------------------------------------------
# Tier A

_A_SPECS = [
    ("st", ("collatz_steps", (27,)), "Berechne die Anzahl der Schritte, die die Collatz-Funktion (gerade: halbieren; ungerade: verdreifachen und 1 addieren) braucht, um {0} auf 1 zu bringen."),
    ("st", ("collatz_steps", (97,)), "Berechne die Anzahl der Collatz-Schritte von {0} bis 1."),
    ("st", ("collatz_steps", (871,)), "Berechne die Anzahl der Collatz-Schritte von {0} bis 1."),
    ("mx", ("collatz_max", (27,)), "Bestimme das Maximum der Collatz-Trajektorie von {0} bis 1 (Startwert eingeschlossen)."),
    ("mx", ("collatz_max", (97,)), "Bestimme das Maximum der Collatz-Trajektorie von {0} bis 1."),
    ("pm", ("powmod", (2, 10, 1000)), "Berechne {0} hoch {1} modulo {2}."),
    ("pm", ("powmod", (3, 100, 97)), "Berechne {0} hoch {1} modulo {2}."),
    ("pm", ("powmod", (7, 128, 1000000007)), "Berechne {0} hoch {1} modulo {2}."),
    ("gc", ("gcd", (12, 18)), "Bestimme den groessten gemeinsamen Teiler von {0} und {1}."),
    ("gc", ("gcd", (1071, 462)), "Bestimme den groessten gemeinsamen Teiler von {0} und {1}."),
    ("fc", ("factorial", (5,)), "Berechne die Fakultaet von {0} ({0}!)."),
    ("fc", ("factorial", (10,)), "Berechne die Fakultaet von {0} ({0}!)."),
    ("ch", ("choose", (10, 3)), "Berechne den Binomialkoeffizienten \"{0} ueber {1}\"."),
    ("ch", ("choose", (52, 5)), "Berechne den Binomialkoeffizienten \"{0} ueber {1}\"."),
    ("fb", ("fib", (30,)), "Bestimme die {0}-te Fibonacci-Zahl (fb(0)=0, fb(1)=1, fb(n)=fb(n-1)+fb(n-2))."),
    ("fb", ("fib", (100,)), "Bestimme die {0}-te Fibonacci-Zahl (fb(0)=0, fb(1)=1)."),
]

_ALIAS = {
    "collatz_steps": "st",
    "collatz_max": "mx",
    "powmod": "pm",
    "gcd": "gc",
    "factorial": "fc",
    "choose": "ch",
    "fib": "fb",
}


def build_tier_a():
    from bemyself.msheet.library import LIBRARY

    tasks = []
    for index, (kind, (fn_name, args), template) in enumerate(_A_SPECS, 1):
        value = LIBRARY[fn_name](*args)
        alias = _ALIAS[fn_name]
        call = f"{alias}({', '.join(str(a) for a in args)})"
        tasks.append(
            {
                "id": f"A-{index:04d}",
                "tier": "A",
                "kind": kind,
                "prompt": template.format(*args),
                "notation": "v1",
                "expected": str(value),
                "witness": f"({call} = {value})",
                "source": f"generiert (tier_a, seed={SEED})",
                "license": "CC0-1.0 (selbst erzeugt)",
            }
        )
    return tasks


# ---------------------------------------------------------------------------
# Tier A-hard (v0.3)
#
# Mehrstellige Arithmetik ohne Bibliotheks-Hilfe: die "Zahlen-Regime"-Zelle.
# Jede Aufgabe traegt (kind, prompt, witness): der Zeuge ist die exakte
# Rechnung unter dem Fragment und wird zur Bauzeit ausgewertet.
# Ziffern-Politik je Familie dokumentiert; ggT bleibt unter dem
# Bibliotheks-Guard von 10^12.

_A_HARD_ADD = [
    ("837465291837", "192837465564"),
    ("409638527194", "583746291038"),
    ("3847562918347652", "9273846510298371"),
    ("99999999999999999998", "12345678901234567893"),
]
_A_HARD_MUL = [
    ("83746293", "61835749"),
    ("384756291834", "927384651029"),
    ("3847562918347652", "9273846510298371"),
    ("12345678901234567891", "98765432109876543213"),
]
_A_HARD_MOD = [
    ("987654321987654321", "1234567891"),
    ("7777777777777777777777", "98765432101"),
]
_A_HARD_MULMOD = [
    ("987654321987", "123456789123", "1000000007"),
]
_A_HARD_GCD = [
    ("987654321987", "123456789123"),
]


def build_tier_a_hard():
    """The hard Tier-A tasks (v0.3): exact gold from the library itself."""
    from math import gcd as _gcd

    from bemyself.msheet.library import LIBRARY

    specs = []
    for left, right in _A_HARD_ADD:
        value = int(left) + int(right)
        specs.append(
            (
                "add",
                f"Berechne die Summe von {left} und {right}. Gewuenscht ist der exakte Wert.",
                f"(({left} + {right}) = {value})",
                str(value),
            )
        )
    for left, right in _A_HARD_MUL:
        value = int(left) * int(right)
        specs.append(
            (
                "mul",
                f"Berechne das Produkt von {left} und {right}. Gewuenscht ist der exakte Wert.",
                f"(({left} * {right}) = {value})",
                str(value),
            )
        )
    for left, right in _A_HARD_MOD:
        value = int(left) % int(right)
        specs.append(
            (
                "mod",
                f"Berechne den Rest von {left} modulo {right}. Gewuenscht ist der exakte Wert.",
                f"(({left} % {right}) = {value})",
                str(value),
            )
        )
    for left, right, modulus in _A_HARD_MULMOD:
        value = (int(left) * int(right)) % int(modulus)
        specs.append(
            (
                "mulmod",
                f"Berechne den Rest von ({left} * {right}) modulo {modulus}. "
                "Gewuenscht ist der exakte Wert.",
                f"((({left} * {right}) % {modulus}) = {value})",
                str(value),
            )
        )
    for left, right in _A_HARD_GCD:
        value = _gcd(int(left), int(right))
        specs.append(
            (
                "gcd",
                f"Bestimme den groessten gemeinsamen Teiler von {left} und {right}. "
                "Gewuenscht ist der exakte Wert.",
                f"(gcd({left}, {right}) = {value})",
                str(value),
            )
        )
    long_specs = [
        ("long", "Berechne fc(40) (die Fakultaet von 40). Gewuenscht ist der exakte Wert.",
         "factorial", (40,), "fc(40)"),
        ("long", "Bestimme fb(300) (die 300-te Fibonacci-Zahl, fb(0)=0, fb(1)=1). "
                 "Gewuenscht ist der exakte Wert.",
         "fib", (300,), "fb(300)"),
        ("long", "Berechne ch(200,100) (den Binomialkoeffizienten \"200 ueber 100\"). "
                 "Gewuenscht ist der exakte Wert.",
         "choose", (200, 100), "ch(200,100)"),
        ("long", "Berechne 2^200 (zwei hoch zweihundert). Gewuenscht ist der exakte Wert.",
         "power", (2, 200), "(2 ** 200)"),
    ]
    for kind, prompt, fn_name, args, call in long_specs:
        if fn_name == "power":
            value = args[0] ** args[1]
        else:
            value = LIBRARY[fn_name](*args)
        witness = f"({call} = {value})"
        specs.append((kind, prompt, witness, str(value)))

    tasks = []
    for index, (kind, prompt, witness, expected) in enumerate(specs, 1):
        evaluated = evaluate_bool(parse_formula(witness))
        if not evaluated:
            raise SystemExit(f"tier A-hard witness does not evaluate true: {witness}")
        tasks.append(
            {
                "id": f"A3-{index:04d}",
                "tier": "A",
                "kind": kind,
                "prompt": prompt,
                "notation": "v11",
                "expected": expected,
                "witness": witness,
                "source": f"generiert (tier_a_hard, seed={SEED})",
                "license": "CC0-1.0 (selbst erzeugt)",
            }
        )
    return tasks


# ---------------------------------------------------------------------------
# Tier B

CURATED_TRACE_MACHINES = [
    (
        "1RB1RZ_0LA0LA",
        "Testfixture tests/test_turing.py (halt nach genau 3 Schritten)",
        [1, 2],
    ),
    (
        "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA",
        "bbchallenge BB(5)-Champion (bbchallenge.org; 47.176.870 Schritte, Score 4098)",
        [5, 10, 20],
    ),
    (
        "1RB0LD_1LC1RD_1LA1LC_1RZ1RE_1RA0RB",
        "Marxen & Buntrock 1989 (bbchallenge; 23.554.764 Schritte, Score 4097)",
        [5, 10, 20],
    ),
    (
        "1RB1LC_0LA0LD_1LA1RZ_1LB1RE_0RD0RB",
        "Uhing 1984 (bbchallenge; 2.133.492 Schritte, Score 1915)",
        [5, 10, 20],
    ),
    (
        "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE",
        "bbchallenge BB(6)-Champion (mxdys 2025; S(6) > 2^^^5, kein Halt im Horizont)",
        [5, 10, 20],
    ),
    (
        "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC",
        "bbchallenge-Wiki \"Translated cycler\" (Figur 44394115; laeuft zyklisch, kein Halt)",
        [5, 10, 20],
    ),
]

CYC_TASKS = [
    (
        "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC",
        (6, 16, 2),
        "bbchallenge-Wiki \"Translated cycler\", Figurmaschine 44394115; Zertifikat lokal re-deriviert (tests/test_cycle.py)",
    ),
    (
        "0LA0LA",
        (0, 1, -1),
        "Testfixture tests/test_cycle.py (Schreiber 0, laeuft nach links; jedes Schritt-Intervall ist eine Translation)",
    ),
]


def _random_machine(rng, states):
    letters = [chr(ord("A") + i) for i in range(states)]
    blocks = []
    for _ in range(states):
        block = ""
        for _ in range(2):
            write = rng.choice("01")
            move = rng.choice("LR")
            target = rng.choice(letters + ["Z"])
            block += f"{write}{move}{target}"
        blocks.append(block)
    return "_".join(blocks)


def _find_generated_machines(rng, wanted, min_halt=6, max_halt=500):
    """Deterministic random machines that halt within a traceable window.

    The step distribution of random 2-3 state machines is bimodal (mostly
    halts below 6 or runs beyond any horizon), so the window is [6, 500];
    the checkpoint list keeps room before the halt (see :func:`build_tier_b`).
    """
    found = []
    attempts = 0
    while len(found) < wanted and attempts < 200000:
        attempts += 1
        states = rng.choice([2, 3])
        text = _random_machine(rng, states)
        try:
            machine = turing.parse(text)
        except turing.MachineError:
            continue
        outcome = turing.run(machine, max_halt + 1)
        if outcome.halts and min_halt <= outcome.steps <= max_halt:
            found.append((text, outcome.steps))
    return found


def _checkpoints(machine, steps):
    _result, snapshots = turing.run_checkpoints(machine, max(steps), tuple(steps))
    rows = []
    for step in steps:
        snapshot = snapshots.get(step)
        if snapshot is None:
            raise SystemExit(f"checkpoint {step} does not materialize for {machine.source}")
        letter = chr(ord("A") + snapshot.state)
        window = "".join(str(cell) for cell in snapshot.left[::-1] + snapshot.right)
        rows.append([step, letter, snapshot.head, window])
    return rows


def build_tier_b():
    tasks = []
    index = 0
    for machine_text, source, steps in CURATED_TRACE_MACHINES:
        index += 1
        machine = turing.parse(machine_text)
        rows = _checkpoints(machine, steps)
        tasks.append(
            _trace_task(
                f"B-{index:04d}", machine_text, steps, rows, source, _LICENSE_CURATED
            )
        )

    rng = random.Random(SEED)
    generated = _find_generated_machines(rng, 4)
    for machine_text, halt_steps in generated:
        index += 1
        machine = turing.parse(machine_text)
        steps = [2, 4, halt_steps - 1]
        rows = _checkpoints(machine, steps)
        source = (
            f"generiert (random.Random({SEED}); lokal simuliert: halt nach "
            f"{halt_steps} Schritten)"
        )
        tasks.append(
            _trace_task(
                f"B-{index:04d}", machine_text, steps, rows, source, _LICENSE_GENERATED
            )
        )

    for machine_text, certificate, source in CYC_TASKS:
        index += 1
        t1, t2, d = certificate
        # Re-derive the certificate through the existing machinery: it must be
        # CONFIRMED, or the task would ask for something false.
        claim = Claim(
            kind="cycle",
            line=0,
            raw="build-check",
            fields={
                "machine": machine_text,
                "values": f"{t1},{t2},{d}",
                "t1": str(t1),
                "t2": str(t2),
                "d": str(d),
            },
        )

        class _Ctx:
            cycle_limit = cycle.DEFAULT_CYCLE_LIMIT

        result = cycle.check(claim, _Ctx())
        if result.verdict.value != "CONFIRMED":
            raise SystemExit(f"cyc task certificate not confirmed for {machine_text}: {result.reason}")
        tasks.append(
            {
                "id": f"B-{index:04d}",
                "tier": "B",
                "tier_b_kind": "cyc",
                "machine": machine_text,
                "certificate": [t1, t2, d],
                "prompt": (
                    "Die 2-Symbol-Turingmaschine in bbchallenge-Notation "
                    f"lautet: {machine_text}. Start: Zustand A, Kopf auf Position 0, "
                    "leeres Band. Belege, dass sie nicht haelt, mit dem "
                    f"Translationszyklus-Zeugen (t1={t1}, t2={t2}, d={d})."
                ),
                "notation": "v11",
                "source": source,
                "license": _LICENSE_CURATED,
            }
        )
    return tasks


# ---------------------------------------------------------------------------
# Tier B-hard (v0.3): tiefe Checkpoints auf langen Laeufen + Zyklus-Aufgaben
# mit und ohne vorgegebenes Zertifikat.

_HARD_TRACE = [
    (
        "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA",
        "bbchallenge BB(5)-Champion (bbchallenge.org; 47.176.870 Schritte, Score 4098)",
        [10, 25, 50, 75, 100, 125, 150],
    ),
    (
        "1RB0LD_1LC1RD_1LA1LC_1RZ1RE_1RA0RB",
        "Marxen & Buntrock 1989 (bbchallenge; 23.554.764 Schritte, Score 4097)",
        [10, 25, 50, 75, 100],
    ),
    (
        "1RB1LC_0LA0LD_1LA1RZ_1LB1RE_0RD0RB",
        "Uhing 1984 (bbchallenge; 2.133.492 Schritte, Score 1915)",
        [10, 25, 50, 100],
    ),
    (
        "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE",
        "bbchallenge BB(6)-Champion (mxdys 2025; S(6) > 2^^^5, kein Halt im Horizont)",
        [10, 25, 50, 75, 100],
    ),
]

# (machine, certificate, certificate_given, source, license)
_HARD_CYC = [
    (
        "0LA0LA",
        (0, 1, -1),
        False,
        "Testfixture tests/test_cycle.py (Schreiber 0, laeuft nach links; jedes "
        "Schritt-Intervall ist eine Translation) -- Zertifikat ohne Vorgabe",
        _LICENSE_CURATED,
    ),
    (
        "0RB1RB_0RA0LZ",
        (1, 3, 2),
        False,
        "lokal gesucht (random.Random(20260914), Kopf-Profil) und per cycle.check "
        "verifiziert -- Zertifikat ohne Vorgabe",
        _LICENSE_GENERATED,
    ),
    (
        "1LC1LB_1LC1RC_1RA0LB",
        (133, 142, 1),
        True,
        "lokal gesucht (random.Random(20260915), Kopf-Profil) und per cycle.check "
        "verifiziert -- Zertifikat vorgegeben",
        _LICENSE_GENERATED,
    ),
    (
        "1LB1LB_1RA0LB",
        (34, 37, -1),
        False,
        "lokal gesucht (random.Random(20260915), Kopf-Profil) und per cycle.check "
        "verifiziert -- Zertifikat ohne Vorgabe",
        _LICENSE_GENERATED,
    ),
]


def _verify_certificate(machine_text, certificate):
    t1, t2, d = certificate
    claim = Claim(
        kind="cycle",
        line=0,
        raw="build-check",
        fields={
            "machine": machine_text,
            "values": f"{t1},{t2},{d}",
            "t1": str(t1),
            "t2": str(t2),
            "d": str(d),
        },
    )

    class _Ctx:
        cycle_limit = cycle.DEFAULT_CYCLE_LIMIT

    return cycle.check(claim, _Ctx())


def build_tier_b_hard():
    tasks = []
    index = 0
    for machine_text, source, steps in _HARD_TRACE:
        index += 1
        machine = turing.parse(machine_text)
        rows = _checkpoints(machine, steps)
        tasks.append(
            _trace_task(
                f"B3-{index:04d}", machine_text, steps, rows, source, _LICENSE_CURATED
            )
        )

    for machine_text, certificate, given, source, license_text in _HARD_CYC:
        index += 1
        t1, t2, d = certificate
        result = _verify_certificate(machine_text, certificate)
        if result.verdict.value != "CONFIRMED":
            raise SystemExit(
                f"cyc task certificate not confirmed for {machine_text}: {result.reason}"
            )
        if given:
            prompt = (
                "Die 2-Symbol-Turingmaschine in bbchallenge-Notation "
                f"lautet: {machine_text}. Start: Zustand A, Kopf auf Position 0, "
                "leeres Band. Belege, dass sie nicht haelt, mit dem "
                f"Translationszyklus-Zeugen (t1={t1}, t2={t2}, d={d})."
            )
        else:
            prompt = (
                "Die 2-Symbol-Turingmaschine in bbchallenge-Notation "
                f"lautet: {machine_text}. Start: Zustand A, Kopf auf Position 0, "
                "leeres Band; R = Kopf nach rechts, L = nach links, Z = Halt. "
                "Untersuche den Lauf: Halte er an, oder laeuft die Maschine in einen "
                "Translationszyklus? Bestimme im Zyklusfall die Werte t1, t2 und d selbst."
            )
        tasks.append(
            {
                "id": f"B3-{index:04d}",
                "tier": "B",
                "tier_b_kind": "cyc",
                "machine": machine_text,
                "certificate": [t1, t2, d],
                "certificate_given": given,
                "prompt": prompt,
                "notation": "v11",
                "source": source,
                "license": license_text,
            }
        )
    return tasks


def _trace_task(task_id, machine_text, steps, rows, source, license_text):
    steps_text = ", ".join(str(s) for s in steps)
    return {
        "id": task_id,
        "tier": "B",
        "tier_b_kind": "trace",
        "machine": machine_text,
        "horizon": max(steps),
        "checkpoints_t": steps,
        "checkpoints_gold": rows,
        "prompt": (
            "Die 2-Symbol-Turingmaschine in bbchallenge-Notation lautet: "
            f"{machine_text}. Start: Zustand A, Kopf auf Position 0, leeres Band; "
            "R = Kopf nach rechts, L = nach links, Z = Halt. Simuliere den Lauf und "
            f"belege die Konfigurationen nach den Schritten {steps_text}."
        ),
        "notation": "v11",
        "source": source,
        "license": license_text,
    }


# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the Tier A/B task sets.")
    parser.add_argument(
        "--out",
        default=str(ROOT / "yesdocs" / "deepseek-math-notation" / "sets"),
        help="output directory",
    )
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tier_a = {
        "set_version": TIER_A_VERSION,
        "created": "2026-09-12",
        "seed": SEED,
        "note": "v0.2: Aufgabeninhalte identisch zu v0.1 (nur Versions-/Provenienzstand).",
        "tasks": build_tier_a(),
    }
    tier_b = {
        "set_version": TIER_B_VERSION,
        "created": "2026-09-12",
        "seed": SEED,
        "note": (
            "v0.2: Inhalte wie v0.1; Hygiene -- Lizenz generierter Maschinen "
            "korrigiert, Memory-ID durch externe Referenz ersetzt. B-0011 enthalten."
        ),
        "tasks": build_tier_b(),
    }
    tier_a_hard = {
        "set_version": "v11-a-0.3",
        "created": "2026-09-12",
        "seed": SEED,
        "note": (
            "v0.3 (Haerte-Runde): mehrstellige Arithmetik (12-20 Stellen), "
            "mod/mulmod/gcd auf grossen Zahlen, vier lange Ziffernlaeufe. "
            "Ziffern-Politik je Familie im Bericht 05-10; Gold = Bibliothek."
        ),
        "tasks": build_tier_a_hard(),
    }
    tier_b_hard = {
        "set_version": "v11-b-0.3",
        "created": "2026-09-12",
        "seed": SEED,
        "note": (
            "v0.3 (Haerte-Runde): tiefe Checkpoints (t bis 150) auf langen "
            "bbchallenge-Laeufen; vier Zyklus-Aufgaben, davon drei ohne "
            "vorgegebenes Zertifikat. Zertifikate zur Bauzeit per cycle.check "
            "verifiziert."
        ),
        "tasks": build_tier_b_hard(),
    }

    for name, payload in (
        ("tier_a", tier_a),
        ("tier_b", tier_b),
        ("tier_a", tier_a_hard),
        ("tier_b", tier_b_hard),
    ):
        path = out / f"{name}_{payload['set_version']}.json"
        text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
        path.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        try:
            shown = path.resolve().relative_to(ROOT)
        except ValueError:
            shown = path.resolve()
        print(f"{shown}  sha256={digest}")
    print(
        f"Tier A: {len(tier_a['tasks'])}/{len(tier_a_hard['tasks'])} Aufgaben, "
        f"Tier B: {len(tier_b['tasks'])}/{len(tier_b_hard['tasks'])} Aufgaben "
        "(v0.2/v0.3)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

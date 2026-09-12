#!/usr/bin/env python3
"""Tests der Haerte-Runde V13 (Sets v0.3, Protokoll-Fixes, Scoring).

Deckt sechs Baustellen:

1. Sets v0.3: Tier-A-hard (mehrstellige Arithmetik, exakter Gold-Zeuge,
   deterministisch) und Tier-B-hard (tiefe Checkpoints auf langen Laeufen,
   Zyklus-Faelle teils *ohne* vorgegebenes Zertifikat).
2. v0.2 bleibt eingefroren: Hashes gepinnt, Rebuild byte-identisch.
3. Prompt-Leck-Freiheit: die Nicht-Vorgabe-Variante der Zyklus-Aufgabe nennt
   keine Zertifikatswerte -- auch nicht im Reparaturpfad.
4. Zyklus-Scoring maschinenverifiziert: das Verdikt kommt aus
   ``claimtypes.cycle`` auf den vom Modell genannten Werten, nie aus einem
   Gold-Stringvergleich (V12 verwarf gueltige *andere* Zertifikate).
5. Sanitizer als Default-Deny-Allowlist: unbekannte Beleg-Arten kommen
   automatisch ohne Referenzwerte zurueck.
6. Erfolg vs. Trigger getrennt: der Trigger (das Ereignis, das die naechste
   Runde ausloest) steht als eigenes Feld in Runden- und Laufdaten.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"
SETS = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load("harness")
prompts = _load("prompts")
evaluate = _load("evaluate")

from bemyself import turing  # noqa: E402
from bemyself.claimtypes import cycle  # noqa: E402
from bemyself.model import Claim, Verdict  # noqa: E402
from bemyself.msheet.formula import evaluate_bool, parse_formula  # noqa: E402

TIER_A_V03 = "tier_a_v11-a-0.3.json"
TIER_B_V03 = "tier_b_v11-b-0.3.json"

# Die eingefrorenen Staende der frueheren Runden (Datei-Hash der committeten
# Bytes). Jede Aenderung an v0.1/v0.2 muesste hier bewusst nachgezogen werden.
FROZEN_SETS = {
    "tier_a_v11-a-0.1.json": "50c985e169aa500799824d7e05fa5cf918b5f1b1c3e45be5a4cb8c3ec73474f9",
    "tier_b_v11-b-0.1.json": "074ab6bf5ebfc2132a73dcaae7b490754e559e1870a594c28dc0deb9a2b02ccf",
    "tier_a_v11-a-0.2.json": "007424292fd10129877b3c0c2d733de6e556d08183955b6d9a10c0d2d8be81ce",
    "tier_b_v11-b-0.2.json": "68eb917ebd26ae2d4ed1200b56c62114edd019bba868d2bd0d350348aad52395",
}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_set(name):
    return json.loads((SETS / name).read_text(encoding="utf-8"))


def _numbers(text):
    import re

    return [int(match) for match in re.findall(r"[0-9]+", text)]


class SetsV03Test(unittest.TestCase):
    """Die harten Sets: Form, Determinismus, exakte Gold-Werte."""

    def test_v03_files_exist_and_parse(self):
        tier_a = _load_set(TIER_A_V03)
        tier_b = _load_set(TIER_B_V03)
        self.assertEqual(tier_a["set_version"], "v11-a-0.3")
        self.assertEqual(tier_b["set_version"], "v11-b-0.3")
        self.assertEqual(len(tier_a["tasks"]), 16)
        self.assertEqual(len(tier_b["tasks"]), 8)
        for payload in (tier_a, tier_b):
            ids = [task["id"] for task in payload["tasks"]]
            self.assertEqual(len(ids), len(set(ids)), "task ids sind eindeutig")

    def test_tier_a_hard_families_and_sizes(self):
        tasks = _load_set(TIER_A_V03)["tasks"]
        counts = {}
        for task in tasks:
            counts[task["kind"]] = counts.get(task["kind"], 0) + 1
        self.assertEqual(
            counts, {"add": 4, "mul": 4, "mod": 2, "mulmod": 1, "gcd": 1, "long": 4}
        )
        for task in tasks:
            kind = task["kind"]
            if kind in ("add", "mod", "mulmod"):
                # Alle Operanden der Rechnung sind mehrstellig (>= 10^5 fuer
                # die kleinen, fuer mod/mulmod entsprechend groesser, siehe
                # die folgenden Schwellen).
                self.assertGreaterEqual(min(_numbers(task["prompt"])), 10**5, task["id"])
            if kind == "add":
                self.assertGreaterEqual(min(_numbers(task["prompt"])), 10**5, task["id"])
            if kind == "mul":
                self.assertGreaterEqual(min(_numbers(task["prompt"])), 10**7, task["id"])
            if kind == "mod":
                self.assertGreaterEqual(min(_numbers(task["prompt"])), 10**6, task["id"])
            if kind == "mulmod":
                self.assertGreaterEqual(min(_numbers(task["prompt"])), 10**6, task["id"])
            if kind == "long":
                self.assertGreaterEqual(len(task["expected"]), 20, task["id"])
        # Die Rechnungen liegen wirklich im mehrstelligen Bereich: zwei
        # Additionen ab 16 Stellen, zwei Multiplikationen ab 16 Stellen,
        # eine mod-Aufgabe ab 15 Stellen.
        adds = [t for t in tasks if t["kind"] == "add"]
        self.assertEqual(sum(1 for t in adds if max(_numbers(t["prompt"])) >= 10**15), 2)
        muls = [t for t in tasks if t["kind"] == "mul"]
        self.assertEqual(sum(1 for t in muls if max(_numbers(t["prompt"])) >= 10**15), 2)

    def test_tier_a_hard_witnesses_prove_the_exact_gold(self):
        # Der Bauzeuge ist exakt: er evaluiert unter dem Fragment zu True und
        # die Ziffernkette des Aufgaben-Texts kommt als Zahl vor. Der Goldwert
        # kommt aus der Bibliothek (eine Quelle der Wahrheit).
        for task in _load_set(TIER_A_V03)["tasks"]:
            witness = task["witness"]
            self.assertTrue(evaluate_bool(parse_formula(witness)), task["id"])
            self.assertIn(task["expected"], witness, task["id"])

    def test_tier_b_hard_trace_tasks_reproduce_at_build_depth(self):
        tasks = [t for t in _load_set(TIER_B_V03)["tasks"] if t["tier_b_kind"] == "trace"]
        self.assertEqual(len(tasks), 4)
        for task in tasks:
            self.assertGreaterEqual(len(task["checkpoints_t"]), 4, task["id"])
            self.assertGreaterEqual(max(task["checkpoints_t"]), 100, task["id"])
            machine = turing.parse(task["machine"])
            _result, snapshots = turing.run_checkpoints(
                machine, max(task["checkpoints_t"]), tuple(task["checkpoints_t"])
            )
            for step, letter, head, window in task["checkpoints_gold"]:
                snapshot = snapshots.get(step)
                self.assertIsNotNone(snapshot, f"{task['id']} t={step}")
                self.assertEqual(chr(ord("A") + snapshot.state), letter, f"{task['id']} t={step}")
                self.assertEqual(snapshot.head, head, f"{task['id']} t={step}")
                window_now = "".join(str(c) for c in snapshot.left[::-1] + snapshot.right)
                self.assertEqual(window_now, window, f"{task['id']} t={step}")

    def test_tier_b_hard_cyc_tasks_carry_verified_certificates(self):
        tasks = [t for t in _load_set(TIER_B_V03)["tasks"] if t["tier_b_kind"] == "cyc"]
        self.assertEqual(len(tasks), 4)
        not_given = [t for t in tasks if t.get("certificate_given") is False]
        self.assertGreaterEqual(len(not_given), 2, "mindestens zwei ohne Vorgabe")
        for task in tasks:
            t1, t2, d = task["certificate"]
            claim = Claim(
                kind="cycle",
                line=0,
                raw="set-check",
                fields={
                    "machine": task["machine"],
                    "values": f"{t1},{t2},{d}",
                    "t1": str(t1),
                    "t2": str(t2),
                    "d": str(d),
                },
            )

            class _Ctx:
                cycle_limit = cycle.DEFAULT_CYCLE_LIMIT

            result = cycle.check(claim, _Ctx())
            self.assertEqual(result.verdict, Verdict.CONFIRMED, f"{task['id']}: {result.reason}")
            prompt = task["prompt"]
            if task.get("certificate_given") is False:
                for needle in (f"t1={t1}", f"t2={t2}", f"d={d}"):
                    self.assertNotIn(needle, prompt, task["id"])
                # Der Prompt verlangt die Bestimmung ausdruecklich selbst.
                self.assertIn("selbst", prompt, task["id"])

    def test_frozen_sets_are_untouched(self):
        for name, digest in FROZEN_SETS.items():
            self.assertEqual(_sha256(SETS / name), digest, name)

    def test_rebuild_writes_v03_and_keeps_v02_byte_identical(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=tmp_root))
        # v0.1 ist Altbestand und wird nicht mehr gebaut; der Builder schreibt
        # v0.2 (unveraendert) und v0.3 (neu).
        written = [name for name in FROZEN_SETS if "0.2" in name] + [TIER_A_V03, TIER_B_V03]
        try:
            subprocess.run(
                [sys.executable, str(TOOLING / "build_sets.py"), "--out", str(tmp)],
                check=True,
                cwd=ROOT,
                capture_output=True,
            )
            for name in written:
                self.assertEqual(
                    (tmp / name).read_bytes(), (SETS / name).read_bytes(), name
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PromptV13Test(unittest.TestCase):
    """Die Antwort-Konvention darf das Gold nicht tragen, wenn 'nicht
    vorgegeben' gesetzt ist -- in keinem Arm, in keiner Runde."""

    CYC_NOT_GIVEN = {
        "id": "B-0005",
        "tier": "B",
        "tier_b_kind": "cyc",
        "machine": "0LA0LA",
        "certificate": [0, 1, -1],
        "certificate_given": False,
        "prompt": "Untersuche den Lauf. Bestimme im Zyklusfall die Werte t1, t2 und d selbst.",
    }

    def _instruction(self, arm):
        return prompts._answer_instruction(arm, self.CYC_NOT_GIVEN)

    def test_no_certificate_values_in_any_arm_instruction(self):
        for arm in ("K", "B", "C", "D"):
            text = self._instruction(arm)
            for needle in ("t1=0", "t2=1", "d=-1", "cyc(0,1,-1)", "(0,1,-1)"):
                self.assertNotIn(needle, text, f"{arm}: {text}")

    def test_instruction_still_asks_for_the_certificate(self):
        for arm in ("K", "B", "C", "D"):
            text = self._instruction(arm)
            self.assertIn("t1", text, arm)
            self.assertIn("d", text, arm)
        self.assertIn("NICHT-HALTEND", self._instruction("K"))
        self.assertIn("cyc(", self._instruction("C"))
        self.assertIn("selbst", self._instruction("C"))

    def test_given_certificate_keeps_the_v12_wording(self):
        task = dict(self.CYC_NOT_GIVEN)
        task["certificate_given"] = True
        self.assertIn("cyc(0,1,-1)", prompts._answer_instruction("C", task))
        self.assertIn("NICHT-HALTEND (t1=0,t2=1,d=-1)", prompts._answer_instruction("K", task))
        legacy = dict(self.CYC_NOT_GIVEN)
        legacy.pop("certificate_given")
        self.assertIn("cyc(0,1,-1)", prompts._answer_instruction("C", legacy))

    def test_k_repair_selfcheck_does_not_leak_the_certificate(self):
        text = prompts.build_repair_message("K", self.CYC_NOT_GIVEN, [], [], [])
        for needle in ("t1=0", "t2=1", "d=-1"):
            self.assertNotIn(needle, text)


class CycScoringV13Test(unittest.TestCase):
    """Das Zyklus-Verdikt kommt aus der Maschinenpruefung, nicht aus dem
    Gold-Stringvergleich: richtige *andere* Zertifikate zaehlen, falsche
    Zertifikate zaehlen nicht."""

    TASK = {
        "id": "B-0005",
        "tier": "B",
        "tier_b_kind": "cyc",
        "machine": "0LA0LA",
        "certificate": [0, 1, -1],
        "certificate_given": False,
        "prompt": "Untersuche den Lauf.",
    }

    def test_right_certificate_solves_k(self):
        answer = "Endantwort: NICHT-HALTEND (t1=0,t2=1,d=-1)"
        self.assertTrue(harness.evaluate_answer("K", self.TASK, answer)["solved"])

    def test_other_valid_certificate_solves_k(self):
        # (0,2,-2) ist ein gueltiges Zertifikat derselben Maschine; V12 haette
        # es verworfen, weil es nicht dem Goldstring entspricht.
        answer = "Endantwort: NICHT-HALTEND (t1=0,t2=2,d=-2)"
        self.assertTrue(harness.evaluate_answer("K", self.TASK, answer)["solved"])

    def test_wrong_certificate_does_not_solve_k(self):
        # (0,1,1) traegt nicht (Kopf nach Schritt 1 ist bei -1, nicht +1).
        answer = "Endantwort: NICHT-HALTEND (t1=0,t2=1,d=1)"
        self.assertFalse(harness.evaluate_answer("K", self.TASK, answer)["solved"])

    def test_b_arm_scores_by_the_machine_too(self):
        good = "M bewegt sich nach links und schreibt 0.\nEndantwort: NICHT-HALTEND (t1=0,t2=2,d=-2)"
        bad = "M bewegt sich nach links und schreibt 0.\nEndantwort: NICHT-HALTEND (t1=0,t2=1,d=1)"
        self.assertTrue(harness.evaluate_answer("B", self.TASK, good)["solved"])
        self.assertFalse(harness.evaluate_answer("B", self.TASK, bad)["solved"])

    def test_solved_requires_the_not_halted_marker(self):
        answer = "v h1: cyc(0,1,-1)"
        self.assertFalse(harness.evaluate_answer("B", self.TASK, answer)["solved"])

    def test_missing_certificate_does_not_solve(self):
        self.assertFalse(
            harness.evaluate_answer("K", self.TASK, "Endantwort: NICHT-HALTEND")["solved"]
        )

    def test_c_arm_sheet_still_machine_verified(self):
        answer = (
            "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,2,-2)\nh1+\n"
            "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
        )
        record = harness.evaluate_answer("C", self.TASK, answer)
        self.assertTrue(record["solved"], record.get("claims"))
        self.assertTrue(record["machine_bound"])

    def test_c_arm_sheet_about_another_machine_does_not_solve(self):
        answer = (
            "a: M = 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC\nh1: M zyklisch (Translation)\n"
            "v h1: cyc(6,16,2)\nh1+\nCLAIM c1: M zyklisch (Translation)\n"
            "WITNESS c1: ref h1\n[HALT] c1"
        )
        self.assertFalse(harness.evaluate_answer("C", self.TASK, answer)["solved"])


class SanitizerV13Test(unittest.TestCase):
    """Default-Deny: nur die geprueften Beleg-Arten duerfen ihre Befunde
    durchreichen; alles andere kommt ohne Referenzwerte zurueck."""

    def test_unknown_kind_refutation_loses_the_values(self):
        text = harness._sanitize_reason("hyperclaim", "REFUTED", "the hidden value is 424242")
        self.assertNotIn("424242", text)
        self.assertIn("traegt nicht", text)

    def test_unknown_kind_unverifiable_loses_the_values(self):
        text = harness._sanitize_reason("hyperclaim", "UNVERIFIABLE", "divergence at cell 31337")
        self.assertNotIn("31337", text)
        self.assertIn("traegt nicht", text)

    def test_missing_kind_is_denied(self):
        text = harness._sanitize_reason(None, "REFUTED", "raw text with 999")
        self.assertNotIn("999", text)

    def test_range_witness_reasons_pass_the_allowlist(self):
        # ``range`` baut seine Formel in witnesses._execute_range und laeuft
        # durch denselben _run_formula-Pfad wie ``auto``: die nicht-REFUTED-
        # Texte sind strukturell identisch und wertfrei (Audit 5.2/2).
        cases = [
            ("range", "REFUTED", "range: the evaluated formula is false"),
            ("range", "UNVERIFIABLE", "range: guard: factorial: n must be in 0..10^4"),
            ("range", "UNVERIFIABLE", "range: formula: expected ')', found '='"),
        ]
        for kind, verdict, reason in cases:
            self.assertEqual(harness._sanitize_reason(kind, verdict, reason), reason)

    def test_reviewed_kinds_keep_their_safe_reasons(self):
        cases = [
            ("auto", "REFUTED", "auto: the evaluated formula is false"),
            ("auto", "UNVERIFIABLE", "auto: formula: expected ')', found '='"),
            ("auto", "UNVERIFIABLE", "auto: guard: factorial: n must be in 0..10^4"),
            ("ref", "UNVERIFIABLE", "ref h1: ref_unconfirmed (last status '-', last verdict REFUTED)"),
            (
                "sim",
                "UNVERIFIABLE",
                "sim: no machine binding in the sheet (expected 'a: M = <machine>')",
            ),
            (
                "sim",
                "UNVERIFIABLE",
                "sim: the configuration at step 5 was not reached (halt before it)",
            ),
            ("py", "REFUTED", "py: the expression evaluated to False"),
            ("py", "UNVERIFIABLE", "py: exception: ZeroDivisionError: division by zero"),
        ]
        for kind, verdict, reason in cases:
            self.assertEqual(harness._sanitize_reason(kind, verdict, reason), reason)

    def test_sim_refutation_stays_sanitized(self):
        text = harness._sanitize_reason(
            "sim", "REFUTED", "sim: at step 5 the head is at 9, not 7"
        )
        self.assertNotIn("not 7", text)
        self.assertIn("stimmt nicht", text)

    def test_cyc_refutation_stays_sanitized(self):
        text = harness._sanitize_reason(
            "cyc", "REFUTED", "cyc: the machine halted after 12 steps, inside the certificate window"
        )
        self.assertNotIn("12 steps", text)
        self.assertIn("traegt", text)


class _FakeCall:
    """Scripted transport: one entry per model call, in call order."""

    def __init__(self, contents):
        self.contents = list(contents)
        self.messages_seen = []
        self.calls = 0

    def __call__(self, messages, timeout):
        self.messages_seen.append([dict(message) for message in messages])
        if self.calls >= len(self.contents):
            raise AssertionError("further calls than scripted answers")
        content = self.contents[self.calls]
        self.calls += 1
        usage = {"completion_tokens": 10, "completion_tokens_details": {"reasoning_tokens": 5}}
        return {"content": content, "reasoning": "", "usage": usage, "finish_reason": "stop"}, {}, 0.1, None


class _FakeArgs:
    timeout = 5.0
    max_repairs = 2


_TRACE_TASK = {
    "id": "B-9001",
    "tier": "B",
    "tier_b_kind": "trace",
    "machine": "1RB1RZ_0LA0LA",
    "checkpoints_t": [1, 2],
    "checkpoints_gold": [[1, "B", 1, "1"], [2, "A", 0, "1"]],
    "prompt": "Simuliere.",
}

_NUM_TASK = {
    "id": "A-9001",
    "tier": "A",
    "expected": "111",
    "prompt": "Berechne etwas.",
}

_CYC_TASK = {
    "id": "B-9002",
    "tier": "B",
    "tier_b_kind": "cyc",
    "machine": "0LA0LA",
    "certificate": [0, 1, -1],
    "certificate_given": False,
    "prompt": "Untersuche den Lauf.",
}

_TRACE_OK = "cp 1: (B,1,1)\ncp 2: (A,0,1)"

_SHEET_BAD = (
    "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,1)\nh1+\n"
    "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
)
_SHEET_OK = (
    "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,-1)\nh1+\n"
    "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
)


class ScoringRobustnessV13Test(unittest.TestCase):
    """Review-Fixes 5.2/1 + 5.4 (MEDIUM): modell-kontrollierte Zahlen duerfen
    einen Lauf nie abbrechen. CPython begrenzt int(str) auf 4300 Stellen und
    wirft darueber ValueError -- der Regex faengt beliebig lange Ziffernfolgen,
    die Konvertierung muss also fail-closed sein (wie in cycle.py)."""

    TASK = {
        "id": "B-9003",
        "tier": "B",
        "tier_b_kind": "cyc",
        "machine": "0LA0LA",
        "certificate": [0, 1, -1],
        "certificate_given": False,
        "prompt": "Untersuche den Lauf.",
    }

    def test_huge_certificate_digits_do_not_crash(self):
        huge = "9" * 5000
        answer = f"Endantwort: NICHT-HALTEND (t1=1,t2={huge},d=1)"
        record = harness.evaluate_answer("K", self.TASK, answer)  # darf nicht werfen
        self.assertFalse(record["solved"])
        self.assertIsNone(record["certificate_claimed"])

    def test_huge_head_position_in_checkpoint_line_does_not_crash(self):
        huge = "7" * 5000
        answer = f"cp 1: (A,{huge},1)"
        matched, first_deviation, pairs = harness._checkpoint_score(
            answer, [[1, "B", 1, "1"]]
        )
        self.assertEqual(matched, 0)
        self.assertEqual(pairs, {})

    def test_huge_step_number_in_checkpoint_line_does_not_crash(self):
        huge = "7" * 5000
        answer = f"cp {huge}: (A,0,1)"
        matched, _first, pairs = harness._checkpoint_score(answer, [[1, "B", 1, "1"]])
        self.assertEqual(matched, 0)
        self.assertEqual(pairs, {})


class TriggerV13Test(unittest.TestCase):
    """Erfolg und Trigger sind getrennte Begriffe: der Erfolg ist der
    typisierte Endzustand, der Trigger das Ereignis, das die naechste Runde
    ausloest. Form-/Transportfehler sind kein Trigger."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_success_is_not_a_trigger(self):
        summary = harness.run_rounds(
            "B", _TRACE_TASK, 1, self._root(), _FakeArgs(), call=_FakeCall([_TRACE_OK])
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual([row["trigger"] for row in summary["rounds"]], [None])
        self.assertEqual(summary["repairs_used"], 0)

    def test_not_confirmed_rounds_name_the_trigger(self):
        summary = harness.run_rounds(
            "C", _CYC_TASK, 1, self._root(), _FakeArgs(), call=_FakeCall([_SHEET_BAD, _SHEET_OK])
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(
            [row["trigger"] for row in summary["rounds"]],
            ["end_state_not_confirmed", None],
        )
        self.assertEqual(summary["repairs_used"], 1)

    def test_k_number_mismatch_is_a_trigger(self):
        summary = harness.run_rounds(
            "K", _NUM_TASK, 1, self._root(), _FakeArgs(),
            call=_FakeCall(["Endantwort: 112", "Endantwort: 111"]),
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["rounds"][0]["trigger"], "end_state_not_confirmed")
        self.assertEqual(summary["rounds"][1]["trigger"], None)

    def test_k_cyc_wrong_certificate_is_a_trigger(self):
        summary = harness.run_rounds(
            "K", _CYC_TASK, 1, self._root(), _FakeArgs(),
            call=_FakeCall(
                [
                    "Endantwort: NICHT-HALTEND (t1=0,t2=1,d=1)",
                    "Endantwort: NICHT-HALTEND (t1=0,t2=1,d=-1)",
                ]
            ),
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["repairs_used"], 1)
        self.assertEqual(summary["rounds"][0]["trigger"], "end_state_not_confirmed")

    def test_exhausted_budget_has_no_trailing_trigger(self):
        summary = harness.run_rounds(
            "C", _CYC_TASK, 1, self._root(), _FakeArgs(),
            call=_FakeCall([_SHEET_BAD, _SHEET_BAD, _SHEET_BAD]),
        )
        self.assertFalse(summary["final_solved"])
        self.assertEqual(
            [row["trigger"] for row in summary["rounds"]],
            ["end_state_not_confirmed", "end_state_not_confirmed", None],
        )

    def test_trigger_is_written_to_the_round_record(self):
        root = self._root()
        harness.run_rounds(
            "C", _CYC_TASK, 1, root, _FakeArgs(), call=_FakeCall([_SHEET_BAD, _SHEET_OK])
        )
        record = json.loads(
            (root / _CYC_TASK["id"] / "C-rep1" / "round0" / "parsed.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["trigger"], "end_state_not_confirmed")


class EvaluateV13Test(unittest.TestCase):
    """Die Auswertung sieht, wie viele Laeufe ueberhaupt einen Trigger hatten."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_triggered_runs_metric_and_round_layout(self):
        root = self._root()
        harness.run_rounds(
            "C", _CYC_TASK, 1, root, _FakeArgs(), call=_FakeCall([_SHEET_BAD, _SHEET_OK])
        )
        harness.run_rounds(
            "C", _CYC_TASK, 2, root, _FakeArgs(), call=_FakeCall([_SHEET_OK])
        )
        _manifest, runs = evaluate.load_runs(root)
        summary = evaluate.summarize_runs(runs)
        entry = summary["C-B"]
        self.assertEqual(entry["n"], 2)
        self.assertEqual(entry["triggered_runs"], 1)
        self.assertEqual(entry["final_solved"], 2)

    def test_markdown_shows_the_trigger_column(self):
        root = self._root()
        harness.run_rounds(
            "C", _CYC_TASK, 1, root, _FakeArgs(), call=_FakeCall([_SHEET_BAD, _SHEET_OK])
        )
        manifest, runs = evaluate.load_runs(root)
        summary = evaluate.summarize_runs(runs)
        markdown = evaluate.render_round_markdown(summary, manifest)
        self.assertIn("Trigger-Läufe", markdown)
        self.assertIn("| C-B | 1 | 0 | 0.0 |", markdown)
        # Eine getriggerte Runde, final gelöst.
        self.assertIn("| 1 | 1 | +100.0 pp |", markdown)


if __name__ == "__main__":
    unittest.main()

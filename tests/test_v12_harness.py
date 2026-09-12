"""Tests for the V12 repair-loop tooling (yesdocs/.../tooling, Runde 2).

Runde 2 (05-09) faehrt den Rueckkanal: eine Aufgabe laeuft ueber mehrere
Runden; nach jeder Runde entscheidet der Runner bzw. das Gold-Kriterium, ob
der Endzustand bestaetigt ist -- sonst folgt eine Reparaturrunde mit
Verdikt-Appendix. Die tragenden Teile sind der Feedback-Builder (mit
Gold-Leak-Schutz), die Runden-Schleife des Harness und die Runden-Metriken
der Auswertung; dazu die v0.2-Fixes (%-Klammerregel der Legenden).

The functions under test decide the measurement: untested feedback or
round-logic would poison the round.
"""

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"

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

from bemyself.msheet.runner import run_sheet  # noqa: E402
from bemyself.msheet.sheet import parse_sheet  # noqa: E402

TASK_A = {"id": "A-0006", "tier": "A", "prompt": "Berechne 2 hoch 10 modulo 1000.", "expected": "24"}
TASK_TRACE = {
    "id": "B-0001",
    "tier": "B",
    "tier_b_kind": "trace",
    "machine": "1RB1RZ_0LA0LA",
    "checkpoints_t": [1, 2],
    "prompt": "Simuliere.",
}


class LegendV02Test(unittest.TestCase):
    """M1: Legenden v0.2 -- %-Klammerregel explizit, Beispiel parser-valid."""

    def test_percent_rule_is_explicit_in_the_formula_arms(self):
        # v0.1 lehrte das Modell die invalide Form ((2 ^ 10) % 1000 = 24)
        # (Repro: Parser -> "expected ')', found '='"). v0.2 nennt die Regel
        # operandenweise und zeigt die korrekte Form.
        for arm in ("B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_A)
            self.assertIn("((A % B) = C)", system, arm)
            self.assertIn("(((2 ^ 10) % 1000) = 24)", system, arm)
            self.assertNotIn("((2 ^ 10) % 1000 = 24)", system, arm)

    def test_k_legend_carries_no_formula_zone_rule(self):
        # K schreibt keine Formelzone; die Regel bliebe dort ohne Adressat.
        system, _user = prompts.build_messages("K", TASK_A)
        self.assertNotIn("((A % B) = C)", system)

    def test_the_legend_example_parses_and_confirms(self):
        # Der Legenden-Ausdruck muss durch Parser und Runner gehen -- sonst
        # lehrt die Legende wieder eine Form, die der Runner ablehnt.
        for arm in ("B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_A)
            match = re.search(r"\(\(\(2 \^ 10\) % 1000\) = 24\)", system)
            self.assertIsNotNone(match, arm)
            sheet = parse_sheet(
                f"CLAIM c1: {match.group(0)}\nWITNESS c1: auto\n[HALT] c1"
            )
            result = run_sheet(sheet, sandbox="auto", timeout=10.0)
            self.assertEqual(
                result.claim_results[0].verdict.value, "CONFIRMED", arm
            )


class TraceConventionV02Test(unittest.TestCase):
    """M1: cp-Konvention praezisiert -- Konfiguration NACH dem Schritt t."""

    def test_precision_is_in_every_arm(self):
        for arm in ("K", "B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_TRACE)
            self.assertIn("NACH dem angegebenen Schritt", system, arm)
            self.assertIn("Schritt 0 ist der Startzustand", system, arm)

    def test_v11_anchors_are_kept(self):
        # Kontinuitaet zu Pilot 1: die I3-Formulierungen bleiben wortgleich.
        for arm in ("K", "B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_TRACE)
            self.assertIn("Kopfposition = ganze Zahl ab", system, arm)
            self.assertIn("Zellen sind 0", system, arm)


class SetsV02Test(unittest.TestCase):
    """M2: Sets v0.2 -- neue Version+sha256, v0.1 unangetastet, B-0011 enthalten."""

    SETS = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"

    def _load_set(self, name):
        return json.loads((self.SETS / name).read_text(encoding="utf-8"))

    def test_v02_sets_exist_with_expected_shape(self):
        tier_a = self._load_set("tier_a_v11-a-0.2.json")
        tier_b = self._load_set("tier_b_v11-b-0.2.json")
        self.assertEqual(tier_a["set_version"], "v11-a-0.2")
        self.assertEqual(tier_b["set_version"], "v11-b-0.2")
        self.assertEqual(len(tier_a["tasks"]), 16)
        self.assertEqual(len(tier_b["tasks"]), 12)

    def test_heavy_translator_cycle_is_present(self):
        # Runde-2-Auftrag: B-0011 wird forciert (kein Shuffle-Ausschluss).
        tier_b = self._load_set("tier_b_v11-b-0.2.json")
        task = next(t for t in tier_b["tasks"] if t["id"] == "B-0011")
        self.assertEqual(task["tier_b_kind"], "cyc")
        self.assertEqual(task["machine"], "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC")
        self.assertEqual(task["certificate"], [6, 16, 2])

    def test_tier_a_content_is_identical_to_v01(self):
        # Kontinuitaet: die Aufgabeninhalte bleiben Pilot-1-gleich.
        old = self._load_set("tier_a_v11-a-0.1.json")
        new = self._load_set("tier_a_v11-a-0.2.json")
        self.assertEqual(old["tasks"], new["tasks"])

    def test_v01_files_are_untouched(self):
        # Hashes aus 05-08 (Pilot-1-Lauf): v0.1 bleibt eingefroren.
        for name, prefix in (
            ("tier_a_v11-a-0.1.json", "50c985e169aa5007"),
            ("tier_b_v11-b-0.1.json", "074ab6bf5ebfc213"),
        ):
            digest = hashlib.sha256((self.SETS / name).read_bytes()).hexdigest()
            self.assertTrue(digest.startswith(prefix), name)

    def test_generated_tasks_carry_own_license_and_no_memory_ids(self):
        tier_b = self._load_set("tier_b_v11-b-0.2.json")
        generated = [t for t in tier_b["tasks"] if t["source"].startswith("generiert")]
        self.assertTrue(generated)
        for task in generated:
            self.assertEqual(task["license"], "CC0-1.0 (selbst erzeugt)", task["id"])
        for task in tier_b["tasks"]:
            self.assertNotIn("Learning", task["source"], task["id"])

    def test_rebuild_reproduces_the_committed_v02_files(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=tmp_root))
        try:
            subprocess.run(
                [sys.executable, str(TOOLING / "build_sets.py"), "--out", str(tmp)],
                check=True,
                cwd=ROOT,
                capture_output=True,
            )
            for name in ("tier_a_v11-a-0.2.json", "tier_b_v11-b-0.2.json"):
                self.assertEqual(
                    (tmp / name).read_bytes(), (self.SETS / name).read_bytes(), name
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _FakeCall:
    """Scripted transport: one entry per model call, in call order."""

    def __init__(self, contents):
        self.contents = list(contents)
        self.messages_seen = []
        self.calls = 0

    def __call__(self, messages, timeout):
        self.calls += 1
        self.messages_seen.append([dict(m) for m in messages])
        content = self.contents.pop(0) if self.contents else "Endantwort: 0"
        payload = {
            "content": content,
            "reasoning": "",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "completion_tokens_details": {"reasoning_tokens": 4},
            },
            "finish_reason": "stop",
        }
        return payload, {"choices": [{"message": {"content": content}}]}, 0.1, None


class _FakeArgs:
    def __init__(self, max_repairs=2):
        self.timeout = 5.0
        self.max_repairs = max_repairs


_SHEET_OK = (
    "g: pm(2,10,1000)?\n"
    "h1: (((2 ^ 10) % 1000) = 24)\n"
    "v h1: auto\n"
    "h1+\n"
    "CLAIM c1: (((2 ^ 10) % 1000) = 24)\n"
    "WITNESS c1: ref h1\n"
    "[HALT] c1"
)
_SHEET_BAD = (
    "g: pm(2,10,1000)?\n"
    "h1: (((2 ^ 10) % 1000) = 124)\n"
    "v h1: auto\n"
    "h1+\n"
    "CLAIM c1: (((2 ^ 10) % 1000) = 124)\n"
    "WITNESS c1: ref h1\n"
    "[HALT] c1"
)


class FeedbackTest(unittest.TestCase):
    """M3: Rueckfuetterung -- Appendix + Befunde, ohne Gold-Werte."""

    def _evidence(self, arm, answer):
        evidence = {}
        record = harness.evaluate_run(arm, TASK_A, {"content": answer}, 0.5, None, None, evidence_out=evidence)
        return record, evidence

    def test_c_feedback_carries_appendix_and_question_reason(self):
        record, evidence = self._evidence("C", _SHEET_BAD)
        self.assertFalse(record["solved"])
        verdicts, notes = harness.feedback_lines("C", TASK_A, evidence)
        self.assertIn("#?: c1", verdicts)
        self.assertIn("#xx: v1", verdicts)
        self.assertTrue(any("v1" in note for note in notes))
        self.assertFalse(any("#ok" in v for v in verdicts))

    def test_c_feedback_has_no_gold_value(self):
        # Die Rueckfuetterung darf den Erwartungswert nicht nennen; die eigene
        # (falsche) Behauptung 124 ist erlaubt, das Gold 24 nicht.
        record, evidence = self._evidence("C", _SHEET_BAD)
        verdicts, notes = harness.feedback_lines("C", TASK_A, evidence)
        text = "\n".join(verdicts + notes)
        self.assertIsNone(re.search(r"(?<![0-9])24(?![0-9])", text))
        self.assertNotIn("111", text)

    def test_b_receives_own_claim_appendix(self):
        # Fairness-Design (Default): B erhaelt seine eigenen maschinell
        # geprueften Claim-Verdikte -- Verdikte, die es gibt.
        bad_b = "CLAIM c1: (((2 ^ 10) % 1000) = 124)\nWITNESS c1: auto\n[HALT] c1"
        evidence = {}
        record = harness.evaluate_run("B", TASK_A, {"content": bad_b}, 0.5, None, None, evidence_out=evidence)
        self.assertFalse(record["solved"])
        verdicts, notes = harness.feedback_lines("B", TASK_A, evidence)
        self.assertIn("#xx: c1", verdicts)

    def test_sim_refutation_note_is_sanitized(self):
        task = {
            "id": "B-0001",
            "tier": "B",
            "tier_b_kind": "trace",
            "machine": "1RB1RZ_0LA0LA",
            "checkpoints_t": [1, 2],
            "checkpoints_gold": [[1, "B", 1, "1"], [2, "A", 0, "1"]],
            "prompt": "Simuliere.",
        }
        bad = (
            "a: M = 1RB1RZ_0LA0LA\n"
            "h1: cp 1: (B,4,1)\n"
            "v h1: sim(0..2)\n"
            "h1+\n"
            "CLAIM c1: cp 1: (B,4,1)\n"
            "WITNESS c1: ref h1\n"
            "[HALT] c1"
        )
        evidence = {}
        harness.evaluate_run("C", task, {"content": bad}, 0.5, None, None, evidence_out=evidence)
        verdicts, notes = harness.feedback_lines("C", task, evidence)
        joined = "\n".join(verdicts + notes)
        # Der echte Grund nennt die Referenzwerte (z.B. "the head is at 1, not 4");
        # die Rueckfuetterung darf sie nicht enthalten.
        reason = evidence["result"].v_results[0].reason
        self.assertIn("the head is at", reason)
        self.assertNotIn("the head is at", joined)
        self.assertIn("#xx: v1", verdicts)

    def test_k_gets_no_verdicts(self):
        verdicts, notes = harness.feedback_lines("K", TASK_A, None)
        self.assertEqual(verdicts, [])
        self.assertEqual(notes, [])

    def test_repair_message_k_is_neutral(self):
        text = prompts.build_repair_message("K", TASK_A, [], [], [])
        self.assertIn("Pruefe", text)
        self.assertIn("Endantwort", text)
        for marker in ("#ok", "#xx", "#?"):
            self.assertNotIn(marker, text)

    def test_repair_message_sheet_arm_carries_appendix(self):
        text = prompts.build_repair_message(
            "C", TASK_A, ["#xx: v1"], ["v1: auto: the evaluated formula is false"], []
        )
        self.assertIn("#xx: v1", text)
        self.assertIn("v1: auto", text)

    def test_repair_message_lists_format_errors(self):
        text = prompts.build_repair_message(
            "B", TASK_A, [], [], ["line 3: no valid line head: 'kaputt'"]
        )
        self.assertIn("no valid line head", text)


class RepairLoopTest(unittest.TestCase):
    """M3: Runden-Schleife -- Abbruch bei ok, max 2 Reparaturen, Logs."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_round0_solved_stops_without_repair(self):
        fake = _FakeCall([_SHEET_OK])
        root = self._root()
        summary = harness.run_rounds("C", TASK_A, 1, root, _FakeArgs(), call=fake)
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["rounds_to_ok"], 0)
        self.assertEqual(summary["repairs_used"], 0)
        self.assertEqual(len(summary["rounds"]), 1)
        self.assertFalse((root / "A-0006" / "C-rep1" / "round1").exists())

    def test_repair_round_fixes_and_is_logged(self):
        fake = _FakeCall([_SHEET_BAD, _SHEET_OK])
        root = self._root()
        summary = harness.run_rounds("C", TASK_A, 1, root, _FakeArgs(), call=fake)
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["rounds_to_ok"], 1)
        self.assertEqual(summary["repairs_used"], 1)
        self.assertEqual(len(summary["rounds"]), 2)
        parsed0 = json.loads((root / "A-0006" / "C-rep1" / "round0" / "parsed.json").read_text())
        self.assertIn("#?: c1", parsed0["next_feedback"])
        parsed1 = json.loads((root / "A-0006" / "C-rep1" / "round1" / "parsed.json").read_text())
        self.assertIn("#?: c1", parsed1["feedback_in"])
        prompt1 = (root / "A-0006" / "C-rep1" / "round1" / "prompt.md").read_text()
        self.assertIn("#?: c1", prompt1)
        self.assertIn(_SHEET_BAD.splitlines()[1], prompt1)  # eigener Vorrunden-Text im Verlauf
        # Die Wiederholung des Blattes in Runde 1 ist die Antwort des Modells,
        # nicht die Rueckfuetterung -- der Verlauf waechst monoton.
        summary_json = json.loads((root / "A-0006" / "C-rep1" / "summary.json").read_text())
        self.assertEqual(summary_json["final_solved"], True)

    def test_max_repairs_bounds_the_loop(self):
        fake = _FakeCall([_SHEET_BAD, _SHEET_BAD, _SHEET_BAD])
        root = self._root()
        summary = harness.run_rounds("C", TASK_A, 1, root, _FakeArgs(max_repairs=2), call=fake)
        self.assertFalse(summary["final_solved"])
        self.assertIsNone(summary["rounds_to_ok"])
        self.assertEqual(summary["repairs_used"], 2)
        self.assertEqual(len(summary["rounds"]), 3)
        self.assertEqual(fake.calls, 3)

    def test_k_repair_is_neutral_selfcheck(self):
        fake = _FakeCall(["Endantwort: 124", "Endantwort: 24"])
        root = self._root()
        summary = harness.run_rounds("K", TASK_A, 1, root, _FakeArgs(), call=fake)
        self.assertTrue(summary["final_solved"])
        prompt1 = (root / "A-0006" / "K-rep1" / "round1" / "prompt.md").read_text()
        self.assertIn("Pruefe", prompt1)
        self.assertNotIn("#xx", prompt1)
        self.assertNotIn("#ok", prompt1)
        self.assertNotIn("#?", prompt1)

    def test_transport_error_is_retried_once(self):
        class ErrorCall(_FakeCall):
            def __call__(self, messages, timeout):
                if self.calls == 0:
                    self.calls += 1
                    self.messages_seen.append([dict(m) for m in messages])
                    return None, None, 0.1, "URLError: boom"
                return super().__call__(messages, timeout)

        fake = ErrorCall([_SHEET_OK])
        root = self._root()
        summary = harness.run_rounds("C", TASK_A, 1, root, _FakeArgs(), call=fake)
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["transport_retries"], 1)

    def test_history_strips_reasoning(self):
        fake = _FakeCall([_SHEET_BAD, _SHEET_OK])
        root = self._root()
        harness.run_rounds("C", TASK_A, 1, root, _FakeArgs(), call=fake)
        last_messages = fake.messages_seen[-1]
        roles = [m["role"] for m in last_messages]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        assistant = [m for m in last_messages if m["role"] == "assistant"][0]
        # decision: reasoning_content wird nicht zurueckgespielt.
        self.assertEqual(set(assistant.keys()), {"role", "content"})


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests des Zwangsprompt-Arms H (V16) und seiner Harness-Integration.

Bewusst als Guard-Tests formuliert:

- H traegt die C-Legende als Praefix (die V1.1-Sprache bleibt die Basis).
- H fuegt den knallharten Zwangsblock hinzu: Marker (MANDATORY, ATTENTION,
  DU MUSST, SUPER WICHTIG), Denkspur-Pflicht fuer ``reasoning_content``,
  Prosa als Formfehler mit Konsequenz, kurzes Beispiel.
- H benutzt die C-Antwortkonventionen und den maschinellen
  Reparatur-Rueckkanal unveraendert (Erfolg/Trigger wie C).
- Kein Arm traegt das Zertifikat der Nicht-Vorgabe-Aufgabe.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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


prompts = _load("prompts")
harness = _load("harness")

_NUM_TASK = {"id": "A-9001", "tier": "A", "expected": "111", "prompt": "Berechne etwas."}
_TRACE_TASK = {
    "id": "B-9001",
    "tier": "B",
    "tier_b_kind": "trace",
    "machine": "1RB1RZ_0LA0LA",
    "checkpoints_t": [1],
    "checkpoints_gold": [[1, "B", 1, "1"]],
    "prompt": "Simuliere.",
}
_CYC_NOT_GIVEN = {
    "id": "B-9002",
    "tier": "B",
    "tier_b_kind": "cyc",
    "machine": "0LA0LA",
    "certificate": [0, 1, -1],
    "certificate_given": False,
    "prompt": "Untersuche den Lauf. Bestimme im Zyklusfall die Werte t1, t2 und d selbst.",
}
_CYC_GIVEN = dict(_CYC_NOT_GIVEN, certificate_given=True)

_TRACE_SHEET = (
    "a: M = 1RB1RZ_0LA0LA\nh1: cp 1: (B,1,1)\nv h1: sim(0..1)\nh1+\n"
    "CLAIM c1: cp 1: (B,1,1)\nWITNESS c1: ref h1\n[HALT] c1"
)
_CYC_BAD = (
    "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,1)\nh1+\n"
    "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
)
_CYC_OK = _CYC_BAD.replace("cyc(0,1,1)", "cyc(0,1,-1)")


class ForceArmLegendTest(unittest.TestCase):
    """Die H-Legende: C als Basis, Zwangsblock gestaffelt darueber."""

    def test_h_extends_c(self):
        self.assertIn("H", prompts.LEGENDS)
        self.assertTrue(prompts.LEGENDS["H"].startswith(prompts.LEGENDS["C"]))

    def test_h_carries_the_hard_markers(self):
        legend = prompts.LEGENDS["H"]
        for marker in ("MANDATORY", "ATTENTION", "DU MUSST", "SUPER WICHTIG"):
            self.assertIn(marker, legend, marker)

    def test_h_requires_the_v11_tag_headers(self):
        legend = prompts.LEGENDS["H"]
        self.assertIn("Tag-Kopf", legend)
        self.assertIn("g:", legend)
        self.assertIn("h1:", legend)

    def test_h_addresses_the_reasoning_channel(self):
        self.assertIn("reasoning_content", prompts.LEGENDS["H"])

    def test_h_declares_prose_a_form_error_with_consequence(self):
        legend = prompts.LEGENDS["H"]
        lowered = legend.lower()
        self.assertIn("formfehler", lowered)
        self.assertIn("prosa", lowered)
        self.assertIn("ungueltig", lowered)

    def test_h_delta_contains_a_short_example(self):
        delta = prompts.LEGENDS["H"][len(prompts.LEGENDS["C"]):]
        self.assertIn("Beispiel", delta)
        self.assertIn("v h1: auto", delta)

    def test_h_keeps_the_c_answer_instructions(self):
        for arm_task in (_NUM_TASK, _TRACE_TASK, _CYC_NOT_GIVEN, _CYC_GIVEN):
            self.assertEqual(
                prompts._answer_instruction("H", arm_task),
                prompts._answer_instruction("C", arm_task),
                arm_task["id"],
            )

    def test_no_certificate_gold_in_h_prompt(self):
        system, user = prompts.build_messages("H", _CYC_NOT_GIVEN)
        for needle in ("t1=0", "t2=1", "d=-1", "cyc(0,1,-1)", "(0,1,-1)"):
            self.assertNotIn(needle, system + user, needle)


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


class HarnessForceArmTest(unittest.TestCase):
    """H verhaelt sich im Harness wie C (Bewertung + Rueckkanal)."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_h_is_a_machine_feedback_arm(self):
        self.assertIn("H", harness.MACHINE_FEEDBACK_ARMS)

    def test_h_trace_answer_evaluates_the_sheet(self):
        record = harness.evaluate_answer("H", _TRACE_TASK, _TRACE_SHEET)
        self.assertEqual(record["checkpoints_matched"], 1)
        self.assertIn("v", record, "Blatt-Belege fehlen fuer den H-Trace-Pfad")

    def test_h_repair_round_carries_machine_verdicts(self):
        fake = _FakeCall([_CYC_BAD, _CYC_OK])
        summary = harness.run_rounds(
            "H", _CYC_NOT_GIVEN, 1, self._root(), _FakeArgs(), call=fake
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["repairs_used"], 1)
        repair_user = fake.messages_seen[1][-1]["content"]
        self.assertIn("Der Zeugen-Runner hat dein Blatt geprueft.", repair_user)

    def test_h_writes_the_same_run_layout(self):
        root = self._root()
        harness.run_rounds(
            "H", _CYC_NOT_GIVEN, 1, root, _FakeArgs(), call=_FakeCall([_CYC_OK])
        )
        summary_path = root / _CYC_NOT_GIVEN["id"] / "H-rep1" / "summary.json"
        self.assertTrue(summary_path.exists())
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["arm"], "H")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests der Lean-Arme L0/L1/L2 (V18) — Guard-Tests im V15-Stil.

- L0 ist **byte-identisch** zu C0 (Kontrolle bleibt Kontrolle).
- L1 ist **byte-identisch** zu C1 (V1.1-RC-Referenz bleibt unveraendert).
- L2 traegt L0/C0 plus die Lean-Taktik-RC-Instruktion (LEAN_RC).
- Alle L-Arme benutzen die C-Antwortkonventionen und den maschinellen
  Reparatur-Rueckkanal unveraendert.
- Kein L-Arm traegt das Zertifikat der Nicht-Vorgabe-Aufgabe.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
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

_CYC_BAD = (
    "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,1)\nh1+\n"
    "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
)
_CYC_OK = _CYC_BAD.replace("cyc(0,1,1)", "cyc(0,1,-1)")


class LeanArmLegendTest(unittest.TestCase):
    """Die Legenden der Lean-Arme: Kontrolle identisch, Zusatz gestaffelt."""

    def test_l0_is_byte_identical_to_c0(self):
        self.assertIn("L0", prompts.LEGENDS)
        self.assertEqual(prompts.LEGENDS["L0"], prompts.LEGENDS["C0"])
        self.assertEqual(prompts.LEGENDS["L0"], prompts.LEGENDS["C"])

    def test_l1_is_byte_identical_to_c1(self):
        self.assertIn("L1", prompts.LEGENDS)
        self.assertEqual(prompts.LEGENDS["L1"], prompts.LEGENDS["C1"])

    def test_l2_extends_l0_with_the_lean_instruction(self):
        l0 = prompts.LEGENDS["L0"]
        l2 = prompts.LEGENDS["L2"]
        self.assertTrue(l2.startswith(l0), "L2 muss L0 als Praefix tragen")
        self.assertIn("reasoning_content", l2)
        lowered = l2.lower()
        self.assertIn("lean", lowered)
        self.assertIn("taktik", lowered)
        self.assertIn("keine prosa", lowered)
        # Das RC-Beispiel gehoert dazu (Beispielpflicht der Lean-Instruktion).
        self.assertIn("Beispiel einer Denkspur", l2)
        self.assertGreater(len(l2), len(l0))

    def test_l2_instruction_is_standalone_piece(self):
        self.assertTrue(prompts.LEAN_RC.strip())
        self.assertTrue(hasattr(prompts, "LEAN_RC"))
        self.assertEqual(prompts.LEGENDS["L2"], prompts.LEGENDS["L0"] + prompts.LEAN_RC)

    def test_all_l_arms_share_the_c_answer_instructions(self):
        for arm in ("L0", "L1", "L2"):
            for task in (_NUM_TASK, _TRACE_TASK, _CYC_NOT_GIVEN):
                self.assertEqual(
                    prompts._answer_instruction(arm, task),
                    prompts._answer_instruction("C", task),
                    f"{arm}/{task['id']}",
                )

    def test_no_certificate_gold_in_any_l_arm_prompt(self):
        for arm in ("L0", "L1", "L2"):
            system, user = prompts.build_messages(arm, _CYC_NOT_GIVEN)
            for needle in ("t1=0", "t2=1", "d=-1", "cyc(0,1,-1)", "(0,1,-1)"):
                self.assertNotIn(needle, system + user, f"{arm}: {needle}")

    def test_existing_arms_unchanged(self):
        self.assertEqual(prompts.LEGENDS["K"], prompts.LEGEND_K)
        self.assertEqual(prompts.LEGENDS["C"], prompts.LEGEND_C)
        self.assertEqual(prompts.LEGENDS["C1"], prompts.LEGEND_C + prompts.RC_STRONG)


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


class HarnessLeanArmTest(unittest.TestCase):
    """Die L-Arme verhalten sich im Harness wie C (Bewertung + Rueckkanal)."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_l_arms_get_machine_feedback(self):
        for arm in ("L0", "L1", "L2"):
            self.assertIn(arm, harness.MACHINE_FEEDBACK_ARMS, arm)

    def test_l2_repair_round_carries_machine_verdicts(self):
        fake = _FakeCall([_CYC_BAD, _CYC_OK])
        summary = harness.run_rounds(
            "L2", _CYC_NOT_GIVEN, 1, self._root(), _FakeArgs(), call=fake
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["repairs_used"], 1)
        repair_user = fake.messages_seen[1][-1]["content"]
        self.assertIn("Der Zeugen-Runner hat dein Blatt geprueft.", repair_user)

    def test_l2_writes_the_same_run_layout(self):
        root = self._root()
        harness.run_rounds("L2", _CYC_NOT_GIVEN, 1, root, _FakeArgs(), call=_FakeCall([_CYC_OK]))
        summary_path = root / _CYC_NOT_GIVEN["id"] / "L2-rep1" / "summary.json"
        self.assertTrue(summary_path.exists())
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["arm"], "L2")


if __name__ == "__main__":
    unittest.main()

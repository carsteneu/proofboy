#!/usr/bin/env python3
"""Tests der RC-Umstellungs-Arme C0/C1/C2 (V15) und der Aufgaben-Auswahl.

Bewusst als Guard-Tests formuliert:

- C0 ist **byte-identisch** zum V13-Arm C (Kontrolle bleibt Kontrolle).
- C1 erweitert die C-Legende um die starke RC-Instruktion.
- C2 erweitert C1 um ein vollstaendiges RC-Beispiel.
- Alle C-Arme benutzen die C-Antwortkonventionen und den maschinellen
  Reparatur-Rueckkanal unveraendert (Erfolg/Trigger wie V13).
- Kein Arm traegt das Zertifikat der Nicht-Vorgabe-Aufgabe.
- ``harness.batch --task-ids`` waehlt exakt die genannten Aufgaben
  (Reproduzierbarkeit der 12-Task-Teilmenge); ohne Flag bleibt der
  Shuffle-Pfad unveraendert.
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


class RcArmLegendTest(unittest.TestCase):
    """Die Legenden der RC-Arme: Kontrolle identisch, Zusatz gestaffelt."""

    def test_c0_is_byte_identical_to_c(self):
        self.assertIn("C0", prompts.LEGENDS)
        self.assertEqual(prompts.LEGENDS["C0"], prompts.LEGENDS["C"])

    def test_c1_extends_c_with_the_rc_instruction(self):
        c0 = prompts.LEGENDS["C0"]
        c1 = prompts.LEGENDS["C1"]
        self.assertTrue(c1.startswith(c0), "C1 muss C0 als Praefix tragen")
        self.assertIn("reasoning_content", c1)
        lowered = c1.lower()
        self.assertIn("keine prosa", lowered)
        self.assertIn("tag-kopf", lowered)

    def test_c2_adds_the_full_rc_example(self):
        c1 = prompts.LEGENDS["C1"]
        c2 = prompts.LEGENDS["C2"]
        self.assertTrue(c2.startswith(c1), "C2 muss C1 als Praefix tragen")
        self.assertIn("Beispiel einer Denkspur", c2)
        self.assertGreater(len(c2), len(c1))

    def test_all_c_arms_share_the_c_answer_instructions(self):
        for arm in ("C0", "C1", "C2"):
            for task in (_NUM_TASK, _TRACE_TASK, _CYC_NOT_GIVEN, _CYC_GIVEN):
                self.assertEqual(
                    prompts._answer_instruction(arm, task),
                    prompts._answer_instruction("C", task),
                    f"{arm}/{task['id']}",
                )

    def test_no_certificate_gold_in_any_c_arm_prompt(self):
        for arm in ("C0", "C1", "C2"):
            system, user = prompts.build_messages(arm, _CYC_NOT_GIVEN)
            for needle in ("t1=0", "t2=1", "d=-1", "cyc(0,1,-1)", "(0,1,-1)"):
                self.assertNotIn(needle, system + user, f"{arm}: {needle}")


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


class HarnessRcArmTest(unittest.TestCase):
    """Die C-Arme verhalten sich im Harness wie C (Bewertung + Rueckkanal)."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_c_arms_get_machine_feedback(self):
        for arm in ("C0", "C1", "C2"):
            self.assertIn(arm, harness.MACHINE_FEEDBACK_ARMS, arm)

    def test_c1_trace_answer_evaluates_the_sheet(self):
        record = harness.evaluate_answer("C1", _TRACE_TASK, _TRACE_SHEET)
        self.assertEqual(record["checkpoints_matched"], 1)
        self.assertIn("v", record, "Blatt-Belege fehlen fuer den C1-Trace-Pfad")

    def test_c1_repair_round_carries_machine_verdicts(self):
        fake = _FakeCall([_CYC_BAD, _CYC_OK])
        summary = harness.run_rounds(
            "C1", _CYC_NOT_GIVEN, 1, self._root(), _FakeArgs(), call=fake
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["repairs_used"], 1)
        repair_user = fake.messages_seen[1][-1]["content"]
        self.assertIn("Der Zeugen-Runner hat dein Blatt geprueft.", repair_user)

    def test_c0_writes_the_same_run_layout(self):
        root = self._root()
        harness.run_rounds(
            "C0", _CYC_NOT_GIVEN, 1, root, _FakeArgs(), call=_FakeCall([_CYC_OK])
        )
        summary_path = root / _CYC_NOT_GIVEN["id"] / "C0-rep1" / "summary.json"
        self.assertTrue(summary_path.exists())
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["arm"], "C0")


class TaskSelectionTest(unittest.TestCase):
    """--task-ids waehlt exakt; der Default-Shuffle bleibt unveraendert."""

    TIER_A = {
        "tasks": [
            {"id": "A3-0001", "tier": "A"},
            {"id": "A3-0002", "tier": "A"},
            {"id": "A3-0003", "tier": "A"},
        ]
    }
    TIER_B = {
        "tasks": [
            {"id": "B3-0001", "tier": "B"},
            {"id": "B3-0002", "tier": "B"},
        ]
    }

    def _args(self, **overrides):
        values = {"seed": 20260912, "tier_a": None, "tier_b": None, "task_ids": None}
        values.update(overrides)
        return SimpleNamespace(**values)

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_task_ids_selects_exactly_and_in_order(self):
        tasks = harness._select_tasks(
            self.TIER_A, self.TIER_B, self._args(task_ids="B3-0002, A3-0001")
        )
        self.assertEqual([task["id"] for task in tasks], ["B3-0002", "A3-0001"])

    def test_unknown_task_id_raises(self):
        with self.assertRaises(ValueError):
            harness._select_tasks(
                self.TIER_A, self.TIER_B, self._args(task_ids="A3-9999")
            )

    def test_without_task_ids_the_shuffle_path_still_works(self):
        tasks = harness._select_tasks(
            self.TIER_A, self.TIER_B, self._args(tier_a=2, tier_b=1)
        )
        self.assertEqual(len(tasks), 3)

    def test_batch_cli_passes_task_ids_through(self):
        seen = {}
        original_select = harness._select_tasks
        original_runs = harness.RUNS_DIR

        def fake_select(tier_a, tier_b, args):
            seen["task_ids"] = args.task_ids
            return []

        harness._select_tasks = fake_select
        harness.RUNS_DIR = self._root()
        try:
            code = harness.main(
                ["batch", "--skip-warmup", "--task-ids", "A3-0001,B3-0001"]
            )
        finally:
            harness._select_tasks = original_select
            harness.RUNS_DIR = original_runs
        self.assertEqual(code, 0)
        self.assertEqual(seen["task_ids"], "A3-0001,B3-0001")


if __name__ == "__main__":
    unittest.main()

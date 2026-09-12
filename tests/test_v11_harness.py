"""Tests for the V1.1 pilot tooling (yesdocs/.../tooling).

The functions under test decide scores of the pilot: the checkpoint score
(including the value-equal tape comparison up to leading/trailing zeros), the
end-answer extraction of the control arm and the prompt/message builder of
the four arms. They are the load-bearing parts of the harness -- untested
scoring would poison the measurement.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))

harness = _load("harness")
prompts = _load("prompts")
evaluate = _load("evaluate")


class EvaluateTest(unittest.TestCase):
    def test_marker_stats_count_v_lines_as_valid(self):
        # Review finding I1 (2026-09-12): v-lines are valid line heads.
        total, valid = evaluate._sheet_marker_stats(
            "g: ziel\nh1: (1 = 1)\nv h1: auto\nh1+\nCLAIM c1: (1 = 1)\nWITNESS c1: ref h1\n[HALT] c1"
        )
        self.assertEqual((total, valid), (7, 7))

    def test_marker_stats_flags_prose(self):
        total, valid = evaluate._sheet_marker_stats("h1: ok\nnur ein satz ohne kopf")
        self.assertEqual((total, valid), (2, 1))

    def _record(self, arm, tier, solved, **over):
        record = {
            "arm": arm,
            "tier": tier,
            "solved": solved,
            "duration_s": 2.0,
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 100,
                "completion_tokens_details": {"reasoning_tokens": 80},
            },
            "answer": "h1: (1 = 1)",
        }
        record.update(over)
        return record

    def test_summary_counts_and_rates(self):
        records = [
            self._record("C", "A", True, claims=[{"id": "c1", "verdict": "CONFIRMED", "reason": ""}]),
            self._record("C", "A", False, claims=[{"id": "c1", "verdict": "REFUTED", "reason": ""}]),
        ]
        summary = evaluate.summarize(records)
        entry = summary["C-A"]
        self.assertEqual(entry["n"], 2)
        self.assertEqual(entry["solved"], 1)
        self.assertEqual(entry["claims_confirmed"], 1)
        self.assertEqual(entry["claims_refuted"], 1)
        self.assertEqual(entry["false_confirm_proxy"], 0.5)
        self.assertAlmostEqual(entry["reasoning_tokens_mean"], 80.0)

    def test_wilson_bounds(self):
        low, high = evaluate.wilson(0, 10)
        self.assertGreaterEqual(low, 0.0)
        self.assertLess(high, 0.4)
        low, high = evaluate.wilson(10, 10)
        self.assertGreater(low, 0.6)
        self.assertLessEqual(high, 1.0)


class CheckpointScoreTest(unittest.TestCase):
    GOLD = [[5, "C", 1, "1111"], [10, "D", 2, "11111"]]

    def test_all_exact(self):
        answer = "cp 5: (C,1,1111)\ncp 10: (D,2,11111)"
        matched, first, _pairs = harness._checkpoint_score(answer, self.GOLD)
        self.assertEqual((matched, first), (2, None))

    def test_trailing_zero_window_is_value_equal(self):
        # The pilot smoke of 2026-09-12: models count a written zero cell at
        # the end of the window; the value is the same.
        answer = "cp 5: (C,1,11110)\ncp 10: (D,2,11111)"
        matched, first, _pairs = harness._checkpoint_score(answer, self.GOLD)
        self.assertEqual((matched, first), (2, None))

    def test_first_deviation(self):
        answer = "cp 5: (C,1,1111)\ncp 10: (D,3,11111)"
        matched, first, _pairs = harness._checkpoint_score(answer, self.GOLD)
        self.assertEqual((matched, first), (1, 10))

    def test_missing_checkpoint_is_a_deviation(self):
        answer = "cp 5: (C,1,1111)"
        matched, first, _pairs = harness._checkpoint_score(answer, self.GOLD)
        self.assertEqual((matched, first), (1, 10))


class EndAnswerTest(unittest.TestCase):
    def test_last_line_wins(self):
        self.assertEqual(harness.extract_endanswer("Endantwort: 111"), "111")
        self.assertEqual(
            harness.extract_endanswer("Endantwort: 12\nnoch was\nEndantwort: 111"),
            "111",
        )

    def test_missing(self):
        self.assertIsNone(harness.extract_endanswer("keine Antwort"))

    def test_normalization(self):
        self.assertEqual(harness._normalize_value("111."), "111")
        self.assertEqual(harness._normalize_value("1,048,576"), "1048576")


class SheetExtractionTest(unittest.TestCase):
    def test_fenced_block_wins(self):
        text = "Hier:\n```\nh1: (1 = 1)\n```\nende"
        self.assertEqual(harness.extract_sheet_text(text).strip(), "h1: (1 = 1)")

    def test_plain_text(self):
        self.assertEqual(harness.extract_sheet_text("h1: (1 = 1)"), "h1: (1 = 1)")


class PromptBuilderTest(unittest.TestCase):
    TASK_A = {"id": "A-0001", "tier": "A", "prompt": "Berechne st(27).", "expected": "111"}
    TASK_TRACE = {
        "id": "B-0001",
        "tier": "B",
        "tier_b_kind": "trace",
        "machine": "0LA0LA",
        "checkpoints_t": [1, 2],
        "prompt": "Simuliere.",
    }
    TASK_CYC = {"id": "B-0011", "tier": "B", "tier_b_kind": "cyc", "certificate": [6, 16, 2], "prompt": "Zeige."}

    def test_arms_have_legends_and_conventions(self):
        for arm in ("K", "B", "C", "D"):
            system, user = prompts.build_messages(arm, self.TASK_A)
            self.assertTrue(system, arm)
            self.assertIn("Berechne st(27).", user)
        _system, user_k = prompts.build_messages("K", self.TASK_A)
        self.assertIn("Endantwort", user_k)

    def test_c_mentions_sim_cyc_aliases(self):
        system, _user = prompts.build_messages("C", self.TASK_CYC)
        self.assertIn("cyc(", system)
        self.assertIn("sim(0..t)", system)
        self.assertIn("st=collatz_steps", system)

    def test_trace_convention_is_in_every_arm(self):
        # Review finding I3: the cp-tuple convention must not live in K alone.
        for arm in ("K", "B", "C", "D"):
            system, _user = prompts.build_messages(arm, self.TASK_TRACE)
            self.assertIn("Kopfposition = ganze Zahl ab", system, arm)
            self.assertIn("Zellen sind 0", system, arm)

    def test_trace_convention_names_the_steps(self):
        _system, user = prompts.build_messages("C", self.TASK_TRACE)
        self.assertIn("1, 2", user)
        self.assertIn("sim(0..t)", user)


class CycScoringTest(unittest.TestCase):
    TASK = {
        "id": "B-0012",
        "tier": "B",
        "tier_b_kind": "cyc",
        "machine": "0LA0LA",
        "certificate": [0, 1, -1],
        "prompt": "Zeige.",
    }

    def test_sheet_must_bind_the_task_machine(self):
        good = "a: M = 0LA0LA\nh1: M zyklisch\nv h1: cyc(0,1,-1)\nh1+\nCLAIM c1: M zyklisch\nWITNESS c1: ref h1\n[HALT] c1"
        record = harness.evaluate_run("C", self.TASK, {"content": good}, 1.0, None, None)
        self.assertTrue(record["machine_bound"])
        self.assertTrue(record["solved"])

    def test_other_machine_does_not_count(self):
        wrong = "a: M = 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC\nh1: M zyklisch\nv h1: cyc(6,16,2)\nh1+\nCLAIM c1: M zyklisch\nWITNESS c1: ref h1\n[HALT] c1"
        record = harness.evaluate_run("C", self.TASK, {"content": wrong}, 1.0, None, None)
        self.assertFalse(record["machine_bound"])
        self.assertFalse(record["solved"])

    def test_extra_unrelated_binding_does_not_count(self):
        extra = (
            "a: M = 0LA0LA\na: N = 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC\n"
            "h1: M zyklisch\nv h1: cyc(0,1,-1)\nh1+\n"
            "CLAIM c1: M zyklisch\nWITNESS c1: ref h1\n[HALT] c1"
        )
        record = harness.evaluate_run("C", self.TASK, {"content": extra}, 1.0, None, None)
        self.assertFalse(record["machine_bound"])
        self.assertFalse(record["solved"])

    def test_witness_kind_and_text_are_persisted(self):
        good = "a: M = 0LA0LA\nh1: M zyklisch\nv h1: cyc(0,1,-1)\nh1+\nCLAIM c1: M zyklisch\nWITNESS c1: ref h1\n[HALT] c1"
        record = harness.evaluate_run("C", self.TASK, {"content": good}, 1.0, None, None)
        self.assertEqual(record["v"][0]["kind"], "cyc")
        self.assertEqual(record["v"][0]["witness"], "cyc(0,1,-1)")
        self.assertEqual(record["claims"][0]["witness"], "ref h1")


if __name__ == "__main__":
    unittest.main()

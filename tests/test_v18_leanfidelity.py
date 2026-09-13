#!/usr/bin/env python3
"""Tests der Lean-Fidelity-Metrik V18 (Denkspur/reasoning_content + sichtbare Zone).

Die Metrik ist ein heuristischer Parser analog rcfidelity: er klassifiziert
Zeilen als Taktik-Zeile (erste Wortmarke ein Lean-Taktik-Schluesselwort),
Statement-Zeile (theorem/lemma/import/... oder ``:=``-Bindung),
Kommentar-Zeile (``--``) und Prosa -- und meldet Anteile plus
Degenerations-Marker. Bewusst konservativ: nackte Formeln ohne
Lean-Schluesselwort zaehlen als Prosa (die Metrik ist eine Untergrenze).
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

if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


leanfidelity = _load("leanfidelity")

# --- Fixtures ---------------------------------------------------------------

RC_PROSE = "\n".join(
    [
        "We need compute the sum of the two large numbers.",
        "First we align the digits.",
        "Then we add column by column, carrying where needed.",
        "Finally we write down the result carefully.",
    ]
)

RC_TACTIC = "\n".join(
    [
        "have h1 : 2 + 2 = 4 := by decide",
        "have h2 : (2 ^ 10) = 1024 := by decide",
        "rw [h2] at h1",
        "exact h1",
    ]
)

RC_STATEMENT = "\n".join(
    [
        "import Std",
        "theorem main_thm : (837465291837 + 192837465564) = 1030302757401 := by decide",
    ]
)

MIXED_PROSE = ["We need check the claim.", "Let me reduce it step by step."]
MIXED_LEAN = [
    "have h1 : 2 + 2 = 4 := by decide",
    "exact h1",
]
RC_MIXED = "\n".join(MIXED_PROSE + MIXED_LEAN)

RC_DEGENERATE = "have h1 : True := trivial\n" * 3 + "We need think again.\n"

RC_TRAILING = "\n".join(
    ["We check the statement now.", "have h1 : 2 + 2 = 4 := by decide", "exact h1"]
)

RC_TRAILING_STOPS = "\n".join(
    ["have h1 : 2 + 2 = 4 := by decide", "exact h1", "Und damit sind wir fertig."]
)


class ParseLeanTextTest(unittest.TestCase):
    """Zeilen-Klassifikation und Anteile auf synthetischen Texten."""

    def test_prose_only(self):
        metrics = leanfidelity.parse_lean_text(RC_PROSE)
        self.assertEqual(metrics["lines"], 4)
        self.assertEqual(metrics["tactic_lines"], 0)
        self.assertEqual(metrics["statement_lines"], 0)
        self.assertEqual(metrics["prose_lines"], 4)
        self.assertEqual(metrics["lean_line_share"], 0.0)
        self.assertEqual(metrics["lean_char_share"], 0.0)
        self.assertEqual(metrics["prose_run_max"], 4)
        self.assertIsNone(metrics["first_lean_line_index"])
        self.assertEqual(metrics["repeat_extra"], 0)

    def test_tactic_only(self):
        metrics = leanfidelity.parse_lean_text(RC_TACTIC)
        self.assertEqual(metrics["lines"], 4)
        self.assertEqual(metrics["tactic_lines"], 4)
        self.assertEqual(metrics["prose_lines"], 0)
        self.assertEqual(metrics["lean_line_share"], 1.0)
        self.assertEqual(metrics["tactic_line_share"], 1.0)
        self.assertEqual(metrics["lean_char_share"], 1.0)
        self.assertEqual(metrics["first_lean_line_index"], 0)
        self.assertEqual(metrics["trailing_lean_block"], 4)
        self.assertEqual(metrics["lean_run_max"], 4)
        self.assertEqual(metrics["prose_run_max"], 0)

    def test_statement_lines(self):
        metrics = leanfidelity.parse_lean_text(RC_STATEMENT)
        self.assertEqual(metrics["lines"], 2)
        self.assertEqual(metrics["statement_lines"], 2)
        self.assertEqual(metrics["tactic_lines"], 0)
        self.assertEqual(metrics["lean_line_share"], 1.0)

    def test_mixed_with_lean_tail(self):
        metrics = leanfidelity.parse_lean_text(RC_MIXED)
        self.assertEqual(metrics["lines"], 4)
        self.assertEqual(metrics["prose_lines"], 2)
        self.assertEqual(metrics["tactic_lines"], 2)
        self.assertEqual(metrics["lean_line_share"], 0.5)
        self.assertEqual(metrics["first_lean_line_index"], 2)
        self.assertAlmostEqual(metrics["first_lean_line_frac"], 0.5, places=4)
        self.assertEqual(metrics["trailing_lean_block"], 2)
        self.assertEqual(metrics["prose_run_max"], 2)

    def test_degeneration_markers(self):
        metrics = leanfidelity.parse_lean_text(RC_DEGENERATE)
        self.assertEqual(metrics["lines"], 4)
        self.assertEqual(metrics["tactic_lines"], 3)
        # Die drei identischen Taktik-Zeilen bilden einen Lauf der Laenge 3:
        # zwei Wiederholungen ueber die erste Zeile hinaus.
        self.assertEqual(metrics["repeat_extra"], 2)
        self.assertEqual(metrics["lean_run_max"], 3)
        self.assertEqual(metrics["prose_run_max"], 1)

    def test_trailing_block_counts_lean_tail(self):
        metrics = leanfidelity.parse_lean_text(RC_TRAILING)
        self.assertEqual(metrics["trailing_lean_block"], 2)

    def test_trailing_block_stops_at_prose(self):
        metrics = leanfidelity.parse_lean_text(RC_TRAILING_STOPS)
        self.assertEqual(metrics["trailing_lean_block"], 0)

    def test_bare_formula_is_prose(self):
        # Konservativ: ohne Lean-Schluesselwort zaehlt eine nackte Formel als
        # Prosa -- die Metrik ist eine Untergrenze der Lean-Form.
        metrics = leanfidelity.parse_lean_text("2 + 2 = 4")
        self.assertEqual(metrics["prose_lines"], 1)
        self.assertEqual(metrics["lean_line_share"], 0.0)

    def test_binding_marks_statement(self):
        metrics = leanfidelity.parse_lean_text("result := 42")
        self.assertEqual(metrics["statement_lines"], 1)

    def test_comment_lines(self):
        metrics = leanfidelity.parse_lean_text("-- goal: 2 + 2 = 4\nhave h : 2 + 2 = 4 := by decide")
        self.assertEqual(metrics["comment_lines"], 1)
        self.assertEqual(metrics["tactic_lines"], 1)
        self.assertEqual(metrics["lean_line_share"], 1.0)

    def test_keyword_prefix_with_bracket(self):
        metrics = leanfidelity.parse_lean_text("rw[h2]\nsimp?\nexact_mod_cast h1")
        self.assertEqual(metrics["tactic_lines"], 3)

    def test_keyword_prefix_needs_word_boundary(self):
        metrics = leanfidelity.parse_lean_text("user data\nfirstly we note\nextend the list")
        self.assertEqual(metrics["tactic_lines"], 0)
        self.assertEqual(metrics["prose_lines"], 3)

    def test_blank_lines_ignored(self):
        metrics = leanfidelity.parse_lean_text("have h : True := trivial\r\n\r\nexact h\r\n")
        self.assertEqual(metrics["lines"], 2)

    def test_empty_text(self):
        metrics = leanfidelity.parse_lean_text("")
        self.assertEqual(metrics["lines"], 0)
        self.assertEqual(metrics["lean_line_share"], 0.0)
        self.assertIsNone(metrics["first_lean_line_index"])

    def test_adversarial_long_line(self):
        # Kein ReDoS: eine 100k-Zeichen-Zeile wird verarbeitet (Scanner).
        text = "have" + "x" * 100000
        metrics = leanfidelity.parse_lean_text(text)
        self.assertEqual(metrics["lines"], 1)
        self.assertEqual(metrics["tactic_lines"], 0)

    def test_longest_line(self):
        line = "have " + "x" * 4995
        metrics = leanfidelity.parse_lean_text(line)
        self.assertEqual(metrics["longest_line_len"], 5000)


class AnalyzeRunsTest(unittest.TestCase):
    """Aggregation ueber einen synthetischen Lauf-Baum."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _make_run(self, root, task, arm, rep, rc_text, answer_text="Endantwort: 4", tokens=90, raw=True):
        run_dir = root / task / f"{arm}-rep{rep}"
        (run_dir / "round0").mkdir(parents=True, exist_ok=True)
        summary = {
            "task_id": task,
            "arm": arm,
            "tier": task[0],
            "rep": rep,
            "max_repairs": 0,
            "rounds": [
                {
                    "round": 0,
                    "solved": True,
                    "trigger": None,
                    "error": None,
                    "duration_s": 1.0,
                    "completion_tokens": tokens + 10,
                    "reasoning_tokens": tokens,
                    "format_errors": 0,
                }
            ],
            "final_solved": True,
            "rounds_to_ok": 0,
            "repairs_used": 0,
            "triggered_rounds": [],
            "transport_retries": 0,
            "total_completion_tokens": tokens + 10,
            "total_reasoning_tokens": tokens,
            "total_duration_s": 1.0,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (run_dir / "round0" / "parsed.json").write_text("{}", encoding="utf-8")
        if raw:
            raw_payload = {
                "choices": [
                    {"message": {"content": answer_text, "reasoning_content": rc_text}}
                ]
            }
            (run_dir / "round0" / "raw.json").write_text(json.dumps(raw_payload), encoding="utf-8")
        return run_dir

    def test_aggregates_per_arm_and_tier(self):
        root = self._root()
        self._make_run(root, "A3-0001", "L0", 1, RC_PROSE, tokens=100)
        self._make_run(root, "A3-0001", "L2", 1, RC_TACTIC, tokens=200)
        report = leanfidelity.analyze_runs(root)
        arms = report["per_arm"]
        self.assertIn("L0-A", arms)
        self.assertIn("L2-A", arms)
        self.assertEqual(arms["L0-A"]["rc_lean_line_share_mean"], 0.0)
        self.assertEqual(arms["L2-A"]["rc_lean_line_share_mean"], 1.0)
        self.assertEqual(arms["L2-A"]["rc_tactic_line_share_mean"], 1.0)
        self.assertEqual(arms["L0-A"]["reasoning_tokens_sum"], 100)
        self.assertEqual(arms["L2-A"]["reasoning_tokens_sum"], 200)

    def test_missing_raw_counts_as_missing(self):
        root = self._root()
        self._make_run(root, "A3-0001", "L0", 1, RC_PROSE, raw=False)
        report = leanfidelity.analyze_runs(root)
        self.assertEqual(report["per_arm"]["L0-A"]["rc_missing"], 1)

    def test_corrupt_raw_is_failsafe(self):
        root = self._root()
        run_dir = self._make_run(root, "A3-0001", "L0", 1, RC_PROSE)
        (run_dir / "round0" / "raw.json").write_text("{not json", encoding="utf-8")
        report = leanfidelity.analyze_runs(root)
        self.assertEqual(report["per_arm"]["L0-A"]["rc_missing"], 1)

    def test_answer_metrics_present(self):
        root = self._root()
        self._make_run(root, "A3-0001", "L2", 1, RC_PROSE, answer_text="have h1 : 1 = 1 := rfl")
        report = leanfidelity.analyze_runs(root)
        self.assertEqual(report["per_arm"]["L2-A"]["answer_lean_line_share_mean"], 1.0)

    def test_markdown_renders(self):
        root = self._root()
        self._make_run(root, "A3-0001", "L2", 1, RC_TACTIC)
        md = leanfidelity.render_markdown(leanfidelity.analyze_runs(root))
        self.assertIn("L2-A", md)
        self.assertIn("Lean-Zeilen", md)


if __name__ == "__main__":
    unittest.main()

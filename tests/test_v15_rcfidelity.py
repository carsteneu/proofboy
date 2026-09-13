#!/usr/bin/env python3
"""Tests der RC-Fidelity-Metrik V15 (Denkspur/reasoning_content, Metrik h).

Die Metrik ist ein heuristischer Parser: er klassifiziert die Zeilen des
``reasoning_content`` in V1.1-Tag-Zeilen (g/d/a/c/h/v/q/=), v-Zeilen,
Status-Mini-Zeilen, V1-Altzeilen (S<n>), Claim-Zeilen (Blatt-Entwurf im RC)
und Prosa -- und meldet Anteile plus Degenerations-Marker.

Geprueft wird gegen synthetische RC-Texte (Prosa, strikt, gemischt,
degeneriert), die Analyse-Funktion auf einem synthetischen Lauf-Baum und der
CLI-Pfad (JSON+Markdown-Ausgabe).
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
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


rcfidelity = _load("rcfidelity")

# --- Fixtures ---------------------------------------------------------------

RC_PROSE = "\n".join(
    [
        "We need compute the remainder of the product modulo the prime.",
        "Let us do it carefully.",
        "First we reduce both factors.",
        "Then we multiply the residues.",
        "Finally we take the remainder.",
    ]
)

RC_STRICT = "\n".join(
    [
        "g: st(27)?",
        "d: st(n) = Schritte bis 1",
        "a: n=27",
        "h1: st(27)=111",
        "v h1: auto",
        "h1+",
        "=: st(27)=111 (h1+)",
    ]
)

# Gemischt: zwei Prosa-Zeilen, dann der Blatt-Entwurf als Tag-Block.
MIXED_PROSE = ["We need solve the task.", "Let me think about the machine."]
MIXED_NOTATION = [
    "a: M = 0LA0LA",
    "h1: M zyklisch",
    "v h1: cyc(0,1,-1)",
    "h1+",
]
RC_MIXED = "\n".join(MIXED_PROSE + MIXED_NOTATION)

RC_DEGENERATE = (
    "g:\n" * 2
    + "We need to check everything very carefully again and again.\n" * 3
).strip()

RC_V1_DRAFT = "\n".join(
    [
        "We need compute and then write S lines.",
        "S1: ? Kandidat 111 pruefen",
        "CLAIM c1: (collatz_steps(27) = 111)",
        "WITNESS c1: auto",
        "[HALT] c1",
    ]
)

# Ein komplettes Blatt in der Denkspur: endet mit der Claim-Zone, die der
# Blatt-Parser verlangt ([HALT] ist die letzte Zeile jedes Blattes).
RC_SHEET_FULL = "\n".join(
    [
        "g: cp 1: (B,1,1)?",
        "a: M = 1RB1RZ_0LA0LA",
        "h1: cp 1: (B,1,1)",
        "v h1: sim(0..1)",
        "h1+",
        "CLAIM c1: cp 1: (B,1,1)",
        "WITNESS c1: ref h1",
        "[HALT] c1",
    ]
)


class ParseRcTest(unittest.TestCase):
    """Zeilen-Klassifikation und Anteile auf synthetischen Texten."""

    def test_prose_only(self):
        metrics = rcfidelity.parse_rc(RC_PROSE)
        self.assertEqual(metrics["lines"], 5)
        self.assertEqual(metrics["tag_lines"], 0)
        self.assertEqual(metrics["v_lines"], 0)
        self.assertEqual(metrics["status_lines"], 0)
        self.assertEqual(metrics["prose_lines"], 5)
        self.assertEqual(metrics["tag_line_share"], 0.0)
        self.assertEqual(metrics["notation_line_share"], 0.0)
        self.assertEqual(metrics["notation_char_share"], 0.0)
        self.assertEqual(metrics["prose_run_max"], 5)
        self.assertIsNone(metrics["first_notation_line_index"])
        self.assertEqual(metrics["empty_tag_lines"], 0)
        self.assertEqual(metrics["repeat_extra"], 0)

    def test_strict_notation(self):
        metrics = rcfidelity.parse_rc(RC_STRICT)
        self.assertEqual(metrics["lines"], 7)
        self.assertEqual(metrics["tag_lines"], 5)
        self.assertEqual(metrics["v_lines"], 1)
        self.assertEqual(metrics["status_lines"], 1)
        self.assertEqual(metrics["prose_lines"], 0)
        # (tag + v) / lines = 6/7
        self.assertAlmostEqual(metrics["tag_line_share"], 6 / 7, places=4)
        self.assertEqual(metrics["notation_line_share"], 1.0)
        self.assertEqual(metrics["notation_char_share"], 1.0)
        self.assertEqual(metrics["first_notation_line_index"], 0)
        self.assertEqual(metrics["trailing_notation_block"], 7)
        self.assertEqual(metrics["prose_run_max"], 0)

    def test_mixed_with_draft_tail(self):
        metrics = rcfidelity.parse_rc(RC_MIXED)
        self.assertEqual(metrics["lines"], 6)
        self.assertEqual(metrics["prose_lines"], 2)
        self.assertEqual(metrics["tag_lines"], 2)
        self.assertEqual(metrics["v_lines"], 1)
        self.assertEqual(metrics["status_lines"], 1)
        self.assertAlmostEqual(metrics["tag_line_share"], 3 / 6, places=4)
        expected_char_share = sum(map(len, MIXED_NOTATION)) / (
            sum(map(len, MIXED_NOTATION)) + sum(map(len, MIXED_PROSE))
        )
        self.assertAlmostEqual(
            metrics["notation_char_share"], expected_char_share, places=4
        )
        self.assertEqual(metrics["first_notation_line_index"], 2)
        self.assertAlmostEqual(
            metrics["first_notation_line_frac"], 2 / 6, places=4
        )
        self.assertEqual(metrics["trailing_notation_block"], 4)
        self.assertEqual(metrics["prose_run_max"], 2)

    def test_degeneration_markers(self):
        metrics = rcfidelity.parse_rc(RC_DEGENERATE)
        self.assertEqual(metrics["lines"], 5)
        self.assertEqual(metrics["empty_tag_lines"], 2)
        # Die drei identischen Prosa-Zeilen bilden einen Lauf der Laenge 3:
        # zwei Wiederholungen ueber die erste Zeile hinaus.
        self.assertEqual(metrics["repeat_extra"], 2)
        self.assertAlmostEqual(metrics["tag_line_share"], 2 / 5, places=4)
        self.assertEqual(metrics["prose_run_max"], 3)

    def test_v1_draft_lines_and_claim_zone(self):
        metrics = rcfidelity.parse_rc(RC_V1_DRAFT)
        self.assertEqual(metrics["lines"], 5)
        self.assertEqual(metrics["legacy_s_lines"], 1)
        self.assertEqual(metrics["claim_lines"], 3)
        self.assertEqual(metrics["prose_lines"], 1)
        self.assertEqual(metrics["tag_lines"], 0)
        self.assertEqual(metrics["tag_line_share"], 0.0)
        # Der Entwurf zaehlt nicht als Notation: die Metrik misst V1.1-Koepfe.
        self.assertEqual(metrics["notation_char_share"], 0.0)

    def test_trailing_block_includes_the_claim_zone(self):
        # Der Blatt-Entwurf endet mit CLAIM/WITNESS/[HALT]; ohne die
        # Claim-Zeilen im Trailing-Lauf waere der Entwurf unsichtbar.
        metrics = rcfidelity.parse_rc(RC_SHEET_FULL)
        self.assertEqual(metrics["lines"], 8)
        self.assertEqual(metrics["prose_lines"], 0)
        self.assertEqual(metrics["trailing_notation_block"], 8)
        self.assertEqual(metrics["claim_lines"], 3)

    def test_trailing_block_stops_at_prose(self):
        text = "\n".join(["CLAIM c1: x = 1", "WITNESS c1: auto", "[HALT] c1", "Und fertig."])
        metrics = rcfidelity.parse_rc(text)
        self.assertEqual(metrics["trailing_notation_block"], 0)

    def test_longest_line(self):
        line = "a: " + "x" * 4997
        metrics = rcfidelity.parse_rc(line)
        self.assertEqual(metrics["longest_line_len"], 5000)

    def test_empty_text(self):
        metrics = rcfidelity.parse_rc("")
        self.assertEqual(metrics["lines"], 0)
        self.assertEqual(metrics["tag_line_share"], 0.0)
        self.assertEqual(metrics["notation_char_share"], 0.0)
        self.assertIsNone(metrics["first_notation_line_index"])

    def test_v_line_needs_target_and_colon(self):
        for bad in ("v h1 auto", "v:", "v1:", "v", "val: x"):
            metrics = rcfidelity.parse_rc(bad)
            self.assertEqual(metrics["v_lines"], 0, bad)

    def test_status_line_needs_suffix_and_digit(self):
        metrics = rcfidelity.parse_rc("h2-\nh2\n+\nc3?\n=2!")
        self.assertEqual(metrics["status_lines"], 3)
        self.assertEqual(metrics["prose_lines"], 2)

    def test_adversarial_line_terminates(self):
        # Kein ReDoS: eine 100k-Zeichen-Zeile mit v+-Kopf wird verarbeitet
        # (Scanner, keine Regex). Die Laufzeit-Linearitaet wurde separat
        # gemessen (50k Zeichen ~2,5 ms; 800k ~40 ms); hier nur Semantik.
        text = "v" + "1" * 50000 + " " + "a" * 50000
        metrics = rcfidelity.parse_rc(text)
        self.assertEqual(metrics["lines"], 1)
        self.assertEqual(metrics["v_lines"], 0)

    def test_crlf_and_blank_lines(self):
        metrics = rcfidelity.parse_rc("g: a\r\n\r\nh1: b\r\n")
        self.assertEqual(metrics["lines"], 2)
        self.assertEqual(metrics["tag_lines"], 2)


class AnalyzeRunsTest(unittest.TestCase):
    """Aggregation ueber einen synthetischen Lauf-Baum."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _make_run(self, root, task, arm, rep, rc_text, tokens=90, raw=True):
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
                "choices": [{"message": {"content": "x", "reasoning_content": rc_text}}]
            }
            (run_dir / "round0" / "raw.json").write_text(
                json.dumps(raw_payload), encoding="utf-8"
            )
        return run_dir

    def test_aggregates_per_arm_and_tier(self):
        root = self._root()
        self._make_run(root, "A3-9001", "C1", 1, RC_STRICT, tokens=100)
        self._make_run(root, "B3-9002", "C1", 1, RC_MIXED, tokens=200)
        self._make_run(root, "B3-9003", "C0", 1, RC_PROSE, tokens=300)
        report = rcfidelity.analyze_runs(root)
        per_arm = report["per_arm"]
        self.assertIn("C1-A", per_arm)
        self.assertIn("C1-B", per_arm)
        self.assertIn("C0-B", per_arm)
        self.assertEqual(per_arm["C1-A"]["n_rounds"], 1)
        self.assertEqual(per_arm["C1-A"]["tag_line_share_mean"], round(6 / 7, 4))
        self.assertEqual(per_arm["C0-B"]["tag_line_share_mean"], 0.0)
        self.assertEqual(per_arm["C1-B"]["reasoning_tokens_sum"], 200)
        self.assertEqual(per_arm["C0-B"]["reasoning_tokens_sum"], 300)

    def test_missing_raw_is_counted_not_crashing(self):
        root = self._root()
        self._make_run(root, "B3-9002", "C2", 1, "", tokens=50, raw=False)
        report = rcfidelity.analyze_runs(root)
        self.assertEqual(report["per_arm"]["C2-B"]["n_rounds"], 1)
        self.assertEqual(report["per_arm"]["C2-B"]["n_rc"], 0)
        self.assertEqual(report["per_arm"]["C2-B"]["rc_missing"], 1)

    def test_unreadable_raw_is_counted_not_crashing(self):
        root = self._root()
        run_dir = self._make_run(root, "B3-9002", "C2", 1, "x")
        (run_dir / "round0" / "raw.json").write_bytes(b'\xff\xfe{"kaputt')
        report = rcfidelity.analyze_runs(root)
        self.assertEqual(report["per_arm"]["C2-B"]["rc_missing"], 1)

    def test_malformed_message_shapes_are_missing(self):
        root = self._root()
        run_dir = self._make_run(root, "B3-9002", "C1", 1, "x")
        payloads = [
            {"choices": [{"message": None}]},
            {"choices": [{"message": {"reasoning_content": 42}}]},
            {"choices": [{"message": {"reasoning_content": {"a": 1}}}]},
            {"choices": ["kaputt"]},
        ]
        for payload in payloads:
            (run_dir / "round0" / "raw.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            report = rcfidelity.analyze_runs(root)
            self.assertEqual(
                report["per_arm"]["C1-B"]["rc_missing"], 1, str(payload)[:60]
            )

    def test_cli_writes_json_and_markdown(self):
        root = self._root()
        self._make_run(root, "B3-9002", "C1", 1, RC_MIXED)
        out_json = root / "report.json"
        out_md = root / "report.md"
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLING / "rcfidelity.py"),
                "--runs",
                str(root),
                "--json",
                str(out_json),
                "--markdown",
                str(out_md),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertIn("per_arm", payload)
        text = out_md.read_text(encoding="utf-8")
        self.assertIn("C1-B", text)
        self.assertIn("Notation", text)


if __name__ == "__main__":
    unittest.main()

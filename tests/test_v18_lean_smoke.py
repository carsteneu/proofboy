#!/usr/bin/env python3
"""Tests des Latent-Lean-Smoke-Runners V18.

Der Runner schickt 16 kurze Sonden ("Schreibe Lean-4-Code, der <Aussage>
beweist") an das Modell, extrahiert den Code aus der Antwort und elaboriert
ihn mit leancheck. Geprueft werden Extraktion, Aggregation und der
Orchestrierungspfad mit geskriptetem Transport und geskriptetem leancheck
(kein Netz, kein Lean noetig).
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


lean_smoke = _load("lean_smoke")


class ExtractCodeTest(unittest.TestCase):
    def test_fenced_lean_block(self):
        answer = "Hier ist der Code:\n```lean\nimport Std\n\ntheorem main_thm : True := trivial\n```\n"
        self.assertEqual(
            lean_smoke.extract_lean_code(answer),
            "import Std\n\ntheorem main_thm : True := trivial",
        )

    def test_fenced_plain_block(self):
        answer = "```\nimport Std\ntheorem main_thm : True := trivial\n```"
        self.assertIn("theorem main_thm", lean_smoke.extract_lean_code(answer))

    def test_no_fence_uses_full_text(self):
        code = "import Std\n\ntheorem main_thm : True := trivial"
        self.assertEqual(lean_smoke.extract_lean_code(code), code)

    def test_largest_block_wins(self):
        answer = "```lean\nx\n```\ntext\n```lean\nimport Std\ntheorem main_thm : True := trivial\n```"
        self.assertIn("import Std", lean_smoke.extract_lean_code(answer))

    def test_empty_answer(self):
        self.assertEqual(lean_smoke.extract_lean_code(""), "")


class SummarizeTest(unittest.TestCase):
    def _entry(self, status, axioms=None, error=None, sorry=False):
        return {
            "id": f"p-{status}",
            "statement": "x",
            "error": error,
            "lean": None if status == "no_code" else {"status": status, "axioms": axioms, "sorry_used": sorry},
        }

    def test_counts(self):
        results = [
            self._entry("valid", "none"),
            self._entry("valid", ["propext", "Quot.sound"]),
            self._entry("invalid"),
            self._entry("timeout"),
            self._entry("no_code"),
            self._entry("valid", ["sorryAx"], sorry=True),
        ]
        summary = lean_smoke.summarize(results)
        self.assertEqual(summary["n"], 6)
        self.assertEqual(summary["valid"], 3)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["timeout"], 1)
        self.assertEqual(summary["no_code"], 1)
        self.assertEqual(summary["axiom_free"], 1)
        self.assertEqual(summary["sorry_used"], 1)
        self.assertEqual(summary["valid_frac"], 0.5)

    def test_transport_error_counted(self):
        results = [self._entry("invalid", error="URLError: boom")]
        summary = lean_smoke.summarize(results)
        self.assertEqual(summary["transport_errors"], 1)

    def test_exit_code_signals_transport_failures_only(self):
        # invalid/timeout/no_code sind Messergebnisse, kein Werkzeug-Fehlschlag.
        self.assertEqual(lean_smoke.exit_code({"transport_errors": 0, "invalid": 3, "timeout": 1}), 0)
        self.assertEqual(lean_smoke.exit_code({"transport_errors": 1}), 1)

    def test_render_labels_transport_failures_under_no_code(self):
        results = [self._entry("valid", "none")]
        summary = lean_smoke.summarize(results)
        summary["no_code"] = 2
        summary["transport_errors"] = 1
        md = lean_smoke.render_summary(summary, results)
        self.assertIn("ohne Code 2 (davon Transportfehler 1)", md)


class ProbesTest(unittest.TestCase):
    def test_probe_list_shape(self):
        self.assertEqual(len(lean_smoke.PROBES), 16)
        ids = [probe["id"] for probe in lean_smoke.PROBES]
        self.assertEqual(len(set(ids)), 16)
        for probe in lean_smoke.PROBES:
            self.assertTrue(probe["statement"].strip())

    def test_statements_avoid_mathlib_only_syntax(self):
        # ℕ/ℚ etc. sind ohne Mathlib nicht verfuegbar (HAdd ℕ … schlaegt fehl);
        # die Sonden muessen Std-tauglich formuliert bleiben.
        for probe in lean_smoke.PROBES:
            self.assertNotIn("ℕ", probe["statement"], probe["id"])

    def test_prompt_contains_statement(self):
        prompt = lean_smoke.build_prompt(lean_smoke.PROBES[0])
        self.assertIn(lean_smoke.PROBES[0]["statement"], prompt)
        self.assertIn("main_thm", prompt)


class RunProbesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_pipeline_with_scripted_call_and_check(self):
        calls = []

        def fake_call(messages, timeout):
            calls.append(messages)
            return (
                {"content": "```lean\nimport Std\ntheorem main_thm : True := trivial\n```", "reasoning": "r", "usage": {"completion_tokens": 11, "completion_tokens_details": {"reasoning_tokens": 3}}, "finish_reason": "stop"},
                {"choices": [{"message": {"content": "x"}}]},
                1.5,
                None,
            )

        def fake_check(source, **kwargs):
            return {"status": "valid", "axioms": "none", "sorry_used": False, "errors": [], "warnings": [], "snippet_lines": source.count("\n"), "file": str(self.tmp / "s.lean")}

        result = lean_smoke.run_probes(
            call=fake_call,
            check=fake_check,
            probes=lean_smoke.PROBES[:2],
            out_dir=self.tmp / "out",
        )
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["summary"]["valid"], 2)
        self.assertEqual(result["summary"]["axiom_free"], 2)
        self.assertTrue((self.tmp / "out" / "results.json").exists())
        self.assertTrue((self.tmp / "out" / "summary.md").exists())
        saved = json.loads((self.tmp / "out" / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["results"]), 2)
        self.assertIn("main_thm", calls[0][1]["content"])

    def test_no_code_skips_leancheck(self):
        def fake_call(messages, timeout):
            return ({"content": "", "reasoning": "", "usage": {}, "finish_reason": "stop"}, {}, 0.1, None)

        def failing_check(source, **kwargs):
            raise AssertionError("leancheck darf bei leerem Code nicht laufen")

        result = lean_smoke.run_probes(
            call=fake_call, check=failing_check, probes=lean_smoke.PROBES[:1], out_dir=self.tmp / "out2"
        )
        self.assertEqual(result["summary"]["no_code"], 1)

    def test_transport_error_is_failsafe(self):
        def fake_call(messages, timeout):
            return (None, None, 0.2, "URLError: down")

        result = lean_smoke.run_probes(
            call=fake_call, check=mock.Mock(), probes=lean_smoke.PROBES[:1], out_dir=self.tmp / "out3"
        )
        self.assertEqual(result["summary"]["transport_errors"], 1)
        self.assertEqual(result["summary"]["no_code"], 1)

    def test_print_axioms_only_when_main_thm_present(self):
        seen = []

        def fake_call(messages, timeout):
            return ({"content": "import Std", "reasoning": "", "usage": {}, "finish_reason": "stop"}, {}, 0.1, None)

        def fake_check(source, **kwargs):
            seen.append(kwargs.get("print_axioms_for"))
            return {"status": "valid", "axioms": None, "sorry_used": False, "errors": [], "warnings": [], "snippet_lines": 1, "file": "x"}

        lean_smoke.run_probes(call=fake_call, check=fake_check, probes=lean_smoke.PROBES[:1], out_dir=self.tmp / "out4")
        self.assertEqual(seen, [None])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests des Lean-Mandat-Runners V19.

Der Runner schickt eine Matrix (Prompt-Varianten V-A..V-E x Aufgaben-Grade x
Wiederholungen) direkt an das Modell, extrahiert den Lean-Code aus der
sichtbaren Antwort, misst die Denkspur mit `leanfidelity` und elaboriert den
Code mit `leancheck`. Geprueft werden die Varianten-/Aufgaben-Definitionen,
die Extraktion (inkl. Prefill-Echo), die Aggregation, der Orchestrierungspfad
mit geskriptetem Transport (kein Netz) und die deterministischen Renderer.
Die Referenzbeweise der Aufgaben werden einmal echt elaboriert (skipWithout
Lake-Toolchain).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
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


lean_mandat = _load("lean_mandat")


def _lake_available():
    if shutil.which("lake"):
        return True
    return (Path.home() / ".elan" / "bin" / "lake").exists()


class VariantsTest(unittest.TestCase):
    def test_five_variants_in_ladder_order(self):
        self.assertEqual(list(lean_mandat.VARIANTS), ["V-A", "V-B", "V-C", "V-D", "V-E"])

    def test_a_is_lean_written_rules(self):
        system = lean_mandat.VARIANTS["V-A"]["system"]
        self.assertTrue(system.startswith("-- SYSTEM PROMPT (Lean 4, Core/Std)"))
        self.assertIn("-- REGELN (MANDATORY", system)
        self.assertIn("Prosa ist ein Kompilierfehler", system)

    def test_b_adds_exactly_one_trace_example(self):
        system_b = lean_mandat.VARIANTS["V-B"]["system"]
        self.assertTrue(system_b.startswith(lean_mandat.VARIANTS["V-A"]["system"]))
        self.assertIn("have h1 : 12 + 30 = 42 := by decide", system_b)
        self.assertNotIn("have h1 : 12 + 30 = 42 := by decide", lean_mandat.VARIANTS["V-A"]["system"])

    def test_c_extends_b_with_three_examples(self):
        system_c = lean_mandat.VARIANTS["V-C"]["system"]
        self.assertTrue(system_c.startswith(lean_mandat.VARIANTS["V-B"]["system"]))
        self.assertIn("have h1 : 12 + 30 = 42 := by decide", system_c)
        self.assertIn("have a : 7 * 6 = 42 := by decide", system_c)
        self.assertIn("have b : 100 - 58 = 42 := by decide", system_c)

    def test_e_is_b_plus_fence_ban(self):
        system_e = lean_mandat.VARIANTS["V-E"]["system"]
        self.assertTrue(system_e.startswith(lean_mandat.VARIANTS["V-B"]["system"]))
        self.assertIn("```", system_e)
        self.assertIn("FENCES", system_e)

    def test_d_declares_prefill_others_do_not(self):
        for name, variant in lean_mandat.VARIANTS.items():
            if name == "V-D":
                self.assertTrue(variant["prefill"])
            else:
                self.assertFalse(variant["prefill"])


class BuildMessagesTest(unittest.TestCase):
    def test_plain_variant_builds_system_and_user(self):
        task = lean_mandat.TASKS[0]
        messages = lean_mandat.build_messages("V-A", task)
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        user = messages[1]["content"]
        self.assertIn(task["statement"], user)
        self.assertIn("main_thm", user)
        self.assertIn("import Std", user)

    def test_prefill_variant_appends_assistant_skeleton(self):
        task = lean_mandat.TASKS[1]
        messages = lean_mandat.build_messages("V-D", task)
        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant"])
        skeleton = messages[2]["content"]
        self.assertIn(f"have h1 : {task['statement']} := by ", skeleton)
        self.assertIn("theorem main_thm", skeleton)
        self.assertTrue(skeleton.rstrip().endswith(":= by"), skeleton)

    def test_tasks_give_distinct_prompts(self):
        first, second = lean_mandat.TASKS[0], lean_mandat.TASKS[5]
        self.assertNotEqual(
            lean_mandat.build_messages("V-A", first)[1]["content"],
            lean_mandat.build_messages("V-A", second)[1]["content"],
        )


class TasksTest(unittest.TestCase):
    def test_seven_tasks_two_two_three_by_grade(self):
        self.assertEqual(len(lean_mandat.TASKS), 7)
        ids = [task["id"] for task in lean_mandat.TASKS]
        self.assertEqual(len(set(ids)), 7)
        grades = {}
        for task in lean_mandat.TASKS:
            grades[task["grade"]] = grades.get(task["grade"], 0) + 1
            self.assertTrue(task["statement"].strip())
            self.assertTrue(task["ref_tactic"].strip())
        self.assertEqual(grades, {"trivial": 2, "mechanical": 2, "lemma": 3})

    def test_statements_avoid_mathlib_only_syntax(self):
        # Ohne Mathlib gibt es ℕ/ℚ nicht; die Aufgaben bleiben Std-tauglich.
        for task in lean_mandat.TASKS:
            self.assertNotIn("ℕ", task["statement"], task["id"])


class ManifestTest(unittest.TestCase):
    def test_default_manifest_shape_without_secrets(self):
        # Hermetisch: default_manifest liest PROOFBOY_TARGET/MAX_TOKENS aus der
        # Umgebung — die Testumgebung wird auf gueltige Werte gepinnt.
        with mock.patch.dict(
            os.environ, {"PROOFBOY_TARGET": "deepseek", "PROOFBOY_MAX_TOKENS": "4096"}
        ):
            manifest = lean_mandat.default_manifest()
        for key in ("target", "url", "model", "max_tokens"):
            self.assertIn(key, manifest)
        self.assertTrue(manifest["url"].startswith("http"))
        self.assertNotIn("key", manifest)


class CodeExtractTest(unittest.TestCase):
    def test_fenced_block_wins_and_flags(self):
        answer = "Hier:\n```lean\nimport Std\n\ntheorem main_thm : True := trivial\n```\n"
        code, fenced = lean_mandat.extract_code(answer)
        self.assertTrue(fenced)
        self.assertEqual(code, "import Std\n\ntheorem main_thm : True := trivial")

    def test_plain_fence_counts_as_fence(self):
        code, fenced = lean_mandat.extract_code("```\nimport Std\n```")
        self.assertTrue(fenced)
        self.assertIn("import Std", code)

    def test_unfenced_text_passes_through(self):
        code, fenced = lean_mandat.extract_code("import Std\n\ntheorem main_thm : True := trivial")
        self.assertFalse(fenced)
        self.assertEqual(code, "import Std\n\ntheorem main_thm : True := trivial")

    def test_largest_block_wins(self):
        answer = "```lean\nx\n```\ntext\n```lean\nimport Std\ntheorem main_thm : True := trivial\n```"
        code, _ = lean_mandat.extract_code(answer)
        self.assertIn("import Std", code)

    def test_empty_answer(self):
        self.assertEqual(lean_mandat.extract_code(""), ("", False))


class PrefillTest(unittest.TestCase):
    def test_strip_prefill_reports_echo(self):
        prefill = lean_mandat.build_prefill(lean_mandat.TASKS[0])
        full = prefill + "decide\n  exact h1"
        continuation, echoed = lean_mandat.strip_prefill(full, prefill)
        self.assertTrue(echoed)
        self.assertEqual(continuation, "decide\n  exact h1")

    def test_strip_prefill_without_echo(self):
        prefill = lean_mandat.build_prefill(lean_mandat.TASKS[0])
        text, echoed = lean_mandat.strip_prefill("import Std\n", prefill)
        self.assertFalse(echoed)
        self.assertEqual(text, "import Std\n")

    def test_strip_prefill_tolerates_whitespace_normalized_echo(self):
        prefill = lean_mandat.build_prefill(lean_mandat.TASKS[0])
        normalized = prefill.rstrip() + "decide"
        continuation, echoed = lean_mandat.strip_prefill(normalized, prefill)
        self.assertTrue(echoed)
        self.assertEqual(continuation, "decide")

    def test_statement_echo_normalizes_whitespace(self):
        self.assertTrue(lean_mandat.statement_echo("theorem main_thm : 2+3=5 := by decide", "2 + 3 = 5"))
        self.assertTrue(lean_mandat.statement_echo("theorem main_thm : 2 + 3 = 5 := by decide", "2 + 3 = 5"))
        self.assertFalse(lean_mandat.statement_echo("theorem main_thm : 2 + 3 = 6 := by decide", "2 + 3 = 5"))


class RunMatrixTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.manifest = {
            "target": "deepseek",
            "url": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-flash",
            "max_tokens": 4096,
        }

    def _scripted_call(self, calls):
        fence = "```lean"
        answer = (
            f"{fence}\nimport Std\n\ntheorem main_thm : 2 + 3 = 5 := by\n  decide\n```"
        )

        def fake_call(messages, timeout):
            calls.append(messages)
            if messages[-1]["role"] == "assistant":
                content = messages[-1]["content"] + "decide\n  exact h1"
            else:
                content = answer
            payload = {
                "content": content,
                "reasoning": "We need decide.\nhave h1 : 1 = 1 := by decide",
                "usage": {"completion_tokens": 40, "completion_tokens_details": {"reasoning_tokens": 12}},
                "finish_reason": "stop",
            }
            return payload, {"choices": [{"message": {"content": content}}]}, 1.5, None

        return fake_call

    def _scripted_check(self, seen):
        def fake_check(source, **kwargs):
            seen.append((source, kwargs))
            return {
                "status": "valid",
                "axioms": "none",
                "sorry_used": False,
                "errors": [],
                "warnings": [],
                "exit_code": 0,
                "duration_s": 0.4,
                "file": str(self.tmp / "s.lean"),
                "message": "",
                "output": "",
            }

        return fake_check

    def test_pipeline_writes_deterministic_artifacts(self):
        calls, seen = [], []
        result = lean_mandat.run_matrix(
            call=self._scripted_call(calls),
            check=self._scripted_check(seen),
            variants=["V-A", "V-D"],
            tasks=lean_mandat.TASKS[:2],
            reps=1,
            manifest=self.manifest,
            out_dir=self.tmp / "out",
        )
        self.assertEqual(len(result["results"]), 4)
        self.assertEqual(result["summary"]["overall"]["valid"], 4)
        self.assertEqual(result["summary"]["overall"]["axiom_free"], 4)
        self.assertEqual(result["summary"]["overall"]["fenced"], 2)
        # V-D: Echo erkannt, Elaborationsquelle traegt den Prefill-Rumpf.
        prefill_entries = [entry for entry in result["results"] if entry["variant"] == "V-D"]
        self.assertTrue(all(entry["prefill_echo"] for entry in prefill_entries))
        self.assertTrue(all("theorem main_thm" in entry["code"] for entry in prefill_entries))
        # Die Axiom-Sonde laeuft nur, wenn main_thm im Code steht.
        self.assertTrue(all(kwargs.get("print_axioms_for") == "main_thm" for _, kwargs in seen))
        for name in ("results.json", "summary.md", "raw.md"):
            self.assertTrue((self.tmp / "out" / name).exists(), name)
        saved = json.loads((self.tmp / "out" / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["manifest"], self.manifest)
        self.assertEqual(len(saved["results"]), 4)
        rendered = lean_mandat.render_summary(result["summary"])
        self.assertEqual((self.tmp / "out" / "summary.md").read_text(encoding="utf-8"), rendered)
        self.assertEqual(lean_mandat.render_raw_table(result["results"]), lean_mandat.render_raw_table(result["results"]))

    def test_axiom_free_counts_valid_entries_only(self):
        def entry(status, axioms):
            return {
                "variant": "V-A",
                "grade": "trivial",
                "usage": {},
                "rc": {},
                "error": None,
                "fenced": False,
                "statement_echo": False,
                "duration_s": 0.0,
                "lean": {"status": status, "axioms": axioms, "sorry_used": False},
            }

        summary = lean_mandat.summarize([entry("valid", "none"), entry("invalid", "none")])
        self.assertEqual(summary["overall"]["valid"], 1)
        self.assertEqual(summary["overall"]["axiom_free"], 1)

    def test_rc_metrics_come_from_leanfidelity(self):
        calls, seen = [], []
        result = lean_mandat.run_matrix(
            call=self._scripted_call(calls),
            check=self._scripted_check(seen),
            variants=["V-A"],
            tasks=lean_mandat.TASKS[:1],
            reps=1,
            manifest=self.manifest,
            out_dir=self.tmp / "out2",
        )
        entry = result["results"][0]
        self.assertEqual(entry["rc"]["lines"], 2)
        self.assertEqual(entry["rc"]["lean_line_share"], 0.5)
        self.assertEqual(entry["usage"]["completion_tokens_details"]["reasoning_tokens"], 12)
        self.assertTrue(entry["statement_echo"])

    def test_transport_error_is_failsafe(self):
        def failing_call(messages, timeout):
            return None, None, 0.2, "URLError: down"

        result = lean_mandat.run_matrix(
            call=failing_call,
            check=self._scripted_check([]),
            variants=["V-A"],
            tasks=lean_mandat.TASKS[:1],
            reps=1,
            manifest=self.manifest,
            out_dir=self.tmp / "out3",
        )
        self.assertEqual(result["summary"]["overall"]["transport_errors"], 1)
        self.assertEqual(result["summary"]["overall"]["no_code"], 1)
        self.assertEqual(lean_mandat.exit_code(result["summary"]), 1)

    def test_no_code_skips_leancheck(self):
        def empty_call(messages, timeout):
            payload = {"content": "", "reasoning": "", "usage": {}, "finish_reason": "stop"}
            return payload, {}, 0.1, None

        seen = []
        result = lean_mandat.run_matrix(
            call=empty_call,
            check=self._scripted_check(seen),
            variants=["V-A"],
            tasks=lean_mandat.TASKS[:1],
            reps=1,
            manifest=self.manifest,
            out_dir=self.tmp / "out4",
        )
        self.assertEqual(result["summary"]["overall"]["no_code"], 1)
        self.assertEqual(seen, [])

    def test_exit_code_signals_transport_failures_only(self):
        self.assertEqual(lean_mandat.exit_code({"transport_errors": 0, "invalid": 3}), 0)
        self.assertEqual(lean_mandat.exit_code({"transport_errors": 2}), 1)

    def test_render_cli_regenerates_assets_deterministically(self):
        calls, seen = [], []
        out_dir = self.tmp / "out5"
        lean_mandat.run_matrix(
            call=self._scripted_call(calls),
            check=self._scripted_check(seen),
            variants=["V-A"],
            tasks=lean_mandat.TASKS[:1],
            reps=1,
            manifest=self.manifest,
            out_dir=out_dir,
        )
        summary_a, raw_a = self.tmp / "summary-a.md", self.tmp / "raw-a.md"
        summary_b, raw_b = self.tmp / "summary-b.md", self.tmp / "raw-b.md"
        lean_mandat.main(["render", "--run", str(out_dir), "--summary", str(summary_a), "--raw", str(raw_a)])
        lean_mandat.main(["render", "--run", str(out_dir), "--summary", str(summary_b), "--raw", str(raw_b)])
        self.assertEqual(summary_a.read_text(encoding="utf-8"), summary_b.read_text(encoding="utf-8"))
        self.assertEqual(raw_a.read_text(encoding="utf-8"), raw_b.read_text(encoding="utf-8"))
        self.assertEqual(summary_a.read_text(encoding="utf-8"), (out_dir / "summary.md").read_text(encoding="utf-8"))


class ReferenceProofsTest(unittest.TestCase):
    @unittest.skipUnless(_lake_available(), "keine lake-Toolchain installiert")
    def test_every_task_has_a_valid_reference_proof(self):
        import leancheck

        for task in lean_mandat.TASKS:
            source = (
                f"import Std\n\ntheorem main_thm : {task['statement']} := by {task['ref_tactic']}"
            )
            result = leancheck.check(source, print_axioms_for="main_thm")
            self.assertEqual(result["status"], "valid", f"{task['id']}: {result['errors'] or result['message']}")
            self.assertNotEqual(result["axioms"], None, task["id"])


if __name__ == "__main__":
    unittest.main()

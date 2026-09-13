#!/usr/bin/env python3
"""Tests der Token-Kosten-Sonde V18 (Lean-Zeile vs. V1.1-Zeile vs. Prosa-Zeile).

Die Sonde misst Tokenkosten gleichbedeutender Zeilen in drei Stilen mit dem
DeepSeek-Tokenizer. Geprueft wird mit einem Stub-Tokenizer die reine
Mess-/Aggregationslogik; ein Integrationstest laeuft nur, wenn die lokalen
Artefakte (.yesmem/tmp/tokenizer/tokenizer.json + pylibs) vorhanden sind.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import types
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


lean_cost = _load("lean_cost")


class StubTokenizer:
    """Duck-typed tokenizers-API: ein Token pro Whitespace-Wort."""

    def encode(self, text):
        ids = text.split()
        return types.SimpleNamespace(ids=ids, tokens=ids)


ITEMS = [
    {"id": "x1", "lean": "have h : 2 + 2 = 4 := by decide", "v11": "h: (2+2=4)", "prose": "two plus two is four"},
    {"id": "x2", "lean": "exact h", "v11": "h1+", "prose": "confirmed"},
]


class MeasureTest(unittest.TestCase):
    def test_counts_tokens_and_chars(self):
        rows = lean_cost.measure(StubTokenizer(), ITEMS)
        self.assertEqual(len(rows), 2)
        row = rows[0]
        # "have h : 2 + 2 = 4 := by decide" -> 11 Whitespace-Tokens
        self.assertEqual(row["lean_tokens"], 11)
        # "h: (2+2=4)" -> 2 Tokens
        self.assertEqual(row["v11_tokens"], 2)
        # "two plus two is four" -> 5 Tokens
        self.assertEqual(row["prose_tokens"], 5)
        self.assertEqual(row["lean_chars"], len(ITEMS[0]["lean"]))
        self.assertEqual(row["lean_vs_prose"], round(11 / 5, 3))
        self.assertEqual(row["v11_vs_prose"], 0.4)

    def test_custom_items(self):
        rows = lean_cost.measure(StubTokenizer(), [{"id": "a", "lean": "a", "v11": "a", "prose": "a"}])
        self.assertEqual(rows[0]["lean_tokens"], 1)

    def test_summarize_totals(self):
        summary = lean_cost.summarize(lean_cost.measure(StubTokenizer(), ITEMS))
        self.assertEqual(summary["totals"]["lean"], 13)  # 11 + "exact h" (2)
        self.assertEqual(summary["totals"]["v11"], 3)  # 2 + "h1+" (1)
        self.assertEqual(summary["totals"]["prose"], 6)  # 5 + "confirmed" (1)
        self.assertEqual(summary["ratios"]["lean_vs_prose"], round(13 / 6, 3))

    def test_render_markdown(self):
        md = lean_cost.render_markdown(lean_cost.measure(StubTokenizer(), ITEMS), lean_cost.summarize(lean_cost.measure(StubTokenizer(), ITEMS)))
        self.assertIn("x1", md)
        self.assertIn("Lean", md)
        # Ohne expliziten Hash rendert der dokumentierte Stand (01-03b).
        self.assertIn(lean_cost.TOKENIZER_SHA256, md)

    def test_render_markdown_uses_given_hash(self):
        rows = lean_cost.measure(StubTokenizer(), ITEMS)
        md = lean_cost.render_markdown(rows, lean_cost.summarize(rows), sha256="ab" * 32)
        self.assertIn("ab" * 32, md)
        self.assertNotIn(lean_cost.TOKENIZER_SHA256, md)

    def test_default_items_are_triplets(self):
        for item in lean_cost.ITEMS:
            self.assertEqual(set(item.keys()), {"id", "lean", "v11", "prose"}, item["id"])
            self.assertTrue(item["lean"].strip() and item["v11"].strip() and item["prose"].strip())
            # V1.1-Zeile: Tag-Kopf oder Statusform.
            self.assertTrue(":" in item["v11"] or item["v11"][-1] in "+-?!", item["id"])


@unittest.skipUnless(
    (ROOT / ".yesmem" / "tmp" / "tokenizer" / "tokenizer.json").exists()
    and (ROOT / ".yesmem" / "tmp" / "pylibs" / "tokenizers").exists(),
    "lokale Tokenizer-Artefakte fehlen",
)
class RealTokenizerTest(unittest.TestCase):
    def test_real_encode_known_vector(self):
        tok = lean_cost.load_tokenizer(
            ROOT / ".yesmem" / "tmp" / "tokenizer" / "tokenizer.json",
            ROOT / ".yesmem" / "tmp" / "pylibs",
        )
        encoding = tok.encode("2+2=4")
        self.assertEqual(len(encoding.ids), 5)  # 2,+ ,2,=,4 (01-03b-Validierung)

    def test_real_measure_runs(self):
        tok = lean_cost.load_tokenizer(
            ROOT / ".yesmem" / "tmp" / "tokenizer" / "tokenizer.json",
            ROOT / ".yesmem" / "tmp" / "pylibs",
        )
        rows = lean_cost.measure(tok)
        self.assertEqual(len(rows), len(lean_cost.ITEMS))
        for row in rows:
            self.assertGreater(row["lean_tokens"], 0)
            self.assertGreater(row["v11_tokens"], 0)
            self.assertGreater(row["prose_tokens"], 0)

    def test_real_tokenizer_matches_documented_sha(self):
        path = ROOT / ".yesmem" / "tmp" / "tokenizer" / "tokenizer.json"
        self.assertEqual(lean_cost.sha256_file(path), lean_cost.TOKENIZER_SHA256)


if __name__ == "__main__":
    unittest.main()

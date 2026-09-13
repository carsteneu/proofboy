#!/usr/bin/env python3
"""Tests for scan_catalog.py — the static formal-conjectures catalog scan.

Run:
    python3 yesdocs/formal-conjectures/tools/test_scan_catalog.py
or
    python3 -m unittest discover -s yesdocs/formal-conjectures/tools

The tests build a tiny synthetic catalog for the parser contract and, when
the real clone is present (gitignored, pinned commit), verify the scan totals
against independently counted reference values.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scan_catalog  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORKTREE = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REAL_CLONE = os.path.join(WORKTREE, ".yesmem", "tmp", "formal-conjectures")

PC = "FormalConjectures"

FILE_A = f"""/-
Copyright 2025 The Formal Conjectures Authors.
-/

/-!
# Demo Problem

*Reference:* [Somewhere](https://example.org/demo)
-/

namespace Demo

/--
A trivial open question, mentioning `@[category test, AMS 15]` inside the docstring
and the `answer(sorry)` idiom in prose.
-/
@[category research open, AMS 11]
theorem demo_open : answer(sorry) ↔ ∃ n : ℕ, Nat.Prime (n + 2) := by
  sorry

/--
A solved variant.
-/
@[category research solved, AMS 5 11, formal_proof using lean4 at "https://example.org/proof.lean"]
theorem demo_solved (n : ℕ) : ∀ m, m ≤ n → True := by
  sorry

@[category test, AMS 3]
theorem demo_machine : Turing.Machine.IsHalting := by
  sorry

--See https://example.org/comment-link
@[category test, AMS 3]
theorem demo_after_comment : answer(False) ↔ 1 + 1 = 2 := by
  sorry

@[category test, AMS 5]
private lemma demo_private (x : ℤ) : x = x := by
  rfl

end Demo
"""

FILE_B = f"""/-
Copyright 2025 The Formal Conjectures Authors.
-/

/-!
# Erdős Problem 42

*Reference:* [erdosproblems.com/42](https://www.erdosproblems.com/42)
-/

open Erdos7

namespace Erdos42

@[category research open, AMS 11]
theorem erdos_42 : answer(sorry) ↔ (∑ i ∈ Finset.range 10, i) > 0 ∧ Machine.IsHalting := by
  sorry

/--
The docstring closes and the attribute follows on the same line.
-/@[category research solved, AMS 11]
theorem erdos_42.docstring_adjacent : True := by
  sorry

end Erdos42
"""


def write_catalog(root):
    """Write the two synthetic statement files under <root>/FormalConjectures."""
    wiki = os.path.join(root, PC, "Wikipedia")
    erdos = os.path.join(root, PC, "ErdosProblems")
    os.makedirs(wiki)
    os.makedirs(erdos)
    with open(os.path.join(wiki, "Demo.lean"), "w", encoding="utf-8") as fh:
        fh.write(FILE_A)
    with open(os.path.join(erdos, "42.lean"), "w", encoding="utf-8") as fh:
        fh.write(FILE_B)


class ParseAttributesTest(unittest.TestCase):
    def test_basic(self):
        got = scan_catalog.parse_attributes("category research open, AMS 5 11")
        self.assertEqual(got["categories"], ["research open"])
        self.assertEqual(got["ams"], ["5", "11"])
        self.assertIsNone(got["formal_proof"])

    def test_formal_proof_url_with_commas_and_slashes(self):
        got = scan_catalog.parse_attributes(
            'category research solved, AMS 11, formal_proof using lean4 at '
            '"https://github.com/x/y/blob/a,b/c.lean#L1"'
        )
        self.assertEqual(got["categories"], ["research solved"])
        self.assertEqual(got["ams"], ["11"])
        self.assertEqual(got["formal_proof"], "https://github.com/x/y/blob/a,b/c.lean#L1")

    def test_no_ams(self):
        got = scan_catalog.parse_attributes("category test")
        self.assertEqual(got["categories"], ["test"])
        self.assertEqual(got["ams"], [])


class ScanFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        write_catalog(cls.tmp.name)
        cls.scan = scan_catalog.scan_catalog(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def files(self):
        return {f["path"]: f for f in self.scan["files"]}

    def test_files_and_collections(self):
        self.assertEqual(
            sorted(self.files()),
            [f"{PC}/ErdosProblems/42.lean", f"{PC}/Wikipedia/Demo.lean"],
        )
        collections = {c["name"]: c for c in self.scan["collections"]}
        self.assertEqual(collections["Wikipedia"]["files"], 1)
        self.assertEqual(collections["ErdosProblems"]["files"], 1)

    def test_totals(self):
        totals = self.scan["totals"]
        self.assertEqual(totals["files"], 2)
        # 5 in Demo.lean + 2 in 42.lean; the docstring mention is not a declaration.
        self.assertEqual(totals["declarations"], 7)
        self.assertEqual(totals["research_open"], 2)
        self.assertEqual(totals["research_solved"], 2)
        self.assertEqual(totals["answer_sorry"], 2)

    def test_declaration_fields(self):
        decls = {d["name"]: d for d in self.files()[f"{PC}/Wikipedia/Demo.lean"]["declarations"]}
        self.assertEqual(set(decls), {
            "demo_open", "demo_solved", "demo_machine", "demo_after_comment", "demo_private",
        })
        self.assertEqual(decls["demo_open"]["categories"], ["research open"])
        self.assertEqual(decls["demo_open"]["ams"], ["11"])
        self.assertEqual(decls["demo_open"]["answer"], "sorry")
        self.assertEqual(decls["demo_solved"]["answer"], None)
        self.assertEqual(decls["demo_after_comment"]["answer"], "False")
        self.assertEqual(
            decls["demo_solved"]["formal_proof"],
            "https://example.org/proof.lean",
        )
        self.assertEqual(decls["demo_private"]["kind"], "lemma")

    def test_features(self):
        decls = {d["name"]: d for d in self.files()[f"{PC}/Wikipedia/Demo.lean"]["declarations"]}
        self.assertIn("exists", decls["demo_open"]["features"])
        self.assertIn("prime", decls["demo_open"]["features"])
        self.assertIn("forall", decls["demo_solved"]["features"])
        self.assertIn("machine", decls["demo_machine"]["features"])
        self.assertIn("int", decls["demo_private"]["features"])
        erdos = {d["name"]: d for d in self.files()[f"{PC}/ErdosProblems/42.lean"]["declarations"]}
        self.assertIn("finset", erdos["erdos_42"]["features"])
        self.assertIn("sum", erdos["erdos_42"]["features"])
        self.assertGreater(erdos["erdos_42"]["statement_chars"], 10)

    def test_references_and_title(self):
        demo = self.files()[f"{PC}/Wikipedia/Demo.lean"]
        self.assertEqual(demo["title"], "Demo Problem")
        self.assertIn("https://example.org/demo", demo["references"])
        self.assertIn("https://example.org/comment-link", demo["references"])
        erdos = self.files()[f"{PC}/ErdosProblems/42.lean"]
        self.assertEqual(erdos["title"], "Erdős Problem 42")
        self.assertIn("https://www.erdosproblems.com/42", erdos["references"])
        self.assertEqual(erdos["problem_id"], "42")
        self.assertIsNone(demo["problem_id"])

    def test_cross_refs(self):
        demo = self.files()[f"{PC}/Wikipedia/Demo.lean"]
        self.assertEqual(demo["cross_refs"], [])
        erdos = self.files()[f"{PC}/ErdosProblems/42.lean"]
        self.assertIn("Erdos7", erdos["cross_refs"])
        # The file's own namespace is not a cross reference.
        self.assertNotIn("Erdos42", erdos["cross_refs"])

    def test_determinism(self):
        again = scan_catalog.scan_catalog(self.tmp.name)
        self.assertEqual(
            json.dumps(self.scan, sort_keys=True),
            json.dumps(again, sort_keys=True),
        )

    def test_cli(self):
        with tempfile.TemporaryDirectory() as out_dir:
            out = os.path.join(out_dir, "scan.json")
            proc = subprocess.run(
                [sys.executable, os.path.join(HERE, "scan_catalog.py"), self.tmp.name,
                 "--json", out],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("files: 2", proc.stdout)
            with open(out, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["schema"], scan_catalog.SCHEMA)


@unittest.skipUnless(
    os.path.isdir(os.path.join(REAL_CLONE, PC)),
    f"real clone absent: {REAL_CLONE}",
)
class RealCloneTest(unittest.TestCase):
    """Reference totals for the clone pinned at commit a2f4a1b (measured by
    independent grep counts; the clone is gitignored and pinned)."""

    @classmethod
    def setUpClass(cls):
        cls.scan = scan_catalog.scan_catalog(REAL_CLONE)

    def test_reference_totals(self):
        if self.scan["catalog"]["commit"] != "a2f4a1bb12a28e04a969da78feefac7d1ce49565":
            self.skipTest("clone is not at the pinned commit a2f4a1b")
        totals = self.scan["totals"]
        self.assertEqual(totals["files"], 1268)
        self.assertEqual(totals["research_open"], 1466)
        # Statement-level answer(sorry): the raw text contains 918 occurrences;
        # 17 of them are prose mentions inside docstrings/comments (checked by
        # offset), leaving 901 declarations whose type uses the answer gadget.
        self.assertEqual(totals["answer_sorry"], 901)
        # 5421 raw lines contain the attribute string; one is a docstring
        # mention (OpenQuantumProblems/23.lean), leaving 5420 declarations.
        self.assertEqual(totals["declarations"], 5420)


if __name__ == "__main__":
    unittest.main(verbosity=2)

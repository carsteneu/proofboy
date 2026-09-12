"""Tests for the sheet parser, the runner and the CLI of bemyself.msheet.

The sheet is the model's answer artifact (05-07 §§2–7): thinking zone with
strict line heads, append-only status register, strict claim zone. The runner
writes the verdicts; the parser collects format errors instead of raising.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from bemyself.model import Verdict
from bemyself.msheet.runner import run_sheet
from bemyself.msheet.sheet import parse_sheet

WIKI_CYCLER = "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC"
SMALL_HALTER = "1RB1RZ_0LA0LA"

THINKING_EXAMPLE = """g: M haltet?; st(27)?
d: st(n) = Schritte bis 1 (V1-Bibliothek)
a: M = 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC
h1: M zyklisch (Translation)
v h1: cyc(6,16,2)
h1+
=: M kein Holdout (h1+)
a: n=27
h2: st(27)=111
v h2: auto
h2+
=: st(27)=111 (h2+)
"""

FULL_SHEET = (
    THINKING_EXAMPLE
    + """CLAIM c1: (st(27) = 111)
WITNESS c1: ref h2
[HALT] c1
"""
)


class ParseTest(unittest.TestCase):
    def test_thinking_example(self):
        sheet = parse_sheet(THINKING_EXAMPLE)
        self.assertEqual(sheet.goal, "M haltet?; st(27)?")
        self.assertEqual(
            [(s.target, s.status) for s in sheet.statuses], [("h1", "+"), ("h2", "+")]
        )
        self.assertEqual([v.vid for v in sheet.vlines], ["v1", "v2"])
        self.assertEqual([v.target for v in sheet.vlines], ["h1", "h2"])
        self.assertEqual([v.spec.kind for v in sheet.vlines], ["cyc", "auto"])
        self.assertEqual(sheet.body_of("h2"), "st(27)=111")
        self.assertIn("M", sheet.machines)
        self.assertEqual(sheet.machines["M"].source, WIKI_CYCLER)
        # No claim zone in a pure thinking example: the errors say so.
        messages = [e.message for e in sheet.errors]
        self.assertTrue(any("no claim zone" in m for m in messages))
        self.assertTrue(any("no [HALT]" in m for m in messages))

    def test_v1_style_sheet_with_def_and_calc(self):
        text = """goal: (forall n in 1..5: (sum_1_to_n(n) = ((n * (n + 1)) // 2)))
def sum_1_to_n(n) = sum(k=1..n, k)
S1: calc
S2:      999999999
S3: +            1
S4: = 1000000000
CLAIM c1: (sum_1_to_n(5) = 15)
WITNESS c1: auto
[HALT] c1
"""
        sheet = parse_sheet(text)
        self.assertEqual([e.message for e in sheet.errors], [])
        self.assertIn("sum_1_to_n", sheet.defs)
        self.assertEqual([t.tag for t in sheet.think[:4]], ["S", "S", "S", "S"])
        result = run_sheet(sheet, sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.CONFIRMED)

    def test_v11_calc_block(self):
        text = """c:
 999999999
+        1
= 1000000000
CLAIM c1: ((999999999 + 1) = 1000000000)
WITNESS c1: auto
[HALT] c1
"""
        # The continuation lines of a calc block are layout, not errors.
        sheet = parse_sheet(text)
        self.assertEqual([e.message for e in sheet.errors], [])

    def test_status_and_ids(self):
        sheet = parse_sheet("h12: body\nS3: s\nq1: (open)\nv2 h12: auto\n")
        self.assertEqual(sheet.think[0].id, "h12")
        self.assertEqual(sheet.think[1].tag, "S")
        self.assertEqual(sheet.think[1].counter, "3")
        self.assertEqual(sheet.vlines[0].vid, "v2")

    def test_format_errors(self):
        cases = [
            ("keine Zeile mit Kopf\n", "no valid line head"),
            ("CLAIM c1: (1 = 1)\n[HALT] c1\n", "has no witness"),
            ("CLAIM c1: (1 = 1)\nCLAIM c1: (2 = 2)\n", "duplicate claim id"),
            ("WITNESS c9: auto\nCLAIM c1: (1 = 1)\nWITNESS c1: auto\n", "unknown claim"),
            (
                "CLAIM c1: (1 = 1)\nWITNESS c1: auto\n",
                "no [HALT]",
            ),
            ("CLAIM 1x: (1 = 1)\n", "not a claim id"),
            ("v h1 auto\n", "malformed v-line"),
        ]
        for text, wanted in cases:
            sheet = parse_sheet(text)
            messages = [e.message for e in sheet.errors]
            self.assertTrue(
                any(wanted in m for m in messages), f"{wanted!r} not in {messages!r} for {text!r}"
            )

    def test_interleaved_thinking_lines_are_accepted(self):
        # The smoke run of 2026-09-12: the model interleaves h/v/CLAIM blocks.
        # Interleaving is a style choice, not a format error (documented
        # implementation precision of the pilot).
        sheet = parse_sheet(
            "h1: (1 = 1)\nv h1: auto\nCLAIM c1: (1 = 1)\nWITNESS c1: ref h1\nh2: (2 = 2)\nv h2: auto\n[HALT] c1\n"
        )
        messages = [e.message for e in sheet.errors]
        self.assertFalse(any("after the claim zone" in m for m in messages), messages)
        self.assertEqual([v.vid for v in sheet.vlines], ["v1", "v2"])

    def test_halt_ids_may_be_comma_separated(self):
        sheet = parse_sheet("CLAIM c1: (1 = 1)\nWITNESS c1: auto\nCLAIM c2: (2 = 2)\nWITNESS c2: auto\n[HALT] c1,c2\n")
        self.assertEqual(sheet.halt, ["c1", "c2"])
        self.assertEqual([e.message for e in sheet.errors], [])

    def test_hostile_whitespace_is_bounded(self):
        text = "h1: " + " " * 5000 + "\n[HALT]" + " " * 3000 + "\n"
        start = time.monotonic()
        sheet = parse_sheet(text)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0)
        self.assertIsNotNone(sheet.halt)


class RunnerTest(unittest.TestCase):
    def test_full_sheet(self):
        sheet = parse_sheet(FULL_SHEET)
        result = run_sheet(sheet, sandbox="off")
        self.assertEqual(
            [(v.vid, v.verdict) for v in result.v_results],
            [("v1", Verdict.CONFIRMED), ("v2", Verdict.CONFIRMED)],
        )
        self.assertEqual(
            [(c.cid, c.verdict) for c in result.claim_results],
            [("c1", Verdict.CONFIRMED)],
        )
        self.assertEqual(result.appendix, ["#ok: v1 v2 c1"])
        self.assertEqual(result.format_errors, [])

    def test_ref_unconfirmed_without_plus(self):
        text = FULL_SHEET.replace("h2+\n", "")
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.UNVERIFIABLE)
        self.assertIn("ref_unconfirmed", result.claim_results[0].reason)
        self.assertIn("#?: c1", " ".join(result.appendix))

    def test_last_status_wins(self):
        text = FULL_SHEET.replace("h2+\n", "h2+\nh2-\n")
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.UNVERIFIABLE)

    def test_py_witness(self):
        text = """CLAIM c1: (st(27) = 111)
WITNESS c1: py: st(27)==111
[HALT] c1
"""
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.CONFIRMED)
        text = text.replace("st(27)==111", "st(27)==110")
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.REFUTED)

    def test_sim_witness_through_the_runner(self):
        text = f"""a: M = {SMALL_HALTER}
h1: cp 1: (B,1,1)
v h1: sim(0..2)
h1+
CLAIM c1: (st(6) = 7)
WITNESS c1: auto
[HALT] c1
"""
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.v_results[0].verdict, Verdict.CONFIRMED)
        self.assertEqual(result.claim_results[0].verdict, Verdict.REFUTED)

    def test_non_formula_claim_with_ref_witness(self):
        # Trace answers reuse the checkpoint text as claim and verify it via
        # the confirmed h-line: the claim text needs no V1 formula then.
        text = f"""g: Lauf?
a: M = {SMALL_HALTER}
h1: cp 1: (B,1,1)
v h1: sim(0..2)
h1+
CLAIM c1: cp 1: (B,1,1)
WITNESS c1: ref h1
[HALT] c1
"""
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.CONFIRMED)

    def test_claim_with_bad_formula(self):
        text = """CLAIM c1: keine formel
WITNESS c1: auto
[HALT] c1
"""
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.UNVERIFIABLE)

    def test_unknown_target(self):
        text = """h1: (1 = 1)
v h9: auto
CLAIM c1: (1 = 1)
WITNESS c1: auto
[HALT] c1
"""
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.v_results[0].verdict, Verdict.UNVERIFIABLE)
        self.assertIn("unknown target", result.v_results[0].reason)

    def test_empty_range_claim(self):
        text = """CLAIM c1: (forall n in 1..0: (n > 0))
WITNESS c1: auto
[HALT] c1
"""
        result = run_sheet(parse_sheet(text), sandbox="off")
        self.assertEqual(result.claim_results[0].verdict, Verdict.UNVERIFIABLE)
        self.assertIn("empty_range", result.claim_results[0].reason)

    def test_json_shape(self):
        result = run_sheet(parse_sheet(FULL_SHEET), sandbox="off")
        payload = result.to_json()
        self.assertEqual(payload["v"][0]["verdict"], "CONFIRMED")
        self.assertEqual(payload["claims"][0]["id"], "c1")
        self.assertEqual(payload["appendix"], ["#ok: v1 v2 c1"])


class CliTest(unittest.TestCase):
    def _run_cli(self, text, *extra):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tmp_root = os.path.join(repo_root, ".yesmem", "tmp")
        os.makedirs(tmp_root, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp_root) as tmp:
            path = os.path.join(tmp, "sheet.msheet")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return subprocess.run(
                [sys.executable, "-m", "bemyself.msheet", "run", path, *extra],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

    def test_json_output(self):
        proc = self._run_cli(FULL_SHEET, "--json", "--sandbox", "off")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["appendix"], ["#ok: v1 v2 c1"])

    def test_plain_output(self):
        proc = self._run_cli(FULL_SHEET, "--sandbox", "off")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "#ok: v1 v2 c1")

    def test_empty_file(self):
        proc = self._run_cli("", "--json")
        # an empty file parses to an empty sheet: verdicts are the appendix
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["v"], [])

    def test_missing_file(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proc = subprocess.run(
            [sys.executable, "-m", "bemyself.msheet", "run", os.path.join(repo_root, "does-not-exist.msheet")],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()

"""Tests for the V12 repair-loop tooling (yesdocs/.../tooling, Runde 2).

Runde 2 (05-09) faehrt den Rueckkanal: eine Aufgabe laeuft ueber mehrere
Runden; nach jeder Runde entscheidet der Runner bzw. das Gold-Kriterium, ob
der Endzustand bestaetigt ist -- sonst folgt eine Reparaturrunde mit
Verdikt-Appendix. Die tragenden Teile sind der Feedback-Builder (mit
Gold-Leak-Schutz), die Runden-Schleife des Harness und die Runden-Metriken
der Auswertung; dazu die v0.2-Fixes (%-Klammerregel der Legenden).

The functions under test decide the measurement: untested feedback or
round-logic would poison the round.
"""

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
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


harness = _load("harness")
prompts = _load("prompts")
evaluate = _load("evaluate")

from bemyself.msheet.runner import run_sheet  # noqa: E402
from bemyself.msheet.sheet import parse_sheet  # noqa: E402

TASK_A = {"id": "A-0006", "tier": "A", "prompt": "Berechne 2 hoch 10 modulo 1000.", "expected": "24"}
TASK_TRACE = {
    "id": "B-0001",
    "tier": "B",
    "tier_b_kind": "trace",
    "machine": "1RB1RZ_0LA0LA",
    "checkpoints_t": [1, 2],
    "prompt": "Simuliere.",
}


class LegendV02Test(unittest.TestCase):
    """M1: Legenden v0.2 -- %-Klammerregel explizit, Beispiel parser-valid."""

    def test_percent_rule_is_explicit_in_the_formula_arms(self):
        # v0.1 lehrte das Modell die invalide Form ((2 ^ 10) % 1000 = 24)
        # (Repro: Parser -> "expected ')', found '='"). v0.2 nennt die Regel
        # operandenweise und zeigt die korrekte Form.
        for arm in ("B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_A)
            self.assertIn("((A % B) = C)", system, arm)
            self.assertIn("(((2 ^ 10) % 1000) = 24)", system, arm)
            self.assertNotIn("((2 ^ 10) % 1000 = 24)", system, arm)

    def test_k_legend_carries_no_formula_zone_rule(self):
        # K schreibt keine Formelzone; die Regel bliebe dort ohne Adressat.
        system, _user = prompts.build_messages("K", TASK_A)
        self.assertNotIn("((A % B) = C)", system)

    def test_the_legend_example_parses_and_confirms(self):
        # Der Legenden-Ausdruck muss durch Parser und Runner gehen -- sonst
        # lehrt die Legende wieder eine Form, die der Runner ablehnt.
        for arm in ("B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_A)
            match = re.search(r"\(\(\(2 \^ 10\) % 1000\) = 24\)", system)
            self.assertIsNotNone(match, arm)
            sheet = parse_sheet(
                f"CLAIM c1: {match.group(0)}\nWITNESS c1: auto\n[HALT] c1"
            )
            result = run_sheet(sheet, sandbox="auto", timeout=10.0)
            self.assertEqual(
                result.claim_results[0].verdict.value, "CONFIRMED", arm
            )


class TraceConventionV02Test(unittest.TestCase):
    """M1: cp-Konvention praezisiert -- Konfiguration NACH dem Schritt t."""

    def test_precision_is_in_every_arm(self):
        for arm in ("K", "B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_TRACE)
            self.assertIn("NACH dem angegebenen Schritt", system, arm)
            self.assertIn("Schritt 0 ist der Startzustand", system, arm)

    def test_v11_anchors_are_kept(self):
        # Kontinuitaet zu Pilot 1: die I3-Formulierungen bleiben wortgleich.
        for arm in ("K", "B", "C", "D"):
            system, _user = prompts.build_messages(arm, TASK_TRACE)
            self.assertIn("Kopfposition = ganze Zahl ab", system, arm)
            self.assertIn("Zellen sind 0", system, arm)


class SetsV02Test(unittest.TestCase):
    """M2: Sets v0.2 -- neue Version+sha256, v0.1 unangetastet, B-0011 enthalten."""

    SETS = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"

    def _load_set(self, name):
        return json.loads((self.SETS / name).read_text(encoding="utf-8"))

    def test_v02_sets_exist_with_expected_shape(self):
        tier_a = self._load_set("tier_a_v11-a-0.2.json")
        tier_b = self._load_set("tier_b_v11-b-0.2.json")
        self.assertEqual(tier_a["set_version"], "v11-a-0.2")
        self.assertEqual(tier_b["set_version"], "v11-b-0.2")
        self.assertEqual(len(tier_a["tasks"]), 16)
        self.assertEqual(len(tier_b["tasks"]), 12)

    def test_heavy_translator_cycle_is_present(self):
        # Runde-2-Auftrag: B-0011 wird forciert (kein Shuffle-Ausschluss).
        tier_b = self._load_set("tier_b_v11-b-0.2.json")
        task = next(t for t in tier_b["tasks"] if t["id"] == "B-0011")
        self.assertEqual(task["tier_b_kind"], "cyc")
        self.assertEqual(task["machine"], "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC")
        self.assertEqual(task["certificate"], [6, 16, 2])

    def test_tier_a_content_is_identical_to_v01(self):
        # Kontinuitaet: die Aufgabeninhalte bleiben Pilot-1-gleich.
        old = self._load_set("tier_a_v11-a-0.1.json")
        new = self._load_set("tier_a_v11-a-0.2.json")
        self.assertEqual(old["tasks"], new["tasks"])

    def test_v01_files_are_untouched(self):
        # Hashes aus 05-08 (Pilot-1-Lauf): v0.1 bleibt eingefroren.
        for name, prefix in (
            ("tier_a_v11-a-0.1.json", "50c985e169aa5007"),
            ("tier_b_v11-b-0.1.json", "074ab6bf5ebfc213"),
        ):
            digest = hashlib.sha256((self.SETS / name).read_bytes()).hexdigest()
            self.assertTrue(digest.startswith(prefix), name)

    def test_generated_tasks_carry_own_license_and_no_memory_ids(self):
        tier_b = self._load_set("tier_b_v11-b-0.2.json")
        generated = [t for t in tier_b["tasks"] if t["source"].startswith("generiert")]
        self.assertTrue(generated)
        for task in generated:
            self.assertEqual(task["license"], "CC0-1.0 (selbst erzeugt)", task["id"])
        for task in tier_b["tasks"]:
            self.assertNotIn("Learning", task["source"], task["id"])

    def test_rebuild_reproduces_the_committed_v02_files(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=tmp_root))
        try:
            subprocess.run(
                [sys.executable, str(TOOLING / "build_sets.py"), "--out", str(tmp)],
                check=True,
                cwd=ROOT,
                capture_output=True,
            )
            for name in ("tier_a_v11-a-0.2.json", "tier_b_v11-b-0.2.json"):
                self.assertEqual(
                    (tmp / name).read_bytes(), (self.SETS / name).read_bytes(), name
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

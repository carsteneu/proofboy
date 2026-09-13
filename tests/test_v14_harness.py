#!/usr/bin/env python3
"""Tests der Lokalisierungs-Runde V14 (Feedback-Leiter G0/G1/G2, Bindungsschutz).

Deckt vier Baustellen:

1. G0 ist der V13-Stand und bleibt exakt erhalten (Regressionstest pinnt die
   realen Feedback-Notizen des Bindungsfalls und der REFUTED-Faelle).
2. G1 lokalisiert auf Klassen ohne Werte: Bindung fehlt / Werte widerlegt /
   Formfehler-Konvention -- inklusive der Schutzanweisung, ungeprueste Werte
   beim Neuformulieren nicht zu aendern.
3. G2 ergaenzt Positions-Legs aus der Checker-Semantik (Zustands-, Kopf-,
   Band-Bedingung; sim-Schritt bleibt modell-eigen) -- ohne Referenzwerte.
4. Leck-Property: die erzeugten Rueckmeldungen nennen keine Gold-Token; der
   Default-Deny-Sanitizer bleibt fuer alles Unbekannte in Kraft.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"
SETS = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"

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

from bemyself.claimtypes import cycle  # noqa: E402
from bemyself.model import Claim  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures: reale Maschinen der v13/v14-Sets (Zertifikate mit cycle.check
# verifiziert; alle Verletzungswerte in den Szenarien wurden gegen den echten
# Checker geprobt und treffen die jeweils genannte Branche).

_HARD = {
    "id": "B3-0008",
    "tier": "B",
    "tier_b_kind": "cyc",
    "machine": "1LB1LB_1RA0LB",
    "certificate": [34, 37, -1],
    "certificate_given": False,
    "prompt": "Untersuche den Lauf.",
}
_HARD_GOLD_TOKENS = ["34", "37"]

_LONG = {
    "id": "B3-0007",
    "tier": "B",
    "tier_b_kind": "cyc",
    "machine": "1LC1LB_1LC1RC_1RA0LB",
    "certificate": [133, 142, 1],
    "certificate_given": True,
    "prompt": "Belege den Zyklus.",
}
_LONG_GOLD_TOKENS = ["133", "142"]

_TRACE = {
    "id": "B-9trace",
    "tier": "B",
    "tier_b_kind": "trace",
    "machine": "1RB1RZ_0LA0LA",
    "checkpoints_t": [1, 2],
    "checkpoints_gold": [[1, "B", 1, "1"], [2, "A", 0, "1"]],
    "prompt": "Simuliere.",
}

# Verletzungs-Szenarien (Probe 2026-09-13): Zustands-, Kopf- und Band-Leg des
# Cycle-Checkers sowie die Bindungsluecke.
_STATE_VIOLATION = (5, 9, 2)   # state mismatch (reason: "the state at step 9 is B, ...")
_HEAD_VIOLATION = (6, 10, 2)   # head mismatch ("the head at step 10 is at cell -4, ...")
_TAPE_VIOLATION = (0, 5, -1)   # tape mismatch ("the tape at step 5 differs ...")


def _cyc_sheet(values, binding=True):
    lines = []
    if binding:
        lines.append("a: M = 1LB1LB_1RA0LB")
    lines += [
        "h1: M zyklisch (Translation)",
        f"v h1: cyc({values[0]},{values[1]},{values[2]})",
        "h1+",
        "CLAIM c1: M zyklisch (Translation)",
        "WITNESS c1: ref h1",
        "[HALT] c1",
    ]
    return "\n".join(lines)


def _evidence(arm, task, answer):
    evidence = {}
    record = harness.evaluate_run(arm, task, {"content": answer}, 0.5, None, None, evidence_out=evidence)
    return record, evidence


def _bundle(arm, task, answer, level):
    _record, evidence = _evidence(arm, task, answer)
    return harness.feedback_bundle(arm, task, evidence, level=level)


def _full_text(arm, task, answer, level):
    verdicts, notes, hints, _classes = _bundle(arm, task, answer, level)
    return prompts.build_repair_message(arm, task, verdicts, notes, [], hint_lines=hints)


class _FakeCall:
    """Scripted transport: one entry per model call, in call order."""

    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    def __call__(self, messages, timeout):
        if self.calls >= len(self.contents):
            raise AssertionError("further calls than scripted answers")
        content = self.contents[self.calls]
        self.calls += 1
        usage = {"completion_tokens": 10, "completion_tokens_details": {"reasoning_tokens": 5}}
        return {"content": content, "reasoning": "", "usage": usage, "finish_reason": "stop"}, {}, 0.1, None


class _FakeArgs:
    def __init__(self, max_repairs=2, feedback="G0"):
        self.timeout = 5.0
        self.max_repairs = max_repairs
        self.feedback = feedback


def _tokens(text):
    return set(re.findall(r"[0-9]+", text))


class G0RegressionTest(unittest.TestCase):
    """G0 ist der V13-Stand: exakt dieselben Notizen, keine Lokalisierung."""

    def test_binding_missing_notes_pinned(self):
        _record, evidence = _evidence("D", _HARD, _cyc_sheet((3, 6, -1), binding=False))
        verdicts, notes = harness.feedback_lines("D", _HARD, evidence)
        self.assertEqual(verdicts, ["#?: v1 c1"])
        self.assertEqual(
            notes,
            [
                "v1: cyc: no machine binding in the sheet (expected 'a: M = <machine>')",
                "c1: ref h1: ref_unconfirmed (last status '+', last verdict UNVERIFIABLE)",
            ],
        )

    def test_refuted_cyc_phrase_unchanged(self):
        _record, evidence = _evidence("D", _HARD, _cyc_sheet(_STATE_VIOLATION))
        verdicts, notes = harness.feedback_lines("D", _HARD, evidence)
        self.assertEqual(notes[0], "v1: cyc: das Zertifikat traegt fuer diese Maschine nicht")

    def test_wrong_machine_g0_has_no_rows(self):
        # V13-Stand: alle Zeilen CONFIRMED (gueltig fuer die *fremde* Maschine),
        # aber die Aufgabe ist nicht geloest -- G0 liefert gar keine Notizen.
        answer = (
            "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,-1)\nh1+\n"
            "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
        )
        record, evidence = _evidence("D", _HARD, answer)
        self.assertFalse(record["solved"])
        self.assertFalse(record["machine_bound"])
        verdicts, notes = harness.feedback_lines("D", _HARD, evidence)
        self.assertEqual(notes, [])

    def test_g0_default_rendering_is_byte_identical(self):
        # default level = G0: feedback_bundle reproduces feedback_lines exactly.
        _record, evidence = _evidence("D", _HARD, _cyc_sheet(_STATE_VIOLATION))
        verdicts, notes = harness.feedback_lines("D", _HARD, evidence)
        b_verdicts, b_notes, _hints, _classes = harness.feedback_bundle("D", _HARD, evidence)
        self.assertEqual(verdicts, b_verdicts)
        self.assertEqual(notes, b_notes)


class LadderG1Test(unittest.TestCase):
    """G1: Klassen-Befunde ohne Werte, Bindungsschutz sprachlich getrennt."""

    def test_binding_missing_is_localized_and_protected(self):
        _record, evidence = _evidence("D", _HARD, _cyc_sheet((3, 6, -1), binding=False))
        verdicts, notes, hints, classes = harness.feedback_bundle("D", _HARD, evidence, level="G1")
        self.assertEqual(verdicts, ["#?: v1 c1"])
        binding_note = next(note for note in notes if note.startswith("v1:"))
        self.assertIn("keine Maschinenbindung", binding_note)
        self.assertIn("nicht widerlegt", binding_note)
        self.assertTrue(hints, "die Schutzanweisung muss mitgeliefert werden")
        hint = "\n".join(hints)
        self.assertIn("nicht", hint)
        self.assertIn("Werte", hint)
        self.assertEqual(classes[0]["id"], "v1")
        self.assertEqual(classes[0]["class"], "binding_missing")

    def test_binding_hint_absent_without_binding_case(self):
        _record, evidence = _evidence("D", _HARD, _cyc_sheet(_STATE_VIOLATION))
        _v, _n, hints, classes = harness.feedback_bundle("D", _HARD, evidence, level="G1")
        self.assertEqual(hints, [])
        self.assertEqual(classes[0]["class"], "values_refuted")

    def test_values_refuted_marked_as_refuted(self):
        _record, evidence = _evidence("D", _HARD, _cyc_sheet(_STATE_VIOLATION))
        _v, notes, _h, _c = harness.feedback_bundle("D", _HARD, evidence, level="G1")
        self.assertIn("widerlegt", notes[0])

    def test_not_checkable_reason_stays_sanitized(self):
        # t2 <= t1 ist ein Werte-Formfehler des Modells (keine Referenzwerte):
        # der Reason-Text bleibt unveraendert durchreichbar (V13-Verhalten).
        _record, evidence = _evidence("D", _HARD, _cyc_sheet((5, 3, -1)))
        _v, notes, _h, classes = harness.feedback_bundle("D", _HARD, evidence, level="G1")
        self.assertIn("t2 > t1", notes[0])
        self.assertEqual(classes[0]["class"], "not_checkable")

    def test_wrong_machine_gets_the_binding_class_note(self):
        answer = (
            "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,-1)\nh1+\n"
            "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
        )
        verdicts, notes, _hints, classes = _bundle("D", _HARD, answer, "G1")
        self.assertTrue(notes, "G1 benennt die falsche Maschinenbindung")
        self.assertTrue(any("andere Maschine" in note for note in notes))
        self.assertTrue(any(row["class"] == "binding_wrong" for row in classes))

    def test_k_arm_unaffected(self):
        _v, notes, hints, classes = harness.feedback_bundle("K", _HARD, None, level="G1")
        self.assertEqual(notes, [])
        self.assertEqual(hints, [])
        self.assertEqual(classes, [])

    def test_unknown_kinds_stay_withheld_at_g1(self):
        # Default-Deny bleibt: unbekannte Beleg-Art mit werthaltigem Grund.
        text = harness._render_note("hyperclaim", "REFUTED", "the hidden value is 424242", level="G1")
        self.assertNotIn("424242", text)


class LadderG2Test(unittest.TestCase):
    """G2: Positions-Legs aus der Checker-Semantik, ohne Referenzwerte."""

    def test_cyc_state_head_tape_legs_from_real_checker_texts(self):
        cases = [
            (_STATE_VIOLATION, "state"),
            (_HEAD_VIOLATION, "head"),
            (_TAPE_VIOLATION, "tape"),
        ]
        for values, leg in cases:
            with self.subTest(values=values):
                _record, evidence = _evidence("D", _HARD, _cyc_sheet(values))
                _v, notes, _h, classes = harness.feedback_bundle("D", _HARD, evidence, level="G2")
                self.assertEqual(classes[0]["class"], "values_refuted")
                self.assertEqual(classes[0]["leg"], leg)
                self.assertIn(harness._LEG_CYC[leg], notes[0])

    def test_cyc_halt_leg_format_from_checker(self):
        # Der Halt-Zweig des Checkers (bei einer haltenden Maschine); hier als
        # Reason-Format gepinnt, damit die Klasse nicht still verschwindet.
        reason = "cyc: the machine halted after 12 steps, inside the certificate window of 20 steps"
        cls, leg, _step = harness._row_class("cyc", "REFUTED", reason)
        self.assertEqual((cls, leg), ("values_refuted", "halt"))
        text = harness._render_note("cyc", "REFUTED", reason, level="G2")
        self.assertIn(harness._LEG_CYC["halt"], text)
        self.assertIsNone(re.search(r"[0-9]", text.split("cyc: ", 1)[1]))

    def test_sim_legs_use_model_owned_step(self):
        sheets = {
            "state": "h1: cp 1: (A,1,1)",
            "head": "h1: cp 1: (B,4,1)",
            "tape": "h1: cp 1: (B,1,0)",
        }
        for leg, head in sheets.items():
            with self.subTest(leg=leg):
                answer = (
                    f"a: M = 1RB1RZ_0LA0LA\n{head}\nv h1: sim(0..2)\nh1+\n"
                    "CLAIM c1: cp 1: (B,1,1)\nWITNESS c1: ref h1\n[HALT] c1"
                )
                _record, evidence = _evidence("C", _TRACE, answer)
                _v, notes, _h, classes = harness.feedback_bundle("C", _TRACE, evidence, level="G2")
                row = next(row for row in classes if row["id"] == "v1")
                self.assertEqual(row["leg"], leg)
                self.assertIn("Schritt 1", notes[0])
                self.assertNotIn("not A", notes[0])
                self.assertNotIn("not 4", notes[0])

    def test_g2_notes_have_no_digits(self):
        for values in (_STATE_VIOLATION, _HEAD_VIOLATION, _TAPE_VIOLATION):
            _record, evidence = _evidence("D", _HARD, _cyc_sheet(values))
            _v, notes, _h, _c = harness.feedback_bundle("D", _HARD, evidence, level="G2")
            binding_free = notes[0].split("v1: ", 1)[1]
            self.assertIsNone(re.search(r"[0-9]", binding_free), notes[0])
        # Bindungsluecke: Klasse + Hinweis sind ebenfalls digit-frei (die
        # Ketten-Note "ref h1" traegt modell-eigene ids und bleibt aussen vor).
        _record, evidence = _evidence("D", _HARD, _cyc_sheet((3, 6, -1), binding=False))
        _v, notes, hints, _c = harness.feedback_bundle("D", _HARD, evidence, level="G2")
        binding_note = next(note for note in notes if note.startswith("v1:"))
        self.assertIsNone(re.search(r"[0-9]", binding_note.split("v1: ", 1)[1]))
        self.assertIsNone(re.search(r"[0-9]", "\n".join(hints)))


class BindingProtectionTest(unittest.TestCase):
    """Die Kernzusage: ungeprueste, aber gueltige Werte werden geschuetzt."""

    def test_binding_case_message_says_values_not_refuted(self):
        for task, tokens in ((_HARD, _HARD_GOLD_TOKENS), (_LONG, _LONG_GOLD_TOKENS)):
            with self.subTest(task=task["id"]):
                answer = _cyc_sheet((34, 37, -1), binding=False)
                if task is _LONG:
                    answer = (
                        "h1: M zyklisch (Translation)\nv h1: cyc(133,142,1)\nh1+\n"
                        "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
                    )
                text = _full_text("D", task, answer, "G1")
                self.assertIn("keine Maschinenbindung", text)
                self.assertIn("nicht widerlegt", text)
                self.assertIn("Hinweis", text)
                seen = _tokens(text)
                for token in tokens:
                    self.assertNotIn(token, seen, f"Gold-Token {token} im Feedback")

    def test_hint_section_in_repair_message(self):
        text = prompts.build_repair_message(
            "D", _HARD, ["#?: v1"], ["v1: keine Maschinenbindung"], [], hint_lines=["Hinweis: Werte nicht aendern"]
        )
        self.assertIn("Hinweise:", text)
        self.assertIn("Werte nicht aendern", text)
        # Ohne Hinweise bleibt die V13-Struktur (keine leere Sektion).
        text_plain = prompts.build_repair_message("D", _HARD, ["#?: v1"], ["v1: x"], [])
        self.assertNotIn("Hinweise:", text_plain)


class PropertyLeakTest(unittest.TestCase):
    """Property: synthetische Verletzungsserien nennen keine Gold-Token."""

    def test_violation_series_leaks_no_gold_tokens(self):
        scenarios = [
            (_HARD, _cyc_sheet(_STATE_VIOLATION), _HARD_GOLD_TOKENS),
            (_HARD, _cyc_sheet(_HEAD_VIOLATION), _HARD_GOLD_TOKENS),
            (_HARD, _cyc_sheet(_TAPE_VIOLATION), _HARD_GOLD_TOKENS),
            (_HARD, _cyc_sheet((3, 6, -1), binding=False), _HARD_GOLD_TOKENS),
            (_HARD, _cyc_sheet((5, 3, -1)), _HARD_GOLD_TOKENS),
        ]
        for task, answer, gold in scenarios:
            for level in ("G0", "G1", "G2"):
                with self.subTest(task=task["id"], level=level):
                    text = _full_text("D", task, answer, level)
                    seen = _tokens(text)
                    for token in gold:
                        self.assertNotIn(token, seen, f"{level}: Gold-Token {token} im Feedback")

    def test_sim_refutation_series_leaks_no_gold_tokens(self):
        machine = _TRACE["machine"]
        gold = ["1", "4"]  # modell-eigene Werte sind erlaubt; hier: Gegenprobe der Klassen
        for level in ("G0", "G1", "G2"):
            answer = "a: M = 1RB1RZ_0LA0LA\nh1: cp 1: (B,4,1)\nv h1: sim(0..2)\nh1+\nCLAIM c1: cp 1: (B,1,1)\nWITNESS c1: ref h1\n[HALT] c1"
            text = _full_text("C", _TRACE, answer, level)
            # Der echte Reason nennt "the head is at 1, not 4" -- nie im Feedback.
            self.assertNotIn("the head is at", text)
            self.assertNotIn("not 4", text)

    def test_gold_certificates_do_not_appear_at_any_level(self):
        for task, gold in ((_HARD, _HARD_GOLD_TOKENS), (_LONG, _LONG_GOLD_TOKENS)):
            for level in ("G0", "G1", "G2"):
                with self.subTest(task=task["id"], level=level):
                    if task is _HARD:
                        answer = _cyc_sheet(_HEAD_VIOLATION)
                    else:
                        answer = (
                            "a: M = 1LC1LB_1LC1RC_1RA0LB\nh1: M zyklisch (Translation)\n"
                            "v h1: cyc(133,142,2)\nh1+\nCLAIM c1: M zyklisch (Translation)\n"
                            "WITNESS c1: ref h1\n[HALT] c1"
                        )
                    text = _full_text("D", task, answer, level)
                    for token in gold:
                        self.assertNotIn(token, _tokens(text))


class RunIntegrationTest(unittest.TestCase):
    """Die Leiter ist im Rundenlauf verdrahtet: Level, Klassen, Verzeichnisse."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_g2_run_records_level_and_classes_and_dir(self):
        root = self._root()
        fixed = (
            "a: M = 1LB1LB_1RA0LB\nh1: M zyklisch (Translation)\nv h1: cyc(3,6,-1)\nh1+\n"
            "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1"
        )
        summary = harness.run_rounds(
            "D",
            _HARD,
            1,
            root,
            _FakeArgs(feedback="G2"),
            call=_FakeCall([_cyc_sheet((3, 6, -1), binding=False), fixed]),
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["feedback"], "G2")
        run_dir = root / _HARD["id"] / "D-G2-rep1"
        record = json.loads((run_dir / "round0" / "parsed.json").read_text(encoding="utf-8"))
        self.assertEqual(record["feedback_level"], "G2")
        self.assertTrue(any(row["class"] == "binding_missing" for row in record["feedback_classes"]))
        self.assertIn("keine Maschinenbindung", record["next_feedback"])
        self.assertIn("Hinweis", record["next_feedback"])
        self.assertNotIn("34", _tokens(record["next_feedback"]))
        # Runde 1 sieht den Hinweis als eigenen Verlaufsteil (feedback_in).
        record1 = json.loads((run_dir / "round1" / "parsed.json").read_text(encoding="utf-8"))
        self.assertIn("Hinweis", record1["feedback_in"])

    def test_g0_default_keeps_v13_dir_naming(self):
        root = self._root()
        summary = harness.run_rounds(
            "D",
            _HARD,
            1,
            root,
            _FakeArgs(),
            call=_FakeCall([_cyc_sheet((3, 6, -1), binding=False), _cyc_sheet((3, 6, -1))]),
        )
        self.assertTrue(summary["final_solved"])
        self.assertEqual(summary["feedback"], "G0")
        self.assertTrue((root / _HARD["id"] / "D-rep1" / "round0" / "parsed.json").exists())

    def test_batch_task_filter_selects_named_tasks(self):
        class _Args:
            seed = 1
            tier_a = None
            tier_b = None
            tasks = "B4-0001,B3-0008"

        tier_a = {"tasks": [{"id": "A-0001"}]}
        tier_b = {"tasks": [{"id": "B3-0008"}, {"id": "B3-0002"}, {"id": "B4-0001"}]}
        selected = harness._select_tasks(tier_a, tier_b, _Args())
        self.assertEqual([task["id"] for task in selected], ["B4-0001", "B3-0008"])

    def test_batch_task_filter_rejects_unknown_ids(self):
        class _Args:
            seed = 1
            tier_a = None
            tier_b = None
            tasks = "NOPE"

        with self.assertRaises(SystemExit):
            harness._select_tasks({"tasks": []}, {"tasks": [{"id": "B3-0008"}]}, _Args())

    def test_runs_root_override_is_honoured(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        base = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)

        class _Override:
            runs_root = str(base / "resume-root")

        target = harness._runs_root(_Override())
        self.assertEqual(target, base / "resume-root")
        self.assertTrue(target.is_dir())

        class _Default:
            runs_root = None

        generated = harness._runs_root(_Default())
        self.addCleanup(shutil.rmtree, generated, ignore_errors=True)
        self.assertTrue(str(generated).startswith(str(harness.RUNS_DIR)))

    def test_display_and_run_dir_helpers(self):
        # Review-Findings: Logpfad darf ausserhalb ROOT nicht crashen und
        # muss das Level tragen.
        outside = Path("/tmp/opencode/outside-root")
        self.assertEqual(harness._display_path(outside), str(outside))
        self.assertEqual(harness._display_path(ROOT / "x"), "x")
        self.assertEqual(harness._run_dir_name("C", 1, "G0"), "C-rep1")
        self.assertEqual(harness._run_dir_name("C", 2, "G2"), "C-G2-rep2")


_ANCHOR = {
    "id": "B3-0005",
    "tier": "B",
    "tier_b_kind": "cyc",
    "machine": "0LA0LA",
    "certificate": [0, 1, -1],
    "certificate_given": False,
    "prompt": "Untersuche den Lauf.",
}


class EvaluateV14Test(unittest.TestCase):
    """Level-Gruppierung, Bindungs-Metrik und Klassen-Histogramm."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_g2_label_and_binding_protection(self):
        root = self._root()
        fixed = _cyc_sheet((34, 37, -1))
        # Ein Bindungsfall, der in R1 gerettet wird (Wert gueltig, Bindung fehlte).
        harness.run_rounds(
            "D", _HARD, 1, root, _FakeArgs(feedback="G2"),
            call=_FakeCall([_cyc_sheet((34, 37, -1), binding=False), fixed]),
        )
        # Ein Bindungsfall, der offen bleibt (gueltiger Fund, nie geschuetzt).
        harness.run_rounds(
            "D", _HARD, 2, root, _FakeArgs(feedback="G2"),
            call=_FakeCall(
                [
                    _cyc_sheet((34, 37, -1), binding=False),
                    _cyc_sheet((5, 9, 2)),
                    _cyc_sheet((5, 9, 2)),
                ]
            ),
        )
        # Ein REFUTED-Fall (Bindung vorhanden, Werte widerlegt) auf G2.
        harness.run_rounds(
            "D", _HARD, 3, root, _FakeArgs(feedback="G2"),
            call=_FakeCall([_cyc_sheet((5, 9, 2)), fixed]),
        )
        # Ein G0-Lauf derselben Aufgabe: eigenes Label, keine G2-Klassen.
        harness.run_rounds(
            "D", _HARD, 4, root, _FakeArgs(),
            call=_FakeCall([fixed]),
        )
        manifest, runs = evaluate.load_runs(root)
        summary = evaluate.summarize_runs(runs, sets={_HARD["id"]: _HARD})
        self.assertIn("D-G2-B", summary)
        self.assertIn("D-B", summary)
        g2 = summary["D-G2-B"]
        self.assertEqual(g2["feedback"], "G2")
        self.assertEqual(g2["n"], 3)
        self.assertEqual(g2["binding_protection"]["cases"], 2)
        self.assertEqual(g2["binding_protection"]["protected"], 1)
        self.assertEqual(g2["feedback_classes"].get("binding_missing"), 2)
        self.assertEqual(g2["feedback_classes"].get("values_refuted"), 2)
        self.assertIsNotNone(g2["hard_case_repair_rate"])
        markdown = evaluate.render_round_markdown(summary, manifest)
        self.assertIn("Bindungsschutz", markdown)
        # Die Tabellenzeile selbst muss das Level tragen (nicht nur die
        # Klassen-Sektion), und die G0-Zeile bleibt am alten Label.
        self.assertIn("| D-G2-B | 3 |", markdown)
        self.assertIn("| D-B | 1 |", markdown)

    def test_g0_label_stays_legacy_shaped(self):
        root = self._root()
        harness.run_rounds(
            "C", _HARD, 1, root, _FakeArgs(),
            call=_FakeCall([_cyc_sheet((34, 37, -1), binding=False), _cyc_sheet((34, 37, -1))]),
        )
        _manifest, runs = evaluate.load_runs(root)
        summary = evaluate.summarize_runs(runs, sets={_HARD["id"]: _HARD})
        self.assertIn("C-B", summary)
        self.assertEqual(summary["C-B"]["feedback"], "G0")


class ScanFeedbackTest(unittest.TestCase):
    """Der empirische Leck-Scan: injizierte Verletzung wird gefunden,
    saubere Laeufe melden 0, modell-eigene ids sind keine Verletzung."""

    def _load_scan(self):
        return _load("scan_feedback")

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _binding_run(self, root, rep=1):
        harness.run_rounds(
            "D", _HARD, rep, root, _FakeArgs(feedback="G2"),
            call=_FakeCall([_cyc_sheet((3, 6, -1), binding=False), _cyc_sheet((3, 6, -1))]),
        )

    def test_clean_run_has_zero_violations(self):
        scan = self._load_scan()
        root = self._root()
        self._binding_run(root)
        report = scan.scan_run(str(root), {_HARD["id"]: _HARD})
        self.assertGreaterEqual(report["scanned"], 1)
        self.assertEqual(report["violations"], [])

    def test_injected_gold_value_is_found(self):
        scan = self._load_scan()
        root = self._root()
        self._binding_run(root)
        path = root / _HARD["id"] / "D-G2-rep1" / "round0" / "parsed.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["next_feedback"] += "\nv1: das Zertifikat (34,37,-1) traegt doch"
        path.write_text(json.dumps(record), encoding="utf-8")
        report = scan.scan_run(str(root), {_HARD["id"]: _HARD})
        self.assertTrue(report["violations"], "die injizierte Gold-Nennung fehlt")

    def test_injected_word_separated_gold_value_is_found(self):
        # Die fruehere Erkennung haette "Zertifikat 34" als id-Kontext
        # durchgewinkt (rstrip + Buchstabe davor); das darf nicht passieren.
        scan = self._load_scan()
        root = self._root()
        self._binding_run(root)
        path = root / _HARD["id"] / "D-G2-rep1" / "round0" / "parsed.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["next_feedback"] += "\nder Wert lautet 34 und nicht 35"
        path.write_text(json.dumps(record), encoding="utf-8")
        report = scan.scan_run(str(root), {_HARD["id"]: _HARD})
        self.assertTrue(
            any(hit["kind"] == "certificate" and hit["value"] == "34" for hit in report["violations"]),
            "Zahl nach Wortgrenze muss als Verletzung gelten",
        )

    def test_benign_contexts_stay_explained(self):
        scan = self._load_scan()
        self.assertTrue(scan._explained("v1: nichts", 1))
        self.assertTrue(scan._explained("siehe Schritt 1 dort", 14))
        self.assertTrue(scan._explained("sim(0..2)", 4))
        self.assertTrue(scan._explained("line 0: no CLAIM zone", 5))
        self.assertFalse(scan._explained("der Wert lautet 34", 16))

    def test_paren_certificate_is_not_explained(self):
        # Eine Aufgaben-Klammer mit Werten ist eine Verletzung; nur die
        # Zeugen-Klammern des Modells (sim/cyc) gelten als erklaert.
        scan = self._load_scan()
        self.assertFalse(scan._explained("das Zertifikat (34,37,-1) traegt", 16))
        self.assertTrue(scan._explained("cyc(34,37,-1)", 4))

    def test_explained_is_linear_on_long_letter_runs(self):
        # Lineare Rueckwaertssuche statt verankertem Regex (ReDoS-Lehre).
        import time as _time

        scan = self._load_scan()
        text = "x" * 60000 + " 34"
        start = _time.perf_counter()
        self.assertFalse(scan._explained(text, len(text) - 2))
        self.assertLess(_time.perf_counter() - start, 0.5)

    def test_missing_runs_path_is_an_error_not_zero(self):
        scan = self._load_scan()
        with self.assertRaises(SystemExit):
            scan.scan_run(str(ROOT / "does-not-exist-xyz"), {})

    def test_empty_sets_path_is_an_error_not_zero(self):
        # Review-Fund: ein falscher --sets-Pfad darf nicht wie ein sauberer
        # Befund aussehen ("violations 0").
        scan = self._load_scan()
        with self.assertRaises(SystemExit):
            scan.load_tasks(ROOT / "does-not-exist-xyz")
        with self.assertRaises(SystemExit):
            evaluate.load_tasks(ROOT / "does-not-exist-xyz")

    def test_model_owned_ids_are_not_violations(self):
        scan = self._load_scan()
        root = self._root()
        # Gold (0,1,-1): die Ziffern 0/1 kollidieren mit ids ("v1", "h1") --
        # der Scan darf daraus keine Verletzung machen.
        harness.run_rounds(
            "D", _ANCHOR, 1, root, _FakeArgs(feedback="G2"),
            call=_FakeCall(
                [
                    "h1: M zyklisch (Translation)\nv h1: cyc(0,1,-1)\nh1+\n"
                    "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1",
                    "a: M = 0LA0LA\nh1: M zyklisch (Translation)\nv h1: cyc(0,1,-1)\nh1+\n"
                    "CLAIM c1: M zyklisch (Translation)\nWITNESS c1: ref h1\n[HALT] c1",
                ]
            ),
        )
        report = scan.scan_run(str(root), {_ANCHOR["id"]: _ANCHOR})
        self.assertEqual(report["violations"], [])

    def test_legacy_layout_runs_are_scannable(self):
        # Der Scan arbeitet auf next_feedback-Feldern; ein Lauf ohne Feedback
        # (Runde 0 geloest) zaehlt einfach nichts.
        scan = self._load_scan()
        root = self._root()
        harness.run_rounds(
            "D", _HARD, 1, root, _FakeArgs(),
            call=_FakeCall([_cyc_sheet((34, 37, -1))]),
        )
        report = scan.scan_run(str(root), {_HARD["id"]: _HARD})
        self.assertEqual(report["scanned"], 0)
        self.assertEqual(report["violations"], [])


class SetsV04Test(unittest.TestCase):
    """Sets v0.4: erweiterte harte Zyklus-Familie + Kontrollen; v0.3 eingefroren."""

    TIER_B_V04 = "tier_b_v11-b-0.4.json"
    # Die eingefrorenen Staende v0.1-v0.3 (Datei-Hash der committeten Bytes).
    FROZEN = {
        "tier_a_v11-a-0.1.json": "50c985e169aa500799824d7e05fa5cf918b5f1b1c3e45be5a4cb8c3ec73474f9",
        "tier_b_v11-b-0.1.json": "074ab6bf5ebfc2132a73dcaae7b490754e559e1870a594c28dc0deb9a2b02ccf",
        "tier_a_v11-a-0.2.json": "007424292fd10129877b3c0c2d733de6e556d08183955b6d9a10c0d2d8be81ce",
        "tier_b_v11-b-0.2.json": "68eb917ebd26ae2d4ed1200b56c62114edd019bba868d2bd0d350348aad52395",
        "tier_a_v11-a-0.3.json": "eb294ea93235e19c247eed4c547bbe879ea357aa86f8cdd80b979e4f9c5d11c3",
        "tier_b_v11-b-0.3.json": "a1fcac5e4c6ae568dc17a4cd56928eaba7d7949ec94760d02281b1e5d3c1c51f",
    }
    EXPECTED_IDS = ["B3-0002", "B3-0005", "B3-0008", "B4-0001", "B4-0002", "B4-0003"]

    def _load(self):
        return json.loads((SETS / self.TIER_B_V04).read_text(encoding="utf-8"))

    def test_v04_file_exists_and_parses(self):
        payload = self._load()
        self.assertEqual(payload["set_version"], "v11-b-0.4")
        self.assertEqual([task["id"] for task in payload["tasks"]], self.EXPECTED_IDS)
        ids = [task["id"] for task in payload["tasks"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_v04_trace_control_rederives_its_gold(self):
        tasks = [t for t in self._load()["tasks"] if t["tier_b_kind"] == "trace"]
        self.assertEqual([t["id"] for t in tasks], ["B3-0002"])
        from bemyself import turing

        for task in tasks:
            machine = turing.parse(task["machine"])
            _result, snapshots = turing.run_checkpoints(
                machine, max(task["checkpoints_t"]), tuple(task["checkpoints_t"])
            )
            for step, letter, head, window in task["checkpoints_gold"]:
                snapshot = snapshots.get(step)
                self.assertIsNotNone(snapshot, f"{task['id']} t={step}")
                self.assertEqual(chr(ord("A") + snapshot.state), letter, f"{task['id']} t={step}")
                self.assertEqual(snapshot.head, head, f"{task['id']} t={step}")
                window_now = "".join(str(c) for c in snapshot.left[::-1] + snapshot.right)
                self.assertEqual(window_now, window, f"{task['id']} t={step}")

    def test_v04_cyc_certificates_confirmed_and_prompts_leak_free(self):
        tasks = [t for t in self._load()["tasks"] if t["tier_b_kind"] == "cyc"]
        self.assertEqual(len(tasks), 5)
        not_given = [t for t in tasks if t.get("certificate_given") is False]
        self.assertEqual(len(not_given), 5, "alle neuen Zyklus-Aufgaben ohne Vorgabe")
        from bemyself.claimtypes import cycle
        from bemyself.model import Claim, Verdict

        for task in tasks:
            t1, t2, d = task["certificate"]
            claim = Claim(
                kind="cycle",
                line=0,
                raw="set-check",
                fields={
                    "machine": task["machine"],
                    "values": f"{t1},{t2},{d}",
                    "t1": str(t1),
                    "t2": str(t2),
                    "d": str(d),
                },
            )

            class _Ctx:
                cycle_limit = cycle.DEFAULT_CYCLE_LIMIT

            result = cycle.check(claim, _Ctx())
            self.assertEqual(result.verdict, Verdict.CONFIRMED, f"{task['id']}: {result.reason}")
            prompt = task["prompt"]
            for needle in (f"t1={t1}", f"t2={t2}", f"d={d}"):
                self.assertNotIn(needle, prompt, task["id"])
            self.assertIn("selbst", prompt, task["id"])

    def test_v04_new_tasks_match_the_frozen_search_finds(self):
        tasks = {task["id"]: task for task in self._load()["tasks"]}
        self.assertEqual(tasks["B4-0001"]["machine"], "1RB1LC_1RD0LC_1RB1LB_1LC1RD")
        self.assertEqual(tasks["B4-0001"]["certificate"], [65, 81, -2])
        self.assertEqual(tasks["B4-0002"]["machine"], "1LC1RD_1RZ0LZ_1RA1LC_0RC1RC")
        self.assertEqual(tasks["B4-0002"]["certificate"], [14, 21, -1])
        self.assertEqual(tasks["B4-0003"]["machine"], "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC")
        self.assertEqual(tasks["B4-0003"]["certificate"], [6, 16, 2])
        self.assertIn("Suchlauf", tasks["B4-0001"]["source"])
        self.assertIn("20260915", tasks["B4-0001"]["source"])
        self.assertIn("Suchlauf", tasks["B4-0002"]["source"])
        self.assertIn("20260914", tasks["B4-0002"]["source"])

    def test_v04_search_reproduces_the_b4_0002_find(self):
        # Der deterministische Suchlauf (Attempt-Zaehlung statt Wall-Clock)
        # liefert mit der eingefrorenen Saat dieselbe Maschine; die Angabe im
        # source-Feld ist damit nachpruefbar.
        import importlib.util
        import random

        spec = importlib.util.spec_from_file_location("build_sets", TOOLING / "build_sets.py")
        build_sets = importlib.util.module_from_spec(spec)
        sys.modules["build_sets"] = build_sets
        spec.loader.exec_module(build_sets)

        found = build_sets._find_translated_cyclers(
            random.Random(20260914), 1, max_attempts=9000, min_t2=20
        )
        self.assertEqual(len(found), 1)
        find = found[0]
        self.assertEqual(find["machine"], "1LC1RD_1RZ0LZ_1RA1LC_0RC1RC")
        self.assertEqual(find["certificate"], (14, 21, -1))
        self.assertEqual(find["attempts"], 8913)

    def test_frozen_sets_untouched(self):
        for name, digest in self.FROZEN.items():
            self.assertEqual(_sha256(SETS / name), digest, name)

    def test_rebuild_writes_v04_and_keeps_v01_v03_byte_identical(self):
        import subprocess

        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(dir=tmp_root))
        # v0.1 ist Altbestand und wird nicht mehr gebaut; der Builder schreibt
        # v0.2/v0.3 (unveraendert) und v0.4 (neu).
        written = [name for name in self.FROZEN if "0.1" not in name] + [self.TIER_B_V04]
        try:
            subprocess.run(
                [sys.executable, str(TOOLING / "build_sets.py"), "--out", str(tmp)],
                check=True,
                cwd=ROOT,
                capture_output=True,
            )
            for name in written:
                self.assertEqual((tmp / name).read_bytes(), (SETS / name).read_bytes(), name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_harness_default_set_is_v04(self):
        self.assertEqual(harness._TIER_B_SET, self.TIER_B_V04)
        self.assertEqual(harness._TIER_A_SET, "tier_a_v11-a-0.3.json")


def _sha256(path):
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests des leancheck-Elaborators V18 (Lean-4-Schnipsel).

leancheck legt je Aufruf ein Minimalprojekt (gepinnte Toolchain, keine
Dependencies) an, laesst ``lake env lean`` mit hartem Timeout darauf laufen
und klassifiziert: valid | invalid | timeout | infra_error. Die Tests
arbeiten zweigleisig:

- Fake-Lake-Skripte fuer die reine Prozess-/Parser-Mechanik (deterministisch,
  kein Lean noetig): Exit-Codes, Fehlerzeilen, Timeout-Kill, print-axioms-
  Anhang, infra_error bei fehlendem lake.
- Echte Elaborationen (skipUnless Lean verfuegbar): valide/ungueltige
  Schnipsel, sorry-Erkennung, Axiom-Sonde (decide/omega), unknownIdentifier
  der angehaengten #print-Zeile darf die Gueltigkeit nicht kippen.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import sys
import tempfile
import textwrap
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


leancheck = _load("leancheck")


def _lean_available():
    return shutil.which("lake") is not None or (Path.home() / ".elan" / "bin" / "lake").exists()


def _fake_lake(directory: Path, body: str) -> Path:
    """A scripted lake stand-in: runs ``body`` as a shell script."""
    path = directory / "fake-lake"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class FakeLakeTests(unittest.TestCase):
    """Prozess- und Parser-Mechanik mit geskriptetem lake."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_valid_silent(self):
        lake = _fake_lake(self.tmp, "exit 0\n")
        res = leancheck.check("import Std\n", lake_bin=str(lake), root=self.tmp / "root")
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["errors"], [])
        self.assertFalse(res["sorry_used"])

    def test_invalid_error_line_parsed(self):
        lake = _fake_lake(
            self.tmp,
            "echo 'snippet.lean:3:7: error: Type mismatch'\n"
            "echo 'snippet.lean:2:1: warning: unused variable `x`'\n"
            "exit 1\n",
        )
        res = leancheck.check("theorem t : True := trivial\n", lake_bin=str(lake), root=self.tmp / "root")
        self.assertEqual(res["status"], "invalid")
        self.assertEqual(res["exit_code"], 1)
        self.assertEqual(len(res["errors"]), 1)
        self.assertEqual(res["errors"][0]["line"], 3)
        self.assertEqual(res["errors"][0]["col"], 7)
        self.assertIn("Type mismatch", res["errors"][0]["message"])
        self.assertEqual(len(res["warnings"]), 1)

    def test_error_with_code_suffix(self):
        lake = _fake_lake(
            self.tmp,
            "echo 'snippet.lean:4:14: error(lean.unknownIdentifier): Unknown constant main_thm'\n"
            "exit 1\n",
        )
        res = leancheck.check("theorem other : True := trivial\n", lake_bin=str(lake), root=self.tmp / "root")
        self.assertEqual(res["errors"][0]["code"], "lean.unknownIdentifier")

    def test_timeout_kills_process(self):
        lake = _fake_lake(self.tmp, "sleep 30\n")
        res = leancheck.check("import Std\n", lake_bin=str(lake), root=self.tmp / "root", timeout=0.5)
        self.assertEqual(res["status"], "timeout")
        self.assertLess(res["duration_s"], 10.0)

    def test_infra_error_when_lake_missing(self):
        res = leancheck.check("import Std\n", lake_bin=str(self.tmp / "does-not-exist"), root=self.tmp / "root")
        self.assertEqual(res["status"], "infra_error")
        self.assertIn("lake", res["message"].lower())

    def test_nonzero_exit_without_error_lines_is_infra_error(self):
        # Ein lake-Abbruch ohne parsebare Diagnosezeile (fehlende Datei,
        # elan-Downloadfehler, unbekannte Option) darf NICHT als valid gelten.
        lake = _fake_lake(self.tmp, 'echo "error: no such file or directory"\nexit 1\n')
        res = leancheck.check("import Std\n", lake_bin=str(lake), root=self.tmp / "root")
        self.assertEqual(res["status"], "infra_error")
        self.assertEqual(res["exit_code"], 1)
        self.assertIn("1", res["message"])

    def test_relative_snippet_arg_is_used(self):
        # Lean schreibt Diagnosen mit dem Argument-Pfad; bei absolutem Pfad
        # mit Leerzeichen zerfällt die Dateiprefix-Erkennung. Darum wird der
        # Schnipsel relativ zum Projekt-cwd übergeben.
        lake = _fake_lake(self.tmp, 'printf "%s\\n" "$3"\n')
        res = leancheck.check("import Std\n", lake_bin=str(lake), root=self.tmp / "root")
        arg = res["output"].strip()
        self.assertFalse(os.path.isabs(arg), arg)
        self.assertTrue(arg.endswith(".lean"), arg)

    def test_resolve_root_returns_absolute(self):
        resolved = leancheck._resolve_root(Path("some") / "relative")
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(Path(leancheck._resolve_root(None)).is_absolute(), True)

    def test_no_print_axioms_without_request(self):
        lake = _fake_lake(self.tmp, 'cat "$3"\n')
        res = leancheck.check("theorem t : True := trivial\n", lake_bin=str(lake), root=self.tmp / "root")
        self.assertNotIn("#print axioms", res["output"])

    def test_print_axioms_appended_when_requested(self):
        lake = _fake_lake(self.tmp, 'cat "$3"\n')
        res = leancheck.check(
            "theorem main_thm : True := trivial\n",
            lake_bin=str(lake),
            root=self.tmp / "root",
            print_axioms_for="main_thm",
        )
        self.assertIn("#print axioms main_thm", res["output"])

    def test_print_axioms_rejects_bad_name(self):
        lake = _fake_lake(self.tmp, "exit 0\n")
        with self.assertRaises(ValueError):
            leancheck.check("import Std\n", lake_bin=str(lake), root=self.tmp / "root", print_axioms_for="a b c")

    def test_snippet_persisted(self):
        lake = _fake_lake(self.tmp, "exit 0\n")
        res = leancheck.check("import Std\n", lake_bin=str(lake), root=self.tmp / "root")
        self.assertTrue(Path(res["file"]).exists())
        self.assertIn("import Std", Path(res["file"]).read_text(encoding="utf-8"))

    def test_sorry_token_detected(self):
        lake = _fake_lake(self.tmp, "exit 0\n")
        res = leancheck.check(
            "theorem t : True := by sorry\n", lake_bin=str(lake), root=self.tmp / "root"
        )
        self.assertTrue(res["sorry_used"])

    def test_sorry_warning_detected(self):
        lake = _fake_lake(
            self.tmp,
            "echo 'snippet.lean:1:8: warning: declaration uses `sorry`'\n"
            "exit 0\n",
        )
        res = leancheck.check(
            "theorem t : True := by\n  trivial\n", lake_bin=str(lake), root=self.tmp / "root"
        )
        self.assertTrue(res["sorry_used"])


class ParserUnitTests(unittest.TestCase):
    def test_parse_axioms_none(self):
        out = "'main_thm' does not depend on any axioms\n"
        self.assertEqual(leancheck._parse_axioms(out), "none")

    def test_parse_axioms_list(self):
        out = "'main_thm' depends on axioms: [propext, Quot.sound]\n"
        self.assertEqual(leancheck._parse_axioms(out), ["propext", "Quot.sound"])

    def test_parse_axioms_sorry(self):
        out = "'main_thm' depends on axioms: [sorryAx]\n"
        self.assertEqual(leancheck._parse_axioms(out), ["sorryAx"])

    def test_parse_axioms_absent(self):
        self.assertIsNone(leancheck._parse_axioms("no axioms line here\n"))

    def test_parse_output_multiline_message(self):
        out = textwrap.dedent(
            """\
            snippet.lean:2:41: error: Type mismatch
              rfl
            has type
              ?m.15 = ?m.15
            """
        )
        errors, warnings = leancheck._parse_output(out)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["line"], 2)
        self.assertEqual(warnings, [])


@unittest.skipUnless(_lean_available(), "Lean-Toolchain nicht verfuegbar")
class RealLeanTests(unittest.TestCase):
    """Echte Elaboration gegen die gepinnte Toolchain (Integration)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "root"

    def test_valid_decide_and_axioms_none(self):
        res = leancheck.check(
            "import Std\n\ntheorem main_thm : (2 + 2 = 4) := by decide\n",
            root=self.root,
            print_axioms_for="main_thm",
        )
        self.assertEqual(res["status"], "valid", res.get("output"))
        self.assertEqual(res["axioms"], "none")
        self.assertFalse(res["sorry_used"])

    def test_omega_reports_propext(self):
        res = leancheck.check(
            "import Std\n\ntheorem main_thm (n : Nat) (h : n > 3) : n + 2 > 5 := by omega\n",
            root=self.root,
            print_axioms_for="main_thm",
        )
        self.assertEqual(res["status"], "valid", res.get("output"))
        self.assertIn("propext", res["axioms"])

    def test_invalid_false_claim(self):
        res = leancheck.check(
            "import Std\n\ntheorem main_thm : (2 + 2 = 5) := by decide\n", root=self.root
        )
        self.assertEqual(res["status"], "invalid")
        self.assertTrue(res["errors"])

    def test_sorry_is_not_a_proof(self):
        res = leancheck.check(
            "import Std\n\ntheorem main_thm : (2 + 2 = 4) := by sorry\n",
            root=self.root,
            print_axioms_for="main_thm",
        )
        self.assertEqual(res["status"], "valid")
        self.assertTrue(res["sorry_used"])
        self.assertEqual(res["axioms"], ["sorryAx"])

    def test_unknown_print_name_does_not_flip_validity(self):
        res = leancheck.check(
            "import Std\n\ntheorem other : True := trivial\n",
            root=self.root,
            print_axioms_for="main_thm",
        )
        self.assertEqual(res["status"], "valid", res.get("output"))
        self.assertIsNone(res["axioms"])

    def test_root_with_spaces_classifies_invalid(self):
        # Regression (Review-Befund): Root-Pfade mit Leerzeichen dürfen die
        # Fehlerzeilen-Erkennung nicht brechen (sonst stilles `valid`).
        spaced = self.tmp / "mit leerzeichen" / "root"
        res = leancheck.check(
            "import Std\n\ntheorem main_thm : (2 + 2 = 5) := by decide\n", root=spaced
        )
        self.assertEqual(res["status"], "invalid", res.get("output"))
        self.assertTrue(res["errors"])

    def test_root_with_spaces_classifies_valid(self):
        spaced = self.tmp / "auch hier drin" / "root"
        res = leancheck.check(
            "import Std\n\ntheorem main_thm : (2 + 2 = 4) := by decide\n",
            root=spaced,
            print_axioms_for="main_thm",
        )
        self.assertEqual(res["status"], "valid", res.get("output"))
        self.assertEqual(res["axioms"], "none")


if __name__ == "__main__":
    unittest.main()

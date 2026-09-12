"""Tests for the eval runner, its metrics and the CLI wiring."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from bemyself import evalset
from bemyself.eval import THRESHOLDS, evaluate, render_text

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_PATH = os.path.join(REPO_ROOT, "tests", "data", "pruefset.json")


class EvalEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.fixture = evalset.build_fixture(os.path.join(cls._tmp.name, "fixture"))
        cls.document = evalset.load_set(SET_PATH)
        cls.report = evaluate(
            cls.document, cls.fixture, os.path.join(cls._tmp.name, "work"), SET_PATH
        )
        cls.by_name = {case["name"]: case for case in cls.report["cases"]}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def verdicts(self, name):
        return {claim["kind"]: claim["verdict"] for claim in self.by_name[name]["claims"]}

    def test_thresholds_are_met(self):
        rates = self.report["rates"]
        self.assertEqual(rates["detection_total"], 15)
        self.assertEqual(rates["true_confirmation_total"], 15)
        self.assertEqual(rates["detection_hits"], rates["detection_total"])
        self.assertEqual(rates["false_confirmation_hits"], 0)
        self.assertEqual(rates["true_confirmation_hits"], rates["true_confirmation_total"])
        self.assertGreater(rates["unverifiable_claims"], 0)
        self.assertLess(rates["unverifiable_rate"], 0.5)
        self.assertTrue(self.report["thresholds_met"])
        self.assertEqual(self.report["expectation_misses"], 0)
        self.assertTrue(self.report["ok"])

    def test_measured_rates_clear_the_documented_thresholds(self):
        self.assertEqual(THRESHOLDS["detection_rate"], 0.90)
        self.assertEqual(THRESHOLDS["true_confirmation_rate"], 0.90)
        self.assertEqual(THRESHOLDS["false_confirmation_rate"], 0.0)
        for key, value in THRESHOLDS.items():
            self.assertGreaterEqual(self.report["rates"][key], value, key)

    def test_every_false_case_is_detected(self):
        for case in self.report["cases"]:
            if case["group"] != "false":
                continue
            self.assertTrue(case["detected"], case["name"])
            self.assertFalse(case["false_confirmed"], case["name"])

    def test_every_genuine_case_confirms(self):
        for case in self.report["cases"]:
            if case["group"] == "genuine":
                self.assertEqual(case["exit"], 0, case["name"])

    def test_verdicts_per_case(self):
        self.assertEqual(self.verdicts("f01-commit-missing")["commit_exists"], "REFUTED")
        self.assertEqual(
            self.verdicts("f02-tests-claimed-green-but-failing")["tests_green"], "REFUTED"
        )
        self.assertEqual(
            self.verdicts("f03-tests-claimed-green-without-tests")["tests_green"], "REFUTED"
        )
        self.assertEqual(self.verdicts("f06-diff-empty")["diff_scope"], "REFUTED")
        self.assertEqual(self.verdicts("f07-diff-planned-but-unchanged")["diff_scope"], "REFUTED")
        self.assertEqual(self.verdicts("f08-diff-extra-changed")["diff_scope"], "REFUTED")
        self.assertEqual(self.verdicts("f09-branch-unpushed")["branch_pushed"], "REFUTED")
        self.assertEqual(
            self.verdicts("f14-hostile-control-characters")["commit_exists"], "UNVERIFIABLE"
        )
        self.assertEqual(self.verdicts("f15-commit-blob-object")["commit_exists"], "REFUTED")
        self.assertEqual(self.verdicts("g03-tests-green")["tests_green"], "CONFIRMED")
        self.assertEqual(self.verdicts("g08-full-report")["diff_scope"], "CONFIRMED")

    def test_mandatory_case_shapes(self):
        f10 = self.by_name["f10-commit-non-hex-head"]
        commits = [claim for claim in f10["claims"] if claim["kind"] == "commit_exists"]
        self.assertEqual(len(commits), 2)
        self.assertNotIn("CONFIRMED", [claim["verdict"] for claim in f10["claims"]])
        self.assertEqual(f10["exit"], 3)
        f11 = self.by_name["f11-report-without-claims"]
        self.assertEqual(f11["claims"], [])
        self.assertEqual(f11["exit"], 3)
        self.assertTrue(f11["detected"])
        for name in ("f12-hostile-giant-line", "f13-hostile-huge-report"):
            case = self.by_name[name]
            self.assertEqual(case["claims"], [], name)
            self.assertEqual(case["exit"], 3, name)

    def test_text_rendering_is_sanitized_and_labeled(self):
        text = render_text(self.report)
        for label in (
            "Erkennungsrate",
            "Falschbestaetigungsrate",
            "Bestaetigungsrate",
            "Unpruefbar-Quote",
        ):
            self.assertIn(label, text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\u202e", text)
        self.assertIn("OK", text)

    def test_json_report_roundtrips(self):
        payload = json.loads(json.dumps(self.report))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["rates"]["detection_rate"], 1.0)
        self.assertEqual(payload["rates"]["false_confirmation_rate"], 0.0)


class MetricFailureTest(unittest.TestCase):
    """The metrics must be able to turn red: a false confirmation is counted."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.fixture = evalset.build_fixture(os.path.join(cls._tmp.name, "fixture"))
        commits = cls.fixture.commits
        cls.document = {
            "version": 1,
            "fixture": {"base": commits["base"], "head": commits["fixed"]},
            "cases": [
                {
                    "name": "x-false-confirmable",
                    "group": "false",
                    "note": "the target claim is confirmable on purpose",
                    "base": commits["base"],
                    "targets": ["commit_exists"],
                    "report": f"**send_to payload:** `[COMMIT: {commits['good']}]`\n",
                },
                {
                    "name": "x-genuine-missing",
                    "group": "genuine",
                    "note": "claims a non-existent commit",
                    "base": commits["base"],
                    "targets": [],
                    "report": f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n",
                },
            ],
        }

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_false_confirmation_is_counted(self):
        report = evaluate(self.document, self.fixture, os.path.join(self._tmp.name, "work"))
        self.assertEqual(report["rates"]["false_confirmation_rate"], 1.0)
        self.assertEqual(report["rates"]["detection_rate"], 0.0)
        self.assertEqual(report["rates"]["true_confirmation_rate"], 0.0)
        self.assertFalse(report["thresholds_met"])
        self.assertFalse(report["ok"])


class SetLoadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def write(self, name, data):
        path = os.path.join(self._tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_load_set_rejects_broken_json(self):
        path = self.write("broken.json", b"{not json")
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_unknown_version(self):
        path = self.write("old.json", json.dumps({"version": 99, "cases": []}).encode())
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_cases_without_reports(self):
        document = evalset.load_set(SET_PATH)
        del document["cases"][0]["report"]
        path = self.write("noreport.json", evalset.set_bytes(document))
        with self.assertRaises(ValueError):
            evalset.load_set(path)


class EvalCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def invoke(self, *args, set_path=None, tmp="run"):
        command = [
            sys.executable,
            "-m",
            "bemyself",
            "eval",
            "--set",
            set_path or SET_PATH,
        ]
        if tmp is not None:
            command += ["--tmp", os.path.join(self._tmp.name, tmp)]
        return subprocess.run(command + list(args), cwd=REPO_ROOT, capture_output=True, text=True)

    def test_json_run_reports_the_rates(self):
        proc = self.invoke("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["rates"]["detection_rate"], 1.0)
        self.assertEqual(payload["rates"]["false_confirmation_rate"], 0.0)
        self.assertEqual(payload["expectation_misses"], 0)

    def test_text_run_prints_the_table(self):
        proc = self.invoke(tmp="run-text")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Erkennungsrate", proc.stdout)
        self.assertIn("Falschbestaetigungsrate", proc.stdout)
        self.assertIn("OK", proc.stdout)

    def test_missing_set_is_an_error(self):
        proc = self.invoke(set_path=os.path.join(self._tmp.name, "nope.json"), tmp=None)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("set", proc.stderr.lower())

    def test_set_for_a_foreign_fixture_is_an_error(self):
        document = evalset.load_set(SET_PATH)
        document["fixture"]["base"] = "0" * 40
        path = self.write(document, "foreign.json")
        proc = self.invoke(set_path=path, tmp="run-foreign")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("fixture", proc.stderr.lower())

    def write(self, document, name):
        path = os.path.join(self._tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(evalset.set_bytes(document))
        return path


if __name__ == "__main__":
    unittest.main()

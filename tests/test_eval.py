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
        self.assertEqual(rates["detection_total"], 21)
        self.assertEqual(rates["true_confirmation_total"], 22)
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
        # Host dependent (exit 5 on Python >= 3.12, exit 0 before); only "never
        # CONFIRMED" is guaranteed, and that is what the set pins.
        self.assertNotEqual(
            self.verdicts("f03-tests-claimed-green-without-tests")["tests_green"], "CONFIRMED"
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
        self.assertEqual(self.verdicts("g16-halt-confirmed")["halt"], "CONFIRMED")
        self.assertEqual(self.verdicts("f16-halt-wrong-step-count")["halt"], "REFUTED")
        self.assertEqual(self.verdicts("f17-halt-wrong-score")["halt"], "REFUTED")
        self.assertEqual(self.verdicts("f18-compute-wrong-hash")["compute"], "REFUTED")
        self.assertEqual(self.verdicts("g18-searched-bounded")["searched"], "CONFIRMED")
        bb6 = self.by_name["g17-halt-beyond-verification"]
        halt_claims = [claim for claim in bb6["claims"] if claim["kind"] == "halt"]
        self.assertEqual(len(halt_claims), 2)
        self.assertEqual([claim["verdict"] for claim in halt_claims], ["UNVERIFIABLE"] * 2)

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

    def test_load_set_rejects_deeply_nested_json(self):
        path = self.write("deep.json", b"[" * 300000)
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_unknown_version(self):
        path = self.write("old.json", json.dumps({"version": 99, "cases": []}).encode())
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_oversized_files(self):
        path = self.write("huge.json", b"x" * ((4 << 20) + 1))
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_case_reports_over_the_check_cap(self):
        document = evalset.load_set(SET_PATH)
        document["cases"][0]["report"] = "x" * ((1 << 20) + 1)
        path = self.write("big-report.json", evalset.set_bytes(document))
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_bad_not_confirmed_pins(self):
        document = evalset.load_set(SET_PATH)
        document["cases"][0]["expect_not_confirmed"] = "tests_green"
        path = self.write("bad-not-confirmed.json", evalset.set_bytes(document))
        with self.assertRaises(ValueError):
            evalset.load_set(path)

    def test_load_set_rejects_cases_without_reports(self):
        document = evalset.load_set(SET_PATH)
        del document["cases"][0]["report"]
        path = self.write("noreport.json", evalset.set_bytes(document))
        with self.assertRaises(ValueError):
            evalset.load_set(path)


class HostileSetTextTest(unittest.TestCase):
    """A hostile set file must not be able to spoof the terminal output."""

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
                    "name": "x-\x1b[2Kevil\u202e",
                    "group": "genuine",
                    "note": "hostile case name and expected kind",
                    "base": commits["base"],
                    "targets": [],
                    "expect_verdicts": {"\x1b[2Kghost": "CONFIRMED"},
                    "report": f"**send_to payload:** `[COMMIT: {commits['good']}]`\n",
                }
            ],
        }

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_hostile_names_are_sanitized(self):
        report = evaluate(self.document, self.fixture, os.path.join(self._tmp.name, "work"))
        self.assertGreater(report["expectation_misses"], 0)
        text = render_text(report)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\u202e", text)


class EvalCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def invoke(self, *args, set_path=None, tmp="run", cwd=None):
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
        env = dict(os.environ)
        env["PYTHONPATH"] = REPO_ROOT + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        return subprocess.run(
            command + list(args),
            cwd=cwd or REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_json_run_reports_the_rates(self):
        proc = self.invoke("--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["rates"]["detection_rate"], 1.0)
        self.assertEqual(payload["rates"]["false_confirmation_rate"], 0.0)
        self.assertEqual(payload["expectation_misses"], 0)

    def test_sandbox_mode_reaches_every_test_run(self):
        proc = self.invoke("--json", "--sandbox", "off", tmp="run-sandbox-off")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        ran = [
            claim
            for case in payload["cases"]
            for claim in case["claims"]
            if claim["kind"] in ("tests_green", "tests_exit")
            and claim["verdict"] in ("CONFIRMED", "REFUTED")
        ]
        self.assertTrue(ran, "the set must yield executed test runs")
        self.assertTrue(all("--sandbox=off" in claim["reason"] for claim in ran))

    def test_text_run_prints_the_table(self):
        proc = self.invoke(tmp="run-text")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Erkennungsrate", proc.stdout)
        self.assertIn("Falschbestaetigungsrate", proc.stdout)
        self.assertIn("OK", proc.stdout)

    def test_halt_limit_reaches_the_check(self):
        document = evalset.load_set(SET_PATH)
        document["cases"] = [
            {
                "name": "x-genuine-halt",
                "group": "genuine",
                "note": "a halt claim that needs three steps",
                "base": document["fixture"]["base"],
                "targets": [],
                "report": (
                    f"**send_to payload:** `[COMMIT: {document['fixture']['base']}] "
                    "[HALT: 1RB1RZ_0LA0LA -> 3]`\n"
                ),
            },
            {
                "name": "x-false-missing-commit",
                "group": "false",
                "note": "keeps the run measurable",
                "base": document["fixture"]["base"],
                "targets": ["commit_exists"],
                "report": f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n",
            },
        ]
        path = self.write(document, "halt-limit.json")
        roomy = self.invoke(set_path=path, tmp="run-halt-roomy")
        self.assertEqual(roomy.returncode, 0, roomy.stdout + roomy.stderr)
        cramped = self.invoke(
            "--json", "--halt-limit", "2", set_path=path, tmp="run-halt-cramped"
        )
        self.assertEqual(cramped.returncode, 0, cramped.stdout + cramped.stderr)
        claims = {
            claim["kind"]: claim
            for case in json.loads(cramped.stdout)["cases"]
            for claim in case["claims"]
            if case["name"] == "x-genuine-halt"
        }
        self.assertEqual(claims["halt"]["verdict"], "UNVERIFIABLE")
        self.assertIn("executable limit of 2", claims["halt"]["reason"])

    def test_search_limit_reaches_the_check(self):
        document = evalset.load_set(SET_PATH)
        document["cases"] = [
            {
                "name": "x-genuine-searched",
                "group": "genuine",
                "note": "a bounded search claim the default limit covers",
                "base": document["fixture"]["base"],
                "targets": [],
                "report": (
                    f"**send_to payload:** `[COMMIT: {document['fixture']['base']}] "
                    "[SEARCHED: 1RA1RA -> 1000]`\n"
                ),
            },
            {
                "name": "x-false-missing-commit",
                "group": "false",
                "note": "keeps the run measurable",
                "base": document["fixture"]["base"],
                "targets": ["commit_exists"],
                "report": f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n",
            },
        ]
        path = self.write(document, "search-limit.json")
        roomy = self.invoke(set_path=path, tmp="run-search-roomy")
        self.assertEqual(roomy.returncode, 0, roomy.stdout + roomy.stderr)
        cramped = self.invoke(
            "--json", "--search-limit", "2", set_path=path, tmp="run-search-cramped"
        )
        self.assertEqual(cramped.returncode, 0, cramped.stdout + cramped.stderr)
        claims = {
            claim["kind"]: claim
            for case in json.loads(cramped.stdout)["cases"]
            for claim in case["claims"]
            if case["name"] == "x-genuine-searched"
        }
        self.assertEqual(claims["searched"]["verdict"], "UNVERIFIABLE")
        self.assertIn("executable limit of 2", claims["searched"]["reason"])

    def test_cycle_limit_reaches_the_check(self):
        document = evalset.load_set(SET_PATH)
        document["cases"] = [
            {
                "name": "x-genuine-cycle",
                "group": "genuine",
                "note": "a translated-cycle certificate the default limit covers",
                "base": document["fixture"]["base"],
                "targets": [],
                "report": (
                    f"**send_to payload:** `[COMMIT: {document['fixture']['base']}] "
                    "[CYCLE: 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC -> 6,16,2]`\n"
                ),
            },
            {
                "name": "x-false-missing-commit",
                "group": "false",
                "note": "keeps the run measurable",
                "base": document["fixture"]["base"],
                "targets": ["commit_exists"],
                "report": f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n",
            },
        ]
        path = self.write(document, "cycle-limit.json")
        roomy = self.invoke(set_path=path, tmp="run-cycle-roomy")
        self.assertEqual(roomy.returncode, 0, roomy.stdout + roomy.stderr)
        cramped = self.invoke(
            "--json", "--cycle-limit", "5", set_path=path, tmp="run-cycle-cramped"
        )
        self.assertEqual(cramped.returncode, 0, cramped.stdout + cramped.stderr)
        claims = {
            claim["kind"]: claim
            for case in json.loads(cramped.stdout)["cases"]
            for claim in case["claims"]
            if case["name"] == "x-genuine-cycle"
        }
        self.assertEqual(claims["cycle"]["verdict"], "UNVERIFIABLE")
        self.assertIn("executable limit of 5", claims["cycle"]["reason"])

    def test_missing_set_is_an_error(self):
        proc = self.invoke(set_path=os.path.join(self._tmp.name, "nope.json"), tmp=None)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("set", proc.stderr.lower())

    def test_strict_flags_unverifiable_claims_in_the_set(self):
        proc = self.invoke("--strict", "--json", tmp="run-strict")
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["strict"])
        self.assertGreater(payload["strict_violations"], 0)
        self.assertEqual(
            payload["strict_violations"], payload["rates"]["unverifiable_claims"]
        )
        self.assertTrue(payload["thresholds_met"])
        self.assertFalse(payload["ok"])

    def test_strict_passes_on_fully_verifiable_set(self):
        document = evalset.load_set(SET_PATH)
        document["cases"] = [
            {
                "name": "x-genuine-verifiable",
                "group": "genuine",
                "note": "its only claim is a confirmable commit",
                "base": document["fixture"]["base"],
                "targets": [],
                "report": f"**send_to payload:** `[COMMIT: {document['fixture']['base']}]`\n",
            },
            {
                "name": "x-false-missing-commit",
                "group": "false",
                "note": "the nonexistent commit is refuted, so the case is detected",
                "base": document["fixture"]["base"],
                "targets": ["commit_exists"],
                "report": f"**send_to payload:** `[COMMIT: {'0' * 40}]`\n",
            },
        ]
        path = self.write(document, "verifiable.json")
        default = self.invoke(set_path=path, tmp="run-verifiable")
        self.assertEqual(default.returncode, 0, default.stdout + default.stderr)
        strict = self.invoke("--strict", set_path=path, tmp="run-verifiable-strict")
        self.assertEqual(strict.returncode, 0, strict.stdout + strict.stderr)

    def test_strict_keeps_threshold_misses_at_exit_one(self):
        document = evalset.load_set(SET_PATH)
        document["cases"] = [
            {
                "name": "x-false-will-confirm",
                "group": "false",
                "note": "a target claim the fixture confirms on purpose",
                "base": document["fixture"]["base"],
                "targets": ["commit_exists"],
                "report": f"**send_to payload:** `[COMMIT: {document['fixture']['base']}]`\n",
            },
            {
                "name": "x-genuine-with-unverifiable",
                "group": "genuine",
                "note": "keeps an unverifiable claim next to a confirmable one",
                "base": document["fixture"]["base"],
                "targets": [],
                "report": (
                    f"**send_to payload:** `[COMMIT: {document['fixture']['base']}] "
                    "[MERGE: no]`\n"
                ),
            },
        ]
        path = self.write(document, "failing-strict.json")
        proc = self.invoke("--strict", set_path=path, tmp="run-failing-strict")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_errors_are_json_on_stdout_when_requested(self):
        proc = self.invoke(
            "--json", set_path=os.path.join(self._tmp.name, "nope.json"), tmp=None
        )
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)

    def test_symlinked_fixture_dir_is_refused(self):
        target = os.path.join(self._tmp.name, "symlink-target")
        os.makedirs(target, exist_ok=True)
        root = os.path.join(self._tmp.name, "symlinked")
        os.makedirs(root, exist_ok=True)
        os.symlink(target, os.path.join(root, "fixture"))
        proc = self.invoke(set_path=SET_PATH, tmp="symlinked")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("symlink", proc.stderr)
        self.assertEqual(os.listdir(target), [])

    def test_symlinked_tmp_root_is_refused(self):
        target = os.path.join(self._tmp.name, "root-target")
        os.makedirs(target, exist_ok=True)
        link = os.path.join(self._tmp.name, "root-link")
        os.symlink(target, link)
        proc = self.invoke(set_path=SET_PATH, tmp="root-link")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("symlink", proc.stderr)
        self.assertEqual(os.listdir(target), [])

    def test_symlinked_check_dir_is_refused(self):
        target = os.path.join(self._tmp.name, "check-target")
        os.makedirs(target, exist_ok=True)
        root = os.path.join(self._tmp.name, "symlinked-check")
        os.makedirs(root, exist_ok=True)
        os.symlink(target, os.path.join(root, "check"))
        proc = self.invoke(set_path=SET_PATH, tmp="symlinked-check")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("symlink", proc.stderr)
        self.assertEqual(os.listdir(target), [])

    def test_default_tmp_outside_the_working_directory_is_refused(self):
        workdir = os.path.join(self._tmp.name, "cwd-with-symlink")
        target = os.path.join(self._tmp.name, "escape-target")
        os.makedirs(workdir, exist_ok=True)
        os.makedirs(target, exist_ok=True)
        os.symlink(target, os.path.join(workdir, ".yesmem"))
        proc = self.invoke(set_path=SET_PATH, tmp=None, cwd=workdir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("outside", proc.stderr)
        self.assertEqual(os.listdir(target), [])

    def test_foreign_fixture_dir_is_not_deleted(self):
        root = os.path.join(self._tmp.name, "foreign")
        os.makedirs(os.path.join(root, "fixture"), exist_ok=True)
        precious = os.path.join(root, "fixture", "precious.txt")
        with open(precious, "w", encoding="utf-8") as handle:
            handle.write("user data\n")
        proc = self.invoke(set_path=SET_PATH, tmp="foreign")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("refusing to delete", proc.stderr)
        with open(precious, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "user data\n")

    def test_second_run_reuses_its_own_fixture(self):
        first = self.invoke(set_path=SET_PATH, tmp="rerun")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.invoke(set_path=SET_PATH, tmp="rerun")
        self.assertEqual(second.returncode, 0, second.stderr)

    def test_unusable_default_tmp_exits_two(self):
        workdir = os.path.join(self._tmp.name, "cwd-file-yesmem")
        os.makedirs(workdir, exist_ok=True)
        with open(os.path.join(workdir, ".yesmem"), "w", encoding="utf-8") as handle:
            handle.write("not a directory\n")
        proc = self.invoke(set_path=SET_PATH, tmp=None, cwd=workdir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("cannot build", proc.stderr)

    def test_failed_evaluation_exits_one(self):
        document = evalset.load_set(SET_PATH)
        document["cases"] = [
            {
                "name": "x-false-will-confirm",
                "group": "false",
                "note": "a target claim the fixture confirms on purpose",
                "base": document["fixture"]["base"],
                "targets": ["commit_exists"],
                "report": f"**send_to payload:** `[COMMIT: {document['fixture']['base']}]`\n",
            }
        ]
        path = self.write(document, "failing.json")
        proc = self.invoke(set_path=path, tmp="run-failing")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

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

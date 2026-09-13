#!/usr/bin/env python3
"""Tests der Trainings-Skripte.

Hier laeuft nur, was auf der CPU-Maschine laufen kann: die dry-run-Pfade, der
Reward gegen den echten Runner, der Leck-Guard der Denk-Trace-Destillation und
der per ENV umstellbare Harness-Endpunkt. Die Trainingspfade selbst (Torch,
Quantisierung, Trainer) sind auf dieser Maschine nicht ausfuehrbar -- sie
werden kompiliert, nicht gestartet.
"""

from __future__ import annotations

import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "training"
TOOLING = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"

SCRIPTS = (
    "build_corpus.py",
    "corpus_io.py",
    "train_sft.py",
    "train_dpo.py",
    "rlvr.py",
    "distill_thinking.py",
)

GOOD_ANSWER = (
    "h1: (((1 + 2) = 3))\n"
    "v h1: auto\n"
    "h1+\n"
    "CLAIM c1: ((1 + 2) = 3)\n"
    "WITNESS c1: ref h1\n"
    "[HALT] c1\n"
)
BAD_ANSWER = "CLAIM c1: ((1 + 2) = 4)\nWITNESS c1: auto\n[HALT] c1\n"


def write_fixture_corpus(directory: Path, *, certificate_given: bool = False) -> Path:
    sft = {
        "id": "sft:fx:B3-0008:D",
        "task_id": "B3-0008",
        "arm": "D",
        "split": "train",
        "messages": [
            {"role": "system", "content": "Legende"},
            {"role": "user", "content": "Aufgabe"},
            {"role": "assistant", "content": GOOD_ANSWER},
        ],
    }
    rlvr = {
        "id": "rlvr:fx:B3-0008:D",
        "task_id": "B3-0008",
        "arm": "D",
        "split": "train",
        "messages": sft["messages"][:2],
        "verifier": {
            "command": ["python3", "-m", "bemyself.msheet", "run", "{sheet}", "--json"],
            "expect": {"all_claims_confirmed": True, "min_claims": 1},
        },
        "gold": {"certificate_given": certificate_given, "certificate": [34, 37, -1]},
        "reference": {"claims": [{"id": "c1", "verdict": "CONFIRMED"}], "fully_confirmed": True},
    }
    dpo = {
        "id": "dpo:B3-0008:D",
        "task_id": "B3-0008",
        "arm": "D",
        "split": "train",
        "messages": sft["messages"][:2],
        "chosen": GOOD_ANSWER,
        "rejected": BAD_ANSWER,
        "meta": {"notes": []},
    }
    directory.mkdir(parents=True, exist_ok=True)
    for name, records in (("sft.jsonl", [sft]), ("rlvr.jsonl", [rlvr]), ("dpo.jsonl", [dpo])):
        (directory / name).write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
    return directory


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TRAINING / name), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(f"training_{name}", TRAINING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ScriptsTest(unittest.TestCase):
    def test_all_scripts_compile(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                py_compile.compile(str(TRAINING / name), doraise=True)

    def test_sft_dry_run_on_the_real_corpus(self):
        result = run_script("train_sft.py", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["mode"], "dry-run")
        self.assertGreater(summary["records"], 100)
        self.assertEqual(summary["by_split"]["train"], summary["records"] - summary["by_split"]["val"])

    def test_sft_dry_run_rejects_a_broken_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus")
            broken = json.loads((directory / "sft.jsonl").read_text())
            broken["messages"] = broken["messages"][:2]
            (directory / "sft.jsonl").write_text(json.dumps(broken) + "\n", encoding="utf-8")
            result = run_script("train_sft.py", "--dry-run", "--corpus", str(directory / "sft.jsonl"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Rollen", result.stderr + result.stdout)

    def test_sft_dry_run_rejects_bad_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus")
            broken = json.loads((directory / "sft.jsonl").read_text())
            broken["split"] = "dev"
            (directory / "sft.jsonl").write_text(json.dumps(broken) + "\n", encoding="utf-8")
            result = run_script("train_sft.py", "--dry-run", "--corpus", str(directory / "sft.jsonl"))
            self.assertNotEqual(result.returncode, 0)

    def test_dpo_dry_run_on_the_real_corpus(self):
        result = run_script("train_dpo.py", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["mode"], "dry-run")
        self.assertGreaterEqual(summary["train_pairs"], 10)

    def test_dpo_dry_run_rejects_chosen_equal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus")
            record = json.loads((directory / "dpo.jsonl").read_text())
            record["rejected"] = record["chosen"]
            (directory / "dpo.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            result = run_script("train_dpo.py", "--dry-run", "--corpus", str(directory / "dpo.jsonl"))
            self.assertNotEqual(result.returncode, 0)

    def test_dpo_detects_adapter_base_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = Path(tmp) / "adapter"
            adapter.mkdir()
            (adapter / "adapter_config.json").write_text(
                json.dumps({"base_model_name_or_path": "Qwen/Qwen3-8B"}), encoding="utf-8"
            )
            dpo = load_module("train_dpo")
            self.assertTrue(dpo.is_adapter(adapter))
            self.assertFalse(dpo.is_adapter(Path(tmp)))

    def test_rlvr_reward_scores_confirmed_and_refuted(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus")
            rlvr = load_module("rlvr")
            record = json.loads((directory / "rlvr.jsonl").read_text())
            good = rlvr.score(GOOD_ANSWER, record)
            self.assertEqual(good["reward"], 1.0, good)
            self.assertEqual(good["reason"], "all_confirmed")
            bad = rlvr.score(BAD_ANSWER, record)
            self.assertEqual(bad["reward"], 0.0, bad)
            self.assertEqual(bad["reason"], "refuted")

    def test_rlvr_cli_scores_an_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus")
            result = run_script(
                "rlvr.py",
                "--corpus", str(directory / "rlvr.jsonl"),
                "--record-id", "rlvr:fx:B3-0008:D",
                "--answer", GOOD_ANSWER,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["reward"], 1.0)

    def test_distill_leak_guard_finds_gold_values(self):
        distill = load_module("distill_thinking")
        record = {"gold": {"certificate_given": False, "certificate": [34, 37, -1]}}
        values = distill.gold_values(record)
        self.assertEqual(values, [34, 37, -1])
        self.assertEqual(distill.find_gold_leaks("t1=34, t2=37, d=-1", values)[:2], [-1, 34])
        self.assertEqual(distill.find_gold_leaks("Suche laeuft, noch kein Zyklus gefunden", values), [])
        given = {"gold": {"certificate_given": True, "certificate": [1, 3, 2]}}
        self.assertEqual(distill.gold_values(given), [])

    def test_distill_dry_run_builds_request_without_sending(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus", certificate_given=False)
            result = run_script(
                "distill_thinking.py",
                "--dry-run", "--corpus", str(directory), "--id", "sft:fx:B3-0008:D",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            request = json.loads(result.stdout)
            self.assertEqual([message["role"] for message in request["messages"]], ["system", "user"])
            self.assertIn("Keine Behauptungszone", request["messages"][1]["content"])
            self.assertIn("KEINE Zyklus-Zahlen", request["messages"][1]["content"])

    def test_distill_dry_run_with_given_certificate_has_no_value_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = write_fixture_corpus(Path(tmp) / "corpus", certificate_given=True)
            result = run_script(
                "distill_thinking.py",
                "--dry-run", "--corpus", str(directory), "--id", "sft:fx:B3-0008:D",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            request = json.loads(result.stdout)
            self.assertNotIn("KEINE Zyklus-Zahlen", request["messages"][1]["content"])

    def test_harness_endpoint_is_env_configurable(self):
        spec = importlib.util.spec_from_file_location("harness_env_test", TOOLING / "harness.py")
        harness = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = harness
        spec.loader.exec_module(harness)
        previous = os.environ.pop("BEMYSELF_PROXY_URL", None)
        try:
            self.assertEqual(harness.proxy_url(), "http://localhost:9099/v1/chat/completions")
            os.environ["BEMYSELF_PROXY_URL"] = "http://gpu-box:8000/v1/chat/completions"
            self.assertEqual(harness.proxy_url(), "http://gpu-box:8000/v1/chat/completions")
        finally:
            if previous is None:
                os.environ.pop("BEMYSELF_PROXY_URL", None)
            else:
                os.environ["BEMYSELF_PROXY_URL"] = previous


if __name__ == "__main__":
    unittest.main()

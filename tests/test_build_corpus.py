#!/usr/bin/env python3
"""Tests des Trainingskorpus-Bauers (training/build_corpus.py).

Der Bauer liest ausschliesslich abgeschlossene Laufordner (v11 flach,
v12/v13 mit Rundenbaeumen) und leitet die Labels maschinell ab: aus
``summary.json`` (v12/v13) bzw. per Re-Evaluierung mit dem eingefrorenen Set
und dem Repo-Evaluator (v11, das keine summary.json kennt).

Gepruefte Zusagen:

1. Layout-Erkennung beider Generationen (flach und Rundenbaum).
2. SFT: nur endgeloeste Laeufe der Arme B/C/D, dedupliziert je (Task, Arm),
   Assistant = Blatt verbatim.
3. DPO: (prompt, chosen, rejected) aus derselben Zelle, Cross-Arm-Fallback
   nur mit Notiz.
4. RLVR: Verifier-Kommando auf dem echten Runner, Erwartungswerte vom
   eingefrorenen (verifizierten) Blatt abgeleitet.
5. Think: nur die Denkzone des verifizierten Blatts.
6. Splits: Task-Familien (Tier + Nummern-Suffix) bleiben zusammen,
   deterministisch aus dem Seed.
7. Manifest: sha256 je Datei, Zaehlungen, Quellen.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "training"
TRAINING_DIR = TRAINING

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_corpus", TRAINING / "build_corpus.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = module
    spec.loader.exec_module(module)
    return module


SYSTEM = (
    "# system\n\n"
    "Du arbeitest in einer zweizonigen formalen Notation (V1).\n"
    "Denkzone: Zeilen mit dem Praefix S<n>: oder h<n>:\n"
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


def write_prompt(path: Path, user: str, prior: str | None = None, feedback: str | None = None):
    text = SYSTEM + "\n# user\n\n" + user + "\n"
    if prior is not None:
        text += "\n# assistant\n\n" + prior + "\n"
    if feedback is not None:
        text += "\n# user\n\n" + feedback + "\n"
    path.write_text(text, encoding="utf-8")


def write_parsed(path: Path, answer: str, tokens: int = 100):
    path.write_text(
        json.dumps(
            {
                "answer": answer,
                "usage": {"completion_tokens": tokens, "reasoning_tokens": tokens - 10},
                "finish_reason": "stop",
            }
        ),
        encoding="utf-8",
    )


def make_round_dir(base: Path, index: int, prior: str | None = None):
    directory = base / f"round{index}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_branch_run(
    root: Path,
    tier_dir: str,
    task: str,
    arm: str,
    rep: int,
    rounds,
    set_version: str = "0.2",
):
    """rounds: list of (answer, solved, trigger). Layout v12/v13."""
    arm_dir = root / tier_dir / task / f"{arm}-rep{rep}"
    arm_dir.mkdir(parents=True, exist_ok=True)
    prior = None
    rows = []
    for index, (answer, solved, trigger) in enumerate(rounds):
        directory = make_round_dir(arm_dir, index, prior)
        if index == 0:
            write_prompt(directory / "prompt.md", "### AUFGABE\nRechne 1 + 2.")
        else:
            write_prompt(
                directory / "prompt.md",
                "### AUFGABE\nRechne 1 + 2.",
                prior=prior,
                feedback="Blatt nicht bestaetigt.",
            )
        write_parsed(directory / "parsed.json", answer)
        (directory / "raw.json").write_text("{}", encoding="utf-8")
        rows.append(
            {
                "round": index,
                "solved": solved,
                "trigger": trigger,
                "error": None,
                "duration_s": 1.0,
                "completion_tokens": 100 + index,
                "reasoning_tokens": 90,
                "format_errors": 0,
            }
        )
        prior = answer
    summary = {
        "task_id": task,
        "arm": arm,
        "tier": task[0],
        "rep": rep,
        "max_repairs": 2,
        "rounds": rows,
        "final_solved": bool(rows[-1]["solved"]),
        "rounds_to_ok": next((r["round"] for r in rows if r["solved"]), None),
        "repairs_used": 0,
        "triggered_rounds": [r["round"] for r in rows if r["trigger"]],
        "transport_retries": 0,
        "total_completion_tokens": sum(r["completion_tokens"] for r in rows),
        "total_reasoning_tokens": sum(r["reasoning_tokens"] for r in rows),
        "total_duration_s": 1.0,
    }
    (arm_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return arm_dir


def write_flat_run(root: Path, stamp: str, task: str, arm: str, rep: int, answer: str):
    """Layout v11: <stamp>/<task>/<arm>-rep<rep>/ ohne summary.json."""
    arm_dir = root / stamp / task / f"{arm}-rep{rep}"
    arm_dir.mkdir(parents=True, exist_ok=True)
    write_prompt(arm_dir / "prompt.md", "### AUFGABE\nRechne 1 + 2.")
    write_parsed(arm_dir / "parsed.json", answer)
    (arm_dir / "raw.json").write_text("{}", encoding="utf-8")
    return arm_dir


def module():
    from tests import test_build_corpus

    return test_build_corpus.builder


class BuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = _load_builder()

    def test_scan_branch_layout_reads_rounds_and_machine_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            write_branch_run(
                root,
                "tier-a-x",
                "A-0001",
                "B",
                1,
                [(BAD_ANSWER, False, "end_state_not_confirmed"), (GOOD_ANSWER, True, None)],
            )
            runs = self.builder.scan_runs([root])
            self.assertEqual(len(runs), 1)
            run = runs[0]
            self.assertEqual((run.version, run.tier, run.task_id, run.arm, run.rep), ("v12", "A", "A-0001", "B", 1))
            self.assertEqual([r.solved for r in run.rounds], [False, True])
            self.assertTrue(run.solved)
            self.assertEqual(run.label_source, "summary.json")

    def test_scan_flat_layout_has_one_unlabeled_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v11-x"
            write_flat_run(root, "20260912-100000", "A-0001", "C", 1, GOOD_ANSWER)
            runs = self.builder.scan_runs([root])
            self.assertEqual(len(runs), 1)
            run = runs[0]
            self.assertEqual(run.version, "v11")
            self.assertEqual(len(run.rounds), 1)
            self.assertIsNone(run.solved)
            self.assertEqual(run.label_source, "unlabeled")

    def test_verify_runs_uses_injected_evaluator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v11-x"
            write_flat_run(root, "t1", "A-0001", "C", 1, GOOD_ANSWER)
            write_flat_run(root, "t1", "A-0002", "C", 1, BAD_ANSWER)
            runs = self.builder.scan_runs([root])

            def fake_evaluator(arm, task, answer):
                return {"solved": "1 + 2) = 3" in answer}

            self.builder.verify_runs(runs, evaluator=fake_evaluator)
            by_task = {run.task_id: run for run in runs}
            self.assertTrue(by_task["A-0001"].solved)
            self.assertFalse(by_task["A-0002"].solved)
            self.assertEqual(by_task["A-0001"].label_source, "reevaluation")

    def test_sft_keeps_only_verified_bcd_and_dedups_per_task_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            write_branch_run(root, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            write_branch_run(root, "tier-a-x", "A-0001", "B", 2, [(GOOD_ANSWER, True, None)])
            write_branch_run(root, "tier-a-x", "A-0001", "K", 1, [(GOOD_ANSWER, True, None)])
            write_branch_run(root, "tier-a-x", "A-0002", "C", 1, [(BAD_ANSWER, False, "end_state_not_confirmed")])
            runs = self.builder.scan_runs([root])
            records = self.builder.build_sft(runs)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["arm"], "B")
            self.assertEqual([m["role"] for m in record["messages"]], ["system", "user", "assistant"])
            self.assertEqual(record["messages"][2]["content"], GOOD_ANSWER)
            self.assertTrue(record["messages"][0]["content"].startswith("Du arbeitest"))

    def test_sft_keeps_distinct_set_versions_as_distinct_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            write_branch_run(root, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            root11 = Path(tmp) / "runs-v11-x"
            write_flat_run(root11, "t1", "A-0001", "B", 1, GOOD_ANSWER)
            root11_runs = self.builder.scan_runs([root11])
            self.builder.verify_runs(
                root11_runs, evaluator=lambda arm, task, answer: {"solved": True}
            )
            records = self.builder.build_sft(self.builder.scan_runs([root]) + root11_runs)
            versions = sorted(record["meta"]["version"] for record in records)
            self.assertEqual(versions, ["v11", "v12"])

    def test_dpo_pairs_rejected_round0_with_solved_later_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v13-x"
            write_branch_run(
                root,
                "tier-a-x",
                "A3-0001",
                "B",
                1,
                [(BAD_ANSWER, False, "end_state_not_confirmed"), (GOOD_ANSWER, True, None)],
            )
            runs = self.builder.scan_runs([root])
            records = self.builder.build_dpo(runs)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["chosen"], GOOD_ANSWER)
            self.assertEqual(record["rejected"], BAD_ANSWER)
            self.assertEqual(record["meta"]["chosen_round"], 1)
            self.assertEqual(record["meta"]["rejected_round"], 0)
            self.assertEqual(record["meta"]["notes"], [])
            self.assertNotIn("# assistant", record["messages"][1]["content"])

    def test_dpo_cross_arm_fallback_is_noted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v13-x"
            write_branch_run(root, "tier-a-x", "A3-0001", "C", 1, [(GOOD_ANSWER, True, None)])
            write_branch_run(
                root, "tier-a-x", "A3-0001", "B", 1, [(BAD_ANSWER, False, "end_state_not_confirmed")]
            )
            runs = self.builder.scan_runs([root])
            records = self.builder.build_dpo(runs)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["meta"]["chosen_arm"], "C")
            self.assertEqual(record["meta"]["rejected_arm"], "B")
            self.assertIn("rejected_from_arm=B", record["meta"]["notes"])

    def test_dpo_uses_run_level_labels_from_reevaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root11 = Path(tmp) / "runs-v11-x"
            write_flat_run(root11, "t1", "A-0001", "B", 1, BAD_ANSWER)
            flat_runs = self.builder.scan_runs([root11])
            self.builder.verify_runs(
                flat_runs, evaluator=lambda arm, task, answer: {"solved": False}
            )
            root12 = Path(tmp) / "runs-v12-x"
            write_branch_run(root12, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            records = self.builder.build_dpo(self.builder.scan_runs([root12]) + flat_runs)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["rejected"], BAD_ANSWER)
            self.assertEqual(records[0]["meta"]["rejected_round"], 0)
            self.assertIn("rejected_from_version=v11", records[0]["meta"]["notes"])

    def test_task_family_groups_set_versions(self):
        self.assertEqual(
            self.builder.task_family("A-0007"), self.builder.task_family("A3-0007")
        )
        self.assertNotEqual(
            self.builder.task_family("A-0007"), self.builder.task_family("B-0007")
        )

    def test_splits_are_deterministic_and_family_level(self):
        families = [f"A:{i:04d}" for i in range(1, 17)]
        first = self.builder.assign_splits(families, seed=20260912)
        second = self.builder.assign_splits(list(reversed(families)), seed=20260912)
        self.assertEqual(first, second)
        self.assertEqual(sorted(first.values()).count("test"), len([v for v in first.values() if v == "test"]))
        self.assertGreaterEqual(sum(1 for v in first.values() if v == "val"), 1)
        self.assertGreaterEqual(sum(1 for v in first.values() if v == "test"), 1)

    def test_think_keeps_only_the_thinking_zone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            write_branch_run(root, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            runs = self.builder.scan_runs([root])
            records = self.builder.build_think(runs)
            self.assertEqual(len(records), 1)
            zone = records[0]["thinking_zone"]
            self.assertEqual(zone, ["h1: (((1 + 2) = 3))", "v h1: auto", "h1+"])
            self.assertNotIn("CLAIM c1: ((1 + 2) = 3)", zone)

    def test_rlvr_uses_the_real_runner_and_expected_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            write_branch_run(root, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            runs = self.builder.scan_runs([root])
            records = self.builder.build_rlvr(runs)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["verifier"]["command"][:3], ["python3", "-m", "proofboy.msheet"])
            self.assertEqual(
                record["verifier"]["expect"], {"all_claims_confirmed": True, "min_claims": 1}
            )
            self.assertEqual(
                record["reference"]["claims"], [{"id": "c1", "verdict": "CONFIRMED"}]
            )
            self.assertTrue(record["reference"]["fully_confirmed"])

    def test_sft_drops_unverifiable_sheets_but_keeps_them_as_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            unbound = (
                "h1: (((1 + 2) = 3))\n"
                "v h1: sim(0..5)\n"
                "h1+\n"
                "CLAIM c1: ((1 + 2) = 3)\n"
                "WITNESS c1: ref h1\n"
                "[HALT] c1\n"
            )
            write_branch_run(root, "tier-a-x", "A-0001", "C", 1, [(unbound, True, None)])
            runs = self.builder.scan_runs([root])
            stats: dict = {}
            self.assertEqual(self.builder.build_sft(runs, stats=stats), [])
            self.assertEqual(stats["sft_dropped_unverified"], 1)
            self.assertEqual(len(self.builder.build_think(runs)), 1)
            self.assertEqual(len(self.builder.build_rlvr(runs)), 1)
            self.assertFalse(self.builder.build_rlvr(runs)[0]["reference"]["fully_confirmed"])

    def test_write_corpus_writes_files_splits_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            for index in range(1, 5):
                write_branch_run(
                    root, "tier-a-x", f"A-{index:04d}", "B", 1, [(GOOD_ANSWER, True, None)]
                )
            write_branch_run(
                root,
                "tier-a-x",
                "A-0001",
                "C",
                1,
                [(BAD_ANSWER, False, "end_state_not_confirmed"), (GOOD_ANSWER, True, None)],
            )
            runs = self.builder.scan_runs([root])
            out = Path(tmp) / "corpus"
            manifest = self.builder.write_corpus(runs, out, seed=7)
            for name in ("sft.jsonl", "dpo.jsonl", "rlvr.jsonl", "think.jsonl", "splits.json"):
                self.assertTrue((out / name).exists(), name)
            sft_lines = [json.loads(line) for line in (out / "sft.jsonl").read_text().splitlines()]
            self.assertEqual(len(sft_lines), 5)
            self.assertTrue(all(record["split"] in ("train", "val", "test") for record in sft_lines))
            digest = hashlib.sha256((out / "sft.jsonl").read_bytes()).hexdigest()
            self.assertEqual(manifest["files"]["sft.jsonl"]["sha256"], digest)
            self.assertEqual(manifest["files"]["sft.jsonl"]["records"], 5)
            self.assertEqual(manifest["seed"], 7)

    def test_clean_sheet_refuses_py_witness_without_bwrap(self):
        """Sandbox-Pflicht: ohne bwrap faellt das Blatt aus SFT/DPO (fail closed)."""
        from proofboy.msheet import witnesses

        py_sheet = (
            "h1: (((1 + 2) = 3))\n"
            "v h1: py: (1 + 2) == 3\n"
            "h1+\n"
            "CLAIM c1: ((1 + 2) = 3)\n"
            "WITNESS c1: ref h1\n"
            "[HALT] c1\n"
        )
        self.assertTrue(self.builder._clean_sheet(py_sheet))
        original = witnesses.find_bwrap
        witnesses.find_bwrap = lambda: None
        self.builder.sheet_verdicts.cache_clear()  # gehaltene Verdikte nicht weiterverwenden
        try:
            self.assertFalse(self.builder._clean_sheet(py_sheet))
            verdicts = self.builder.sheet_verdicts(py_sheet, "auto")
            self.assertTrue(verdicts["unsandboxed"])
            self.assertFalse(self.builder._clean_sheet(py_sheet, "auto"))
        finally:
            witnesses.find_bwrap = original
            self.builder.sheet_verdicts.cache_clear()

    def test_no_verify_cli_runs_without_dependency_on_harness_import(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            write_branch_run(root, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            out = Path(tmp) / "corpus"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TRAINING_DIR / "build_corpus.py"),
                    "--runs", str(root),
                    "--out", str(out),
                    "--no-verify",
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("ModuleNotFoundError", result.stderr)
            self.assertTrue((out / "manifest.json").exists())
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sandbox"], "require")

    def test_scan_runs_reports_missing_summary_as_unlabeled_not_solved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs-v12-x"
            arm_dir = write_branch_run(root, "tier-a-x", "A-0001", "B", 1, [(GOOD_ANSWER, True, None)])
            (arm_dir / "summary.json").unlink()
            runs = self.builder.scan_runs([root])
            self.assertEqual(len(runs), 1)
            self.assertIsNone(runs[0].solved)
            self.assertEqual(self.builder.build_sft(runs), [])


if __name__ == "__main__":
    unittest.main()

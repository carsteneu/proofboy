#!/usr/bin/env python3
"""RLVR-Skizze: Reward = Maschinenverdikt des Runners (kein Modell-Urteil).

Der Korpus ``rlvr.jsonl`` traegt je Zelle Task + Verifier-Kommando
(``python3 -m bemyself.msheet run <sheet> --json``) + Erwartung. Dieses Skript
ist der Andockpunkt fuer RLVR/GRPO: ``reward(completions, record_id=…, …)``
passt auf TRLs Reward-Aufruf (``reward_funcs=[functools.partial(reward,
records_by_id=…)]``; TRL uebergibt ``prompts``, ``completions`` und die
Dataset-Spalten als Listen -- die Spalte muss ``record_id`` heissen).

Belohnungsvertrag:
* eine widerlegte Behauptung (``REFUTED``) -> 0.0 (fail closed),
* Zellen mit Behauptungszone: ``confirmed / target`` mit ``target =
  max(min_claims, Anzahl Referenz-Behauptungen)``, gedeckelt auf 1.0,
* Zellen ohne Behauptungszone (v0.1-/v0.2-Format ``S<n>: cp <t>: (…)``):
  maschineller Checkpoint-Abgleich gegen die Aufgaben-Zielpunkte
  (``matched / total``) -- dasselbe Verfahren, mit dem der Original-Harness
  diese Laeufe bewertet hat,
* kein Referenzmaterial -> 0.0 mit ``reason = "no_reference"`` (nicht still
  "gelöst"),
* ``sandboxed``/``unsandboxed`` stehen im Ergebnis; ``py:``-Zeugen laufen mit
  ``--sandbox require``, damit ein fehlendes bwrap nicht still unsandboxed
  ausfuehrt (dann UNVERIFIABLE -> kein Reward).

Selbsttest (schnell, ohne GPU):

    python3 training/rlvr.py --corpus training/corpus/rlvr.jsonl \
        --record-id rlvr:v13:B3-0001:C --answer-file /path/to/blob.msheet
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_io import read_jsonl  # noqa: E402

TOOLING_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"
DEFAULT_SANDBOX = "require"


@functools.lru_cache(maxsize=1)
def harness_module():
    spec = importlib.util.spec_from_file_location(
        "bemyself_rlvr_harness", TOOLING_DIR / "harness.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sandbox_state(flags) -> dict:
    """True/False nur bei py:-Zeugen; None = das Blatt hatte keine py:-Zeugen."""
    if any(flag is False for flag in flags):
        return {"unsandboxed": True, "sandboxed": False}
    if any(flag is True for flag in flags):
        return {"unsandboxed": False, "sandboxed": True}
    return {"unsandboxed": False, "sandboxed": None}


def run_verdicts(answer: str, sandbox: str = DEFAULT_SANDBOX) -> dict:
    """Verdikte des Blatts -- aus dem echten Runner (kein Modell-Urteil)."""
    from bemyself.msheet.runner import run_sheet
    from bemyself.msheet.sheet import parse_sheet

    sheet = parse_sheet(answer)
    result = run_sheet(sheet, sandbox=sandbox, timeout=20.0)
    flags = [item.sandboxed for item in (*result.v_results, *result.claim_results)]
    return {
        "claims": [
            {"id": claim.cid, "verdict": claim.verdict.value} for claim in result.claim_results
        ],
        "sandbox": sandbox,
        **_sandbox_state(flags),
    }


def checkpoint_score(answer: str, checkpoints_gold) -> tuple[int, int]:
    """(matched, total) der cp-Zeilen gegen die Zielpunkte der Aufgabe."""
    if not checkpoints_gold:
        return 0, 0
    matched, _first_deviation, _pairs = harness_module()._checkpoint_score(
        answer, checkpoints_gold
    )
    return matched, len(checkpoints_gold)


def score(answer: str, record: dict, *, sandbox: str = DEFAULT_SANDBOX) -> dict:
    reference = record.get("reference") or {}
    gold = record.get("gold") or {}
    try:
        verdicts = run_verdicts(answer, sandbox)
    except Exception as exc:  # noqa: BLE001 -- ein kaputtes Blatt ist 0 Reward, kein Absturz
        return {"reward": 0.0, "reason": "unreadable_sheet", "error": f"{type(exc).__name__}: {exc}"}
    claims = verdicts["claims"]
    expect = (record.get("verifier") or {}).get("expect", {}) or {}
    detail = {
        "claims": claims,
        "confirmed": sum(1 for claim in claims if claim["verdict"] == "CONFIRMED"),
        "min_claims": expect.get("min_claims", 0),
        "reference_claims": len(reference.get("claims") or []),
        "sandbox": verdicts["sandbox"],
        "sandboxed": verdicts["sandboxed"],
        "unsandboxed": verdicts["unsandboxed"],
    }
    if any(claim["verdict"] == "REFUTED" for claim in claims):
        return {"reward": 0.0, "reason": "refuted", **detail}
    if expect.get("checkpoints_all_matched"):
        try:
            matched, total = checkpoint_score(answer, gold.get("checkpoints_gold"))
        except Exception as exc:  # noqa: BLE001 -- defektes Gold ist 0 Reward, kein Absturz
            return {"reward": 0.0, "reason": "unreadable_reference",
                    "error": f"{type(exc).__name__}: {exc}", **detail}
        detail["checkpoints_matched"] = matched
        detail["checkpoints_total"] = total or expect.get("checkpoints_total", 0)
        reward = matched / detail["checkpoints_total"] if detail["checkpoints_total"] else 0.0
        reason = "checkpoints_matched" if reward == 1.0 else "partial_checkpoints"
        return {"reward": reward, "reason": reason, **detail}
    if expect.get("all_claims_confirmed") or detail["reference_claims"]:
        target = max(detail["min_claims"], detail["reference_claims"], 1)
        reward = min(1.0, detail["confirmed"] / target)
        reason = "all_confirmed" if reward == 1.0 else "partial_confirmed"
        return {"reward": reward, "reason": reason, **detail}
    return {"reward": 0.0, "reason": "no_reference", **detail}


def reward(completions, prompts=None, record_id=None, records_by_id=None, **kwargs) -> list[float]:
    """TRL-GRPOTrainer-Signatur; ``record_id`` ist die Dataset-Spalte.

    TRL ruft Reward-Funktionen mit ``prompts=…, completions=…`` plus allen
    Dataset-Spalten auf. ``record_ids`` wird als Alias akzeptiert (aeltere
    eigene Aufrufe).
    """
    ids = record_id if record_id is not None else kwargs.get("record_ids")
    if ids is None:
        ids = [None] * len(completions)
    elif isinstance(ids, str):
        ids = [ids] * len(completions)
    records_by_id = records_by_id or {}
    scores: list[float] = []
    for completion, key in zip(completions, ids):
        record = records_by_id.get(key) if key else None
        if record is None:
            scores.append(0.0)
            continue
        text = completion if isinstance(completion, str) else str(completion)
        try:
            scores.append(score(text, record)["reward"])
        except Exception:  # noqa: BLE001 -- ein defekter Datensatz ist 0 Reward, kein Trainer-Absturz
            scores.append(0.0)
    return scores


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RLVR-Reward gegen den Runner pruefen.")
    parser.add_argument("--corpus", default=str(Path(__file__).resolve().parent / "corpus" / "rlvr.jsonl"))
    parser.add_argument("--record-id", required=True, help="z.B. rlvr:v13:B3-0001:C")
    parser.add_argument("--answer", default=None, help="Blatt als Text")
    parser.add_argument("--answer-file", default=None, help="Blatt aus Datei")
    parser.add_argument("--sandbox", choices=("require", "auto", "off"), default=DEFAULT_SANDBOX)
    args = parser.parse_args(argv)
    records = {record["id"]: record for record in read_jsonl(args.corpus)}
    record = records.get(args.record_id)
    if record is None:
        raise SystemExit(f"unbekannte record-id {args.record_id!r}")
    if args.answer_file:
        answer = Path(args.answer_file).read_text(encoding="utf-8")
    elif args.answer is not None:
        answer = args.answer
    else:
        raise SystemExit("--answer oder --answer-file angeben")
    print(json.dumps(score(answer, record, sandbox=args.sandbox), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

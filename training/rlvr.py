#!/usr/bin/env python3
"""RLVR-Skizze: Reward = Maschinenverdikt des Runners (kein Modell-Urteil).

Der Korpus ``rlvr.jsonl`` traegt je Zelle Task + Verifier-Kommando
(``python3 -m bemyself.msheet run <sheet> --json``) + Erwartung
(``all_claims_confirmed``). Dieses Skript ist der Andockpunkt fuer RLVR/GRPO:
``reward(completions, record_ids=...)`` ist als ``reward_funcs``-Eintrag eines
``trl.GRPOTrainer`` gedacht und benutzt ausschliesslich den Runner -- das
Modell kann sich die Belohnung nicht selbst ausstellen.

Belohnungsvertrag:
* eine widerlegte Behauptung (``REFUTED``) -> 0.0 (fail closed),
* sonst ``confirmed / target`` mit ``target = max(min_claims,
  Anzahl Referenz-Behauptungen)``, gedeckelt auf 1.0,
* ``gold`` im Datensatz dient der Leiter-Auswertung (Checkpoints, Zertifikat,
  Zahl) -- nicht der Belohnung; die Belohnung laeuft ueber den Runner.

Selbsttest (schnell, ohne GPU):

    python3 training/rlvr.py --corpus training/corpus/rlvr.jsonl \
        --answer-file /path/to/blob.msheet --record-id rlvr:v13:B3-0001:C
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_io import read_jsonl  # noqa: E402


def run_verdicts(answer: str) -> list[tuple[str, str]]:
    """(claim_id, verdict) des Blatts -- aus dem echten Runner."""
    from bemyself.msheet.runner import run_sheet
    from bemyself.msheet.sheet import parse_sheet

    sheet = parse_sheet(answer)
    result = run_sheet(sheet, sandbox="auto", timeout=20.0)
    return [(claim.cid, claim.verdict.value) for claim in result.claim_results]


def score(answer: str, record: dict) -> dict:
    claims = run_verdicts(answer)
    verdicts = [verdict for _, verdict in claims]
    detail = {
        "claims": [{"id": claim_id, "verdict": verdict} for claim_id, verdict in claims],
        "confirmed": verdicts.count("CONFIRMED"),
        "min_claims": record.get("verifier", {}).get("expect", {}).get("min_claims", 1),
        "reference_claims": len(record.get("reference", {}).get("claims", [])),
    }
    if "REFUTED" in verdicts:
        return {"reward": 0.0, "reason": "refuted", **detail}
    target = max(detail["min_claims"], detail["reference_claims"], 1)
    reward = min(1.0, detail["confirmed"] / target)
    reason = "all_confirmed" if reward == 1.0 else "partial_confirmed"
    return {"reward": reward, "reason": reason, **detail}


def reward(completions, record_ids=None, records_by_id=None) -> list[float]:
    """TRL-GRPOTrainer-Signatur: reward_funcs=[functools.partial(reward, records_by_id=...)]."""
    records_by_id = records_by_id or {}
    scores: list[float] = []
    for completion, record_id in zip(completions, record_ids or [None] * len(completions)):
        record = records_by_id.get(record_id) if record_id else None
        if record is None:
            scores.append(0.0)
            continue
        text = completion if isinstance(completion, str) else str(completion)
        try:
            scores.append(score(text, record)["reward"])
        except Exception:  # noqa: BLE001 -- ein kaputtes Blatt ist 0 Reward, kein Absturz
            scores.append(0.0)
    return scores


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RLVR-Reward gegen den Runner pruefen.")
    parser.add_argument("--corpus", default=str(Path(__file__).resolve().parent / "corpus" / "rlvr.jsonl"))
    parser.add_argument("--record-id", required=True, help="z.B. rlvr:v13:B3-0001:C")
    parser.add_argument("--answer", default=None, help="Blatt als Text")
    parser.add_argument("--answer-file", default=None, help="Blatt aus Datei")
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
    print(json.dumps(score(answer, record), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

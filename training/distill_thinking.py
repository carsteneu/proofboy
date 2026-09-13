#!/usr/bin/env python3
"""Denk-Trace-Destillation (Geruest): Task + verifiziertes Blatt -> Notation-Denk-Trace.

Die Laeufe liefern Prosabegruendungen (``reasoning_content``) und Blaetter mit
Denkzone. Fuer eine Denk-Trace-Destillation wird der Fragekopf (System-Legende
+ Aufgabe) plus das verifizierte Blatt an ein Modell gegeben, das NUR die
Denkzone in der Notation schreibt.

LECK-POLICY (getestet): Bei den Zyklus-Aufgaben ohne vorgegebenes Zertifikat
(``certificate_given: false``) darf der Trace die eingefrorenen Gold-Werte
nicht nennen -- die Aufgabe verlangt die Suche; Gold-Ziffern im Trace waeren
ein Leck aus dem Set. ``find_gold_leaks`` prueft das mechanisch (ganze Zahlen
im Text gegen die Gold-Werte).

    python3 training/distill_thinking.py --dry-run --id sft:v13:B3-0008:D
    python3 training/distill_thinking.py --send  --id sft:v13:B3-0008:D --out trace.txt
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
DEFAULT_URL = os.environ.get("BEMYSELF_DISTILL_URL", "http://localhost:9099/v1/chat/completions")
DEFAULT_MODEL = os.environ.get("BEMYSELF_DISTILL_MODEL", "deepseek-flash")

INSTRUCTION = (
    "### AUFTRAG\n"
    "Schreibe die Denkzone zu dieser Aufgabe in der Notation (eine Zeile pro "
    "Schritt, Praefixe S<n>: oder h<n>:), so wie ein sorgfaeltiges Modell sie "
    "beim Loesen schreiben wuerde. Keine Behauptungszone, kein CLAIM/WITNESS, "
    "kein [HALT], kein Markdown. Nur die Denkzeilen.\n"
)

NO_CERT_VALUES = (
    "### REGEL\nNenne im Trace KEINE Zyklus-Zahlen (kein t1/t2/d und keine "
    "Schritt- oder Zykluslaengen) -- der Trace soll den Suchweg zeigen, nicht "
    "das Ergebnis behaupten.\n"
)

_INT_RE = re.compile(r"-?\d+")


def gold_values(record: dict) -> list[int]:
    """Die zu schuetzenden Gold-Werte des Datensatzes (leer, wenn keine)."""
    gold = record.get("gold") or {}
    if gold.get("certificate_given") is False and gold.get("certificate"):
        return [int(value) for value in gold["certificate"]]
    return []


def find_gold_leaks(text: str, values) -> list[int]:
    """Gold-Werte, die im Text als ganze Zahl vorkommen (Leck-Kandidaten)."""
    if not values:
        return []
    present = {int(match) for match in _INT_RE.findall(text)}
    return sorted(value for value in values if value in present)


def build_request(sft_record: dict, rlvr_record: dict | None, model: str = DEFAULT_MODEL) -> dict:
    messages = sft_record["messages"]
    user = f"### SYSTEM\n{messages[0]['content']}\n\n### AUFGABE\n{messages[1]['content']}\n\n"
    user += f"### VERIFIZIERTES BLATT (Zielform)\n{messages[2]['content']}\n\n"
    user += INSTRUCTION
    values = gold_values(rlvr_record or {})
    if values:
        user += NO_CERT_VALUES
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "Du schreibst kurze, exakte Denkzonen in einer formalen Notation."},
            {"role": "user", "content": user},
        ],
        "max_tokens": 2048,
    }


def load_pair(corpus_dir: Path | str, record_id: str) -> tuple[dict, dict | None]:
    def read(name):
        path = Path(corpus_dir) / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    if not record_id.startswith("sft:"):
        raise SystemExit("--id erwartet eine sft:-Kennung, z.B. sft:v13:B3-0008:D")
    tail = record_id[len("sft:"):]
    sft = next((record for record in read("sft.jsonl") if record["id"] == record_id), None)
    if sft is None:
        raise SystemExit(f"unbekannte id {record_id!r}")
    rlvr = next((record for record in read("rlvr.jsonl") if record["id"] == f"rlvr:{tail}"), None)
    return sft, rlvr


def fetch_trace(request: dict, *, url: str, api_key: str, timeout: float) -> str:
    body = json.dumps(request).encode("utf-8")
    http = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(http, timeout=timeout) as response:
        payload = json.load(response)
    message = payload["choices"][0]["message"]
    return message.get("content") or ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Denk-Trace-Destillation (Geruest).")
    parser.add_argument("--corpus", default=str(CORPUS_DIR))
    parser.add_argument("--id", required=True, help="sft:-Kennung, z.B. sft:v13:B3-0008:D")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--api-key", default=os.environ.get("BEMYSELF_DISTILL_KEY", ""))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", default=None, help="Trace in Datei schreiben")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="nur die Anfrage zeigen")
    group.add_argument("--send", action="store_true", help="Anfrage senden und Trace pruefen")
    args = parser.parse_args(argv)

    sft, rlvr = load_pair(args.corpus, args.id)
    request = build_request(sft, rlvr, model=args.model)
    if args.dry_run:
        print(json.dumps(request, ensure_ascii=False, indent=2))
        return 0

    if not args.api_key:
        raise SystemExit("--api-key oder BEMYSELF_DISTILL_KEY noetig fuer --send")
    trace = fetch_trace(request, url=args.url, api_key=args.api_key, timeout=args.timeout)
    leaks = find_gold_leaks(trace, gold_values(rlvr or {}))
    if leaks:
        print(json.dumps({"leak": True, "values": leaks, "trace_rejected": True}, ensure_ascii=False))
        return 3
    if args.out:
        Path(args.out).write_text(trace, encoding="utf-8")
    print(json.dumps({"leak": False, "chars": len(trace), "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

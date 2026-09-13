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
    BEMYSELF_DISTILL_KEY=… python3 training/distill_thinking.py --send \
        --id sft:v13:B3-0008:D --out trace.txt
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

# t1/t2/d-Zuweisungen -- die Schreibweise, in der Zertifikate in den Laeufen
# vorkommen. Zeilenpraefixe (h1:, S2:, cp 5:) sind bewusst NICHT Teil eines
# Treffers: eine Denkzone beginnt praktisch immer mit "h1:"/"S1:", ein reiner
# Zahlen-Scan wuerde also jede Denkzone als Leck melden (falsch-positiv).
_LABEL_RE = re.compile(r"\b(?:t1|t2|d)\s*[=:]\s*(-?\d+)", re.IGNORECASE)
_TUPLE_RE = re.compile(r"[\(\[\{]\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*[\)\]\}]")


def gold_values(record: dict) -> list[int]:
    """Die zu schuetzenden Gold-Werte des Datensatzes (leer, wenn keine).

    Default-Deny: sobald ein Zertifikat vorliegt und ``certificate_given``
    nicht ausdruecklich ``True`` ist (aeltere Set-Versionen kennen das Flag
    nicht), gilt das Zertifikat als nicht vorgegeben und wird geschuetzt.
    """
    gold = record.get("gold") or {}
    certificate = gold.get("certificate")
    if certificate and gold.get("certificate_given") is not True:
        return [int(value) for value in certificate]
    return []


def find_gold_leaks(text: str, values) -> list[int]:
    """Gold-Werte, die der Text als Zertifikatsaussage verraet.

    Erkannt wird ein Wert, wenn er
    * mit ``t1=``/``t2=``/``d=`` beschriftet ist, oder
    * Teil eines Zahlentripels ``(a, b, c)`` ist, das die Zertifikatswerte
      vollstaendig enthaelt.

    Bewusste Grenze: eine unbeschriftete Zahlenfolge ohne Tripel-Klammern
    ("34 37") wird nicht erkannt -- dafuer gibt es praktisch keine
    Falsch-Positive mehr.
    """
    values = list(values)
    if not values or not text:
        return []
    leaked: set[int] = set()
    for match in _LABEL_RE.finditer(text):
        value = int(match.group(1))
        if value in values:
            leaked.add(value)
    wanted = tuple(sorted(values))
    for match in _TUPLE_RE.finditer(text):
        triple = tuple(sorted(int(group) for group in match.groups()))
        if triple == wanted:
            leaked.update(triple)
    return sorted(leaked)


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

    api_key = os.environ.get("BEMYSELF_DISTILL_KEY", "")
    if not api_key:
        raise SystemExit("BEMYSELF_DISTILL_KEY noetig fuer --send (ENV, nicht CLI -- ps sichtbar)")
    trace = fetch_trace(request, url=args.url, api_key=api_key, timeout=args.timeout)
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

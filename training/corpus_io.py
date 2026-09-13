#!/usr/bin/env python3
"""Kleine stdlib-Helfer fuer die Trainings-Skripte.

Die Korpusdateien sind JSONL mit einem Objekt je Zeile; die Trainings-Skripte
teilen sich hier Validierung und Statistik, damit alle dieselbe Auffassung von
"gueltiger Datensatz" haben (und die dry-run-Pfade ohne Torch laufen).
"""

from __future__ import annotations

import json
from pathlib import Path

ROLES = ("system", "user", "assistant")
SPLITS = ("train", "val", "test")


def read_jsonl(path: Path | str) -> list[dict]:
    records: list[dict] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: kein JSON-Objekt: {exc}") from None
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{lineno}: Zeile ist kein JSON-Objekt")
        records.append(record)
    return records


def validate_records(records, *, path: str = "<records>", require_assistant: bool = True) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records):
        where = f"{path}[{index}]"
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"{where}: id fehlt")
        if record_id in seen:
            raise ValueError(f"{where}: doppelte id {record_id!r}")
        seen.add(record_id)
        split = record.get("split")
        if split not in SPLITS:
            raise ValueError(f"{where}: split {split!r} nicht in {SPLITS}")
        messages = record.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError(f"{where}: messages fehlen")
        roles = [message.get("role") for message in messages]
        expected = ROLES if require_assistant else ROLES[:2]
        if tuple(roles[: len(expected)]) != expected or len(roles) != len(expected):
            raise ValueError(f"{where}: Rollen {roles!r}, erwartet {list(expected)}")
        for message in messages:
            if not isinstance(message.get("content"), str) or not message["content"].strip():
                raise ValueError(f"{where}: leere Nachricht ({message.get('role')})")


def corpus_stats(records) -> dict:
    by_split = {split: 0 for split in SPLITS}
    chars = 0
    prompt_chars = 0
    for record in records:
        by_split[record["split"]] = by_split.get(record["split"], 0) + 1
        messages = record["messages"]
        chars += sum(len(message["content"]) for message in messages)
        prompt_chars += sum(len(message["content"]) for message in messages[:-1])
    return {
        "records": len(records),
        "by_split": by_split,
        "chars": chars,
        "prompt_chars": prompt_chars,
        "est_tokens": chars // 4,
    }

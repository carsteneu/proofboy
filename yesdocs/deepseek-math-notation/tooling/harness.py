#!/usr/bin/env python3
"""Pilot-Harness: fuehrt Aufgaben x Arme gegen die lokale Modell-Instanz aus.

Transport ist der **direkte HTTP-Pfad** ueber den lokalen Proxy
(``http://localhost:9099/v1/chat/completions``) mit dem DeepSeek-Schluessel
aus ``~/.local/share/opencode/auth.json``. Verifiziert am 2026-09-12:

- Der Aufruf kennt **keine Werkzeuge** — gemessen wird die Notation, nicht
  Tool-Nutzung; der Modell-Aufruf enthaelt nur unseren System- und User-Text.
- Der opencode-Systemprompt-Sockel (~21–28k Tokens, 05-04) faellt weg; Input,
  Output und Reasoning stehen als direkte Usage-Felder bereit
  (``completion_tokens_details.reasoning_tokens``).
- ``reasoning_content`` kommt als eigenes Feld der Antwort zurueck.
- Auth: ``Authorization: Bearer <key>`` und ``x-api-key: <key>`` liefern
  beide HTTP 200 (der 05-04-Vorbehalt ,,Auth ungeklaert'' ist damit
  ausgeraeumt — Abweichung dokumentiert im Pilotbericht).

Logs je Lauf: ``<runs>/<ts>/<task>/<arm>-rep<r>/`` mit ``prompt.md``
(System+User), ``raw.json`` (vollstaendige Antwort) und ``parsed.json``
(Metriken + Verdikte).

Aufrufe::

    python3 harness.py batch --arms K,B,C --reps 2 --tier-a 15 --tier-b 8
    python3 harness.py one --arm C --task A-0001 --rep 1
    python3 harness.py dry --arm C --task A-0001
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from bemyself.msheet.runner import run_sheet  # noqa: E402
from bemyself.msheet.sheet import parse_sheet  # noqa: E402
from bemyself.msheet.witnesses import _CP_RE, find_bwrap  # noqa: E402
from prompts import build_messages  # noqa: E402

PROXY_URL = "http://localhost:9099/v1/chat/completions"
MODEL = "deepseek-flash"
AUTH_PATH = os.path.expanduser("~/.local/share/opencode/auth.json")
SETS_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"
RUNS_DIR = ROOT / ".yesmem" / "tmp" / "runs"

_TIER_A_SET = "tier_a_v11-a-0.1.json"
_TIER_B_SET = "tier_b_v11-b-0.1.json"


def _api_key():
    with open(AUTH_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)["deepseek"]["key"]


def _load_set(filename):
    path = SETS_DIR / filename
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    payload["_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload["_path"] = str(path.relative_to(ROOT))
    return payload


def call_model(system, user, timeout):
    """One chat completion; returns (payload, raw, duration) or an error record."""
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 8192,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        PROXY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.load(response)
        duration = time.monotonic() - start
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return None, None, time.monotonic() - start, f"{type(exc).__name__}: {exc}"
    message = raw["choices"][0]["message"]
    payload = {
        "content": message.get("content") or "",
        "reasoning": message.get("reasoning_content") or "",
        "usage": raw.get("usage", {}),
        "finish_reason": raw["choices"][0].get("finish_reason"),
    }
    return payload, raw, duration, None


def extract_sheet_text(answer):
    """The sheet inside an answer: the largest fenced block, else the text."""
    fences = re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", answer, flags=re.DOTALL)
    if fences:
        return max(fences, key=len)
    return answer


def extract_endanswer(answer):
    matches = re.findall(r"Endantwort\s*:\s*(.+)", answer)
    if not matches:
        return None
    value = matches[-1].strip().split()[0] if matches[-1].strip() else None
    return value


def _normalize_value(value):
    if value is None:
        return None
    cleaned = value.strip().rstrip(".,;:)")
    cleaned = cleaned.replace(",", "").replace("_", "")
    return cleaned


def _contains_token(text, expected):
    return re.search(r"(?<![0-9])" + re.escape(expected) + r"(?![0-9])", text) is not None


def _checkpoint_pairs(text):
    pairs = {}
    for match in _CP_RE.findall(text):
        step = int(match[0])
        pairs[step] = (match[1], int(match[2]), match[3])
    return pairs


def _tape_key(tape):
    """Tape comparison up to leading/trailing zeros (value-equal windows)."""
    return tape.strip("0")


def _checkpoint_score(answer, gold):
    pairs = _checkpoint_pairs(answer)
    matched = 0
    first_deviation = None
    for step, state, head, tape in gold:
        got = pairs.get(step)
        if got is not None and got[0] == state and got[1] == head and _tape_key(got[2]) == _tape_key(tape):
            matched += 1
        elif first_deviation is None:
            first_deviation = step
    return matched, first_deviation, {str(k): v for k, v in sorted(pairs.items())}


def _sheet_evaluation(arm, answer):
    sheet = parse_sheet(extract_sheet_text(answer))
    result = run_sheet(sheet, sandbox="auto", timeout=20.0)
    return sheet, result


def evaluate_run(arm, task, payload, duration, error, args):
    record = {
        "arm": arm,
        "task_id": task["id"],
        "tier": task["tier"],
        "tier_b_kind": task.get("tier_b_kind"),
        "duration_s": round(duration, 2),
        "error": error,
        "usage": payload.get("usage") if payload else {},
        "finish_reason": payload.get("finish_reason") if payload else None,
    }
    answer = payload.get("content", "") if payload else ""
    reasoning = payload.get("reasoning", "") if payload else ""
    record["answer"] = answer[:20000]
    record["reasoning_chars"] = len(reasoning)
    record["reasoning"] = reasoning[:20000]
    record["solved"] = False

    if payload is None:
        return record

    if task["tier"] == "A":
        if arm == "K":
            value = _normalize_value(extract_endanswer(answer))
            record["endanswer"] = value
            record["solved"] = value == task["expected"]
        else:
            sheet, result = _sheet_evaluation(arm, answer)
            record["format_errors"] = result.format_errors
            record["v"] = [
                {"id": v.vid, "target": v.target, "verdict": v.verdict.value}
                for v in result.v_results
            ]
            record["claims"] = [
                {"id": c.cid, "verdict": c.verdict.value, "reason": c.reason}
                for c in result.claim_results
            ]
            record["appendix"] = result.appendix
            claim_texts = {claim.cid: claim.text for claim in sheet.claims}
            confirmed = [
                c
                for c in result.claim_results
                if c.verdict.value == "CONFIRMED" and _contains_token(claim_texts.get(c.cid, ""), task["expected"])
            ]
            record["solved"] = bool(result.claim_results) and all(
                c.verdict.value == "CONFIRMED" for c in result.claim_results
            ) and bool(confirmed)
    elif task.get("tier_b_kind") == "trace":
        matched, first_deviation, pairs = _checkpoint_score(answer, task["checkpoints_gold"])
        record["checkpoints_matched"] = matched
        record["checkpoints_total"] = len(task["checkpoints_gold"])
        record["first_deviation"] = first_deviation
        record["checkpoints"] = pairs
        record["solved"] = matched == len(task["checkpoints_gold"])
        if arm in ("B", "C", "D"):
            sheet, result = _sheet_evaluation(arm, answer)
            record["format_errors"] = result.format_errors
            record["appendix"] = result.appendix
            record["v"] = [
                {"id": v.vid, "target": v.target, "verdict": v.verdict.value}
                for v in result.v_results
            ]
    elif task.get("tier_b_kind") == "cyc":
        t1, t2, d = (str(x) for x in task["certificate"])
        if arm in ("K", "B"):
            record["solved"] = (
                "NICHT-HALTEND" in answer
                and f"t1={t1}" in answer
                and f"t2={t2}" in answer
                and f"d={d}" in answer
            )
        else:
            sheet, result = _sheet_evaluation(arm, answer)
            record["format_errors"] = result.format_errors
            record["appendix"] = result.appendix
            record["claims"] = [
                {"id": c.cid, "verdict": c.verdict.value, "reason": c.reason}
                for c in result.claim_results
            ]
            record["v"] = [
                {"id": v.vid, "target": v.target, "verdict": v.verdict.value}
                for v in result.v_results
            ]
            # The sheet must reason about the task's machine: a self-consistent
            # sheet about another machine must not count as an answer.
            task_machine = task["machine"].replace(" ", "").replace("_", "").upper()
            bound = {
                machine.source.replace(" ", "").replace("_", "").upper()
                for machine in sheet.machines.values()
            }
            record["machine_bound"] = task_machine in bound
            record["solved"] = (
                bool(result.claim_results)
                and all(c.verdict.value == "CONFIRMED" for c in result.claim_results)
                and record["machine_bound"]
            )
    return record


def run_one(arm, task, rep, runs_root, args, warmup=False):
    out_dir = runs_root / ("_warmup" if warmup else f"{task['id']}") / f"{arm}-rep{rep}"
    out_dir.mkdir(parents=True, exist_ok=True)
    system, user = build_messages(arm, task)
    (out_dir / "prompt.md").write_text(
        f"# system\n\n{system}\n\n# user\n\n{user}\n", encoding="utf-8"
    )
    payload, raw, duration, error = call_model(system, user, args.timeout)
    if raw is not None:
        (out_dir / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    record = evaluate_run(arm, task, payload, duration, error, args)
    record["rep"] = rep
    (out_dir / "parsed.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def _select_tasks(tier_a, tier_b, args):
    rng = random.Random(args.seed)
    a_tasks = list(tier_a["tasks"])
    b_tasks = list(tier_b["tasks"])
    rng.shuffle(a_tasks)
    rng.shuffle(b_tasks)
    if args.tier_a is not None:
        a_tasks = a_tasks[: args.tier_a]
    if args.tier_b is not None:
        b_tasks = b_tasks[: args.tier_b]
    return a_tasks + b_tasks


def cmd_batch(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = _select_tasks(tier_a, tier_b, args)
    arms = [arm.strip().upper() for arm in args.arms.split(",") if arm.strip()]
    runs_root = RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")
    runs_root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    manifest = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": MODEL,
        "arms": arms,
        "reps": args.reps,
        "tier_a_set": {"version": tier_a["set_version"], "sha256": tier_a["_sha256"]},
        "tier_b_set": {"version": tier_b["set_version"], "sha256": tier_b["_sha256"]},
        "tasks": [task["id"] for task in tasks],
        "seed": args.seed,
    }
    (runs_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"runs root: {runs_root.relative_to(ROOT)}")
    print(f"tasks: {len(tasks)} ({len([t for t in tasks if t['tier']=='A'])} A, "
          f"{len([t for t in tasks if t['tier']=='B'])} B), arms {arms}, reps {args.reps}")

    if not args.skip_warmup:
        _payload, _raw, duration, error = call_model(
            "Du bist ein Test.", "Antworte mit exakt einem Wort: OK", args.timeout
        )
        print(f"warmup: {duration:.1f}s error={error}")

    solved = 0
    runs = 0
    for task in tasks:
        for rep in range(1, args.reps + 1):
            order = list(arms)
            rng.shuffle(order)
            for arm in order:
                runs += 1
                record = run_one(arm, task, rep, runs_root, args)
                solved += bool(record.get("solved"))
                marker = "OK " if record.get("solved") else "   "
                usage = record.get("usage") or {}
                print(
                    f"{marker}{task['id']} rep{rep} {arm}: "
                    f"{record['duration_s']:6.1f}s "
                    f"out={usage.get('completion_tokens', '?')} "
                    f"reas={usage.get('completion_tokens_details', {}).get('reasoning_tokens', '?')}"
                    + (f" ERR={record['error']}" if record.get("error") else "")
                )
    print(f"done: {runs} runs, solved {solved}/{runs}")
    return 0


def cmd_one(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = {t["id"]: t for t in tier_a["tasks"] + tier_b["tasks"]}
    task = tasks[args.task]
    runs_root = RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")
    record = run_one(args.arm.upper(), task, args.rep, runs_root, args)
    print(json.dumps({k: v for k, v in record.items() if k not in ("answer", "reasoning")}, indent=2))
    return 0


def cmd_dry(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = {t["id"]: t for t in tier_a["tasks"] + tier_b["tasks"]}
    system, user = build_messages(args.arm.upper(), tasks[args.task])
    print(f"# system\n{system}\n\n# user\n{user}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p):
        p.add_argument("--timeout", type=float, default=300.0, help="seconds per model call")

    batch = sub.add_parser("batch", help="run the pilot matrix")
    batch.add_argument("--arms", default="K,B,C")
    batch.add_argument("--reps", type=int, default=2)
    batch.add_argument("--tier-a", type=int, default=None, help="max Tier-A tasks")
    batch.add_argument("--tier-b", type=int, default=None, help="max Tier-B tasks")
    batch.add_argument("--seed", type=int, default=20260912)
    batch.add_argument("--skip-warmup", action="store_true")
    _common(batch)
    batch.set_defaults(func=cmd_batch)

    one = sub.add_parser("one", help="run one task x arm x rep")
    one.add_argument("--arm", required=True)
    one.add_argument("--task", required=True)
    one.add_argument("--rep", type=int, default=1)
    _common(one)
    one.set_defaults(func=cmd_one)

    dry = sub.add_parser("dry", help="print the messages of one run")
    dry.add_argument("--arm", required=True)
    dry.add_argument("--task", required=True)
    dry.set_defaults(func=cmd_dry)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

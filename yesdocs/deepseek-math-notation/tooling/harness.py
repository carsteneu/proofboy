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

Logs je Lauf: ``<runs>/<ts>/<task>/<arm>-rep<r>/`` mit ``round<n>/`` je
Runde (``prompt.md`` = gesamter Verlauf, ``raw.json`` = vollstaendige Antwort,
``parsed.json`` = Metriken + Verdikte + Feedback) und ``summary.json`` je
Lauf (Runden, Endzustand, Tokens).

Runde 2 (V12): Reparatur-Loop. Runde 0 laeuft wie der Pilot; ist der
Endzustand danach nicht bestaetigt, folgt eine Reparaturrunde (max.
``--max-repairs``, Default 2) mit dem Verdikt-Appendix des Runners im
Verlauf. K erhaelt stattdessen eine neutrale Selbstpruefung; die Formel-Arme
(B/C/D) erhalten ihre eigenen maschinell geprueften Verdikte -- niemals
Referenzwerte (Gold-Leak-Schutz in :func:`feedback_lines`).

Aufrufe::

    python3 harness.py batch --arms K,B,C,D --reps 2 --tier-a 16 --tier-b 12
    python3 harness.py one --arm C --task A-0006 --rep 1
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
from prompts import build_messages, build_repair_message  # noqa: E402

PROXY_URL = "http://localhost:9099/v1/chat/completions"
MODEL = "deepseek-flash"
AUTH_PATH = os.path.expanduser("~/.local/share/opencode/auth.json")
SETS_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"
RUNS_DIR = ROOT / ".yesmem" / "tmp" / "runs"

_TIER_A_SET = "tier_a_v11-a-0.2.json"
_TIER_B_SET = "tier_b_v11-b-0.2.json"

# Runde-2-Fairness-Design: Diese Arme erhalten in der Reparaturrunde ihre
# eigenen maschinellen Verdikte (Appendix + Befunde). K erhaelt die neutrale
# Selbstpruefung -- Verdikte, die es nicht gibt, werden nicht erfunden.
MACHINE_FEEDBACK_ARMS = ("B", "C", "D")


def _api_key():
    try:
        with open(AUTH_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)["deepseek"]["key"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"cannot read the deepseek key from {AUTH_PATH}: {type(exc).__name__}: {exc}"
        ) from None


def _load_set(filename):
    path = SETS_DIR / filename
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    payload["_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload["_path"] = str(path.relative_to(ROOT))
    return payload


def call_model(messages, timeout):
    """One chat completion (messages array, direct proxy); returns
    (payload, raw, duration, error)."""
    body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
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
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, None, time.monotonic() - start, f"malformed response: {exc}"
    try:
        message = raw["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        return None, raw, time.monotonic() - start, f"unexpected response shape: {exc!r}"
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


def _sheet_evaluation(answer):
    sheet = parse_sheet(extract_sheet_text(answer))
    result = run_sheet(sheet, sandbox="auto", timeout=20.0)
    return sheet, result


def _sheet_block(sheet, result):
    """The persisted sheet evidence: verdicts, witness kind/text, errors."""
    kinds = {v.vid: (v.spec.kind if v.spec else "unparsable") for v in sheet.vlines}
    texts = {v.vid: v.witness_text for v in sheet.vlines}
    block = {
        "format_errors": result.format_errors,
        "appendix": result.appendix,
        "v": [
            {
                "id": v.vid,
                "target": v.target,
                "verdict": v.verdict.value,
                "kind": kinds.get(v.vid, "?"),
                "witness": texts.get(v.vid, ""),
            }
            for v in result.v_results
        ],
    }
    if result.claim_results:
        block["claims"] = [
            {
                "id": c.cid,
                "verdict": c.verdict.value,
                "reason": c.reason,
                "witness": (
                    sheet.witness_for(c.cid).text if sheet.witness_for(c.cid) else ""
                ),
            }
            for c in result.claim_results
        ]
    return block


def evaluate_answer(arm, task, answer, evidence_out=None):
    """Score one answer by the pilot conventions.

    Fills ``evidence_out`` (when given) with the parsed sheet and its runner
    result whenever a sheet was evaluated -- the repair round builds its
    feedback from exactly this evidence.
    """
    fragment = {"solved": False}

    if task["tier"] == "A":
        if arm == "K":
            value = _normalize_value(extract_endanswer(answer))
            fragment["endanswer"] = value
            fragment["solved"] = value == task["expected"]
        else:
            sheet, result = _sheet_evaluation(answer)
            if evidence_out is not None:
                evidence_out["sheet"] = sheet
                evidence_out["result"] = result
            fragment.update(_sheet_block(sheet, result))
            claim_texts = {claim.cid: claim.text for claim in sheet.claims}
            confirmed = [
                c
                for c in result.claim_results
                if c.verdict.value == "CONFIRMED"
                and _contains_token(claim_texts.get(c.cid, ""), task["expected"])
            ]
            fragment["solved"] = (
                bool(result.claim_results)
                and all(c.verdict.value == "CONFIRMED" for c in result.claim_results)
                and bool(confirmed)
            )
    elif task.get("tier_b_kind") == "trace":
        matched, first_deviation, pairs = _checkpoint_score(answer, task["checkpoints_gold"])
        fragment["checkpoints_matched"] = matched
        fragment["checkpoints_total"] = len(task["checkpoints_gold"])
        fragment["first_deviation"] = first_deviation
        fragment["checkpoints"] = pairs
        fragment["solved"] = matched == len(task["checkpoints_gold"])
        if arm in ("B", "C", "D"):
            sheet, result = _sheet_evaluation(answer)
            if evidence_out is not None:
                evidence_out["sheet"] = sheet
                evidence_out["result"] = result
            fragment.update(_sheet_block(sheet, result))
    elif task.get("tier_b_kind") == "cyc":
        t1, t2, d = (str(x) for x in task["certificate"])
        if arm in ("K", "B"):
            fragment["solved"] = (
                "NICHT-HALTEND" in answer
                and f"t1={t1}" in answer
                and f"t2={t2}" in answer
                and f"d={d}" in answer
            )
        else:
            sheet, result = _sheet_evaluation(answer)
            if evidence_out is not None:
                evidence_out["sheet"] = sheet
                evidence_out["result"] = result
            fragment.update(_sheet_block(sheet, result))
            # The sheet must reason about the task's machine: a self-consistent
            # sheet about another machine must not count as an answer (and no
            # extra unrelated bindings either).
            task_machine = task["machine"].replace(" ", "").replace("_", "").upper()
            bound = {
                machine.source.replace(" ", "").replace("_", "").upper()
                for machine in sheet.machines.values()
            }
            fragment["machine_bound"] = bool(bound) and bound == {task_machine}
            fragment["solved"] = (
                bool(result.claim_results)
                and all(c.verdict.value == "CONFIRMED" for c in result.claim_results)
                and fragment["machine_bound"]
            )
    return fragment


def evaluate_run(arm, task, payload, duration, error, args, evidence_out=None):
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

    record.update(evaluate_answer(arm, task, answer, evidence_out=evidence_out))
    return record


_SIM_STEP_RE = re.compile(r"sim: at step ([0-9]+)")


def _sanitize_reason(kind, verdict, reason):
    """The reason as safe to hand back: error texts stay, computed reference
    values do not (no gold leak). ``sim``/``cyc`` refutations name the actual
    state/head/tape or certificate parts -- the sheet owner must find its own
    values again."""
    if verdict != "REFUTED":
        return reason
    if kind == "sim":
        match = _SIM_STEP_RE.search(reason)
        where = f" bei Schritt {match.group(1)}" if match else ""
        return (
            f"sim: die Konfiguration{where} stimmt nicht mit der "
            "Referenzsimulation ueberein"
        )
    if kind == "cyc":
        return "cyc: das Zertifikat traegt fuer diese Maschine nicht"
    return reason


def feedback_lines(arm, task, evidence):
    """(appendix, notes) of the repair round -- sanitized, never gold.

    K (and any arm without machine-checked evidence) gets nothing: verdicts
    that do not exist are not invented.
    """
    if arm not in MACHINE_FEEDBACK_ARMS or not evidence:
        return [], []
    sheet = evidence.get("sheet")
    result = evidence.get("result")
    if result is None:
        return [], []
    kinds = {vline.vid: (vline.spec.kind if vline.spec else None) for vline in sheet.vlines}
    for claim in sheet.claims:
        witness = sheet.witness_for(claim.cid)
        kinds[claim.cid] = witness.spec.kind if witness is not None and witness.spec else None
    notes = []
    for row in list(result.v_results) + list(result.claim_results):
        rid = getattr(row, "vid", None) or row.cid
        if row.verdict.value == "CONFIRMED":
            continue
        notes.append(f"{rid}: {_sanitize_reason(kinds.get(rid), row.verdict.value, row.reason)}")
    return list(result.appendix), notes


def _render_messages(messages):
    parts = [f"# {message['role']}\n\n{message.get('content', '')}" for message in messages]
    return "\n\n".join(parts) + "\n"


def run_rounds(arm, task, rep, runs_root, args, call=None):
    """One task x arm x rep over round 0 + up to ``max_repairs`` repair rounds.

    Round 0 runs like the pilot. When the end state is not confirmed, the next
    round continues the same conversation: the model's own answer plus the
    verdict feedback (or, for K, the neutral self-check). Stops as soon as the
    end state is confirmed. Transport errors get the single retry of the 05-05
    stop rule; a round without model output ends the run.
    """
    call = call or call_model
    max_repairs = getattr(args, "max_repairs", 2)
    base = runs_root / task["id"] / f"{arm}-rep{rep}"
    base.mkdir(parents=True, exist_ok=True)
    system, user = build_messages(arm, task)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    rounds = []
    retries = 0
    feedback_in = None

    for round_index in range(max_repairs + 1):
        out_dir = base / f"round{round_index}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "prompt.md").write_text(_render_messages(messages), encoding="utf-8")
        payload = raw = None
        duration = 0.0
        error = "not called"
        for attempt in (0, 1):
            payload, raw, duration, error = call(messages, args.timeout)
            if error is None:
                break
            if attempt == 0:
                retries += 1
        if raw is not None:
            (out_dir / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

        evidence = {}
        record = evaluate_run(arm, task, payload, duration, error, args, evidence_out=evidence)
        record["round"] = round_index
        record["feedback_in"] = feedback_in
        answer = record.get("answer", "")
        solved = bool(record["solved"])
        usage = record.get("usage") or {}
        rounds.append(
            {
                "round": round_index,
                "solved": solved,
                "error": error,
                "duration_s": record["duration_s"],
                "completion_tokens": usage.get("completion_tokens", 0),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens", 0
                ),
                "format_errors": len(record.get("format_errors") or []),
            }
        )

        stop = solved or payload is None or round_index == max_repairs
        repair_text = None
        if not stop:
            result = evidence.get("result")
            verdicts, notes = feedback_lines(arm, task, evidence)
            format_errors = list(result.format_errors) if result is not None else []
            repair_text = build_repair_message(arm, task, verdicts, notes, format_errors)
        record["next_feedback"] = repair_text
        (out_dir / "parsed.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

        if stop:
            break
        messages.append({"role": "assistant", "content": answer})
        messages.append({"role": "user", "content": repair_text})
        feedback_in = repair_text

    rounds_to_ok = next((row["round"] for row in rounds if row["solved"]), None)
    summary = {
        "task_id": task["id"],
        "arm": arm,
        "tier": task["tier"],
        "rep": rep,
        "max_repairs": max_repairs,
        "rounds": rounds,
        "final_solved": bool(rounds and rounds[-1]["solved"]),
        "rounds_to_ok": rounds_to_ok,
        "repairs_used": len(rounds) - 1,
        "transport_retries": retries,
        "total_completion_tokens": sum(row["completion_tokens"] for row in rounds),
        "total_reasoning_tokens": sum(row["reasoning_tokens"] for row in rounds),
        "total_duration_s": round(sum(row["duration_s"] for row in rounds), 2),
    }
    (base / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


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
        "mode": "repair",
        "max_repairs": args.max_repairs,
        "transport": "proxy-9099",
        "reasoning_history": "strip",
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
          f"{len([t for t in tasks if t['tier']=='B'])} B), arms {arms}, reps {args.reps}, "
          f"max_repairs {args.max_repairs}")

    if not args.skip_warmup:
        _payload, _raw, duration, error = call_model(
            [
                {"role": "system", "content": "Du bist ein Test."},
                {"role": "user", "content": "Antworte mit exakt einem Wort: OK"},
            ],
            args.timeout,
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
                summary = run_rounds(arm, task, rep, runs_root, args)
                solved += bool(summary["final_solved"])
                marker = "OK " if summary["final_solved"] else "   "
                r0 = summary["rounds"][0]
                print(
                    f"{marker}{task['id']} rep{rep} {arm}: "
                    f"rounds={len(summary['rounds'])} r0={'ok' if r0['solved'] else 'no'} "
                    f"r2ok={summary['rounds_to_ok']} "
                    f"tok={summary['total_completion_tokens']} "
                    f"({summary['total_duration_s']:.1f}s)"
                    + (f" ERR={summary['rounds'][-1]['error']}" if summary["rounds"][-1]["error"] else "")
                )
    print(f"done: {runs} runs, final solved {solved}/{runs}")
    return 0


def cmd_one(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = {t["id"]: t for t in tier_a["tasks"] + tier_b["tasks"]}
    task = tasks[args.task]
    runs_root = RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")
    summary = run_rounds(args.arm.upper(), task, args.rep, runs_root, args)
    print(json.dumps(summary, indent=2))
    print(f"logs: {(runs_root / task['id'] / f'{args.arm.upper()}-rep{args.rep}').relative_to(ROOT)}")
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
        p.add_argument(
            "--max-repairs",
            type=int,
            default=2,
            help="repair rounds after a not-confirmed round 0 (default 2)",
        )

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

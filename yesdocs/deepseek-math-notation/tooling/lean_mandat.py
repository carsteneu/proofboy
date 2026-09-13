#!/usr/bin/env python3
"""Lean-Mandat-Runner V19 — Prompt-Varianten-Matrix fuer Lean-Denken/-Liefern.

Hintergrund: Die Inline-Proben vom 2026-09-13 (17:03–17:05, rohe Python-Calls,
nicht abgelegt) zeigten zweierlei: Der Denkkanal (``reasoning_content``) ist per
Prompt nicht in Lean zu bringen (10/10 Proben Prosa, fuenf Stile, zwei Modelle),
die sichtbare Antwort dagegen wird mit einem Lean-geschriebenen Systemprompt
zuverlaessig pures Lean. Dieser Runner macht die Proben reproduzierbar:

- **Varianten V-A..V-E**: V-A Regeln als ``--``-Kommentare (Systemprompt selbst
  Lean); V-B + ein Denkspur-Beispiel; V-C + drei Beispiele; V-D Completion-
  Prefill (unfertiges ``have h1 : … := by`` im Assistant-Content); V-E = V-B
  + Fence-Verbot. Die Variantentexte sind aus der Inline-Session geborgen;
  V-C leitet monoton aus V-B ab (inline war die Basis dort kuerzer).
- **Aufgaben-Grade**: trivial / mechanisch / Lemma (7 Aufgaben, alle mit
  vorvalidiertem Std-Referenzbeweis als ``ref_tactic``).

Gemessen wird deskriptiv: RC-Lean-Anteil (``leanfidelity``), Fence-Rate,
Statement-Echo (steht die geforderte Aussage im Code?), Verdikt des
``leancheck``-Elaborators (valid/invalid/timeout, ``sorry``, Axiome), Tokens
(completion + reasoning) und Dauer. Keine Signifikanzaussagen.

Aufruf::

    BEMYSELF_TARGET=deepseek BEMYSELF_MAX_TOKENS=4096 \
        python3 lean_mandat.py run --out .yesmem/tmp/lean-mandat/<ts> --reps 3
    python3 lean_mandat.py render --run <dir> [--raw raw.md] [--summary summary.md]

Hinweise: Transport ist ``harness.call_model`` (direkter HTTP-Pfad; Schluessel
nie in Artefakten). Der Prefill (V-D) laeuft im inline-treuen ``/v1``-Modus
ohne ``prefix: true``; der ``content`` kann den Prefill wiederholen (Feld
``prefill_echo``, ``continuation`` = eigener Text). Der Artefakt-Kontrakt
(``import Std`` + ``theorem main_thm``) weicht bewusst von den Inline-Proben ab
— ohne Theoremnamen traegt der Schnipsel keine Axiom-Sonde und ist im
Minimalprojekt nicht elaborierbar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]  # yesdocs/deepseek-math-notation/tooling -> repo root

# ---------------------------------------------------------------------------
# Variantentexte. SYS_A / SYS_LEAN / das Denkspur-Beispiel stammen woertlich
# aus der Inline-Session (2026-09-13, deep_search); V-C erweitert V-B monoton
# um die zwei weiteren Beispiele der Inline-Variante E.
# ---------------------------------------------------------------------------

SYS_A = """-- SYSTEM PROMPT (Lean 4, Core/Std) -- diese Nachricht ist selbst Lean-Code.
-- REGELN (MANDATORY, nicht optional, nicht verhandelbar):
-- 1. Deine gesamte Denkspur (reasoning_content) MUSS aus Lean-4-Code bestehen.
-- 2. Deine sichtbare Antwort MUSS aus Lean-4-Code bestehen.
-- 3. Prosa ist ein Kompilierfehler: kein Satz ausserhalb von `--`-Kommentaren,
--    keine Vorrede, kein Markdown, keine Code-Fences.
-- 4. Jede Denkspur-Zeile ist eine Taktik-Zeile: `have <id> : <aussage> := by <taktik>`
--    oder eine Taktik (`decide`, `rfl`, `omega`, `simp`, `norm_num`) oder `--`.
-- BEISPIEL:
example : 1 + 1 = 2 := by decide
-- ENDE DER REGELN."""

SYS_B_EXTRA = """

-- BEISPIEL EINER KORREKTEN DENKSPUR (Form, beliebige Zahlen):
-- goal: 12 + 30 = 42
have h1 : 12 + 30 = 42 := by decide
-- goal erreicht, Abschluss:
exact h1"""

SYS_C_EXTRA = """

-- WEITERE BEISPIELE KORREKTER DENKSPUREN:
-- goal: 7 * 6 = 42
have a : 7 * 6 = 42 := by decide
exact a
-- goal: 100 - 58 = 42
have b : 100 - 58 = 42 := by decide
exact b"""

SYS_D = """-- SYSTEM PROMPT (Lean 4). REGEL: Jede Zeile (Denkspur UND Antwort) ist
-- (1) `-- ...`, (2) `have <id> : <a> := by <t>`, (3) Taktik, (4) `example ...`.
-- PROSA IST VERBOTEN. Beispiel:
-- goal: 12 + 30 = 42
have h1 : 12 + 30 = 42 := by decide
exact h1"""

FENCE_BAN = """

-- ZUSATZ (MANDATORY): Die formale Antwort enthaelt KEINE Markdown-FENCES
-- (kein ```, kein ```lean). Nur blanker Lean-Code, direkt elaborierbar."""

USER_TEMPLATE = """-- ZIEL: Beweise in Lean 4 (Core/Std) als Theorem `main_thm`:
--   theorem main_thm : {statement} := by ...
-- Vorgaben: erste Zeile `import Std`; Theoremname `main_thm`; keine weiteren Imports.
-- Antwort: der komplette Lean-Beweis (nur Code, kein Markdown).
-- Denkspur: NUR Lean-4-Taktikzeilen."""

PREFILL_TEMPLATE = """import Std

theorem main_thm : {statement} := by
  have h1 : {statement} := by """

VARIANTS = {
    "V-A": {"label": "Regeln als Lean-Kommentare", "system": SYS_A, "prefill": False},
    "V-B": {"label": "+ ein Denkspur-Beispiel", "system": SYS_A + SYS_B_EXTRA, "prefill": False},
    "V-C": {
        "label": "+ drei Denkspur-Beispiele",
        "system": SYS_A + SYS_B_EXTRA + SYS_C_EXTRA,
        "prefill": False,
    },
    "V-D": {"label": "Completion-Prefill (content)", "system": SYS_D, "prefill": True},
    "V-E": {"label": "V-B + Fence-Verbot", "system": SYS_A + SYS_B_EXTRA + FENCE_BAN, "prefill": False},
}

# 7 Aufgaben mit Std-Referenzbeweis (per Test real elaboriert). Die Aussagen
# sind wahr und im Minimalprojekt beweisbar; `ref_tactic` ist die Vorab-Pruefung
# der Machbarkeit, kein Modell-Output.
TASKS = [
    {"id": "t1", "grade": "trivial", "statement": "2 + 3 = 5", "ref_tactic": "decide"},
    {"id": "t2", "grade": "trivial", "statement": "1 + 1 = 2", "ref_tactic": "decide"},
    {"id": "m1", "grade": "mechanical", "statement": "(12 + 30) % 7 = 0", "ref_tactic": "decide"},
    {
        "id": "m2",
        "grade": "mechanical",
        "statement": "837465291837 + 192837465564 = 1030302757401",
        "ref_tactic": "decide",
    },
    {"id": "l1", "grade": "lemma", "statement": "∀ n : Nat, n + 0 = n", "ref_tactic": "simp"},
    {"id": "l2", "grade": "lemma", "statement": "[1, 2, 3].length = 3", "ref_tactic": "decide"},
    {"id": "l3", "grade": "lemma", "statement": "∀ a b : Nat, a + b = b + a", "ref_tactic": "omega"},
]

GRADE_ORDER = ("trivial", "mechanical", "lemma")

# Dieselbe Extraktion wie lean_smoke/harness: groesster Zaun-Block, sonst der
# volle Text. `fenced` unterscheidet die zwei Faelle (Leck-Metrik).
FENCE_RE = re.compile(r"```[a-zA-Z0-9]*\n(.*?)```", flags=re.DOTALL)

SUMMARY_MARKER = "# Lean-Mandat-Matrix V19"


def build_prefill(task):
    """Der Assistant-Prefill der Completion-Variante (unfertiges `have`)."""
    return PREFILL_TEMPLATE.format(statement=task["statement"])


def build_messages(variant_id, task):
    """System/User (und ggf. Prefill-Assistant) fuer eine Zelle."""
    variant = VARIANTS[variant_id]
    messages = [
        {"role": "system", "content": variant["system"]},
        {"role": "user", "content": USER_TEMPLATE.format(statement=task["statement"])},
    ]
    if variant["prefill"]:
        messages.append({"role": "assistant", "content": build_prefill(task)})
    return messages


def extract_code(answer):
    """``(code, fenced)`` — groesster Zaun-Block, sonst der volle Text."""
    fences = FENCE_RE.findall(answer or "")
    if fences:
        return max(fences, key=len).strip(), True
    return (answer or "").strip(), False


def strip_prefill(text, prefill):
    """``(eigener_text, echo)`` — entfernt einen wiederholten Prefill-Rumpf."""
    if prefill and text.startswith(prefill):
        return text[len(prefill):].lstrip("\n"), True
    return text, False


def statement_echo(code, statement):
    """Steht die geforderte Aussage im Code? (nur Whitespace normalisiert)"""
    if not code:
        return False
    normalize = lambda value: re.sub(r"\s+", "", value)
    return normalize(statement) in normalize(code)


def _rc_metrics(text):
    from leanfidelity import parse_lean_text  # gleicher Tooling-Ordner

    return parse_lean_text(text or "")


def _aggregate(entries):
    """Deskriptive Zaehlung ueber Eintraege (keine Signifikanzaussagen)."""
    counts = {"valid": 0, "invalid": 0, "timeout": 0, "infra_error": 0}
    no_code = 0
    transport_errors = 0
    axiom_free = 0
    sorry_used = 0
    fenced = 0
    echoed = 0
    statement_echoed = 0
    reasoning_tokens = 0
    completion_tokens = 0
    duration = 0.0
    rc_shares = []
    rc_tactic_shares = []
    rc_lines = 0
    for entry in entries:
        if entry.get("error"):
            transport_errors += 1
        usage = entry.get("usage") or {}
        reasoning_tokens += (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        completion_tokens += usage.get("completion_tokens", 0)
        duration += entry.get("duration_s") or 0.0
        if entry.get("fenced"):
            fenced += 1
        if entry.get("prefill_echo"):
            echoed += 1
        if entry.get("statement_echo"):
            statement_echoed += 1
        rc = entry.get("rc") or {}
        if rc:
            rc_shares.append(rc.get("lean_line_share", 0.0))
            rc_tactic_shares.append(rc.get("tactic_line_share", 0.0))
            rc_lines += rc.get("lines", 0)
        lean = entry.get("lean")
        if lean is None:
            no_code += 1
            continue
        status = lean.get("status")
        if status in counts:
            counts[status] += 1
        # Nur valide Zellen tragen eine sinnvolle Axiom-Aussage: die Sonde der
        # angehaengten Zeile kann auch bei invalidem Schnipsel bestehen.
        if status == "valid" and lean.get("axioms") == "none":
            axiom_free += 1
        if lean.get("sorry_used"):
            sorry_used += 1
    n = len(entries)
    mean = lambda values: round(sum(values) / len(values), 4) if values else 0.0
    return {
        "n": n,
        **counts,
        "no_code": no_code,
        "transport_errors": transport_errors,
        "axiom_free": axiom_free,
        "sorry_used": sorry_used,
        "fenced": fenced,
        "prefill_echo": echoed,
        "statement_echo": statement_echoed,
        "valid_frac": round(counts["valid"] / n, 4) if n else 0.0,
        "fence_frac": round(fenced / n, 4) if n else 0.0,
        "reasoning_tokens_sum": reasoning_tokens,
        "completion_tokens_sum": completion_tokens,
        "duration_s_sum": round(duration, 1),
        "rc_lean_line_share_mean": mean(rc_shares),
        "rc_tactic_line_share_mean": mean(rc_tactic_shares),
        "rc_lines_sum": rc_lines,
    }


def summarize(results):
    """Aggregate je Gesamt, je Variante und je Zelle (Variante x Grad)."""
    per_variant = {}
    per_cell = {}
    for entry in results:
        per_variant.setdefault(entry["variant"], []).append(entry)
        per_cell.setdefault((entry["variant"], entry["grade"]), []).append(entry)
    cells = []
    for (variant, grade), entries in per_cell.items():
        cells.append({"variant": variant, "grade": grade, **_aggregate(entries)})
    cells.sort(key=lambda cell: (list(VARIANTS).index(cell["variant"]), GRADE_ORDER.index(cell["grade"])))
    return {
        "overall": _aggregate(results),
        "per_variant": {variant: _aggregate(entries) for variant, entries in per_variant.items()},
        "per_cell": cells,
    }


def _cell_text(text, limit=None):
    value = " ".join(str(text or "").split())
    if limit and len(value) > limit:
        value = value[: limit - 1] + "…"
    return value.replace("|", "\\|")


def _entry_status(entry):
    if entry.get("error"):
        return "transport_error"
    if entry.get("lean") is None:
        return "no_code"
    return (entry.get("lean") or {}).get("status", "?")


def _entry_diagnostic(entry):
    if entry.get("error"):
        return entry["error"]
    lean = entry.get("lean") or {}
    errors = lean.get("errors") or []
    if errors:
        return errors[0].get("message")
    return lean.get("message")


def render_summary(summary, results):
    """Markdown-Asset mit den Aggregaten (deterministisch aus results.json)."""
    overall = summary["overall"]
    lines = [
        SUMMARY_MARKER + " (deskriptiv)",
        "",
        f"- Zellen: {overall['n']} · valid {overall['valid']} ({overall['valid_frac']}) · "
        f"axiomfrei {overall['axiom_free']} · sorry {overall['sorry_used']} · "
        f"invalid {overall['invalid']} · timeout {overall['timeout']} · infra {overall['infra_error']} · "
        f"ohne Code {overall['no_code']} (davon Transportfehler {overall['transport_errors']})",
        f"- Fences: {overall['fenced']} ({overall['fence_frac']}) · Prefill-Echo: {overall['prefill_echo']} · "
        f"Statement-Echo: {overall['statement_echo']}",
        f"- Denkspur: Lean-Zeilen-Anteil ø {overall['rc_lean_line_share_mean']} · "
        f"Taktik-Zeilen-Anteil ø {overall['rc_tactic_line_share_mean']} · RC-Zeilen Σ {overall['rc_lines_sum']}",
        f"- Tokens: reasoning {overall['reasoning_tokens_sum']} · completion {overall['completion_tokens_sum']} · "
        f"Dauer {overall['duration_s_sum']} s",
        "",
        "| Variante | Grad | n | valid | axiomfrei | sorry | Fence | Statement-Echo | RC-Lean ø | RC-Taktik ø | Reasoning-Tok | Completion-Tok |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in summary["per_cell"]:
        lines.append(
            f"| {cell['variant']} | {cell['grade']} | {cell['n']} | {cell['valid']} | {cell['axiom_free']} | "
            f"{cell['sorry_used']} | {cell['fenced']} | {cell['statement_echo']} | {cell['rc_lean_line_share_mean']} | "
            f"{cell['rc_tactic_line_share_mean']} | {cell['reasoning_tokens_sum']} | {cell['completion_tokens_sum']} |"
        )
    lines.extend(
        [
            "",
            "| Variante | n | valid | axiomfrei | sorry | Fence | RC-Lean ø | RC-Taktik ø | Reasoning-Tok | Completion-Tok | Dauer s |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for variant, data in summary["per_variant"].items():
        lines.append(
            f"| {variant} | {data['n']} | {data['valid']} | {data['axiom_free']} | {data['sorry_used']} | "
            f"{data['fenced']} | {data['rc_lean_line_share_mean']} | {data['rc_tactic_line_share_mean']} | "
            f"{data['reasoning_tokens_sum']} | {data['completion_tokens_sum']} | {data['duration_s_sum']} |"
        )
    lines.extend(
        [
            "",
            "Hinweise: `valid` = elaboriert fehlerfrei (`leancheck`, Std-Minimalprojekt, Lean 4.33.1); "
            "`axiomfrei` = ohne Axiome unter den validen Zellen (`propext`/`Quot.sound` zaehlen nicht als "
            "axiomfrei); `Fence` = Antwort enthielt einen Markdown-Code-Zaun; `RC-Lean`/`RC-Taktik` sind die "
            "heuristischen `leanfidelity`-Anteile der Denkspur (Untergrenze bzw. ueberschaetzend bei "
            "zitierten Code-Zeilen in Prosa — Augenschein-Stichprobe im Bericht); n klein, keine Signifikanz.",
        ]
    )
    return "\n".join(lines)


def render_raw_table(results):
    """Markdown-Roh-Tabelle je Aufruf (deterministisch aus results.json)."""
    lines = [
        "# Lean-Mandat-Roh-Tabelle V19 (je Aufruf)",
        "",
        "| # | Variante | Aufgabe | Grad | rep | Status | Echo | Fence | Statement-Echo | RC-Zeilen | RC-Lean | RC-Taktik | Reasoning-Tok | Completion-Tok | Dauer s | Diagnose (Auszug) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, entry in enumerate(results, start=1):
        rc = entry.get("rc") or {}
        usage = entry.get("usage") or {}
        reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        lines.append(
            f"| {index} | {entry.get('variant')} | {entry.get('task')} | {entry.get('grade')} | {entry.get('rep')} | "
            f"{_entry_status(entry)} | {entry.get('prefill_echo')} | {entry.get('fenced')} | "
            f"{entry.get('statement_echo')} | {rc.get('lines', '')} | {rc.get('lean_line_share', '')} | "
            f"{rc.get('tactic_line_share', '')} | {reasoning_tokens} | {usage.get('completion_tokens', 0)} | "
            f"{entry.get('duration_s')} | {_cell_text(_entry_diagnostic(entry), 70)} |"
        )
    return "\n".join(lines)


def default_manifest():
    """Transport-Konfiguration fuer das Manifest (URL ohne Zugangsdaten)."""
    import harness  # gleicher Tooling-Ordner

    config = harness.target_config()
    return {
        "target": harness.target_name(),
        "url": harness.display_url(config["url"]),
        "model": config["model"],
        "max_tokens": harness.max_tokens(),
        "reasoning_effort": harness.reasoning_effort() or None,
    }


def run_matrix(
    call=None,
    check=None,
    variants=None,
    tasks=None,
    reps=3,
    timeout=300.0,
    lean_timeout=60.0,
    out_dir=None,
    manifest=None,
):
    """Die Matrix sequenziell; Ergebnisse + Aggregate unter ``out_dir``."""
    if call is None:
        import harness  # gleicher Tooling-Ordner

        call = harness.call_model
    if check is None:
        import leancheck  # gleicher Tooling-Ordner

        check = leancheck.check
    variant_ids = list(variants) if variants is not None else list(VARIANTS)
    task_list = list(tasks) if tasks is not None else list(TASKS)
    if manifest is None:
        manifest = default_manifest()
    if out_dir is None:
        out_dir = ROOT / ".yesmem" / "tmp" / "lean-mandat" / time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for variant_id in variant_ids:
        for task in task_list:
            for rep in range(1, reps + 1):
                messages = build_messages(variant_id, task)
                payload, _raw, duration, error = call(messages, timeout)
                entry = {
                    "variant": variant_id,
                    "task": task["id"],
                    "grade": task["grade"],
                    "rep": rep,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "duration_s": round(duration or 0.0, 2),
                    "error": error,
                    "usage": (payload or {}).get("usage", {}),
                    "answer": (payload or {}).get("content", "") if payload else "",
                    "reasoning": (payload or {}).get("reasoning", "") if payload else "",
                    "prefill_echo": None,
                    "continuation": "",
                    "fenced": False,
                    "code": None,
                    "statement_echo": False,
                    "rc": {},
                    "lean": None,
                }
                if payload is not None:
                    answer = entry["answer"]
                    if VARIANTS[variant_id]["prefill"]:
                        continuation, echoed = strip_prefill(answer, build_prefill(task))
                        entry["prefill_echo"] = echoed
                    else:
                        continuation = answer
                    entry["continuation"] = continuation
                    code, fenced = extract_code(answer)
                    entry["code"] = code
                    entry["fenced"] = fenced
                    entry["statement_echo"] = statement_echo(code, task["statement"])
                    entry["rc"] = _rc_metrics(entry["reasoning"])
                    if code:
                        entry["lean"] = check(
                            code,
                            timeout=lean_timeout,
                            print_axioms_for="main_thm" if "main_thm" in code else None,
                        )
                results.append(entry)
                (out_dir / f"{variant_id}-{task['id']}-r{rep}.json").write_text(
                    json.dumps(entry, indent=1, ensure_ascii=False), encoding="utf-8"
                )
                status = entry["error"] or (entry["lean"] or {}).get("status", "no_code")
                print(f"{variant_id} {task['id']} r{rep}: {status} ({entry['duration_s']}s)", flush=True)

    summary = summarize(results)
    (out_dir / "results.json").write_text(
        json.dumps({"manifest": manifest, "results": results, "summary": summary}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(render_summary(summary, results), encoding="utf-8")
    (out_dir / "raw.md").write_text(render_raw_table(results), encoding="utf-8")
    print(render_summary(summary, results))
    return {"manifest": manifest, "results": results, "summary": summary}


def exit_code(summary):
    """Exit-Code fuer die CLI: 1, sobald ein Transportfehler auftrat.

    ``invalid``/``timeout``/``no_code`` sind Messergebnisse (Daten), kein
    Werkzeug-Fehlschlag; Transportfehler dagegen schon. Akzeptiert das
    Gesamt-Aggregat oder die volle Zusammenfassung.
    """
    data = summary.get("overall", summary)
    return 1 if data.get("transport_errors") else 0


def _load_run(out_dir):
    payload = json.loads((Path(out_dir) / "results.json").read_text(encoding="utf-8"))
    return payload


def _select(parser, all_ids, raw, what):
    if not raw:
        return None
    wanted = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [part for part in wanted if part not in all_ids]
    if unknown:
        parser.error(f"unbekannte {what}: {', '.join(unknown)}")
    return wanted


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Matrix ausfuehren")
    run_parser.add_argument("--out", default=None)
    run_parser.add_argument("--reps", type=int, default=3)
    run_parser.add_argument("--variants", default=None, help="Komma-Liste, z. B. V-A,V-B")
    run_parser.add_argument("--tasks", default=None, help="Komma-Liste von Aufgaben-ids")
    run_parser.add_argument("--timeout", type=float, default=300.0, help="Sekunden je Modellaufruf")
    run_parser.add_argument("--lean-timeout", type=float, default=60.0, dest="lean_timeout")

    render_parser = sub.add_parser("render", help="Markdown-Assets aus results.json neu erzeugen")
    render_parser.add_argument("--run", required=True, help="Lauf-Verzeichnis mit results.json")
    render_parser.add_argument("--summary", default=None)
    render_parser.add_argument("--raw", default=None)

    args = parser.parse_args(argv)
    if args.command == "run":
        if args.reps < 1:
            parser.error("--reps muss >= 1 sein")
        variant_ids = _select(parser, list(VARIANTS), args.variants, "Varianten")
        task_ids = _select(parser, [task["id"] for task in TASKS], args.tasks, "Aufgaben")
        tasks = None if task_ids is None else [task for task in TASKS if task["id"] in task_ids]
        result = run_matrix(
            variants=variant_ids,
            tasks=tasks,
            reps=args.reps,
            timeout=args.timeout,
            lean_timeout=args.lean_timeout,
            out_dir=args.out,
        )
        return exit_code(result["summary"])
    out_dir = Path(args.run)
    payload = _load_run(out_dir)
    # Aggregate aus den Rohdaten neu berechnen: das gespeicherte Summary kann
    # nach einer Metrik-Korrektur veraltet sein, die Renderer bleiben so
    # deterministisch an der aktuellen Definition.
    summary = summarize(payload["results"])
    summary_path = Path(args.summary) if args.summary else out_dir / "summary.md"
    raw_path = Path(args.raw) if args.raw else out_dir / "raw.md"
    summary_path.write_text(render_summary(summary, payload["results"]), encoding="utf-8")
    raw_path.write_text(render_raw_table(payload["results"]), encoding="utf-8")
    print(f"geschrieben: {summary_path} · {raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

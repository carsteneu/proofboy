#!/usr/bin/env python3
"""Latent-Lean-Smoke-Test V18 — wie viel Lean steckt in den Weights?

16 kurze Sonden ("Schreibe Lean-4-Code, der <kleine Aussage> als Theorem
``main_thm`` beweist") gehen direkt an das Modell (kein Arm, kein Blatt);
der extrahierte Code wird mit :mod:`leancheck` im Std-Minimalprojekt
elaboriert. Gemessen wird deskriptiv: Anteil elaborierender Antworten
(``valid``), davon axiomfrei (``axioms == "none"``), ``sorry``-Nutzung und
Transportfehler. Jede Sonde ist mit dem Std-Referenzbeweis validiert (siehe
Probe-Liste, ``ref_tactic``).

Die Aussagen sind bewusst Std-tauglich formuliert (``Nat`` statt ``ℕ``; kein
``Nat.factorial`` -- ohne Mathlib gibt es beides nicht) und ohne
Mathlib-only-Taktiken als Vorgabe.

Aufruf::

    python3 lean_smoke.py [--out .yesmem/tmp/lean-smoke/<ts>] [--timeout 300]
                          [--lean-timeout 60] [--probes p01,p02]
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

SYSTEM = "Du bist ein Lean-4-Experte."
PROMPT_TEMPLATE = (
    "Schreibe Lean-4-Code, der diese Aussage als Theorem `main_thm` beweist:\n\n"
    "  {statement}\n\n"
    "Vorgaben: erste Zeile `import Std`, Theoremname `main_thm`, keine weiteren "
    "Imports. Antworte ausschliesslich mit dem Lean-Code (keine Erklaerung, kein "
    "Markdown)."
)

# Jede Sonde: Std-validierte Aussage + Referenz-Taktik (probe-reference-Asset).
PROBES = [
    {"id": "p01", "statement": "2 + 2 = 4", "ref_tactic": "decide"},
    {"id": "p02", "statement": "10 * 10 = 100", "ref_tactic": "decide"},
    {"id": "p03", "statement": "29 * 31 = 899", "ref_tactic": "decide"},
    {"id": "p04", "statement": "123456789 + 987654321 = 1111111110", "ref_tactic": "decide"},
    {"id": "p05", "statement": "837465291837 + 192837465564 = 1030302757401", "ref_tactic": "decide"},
    {"id": "p06", "statement": "2 ^ 10 = 1024", "ref_tactic": "decide"},
    {"id": "p07", "statement": "(2 ^ 10) % 7 = 2", "ref_tactic": "decide"},
    {"id": "p08", "statement": "7 * 11 * 13 = 1001", "ref_tactic": "decide"},
    {"id": "p09", "statement": "Nat.gcd 12 18 = 6", "ref_tactic": "decide"},
    {"id": "p10", "statement": "[1,2,3].length = 3", "ref_tactic": "decide"},
    {"id": "p11", "statement": "∀ n : Nat, n + 0 = n", "ref_tactic": "simp"},
    {"id": "p12", "statement": "∀ n : Nat, 0 + n = n", "ref_tactic": "simp"},
    {"id": "p13", "statement": "∀ n : Nat, n * 1 = n", "ref_tactic": "simp"},
    {"id": "p14", "statement": "∀ a b : Nat, a + b = b + a", "ref_tactic": "omega"},
    {"id": "p15", "statement": "∀ n : Nat, n < n + 1", "ref_tactic": "omega"},
    {"id": "p16", "statement": "∀ n : Nat, 2 * n = n + n", "ref_tactic": "omega"},
]

# Dieselbe Extraktion wie harness.extract_sheet_text: groesster Zaun-Block,
# sonst der volle Text.
FENCE_RE = re.compile(r"```[a-zA-Z0-9]*\n(.*?)```", flags=re.DOTALL)


def extract_lean_code(answer):
    """Der Lean-Code einer Antwort: groesster ```-Block, sonst der volle Text."""
    fences = FENCE_RE.findall(answer or "")
    if fences:
        return max(fences, key=len).strip()
    return (answer or "").strip()


def build_prompt(probe):
    return PROMPT_TEMPLATE.format(statement=probe["statement"])


def summarize(results):
    """Deskriptive Zaehlung ueber alle Sonden (keine Signifikanzaussagen)."""
    counts = {"valid": 0, "invalid": 0, "timeout": 0, "infra_error": 0}
    no_code = 0
    axiom_free = 0
    sorry_used = 0
    transport_errors = 0
    reasoning_tokens = 0
    completion_tokens = 0
    duration = 0.0
    for entry in results:
        if entry.get("error"):
            transport_errors += 1
        usage = entry.get("usage") or {}
        reasoning_tokens += (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        completion_tokens += usage.get("completion_tokens", 0)
        duration += entry.get("duration_s") or 0.0
        lean = entry.get("lean")
        if lean is None:
            no_code += 1
            continue
        status = lean.get("status")
        if status in counts:
            counts[status] += 1
        if lean.get("axioms") == "none":
            axiom_free += 1
        if lean.get("sorry_used"):
            sorry_used += 1
    n = len(results)
    return {
        "n": n,
        **counts,
        "no_code": no_code,
        "transport_errors": transport_errors,
        "axiom_free": axiom_free,
        "sorry_used": sorry_used,
        "valid_frac": round(counts["valid"] / n, 4) if n else 0.0,
        "reasoning_tokens_sum": reasoning_tokens,
        "completion_tokens_sum": completion_tokens,
        "duration_s_sum": round(duration, 1),
    }


def render_summary(summary, results):
    lines = [
        "# Latent-Lean-Smoke-Test (V18, deskriptiv)",
        "",
        f"- Sonden: {summary['n']} · valid {summary['valid']} ({summary['valid_frac']}) · "
        f"axiomfrei {summary['axiom_free']} · sorry {summary['sorry_used']} · "
        f"invalid {summary['invalid']} · timeout {summary['timeout']} · ohne Code {summary['no_code']} · "
        f"Transportfehler {summary['transport_errors']}",
        f"- Tokens: reasoning {summary['reasoning_tokens_sum']} · completion {summary['completion_tokens_sum']} · "
        f"Dauer {summary['duration_s_sum']} s",
        "",
        "| Sonde | Aussage | Modell: Status | Axiome | Fehler (Auszug) |",
        "|---|---|---|---|---|",
    ]
    for entry in results:
        lean = entry.get("lean")
        if entry.get("error"):
            status = "transport_error"
        elif lean is None:
            status = "no_code"
        else:
            status = lean.get("status", "?")
        axioms = (lean or {}).get("axioms")
        errors = (lean or {}).get("errors") or []
        excerpt = errors[0]["message"][:60] if errors else ""
        lines.append(f"| {entry['id']} | `{entry['statement']}` | {status} | {axioms} | {excerpt} |")
    lines.append("")
    lines.append(
        "Hinweise: eine Sonde, eine Modellantwort, eine Elaboration (kein Reparaturpfad); "
        "`valid` = elaboriert fehlerfrei, `axiomfrei` = ohne Axiome (decide-Beweise), "
        "`propext/Quot.sound` gelten als Standard-Axiome (simp/omega). n klein, deskriptiv."
    )
    return "\n".join(lines)


def run_probes(call=None, check=None, probes=None, timeout=300.0, lean_timeout=60.0, out_dir=None):
    """Alle Sonden sequenziell; Ergebnisse + Zusammenfassung unter ``out_dir``."""
    if call is None:
        import harness  # gleicher Tooling-Ordner

        call = harness.call_model
    if check is None:
        import leancheck  # gleicher Tooling-Ordner

        check = leancheck.check
    probes = probes if probes is not None else PROBES
    if out_dir is None:
        out_dir = ROOT / ".yesmem" / "tmp" / "lean-smoke" / time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for probe in probes:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(probe)},
        ]
        payload, _raw, duration, error = call(messages, timeout)
        entry = {
            "id": probe["id"],
            "statement": probe["statement"],
            "ref_tactic": probe.get("ref_tactic"),
            "duration_s": round(duration or 0.0, 2),
            "error": error,
            "usage": (payload or {}).get("usage", {}),
            "answer": (payload or {}).get("content", "") if payload else "",
            "reasoning": (payload or {}).get("reasoning", "") if payload else "",
            "code": None,
            "lean": None,
        }
        if error is None and payload is not None:
            code = extract_lean_code(payload.get("content"))
            entry["code"] = code
            if code:
                entry["lean"] = check(
                    code,
                    timeout=lean_timeout,
                    print_axioms_for="main_thm" if "main_thm" in code else None,
                )
        results.append(entry)
        (out_dir / f"{probe['id']}.json").write_text(
            json.dumps(entry, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        status = entry["error"] or (entry["lean"] or {}).get("status", "no_code")
        print(f"{probe['id']}: {status} ({entry['duration_s']}s)", flush=True)

    summary = summarize(results)
    (out_dir / "results.json").write_text(
        json.dumps({"results": results, "summary": summary}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown = render_summary(summary, results)
    (out_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return {"results": results, "summary": summary}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=None)
    parser.add_argument("--timeout", type=float, default=300.0, help="Sekunden je Modellaufruf")
    parser.add_argument("--lean-timeout", type=float, default=60.0, dest="lean_timeout")
    parser.add_argument("--probes", default=None, help="Komma-Liste von Sonden-ids")
    args = parser.parse_args(argv)
    probes = None
    if args.probes:
        wanted = {part.strip() for part in args.probes.split(",") if part.strip()}
        probes = [probe for probe in PROBES if probe["id"] in wanted]
        if not probes:
            parser.error(f"keine bekannten Sonden in {args.probes!r}")
    run_probes(probes=probes, timeout=args.timeout, lean_timeout=args.lean_timeout, out_dir=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

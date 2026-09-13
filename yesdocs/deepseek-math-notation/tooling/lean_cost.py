#!/usr/bin/env python3
"""Token-Kosten-Sonde V18 — Lean-Zeile vs. V1.1-Zeile vs. Prosa-Zeile.

Misst mit dem DeepSeek-Tokenizer (``tokenizer.json``, SHA-256
``c90dfa01…`` wie in 01-03b) die Tokenkosten gleichbedeutender Zeilen in drei
Stilen:

- **lean**  — Lean-4-Taktik-/Statementzeile (``have … := by decide``, ``exact``)
- **v11**   — V1.1-Denkzeile (Tag-Kopf + kompakter Rumpf, wie in den Läufen)
- **prose** — deutsche/englische Prosa-Zeile ("aufgaben-gleichbedeutend")

Grenzen (bewusst): gemessen wird je Zeile ohne BOS/Serving-Kontext; für
Trace-/Zyklus-Aussagen gibt es keine Std-Lean-Formalisierung, dort ist die
Lean-Zeile eine Kommentar-Skizze (als solche gekennzeichnet). Die Prosa-Zeilen
sind kurze, gleichwertige Einzelsätze — keine Gewichtung nach Satzlänge.

Aufruf (tokenizers-Bibliothek liegt projektlokal, kein pip auf der Maschine)::

    python3 lean_cost.py [--tokenizer .yesmem/tmp/tokenizer/tokenizer.json]
                         [--pylibs .yesmem/tmp/pylibs] [--json out.json] [--markdown out.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # yesdocs/deepseek-math-notation/tooling -> repo root

DEFAULT_TOKENIZER = ROOT / ".yesmem" / "tmp" / "tokenizer" / "tokenizer.json"
DEFAULT_PYLIBS = ROOT / ".yesmem" / "tmp" / "pylibs"

# Die Item-Liste ist der Inhalt der Sonde: je Zeile dieselbe Aussage in drei
# Stilen. Lean-Zeilen sind, wo möglich, echte Std-Lean-4-Formen; fuer Trace-/
# Zyklus-Aussagen steht eine Kommentar-Skizze (kein Std-Aequivalent).
ITEMS = [
    {
        "id": "sum-klein",
        "lean": "have h1 : 2 + 2 = 4 := by decide",
        "v11": "c: 2+2=4",
        "prose": "Two plus two equals four.",
    },
    {
        "id": "sum-gross",
        "lean": "have h1 : 837465291837 + 192837465564 = 1030302757401 := by decide",
        "v11": "=: 837465291837+192837465564=1030302757401",
        "prose": "The sum of 837465291837 and 192837465564 is 1030302757401.",
    },
    {
        "id": "produkt",
        "lean": "have h2 : 29 * 31 = 899 := by decide",
        "v11": "=: 29*31=899",
        "prose": "29 times 31 equals 899.",
    },
    {
        "id": "modulo",
        "lean": "have h3 : (2 ^ 10) % 1000 = 24 := by decide",
        "v11": "=: ((2^10)%1000)=24",
        "prose": "2 to the power of 10 modulo 1000 is 24.",
    },
    {
        "id": "teilbarkeit",
        "lean": "have h4 : 3 ∣ 12 := ⟨4, rfl⟩",
        "v11": "a: di(3,12)",
        "prose": "3 divides 12.",
    },
    {
        "id": "forall-null",
        "lean": "have h5 : ∀ n : ℕ, n + 0 = n := by intro n; rfl",
        "v11": "h5: (forall n: (n+0=n))",
        "prose": "For every number n we have n plus 0 equals n.",
    },
    {
        "id": "forall-schranke",
        "lean": "have h6 : ∀ n : ℕ, n < n + 1 := by intro n; omega",
        "v11": "h6: (forall n: (n<n+1))",
        "prose": "Every number is smaller than itself plus one.",
    },
    {
        "id": "liste-summe",
        "lean": "have h7 : ([1,2,3,4,5].sum = 15) := by decide",
        "v11": "=: sum(1..5)=15",
        "prose": "The sum of the numbers one through five is fifteen.",
    },
    {
        "id": "trace-checkpoint",
        "lean": "-- checkpoint 10: (B, 1, 1101)",
        "v11": "h2: cp 10: (B,1,1101)",
        "prose": "After step 10 the machine is in state B, head at 1, tape 1101.",
    },
    {
        "id": "zyklus",
        "lean": "-- cycle translation: t1=6, t2=16, d=2",
        "v11": "v h1: cyc(6,16,2)",
        "prose": "The machine does not halt; it cycles with t1=6, t2=16 and shift d=2.",
    },
]

STYLES = ("lean", "v11", "prose")


def load_tokenizer(tokenizer_path=DEFAULT_TOKENIZER, pylibs=DEFAULT_PYLIBS):
    """Laedt den HF-Tokenizer; die Bibliothek kommt per PYTHONPATH-Insertion."""
    pylibs = Path(pylibs)
    if pylibs.exists() and str(pylibs) not in sys.path:
        sys.path.insert(0, str(pylibs))
    from tokenizers import Tokenizer  # noqa: E402 — bewusst erst nach sys.path

    return Tokenizer.from_file(str(tokenizer_path))


def measure(tok, items=ITEMS):
    """Token-/Zeichenkosten je Stil und Zeile (``tok.encode`` duck-typed)."""
    rows = []
    for item in items:
        row = {"id": item["id"]}
        for style in STYLES:
            text = item[style]
            encoding = tok.encode(text)
            row[f"{style}_tokens"] = len(encoding.ids)
            row[f"{style}_chars"] = len(text)
        row["lean_vs_prose"] = round(row["lean_tokens"] / row["prose_tokens"], 3) if row["prose_tokens"] else None
        row["v11_vs_prose"] = round(row["v11_tokens"] / row["prose_tokens"], 3) if row["prose_tokens"] else None
        rows.append(row)
    return rows


def summarize(rows):
    """Summen und Gesamtverhaeltnisse je Stil."""
    totals = {style: sum(row[f"{style}_tokens"] for row in rows) for style in STYLES}
    ratios = {
        "lean_vs_prose": round(totals["lean"] / totals["prose"], 3) if totals["prose"] else None,
        "v11_vs_prose": round(totals["v11"] / totals["prose"], 3) if totals["prose"] else None,
        "lean_vs_v11": round(totals["lean"] / totals["v11"], 3) if totals["v11"] else None,
    }
    return {"totals": totals, "ratios": ratios, "n_items": len(rows)}


def render_markdown(rows, summary):
    lines = [
        "# Token-Kosten-Sonde V18: Lean-Zeile vs. V1.1-Zeile vs. Prosa-Zeile",
        "",
        f"- tokenizer.json SHA-256 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b` · {summary['n_items']} Zeilen-Tripel",
        "",
        "| Zeile | lean | v1.1 | prosa | lean/prosa | v1.1/prosa |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['lean_tokens']} | {row['v11_tokens']} | {row['prose_tokens']} "
            f"| {row['lean_vs_prose']} | {row['v11_vs_prose']} |"
        )
    lines.append(
        f"| **Σ** | **{summary['totals']['lean']}** | **{summary['totals']['v11']}** "
        f"| **{summary['totals']['prose']}** | **{summary['ratios']['lean_vs_prose']}** "
        f"| **{summary['ratios']['v11_vs_prose']}** |"
    )
    lines.append("")
    lines.append(
        "Hinweise: je Zeile dieselbe Aussage in drei Stilen; Lean-Zeilen sind Std-Formen, "
        "Trace-/Zyklus-Zeilen eine Kommentar-Skizze (kein Std-Aequivalent); gemessen ohne "
        "BOS/Serving-Kontext. Deskriptiv, keine Signifikanzaussagen."
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tokenizer", default=str(DEFAULT_TOKENIZER))
    parser.add_argument("--pylibs", default=str(DEFAULT_PYLIBS))
    parser.add_argument("--json", default=None)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args(argv)
    tok = load_tokenizer(args.tokenizer, args.pylibs)
    rows = measure(tok)
    summary = summarize(rows)
    markdown = render_markdown(rows, summary)
    print(markdown)
    if args.json:
        Path(args.json).write_text(
            json.dumps({"items": rows, "summary": summary}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

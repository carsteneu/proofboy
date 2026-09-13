#!/usr/bin/env python3
"""Lean-Fidelity (V18, Metrik h_lean) — Parser fuer Taktik-zeilenfoermige Denkspuren.

Was die Metrik misst (heuristisch, ehrlich als Heuristik ausgewiesen):

- **Zeilenklassen**: Taktik-Zeilen (erste Wortmarke ist ein Lean-Taktik-
  Schluesselwort: ``have/apply/exact/rw/simp/omega/linarith/decide/...``,
  auch mit angehaengter Klammer wie ``rw[h2]``), Statement-Zeilen
  (``theorem/lemma/example/import/...`` oder eine ``:=``-Bindung),
  Kommentar-Zeilen (``--``) und Prosa (alles andere). Leere Zeilen zaehlen
  nicht.
- **Anteile**: ``lean_line_share`` = (Taktik- + Statement- + Kommentar-Zeilen)/
  Zeilen; ``tactic_line_share`` = Taktik-Zeilen/Zeilen; ``lean_char_share`` =
  Zeichen der Lean-Zeilen / Zeichen aller Zeilen (dokumentierter Proxy ohne
  Tokenizer; unterschaetzt tendenziell, weil Prosa-Leerzeichen zusaetzliche
  Token-Kosten tragen).
- **Degeneration**: identische Zeilenlaeufe (>= 3), laengste Zeile, laengster
  Prosa-Lauf; ``trailing_lean_block`` = zusammenhaengender Lean-Block am Ende
  (Blatt-Entwurf in der Denkspur).
- **Bewusste Untergrenze**: nackte Formeln ohne Lean-Schluesselwort zaehlen
  als Prosa; die Erkennung ist ein linearer Scanner (kein Regex-Backtracking).

Aufruf::

    python3 leanfidelity.py --runs .yesmem/tmp/runs/<ts> [--json out.json] [--markdown out.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# Die Taktik-/Statement-Listen sind der heuristische Kern der Metrik: eine
# erste Wortmarke aus diesen Mengen (oder eine ``:=``-Bindung) macht eine
# Zeile zur Lean-Zeile. Erweiterungen aendern die Metrik -- bewusst hier
# zentral, damit Tests und Bericht dieselbe Liste zitieren.
TACTIC_KEYWORDS = frozenset(
    {
        "have", "apply", "exact", "rw", "simp", "simpa", "omega", "linarith", "nlinarith",
        "decide", "norm_num", "native_decide", "induction", "cases", "rcases", "obtain",
        "intro", "intros", "refine", "calc", "constructor", "use", "subst", "ring",
        "field_simp", "positivity", "interval_cases", "fin_cases", "contradiction", "exfalso",
        "push_neg", "contrapose", "by_contra", "specialize", "dsimp", "unfold", "assumption",
        "trivial", "rfl", "exact_mod_cast", "norm_cast", "gcongr", "haveI", "let", "suffices",
        "show", "revert", "generalize", "clear", "rename", "repeat", "all_goals", "first",
        "try", "split", "left", "right", "ext", "funext", "aesop", "tauto", "by_cases",
        "by_contradiction", "classical", "convert", "eapply", "erw", "fapply", "finish",
        "funext", "injection", "linarith!", "nlinarith", "push_cast", "qify", "rw_mod_cast",
        "squeeze_simp", "trans", "type_check", "wlog", "zify", "sorry",
    }
)
STATEMENT_KEYWORDS = frozenset(
    {
        "theorem", "lemma", "example", "def", "abbrev", "structure", "instance", "class",
        "import", "open", "namespace", "end", "section", "variable", "variables", "axiom",
        "noncomputable", "private", "protected", "scoped", "local", "notation", "infix",
        "prefix", "postfix", "macro", "syntax", "elab", "deriving", "where", "mutual",
        "inductive", "opaque", "alias", "attribute", "set_option",
    }
)
COMMENT_PREFIX = "--"
BINDING = ":="
REPEAT_MIN_RUN = 3
LEAN_KINDS = ("tactic", "statement", "comment")


def _line_kind(line):
    """``"tactic" | "statement" | "comment" | "prose"`` (heuristisch, linear)."""
    if line.startswith(COMMENT_PREFIX):
        return "comment"
    head = line.split(maxsplit=1)[0]
    if head.endswith(":") and len(head) > 1:
        head = head[:-1]
    if head in TACTIC_KEYWORDS:
        return "tactic"
    if head in STATEMENT_KEYWORDS:
        return "statement"
    # Wortgrenze: ``rw[h2]``/``simp?`` zaehlen, ``user``/``extend`` nicht.
    for keyword in TACTIC_KEYWORDS:
        if head.startswith(keyword) and len(head) > len(keyword) and not head[len(keyword)].isalpha():
            return "tactic"
    if BINDING in line:
        return "statement"
    return "prose"


def parse_lean_text(text):
    """Die Lean-Fidelity-Metriken eines Textes (Denkspur oder sichtbare Zone)."""
    lines = [line.strip() for line in (text or "").splitlines()]
    non_empty = [line for line in lines if line]

    counts = {"tactic_lines": 0, "statement_lines": 0, "comment_lines": 0, "prose_lines": 0}
    chars = {key: 0 for key in counts}
    kinds = []
    for line in non_empty:
        kind = _line_kind(line)
        kinds.append(kind)
        key = {
            "tactic": "tactic_lines",
            "statement": "statement_lines",
            "comment": "comment_lines",
            "prose": "prose_lines",
        }[kind]
        counts[key] += 1
        chars[key] += len(line)

    total_lines = len(non_empty)
    total_chars = sum(len(line) for line in non_empty)

    repeat_extra = 0
    index = 0
    while index < len(non_empty):
        following = index + 1
        while following < len(non_empty) and non_empty[following] == non_empty[index]:
            following += 1
        run_length = following - index
        if run_length >= REPEAT_MIN_RUN:
            repeat_extra += run_length - 1
        index = following

    prose_run_max = 0
    lean_run_max = 0
    current_prose = 0
    current_lean = 0
    for kind in kinds:
        if kind == "prose":
            current_prose += 1
            prose_run_max = max(prose_run_max, current_prose)
            current_lean = 0
        else:
            current_lean += 1
            lean_run_max = max(lean_run_max, current_lean)
            current_prose = 0

    first_lean_index = next(
        (position for position, kind in enumerate(kinds) if kind in LEAN_KINDS), None
    )
    trailing_lean_block = 0
    for kind in reversed(kinds):
        if kind in LEAN_KINDS:
            trailing_lean_block += 1
        else:
            break

    lean_lines = sum(counts[key] for key in ("tactic_lines", "statement_lines", "comment_lines"))
    lean_chars = sum(chars[key] for key in ("tactic_lines", "statement_lines", "comment_lines"))

    def share(part, whole):
        return round(part / whole, 4) if whole else 0.0

    return {
        "chars": total_chars,
        "lines": total_lines,
        **counts,
        "lean_line_share": share(lean_lines, total_lines),
        "tactic_line_share": share(counts["tactic_lines"], total_lines),
        "lean_char_share": share(lean_chars, total_chars),
        "first_lean_line_index": first_lean_index,
        "first_lean_line_frac": (
            round(first_lean_index / total_lines, 4)
            if first_lean_index is not None and total_lines
            else None
        ),
        "trailing_lean_block": trailing_lean_block,
        "lean_run_max": lean_run_max,
        "prose_run_max": prose_run_max,
        "repeat_extra": repeat_extra,
        "longest_line_len": max((len(line) for line in non_empty), default=0),
    }


def _read_round_texts(raw_path):
    """(reasoning_content, content) einer Runde -- fail-safe ``(None, None)``.

    Jede unlesbare/korrupte Datei zaehlt als fehlende Denkspur (rc_missing)
    statt die Auswertung abzubrechen; ein leerer String gilt als leere Spur.
    """
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        message = payload["choices"][0]["message"]
        if not isinstance(message, dict):
            return None, None
        reasoning = message.get("reasoning_content")
        if reasoning is None or not isinstance(reasoning, str):
            return None, None
        content = message.get("content")
        if not isinstance(content, str):
            content = ""
        return reasoning, content
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        return None, None


def _mean(values):
    return round(sum(values) / len(values), 4) if values else 0.0


def analyze_runs(root):
    """Lean-Fidelity je Runde eines Lauf-Baums (evaluate-Layout)."""
    from evaluate import load_runs  # gleicher Tooling-Ordner; lazy fuer Standalone-Parsing

    root = Path(root)
    manifest, runs = load_runs(root)
    per_run = []
    for run in runs:
        summary = run["summary"]
        if summary is None:
            continue  # Legacy-Flachlayout (V11): kein per-Runde raw.json
        run_dir = Path(run["path"]).parent
        for round_index, row in enumerate(summary.get("rounds", [])):
            raw_path = run_dir / f"round{round_index}" / "raw.json"
            rc, answer = _read_round_texts(raw_path) if raw_path.exists() else (None, None)
            entry = {
                "task_id": summary.get("task_id"),
                "arm": summary.get("arm"),
                "tier": summary.get("tier"),
                "rep": summary.get("rep"),
                "round": round_index,
                "solved": bool(row.get("solved")),
                "reasoning_tokens": row.get("reasoning_tokens", 0),
                "completion_tokens": row.get("completion_tokens", 0),
                "rc_missing": rc is None,
            }
            if rc is not None:
                entry.update({f"rc_{key}": value for key, value in parse_lean_text(rc).items()})
            entry.update(
                {f"answer_{key}": value for key, value in parse_lean_text(answer or "").items()}
            )
            per_run.append(entry)

    groups = {}
    for entry in per_run:
        groups.setdefault(f"{entry['arm']}-{entry['tier']}", []).append(entry)

    per_arm = {}
    for key, rows in sorted(groups.items()):
        with_rc = [row for row in rows if not row["rc_missing"]]
        with_answer = [row for row in rows if "answer_lean_line_share" in row]
        per_arm[key] = {
            "arm": rows[0]["arm"],
            "tier": rows[0]["tier"],
            "n_rounds": len(rows),
            "n_rc": len(with_rc),
            "rc_missing": len(rows) - len(with_rc),
            "rc_lean_line_share_mean": _mean([row["rc_lean_line_share"] for row in with_rc]),
            "rc_tactic_line_share_mean": _mean([row["rc_tactic_line_share"] for row in with_rc]),
            "rc_lean_char_share_mean": _mean([row["rc_lean_char_share"] for row in with_rc]),
            "rc_tactic_lines_sum": sum(row["rc_tactic_lines"] for row in with_rc),
            "rc_trailing_lean_block_mean": _mean(
                [row["rc_trailing_lean_block"] for row in with_rc]
            ),
            "rc_prose_run_max_mean": _mean([row["rc_prose_run_max"] for row in with_rc]),
            "rc_repeat_extra_sum": sum(row["rc_repeat_extra"] for row in with_rc),
            "rc_longest_line_max": max(
                (row["rc_longest_line_len"] for row in with_rc), default=0
            ),
            "answer_lean_line_share_mean": _mean(
                [row["answer_lean_line_share"] for row in with_answer]
            ),
            "reasoning_tokens_sum": sum(row["reasoning_tokens"] for row in rows),
            "reasoning_tokens_mean": round(
                sum(row["reasoning_tokens"] for row in rows) / len(rows), 1
            ),
            "completion_tokens_sum": sum(row["completion_tokens"] for row in rows),
        }
    return {
        "root": str(root),
        "manifest": {
            key: manifest.get(key)
            for key in ("started", "model", "arms", "reps", "tasks")
        },
        "per_run": per_run,
        "per_arm": per_arm,
    }


def render_markdown(report):
    lines = [
        "# Lean-Fidelity der Denkspur (Metrik h_lean, deskriptiv)",
        "",
        f"- Wurzel: {report['root']} · Modell: {report['manifest'].get('model') or '?'}",
        "",
        "| Arm-Tier | Runden | RC da | Lean-Zeilen ø (RC) | davon Taktik ø | Lean-Zeichen ø (Proxy) | Taktik-Zeilen Σ | Prosa-Lauf max ø | Draft-Block ø | sichtbar: Lean-Zeilen ø | Reasoning-Tokens Σ | Ø/Runde |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in report["per_arm"].values():
        lines.append(
            "| {key} | {n} | {rc} | {ll} | {tl} | {lc} | {ts} | {pr} | {tb} | {al} | {tok} | {tokm} |".format(
                key=f"{entry['arm']}-{entry['tier']}",
                n=entry["n_rounds"],
                rc=entry["n_rc"],
                ll=entry["rc_lean_line_share_mean"],
                tl=entry["rc_tactic_line_share_mean"],
                lc=entry["rc_lean_char_share_mean"],
                ts=entry["rc_tactic_lines_sum"],
                pr=entry["rc_prose_run_max_mean"],
                tb=entry["rc_trailing_lean_block_mean"],
                al=entry["answer_lean_line_share_mean"],
                tok=entry["reasoning_tokens_sum"],
                tokm=entry["reasoning_tokens_mean"],
            )
        )
    lines.append("")
    lines.append(
        "Hinweise: `Lean-Zeilen` = (Taktik- + Statement- + Kommentar-Zeilen)/Zeilen "
        "(heuristisch; nackte Formeln ohne Schluesselwort zaehlen als Prosa, die "
        "Metrik ist eine Untergrenze); `Lean-Zeichen` ist der dokumentierte "
        "Zeichen-Proxy; `Draft-Block` = zusammenhaengender Lean-Block am RC-Ende. "
        "Keine Signifikanzaussagen."
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--json", default=None)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args(argv)
    report = analyze_runs(args.runs)
    markdown = render_markdown(report)
    print(markdown)
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

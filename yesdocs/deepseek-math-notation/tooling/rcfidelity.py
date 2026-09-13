#!/usr/bin/env python3
"""RC-Fidelity der Denkspur (V15, Metrik h) — Parser fuer ``reasoning_content``.

Was die Metrik misst (heuristisch, ehrlich als Heuristik ausgewiesen):

- **Zeilenklassen**: V1.1-Tag-Zeilen (``g: d: a: c: h: v: q: =:`` mit
  optionaler Ziffer), v-Zeilen (``v<n> <ziel>:``), Status-Mini-Zeilen
  (``<id><+/-/?/!>``), V1-Altzeilen (``S<n>:``), Claim-Zeilen
  (``CLAIM``/``WITNESS``/``[HALT]`` -- der Blatt-Entwurf im RC) und Prosa
  (alles andere).
- **Anteile**: ``tag_line_share`` = (Tag- + v-Zeilen)/Zeilen;
  ``notation_line_share`` zusaetzlich mit Statuszeilen;
  ``notation_char_share`` = Zeichen der Notationszeilen / Zeichen aller
  Zeilen. Token-genaue Anteile braeuchten den Modell-Tokenizer (lokal nicht
  vorhanden) -- der Zeichenanteil ist der dokumentierte Proxy; er
  *unterschaetzt* die Notation, weil Prosa-Leerzeichen zusaetzliche
  Token-Kosten tragen.
- **Degeneration**: leere Tag-Koepfe (``g:`` ohne Inhalt), identische
  Zeilenlaeufe (>= 3), laengste Zeile, laengster Prosa-Lauf.
- **Bekannter Konfund**: der Blatt-Entwurf in der Denkspur traegt gueltige
  V1.1-Zeilen (auch die Claim-Zone CLAIM/WITNESS/[HALT]); der
  ``trailing_notation_block`` misst den zusammenhaengenden
  Notation-/Claim-Block am RC-Ende, damit der Draft-Anteil von echter
  Denkspur-Notation unterscheidbar bleibt.

Hinweis zur Grammatik: die Status-/v-Zeilen-Erkennung ist eine bewusst
laxe Heuristik (Status-id: Ziffer irgendwo; v-Zeile: ``v<n> <ziel>:`` ohne
Zeugentext-Pflicht) und damit weiter als der Blatt-Parser; in den
V13/V15-Rohdaten traten keine abweichenden Zeilen auf.

Kein Regex-Backtracking: die Kopf-Erkennung ist ein linearer Scanner
(ReDoS-Lehre; V13-Security-Review).

Aufruf::

    python3 rcfidelity.py --runs .yesmem/tmp/runs/<ts> [--json out.json] [--markdown out.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

TAG_CHARS = "gdachq="
STATUS_SUFFIX = "+-?!"
CLAIM_PREFIXES = ("CLAIM ", "WITNESS ", "[HALT]")
REPEAT_MIN_RUN = 3
NOTATION_KINDS = ("tag", "v")
# Der Blatt-Entwurf endet mit der Claim-Zone (CLAIM/WITNESS/[HALT]) — ohne
# die Claim-Zeilen waere ein vollstaendig notationisches RC unsichtbar.
TRAILING_BLOCK_KINDS = ("tag", "v", "status", "claim")


def _head_kind(line):
    """The V1.1 head kind of one line ("g".."=", "v") or None.

    Linear scanner with early exits; the tag registry is fixed in
    :data:`TAG_CHARS`, the v-line form is ``v<n> <ziel>:``.
    """
    if not line:
        return None
    first = line[0]
    if first in TAG_CHARS:
        index = 1
        while index < len(line) and line[index].isdigit():
            index += 1
        if index < len(line) and line[index] == ":":
            return first
        return None
    if first == "v":
        index = 1
        while index < len(line) and line[index].isdigit():
            index += 1
        if index >= len(line) or line[index] not in " \t":
            return None
        rest = line[index + 1 :].lstrip(" \t")
        target = 0
        while target < len(rest) and (rest[target].isalnum() or rest[target] in "=_"):
            target += 1
        if target == 0:
            return None
        cursor = target
        while cursor < len(rest) and rest[cursor] in " \t":
            cursor += 1
        if cursor < len(rest) and rest[cursor] == ":":
            return "v"
    return None


def _is_status_line(line):
    """``<id><+/-/?/!>`` with at least one digit in the id (V1.1 status)."""
    if len(line) < 2 or line[-1] not in STATUS_SUFFIX:
        return False
    body = line[:-1]
    if not body or not body[0].isalpha() and body[0] != "=":
        return False
    has_digit = False
    for char in body:
        if char.isdigit():
            has_digit = True
        elif not char.isalnum() and char != "=":
            return False
    return has_digit


def _is_legacy_s_line(line):
    """``S<n>:`` — the V1 thinking-zone head (altzeilen, not V1.1)."""
    if not line.startswith("S"):
        return False
    index = 1
    while index < len(line) and line[index].isdigit():
        index += 1
    return index > 1 and index < len(line) and line[index] == ":"


def _classify(line):
    kind = _head_kind(line)
    if kind is not None:
        return "v" if kind == "v" else "tag"
    if _is_status_line(line):
        return "status"
    if _is_legacy_s_line(line):
        return "legacy"
    if line.startswith(CLAIM_PREFIXES):
        return "claim"
    return "prose"


def _tag_body(line):
    """The body of a tag-headed line (text after the first colon)."""
    _, _, body = line.partition(":")
    return body.strip()


def parse_rc(text):
    """The RC-fidelity metrics of one reasoning text (heuristic parser)."""
    lines = [line.strip() for line in (text or "").splitlines()]
    non_empty = [line for line in lines if line]

    counts = {
        "tag_lines": 0,
        "v_lines": 0,
        "status_lines": 0,
        "legacy_s_lines": 0,
        "claim_lines": 0,
        "prose_lines": 0,
    }
    chars = {key: 0 for key in counts}
    empty_tag_lines = 0
    kinds = []
    for line in non_empty:
        kind = _classify(line)
        kinds.append(kind)
        key = {
            "tag": "tag_lines",
            "v": "v_lines",
            "status": "status_lines",
            "legacy": "legacy_s_lines",
            "claim": "claim_lines",
            "prose": "prose_lines",
        }[kind]
        counts[key] += 1
        chars[key] += len(line)
        if kind == "tag" and not _tag_body(line):
            empty_tag_lines += 1

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
    current = 0
    for kind in kinds:
        if kind == "prose":
            current += 1
            prose_run_max = max(prose_run_max, current)
        else:
            current = 0

    first_notation_index = next(
        (position for position, kind in enumerate(kinds) if kind in NOTATION_KINDS),
        None,
    )
    trailing_notation_block = 0
    for kind in reversed(kinds):
        if kind in TRAILING_BLOCK_KINDS:
            trailing_notation_block += 1
        else:
            break

    tag_v = counts["tag_lines"] + counts["v_lines"]
    notation_lines = tag_v + counts["status_lines"]
    notation_chars = (
        chars["tag_lines"] + chars["v_lines"] + chars["status_lines"]
    )

    def share(part, whole):
        return round(part / whole, 4) if whole else 0.0

    return {
        "chars": total_chars,
        "lines": total_lines,
        **counts,
        "tag_line_share": share(tag_v, total_lines),
        "notation_line_share": share(notation_lines, total_lines),
        "notation_char_share": share(notation_chars, total_chars),
        "first_notation_line_index": first_notation_index,
        "first_notation_line_frac": (
            round(first_notation_index / total_lines, 4)
            if first_notation_index is not None and total_lines
            else None
        ),
        "trailing_notation_block": trailing_notation_block,
        "empty_tag_lines": empty_tag_lines,
        "repeat_extra": repeat_extra,
        "longest_line_len": max((len(line) for line in non_empty), default=0),
        "prose_run_max": prose_run_max,
    }


def _read_rc(raw_path):
    """The full reasoning_content of one round's raw.json, or None.

    Fail-safe fuer die Denkspur: jede unlesbare/korrupte Datei und jede
    fehlende/null ``reasoning_content`` zaehlt als fehlend (rc_missing)
    statt die Auswertung des ganzen Lauf-Baums abzubrechen; ein *leerer*
    String gilt dagegen als leere Denkspur.
    """
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        message = payload["choices"][0]["message"]
        if not isinstance(message, dict):
            return None
        reasoning = message.get("reasoning_content")
        if reasoning is None or not isinstance(reasoning, str):
            return None
        return reasoning
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        return None


def _mean(values):
    return round(sum(values) / len(values), 4) if values else 0.0


def analyze_runs(root):
    """RC metrics for every round of a run tree (evaluate layout).

    Grenze der Fehlertoleranz: fehlende/korrupte ``raw.json`` sind
    fail-safe (rc_missing), die Lauf-Metadaten (``manifest.json``/
    ``summary.json``) dagegen fail-loud — ein kaputtes Aggregat soll nicht
    stillschweigend ein falsches Bild erzeugen.
    """
    from evaluate import load_runs  # same tooling dir; lazy to keep parse_rc standalone

    root = Path(root)
    manifest, runs = load_runs(root)
    per_run = []
    for run in runs:
        summary = run["summary"]
        if summary is None:
            continue  # legacy flat layout (V11): no per-round raw.json
        run_dir = Path(run["path"]).parent
        for round_index, row in enumerate(summary.get("rounds", [])):
            raw_path = run_dir / f"round{round_index}" / "raw.json"
            rc = _read_rc(raw_path) if raw_path.exists() else None
            entry = {
                "task_id": summary.get("task_id"),
                "arm": summary.get("arm"),
                "tier": summary.get("tier"),
                "rep": summary.get("rep"),
                "round": round_index,
                "solved": bool(row.get("solved")),
                "reasoning_tokens": row.get("reasoning_tokens", 0),
                "completion_tokens": row.get("completion_tokens", 0),
                "duration_s": row.get("duration_s", 0.0),
                "rc_missing": rc is None,
            }
            if rc is not None:
                entry.update(parse_rc(rc))
            per_run.append(entry)

    groups = {}
    for entry in per_run:
        groups.setdefault(f"{entry['arm']}-{entry['tier']}", []).append(entry)

    per_arm = {}
    for key, rows in sorted(groups.items()):
        with_rc = [row for row in rows if not row["rc_missing"]]
        per_arm[key] = {
            "arm": rows[0]["arm"],
            "tier": rows[0]["tier"],
            "n_rounds": len(rows),
            "n_rc": len(with_rc),
            "rc_missing": len(rows) - len(with_rc),
            "tag_line_share_mean": _mean([row["tag_line_share"] for row in with_rc]),
            "notation_line_share_mean": _mean(
                [row["notation_line_share"] for row in with_rc]
            ),
            "notation_char_share_mean": _mean(
                [row["notation_char_share"] for row in with_rc]
            ),
            "prose_run_max_mean": _mean([row["prose_run_max"] for row in with_rc]),
            "trailing_notation_block_mean": _mean(
                [row["trailing_notation_block"] for row in with_rc]
            ),
            "empty_tag_lines_sum": sum(row["empty_tag_lines"] for row in with_rc),
            "repeat_extra_sum": sum(row["repeat_extra"] for row in with_rc),
            "longest_line_max": max(
                (row["longest_line_len"] for row in with_rc), default=0
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
        "# RC-Fidelity der Denkspur (Metrik h, deskriptiv)",
        "",
        f"- Wurzel: {report['root']} · Modell: {report['manifest'].get('model') or '?'}",
        "",
        "| Arm-Tier | Runden | RC da | Tag-Zeilen ø | Notation-Zeilen ø | Notation-Zeichen ø (Proxy) | Reasoning-Tokens Σ | Ø/Runde | leere Tags | Loops (extra) | Prosa-Lauf max ø | Draft-Block ø |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in report["per_arm"].values():
        lines.append(
            "| {key} | {n} | {rc} | {tag} | {nl} | {nc} | {tok} | {tokm} | {empty} | {loops} | {prose} | {draft} |".format(
                key=f"{entry['arm']}-{entry['tier']}",
                n=entry["n_rounds"],
                rc=entry["n_rc"],
                tag=entry["tag_line_share_mean"],
                nl=entry["notation_line_share_mean"],
                nc=entry["notation_char_share_mean"],
                tok=entry["reasoning_tokens_sum"],
                tokm=entry["reasoning_tokens_mean"],
                empty=entry["empty_tag_lines_sum"],
                loops=entry["repeat_extra_sum"],
                prose=entry["prose_run_max_mean"],
                draft=entry["trailing_notation_block_mean"],
            )
        )
    lines.append("")
    lines.append(
        "Hinweise: `Tag-Zeilen` = (Tag- + v-Zeilen)/Zeilen (Metrik h); "
        "`Notation-Zeichen` ist der dokumentierte Zeichen-Proxy fuer den "
        "Token-Anteil (kein lokaler Tokenizer; unterschaetzt die Notation); "
        "`Draft-Block` = zusammenhaengender Notations-/Claim-Block am RC-Ende "
        "(Blatt-Entwurf inkl. CLAIM/WITNESS/[HALT]). Keine Signifikanzaussagen."
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

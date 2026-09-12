#!/usr/bin/env python3
"""Auswertung der Pilot-Laeufe (deskriptiv; keine Signifikanz-Claims).

Liest einen Lauf-Baum (``.yesmem/tmp/runs/<ts>/`` mit ``manifest.json`` und
``<task>/<arm>-rep<r>/parsed.json``) und berichtet die Metriken des
05-05-Nachtrags (a-d, f, g, h-k) je Arm und Tier, mit Wilson-Intervallen fuer
die Einzelraten. Beschreibende Statistik: der Pilot traegt keine
Bestaetigungs-Etiketten (05-05 Abschnitt 5, Multiplizitaets-Regel).

Aufruf: python3 evaluate.py --runs .yesmem/tmp/runs/<ts> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

_HEAD_RE = re.compile(r"\A(S[0-9]+|g[0-9]*|d[0-9]*|a[0-9]*|c[0-9]*|h[0-9]*|q[0-9]*|=[0-9]*):")
_STATUS_RE = re.compile(r"\A[a-zA-Z=][a-zA-Z0-9]*[0-9][+\-?!]\Z")
_VLINE_RE = re.compile(r"\Av[0-9]*\s+[a-zA-Z=][a-zA-Z0-9]*\s*:")


def wilson(successes, total, z=1.959963984540054):
    """Wilson interval for one proportion."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (centre - margin, centre + margin)


def load_runs(runs_root):
    records = []
    for parsed in sorted(Path(runs_root).glob("*/[!_]*-rep*/parsed.json")):
        data = json.loads(parsed.read_text(encoding="utf-8"))
        data["_path"] = str(parsed)
        records.append(data)
    manifest_path = Path(runs_root) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return manifest, records


def _sheet_marker_stats(answer):
    """(thinking lines, valid heads, format-error-line estimate) of one answer."""
    total = 0
    valid = 0
    for raw in answer.splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        total += 1
        if (
            _HEAD_RE.match(line)
            or _STATUS_RE.match(line)
            or _VLINE_RE.match(line)
            or line.startswith(("CLAIM ", "WITNESS ", "[HALT]"))
        ):
            valid += 1
    return total, valid


def summarize(records):
    groups = {}
    for record in records:
        arm = record["arm"]
        tier = record["tier"]
        key = (arm, tier)
        groups.setdefault(key, []).append(record)

    summary = {}
    for key, rows in sorted(groups.items()):
        arm, tier = key
        n = len(rows)
        solved = sum(1 for r in rows if r.get("solved"))
        durations = [r["duration_s"] for r in rows if r.get("duration_s") is not None]
        usage = [r.get("usage") or {} for r in rows]
        completion = [u.get("completion_tokens", 0) for u in usage]
        reasoning = [u.get("completion_tokens_details", {}).get("reasoning_tokens", 0) for u in usage]
        prompt_tokens = [u.get("prompt_tokens", 0) for u in usage]
        errors = sum(1 for r in rows if r.get("error"))
        sheet_rows = [r for r in rows if isinstance(r.get("format_errors"), list)]
        with_format_errors = sum(1 for r in sheet_rows if r["format_errors"])

        claims = [
            claim
            for r in rows
            for claim in (r.get("claims") or [])
        ]
        vlines = [v for r in rows for v in (r.get("v") or [])]
        refuted = sum(1 for c in claims if c["verdict"] == "REFUTED") + sum(
            1 for v in vlines if v["verdict"] == "REFUTED"
        )
        confirmed = sum(1 for c in claims if c["verdict"] == "CONFIRMED") + sum(
            1 for v in vlines if v["verdict"] == "CONFIRMED"
        )
        unknown = sum(1 for c in claims if c["verdict"] == "UNVERIFIABLE") + sum(
            1 for v in vlines if v["verdict"] == "UNVERIFIABLE"
        )

        markers = [_sheet_marker_stats(r.get("answer", "")) for r in sheet_rows]
        marker_total = sum(m[0] for m in markers)
        marker_valid = sum(m[1] for m in markers)

        trace_rows = [r for r in rows if r.get("tier_b_kind") == "trace"]
        matched = sum(r.get("checkpoints_matched", 0) for r in trace_rows)
        total_cp = sum(r.get("checkpoints_total", 0) for r in trace_rows)
        first_dev = [r.get("first_deviation") for r in trace_rows if r.get("first_deviation") is not None]

        low, high = wilson(solved, n)
        summary[f"{arm}-{tier}"] = {
            "arm": arm,
            "tier": tier,
            "n": n,
            "errors": errors,
            "solved": solved,
            "solve_rate": round(solved / n, 4) if n else None,
            "solve_ci95": [round(low, 4), round(high, 4)],
            "duration_mean_s": round(sum(durations) / len(durations), 1) if durations else None,
            "duration_max_s": max(durations) if durations else None,
            "prompt_tokens_mean": round(sum(prompt_tokens) / n, 1) if n else None,
            "completion_tokens_mean": round(sum(completion) / n, 1) if n else None,
            "reasoning_tokens_mean": round(sum(reasoning) / n, 1) if n else None,
            "format_error_sheets": with_format_errors,
            "format_error_rate": round(with_format_errors / len(sheet_rows), 4) if sheet_rows else None,
            "claims_total": len(claims) + len(vlines),
            "claims_confirmed": confirmed,
            "claims_refuted": refuted,
            "claims_unverifiable": unknown,
            "false_confirm_proxy": round(refuted / (confirmed + refuted), 4) if (confirmed + refuted) else None,
            "marker_fidelity": round(marker_valid / marker_total, 4) if marker_total else None,
            "vlines_mean": round(len(vlines) / len(sheet_rows), 2) if sheet_rows else None,
            "trace_checkpoints_matched": matched,
            "trace_checkpoints_total": total_cp,
            "trace_first_deviations": sorted(first_dev),
        }
    return summary


def render_markdown(summary, manifest):
    lines = [
        "# Pilot-Auswertung V1.1 (deskriptiv)",
        "",
        f"- Lauf: {manifest.get('started', '?')} · Modell: {manifest.get('model', '?')} · Arme: {manifest.get('arms', '?')} · reps: {manifest.get('reps', '?')}",
        f"- Tier-A-Set: {manifest.get('tier_a_set', {}).get('version', '?')} sha256 {manifest.get('tier_a_set', {}).get('sha256', '?')[:16]}…",
        f"- Tier-B-Set: {manifest.get('tier_b_set', {}).get('version', '?')} sha256 {manifest.get('tier_b_set', {}).get('sha256', '?')[:16]}…",
        "",
        "| Arm-Tier | n | gelöst | Rate (95%-CI Wilson) | Dauer ø | completion ø | reasoning ø | Formfehler-Blätter | bestätigt/refutiert/unprüfbar | Marker-Treue | Trace-CPs |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in summary.values():
        lines.append(
            "| {arm}-{tier} | {n} | {solved} | {rate} ({lo:.2f}–{hi:.2f}) | {dur}s | {comp} | {reas} | {ferr} | {c}/{r}/{u} | {mf} | {cp}/{cpt} |".format(
                arm=entry["arm"],
                tier=entry["tier"],
                n=entry["n"],
                solved=entry["solved"],
                rate=entry["solve_rate"],
                lo=entry["solve_ci95"][0],
                hi=entry["solve_ci95"][1],
                dur=entry["duration_mean_s"],
                comp=entry["completion_tokens_mean"],
                reas=entry["reasoning_tokens_mean"],
                ferr=entry["format_error_sheets"],
                c=entry["claims_confirmed"],
                r=entry["claims_refuted"],
                u=entry["claims_unverifiable"],
                mf=entry["marker_fidelity"],
                cp=entry["trace_checkpoints_matched"],
                cpt=entry["trace_checkpoints_total"],
            )
        )
    lines.append("")
    lines.append("Hinweise: `Trace-CPs` zählt exakt getroffene Gold-Checkpoints über alle Trace-Läufe des Arms. "
                 "„refutiert“ ist der Falschbestätigungs-Proxy (metrik e-Entsprechung). Keine Signifikanzaussagen.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True)
    parser.add_argument("--json", default=None)
    parser.add_argument("--markdown", default=None)
    args = parser.parse_args(argv)
    manifest, records = load_runs(args.runs)
    summary = summarize(records)
    markdown = render_markdown(summary, manifest)
    print(markdown)
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

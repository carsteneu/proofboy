#!/usr/bin/env python3
"""Auswertung der Pilot-Laeufe (deskriptiv; keine Signifikanz-Claims).

Liest einen Lauf-Baum und berichtet die Metriken je Arm und Tier, mit
Wilson-Intervallen fuer die Einzelraten. Zwei Layouts:

- Runde 2 (V12): ``<task>/<arm>-rep<r>/round<n>/parsed.json`` + ``summary.json``
  je Lauf -- zusaetzlich End-Trefferquote, Runden bis ok, Reparaturgewinn
  (R0 vs. final), ``#xx``-Aufloesungsrate und Tokens je Ergebnis.
- Pilot (V11): ``<task>/<arm>-rep<r>/parsed.json`` flach (weiter auswertbar;
  zaehlt als Ein-Runden-Lauf).

Beschreibende Statistik: der Lauf traegt keine Bestaetigungs-Etiketten
(05-05 Abschnitt 5, Multiplizitaets-Regel).

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
    """(manifest, runs): round-aware runs (summary.json) or legacy flat records.

    A round-aware run is ``{"summary": ..., "rounds": [parsed, ...], "path": ...}``
    (Runde-2-Layout ``<task>/<arm>-rep<r>/round<n>/parsed.json``); the legacy
    pilot layout (``<task>/<arm>-rep<r>/parsed.json``, V11) loads as a
    single-round run with ``summary=None``.
    """
    root = Path(runs_root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    runs = []
    # Fallback pro Lauf: ein gemischter Baum (Runden-Layout + V11-Flachlayout)
    # verliert nichts mehr.
    for run_dir in sorted(root.glob("*/[!_]*-rep*")):
        summary_path = run_dir / "summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            rounds = []
            for index in range(len(summary.get("rounds", []))):
                parsed_path = run_dir / f"round{index}" / "parsed.json"
                rounds.append(
                    json.loads(parsed_path.read_text(encoding="utf-8"))
                    if parsed_path.exists()
                    else None
                )
            runs.append({"summary": summary, "rounds": rounds, "path": str(summary_path)})
            continue
        legacy_path = run_dir / "parsed.json"
        if legacy_path.exists():
            data = json.loads(legacy_path.read_text(encoding="utf-8"))
            data["_path"] = str(legacy_path)
            runs.append({"summary": None, "rounds": [data], "path": str(legacy_path)})
    return manifest, runs


def _refuted_ids(record):
    """The ids the runner refuted in one round (v-lines and claims)."""
    ids = {row["id"] for row in (record.get("v") or []) if row.get("verdict") == "REFUTED"}
    ids |= {row["id"] for row in (record.get("claims") or []) if row.get("verdict") == "REFUTED"}
    return ids


def summarize_runs(runs):
    """Runde-2-Aggregat je Arm-Tier (deskriptiv, ohne Signifikanz-Claims)."""
    groups = {}
    for run in runs:
        summary = run["summary"]
        if summary is None:
            record = run["rounds"][0]
            summary = {
                "arm": record["arm"],
                "tier": record["tier"],
                "rounds": [{"solved": bool(record.get("solved")), "completion_tokens": (record.get("usage") or {}).get("completion_tokens", 0), "reasoning_tokens": ((record.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens", 0), "duration_s": record.get("duration_s") or 0.0, "format_errors": len(record.get("format_errors") or []), "error": record.get("error")}],
                "final_solved": bool(record.get("solved")),
                "rounds_to_ok": 0 if record.get("solved") else None,
            }
            run = {"summary": summary, "rounds": run["rounds"], "path": run["path"]}
        groups.setdefault((summary["arm"], summary["tier"]), []).append(run)

    out = {}
    for (arm, tier), rows in sorted(groups.items()):
        n = len(rows)
        r0_solved = sum(
            1
            for run in rows
            if run["summary"]["rounds"] and run["summary"]["rounds"][0]["solved"]
        )
        final_solved = sum(1 for run in rows if run["summary"]["final_solved"])
        repaired = sum(
            1
            for run in rows
            if run["summary"]["rounds"]
            and run["summary"]["final_solved"]
            and not run["summary"]["rounds"][0]["solved"]
        )
        hist = {"0": 0, "1": 0, "2": 0, "unresolved": 0}
        for run in rows:
            idx = run["summary"].get("rounds_to_ok")
            if idx is None:
                hist["unresolved"] += 1
            else:
                hist[str(idx)] = hist.get(str(idx), 0) + 1
        resolved = total_refuted = 0
        for run in rows:
            rounds = run["rounds"]
            for index in range(len(rounds) - 1):
                current, following = rounds[index], rounds[index + 1]
                if current is None or following is None:
                    continue
                refuted = _refuted_ids(current)
                if not refuted:
                    continue
                total_refuted += len(refuted)
                resolved += len(refuted - _refuted_ids(following))
        completion = [run["summary"]["rounds"] for run in rows]
        # completion_tokens enthaelt die Reasoning-Tokens (API-Detailfeld ist
        # die Aufschluesselung, keine zweite Summe) -- nicht doppelt zaehlen.
        total_tokens = sum(
            row["completion_tokens"] for rounds in completion for row in rounds
        )
        total_duration = sum(
            row["duration_s"] for rounds in completion for row in rounds
        )
        r0_format_errors = sum(
            1
            for run in rows
            if run["rounds"] and ((run["rounds"][0] or {}).get("format_errors") or [])
        )
        low, high = wilson(final_solved, n)
        r0_low, r0_high = wilson(r0_solved, n)
        out[f"{arm}-{tier}"] = {
            "arm": arm,
            "tier": tier,
            "n": n,
            "r0_solved": r0_solved,
            "r0_rate": round(r0_solved / n, 4) if n else None,
            "r0_ci95": [round(r0_low, 4), round(r0_high, 4)],
            "final_solved": final_solved,
            "final_rate": round(final_solved / n, 4) if n else None,
            "final_ci95": [round(low, 4), round(high, 4)],
            "repaired": repaired,
            "repair_gain_pp": round(100 * (final_solved - r0_solved) / n, 1) if n else None,
            "rounds_to_ok": hist,
            "xx_resolution": {
                "resolved": resolved,
                "total": total_refuted,
                "rate": round(resolved / total_refuted, 4) if total_refuted else None,
            },
            "r0_format_error_runs": r0_format_errors,
            "tokens_total": total_tokens,
            "tokens_per_run_mean": round(total_tokens / n, 1) if n else None,
            "tokens_per_final_solved": round(total_tokens / final_solved, 1) if final_solved else None,
            "wallclock_total_s": round(total_duration, 1),
            "repairs_used_mean": round(
                sum(run["summary"].get("repairs_used", 0) for run in rows) / n, 2
            ) if n else None,
        }
    return out


def render_round_markdown(summary, manifest):
    lines = [
        "# Runden-Auswertung V12 (deskriptiv)",
        "",
        f"- Lauf: {manifest.get('started', '?')} · Modell: {manifest.get('model', '?')} · Arme: {manifest.get('arms', '?')} · reps: {manifest.get('reps', '?')} · max_repairs: {manifest.get('max_repairs', '?')}",
        f"- Tier-A-Set: {manifest.get('tier_a_set', {}).get('version', '?')} sha256 {manifest.get('tier_a_set', {}).get('sha256', '?')[:16]}…",
        f"- Tier-B-Set: {manifest.get('tier_b_set', {}).get('version', '?')} sha256 {manifest.get('tier_b_set', {}).get('sha256', '?')[:16]}…",
        "",
        "| Arm-Tier | n | R0 gelöst | R0-Rate | Formfehler-Läufe R0 | Final gelöst | Final-Rate (95%-CI) | repariert | Reparaturgewinn | Runden bis ok (0..max/offen) | #xx-Auflösung | Tokens gesamt | Tokens/Treffer | Zeit gesamt |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in summary.values():
        hist = entry["rounds_to_ok"]
        # Dynamische Buckets: kein stilles Auslassen, falls je mehr als zwei
        # Reparaturrunden gefahren werden.
        keys = sorted((k for k in hist if k != "unresolved"), key=int)
        hist_str = "/".join(str(hist[k]) for k in keys + ["unresolved"])
        resolution = entry["xx_resolution"]
        tokens_per_solved = (
            entry["tokens_per_final_solved"]
            if entry["tokens_per_final_solved"] is not None
            else "—"
        )
        lines.append(
            "| {arm}-{tier} | {n} | {r0} | {r0r} | {ferr} | {fin} | {finr} ({lo:.2f}–{hi:.2f}) | {rep} | +{gain} pp | {hist} | {res}/{tot} | {tok} | {tps} | {wall}s |".format(
                arm=entry["arm"],
                tier=entry["tier"],
                n=entry["n"],
                r0=entry["r0_solved"],
                r0r=entry["r0_rate"],
                ferr=entry["r0_format_error_runs"],
                fin=entry["final_solved"],
                finr=entry["final_rate"],
                lo=entry["final_ci95"][0],
                hi=entry["final_ci95"][1],
                rep=entry["repaired"],
                gain=entry["repair_gain_pp"],
                hist=hist_str,
                res=resolution["resolved"],
                tot=resolution["total"],
                tok=entry["tokens_total"],
                tps=tokens_per_solved,
                wall=entry["wallclock_total_s"],
            )
        )
    lines.append("")
    lines.append(
        "Hinweise: `repariert` = R0 nicht gelöst, final gelöst; `Reparaturgewinn` = Differenz "
        "in Prozentpunkten über n; `Runden bis ok` zählt die Buckets 0..max in Ordnung, dann "
        "die offenen Läufe; `#xx-Auflösung` = Anteil der in Runde r refutierten ids, "
        "die in Runde r+1 nicht mehr refutiert sind; `Tokens` = completion über "
        "alle Runden (enthaelt reasoning). Keine Signifikanzaussagen."
    )
    return "\n".join(lines)


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
    manifest, runs = load_runs(args.runs)
    if any(run["summary"] is not None for run in runs):
        summary = summarize_runs(runs)
        markdown = render_round_markdown(summary, manifest)
    else:
        summary = summarize([run["rounds"][0] for run in runs])
        markdown = render_markdown(summary, manifest)
    print(markdown)
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

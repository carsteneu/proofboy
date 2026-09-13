#!/usr/bin/env python3
"""Retrospective audit: placeholder lines in the yesloop worker sections.

The P15 change makes the marker templates of a briefing count as no claim:
a body like ``<hash>``, ``...`` or ``TODO`` is a placeholder, so the line is
ignored instead of ending UNVERIFIABLE. This script measures that effect on
the real sections the workers wrote before the change.

Usage:

    python3 yesdocs/audit/audit_sections.py
    python3 yesdocs/audit/audit_sections.py --checkout .yesmem/tmp/audit-base
    python3 yesdocs/audit/audit_sections.py --json audit.json

For every section of the 13 yesloop workers it runs

    python3 -m bemyself check --section <name> --project <project>
        --repo <project> [--base <base>]

from ``--checkout`` (the code under test) and adds up the verdicts. The
section bases are the regression baselines the sections themselves document
(their Phase-4 lines), so a diff-scope claim compares against the revision
its worker actually used; ``p1`` and ``p3`` document no usable base and run
without one. The exit-code matrix at the end pins that reports with real
values keep their exit codes; its last row shows the deliberate exception
(a placeholder line no longer turns a strict run into exit 4). Since P18 the
two HALT rows also move under ``--strict``: a claim whose step count exceeds
the budget is the class ``limit`` and exits 6 (see the note in README.md of
this directory).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# The 13 yesloop worker sections (p1..p14, no p2) with the base revision
# each one documents for its own regression baseline (p1 documents none).
SECTIONS = {
    "yesloop-bemyself-p1-verifier": None,
    "yesloop-bemyself-p3-eval": "7c7392c",
    "yesloop-bemyself-p4-cli": "ead3dc7",
    "yesloop-bemyself-p5-strict": "5068e5f",
    "yesloop-bemyself-p6-sandbox": "b8f437f",
    "yesloop-bemyself-p7-halt": "6d82c4b",
    "yesloop-bemyself-p8-repo-optional": "4fd2b3003e96c4a4a56b16cfebe43ae9c305d66e",
    "yesloop-bemyself-p9-compute": "ff9b775",
    "yesloop-bemyself-p10-cycle": "8766e37",
    "yesloop-bemyself-p11-erdos-straus": "47301fc",
    "yesloop-bemyself-p12-ident": "28609e0",
    "yesloop-bemyself-p13-schur": "3025c29",
    "yesloop-bemyself-p14-merge-artifact": "dd0767c",
}

# Exit-code matrix: reports built from real values only (plus one row that
# pins the placeholder rule), each as (name, report text, needs repo?).
# The commit is master's P14 merge -- a commit every checkout can resolve.
_REAL_COMMIT = "b85de12"
_MATRIX = (
    ("commit-confirmed", f"[COMMIT: {_REAL_COMMIT}]\n", True),
    ("commit-missing-refuted", "[COMMIT: 1234567890abcdef1234567890abcdef12345678]\n", True),
    ("halt-confirmed", "[HALT: 1RB1RZ_0LA0LA -> 3]\n", False),
    ("halt-refuted", "[HALT: 1RB1RZ_0LA0LA -> 4]\n", False),
    ("halt-over-limit-unverifiable", "[HALT: 1RB1RZ_0LA0LA -> 999999999999]\n", False),
    ("no-claims", "nothing to see here\n", False),
    (
        "strict-mixed-real",
        f"[COMMIT: {_REAL_COMMIT}]\n[HALT: 1RB1RZ_0LA0LA -> 999999999999]\n",
        True,
    ),
    (
        "strict-mixed-placeholder",
        f"[COMMIT: {_REAL_COMMIT}]\n[HALT: <machine> -> <steps>]\n",
        True,
    ),
)


def _run_check(checkout, args):
    command = [sys.executable, "-m", "bemyself", *args]
    return subprocess.run(
        command,
        cwd=checkout,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": checkout},
    )


def _checkout_head(checkout):
    proc = subprocess.run(
        ["git", "-C", checkout, "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() or "unknown"


def audit_sections(checkout, project, db=None):
    """Run every section and return a per-section verdict summary."""
    rows = []
    for name, base in SECTIONS.items():
        args = ["check", "--section", name, "--project", project, "--repo", project, "--json"]
        if db:
            args += ["--db", db]
        if base:
            args += ["--base", base]
        proc = _run_check(checkout, args)
        try:
            payload = json.loads(proc.stdout)
            summary = payload["summary"]
        except (json.JSONDecodeError, KeyError):
            summary = None
        rows.append(
            {
                "section": name,
                "base": base,
                "exit": proc.returncode,
                "summary": summary,
                "stderr": proc.stderr.strip()[:200],
            }
        )
    return rows


def audit_exit_codes(checkout, project, workdir):
    """Run the exit-code matrix on synthetic reports with real values."""
    os.makedirs(workdir, exist_ok=True)
    rows = []
    for name, report, needs_repo in _MATRIX:
        path = os.path.join(workdir, f"{name}.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(report)
        args = ["check", "--report", path, "--json"]
        if needs_repo:
            args += ["--repo", project]
        default = _run_check(checkout, args)
        strict = _run_check(checkout, args + ["--strict"])
        try:
            summary = json.loads(default.stdout)["summary"]
        except (json.JSONDecodeError, KeyError):
            summary = None
        rows.append(
            {
                "name": name,
                "exit": default.returncode,
                "strict_exit": strict.returncode,
                "summary": summary,
                "stderr": default.stderr.strip()[:200] if summary is None else "",
            }
        )
    return rows


def _totals(rows):
    totals = {"CONFIRMED": 0, "REFUTED": 0, "UNVERIFIABLE": 0}
    for row in rows:
        if row["summary"] is None:
            continue
        for verdict, count in row["summary"].items():
            totals[verdict] += count
    return totals


def _failed(rows):
    """Rows whose run produced no parsable summary (never counted as zero)."""
    return [row for row in rows if row["summary"] is None]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--checkout",
        default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        help="code under test: the bemyself package is imported from here",
    )
    parser.add_argument(
        "--project",
        default="/home/carsten/projects/bemyself",
        help="scratchpad project of the sections (default: the bemyself project)",
    )
    parser.add_argument("--db", help="yesmem database path (default: ~/.claude/yesmem/yesmem.db)")
    parser.add_argument(
        "--workdir",
        default=None,
        help="where the synthetic reports are written (default: <checkout>/.yesmem/tmp/audit)",
    )
    parser.add_argument("--json", help="write the full result as JSON to this path")
    args = parser.parse_args(argv)

    checkout = os.path.abspath(args.checkout)
    workdir = args.workdir or os.path.join(checkout, ".yesmem", "tmp", "audit")

    sections = audit_sections(checkout, args.project, args.db)
    matrix = audit_exit_codes(checkout, args.project, workdir)

    head = _checkout_head(checkout)
    print(f"checkout: {checkout} (HEAD {head})")
    print(f"project:  {args.project}")
    print()
    print(f"{'section':44s} {'C':>3s} {'R':>3s} {'U':>3s}  exit")
    for row in sections:
        summary = row["summary"] or {}
        print(
            f"{row['section']:44s} {summary.get('CONFIRMED', '-'):>3} "
            f"{summary.get('REFUTED', '-'):>3} {summary.get('UNVERIFIABLE', '-'):>3}  {row['exit']}"
        )
    totals = _totals(sections)
    print(
        f"{'TOTAL':44s} {totals['CONFIRMED']:>3} {totals['REFUTED']:>3} "
        f"{totals['UNVERIFIABLE']:>3}"
    )
    print()
    print(f"{'exit matrix':36s} {'exit':>4s} {'strict':>6s}  summary")
    for row in matrix:
        summary = row["summary"] or {}
        short = ", ".join(f"{key[0]}:{value}" for key, value in summary.items())
        print(f"{row['name']:36s} {row['exit']:>4} {row['strict_exit']:>6}  {short}")

    failed = _failed(sections) + _failed(matrix)
    if failed:
        # A crashed or unparsable run must not read as "zero claims".
        print()
        print(f"FAILED RUNS: {len(failed)} (not counted in the totals above)")
        for row in failed:
            name = row.get("section") or row.get("name")
            print(f"  !! {name}: {row.get('stderr', '')}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(
                {"checkout": checkout, "head": head, "sections": sections, "matrix": matrix},
                handle,
                indent=2,
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

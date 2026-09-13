#!/usr/bin/env python3
"""Empirischer Gold-Leck-Scan ueber die Feedback-Logs eines Lauf-Baums (V14).

Liest jeden Runden-Record eines Lauf-Baums, sammelt die Feedback-Texte
(``next_feedback``) und prueft sie gegen die Referenzwerte der Aufgabe:

- Zyklus-Aufgaben: die Zertifikatswerte (t1, t2, d);
- Trace-Aufgaben: die Gold-Bandfenster (ab vier Zeichen) und Kopfpositionen.

Eine Nennung ist eine Verletzung, wenn sie nicht erkennbar modell-eigen ist:
Ein Ziffern-Token direkt hinter einem Buchstaben (``v1``, ``h1``, ``c1``,
``ref h1``, ``Schritt 5``, ``cp 5``) gilt als id-/Schritt-Kontext und ist
erklaert; alles andere (Werte in Klammern, hinter ``=``, freistehend) zaehlt.
Beide Kategorien werden berichtet -- der Scan behauptet nichts, er legt offen.

Aufruf::

    python3 scan_feedback.py --runs .yesmem/tmp/runs/<ts>[,<ts2>] --sets <sets-dir> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SETS_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"


def load_tasks(sets_dir):
    """``{task_id: task}`` over every set file; spaetere Versionen gewinnen."""
    tasks = {}
    for path in sorted(Path(sets_dir).glob("tier_*_v11-*-0.*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for task in payload.get("tasks", []):
            tasks[task["id"]] = task
    return tasks


def task_sensitive(task):
    """``[(kind, value_text)]`` -- die Referenzwerte, die nicht zurueckduerfen."""
    out = []
    if task.get("tier_b_kind") == "cyc":
        for value in task.get("certificate") or []:
            out.append(("certificate", str(value)))
    elif task.get("tier_b_kind") == "trace":
        for _step, _state, head, window in task.get("checkpoints_gold") or []:
            out.append(("head", str(head)))
            if len(window) >= 4:
                out.append(("tape", str(window)))
    return out


def _token_matches(text, value):
    pattern = re.compile(r"(?<![0-9])" + re.escape(value) + r"(?![0-9])")
    return [match.start() for match in pattern.finditer(text)]


# Nur diese Kontexte gelten als modell-eigen: ids wie ``v1``/``h1`` (Ziffer
# direkt an einem Buchstaben), Zaehl-/Schritt-Kontexte mit Wort davor und
# die Schritt-Angaben in Klammern (``sim(0..2)``). Alles andere -- etwa eine
# Zahl nach einem normalen Wort -- zaehlt als Verletzung (konservativ: lieber
# ein Fehlalarm zur Sichtpruefung als ein uebersehenes Leck).
_BENIGN_WORDS = frozenset({"schritt", "step", "line", "zeile"})
_WORD_BEFORE_RE = re.compile(r"([A-Za-z]+)\s*$")


def _explained(text, start):
    before = text[:start]
    if before and before[-1].isalpha():
        return True  # v1, h1, S0, cp5, ref h1 -- Ziffer klebt am Buchstaben
    stripped = before.rstrip()
    if stripped.endswith("("):
        return True  # sim(0..2), cyc(3,4,1) -- Beleg-Parameter des Modells
    word = _WORD_BEFORE_RE.search(stripped)
    if word and word.group(1).lower() in _BENIGN_WORDS:
        return True
    return False


def _snippet(text, start, length=40):
    low = max(0, start - length)
    high = min(len(text), start + length)
    return text[low:high].replace("\n", " | ")


def scan_run(runs_root, tasks):
    """Scan one run tree (or a comma list of trees).

    Returns ``{"scanned": N, "violations": [...], "explained": [...]}`` --
    violations are unexplained reference-value mentions, explained are the
    id/step-context hits (reported for transparency).
    """
    scanned = 0
    violations = []
    explained = []
    for part in str(runs_root).split(","):
        part = part.strip()
        if not part:
            continue
        for parsed_path in sorted(Path(part).glob("*/[!_]*-rep*/round*/parsed.json")):
            record = json.loads(parsed_path.read_text(encoding="utf-8"))
            text = record.get("next_feedback")
            if not text:
                continue
            scanned += 1
            task = tasks.get(parsed_path.parents[2].name)
            if task is None:
                continue
            for kind, value in task_sensitive(task):
                if kind == "tape":
                    if value in text:
                        index = text.index(value)
                        violations.append(
                            {
                                "run": str(parsed_path),
                                "task": task["id"],
                                "kind": kind,
                                "value": value,
                                "context": _snippet(text, index),
                            }
                        )
                    continue
                for start in _token_matches(text, value):
                    entry = {
                        "run": str(parsed_path),
                        "task": task["id"],
                        "kind": kind,
                        "value": value,
                        "context": _snippet(text, start),
                    }
                    if _explained(text, start):
                        explained.append(entry)
                    else:
                        violations.append(entry)
    return {"scanned": scanned, "violations": violations, "explained": explained}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True, help="run root(s), comma-separated")
    parser.add_argument("--sets", default=str(SETS_DIR), help="sets directory")
    parser.add_argument("--json", default=None, help="write the report as JSON")
    args = parser.parse_args(argv)

    report = scan_run(args.runs, load_tasks(args.sets))
    print(
        f"scanned {report['scanned']} feedback texts; "
        f"violations {len(report['violations'])}, "
        f"explained (id/Schritt-Kontext) {len(report['explained'])}"
    )
    for violation in report["violations"]:
        print(
            f"  VIOLATION {violation['task']} {violation['kind']}={violation['value']}: "
            f"{violation['context']}"
        )
    for entry in report["explained"]:
        print(
            f"  (explained) {entry['task']} {entry['kind']}={entry['value']}: {entry['context']}"
        )
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

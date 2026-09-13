#!/usr/bin/env python3
"""leancheck — schlanker Sandkasten-Elaborator fuer Lean-4-Schnipsel (V18).

Jeder Aufruf legt unter ``<root>/snips/`` eine eindeutige ``.lean``-Datei an
und laesst ``lake env lean`` mit hartem Timeout (Prozessgruppe) darauf laufen.
Das Projekt ``<root>/project`` ist ein Minimalprojekt ohne Dependencies
(gepinnte Toolchain ``leanprover/lean4:v4.33.1``, nur ``import Std`` moeglich):
deterministisch, offline (kein ``lake update``/Netz), ein Manifest wird
einmalig angelegt und wiederverwendet.

Klassifikation:

- ``valid``   = keine Fehlerzeilen im Schnipsel (Warnungen erlaubt). ``sorry``
                elaboriert, ist aber kein Beweis -- das separate Feld
                ``sorry_used`` sagt es, der Status nicht.
- ``invalid`` = Fehlerzeilen im Schnipsel.
- ``timeout`` = Laufzeit ueber ``timeout``; die Prozessgruppe wird gekillt.
- ``infra_error`` = Setup-/Werkzeugfehler (lake fehlt, Projekt nicht
                schreibbar) -- bewusst NICHT ``invalid``.

Axiom-Sonde: ``print_axioms_for`` haengt ``#print axioms <name>`` an und parst
die Ausgabe (``"none"`` | Liste | ``None``). Fehler dieser *angehaengten*
Zeile (z.B. unknownIdentifier bei falschem Namen) kippen die Gueltigkeit
nicht -- gezaehlt wird nur, was im Schnipsel selbst liegt.

Aufruf::

    python3 leancheck.py --file schnipsel.lean [--timeout 60] [--print-axioms main_thm] [--json out.json]

Als Bibliothek: ``check(source, timeout=60.0, print_axioms_for=None)``.
Die Toolchain wird nicht heruntergeladen: fehlt ``lake``, ist das Ergebnis
``infra_error``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # yesdocs/deepseek-math-notation/tooling -> repo root

TOOLCHAIN = "leanprover/lean4:v4.33.1"
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_'!?.]*$")
# `path.lean:12:34: error[(code)]: message` (Lean 4.33-Ausgabeform)
LINE_RE = re.compile(
    r"^(?P<file>[^:\s]+\.lean):(?P<line>\d+):(?P<col>\d+): "
    r"(?P<severity>error|warning)(?:\((?P<code>[^)]*)\))?: (?P<message>.*)$"
)
AXIOMS_NONE_RE = re.compile(r"'[^']*' does not depend on any axioms")
AXIOMS_LIST_RE = re.compile(r"'[^']*' depends on axioms: \[(?P<list>[^\]]*)\]")
SORRY_WARNING_RE = re.compile(r"declaration uses [`']sorry[`']")
SORRY_SOURCE_RE = re.compile(r"(?<![\w.'])sorry(?![\w'])")

PROJECT_LAKEFILE = 'name = "leancheck"\nversion = "0.1.0"\n'


def _parse_output(text):
    """(errors, warnings) aus der Lean-Ausgabe -- nur Zeilen mit Dateiprefix."""
    errors = []
    warnings = []
    for line in (text or "").splitlines():
        match = LINE_RE.match(line)
        if not match:
            continue
        entry = {
            "file": match.group("file"),
            "line": int(match.group("line")),
            "col": int(match.group("col")),
            "code": match.group("code"),
            "message": match.group("message"),
        }
        (errors if match.group("severity") == "error" else warnings).append(entry)
    return errors, warnings


def _parse_axioms(text):
    """``"none"`` | Liste | ``None`` aus einer ``#print axioms``-Ausgabe."""
    if not text:
        return None
    if AXIOMS_NONE_RE.search(text):
        return "none"
    match = AXIOMS_LIST_RE.search(text)
    if match:
        return [item.strip() for item in match.group("list").split(",") if item.strip()]
    return None


def _resolve_lake(lake_bin):
    if lake_bin:
        return lake_bin
    env = os.environ.get("LEANCHECK_LAKE", "").strip()
    if env:
        return env
    found = shutil.which("lake")
    if found:
        return found
    home_lake = Path.home() / ".elan" / "bin" / "lake"
    if home_lake.exists():
        return str(home_lake)
    return None


def _resolve_root(root):
    if root:
        return Path(root)
    env = os.environ.get("LEANCHECK_ROOT", "").strip()
    if env:
        return Path(env)
    return ROOT / ".yesmem" / "tmp" / "leancheck"


def _write_project(project):
    """Minimalprojekt (einmalig) -- gepinnte Toolchain, keine Dependencies."""
    project.mkdir(parents=True, exist_ok=True)
    (project / "lean-toolchain").write_text(TOOLCHAIN + "\n", encoding="utf-8")
    (project / "lakefile.toml").write_text(PROJECT_LAKEFILE, encoding="utf-8")


def check(source, *, timeout=60.0, print_axioms_for=None, root=None, lake_bin=None, toolchain=TOOLCHAIN):
    """Elaboriert ``source`` im Minimalprojekt; siehe Modul-Docstring."""
    if print_axioms_for is not None and not IDENT_RE.match(print_axioms_for):
        raise ValueError(f"print_axioms_for ist kein Lean-Identifikator: {print_axioms_for!r}")

    preamble = source if source.endswith("\n") else source + "\n"
    snippet_lines = len(preamble.splitlines())
    payload = preamble
    if print_axioms_for:
        payload += f"#print axioms {print_axioms_for}\n"

    result = {
        "status": "infra_error",
        "exit_code": None,
        "duration_s": 0.0,
        "errors": [],
        "warnings": [],
        "sorry_used": bool(SORRY_SOURCE_RE.search(source)),
        "axioms": None,
        "output": "",
        "file": None,
        "message": "",
    }

    lake = _resolve_lake(lake_bin)
    if not lake:
        result["message"] = "kein lake gefunden (LEANCHECK_LAKE, PATH, ~/.elan/bin/lake)"
        return result

    root_path = _resolve_root(root)
    project = root_path / "project"
    snips = root_path / "snips"
    try:
        _write_project(project)
        snips.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result["message"] = f"Projekt nicht anlegbar: {type(exc).__name__}: {exc}"
        return result

    if toolchain != TOOLCHAIN:
        (project / "lean-toolchain").write_text(toolchain + "\n", encoding="utf-8")
    snippet = snips / f"snippet-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.lean"
    try:
        snippet.write_text(payload, encoding="utf-8")
    except OSError as exc:
        result["message"] = f"Schnipsel nicht schreibbar: {type(exc).__name__}: {exc}"
        return result
    result["file"] = str(snippet)

    env = dict(os.environ)
    path_parts = [str(Path.home() / ".elan" / "bin")]
    if env.get("PATH"):
        path_parts.append(env["PATH"])
    env["PATH"] = os.pathsep.join(path_parts)

    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            [lake, "env", "lean", str(snippet)],
            cwd=str(project),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        result["message"] = f"lake nicht startbar: {type(exc).__name__}: {exc}"
        result["duration_s"] = round(time.monotonic() - start, 3)
        return result

    try:
        output, _ = proc.communicate(timeout=timeout)
        result["status"] = None  # unten anhand der Fehlerzeilen entschieden
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        output, _ = proc.communicate()
        result["status"] = "timeout"
    result["duration_s"] = round(time.monotonic() - start, 3)
    result["exit_code"] = proc.returncode
    result["output"] = output or ""

    errors, warnings = _parse_output(result["output"])
    result["errors"] = errors
    result["warnings"] = warnings
    if any(SORRY_WARNING_RE.search(item["message"]) for item in warnings):
        result["sorry_used"] = True
    result["axioms"] = _parse_axioms(result["output"])

    if result["status"] is None:
        errors = result["errors"]
        if print_axioms_for:
            # Nur die angehaengte #print-Zeile darf Fehler beisteuern, die die
            # Gueltigkeit des Schnipsels nicht beruehren (unknownIdentifier
            # bei falschem Namen) -- ohne Anhang gibt es nichts zu filtern.
            errors = [item for item in errors if item["line"] <= snippet_lines]
        result["errors"] = errors
        result["status"] = "invalid" if errors else "valid"
    return result


def _read_source(args):
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.text:
        return args.text
    return sys.stdin.read()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", default=None, help="Lean-Schnipsel (sonst --text oder stdin)")
    parser.add_argument("--text", default=None, help="Schnipsel direkt auf der Kommandozeile")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--print-axioms", default=None, dest="print_axioms",
                        help="anhaengen: #print axioms <name> und Ausgabe parsen")
    parser.add_argument("--json", default=None, help="Ergebnis als JSON schreiben")
    args = parser.parse_args(argv)
    result = check(_read_source(args), timeout=args.timeout, print_axioms_for=args.print_axioms)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if result["status"] in ("valid", "invalid", "timeout") else 1


if __name__ == "__main__":
    raise SystemExit(main())

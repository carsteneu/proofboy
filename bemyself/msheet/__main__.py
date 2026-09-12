"""Command line of the msheet engine.

Usage::

    python3 -m bemyself.msheet run <file> [--json] [--sandbox auto|require|off]
                                         [--timeout SECONDS]

Without ``--json`` the verdict appendix is printed (one ``#ok:``/``#xx:``/
``#?:`` line per verdict class); with ``--json`` the full structured result.
Exit codes: 0 = the sheet ran (whatever the verdicts), 2 = usage or I/O
error.
"""

from __future__ import annotations

import argparse
import json
import sys

from bemyself.msheet.runner import run_sheet
from bemyself.msheet.sheet import parse_sheet


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m bemyself.msheet",
        description="Run one sheet of the Denk-Sprache notation and print the verdicts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="parse and run one sheet file")
    run.add_argument("file", help="path of the sheet file")
    run.add_argument("--json", action="store_true", help="print the structured result")
    run.add_argument(
        "--sandbox",
        choices=("auto", "require", "off"),
        default="auto",
        help="how py: witnesses are executed (default: auto)",
    )
    run.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="seconds one py: witness may run (default: 10)",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        print(f"error: cannot read {args.file}: {exc}", file=sys.stderr)
        return 2

    sheet = parse_sheet(text)
    result = run_sheet(sheet, sandbox=args.sandbox, timeout=args.timeout)
    if args.json:
        print(json.dumps(result.to_json(), indent=2, ensure_ascii=False))
    else:
        for line in result.appendix:
            print(line)
        if not result.appendix:
            print("(no verdicts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Sandboxed executor for one ``py:`` witness expression.

Run as a subprocess (optionally inside bwrap, see
:mod:`proofboy.msheet.witnesses`). Evaluates the expression with the V1
library and a minimal set of builtins (all, any, sum, prod, range, len, min,
max, abs); everything else is unbound. Prints exactly one JSON line on
stdout:

    {"kind": "bool", "value": true}
    {"kind": "nonbool", "type": "int", "value": "5"}
    {"kind": "error", "error": "ZeroDivisionError: division by zero"}

Usage: python3 -S _pyexec.py <expression> <cpu-seconds>
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _limit(value):
    try:
        import resource

        cpu = max(1, int(value))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    except (ImportError, ValueError, OSError):
        pass


def main(argv):
    expr = argv[1] if len(argv) > 1 else ""
    _limit(argv[2] if len(argv) > 2 else "10")
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from proofboy.msheet.library import RESOLVED

    safe_builtins = {
        "all": all,
        "any": any,
        "sum": sum,
        "prod": math.prod,
        "range": range,
        "len": len,
        "min": min,
        "max": max,
        "abs": abs,
        "True": True,
        "False": False,
        "None": None,
    }
    env = dict(RESOLVED)
    env["__builtins__"] = safe_builtins
    try:
        value = eval(expr, env)  # noqa: S307 -- the sandbox is the boundary
    except BaseException as exc:  # noqa: BLE001 -- any exception is an unverifiable witness
        print(json.dumps({"kind": "error", "error": f"{type(exc).__name__}: {exc}"}))
        return 0
    if isinstance(value, bool):
        print(json.dumps({"kind": "bool", "value": value}))
    else:
        print(
            json.dumps(
                {
                    "kind": "nonbool",
                    "type": type(value).__name__,
                    "value": repr(value)[:200],
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

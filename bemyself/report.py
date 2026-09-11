"""Parse a plaintext agent report into a list of verifiable claims.

The report is a yesloop Phase-6 DONE report. Recognised claim sources:

- markers ``[COMMIT: <hash>]``, ``[BRANCH: <name>]``, ``[MERGE: ...]``,
  ``[DEPLOY: ...]`` (typically inside the ``send_to payload`` line)
- ``Tests run: <command> -> exit <n>`` lines. Exit 0 is the claim
  ``tests_green``; a non-zero exit is ``tests_exit`` (an honest failure
  report, verified against its own exit code -- not labelled "green").
- a ``Files in scope: a, b`` line, which becomes a diff-scope claim

Parsing is deliberately permissive: unknown lines are ignored, and a claim is
only emitted when its source is present. Absurdly long lines are skipped so a
hostile report cannot trigger pathological regex work.
"""

from __future__ import annotations

import re

from bemyself.model import Claim

_MAX_LINE = 8192

_MARKER_RE = re.compile(r"\[(COMMIT|BRANCH|MERGE|DEPLOY):[ \t]*([^\]\[]*?)[ \t]*\]")
_TESTS_RE = re.compile(
    r"^[ \t]*(?:\*\*)?Tests? run:[ \t]*(?P<cmd>\S(?:.*\S)?)[ \t]+"
    r"(?:->|\u2192)[ \t]+exit[ \t]+(?P<code>-?\d+)[ \t]*$"
)
_FILES_RE = re.compile(
    r"^[ \t]*(?:\*\*)?Files in scope:[ \t]*(?:\*\*)?[ \t]*(?P<files>\S.*?)[ \t]*$"
)


def _split_list(value: str) -> tuple[str, ...]:
    parts = (p.strip().strip("`*") for p in value.split(","))
    return tuple(p for p in parts if p)


def parse_report(text: str) -> list[Claim]:
    claims: list[Claim] = []
    first_commit: str | None = None
    tests_lines: list[tuple[int, str, str, int]] = []
    files_line: tuple[int, str, tuple[str, ...]] | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if len(raw) > _MAX_LINE:
            continue
        for match in _MARKER_RE.finditer(raw):
            key = match.group(1).upper()
            value = match.group(2).strip().strip("`")
            if key == "COMMIT":
                claims.append(Claim("commit_exists", lineno, raw, {"commit": value}))
                if first_commit is None:
                    first_commit = value
            elif key == "BRANCH":
                claims.append(
                    Claim("branch_pushed", lineno, raw, {"branch": value, "commit": None})
                )
            elif key == "MERGE":
                claims.append(Claim("merge", lineno, raw, {"value": value}))
            elif key == "DEPLOY":
                claims.append(Claim("deploy", lineno, raw, {"value": value}))

        tests_match = _TESTS_RE.match(raw)
        if tests_match:
            tests_lines.append(
                (
                    lineno,
                    raw,
                    tests_match.group("cmd").strip(),
                    int(tests_match.group("code")),
                )
            )

        files_match = _FILES_RE.match(raw)
        if files_match:
            files_line = (lineno, raw, _split_list(files_match.group("files")))

    if first_commit is not None:
        for claim in claims:
            if claim.kind == "branch_pushed" and claim.fields["commit"] is None:
                claim.fields["commit"] = first_commit

    for lineno, raw, command, code in tests_lines:
        kind = "tests_green" if code == 0 else "tests_exit"
        claims.append(
            Claim(
                kind,
                lineno,
                raw,
                {"command": command, "claimed_exit": code, "commit": first_commit},
            )
        )

    if files_line is not None and first_commit is not None:
        lineno, raw, planned = files_line
        claims.append(
            Claim("diff_scope", lineno, raw, {"head": first_commit, "planned": planned})
        )

    claims.sort(key=lambda claim: claim.line)
    return claims

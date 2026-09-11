"""Parse a plaintext agent report into a list of verifiable claims.

The report is a yesloop Phase-6 DONE report. Recognised claim sources:

- markers ``[COMMIT: <hash>]``, ``[BRANCH: <name>]``, ``[MERGE: ...]``,
  ``[DEPLOY: ...]`` (typically inside the ``send_to payload`` line)
- ``Tests run: <command> -> exit <n>`` lines
- a ``Files in scope: a, b`` line, which becomes a diff-scope claim

Parsing is deliberately permissive: unknown lines are ignored, and a claim is
only emitted when its source is present.
"""

from __future__ import annotations

import re

from bemyself.model import Claim

_MARKER_RE = re.compile(r"\[(COMMIT|BRANCH|MERGE|DEPLOY):\s*([^\]\[]*?)\s*\]")
_TESTS_RE = re.compile(
    r"^\s*(?:\*\*)?Tests? run:\s*(?P<cmd>.+?)\s*(?:->|\u2192)\s*exit\s*(?P<code>-?\d+)\s*$"
)
_FILES_RE = re.compile(
    r"^\s*(?:\*\*)?Files in scope:\s*(?:\*\*)?\s*(?P<files>.+?)\s*$"
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
        claims.append(
            Claim(
                "tests_green",
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

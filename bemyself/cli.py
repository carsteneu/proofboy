"""Command line interface for the claim verifier."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from bemyself.checks import DEFAULT_COMMAND_ALLOWLIST, Ctx, git_env, run_claim
from bemyself.model import Claim, Verdict
from bemyself.report import parse_report

EXIT_OK = 0
EXIT_REFUTED = 1
EXIT_ERROR = 2
EXIT_NOTHING = 3
MAX_REPORT_BYTES = 1 << 20
_CONTROL_CHARS = {code: "?" for code in range(0x20) if code != 0x0A}
_CONTROL_CHARS[0x09] = " "
_CONTROL_CHARS[0x7F] = "?"
_CONTROL_CHARS.update({code: "?" for code in range(0x80, 0xA0)})
_CONTROL_CHARS.update(
    {
        code: "?"
        for code in (
            0x00AD,  # soft hyphen
            0x061C,  # arabic letter mark
            0x200B,  # zero width space
            0x200C,  # zero width non-joiner
            0x200D,  # zero width joiner
            0x200E,  # left-to-right mark
            0x200F,  # right-to-left mark
            0x2028,  # line separator
            0x2029,  # paragraph separator
            0x202A,
            0x202B,
            0x202C,
            0x202D,
            0x202E,  # bidi embeddings/overrides
            0x2060,  # word joiner
            0x2066,
            0x2067,
            0x2068,
            0x2069,  # bidi isolates
            0xFEFF,  # zero width no-break space
        )
    }
)


def _sanitize(value):
    """Keep hostile bytes from spoofing the verdict display on a terminal."""
    return value.translate(_CONTROL_CHARS)


def _resolve_repo_root(path):
    """Resolve a path inside a repository to the repository root."""
    proc = subprocess.run(
        ["git", "-C", path, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        env=git_env(),
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return path


def _json_error(report_path, repo, message):
    return {
        "report": report_path,
        "repo": repo,
        "claims": [],
        "summary": summarize([]),
        "error": message,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m bemyself",
        description="Verify a report's claims against the repository. It believes nothing.",
        epilog=(
            "exit codes: 0 = at least one claim CONFIRMED and none REFUTED; "
            "1 = at least one REFUTED; 2 = error; 3 = nothing CONFIRMED. "
            "Exit 0 does not mean every claim was proven - read the summary "
            "or --json to see the UNVERIFIABLE claims."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="verify every claim in a report")
    check.add_argument("--report", required=True, help="path to the report file")
    check.add_argument("--repo", required=True, help="path to the git repository")
    check.add_argument(
        "--base",
        help="base revision for diff-scope; without it diff-scope claims stay UNVERIFIABLE",
    )
    check.add_argument("--files", help="comma separated planned file list, overrides 'Files in scope'")
    check.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    check.add_argument("--tmp", help="directory for throwaway checkouts")
    check.add_argument(
        "--allow", action="append", default=[], help="extra allowlisted command prefix (repeatable)"
    )
    return parser


def _apply_files_override(claims, files_value):
    if not files_value:
        return claims
    planned = tuple(part.strip() for part in files_value.split(",") if part.strip())
    if not planned:
        return claims
    retargeted = False
    for claim in claims:
        if claim.kind == "diff_scope":
            claim.fields["planned"] = planned
            retargeted = True
    if not retargeted:
        # Bind to the report's commit only when it names exactly one; several
        # distinct commits would make the binding a guess.
        commits = {claim.fields["commit"] for claim in claims if claim.kind == "commit_exists"}
        head = next(iter(commits)) if len(commits) == 1 else None
        claims.append(
            Claim(
                "diff_scope",
                0,
                "--files override",
                {"head": head, "planned": planned},
            )
        )
        claims.sort(key=lambda c: c.line)
    return claims


def summarize(results):
    summary = {verdict.value: 0 for verdict in Verdict}
    for _, result in results:
        summary[result.verdict.value] += 1
    return summary


def exit_code(results):
    verdicts = [result.verdict for _, result in results]
    if Verdict.REFUTED in verdicts:
        return EXIT_REFUTED
    if Verdict.CONFIRMED not in verdicts:
        # Nothing was refuted, but nothing was proven either (all UNVERIFIABLE
        # or no claims at all): this must not read as success.
        return EXIT_NOTHING
    return EXIT_OK


def _json_payload(report_path, repo, results):
    return {
        "report": report_path,
        "repo": repo,
        "claims": [
            {
                "kind": claim.kind,
                "line": claim.line,
                "raw": claim.raw,
                "verdict": result.verdict.value,
                "reason": result.reason,
                "command": result.command,
                "output": result.output,
            }
            for claim, result in results
        ],
        "summary": summarize(results),
    }


def render_text(results):
    width = max((len(claim.kind) for claim, _ in results), default=0)
    lines = []
    for claim, result in results:
        lines.append(f"{claim.kind:<{width}}  {result.verdict.value:<12}  {result.reason}")
        if result.command:
            lines.append(f"    cmd: {result.command}")
        if result.output:
            for output_line in result.output.splitlines():
                lines.append(f"    out: {output_line}")
    summary = summarize(results)
    lines.append("")
    lines.append("summary: " + ", ".join(f"{v.value}: {summary[v.value]}" for v in Verdict))
    return "\n".join(lines)


def run_check(args):
    report_path = os.path.abspath(args.report)
    repo_arg = os.path.abspath(args.repo)
    try:
        with open(report_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        message = f"cannot read report {report_path}: {exc}"
        print(f"bemyself: {message}", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_error(report_path, repo_arg, message), indent=2, ensure_ascii=True))
        return EXIT_ERROR

    if len(text) > MAX_REPORT_BYTES:
        # Verifying a silently truncated report could hide the claims that
        # matter; refuse instead of guessing.
        message = f"report exceeds 1 MiB; refusing to verify a truncated report: {report_path}"
        print(f"bemyself: {message}", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_error(report_path, repo_arg, message), indent=2, ensure_ascii=True))
        return EXIT_ERROR

    if not os.path.isdir(repo_arg):
        message = f"repo path does not exist: {repo_arg}"
        print(f"bemyself: {message}", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_error(report_path, repo_arg, message), indent=2, ensure_ascii=True))
        return EXIT_ERROR
    repo = _resolve_repo_root(repo_arg)

    claims = _apply_files_override(parse_report(text), args.files)

    if not claims:
        print("bemyself: no verifiable claims found in the report", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_payload(report_path, repo, []), indent=2, ensure_ascii=True))
        return EXIT_NOTHING

    ctx = Ctx(
        repo=repo,
        tmp_dir=os.path.abspath(args.tmp)
        if args.tmp
        else os.path.join(repo, ".yesmem", "tmp", "check"),
        base=args.base,
        allowlist=DEFAULT_COMMAND_ALLOWLIST + tuple(args.allow),
    )
    results = [(claim, run_claim(claim, ctx)) for claim in claims]

    if args.json:
        print(json.dumps(_json_payload(report_path, repo, results), indent=2, ensure_ascii=True))
    else:
        print(_sanitize(render_text(results)))

    return exit_code(results)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return run_check(args)
    parser.error(f"unknown command: {args.command}")
    return EXIT_ERROR

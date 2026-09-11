"""Command line interface for the claim verifier."""

from __future__ import annotations

import argparse
import json
import os
import sys

from bemyself.checks import DEFAULT_COMMAND_ALLOWLIST, Ctx, run_claim
from bemyself.model import Claim, Verdict
from bemyself.report import parse_report

EXIT_OK = 0
EXIT_REFUTED = 1
EXIT_ERROR = 2
EXIT_NOTHING = 3
MAX_REPORT_BYTES = 1 << 20


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m bemyself",
        description="Verify a report's claims against the repository. It believes nothing.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="verify every claim in a report")
    check.add_argument("--report", required=True, help="path to the report file")
    check.add_argument("--repo", required=True, help="path to the git repository")
    check.add_argument("--base", help="base revision for diff-scope (default: <commit>^)")
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
        commit_claim = next((c for c in claims if c.kind == "commit_exists"), None)
        if commit_claim is not None:
            claims.append(
                Claim(
                    "diff_scope",
                    commit_claim.line,
                    "--files override",
                    {"head": commit_claim.fields["commit"], "planned": planned},
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
    try:
        with open(report_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read(MAX_REPORT_BYTES)
    except OSError as exc:
        print(f"bemyself: cannot read report {report_path}: {exc}", file=sys.stderr)
        if args.json:
            print(
                json.dumps(
                    {
                        "report": report_path,
                        "repo": os.path.abspath(args.repo),
                        "claims": [],
                        "summary": summarize([]),
                        "error": str(exc),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        return EXIT_ERROR

    repo = os.path.abspath(args.repo)
    claims = _apply_files_override(parse_report(text), args.files)

    if not claims:
        print("bemyself: no verifiable claims found in the report", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_payload(report_path, repo, []), indent=2, ensure_ascii=False))
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
        print(json.dumps(_json_payload(report_path, repo, results), indent=2, ensure_ascii=False))
    else:
        print(render_text(results))

    return exit_code(results)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return run_check(args)
    parser.error(f"unknown command: {args.command}")
    return EXIT_ERROR

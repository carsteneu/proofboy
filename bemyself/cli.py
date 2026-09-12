"""Command line interface for the claim verifier."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from bemyself.checks import (
    DEFAULT_COMMAND_ALLOWLIST,
    SANDBOX_MODES,
    Ctx,
    git_env,
    kind_needs_repo,
    run_claim,
)
from bemyself.claimtypes.compute import DEFAULT_COMPUTE_ALLOWLIST
from bemyself.claimtypes.coloring import DEFAULT_COLORING_LIMIT
from bemyself.claimtypes.cycle import DEFAULT_CYCLE_LIMIT
from bemyself.claimtypes.halt import DEFAULT_HALT_LIMIT
from bemyself.claimtypes.search import DEFAULT_SEARCH_LIMIT
from bemyself.model import Claim, Verdict
from bemyself.report import parse_report
from bemyself.scratchpad import DEFAULT_DB, ScratchpadError, default_db_path, read_section

EXIT_OK = 0
EXIT_REFUTED = 1
EXIT_ERROR = 2
EXIT_NOTHING = 3
EXIT_STRICT = 4
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


def sanitize(value):
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


def _json_error(source, repo, message):
    return {
        "report": source,
        "repo": repo,
        "claims": [],
        "summary": summarize([]),
        "error": message,
    }


def _non_negative_int(value):
    """argparse type for --halt-limit: plain decimal digits, non-negative."""
    if not (value.isascii() and value.isdigit()):
        raise argparse.ArgumentTypeError(f"not a non-negative integer: {value!r}")
    return int(value)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m bemyself",
        description="Verify a report's claims against the repository. It believes nothing.",
        epilog=(
            "exit codes: 0 = at least one claim CONFIRMED and none REFUTED; "
            "1 = at least one REFUTED; 2 = error; 3 = nothing CONFIRMED; "
            "4 = --strict, nothing REFUTED, at least one CONFIRMED and at "
            "least one UNVERIFIABLE. "
            "Exit 0 does not mean every claim was proven - read the summary "
            "or --json to see the UNVERIFIABLE claims, or pass --strict to "
            "make an unchecked claim fail the run."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="verify every claim in a report")
    check.add_argument("--report", help="path to the report file")
    check.add_argument(
        "--section",
        help="name of a YesMem scratchpad section to verify instead of a file",
    )
    check.add_argument(
        "--project",
        help="scratchpad project of --section; --repo defaults to the same path",
    )
    check.add_argument(
        "--db",
        help=f"path to the YesMem database (default {DEFAULT_DB}), opened read-only",
    )
    check.add_argument(
        "--repo",
        help="path to the git repository; required with --report only when a claim kind in it needs one",
    )
    check.add_argument(
        "--base",
        help="base revision for diff-scope; without it diff-scope claims stay UNVERIFIABLE",
    )
    check.add_argument("--files", help="comma separated planned file list, overrides 'Files in scope'")
    check.add_argument(
        "--strict",
        action="store_true",
        help=(
            "fail unless every claim was proven: with something CONFIRMED "
            "and nothing REFUTED, a single UNVERIFIABLE claim becomes exit 4 "
            "(without the flag exit codes are unchanged)"
        ),
    )
    check.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    check.add_argument("--tmp", help="directory for throwaway checkouts")
    check.add_argument(
        "--allow",
        action="append",
        default=[],
        help=(
            "extra allowlisted command prefix for test runs and [COMPUTE] "
            "claims (repeatable)"
        ),
    )
    check.add_argument(
        "--sandbox",
        choices=SANDBOX_MODES,
        default="auto",
        help=(
            "how test commands run: auto sandboxes with bwrap when available "
            "(the default), require refuses to run without a working sandbox, "
            "off runs unsandboxed"
        ),
    )
    check.add_argument(
        "--halt-limit",
        type=_non_negative_int,
        default=DEFAULT_HALT_LIMIT,
        metavar="N",
        help=(
            "largest step count a [HALT] claim may ask the simulator to "
            f"execute (default {DEFAULT_HALT_LIMIT}); a claim beyond it stays "
            "unverifiable"
        ),
    )
    check.add_argument(
        "--search-limit",
        type=_non_negative_int,
        default=DEFAULT_SEARCH_LIMIT,
        metavar="N",
        help=(
            "largest step count a [SEARCHED] claim may ask the simulator to "
            f"execute (default {DEFAULT_SEARCH_LIMIT}); a claim beyond it "
            "stays unverifiable"
        ),
    )
    check.add_argument(
        "--cycle-limit",
        type=_non_negative_int,
        default=DEFAULT_CYCLE_LIMIT,
        metavar="N",
        help=(
            "largest step count a [CYCLE] claim may ask the simulator to "
            f"execute (default {DEFAULT_CYCLE_LIMIT}); a claim beyond it "
            "stays unverifiable"
        ),
    )
    check.add_argument(
        "--coloring-limit",
        type=_non_negative_int,
        default=DEFAULT_COLORING_LIMIT,
        metavar="N",
        help=(
            "largest N a [COLORING] claim may ask the checker to enumerate "
            f"(default {DEFAULT_COLORING_LIMIT}); a longer certificate stays "
            "unverifiable"
        ),
    )
    evaluate = sub.add_parser("eval", help="measure the verifier against a labelled message set")
    evaluate.add_argument("--set", required=True, help="path to the evaluation set (JSON)")
    evaluate.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    evaluate.add_argument("--tmp", help="directory for the throwaway fixture and checkouts")
    evaluate.add_argument(
        "--sandbox",
        choices=SANDBOX_MODES,
        default="auto",
        help=(
            "how test commands run: auto sandboxes with bwrap when available "
            "(the default), require refuses to run without a working sandbox, "
            "off runs unsandboxed"
        ),
    )
    evaluate.add_argument(
        "--halt-limit",
        type=_non_negative_int,
        default=DEFAULT_HALT_LIMIT,
        metavar="N",
        help=(
            "largest step count a [HALT] claim may ask the simulator to "
            f"execute (default {DEFAULT_HALT_LIMIT}); a claim beyond it stays "
            "unverifiable"
        ),
    )
    evaluate.add_argument(
        "--search-limit",
        type=_non_negative_int,
        default=DEFAULT_SEARCH_LIMIT,
        metavar="N",
        help=(
            "largest step count a [SEARCHED] claim may ask the simulator to "
            f"execute (default {DEFAULT_SEARCH_LIMIT}); a claim beyond it "
            "stays unverifiable"
        ),
    )
    evaluate.add_argument(
        "--cycle-limit",
        type=_non_negative_int,
        default=DEFAULT_CYCLE_LIMIT,
        metavar="N",
        help=(
            "largest step count a [CYCLE] claim may ask the simulator to "
            f"execute (default {DEFAULT_CYCLE_LIMIT}); a claim beyond it "
            "stays unverifiable"
        ),
    )
    evaluate.add_argument(
        "--coloring-limit",
        type=_non_negative_int,
        default=DEFAULT_COLORING_LIMIT,
        metavar="N",
        help=(
            "largest N a [COLORING] claim may ask the checker to enumerate "
            f"(default {DEFAULT_COLORING_LIMIT}); a longer certificate stays "
            "unverifiable"
        ),
    )
    evaluate.add_argument(
        "--strict",
        action="store_true",
        help="fail with exit 4 when a claim in the set stays UNVERIFIABLE and the thresholds hold",
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


def exit_code(results, strict=False):
    verdicts = [result.verdict for _, result in results]
    if Verdict.REFUTED in verdicts:
        return EXIT_REFUTED
    if Verdict.CONFIRMED not in verdicts:
        # Nothing was refuted, but nothing was proven either (all UNVERIFIABLE
        # or no claims at all): this must not read as success.
        return EXIT_NOTHING
    if strict and Verdict.UNVERIFIABLE in verdicts:
        # Strict mode reserves exit 0 for reports whose every claim was
        # actually proven; a claim that was never checked is a failure.
        return EXIT_STRICT
    return EXIT_OK


def _json_payload(source, repo, results):
    return {
        "report": source,
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
                "sandboxed": result.sandboxed,
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


def _tmp_dir(args, repo):
    """The throwaway root, or None when the default would leave the repo.

    A committed ``.yesmem`` symlink must not redirect the verifier's scratch
    files outside the inspected repository.
    """
    if args.tmp:
        return os.path.abspath(args.tmp)
    if repo is None:
        # No repository in this run: there is no checkout to place, and a
        # repo-free checker does not touch the tmp dir.
        return None
    candidate = os.path.join(repo, ".yesmem", "tmp", "check")
    repo_real = os.path.realpath(repo)
    candidate_real = os.path.realpath(candidate)
    if candidate_real != repo_real and not candidate_real.startswith(repo_real + os.sep):
        return None
    return candidate


def _validate_check_args(parser, args):
    """Enforce the source contract before any file or database is touched.

    argparse cannot express the dependency pairs, so this is a usage error
    (exit 2) in every invalid combination.
    """
    if args.report is None and args.section is None:
        parser.error("one of --report or --section is required")
    if args.report is not None and args.section is not None:
        parser.error("--report and --section are mutually exclusive")
    # --repo is decided in run_check, not here: whether a report needs a
    # repository depends on the claim kinds it contains.
    if args.section is not None and args.project is None:
        parser.error("--project is required with --section")


def _source_error(as_json, source, repo, message):
    """Report a source (file or section) error in both output modes."""
    print(f"bemyself: {message}", file=sys.stderr)
    if as_json:
        print(json.dumps(_json_error(source, repo, message), indent=2, ensure_ascii=True))
    return EXIT_ERROR


def run_check(args, parser):
    if args.section is not None:
        # The descriptor names the source in the JSON output: there is no
        # report file behind a section, and the exit code alone cannot say
        # where the message came from.
        source = f"scratchpad:{args.section}@{args.project}"
        repo_arg = os.path.abspath(args.repo or args.project)
        try:
            text = read_section(
                args.db or default_db_path(), args.project, args.section, MAX_REPORT_BYTES + 1
            )
        except ScratchpadError as exc:
            return _source_error(args.json, source, repo_arg, f"cannot read scratchpad section: {exc}")
        if text is None:
            return _source_error(
                args.json,
                source,
                repo_arg,
                f"section {args.section!r} not found in project {args.project!r}",
            )
        if len(text) > MAX_REPORT_BYTES:
            return _source_error(
                args.json,
                source,
                repo_arg,
                f"section exceeds 1 MiB; refusing to verify a truncated section: {source}",
            )
    else:
        source = os.path.abspath(args.report)
        repo_arg = os.path.abspath(args.repo) if args.repo is not None else None
        try:
            with open(source, encoding="utf-8", errors="replace") as handle:
                text = handle.read(MAX_REPORT_BYTES + 1)
        except OSError as exc:
            return _source_error(args.json, source, repo_arg, f"cannot read report {source}: {exc}")
        if len(text) > MAX_REPORT_BYTES:
            # Verifying a silently truncated report could hide the claims that
            # matter; refuse instead of guessing.
            return _source_error(
                args.json,
                source,
                repo_arg,
                f"report exceeds 1 MiB; refusing to verify a truncated report: {source}",
            )

    if repo_arg is not None:
        if not os.path.isdir(repo_arg):
            return _source_error(args.json, source, repo_arg, f"repo path does not exist: {repo_arg}")
        repo = _resolve_repo_root(repo_arg)
    else:
        repo = None

    claims = _apply_files_override(parse_report(text), args.files)

    if repo is None:
        needed = next((claim.kind for claim in claims if kind_needs_repo(claim.kind)), None)
        if needed is not None:
            # Decidable only now: a report needs --repo once one of its claim
            # kinds declares a repository need.
            parser.error(
                "--repo is required with --report "
                f"(claim kind {needed!r} needs a repository)"
            )

    if not claims:
        kind = "section" if args.section is not None else "report"
        print(f"bemyself: no verifiable claims found in the {kind}", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_payload(source, repo, []), indent=2, ensure_ascii=True))
        return EXIT_NOTHING

    tmp_dir = _tmp_dir(args, repo)
    if repo is not None and tmp_dir is None:
        # A None tmp_dir is an error only for a repo-backed run: it means the
        # default resolves outside the repo (committed .yesmem symlink). A
        # repo-free run has no default to resolve.
        message = (
            "default tmp dir resolves outside the repo (committed .yesmem symlink?); "
            "pass --tmp to place it elsewhere"
        )
        print(f"bemyself: {message}", file=sys.stderr)
        if args.json:
            print(json.dumps(_json_error(source, repo, message), indent=2, ensure_ascii=True))
        return EXIT_ERROR
    ctx = Ctx(
        repo=repo,
        tmp_dir=tmp_dir,
        base=args.base,
        allowlist=DEFAULT_COMMAND_ALLOWLIST + tuple(args.allow),
        sandbox=args.sandbox,
        halt_limit=args.halt_limit,
        search_limit=args.search_limit,
        cycle_limit=args.cycle_limit,
        coloring_limit=args.coloring_limit,
        compute_allowlist=DEFAULT_COMPUTE_ALLOWLIST + tuple(args.allow),
    )
    results = [(claim, run_claim(claim, ctx)) for claim in claims]

    if args.json:
        print(json.dumps(_json_payload(source, repo, results), indent=2, ensure_ascii=True))
    else:
        print(sanitize(render_text(results)))

    return exit_code(results, strict=args.strict)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        _validate_check_args(parser, args)
        return run_check(args, parser)
    if args.command == "eval":
        # Imported here so the check path does not load the eval harness.
        from bemyself.eval import run_eval

        return run_eval(args)
    parser.error(f"unknown command: {args.command}")
    return EXIT_ERROR

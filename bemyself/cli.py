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
from bemyself import claimtypes, profiles, projectconfig, stackdetect, toolmanifest
from bemyself.model import Cause, Claim, Verdict
from bemyself.report import parse_report
from bemyself.scratchpad import DEFAULT_DB, ScratchpadError, default_db_path, read_section

EXIT_OK = 0
EXIT_REFUTED = 1
EXIT_ERROR = 2
EXIT_NOTHING = 3
EXIT_STRICT = 4
# A defective claim -- the report or the checked thing violates a required
# form -- fails in both modes: the gate must see "the claim cannot bind",
# not a boundary of the run.
EXIT_DEFECT = 5
# A claim a budget kept from being executed fails only under --strict, but
# with its own code: "could not check" is not "checked and failed".
EXIT_LIMIT = 6
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
        "classes": class_summary([]),
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
            "least one UNVERIFIABLE; 5 = at least one defective claim (the "
            "report or the checked thing violates a required form - an "
            "unknown marker, a class its profile requires, a malformed "
            "binding; fails with and without --strict); "
            "6 = --strict, nothing REFUTED and at least one claim a budget "
            "kept from being executed. "
            "Exit 0 does not mean every claim was proven - read the summary "
            "or --json to see the UNVERIFIABLE claims and their class, pass "
            "--strict to make an unchecked claim fail the run, or --profile "
            "to demand the claim classes a report of that kind must contain."
        ),
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="list the registered optional claim types and exit",
    )
    # Not required: `--list-types` is a question of its own, answered without
    # a subcommand; main() turns a missing command into the usage error.
    sub = parser.add_subparsers(dest="command", required=False)
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
            "and a claim a budget kept from execution exit 6; a defective "
            "claim fails with exit 5 in both modes (without the flag the "
            "other exit codes are unchanged)"
        ),
    )
    check.add_argument(
        "--profile",
        choices=profiles.profile_names(),
        help=(
            "report profile: the claim classes a report of this kind must "
            "contain; a required class the report does not yield is a defect "
            "(exit 5, with and without --strict)"
        ),
    )
    check.add_argument(
        "--list-types",
        action="store_true",
        help="list the registered optional claim types and exit (no report needed)",
    )
    check.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    check.add_argument("--tmp", help="directory for throwaway checkouts")
    check.add_argument(
        "--artifact-root",
        help=(
            "directory that [ARTIFACT] paths resolve against; default is the "
            "repository, and without either the claim stays UNVERIFIABLE"
        ),
    )
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
        default=None,
        help=(
            "how test commands run: auto sandboxes with bwrap when available "
            "(the default), require refuses to run without a working sandbox, "
            "off runs unsandboxed"
        ),
    )
    check.add_argument(
        "--project-config",
        metavar="DATEI",
        help=(
            "path to a JSON project config naming check knobs (allow, profile, "
            "sandbox, tools, tmp); an explicit CLI flag wins over the config "
            "entry, the config entry wins over the built-in default, allow "
            "entries are additive, and an unreadable or invalid config is a "
            "usage error"
        ),
    )
    check.add_argument(
        "--detect",
        action="store_true",
        help=(
            "print the stacks detected from the repository's root marker files "
            "and the commands they suggest; a pure suggestion layer -- with a "
            "report it only rides along in the output, changing no claim and "
            "no exit code, and without one it is a standalone query"
        ),
    )
    check.add_argument(
        "--tools",
        metavar="MANIFEST",
        help=(
            "path to a TOML tool manifest pinning lean, leanchecker and lake "
            "by path, version and sha256 digest; a pinned tool wins over a "
            "repository's toolchain request, and a tool the manifest does not "
            "name is not run (the [LEAN] claim stays unverifiable)"
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
            "unverifiable -- report lines beyond 8192 characters are ignored "
            "entirely, so higher values cannot take effect"
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
            "unverifiable -- report lines beyond 8192 characters are ignored "
            "entirely, so higher values cannot take effect"
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


def class_summary(results):
    """The unconfirmed claims counted per class, every class present."""
    counts = {cause.value: 0 for cause in Cause}
    for _, result in results:
        if result.cause is not None:
            counts[result.cause.value] += 1
    return counts


def executed_count(results):
    """Claims whose check ran: everything but defects and exhausted budgets.

    A defect leaves nothing to judge -- the claim cannot bind -- and a limit
    stopped the execution; the environment and residual classes had their
    check attempted.
    """
    return sum(
        1 for _, result in results if result.cause not in (Cause.DEFECT, Cause.LIMIT)
    )


def exit_code(results, strict=False):
    verdicts = [result.verdict for _, result in results]
    if Verdict.REFUTED in verdicts:
        return EXIT_REFUTED
    if any(result.cause is Cause.DEFECT for _, result in results):
        # A defect fails in both modes; it is a form violation in the report
        # or in the checked thing, not a boundary of the run.
        return EXIT_DEFECT
    if strict and any(result.cause is Cause.LIMIT for _, result in results):
        # "Could not check because of a budget" is not "checked and could not
        # decide" -- the gate gets the distinct code.
        return EXIT_LIMIT
    if Verdict.CONFIRMED not in verdicts:
        # Nothing was refuted, but nothing was proven either (all UNVERIFIABLE
        # or no claims at all): this must not read as success.
        return EXIT_NOTHING
    if strict and Verdict.UNVERIFIABLE in verdicts:
        # Strict mode reserves exit 0 for reports whose every claim was
        # actually proven; a claim that was never checked is a failure.
        return EXIT_STRICT
    return EXIT_OK


def list_types(json_mode=False):
    """Print the registered optional claim types and what they declare.

    Read from the registry (``bemyself.claimtypes.CLAIM_TYPES``), never a
    copy: ``kind``, ``needs_repo`` and ``binds_commit`` are the contract of a
    type, and the marker tokens show which report markers it claims -- the
    set an unknown marker is measured against.
    """
    entries = [
        {
            "kind": claim_type.kind,
            "needs_repo": claimtypes.type_needs_repo(claim_type.kind),
            "binds_commit": claim_type.binds_commit,
            "markers": list(claimtypes.marker_tokens(claim_type)),
        }
        for claim_type in claimtypes.CLAIM_TYPES
    ]
    if json_mode:
        print(json.dumps(entries, indent=2, ensure_ascii=True))
    else:
        for entry in entries:
            print(
                f"{entry['kind']:<10} needs_repo={str(entry['needs_repo']):<5} "
                f"binds_commit={str(entry['binds_commit']):<5} "
                f"markers={','.join(entry['markers'])}"
            )
    return EXIT_OK


def _json_payload(source, repo, results, profile=None):
    return {
        "report": source,
        "repo": repo,
        "claims": [
            {
                "kind": claim.kind,
                "line": claim.line,
                "raw": claim.raw,
                "verdict": result.verdict.value,
                "class": result.cause.value if result.cause is not None else None,
                "reason": result.reason,
                "command": result.command,
                "output": result.output,
                "sandboxed": result.sandboxed,
            }
            for claim, result in results
        ],
        "summary": summarize(results),
        "classes": class_summary(results),
        "negative_space": profiles.negative_space(results, profile),
    }


def render_text(results, profile=None):
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
    classes = class_summary(results)
    executed = executed_count(results)
    lines.append("")
    lines.append(
        "summary: "
        + ", ".join(f"{v.value}: {summary[v.value]}" for v in Verdict)
        + " ("
        + ", ".join(f"{cause.value}: {classes[cause.value]}" for cause in Cause)
        + ")"
        + f"; executed: {executed}, not executed: {len(results) - executed}"
    )
    lines.append(profiles.render_negative_space(profiles.negative_space(results, profile)))
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


def _detection_payload(detection):
    """The JSON shape of a stack detection (suggestion layer, no verdict)."""
    return {
        "stacks": list(detection.stacks),
        "files": list(detection.files),
        "suggested_commands": list(detection.commands),
        "suggested_lint_commands": list(detection.lint_commands),
    }


def _apply_project_config(parser, args):
    """Merge the project config under the explicit CLI flags.

    Provenance is one-way: an explicit CLI flag wins over the config entry,
    the config entry wins over the built-in default. ``allow`` entries are
    additive (config entries first, then the CLI's --allow). The check's
    source (--report/--section/--repo/--db) is never configurable. An
    unreadable or invalid config is a usage error (exit 2): a typo in a
    project file must not silently change nothing.

    Called for every check run (the defaults are applied here too), so the
    knob defaults live in exactly one place.
    """
    path = getattr(args, "project_config", None)
    config = {}
    if path is not None:
        try:
            config = projectconfig.load(path)
        except projectconfig.ProjectConfigError as exc:
            parser.error(str(exc))
    args.allow = list(config.get("allow", [])) + list(args.allow or [])
    if args.profile is None:
        args.profile = config.get("profile")
    if args.sandbox is None:
        args.sandbox = config.get("sandbox") or "auto"
    if args.tools is None:
        args.tools = config.get("tools")
    if args.tmp is None:
        args.tmp = config.get("tmp")


def _validate_check_args(parser, args):
    """Enforce the source contract before any file or database is touched.

    argparse cannot express the dependency pairs, so this is a usage error
    (exit 2) in every invalid combination.
    """
    if args.report is None and args.section is None and not args.detect:
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
    if args.detect and args.report is None and args.section is None:
        # Suggestion-only mode: no report, no claims, no verdict. Printing
        # what the repository looks like changes nothing about a check.
        repo = os.path.abspath(args.repo) if args.repo is not None else None
        if repo is None or not os.path.isdir(repo):
            parser.error("--detect without --report/--section requires --repo <directory>")
        detection = stackdetect.detect(_resolve_repo_root(repo))
        if args.json:
            print(json.dumps(_detection_payload(detection), indent=2, ensure_ascii=True))
        else:
            print(stackdetect.render(detection))
        return EXIT_OK
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

    # The detection is a suggestion layer: it reads marker file names under
    # the repo root and changes neither a claim nor the exit code. With a
    # report it only rides along in the output.
    detection = None
    if args.detect and repo is not None:
        detection = stackdetect.detect(repo)

    tools = None
    if args.tools is not None:
        # The manifest is host-side trust input: a defective one is a usage
        # error before any claim runs, never a silently weaker pin.
        try:
            tools = toolmanifest.load(args.tools)
        except toolmanifest.ToolManifestError as exc:
            return _source_error(args.json, source, repo, str(exc))

    claims = profiles.profile_claims(
        _apply_files_override(parse_report(text), args.files), args.profile
    )

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
            payload = _json_payload(source, repo, [], args.profile)
            if detection is not None:
                payload["detected"] = _detection_payload(detection)
            print(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            # The negative space is what keeps this run apart from one that
            # sought classes and missed them: "found nothing" and "sought
            # nothing" must not read the same.
            print(profiles.render_negative_space(profiles.negative_space([], args.profile)))
            if detection is not None:
                print(stackdetect.render(detection))
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
        artifact_root=os.path.abspath(args.artifact_root) if args.artifact_root else None,
        tools=tools,
    )
    results = [(claim, run_claim(claim, ctx)) for claim in claims]

    if args.json:
        payload = _json_payload(source, repo, results, args.profile)
        if detection is not None:
            payload["detected"] = _detection_payload(detection)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        print(sanitize(render_text(results, args.profile)))
        if detection is not None:
            print(stackdetect.render(detection))

    return exit_code(results, strict=args.strict)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "list_types", False):
        # Answered on its own: no report, no repository, no claim runs.
        return list_types(json_mode=bool(getattr(args, "json", False)))
    if args.command == "check":
        _apply_project_config(parser, args)
        _validate_check_args(parser, args)
        return run_check(args, parser)
    if args.command == "eval":
        # Imported here so the check path does not load the eval harness.
        from bemyself.eval import run_eval

        return run_eval(args)
    if args.command is None:
        parser.error("one of the commands check or eval is required")
    parser.error(f"unknown command: {args.command}")
    return EXIT_ERROR

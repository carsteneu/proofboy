"""The ``[LINT: <command>]`` claim type: a lint run against the pinned commit.

A LINT claim asserts that a lint tool ran clean on the checked-out code:
``php -l <file>``, the Symfony console linters (``lint:twig``, ``lint:yaml``,
``lint:container``) or ``composer validate``. The check runs the command in a
throwaway checkout of the bound commit with the same engine as the tests gate
(:func:`proofboy.checks._run_in_checkout`): allowlist, argument escape rules,
sandbox, output limits and the environment classification are shared, not
copied.

What the verdicts mean:

* CONFIRMED only with the tool's own positive line (e.g. "No syntax errors
  detected in <path>", "All N Twig files contain valid syntax."); exit 0
  alone is not a lint result.
* The positive line is bound to the checkout: a reported file count that
  does not match the files under the checked target, or a "php -l" line that
  names a different file than the checked one, makes the claim UNVERIFIABLE
  -- the run was redirected, and a redirected run confirms nothing.
* REFUTED when the tool reports a real failure (non-zero exit with its own
  error line).
* UNVERIFIABLE for a missing target in the commit, a missing tool or its
  dependencies (class environment), or when no commit is bound.

The lint allowlist is separate from the test allowlist (a ``[LINT]`` claim
can never smuggle a test runner, and vice versa); ``--allow`` extends both.
"""

from __future__ import annotations

import os
import re

from proofboy.model import Cause, ClaimType, Result, Verdict

# The lint commands a report may ask for. Separate from the test allowlist on
# purpose: the two claim kinds each open exactly the commands they mean.
DEFAULT_LINT_ALLOWLIST = (
    "php -l",
    "bin/console lint:twig",
    "bin/console lint:yaml",
    "bin/console lint:container",
    "php bin/console lint:twig",
    "php bin/console lint:yaml",
    "php bin/console lint:container",
    "composer validate",
)

# One lazy "anything but a bracket" capture per marker (linear pattern; see
# proofboy/claimtypes/halt.py for the reasoning).
_LINT_RE = re.compile(r"\[LINT:(?P<command>[^\]\[]*?)\]")

# The positive lines of the supported tools. Each entry is searched in the
# run output; "count" and "path" name the captured value the verdict binds
# to the checkout.
_TWIG_SUCCESS = re.compile(r"All (?P<count>\d+) \w+ files? contain valid syntax")
_YAML_SUCCESS = re.compile(r"All (?P<count>\d+) \w+ files? contain valid syntax")
_OK_IN_FILES = re.compile(r"^OK in (?P<count>\d+) files?$", re.MULTILINE)
_PHP_L_SUCCESS = re.compile(r"^No syntax errors detected in (?P<path>.+?)\s*$", re.MULTILINE)
_CONTAINER_SUCCESS = re.compile(r"The container was linted successfully")
_COMPOSER_VALID = re.compile(r"is valid")


class _LintTool:
    """One supported lint tool: how to find it and what its success is."""

    __slots__ = ("name", "prefix", "success", "suffixes", "binds_path")

    def __init__(self, name, prefix, success, suffixes=(), binds_path=False):
        self.name = name
        self.prefix = prefix
        self.success = success
        # File suffixes the tool scans under a target; a positive line that
        # reports a count is bound to the files found under that target.
        self.suffixes = suffixes
        # True for a tool whose positive line names the checked file.
        self.binds_path = binds_path


def _absolute_prefixes(tool):
    """The tool's prefixes, tolerating the "php " launcher in front."""
    if tool.prefix and tool.prefix[0] == "bin/console":
        return ((tool.prefix[0], tool.prefix[1]), ("php", tool.prefix[0], tool.prefix[1]))
    return (tool.prefix,)


_TOOLS = (
    _LintTool(
        "php -l",
        ("php", "-l"),
        (_PHP_L_SUCCESS,),
        binds_path=True,
    ),
    _LintTool(
        "lint:twig",
        ("bin/console", "lint:twig"),
        (_TWIG_SUCCESS, _OK_IN_FILES),
        suffixes=(".twig",),
    ),
    _LintTool(
        "lint:yaml",
        ("bin/console", "lint:yaml"),
        (_YAML_SUCCESS, _OK_IN_FILES),
        suffixes=(".yaml", ".yml"),
    ),
    _LintTool(
        "lint:container",
        ("bin/console", "lint:container"),
        (_CONTAINER_SUCCESS,),
    ),
    _LintTool(
        "composer validate",
        ("composer", "validate"),
        (_COMPOSER_VALID,),
    ),
)


def _tool_for(argv):
    """The tool for an argv and the length of its matched prefix."""
    for tool in _TOOLS:
        for prefix in _absolute_prefixes(tool):
            if tuple(argv[: len(prefix)]) == prefix:
                return tool, len(prefix)
    return None, 0


def parse(match, raw):
    """Fields of one [LINT] marker: the command to re-run."""
    command = match.group("command").strip()
    if not command:
        return None
    return {"command": command}


def _lint_allowlist(ctx):
    from proofboy import checks  # lazy: checks imports the type registry

    extras = tuple(
        entry for entry in ctx.allowlist if entry not in checks.DEFAULT_COMMAND_ALLOWLIST
    )
    return DEFAULT_LINT_ALLOWLIST + extras


def _targets(argv, prefix_len):
    """The non-option arguments after the tool prefix."""
    return [arg for arg in argv[prefix_len:] if not arg.startswith("-")]


def _count_suffixes(checkout, target, suffixes):
    """How many files with ``suffixes`` live under ``target``, or None."""
    path = os.path.join(checkout, target)
    if os.path.isfile(path):
        return 1 if path.endswith(tuple(suffixes)) else 0
    if not os.path.isdir(path):
        return None
    count = 0
    for root, _dirs, names in os.walk(path):
        count += sum(1 for name in names if name.endswith(tuple(suffixes)))
    return count


def _same_file(reported, target):
    return os.path.normpath(reported) == os.path.normpath(target)


def check(claim, ctx):
    from proofboy import checks  # lazy: checks imports the type registry

    guard = checks._repo_guard(ctx)
    if guard is not None:
        return guard
    command_str = claim.fields["command"]
    value = claim.fields.get("commit")
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="no commit hash to check out for the lint run",
            cause=Cause.DEFECT,
        )
    commit = checks._resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
            cause=Cause.UNVERIFIABLE,
        )
    argv, strict, problem = checks._prepare_command(command_str, _lint_allowlist(ctx))
    if problem is not None:
        return problem
    tool, prefix_len = _tool_for(argv)
    if tool is None:
        # Unreachable for allowed commands; a safety net for a future
        # allowlist entry without an adapter.
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"no lint adapter for this command: {command_str!r}",
            cause=Cause.ENVIRONMENT,
        )
    targets = _targets(argv, prefix_len)
    if tool.binds_path and not targets:
        # "php -l" lints stdin when no file is named: the run would check
        # nothing from the checkout, so it can never confirm the claim.
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"{tool.name!r} needs a file target: without one the run "
            "checks no file from the checkout",
            cause=Cause.UNVERIFIABLE,
        )
    # The starter of the tool: a path token inside the matched prefix
    # (bin/console), whether it stands alone or behind the php launcher.
    launcher = next((token for token in argv[:prefix_len] if "/" in token), None)
    facts = {}

    def pre_run(checkout, command_desc):
        # The same containment the tests gate enforces: an argument that
        # resolves outside the checkout (a committed symlink to host code or
        # a host directory) would run or scan something the commit does not
        # contain -- a lint claim must never confirm from it.
        escape = checks._symlink_escape(argv, checkout, strict=strict)
        if escape is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command argument resolves outside the checkout: {escape!r}",
                cause=Cause.DEFECT,
            )
        # A repo-provided launcher (bin/console) must come from the checkout
        # and be executable; the tool's own absence is an environment gap.
        if launcher is not None:
            path = os.path.join(checkout, launcher)
            if not os.path.isfile(path) or not os.access(path, os.X_OK):
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"the checkout's {launcher!r} is missing or not executable",
                    cause=Cause.ENVIRONMENT,
                )
        for target in targets:
            if not os.path.exists(os.path.join(checkout, target)):
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"the lint target {target!r} is not in the checked-out commit",
                    cause=Cause.ENVIRONMENT,
                )
        if tool.suffixes and targets:
            count = 0
            for target in targets:
                found = _count_suffixes(checkout, target, tool.suffixes)
                if found is None:
                    return Result(
                        Verdict.UNVERIFIABLE,
                        command_desc,
                        "",
                        f"the lint target {target!r} cannot be scanned in the checkout",
                        cause=Cause.ENVIRONMENT,
                    )
                count += found
            if count == 0:
                # The real linters report success for an empty target
                # ("All 0 ... contain valid syntax."); a run that checks no
                # file proves nothing, exactly like "0 passing" in the
                # tests gate.
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"the lint target {targets[0]!r} holds no files for this tool; "
                    "a run that checks nothing confirms nothing",
                    cause=Cause.UNVERIFIABLE,
                )
            facts["count"] = count
        return None

    outcome = checks._run_in_checkout(ctx, command_str, commit, argv, strict, pre_run=pre_run)
    if isinstance(outcome, Result):
        return outcome
    return _lint_verdict(tool, targets, facts, command_str, argv, outcome)


def _lint_verdict(tool, targets, facts, command_str, argv, outcome):
    from proofboy import checks  # lazy: checks imports the type registry

    note = outcome.note_suffix
    if outcome.returncode == 0:
        match = None
        for pattern in tool.success:
            found = pattern.search(outcome.raw_output)
            if found is not None:
                match = found
                break
        if match is None:
            # Exit 0 without the tool's own success line is not a lint result:
            # an aborted or hijacked run must not read as clean.
            return Result(
                Verdict.UNVERIFIABLE,
                outcome.command_desc,
                outcome.output,
                f"the command exited 0 but its output carries no success line of "
                f"{tool.name!r}; exit 0 alone is not a lint result" + note,
                sandboxed=outcome.sandboxed,
                cause=Cause.UNVERIFIABLE,
            )
        if "count" in facts and "count" in (match.groupdict() or {}):
            reported = int(match.group("count"))
            if reported != facts["count"]:
                return Result(
                    Verdict.UNVERIFIABLE,
                    outcome.command_desc,
                    outcome.output,
                    f"the success line reports {reported} files, but the checkout holds "
                    f"{facts['count']} matching the target; the run was redirected" + note,
                    sandboxed=outcome.sandboxed,
                    cause=Cause.DEFECT,
                )
        if tool.binds_path and targets:
            reported_path = (match.group("path") or "").strip()
            if not _same_file(reported_path, targets[0]):
                return Result(
                    Verdict.UNVERIFIABLE,
                    outcome.command_desc,
                    outcome.output,
                    f"the success line names {reported_path!r}, but the checked target is "
                    f"{targets[0]!r}; the run checked something else" + note,
                    sandboxed=outcome.sandboxed,
                    cause=Cause.DEFECT,
                )
        line = match.group(0).strip()[:160]
        return Result(
            Verdict.CONFIRMED,
            outcome.command_desc,
            outcome.output,
            f"{command_str!r} exited 0; evidence: {line}" + note,
            sandboxed=outcome.sandboxed,
        )
    if checks._missing_dependency(argv, outcome.raw_output):
        return Result(
            Verdict.UNVERIFIABLE,
            outcome.command_desc,
            outcome.output,
            "the tool's dependencies are missing in the checkout "
            "(no vendor/, no composer install); nothing was linted" + note,
            sandboxed=outcome.sandboxed,
            cause=Cause.ENVIRONMENT,
        )
    first = next((ln.strip() for ln in outcome.output.splitlines() if ln.strip()), "")
    return Result(
        Verdict.REFUTED,
        outcome.command_desc,
        outcome.output,
        f"the lint run exited {outcome.returncode}: {first[:160]}" + note,
        sandboxed=outcome.sandboxed,
    )


LINT = ClaimType(
    kind="lint",
    pattern=_LINT_RE,
    parse=parse,
    check=check,
    needs_repo=True,
    binds_commit=True,
)

"""Checkers that re-derive each claim against the repository.

Every checker returns a :class:`~bemyself.model.Result` carrying the verdict
plus the command it ran and the raw output. The doctrine is strict: a verdict
is ``CONFIRMED`` only when the check actually ran and proved the claim, and a
claim that cannot be run is ``UNVERIFIABLE`` -- never ``CONFIRMED``.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass

try:
    import resource
except ImportError:  # pragma: no cover - non-POSIX platforms
    resource = None

from bemyself.model import Cause, Claim, Result, Verdict
from bemyself import claimtypes
from bemyself.claimtypes.coloring import DEFAULT_COLORING_LIMIT
from bemyself.claimtypes.compute import DEFAULT_COMPUTE_ALLOWLIST
from bemyself.claimtypes.cycle import DEFAULT_CYCLE_LIMIT
from bemyself.claimtypes.halt import DEFAULT_HALT_LIMIT
from bemyself.claimtypes.search import DEFAULT_SEARCH_LIMIT

GIT_TIMEOUT = 60
FETCH_TIMEOUT = 30
TEST_TIMEOUT = 300
SANDBOX_MODES = ("auto", "require", "off")
SANDBOX_PROBE_TIMEOUT = 10
ORIGIN = "origin"
LAST_LINES = 5
MAX_OUTPUT_BYTES = 1 << 16
MAX_LOG_BYTES = 16 << 20

_COMMIT_HASH_RE = re.compile(r"\A[0-9a-fA-F]{4,64}\Z")
_RESOLVED_RE = re.compile(r"\A[0-9a-fA-F]{40,64}\Z")
_UNITTEST_SUMMARY_RE = re.compile(r"\bRan [1-9]\d* tests?\b")
_BRANCH_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_NO_TESTS_PATTERNS = (
    re.compile(r"\bran 0 tests?\b", re.IGNORECASE),
    re.compile(r"\bno test files\b", re.IGNORECASE),
    re.compile(r"\bno tests? (?:were |was )?(?:ran|run|found|collected|to run)\b", re.IGNORECASE),
    re.compile(r"^\s*running 0 tests\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*0 tests?\s*$", re.IGNORECASE | re.MULTILINE),
)
# Positive signals that tests actually ran. A green claim without any of
# these is UNVERIFIABLE: exiting 0 is not proof that tests executed, and a
# zero-count summary ("0 passing", "Tests: 0 total") is not either.
_TEST_EVIDENCE_PATTERNS = (
    _UNITTEST_SUMMARY_RE,
    re.compile(r"\b[1-9]\d* (?:passed|failed|errors?)\b", re.IGNORECASE),
    re.compile(r"\b[1-9]\d* (?:passing|failing)\b", re.IGNORECASE),
    re.compile(r"(?<![\w])(?:tests?|pass)\s+[1-9]\d*(?![\w])"),
    re.compile(r"\btest result:\s*\w+\s+[1-9]\d* passed", re.IGNORECASE),
    re.compile(r"^\s*tests?:\s.*\b[1-9]\d*\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ok|FAIL)\s+\S", re.MULTILINE),
    re.compile(r"^--- (?:PASS|FAIL):", re.MULTILINE),
    re.compile(r"^\s*(?:pass|fail)\s+[1-9]\d*$", re.IGNORECASE | re.MULTILINE),
    # PHPUnit: the text summary ("OK (2 tests, 3 assertions)") and the
    # machine-readable TeamCity stream (one testFinished per executed test).
    re.compile(r"\bOK \([1-9]\d* tests?, \d+ assertions?\)"),
    re.compile(r"^##teamcity\[testFinished\b", re.MULTILINE),
)
_WRITE_LIMIT_RE = re.compile(r"\[Errno 27\]|File too large")
# Legacy suites hide in skips: a "3 passed, 2 skipped" line must not read
# like a clean "3 passed". These counters ride along in the verdict text
# (display only -- they never influence the verdict itself).
_SKIP_COUNTER_RE = re.compile(
    r"\b[1-9]\d* (?:skipped|pending|ignored|incomplete)\b|\bskipped=[1-9]\d*",
    re.IGNORECASE,
)
_MISSING_MODULE_RE = re.compile(r"No module named '?([A-Za-z_][\w.]*)'?")
# "Runner present, its dependencies absent": the throwaway checkout has no
# vendor/ (no composer install). These are the startup failures of the real
# tools, not test outcomes.
_MISSING_DEPENDENCY_PATTERNS = (
    re.compile(r"Failed opening required '?[^'\s]*vendor/autoload\.php", re.IGNORECASE),
    re.compile(r"vendor/autoload\.php[^\n]*Failed to open stream", re.IGNORECASE),
    re.compile(r"Could not open input file: [^\s]*phpunit", re.IGNORECASE),
    re.compile(r'Class "PHPUnit\\', re.IGNORECASE),
    re.compile(r"please run .{0,40}composer install", re.IGNORECASE),
    re.compile(r"try running .{0,40}composer install", re.IGNORECASE),
)
_URL_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*://")
# Option names that make a runner interpret the value as code or config.
_DANGEROUS_OPTION_NAMES = frozenset(
    {
        "eval",
        "exec",
        "config",
        "script-shell",
        "node-options",
        "preload",
        "require",
        "loader",
        "experimental-loader",
        "import",
        "test-reporter",
        "toolexec",
    }
)
# Characters that only occur in arguments a shell (or a runner re-shelling a
# value) would treat specially. The verifier itself never uses a shell, but
# wrappers like make and npm hand values and arguments to sh.
_SHELL_METACHARS = frozenset(" \t\n\r;&|$`<>(){}'\"\\")
# Plain tokens of a shell-backed command: whitespace is the word boundary
# that lets a value become an extra command ("TESTS=echo Ran 1 test").
_TOKEN_METACHARS = frozenset(" \t\n\r;&|$`<>(){}[]")
_PYTHON_TUPLE_METACHARS = frozenset()
_KNOWN_RUNNER_MODULES = ("unittest", "pytest", "nose2")
_PYTHON_COMMAND_TOKENS = ("python", "python2", "python3", "pytest", "py.test")
_WRAPPER_COMMAND_TOKENS = ("make", "npm", "yarn", "bun", "pnpm", "npx")
_SANITIZED_ENV_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)

# Only test-runner prefixes may be executed from a report. A report is a
# claim, not a trusted script, so anything outside this list stays unverifiable.
DEFAULT_COMMAND_ALLOWLIST = (
    "python3 -m unittest",
    "python3 -m pytest",
    "python -m unittest",
    "python -m pytest",
    "pytest",
    "go test",
    "cargo test",
    "npm test",
    "npm run test",
    "yarn test",
    "bun test",
    "node --test",
    "make test",
    "make check",
    # PHP-family runners (P20). The runner itself is a project artifact
    # (vendor/), like node_modules: the checkout decides what runs, which is
    # the documented boundary of this gate, not a hole of the allowlist.
    "phpunit",
    "bin/phpunit",
    "vendor/bin/phpunit",
    "composer test",
    "composer run test",
)


@dataclass
class Ctx:
    # None only while no claim kind in the run declares a repo need: a checker
    # that declares one always receives a real path.
    repo: str | None
    tmp_dir: str | None
    base: str | None = None
    allowlist: tuple[str, ...] = DEFAULT_COMMAND_ALLOWLIST
    sandbox: str = "auto"
    # The largest step count a [HALT] claim may ask the simulator to execute.
    halt_limit: int = DEFAULT_HALT_LIMIT
    # The largest step count a [SEARCHED] claim may ask for.
    search_limit: int = DEFAULT_SEARCH_LIMIT
    # The largest step count a [CYCLE] claim may ask for.
    cycle_limit: int = DEFAULT_CYCLE_LIMIT
    # The largest N a [COLORING] claim may ask the checker to enumerate.
    coloring_limit: int = DEFAULT_COLORING_LIMIT
    # Command prefixes a [COMPUTE] claim may run; --allow extends it.
    compute_allowlist: tuple[str, ...] = DEFAULT_COMPUTE_ALLOWLIST
    # The directory [ARTIFACT] paths resolve against; None falls back to the
    # repository (--artifact-root overrides it).
    artifact_root: str | None = None
    # The --tools manifest: pins the [LEAN] tools by path, version and digest.
    # None means the tools come from PATH (the conservative default); a
    # manifest that does not allow a required tool leaves the claim
    # unverifiable instead.
    tools: dict | None = None


def _repo_command(ctx, *args):
    # Repo-owned config must not execute programs during verification: hooks
    # (reference-transaction via core.hooksPath) and core.fsmonitor are
    # neutralized for every command that runs inside the untrusted repo. The
    # commit-graph is a derivable cache a hostile repo can forge: a patched
    # entry lets `rev-list --parents` and `merge-base --is-ancestor` report
    # parents that the object does not have, so the cache is ignored and the
    # object store is read directly.
    return [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.commitGraph=false",
        "-C",
        ctx.repo,
        *args,
    ]


def _format(cmd):
    return " ".join(shlex.quote(part) for part in cmd)


def git_env():
    """Copy the environment but never let a caller's git variables redirect us."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Object-graph overrides in the inspected repo would forge verdicts:
    # replace refs substitute object content, grafts rewrite ancestry.
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_GRAFT_FILE"] = os.devnull
    for key in _SANITIZED_ENV_KEYS:
        env.pop(key, None)
    return env


def _run_git(args, timeout):
    """Run git without a shell; a timeout becomes a non-zero result."""
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=git_env()
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"timed out after {timeout}s")


def _git(ctx, *args, timeout=GIT_TIMEOUT):
    return _run_git(_repo_command(ctx, *args), timeout)


def _output(proc):
    return (proc.stdout + proc.stderr).strip()


def _last_lines(text, count=LAST_LINES):
    lines = text.rstrip("\n").splitlines()
    return "\n".join(lines[-count:])


def _tail_open(handle, limit=MAX_OUTPUT_BYTES):
    """Read at most ``limit`` bytes from the end of an already-open file.

    Reading through the descriptor (never by path) keeps a hostile child from
    redirecting the read after the fact.
    """
    try:
        size = os.fstat(handle.fileno()).st_size
    except OSError:
        return "", 0
    handle.seek(max(0, size - limit))
    return handle.read(limit).decode("utf-8", "replace"), size


def _rev_parse(ctx, revision):
    """Resolve any revision to a concrete commit hash, else None."""
    if not revision or revision.startswith("-"):
        return None
    proc = _git(ctx, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
    resolved = proc.stdout.strip()
    if proc.returncode == 0 and _RESOLVED_RE.match(resolved):
        return resolved
    return None


def _resolve_commit(ctx, value):
    """Resolve a report-supplied commit: it must be a hex object id."""
    value = (value or "").strip()
    if not _COMMIT_HASH_RE.match(value):
        return None
    return _rev_parse(ctx, value)


def _valid_branch(name):
    """A report-supplied branch must be a plain ref name.

    Anything git could read as an option (leading dash), a refspec (colon,
    plus) or a revision expression (``..``, ``@{``) is rejected before any
    git call sees it.
    """
    if not name or name.startswith("-") or not _BRANCH_RE.match(name):
        return False
    if ".." in name or "@{" in name or name.endswith("/") or name.endswith(".lock"):
        return False
    return all(part and not part.startswith(".") for part in name.split("/"))


def _is_dangerous_option_name(name, allow_short_prefix=False):
    """Prefix-aware: runners accept abbreviations of long option names."""
    name = name.lower()
    if name in _DANGEROUS_OPTION_NAMES:
        return True
    if allow_short_prefix:
        # Any abbreviation of a long option ("--ev" is "--eval").
        return len(name) >= 2 and any(d.startswith(name) for d in _DANGEROUS_OPTION_NAMES)
    return len(name) >= 4 and any(d.startswith(name) for d in _DANGEROUS_OPTION_NAMES)


def _path_candidates(arg, strict=True):
    """Return the path-like pieces of one argv element, or None to reject it.

    A report-supplied argument must not reach outside the fresh checkout.
    The verifier runs no shell, but wrappers (make, npm) hand values and
    arguments to sh, so for those commands every token is held to shell-word
    rules; direct runners (python, pytest, go, cargo, node) parse their own
    argv and only need the path rules. Plain tokens, key=value tokens (both
    sides), long options (abbreviations included), attached and clustered
    short-option values, whitespace/comma-split values, and values that are
    themselves options are all checked.
    """
    metachars = _TOKEN_METACHARS if strict else _PYTHON_TUPLE_METACHARS
    norm = arg.replace("\\", "/")
    pieces = []
    if norm in ("-", "--"):
        return []
    if norm.startswith("--"):
        name, sep, value = norm[2:].partition("=")
        if not re.match(r"\A[A-Za-z0-9][A-Za-z0-9-]*\Z", name):
            return None
        if _is_dangerous_option_name(name, allow_short_prefix=True):
            return None
        if any(ch in norm[2:] for ch in _SHELL_METACHARS):
            return None
        if sep:
            pieces = [value, *value.split(), *value.split(",")]
    elif norm.startswith("-"):
        body = norm[1:]
        if not body:
            return []
        if _is_dangerous_option_name(body.split("=", 1)[0]):
            return None
        if any(ch in body for ch in _SHELL_METACHARS):
            return None
        if "=" in body:
            # Attached forms: -C/abs, -C../x=1. Both readings are checked.
            value = body.split("=", 1)[1]
            pieces = [value, *value.split(), *value.split(","), body[1:]]
        elif len(body) > 1:
            # Attached and clustered forms: -sVALUE, -C.., -kf/path. Every
            # suffix that follows an option letter is a possible value.
            pieces = [body[index + 1 :] for index in range(len(body))]
    else:
        if any(ch in norm for ch in metachars):
            return None
        head, sep, value = norm.partition("=")
        if sep:
            pieces = [head, value, *value.split(), *value.split(",")]
        else:
            pieces = [norm]
    for piece in pieces:
        if piece.startswith("-") and piece not in ("-", "--"):
            if _path_candidates(piece, strict=strict) is None:
                return None
        elif _candidate_escapes(piece, strict=strict):
            return None
    return pieces


def _candidate_escapes(piece, strict=True):
    if piece.startswith("/"):
        return True
    if ".." in piece.split("/"):
        return True
    if _URL_RE.match(piece):
        return True
    # ~user expands via passwd inside shells and tools, not via HOME.
    return strict and "~" in piece


def _arg_escapes_checkout(arg, strict=True):
    """Flag command arguments that can reach outside the fresh checkout."""
    return _path_candidates(arg, strict=strict) is None


def _symlink_escape(argv, checkout, strict=True):
    """Return an argument piece whose real path leaves the checkout.

    A committed symlink (``make -C link``) would otherwise run code outside
    the checkout even though the argument is lexically harmless.
    """
    root = os.path.realpath(checkout)
    for arg in argv:
        for piece in _path_candidates(arg, strict=strict) or []:
            if not piece or piece.startswith("-"):
                continue
            resolved = os.path.realpath(os.path.join(root, piece))
            if resolved != root and not resolved.startswith(root + os.sep):
                return piece
    return None


def _is_wrapper_command(argv):
    """True for commands that re-parse arguments through a shell."""
    return bool(argv) and os.path.basename(argv[0]) in _WRAPPER_COMMAND_TOKENS


def _shows_test_evidence(output):
    return any(pattern.search(output) for pattern in _TEST_EVIDENCE_PATTERNS)


def _module_present(checkout, module):
    """True when the module name would import from the checkout itself."""
    if os.path.isfile(os.path.join(checkout, module + ".py")):
        return True
    package = os.path.join(checkout, module)
    if os.path.isdir(package):
        return any(
            os.path.isfile(os.path.join(package, marker))
            for marker in ("__init__.py", "__main__.py")
        )
    return False


def _shadowed_module(checkout, argv):
    """Return a module name the checkout would shadow for this command.

    ``python3 -m unittest`` imports from the working directory first, so a
    committed ``unittest.py`` -- or any stdlib module the runner imports at
    startup, like ``difflib`` -- would fabricate the runner's output.
    Wrapper commands (``make test``, ``npm test``) hide the runner name, so
    a known set is checked for them as well.
    """
    for index, arg in enumerate(argv[:-1]):
        if arg != "-m":
            continue
        module = argv[index + 1].split(".")[0]
        if module and module not in (".", "..") and _module_present(checkout, module):
            return module
    tokens = {os.path.basename(arg) for arg in argv}
    if any(token.startswith("python") for token in tokens) or tokens & set(
        _PYTHON_COMMAND_TOKENS
    ):
        # Frozen/builtin modules can never be shadowed by a root-level file.
        shadowable = set(sys.stdlib_module_names) - set(sys.builtin_module_names)
        names = sorted(shadowable | {"pytest", "nose2"})
    elif tokens & set(_WRAPPER_COMMAND_TOKENS):
        names = sorted(set(_KNOWN_RUNNER_MODULES) | {"difflib"})
    else:
        return None
    for name in names:
        if _module_present(checkout, name):
            return name
    return None


def _display_name(name):
    """Make a repository-controlled name safe to print on one line."""
    return name.translate({code: "?" for code in (*range(0x20), 0x7F)})


def _claims_no_tests(output):
    return any(pattern.search(output) for pattern in _NO_TESTS_PATTERNS)


def _missing_dependency(argv, output):
    """True when a PHP-family runner's dependencies are visibly absent.

    A checkout without vendor/ is an environment gap (no composer install),
    never a defect and never a confirmation. The output is repo-controlled,
    so the phrases only count when the command itself is a PHP-family
    runner and no test evidence exists; a repo can print such a phrase to
    downgrade a REFUTED to UNVERIFIABLE, which the README documents as a
    boundary (like the missing Python runner module).
    """
    if not argv or _shows_test_evidence(output):
        return False
    tool = os.path.basename(argv[0])
    if tool not in ("composer", "phpunit") and not tool.startswith("php"):
        return False
    return any(pattern.search(output) for pattern in _MISSING_DEPENDENCY_PATTERNS)


def _evidence_summary(output):
    """The positive test evidence in one line, with its counters appended.

    The first line that carries an evidence pattern is shown, followed by
    the skip/pending/ignored counters found in the output (deduplicated,
    bounded). A counter the evidence line already carries is not repeated.
    Display text only: it makes a green verdict readable -- "3 passed,
    2 skipped" must not look like "3 passed" -- and never feeds a verdict.
    """
    line = ""
    for candidate in output.splitlines():
        stripped = candidate.strip()
        if stripped and _shows_test_evidence(stripped):
            line = stripped[:160]
            break
    counters = []
    for match in _SKIP_COUNTER_RE.finditer(output):
        token = match.group(0)
        if any(token.lower() == seen.lower() for seen in counters):
            continue
        counters.append(token)
        if len(counters) >= 4:
            break
    counters = [token for token in counters if token.lower() not in line.lower()]
    pieces = []
    if line:
        pieces.append(f"evidence: {line}")
    if counters:
        pieces.append("counters: " + ", ".join(counters))
    return "; ".join(pieces)


def _test_env(checkout):
    """A minimal environment: the report's command must not read the verifier's."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": checkout,
        "TMPDIR": checkout,
        "GIT_TERMINAL_PROMPT": "0",
        # Without this, HOME=<checkout> would let a committed
        # .local/lib/python*/site-packages/usercustomize.py inject code.
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def find_bwrap():
    """The bubblewrap binary, or None when it is not on PATH."""
    path = shutil.which("bwrap")
    return os.path.abspath(path) if path else None


def _sandbox_prefix(program, checkout, extra_ro_binds=(), cwd=None):
    """The bwrap wrapper for one test run.

    The filesystem root is bound read-only; only the throwaway checkout is
    writable. The command gets its own network, PID and UTS namespaces, so it
    can neither reach the host network nor see host processes. ``--die-with-parent``
    keeps a sandbox from outliving the verifier. ``extra_ro_binds`` stacks
    further read-only mounts (source, target) over the root bind; the [LEAN]
    checker uses them to carry a working-tree dependency cache into the
    throwaway checkout under the same path. ``cwd`` is the working directory
    inside the sandbox (default: the checkout); [LEAN] runs lake in the
    project directory.
    """
    prefix = [
        program,
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        # The ro root leaves host runtime sockets (D-Bus, systemd, docker)
        # reachable: --unshare-net separates IP networking, not AF_UNIX
        # pathname sockets. An empty /run hides them; /var/run follows
        # because it is a symlink to /run.
        "--tmpfs",
        "/run",
        "--bind",
        checkout,
        checkout,
    ]
    for source, target in extra_ro_binds:
        prefix += ["--ro-bind", source, target]
    prefix += [
        "--unshare-net",
        "--unshare-pid",
        "--unshare-uts",
        "--chdir",
        cwd or checkout,
        "--",
    ]
    return prefix


def _sandbox_display(command_str):
    """The sandboxed command line as shown in a result."""
    return " ".join(_sandbox_prefix("bwrap", "<checkout>")) + " " + command_str


def _sandbox_probe(bwrap, checkout):
    """Return None when bwrap can start the sandbox, else a failure description.

    A bwrap that exists but cannot create its namespaces (apparmor, kernel
    settings) is not available in any meaningful sense; probing separates
    "the sandbox does not work" from "the test command failed", which would
    otherwise turn every test run into a false REFUTED.
    """
    try:
        proc = subprocess.run(
            # An absolute interpreter path, not a PATH lookup: the probe must
            # not fail on a host whose PATH lacks the binary it would use.
            _sandbox_prefix(bwrap, checkout) + [sys.executable, "-c", ""],
            cwd=checkout,
            env=_test_env(checkout),
            capture_output=True,
            text=True,
            timeout=SANDBOX_PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"the sandbox probe timed out after {SANDBOX_PROBE_TIMEOUT}s"
    except OSError as exc:
        return f"the sandbox probe could not run: {exc}"
    if proc.returncode != 0:
        return _last_lines(_output(proc)) or f"the sandbox probe exited {proc.returncode}"
    return None


def _child_preexec():
    # Own process group so a timeout can take the whole tree down; own file
    # limit so a runaway child cannot fill the disk.
    os.setsid()
    if resource is not None:
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_LOG_BYTES, MAX_LOG_BYTES))
        except (OSError, ValueError):
            pass


def _kill_process_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass


def _repo_guard(ctx):
    """Return an UNVERIFIABLE result if the repo is unusable, else None."""
    if not os.path.isdir(ctx.repo):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"repo path does not exist: {ctx.repo}",
            cause=Cause.ENVIRONMENT,
        )
    proc = _git(ctx, "rev-parse", "--git-dir")
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "rev-parse", "--git-dir")),
            output=_output(proc),
            reason=f"not a git repository: {ctx.repo}",
            cause=Cause.ENVIRONMENT,
        )
    return None


def _is_allowed(command, allowlist):
    normalized = " ".join(command.split())
    return any(
        normalized == prefix or normalized.startswith(prefix + " ") for prefix in allowlist
    )


def needs_repo(checker):
    """Declaration: this checker re-derives its claim in a git repository.

    The CLI requires ``--repo`` for a report only while some occurring claim
    kind declares this (see :func:`kind_needs_repo`).
    """
    checker.needs_repo = True
    return checker


@needs_repo
def check_commit_exists(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    value = (claim.fields.get("commit") or "").strip()
    if not _COMMIT_HASH_RE.match(value):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a commit hash: {value!r}",
            cause=Cause.DEFECT,
        )
    revision = f"{value}^{{commit}}"
    command = _format(_repo_command(ctx, "rev-parse", "--verify", "--quiet", revision))
    resolved = _rev_parse(ctx, value)
    if resolved is not None:
        return Result(Verdict.CONFIRMED, command, resolved, f"commit {value} resolves to {resolved}")
    return Result(Verdict.REFUTED, command, "", f"commit {value} does not exist in {ctx.repo}")


@needs_repo
def check_branch_pushed(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    branch = claim.fields["branch"] or ""
    if not _valid_branch(branch):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a valid branch name: {branch!r}",
            cause=Cause.DEFECT,
        )
    value = claim.fields.get("commit")
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="report names a branch but no commit hash",
            cause=Cause.DEFECT,
        )

    remotes_proc = _git(ctx, "remote")
    remotes = remotes_proc.stdout.split()
    if not remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            reason="no git remote configured; cannot verify the branch was pushed",
            cause=Cause.ENVIRONMENT,
        )
    if ORIGIN not in remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            output=_output(remotes_proc),
            reason=f"no '{ORIGIN}' remote (found: {', '.join(remotes)})",
            cause=Cause.ENVIRONMENT,
        )

    commit = _resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
            cause=Cause.UNVERIFIABLE,
        )

    # Programs named by the repo's own config must not run during
    # verification. Hooks and fsmonitor are disabled via _repo_command,
    # upload-pack and ssh via fetch arguments and http.proxy via -c; gitProxy
    # and askpass have no working override, so a fetch is refused when a repo
    # sets them.
    for key in ("core.gitProxy", "core.askpass"):
        cfg = _git(ctx, "config", "--local", "--get", key)
        if cfg.returncode == 0 and cfg.stdout.strip():
            return Result(
                Verdict.UNVERIFIABLE,
                command=_format(_repo_command(ctx, "config", "--local", "--get", key)),
                output=_output(cfg),
                reason=f"repo config sets {key}; refusing to fetch through a repo-configured program",
                cause=Cause.ENVIRONMENT,
            )
    proxies = _git(ctx, "config", "--local", "--get-regexp", r"^http\..*\.proxy$")
    if proxies.returncode == 0 and proxies.stdout.strip():
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "config", "--local", "--get-regexp", "http-proxy")),
            output=_output(proxies),
            reason="repo config sets a URL-specific http proxy; refusing to fetch through it",
            cause=Cause.ENVIRONMENT,
        )

    # Fetch refs/heads/<branch> into a private ref: a tag or remote HEAD of
    # the same name must not confirm a branch claim, and a private ref keeps
    # concurrent runs from judging each other's fetch state.
    private_ref = f"refs/bemyself-verify/{os.urandom(8).hex()}"
    fetch_args = [
        "-c",
        "core.sshCommand=ssh",
        "-c",
        "credential.helper=",
        "-c",
        "http.proxy=",
        "-c",
        "protocol.ext.allow=never",
        "fetch",
        "--quiet",
        "--no-tags",
        "--no-write-fetch-head",
        "--upload-pack=git-upload-pack",
        ORIGIN,
        f"+refs/heads/{branch}:{private_ref}",
    ]
    try:
        fetch = _git(ctx, *fetch_args, timeout=FETCH_TIMEOUT)
        if fetch.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command=_format(_repo_command(ctx, *fetch_args)),
                output=_output(fetch),
                reason=f"could not fetch refs/heads/{branch} to confirm the push",
                cause=Cause.UNVERIFIABLE,
            )
        tip = _rev_parse(ctx, private_ref)
        if tip is None:
            return Result(
                Verdict.UNVERIFIABLE,
                reason=f"{private_ref} did not resolve to a commit after fetch",
                cause=Cause.UNVERIFIABLE,
            )
        proc = _git(ctx, "merge-base", "--is-ancestor", commit, private_ref)
        command = _format(_repo_command(ctx, "merge-base", "--is-ancestor", commit, private_ref))
        if proc.returncode == 0:
            return Result(
                Verdict.CONFIRMED, command, "", f"{commit} is reachable from {branch} on {ORIGIN}"
            )
        if proc.returncode == 1:
            return Result(
                Verdict.REFUTED, command, "", f"{commit} is not reachable from {branch} on {ORIGIN}"
            )
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            _output(proc),
            reason=f"could not compare {commit} with {branch} on {ORIGIN}",
            cause=Cause.UNVERIFIABLE,
        )
    finally:
        # Best effort: the private verification ref must not linger.
        _git(ctx, "update-ref", "-d", private_ref)


@needs_repo
def check_diff_scope(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    if not ctx.base:
        # Without an explicit base, `head^` would compare only the last commit
        # and could confirm a branch-wide scope while missing earlier changes.
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no base revision given; pass --base to compare the diff scope",
            cause=Cause.ENVIRONMENT,
        )
    planned = {name[2:] if name.startswith("./") else name for name in claim.fields.get("planned") or ()}
    planned.discard("")
    if not planned:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no planned file list to compare against",
            cause=Cause.DEFECT,
        )

    base = _rev_parse(ctx, ctx.base)
    if base is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"base revision does not resolve: {ctx.base!r}",
            cause=Cause.ENVIRONMENT,
        )
    head_value = claim.fields.get("head")
    head = _resolve_commit(ctx, head_value)
    if head is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"head {head_value!r} does not resolve to a commit",
            # A missing [COMMIT] to bind is the report's defect; a present but
            # unresolvable one is a state the verifier cannot pin.
            cause=Cause.DEFECT if not head_value else Cause.UNVERIFIABLE,
        )

    diff_args = [
        "-c",
        "core.quotePath=false",
        "diff",
        "--name-only",
        "-z",
        f"{base}..{head}",
    ]
    proc = _git(ctx, *diff_args)
    command = _format(_repo_command(ctx, *diff_args))
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            _output(proc),
            reason=f"could not diff {base}..{head}",
            cause=Cause.UNVERIFIABLE,
        )

    changed = {name for name in proc.stdout.split("\0") if name.strip()}
    output = "\n".join(sorted(changed))
    if not changed:
        return Result(
            Verdict.REFUTED,
            command,
            "",
            f"no changed files between {base} and {head}; nothing was changed in scope",
        )
    extra = sorted(changed - planned)
    missing = sorted(planned - changed)
    if extra or missing:
        details = []
        if extra:
            details.append("changed but not planned: " + ", ".join(map(_display_name, extra)))
        if missing:
            details.append("planned but unchanged: " + ", ".join(map(_display_name, missing)))
        return Result(Verdict.REFUTED, command, output, "diff scope mismatch; " + "; ".join(details))
    return Result(
        Verdict.CONFIRMED,
        command,
        output,
        f"the {len(changed)} changed files match the planned scope exactly",
    )


def _prepare_command(command_str, allowlist):
    """Validate a report command: ``(argv, strict, Result|None)``.

    Shared by every checker that runs a report command: the allowlist gate,
    the argv parse and the escape rules (absolute paths, ``..``, symlink
    targets outside the checkout) are the same everywhere; only the
    allowlist differs. ``argv`` is None when the third element is a Result.
    """
    if not _is_allowed(command_str, allowlist):
        return None, False, Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"command is not in the allowlist: {command_str!r}",
            cause=Cause.ENVIRONMENT,
        )
    try:
        argv = shlex.split(command_str)
    except ValueError as exc:
        return None, False, Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"could not parse command: {exc}",
            cause=Cause.DEFECT,
        )
    if not argv:
        return None, False, Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="empty command",
            cause=Cause.DEFECT,
        )
    strict = _is_wrapper_command(argv)
    escaping = [arg for arg in argv if _arg_escapes_checkout(arg, strict=strict)]
    if escaping:
        # Only the cwd is confined; an argument pointing outside the fresh
        # checkout would run code the verified commit never contained.
        return None, strict, Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"unsafe command argument: {escaping[0]!r}",
            cause=Cause.DEFECT,
        )
    return argv, strict, None


class _RunOutcome:
    """The observable outcome of one sandboxed run in a throwaway checkout.

    ``checkout`` is the directory the command ran in; the caller may use it
    for path comparisons after the run (it is already removed by then, so
    only its string is meaningful). ``sandboxed`` stays None when the run
    never started.
    """

    __slots__ = (
        "command_desc",
        "checkout",
        "returncode",
        "raw_output",
        "output",
        "sandboxed",
        "note_suffix",
    )

    def __init__(self, command_desc, checkout, returncode, raw_output, output, sandboxed, note_suffix):
        self.command_desc = command_desc
        self.checkout = checkout
        self.returncode = returncode
        self.raw_output = raw_output
        self.output = output
        self.sandboxed = sandboxed
        self.note_suffix = note_suffix


def _run_in_checkout(ctx, command_str, commit, argv, strict, pre_run=None):
    """Run ``argv`` in a throwaway checkout of ``commit``, sandboxed.

    The shared engine of the command-running checkers (tests, lint): the
    sandbox decision, the clone + checkout of the claimed commit, the
    optional ``pre_run(checkout, command_desc)`` hook (returning a Result
    aborts the run), the sandbox probe, the run itself and the capped
    read-back of its output all live here once. Returns a Result for every
    failure before or while starting the run, else a :class:`_RunOutcome`
    (with the checkout already cleaned up).
    """
    # require is a hard gate: when no bwrap is on PATH the command is never
    # run, not even unsandboxed -- a fallback would be silent by construction.
    mode = ctx.sandbox
    if mode not in SANDBOX_MODES:
        # A typo like "Require" must not degrade into an auto fallback.
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"unknown sandbox mode: {mode!r}",
            cause=Cause.ENVIRONMENT,
        )
    bwrap = None if mode == "off" else find_bwrap()
    if mode == "require" and bwrap is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="sandbox required (--sandbox=require) but bwrap is not available in PATH; "
            "refusing to run the command unsandboxed",
            cause=Cause.ENVIRONMENT,
        )
    try:
        os.makedirs(ctx.tmp_dir, exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="checkout-", dir=ctx.tmp_dir)
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"cannot create a throwaway checkout under {ctx.tmp_dir}: {exc}",
            cause=Cause.ENVIRONMENT,
        )
    try:
        log_fd, log_path = tempfile.mkstemp(prefix="run-", suffix=".log", dir=ctx.tmp_dir)
    except OSError as exc:
        shutil.rmtree(checkout, ignore_errors=True)
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"cannot create a log file under {ctx.tmp_dir}: {exc}",
            cause=Cause.ENVIRONMENT,
        )
    command_desc = f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && {command_str}"
    log = None
    try:
        clone = _run_git(
            ["git", "clone", "--quiet", "--no-hardlinks", ctx.repo, checkout], GIT_TIMEOUT
        )
        if clone.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(clone),
                reason="could not create a clean checkout",
                cause=Cause.UNVERIFIABLE,
            )
        co = _run_git(["git", "-C", checkout, "checkout", "--quiet", commit], GIT_TIMEOUT)
        if co.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(co),
                reason=f"could not check out {commit}",
                cause=Cause.UNVERIFIABLE,
            )
        if pre_run is not None:
            abort = pre_run(checkout, command_desc)
            if abort is not None:
                return abort
        # A bwrap that exists but cannot start a sandbox is not usable; the
        # probe must pass before the command runs, or require stays hard and
        # auto falls back with an explicit note instead of misreporting the
        # command as failed.
        sandbox_error = _sandbox_probe(bwrap, checkout) if bwrap is not None else None
        if mode == "require" and sandbox_error is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                "sandbox required (--sandbox=require) but bwrap could not start a sandbox: "
                f"{sandbox_error}; refusing to run the command unsandboxed",
                cause=Cause.ENVIRONMENT,
            )
        sandboxed = bwrap is not None and sandbox_error is None
        if sandboxed:
            run_argv = _sandbox_prefix(bwrap, checkout) + argv
            note = "sandboxed with bwrap"
            command_desc = (
                f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && "
                + _sandbox_display(command_str)
            )
        elif mode == "off":
            run_argv = argv
            note = "not sandboxed: --sandbox=off"
        elif bwrap is None:
            run_argv = argv
            note = "not sandboxed: bwrap not available"
        else:
            run_argv = argv
            note = "not sandboxed: bwrap cannot start a sandbox"
        note_suffix = f" ({note})"
        # The command output goes to a private, unpredictable file: the child
        # can neither pre-plant a symlink there nor fill the disk (RLIMIT_FSIZE),
        # and the result is read back through the same descriptor, never by path.
        log = os.fdopen(log_fd, "w+b")
        log_fd = None
        try:
            proc = subprocess.Popen(
                run_argv,
                cwd=checkout,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=_test_env(checkout),
                preexec_fn=_child_preexec,
            )
        except FileNotFoundError as exc:
            # Only bwrap itself can be missing here (the probe ran the same
            # binary path moments ago); the command never executed.
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command not found: {exc}" + note_suffix,
                cause=Cause.ENVIRONMENT,
            )
        except PermissionError as exc:
            # A repo-provided runner (bin/console, vendor/bin/phpunit) whose
            # exec bit is unset: the command never ran, so it says nothing
            # about the code.
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command not executable: {exc}" + note_suffix,
                cause=Cause.ENVIRONMENT,
            )
        try:
            returncode = proc.wait(timeout=TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc)
            proc.wait()
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _last_lines(_tail_open(log)[0]),
                f"command timed out after {TEST_TIMEOUT}s (built-in time limit)" + note_suffix,
                sandboxed=sandboxed,
                cause=Cause.LIMIT,
            )
        raw_output, log_size = _tail_open(log)
        output = _last_lines(raw_output)
        if (
            returncode is not None
            and hasattr(signal, "SIGXFSZ")
            and returncode == -signal.SIGXFSZ
        ):
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                output,
                f"command output exceeded the per-file limit of {MAX_LOG_BYTES} bytes "
                "(built-in output limit)" + note_suffix,
                sandboxed=sandboxed,
                cause=Cause.LIMIT,
            )
        # CPython ignores SIGXFSZ and dies with another code once the write
        # limit is hit, so the capped file is the reliable signal.
        if log_size >= MAX_LOG_BYTES:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                output,
                f"command output reached the per-file limit of {MAX_LOG_BYTES} bytes "
                "(built-in output limit); "
                "the run cannot be verified from truncated output" + note_suffix,
                sandboxed=sandboxed,
                cause=Cause.LIMIT,
            )
        return _RunOutcome(
            command_desc, checkout, returncode, raw_output, output, sandboxed, note_suffix
        )
    finally:
        if log is not None:
            try:
                log.close()
            except OSError:
                pass
        if log_fd is not None:
            try:
                os.close(log_fd)
            except OSError:
                pass
        shutil.rmtree(checkout, ignore_errors=True)
        try:
            os.unlink(log_path)
        except OSError:
            pass


@needs_repo
def check_tests_green(claim: Claim, ctx: Ctx) -> Result:
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    command_str = claim.fields["command"]
    claimed_exit = claim.fields["claimed_exit"]
    value = claim.fields.get("commit")
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="no commit hash to check out for the test run",
            cause=Cause.DEFECT,
        )
    commit = _resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
            cause=Cause.UNVERIFIABLE,
        )
    argv, strict, problem = _prepare_command(command_str, ctx.allowlist)
    if problem is not None:
        return problem

    def pre_run(checkout, command_desc):
        shadow = _shadowed_module(checkout, argv)
        if shadow is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"the checkout shadows the {shadow!r} module; the runner would not be the real one",
                cause=Cause.ENVIRONMENT,
            )
        escape = _symlink_escape(argv, checkout, strict=strict)
        if escape is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command argument resolves outside the checkout: {escape!r}",
                cause=Cause.DEFECT,
            )
        return None

    outcome = _run_in_checkout(ctx, command_str, commit, argv, strict, pre_run=pre_run)
    if isinstance(outcome, Result):
        return outcome
    return _tests_verdict(claim, claimed_exit, argv, outcome)


def _tests_verdict(claim, claimed_exit, argv, outcome):
    """The verdict of a completed tests run: green or an exit claim."""
    returncode = outcome.returncode
    raw_output = outcome.raw_output
    output = outcome.output
    command_desc = outcome.command_desc
    note_suffix = outcome.note_suffix
    sandboxed = outcome.sandboxed
    command_str = claim.fields["command"]
    if returncode == claimed_exit:
        if claim.kind == "tests_green":
            # Exiting 0 is not proof that tests ran: require a positive
            # test summary, and treat "no tests" output as unverifiable.
            if _shows_test_evidence(raw_output):
                return Result(
                    Verdict.CONFIRMED,
                    command_desc,
                    output,
                    f"{command_str!r} exited {returncode} as claimed; "
                    + _evidence_summary(raw_output)
                    + note_suffix,
                    sandboxed=sandboxed,
                )
            elif _claims_no_tests(raw_output):
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    output,
                    "the command exited 0 but reported that no tests were executed" + note_suffix,
                    sandboxed=sandboxed,
                    cause=Cause.UNVERIFIABLE,
                )
            else:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    output,
                    "the command exited 0 but its output shows no evidence that tests ran" + note_suffix,
                    sandboxed=sandboxed,
                    cause=Cause.UNVERIFIABLE,
                )
        return Result(
            Verdict.CONFIRMED,
            command_desc,
            output,
            f"{command_str!r} exited {returncode} as claimed" + note_suffix,
            sandboxed=sandboxed,
        )
    # A missing runner module is an environment gap, not evidence that the
    # tests failed -- but only when the report's own command names it.
    # Child output is repo-controlled and must not be able to turn a
    # REFUTED into an UNVERIFIABLE by printing the phrase.
    missing_match = _MISSING_MODULE_RE.search(raw_output)
    if missing_match is not None:
        missing = missing_match.group(1).split(".")[0]
        runner_module = None
        for index, arg in enumerate(argv[:-1]):
            if arg == "-m":
                runner_module = argv[index + 1].split(".")[0]
                break
        if runner_module is not None and missing == runner_module:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                output,
                f"the runner module {missing!r} is not available in this environment" + note_suffix,
                sandboxed=sandboxed,
                cause=Cause.ENVIRONMENT,
            )
    # A PHP-family runner whose dependencies are absent from the checkout
    # (no vendor/, no composer install) is an environment gap: the run
    # says nothing about the code, so it must not read as a test failure.
    if _missing_dependency(argv, raw_output):
        return Result(
            Verdict.UNVERIFIABLE,
            command_desc,
            output,
            "the runner's dependencies are missing in the checkout "
            "(no vendor/, no composer install); the run stopped before any test"
            + note_suffix,
            sandboxed=sandboxed,
            cause=Cause.ENVIRONMENT,
        )
    if _WRITE_LIMIT_RE.search(raw_output):
        return Result(
            Verdict.UNVERIFIABLE,
            command_desc,
            output,
            f"the run hit the per-file write limit of {MAX_LOG_BYTES} bytes "
            "(built-in limit); its outcome cannot be verified" + note_suffix,
            sandboxed=sandboxed,
            cause=Cause.LIMIT,
        )
    return Result(
        Verdict.REFUTED,
        command_desc,
        output,
        f"claimed exit {claimed_exit}, actually exited {returncode}" + note_suffix,
        sandboxed=sandboxed,
    )

# The report values of a [MERGE] marker that name no branch: a yesloop DONE
# payload uses [MERGE: no|pending-PR|blocked-PR] as a status token, and a
# status is not a branch claim. HEAD is a revision, not a branch (git refuses
# to create refs/heads/HEAD), and resolving it would compare against
# origin/HEAD's branch. Any such value stays UNVERIFIABLE -- never a
# confirmation by imagination.
_MERGE_STATUS_VALUES = frozenset({"", "-", "no", "none", "pending-pr", "blocked-pr", "head"})


def _merge_target_branch(ctx):
    """The branch a merge landed on, as ``(name, commit)``, or None.

    Order: the remote's default branch (``refs/remotes/origin/HEAD``), a
    local main or master, the current branch. Without any resolvable
    candidate the target is unknown and the merge claim stays UNVERIFIABLE --
    the target is never guessed.
    """
    proc = _git(ctx, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    name = proc.stdout.strip() if proc.returncode == 0 else ""
    if name:
        commit = _rev_parse(ctx, name)
        if commit is not None:
            return name, commit
    for candidate in ("main", "master"):
        commit = _rev_parse(ctx, f"refs/heads/{candidate}")
        if commit is not None:
            return candidate, commit
    proc = _git(ctx, "symbolic-ref", "--short", "HEAD")
    if proc.returncode == 0 and proc.stdout.strip():
        commit = _rev_parse(ctx, "HEAD")
        if commit is not None:
            return proc.stdout.strip(), commit
    return None


# The [MERGE] claim: the bound commit is the merge of the named branch. The
# checks are structural and local (no fetch): the commit must exist and have
# exactly two parents, one parent must be the tip of the named branch (a
# local branch first, then the origin-tracking ref of the same name), and the
# other parent must lie on the target branch or be its tip. A contradiction
# is REFUTED and names the parents that really exist; a branch whose tip
# moved on after the merge leaves the claim UNVERIFIABLE (no object records
# where a branch pointed when the merge was made). A claim without a branch
# (a status token like "no") or without the one hash-shaped [COMMIT] marker
# stays UNVERIFIABLE. The checker declares no repository need, so a report
# that only carries [MERGE: no] keeps running without --repo; without a
# repository the claim is UNVERIFIABLE.
def check_merge(claim: Claim, ctx: Ctx) -> Result:
    if ctx.repo is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no repository given; a [MERGE] claim needs --repo to compare the merge parents",
            cause=Cause.ENVIRONMENT,
        )
    guard = _repo_guard(ctx)
    if guard is not None:
        return guard
    branch = (claim.fields.get("value") or "").strip()
    if branch.lower() in _MERGE_STATUS_VALUES:
        # A status token ("no", "pending-PR") names no branch: that is not a
        # defective claim, it simply carries nothing to check.
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the claim names no branch to check: {branch!r}",
        )
    if not _valid_branch(branch):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a valid branch name: {branch!r}",
            cause=Cause.DEFECT,
        )
    value = (claim.fields.get("commit") or "").strip()
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no commit hash to bind the merge claim; the report needs one hash-shaped [COMMIT] marker",
            cause=Cause.DEFECT,
        )
    if not _COMMIT_HASH_RE.match(value):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"not a commit hash: {value!r}",
            cause=Cause.DEFECT,
        )
    resolution = _format(
        _repo_command(ctx, "rev-parse", "--verify", "--quiet", f"{value}^{{commit}}")
    )
    commit = _rev_parse(ctx, value)
    if commit is None:
        return Result(
            Verdict.REFUTED, resolution, "", reason=f"commit {value} does not exist in {ctx.repo}"
        )
    parents_args = ("rev-list", "--parents", "-n", "1", commit)
    parents_proc = _git(ctx, *parents_args)
    command = _format(_repo_command(ctx, *parents_args))
    if parents_proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            _output(parents_proc),
            reason=f"could not read the parents of {commit[:12]}",
            cause=Cause.UNVERIFIABLE,
        )
    parents = parents_proc.stdout.split()[1:]
    actual = ", ".join(parent[:12] for parent in parents) or "none"
    if len(parents) != 2:
        return Result(
            Verdict.REFUTED,
            command,
            parents_proc.stdout.strip(),
            f"not a two-parent merge: {commit[:12]} has {len(parents)} parent(s) ({actual})",
        )
    tip = _rev_parse(ctx, f"refs/heads/{branch}") or _rev_parse(
        ctx, f"refs/remotes/origin/{branch}"
    )
    if tip is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            parents_proc.stdout.strip(),
            f"branch {branch!r} does not resolve in {ctx.repo} (neither locally nor on origin)",
            cause=Cause.UNVERIFIABLE,
        )
    if tip not in parents:
        # The named branch is not a merge parent. Two findings are provable
        # from that state: the commit lies on the named branch itself (a
        # branch is not merged into a commit it contains), or no parent of
        # the commit belongs to the branch's history at all (the merge had
        # nothing to do with that branch). In between -- the tip moved on
        # after the merge -- the claim may well be true for the state at
        # merge time, which no object records, so it stays UNVERIFIABLE
        # instead of a refutation by imagination.
        on_branch = _git(ctx, "merge-base", "--is-ancestor", commit, tip)
        if on_branch.returncode == 0:
            return Result(
                Verdict.REFUTED,
                command,
                parents_proc.stdout.strip(),
                f"{commit[:12]} lies on {branch!r} (tip {tip[:12]}); it is not a merge "
                f"of it, its parents are {actual}",
            )
        for parent in parents:
            if _git(ctx, "merge-base", "--is-ancestor", parent, tip).returncode == 0:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command,
                    parents_proc.stdout.strip(),
                    f"the tip of {branch!r} moved on ({tip[:12]}); parent {parent[:12]} "
                    f"lies in its history, so {commit[:12]} cannot be pinned as its merge",
                    cause=Cause.UNVERIFIABLE,
                )
        return Result(
            Verdict.REFUTED,
            command,
            parents_proc.stdout.strip(),
            f"no parent of {commit[:12]} belongs to {branch!r} (tip {tip[:12]}); "
            f"the parents are {actual}",
        )
    other = parents[1] if parents[0] == tip else parents[0]
    target = _merge_target_branch(ctx)
    if target is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command,
            parents_proc.stdout.strip(),
            reason="cannot determine the target branch (no origin/HEAD, no local main or master, "
            "no current branch); the other parent cannot be compared",
            cause=Cause.ENVIRONMENT,
        )
    target_name, target_commit = target
    ancestor_args = ("merge-base", "--is-ancestor", other, target_commit)
    ancestor = _git(ctx, *ancestor_args)
    ancestor_command = _format(_repo_command(ctx, *ancestor_args))
    if ancestor.returncode == 0:
        return Result(
            Verdict.CONFIRMED,
            ancestor_command,
            parents_proc.stdout.strip(),
            f"{commit[:12]} is a merge of {branch!r}: parent {tip[:12]} is its tip and "
            f"parent {other[:12]} lies on {target_name}",
        )
    if ancestor.returncode == 1:
        return Result(
            Verdict.REFUTED,
            ancestor_command,
            parents_proc.stdout.strip(),
            f"the other parent {other[:12]} of {commit[:12]} lies on no {target_name}: "
            f"its tip {target_commit[:12]} does not contain it; the parents are {actual}",
        )
    return Result(
        Verdict.UNVERIFIABLE,
        ancestor_command,
        _output(ancestor),
        reason=f"could not compare {other[:12]} with {target_name}",
        cause=Cause.UNVERIFIABLE,
    )


def check_unknown_marker(claim: Claim, ctx: Ctx) -> Result:
    """A marker token no registered claim type claims: a form violation.

    The report parser (bemyself/report.py) emits this claim; nothing about it
    can be checked against the world, so the verdict is the defect itself.
    """
    token = claim.fields.get("token") or ""
    return Result(
        Verdict.UNVERIFIABLE,
        reason=(
            f"unknown marker token {token!r}: no registered claim type claims "
            "it (see --list-types)"
        ),
        cause=Cause.DEFECT,
    )


def check_profile(claim: Claim, ctx: Ctx) -> Result:
    """A report that misses a class its profile requires: a defect.

    The profile module (bemyself/profiles.py) emits this claim when the
    report's classes do not satisfy the declared profile; the missing classes
    ride in the claim's fields, so the verdict names the report's fault.
    """
    name = claim.fields.get("profile") or ""
    missing = claim.fields.get("missing") or ()
    labels = ", ".join("/".join(requirement) for requirement in missing)
    if len(missing) == 1:
        required = f"a claim of class {labels}"
    else:
        required = f"claims of classes {labels}"
    return Result(
        Verdict.UNVERIFIABLE,
        reason=f"profile {name!r} requires {required}; the report has none",
        cause=Cause.DEFECT,
    )


REGISTRY = {
    "commit_exists": check_commit_exists,
    "branch_pushed": check_branch_pushed,
    "diff_scope": check_diff_scope,
    "tests_green": check_tests_green,
    "tests_exit": check_tests_green,
    "merge": check_merge,
    "unknown_marker": check_unknown_marker,
    "profile": check_profile,
}


def kind_needs_repo(kind: str, registry: dict | None = None) -> bool:
    """Whether the checker for ``kind`` declares a repository need.

    Resolution mirrors :func:`run_claim`: the built-in registry first, then
    the optional claim types. A kind without any checker needs nothing -- it
    stays UNVERIFIABLE ("no checker registered").
    """
    registry = REGISTRY if registry is None else registry
    checker = registry.get(kind)
    if checker is None:
        return claimtypes.type_needs_repo(kind)
    return bool(getattr(checker, "needs_repo", False))


def run_claim(claim: Claim, ctx: Ctx, registry: dict | None = None) -> Result:
    """Run one claim through the checker registry.

    Built-in kinds resolve through :data:`REGISTRY`; a kind that is not a
    built-in is looked up among the optional claim types
    (:mod:`bemyself.claimtypes`). A hostile report must never crash the
    verifier: embedded NUL bytes are rejected up front, and an unexpected
    checker error becomes UNVERIFIABLE instead of a traceback.
    """
    registry = REGISTRY if registry is None else registry
    for value in claim.fields.values():
        if isinstance(value, str) and "\x00" in value:
            return Result(
                Verdict.UNVERIFIABLE,
                reason="claim field contains an embedded NUL byte",
                cause=Cause.DEFECT,
            )
    checker = registry.get(claim.kind)
    if checker is None:
        # A caller-supplied registry is an override layer, not an exhaustive
        # one: optional claim types stay resolvable even then.
        checker = claimtypes.checker_for(claim.kind)
    if checker is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"no checker registered for claim kind {claim.kind!r}",
        )
    try:
        return checker(claim, ctx)
    except Exception as exc:  # noqa: BLE001 - hostile input must not crash the verifier
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"checker failed: {type(exc).__name__}: {exc}",
        )

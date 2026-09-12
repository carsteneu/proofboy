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

from bemyself.model import Claim, Result, Verdict
from bemyself import claimtypes
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
)
_WRITE_LIMIT_RE = re.compile(r"\[Errno 27\]|File too large")
_MISSING_MODULE_RE = re.compile(r"No module named '?([A-Za-z_][\w.]*)'?")
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
    # Command prefixes a [COMPUTE] claim may run; --allow extends it.
    compute_allowlist: tuple[str, ...] = DEFAULT_COMPUTE_ALLOWLIST


def _repo_command(ctx, *args):
    # Repo-owned config must not execute programs during verification: hooks
    # (reference-transaction via core.hooksPath) and core.fsmonitor are
    # neutralized for every command that runs inside the untrusted repo.
    return [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
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


def _sandbox_prefix(program, checkout):
    """The bwrap wrapper for one test run.

    The filesystem root is bound read-only; only the throwaway checkout is
    writable. The command gets its own network, PID and UTS namespaces, so it
    can neither reach the host network nor see host processes. ``--die-with-parent``
    keeps a sandbox from outliving the verifier.
    """
    return [
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
        "--unshare-net",
        "--unshare-pid",
        "--unshare-uts",
        "--chdir",
        checkout,
        "--",
    ]


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
        return Result(Verdict.UNVERIFIABLE, reason=f"repo path does not exist: {ctx.repo}")
    proc = _git(ctx, "rev-parse", "--git-dir")
    if proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "rev-parse", "--git-dir")),
            output=_output(proc),
            reason=f"not a git repository: {ctx.repo}",
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
        return Result(Verdict.UNVERIFIABLE, reason=f"not a commit hash: {value!r}")
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
        return Result(Verdict.UNVERIFIABLE, reason=f"not a valid branch name: {branch!r}")
    value = claim.fields.get("commit")
    if not value:
        return Result(Verdict.UNVERIFIABLE, reason="report names a branch but no commit hash")

    remotes_proc = _git(ctx, "remote")
    remotes = remotes_proc.stdout.split()
    if not remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            reason="no git remote configured; cannot verify the branch was pushed",
        )
    if ORIGIN not in remotes:
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "remote")),
            output=_output(remotes_proc),
            reason=f"no '{ORIGIN}' remote (found: {', '.join(remotes)})",
        )

    commit = _resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
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
            )
    proxies = _git(ctx, "config", "--local", "--get-regexp", r"^http\..*\.proxy$")
    if proxies.returncode == 0 and proxies.stdout.strip():
        return Result(
            Verdict.UNVERIFIABLE,
            command=_format(_repo_command(ctx, "config", "--local", "--get-regexp", "http-proxy")),
            output=_output(proxies),
            reason="repo config sets a URL-specific http proxy; refusing to fetch through it",
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
            )
        tip = _rev_parse(ctx, private_ref)
        if tip is None:
            return Result(
                Verdict.UNVERIFIABLE,
                reason=f"{private_ref} did not resolve to a commit after fetch",
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
        )
    planned = {name[2:] if name.startswith("./") else name for name in claim.fields.get("planned") or ()}
    planned.discard("")
    if not planned:
        return Result(Verdict.UNVERIFIABLE, reason="no planned file list to compare against")

    base = _rev_parse(ctx, ctx.base)
    if base is None:
        return Result(Verdict.UNVERIFIABLE, reason=f"base revision does not resolve: {ctx.base!r}")
    head = _resolve_commit(ctx, claim.fields.get("head"))
    if head is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"head {claim.fields.get('head')!r} does not resolve to a commit",
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
            Verdict.UNVERIFIABLE, command, _output(proc), reason=f"could not diff {base}..{head}"
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
        )
    commit = _resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
        )
    if not _is_allowed(command_str, ctx.allowlist):
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"command is not in the allowlist: {command_str!r}",
        )
    try:
        argv = shlex.split(command_str)
    except ValueError as exc:
        return Result(Verdict.UNVERIFIABLE, command=command_str, reason=f"could not parse command: {exc}")
    if not argv:
        return Result(Verdict.UNVERIFIABLE, command=command_str, reason="empty command")
    strict = _is_wrapper_command(argv)
    escaping = [arg for arg in argv if _arg_escapes_checkout(arg, strict=strict)]
    if escaping:
        # Only the cwd is confined; an argument pointing outside the fresh
        # checkout would run code the verified commit never contained.
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"unsafe command argument: {escaping[0]!r}",
        )

    # require is a hard gate: when no bwrap is on PATH the command is never
    # run, not even unsandboxed -- a fallback would be silent by construction.
    mode = ctx.sandbox
    if mode not in SANDBOX_MODES:
        # A typo like "Require" must not degrade into an auto fallback.
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"unknown sandbox mode: {mode!r}",
        )
    bwrap = None if mode == "off" else find_bwrap()
    if mode == "require" and bwrap is None:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason="sandbox required (--sandbox=require) but bwrap is not available in PATH; "
            "refusing to run the command unsandboxed",
        )

    try:
        os.makedirs(ctx.tmp_dir, exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="checkout-", dir=ctx.tmp_dir)
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"cannot create a throwaway checkout under {ctx.tmp_dir}: {exc}",
        )
    try:
        log_fd, log_path = tempfile.mkstemp(prefix="run-", suffix=".log", dir=ctx.tmp_dir)
    except OSError as exc:
        shutil.rmtree(checkout, ignore_errors=True)
        return Result(
            Verdict.UNVERIFIABLE,
            command=command_str,
            reason=f"cannot create a log file under {ctx.tmp_dir}: {exc}",
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
            )
        co = _run_git(["git", "-C", checkout, "checkout", "--quiet", commit], GIT_TIMEOUT)
        if co.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                _output(co),
                reason=f"could not check out {commit}",
            )
        shadow = _shadowed_module(checkout, argv)
        if shadow is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"the checkout shadows the {shadow!r} module; the runner would not be the real one",
            )
        escape = _symlink_escape(argv, checkout, strict=strict)
        if escape is not None:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"command argument resolves outside the checkout: {escape!r}",
            )
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
                f"command timed out after {TEST_TIMEOUT}s" + note_suffix, sandboxed=sandboxed,
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
                f"command output exceeded the per-file limit of {MAX_LOG_BYTES} bytes" + note_suffix, sandboxed=sandboxed,
            )
        # CPython ignores SIGXFSZ and dies with another code once the write
        # limit is hit, so the capped file is the reliable signal.
        if log_size >= MAX_LOG_BYTES:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                output,
                f"command output reached the per-file limit of {MAX_LOG_BYTES} bytes; "
                "the run cannot be verified from truncated output" + note_suffix, sandboxed=sandboxed,
            )
        if returncode == claimed_exit:
            if claim.kind == "tests_green":
                # Exiting 0 is not proof that tests ran: require a positive
                # test summary, and treat "no tests" output as unverifiable.
                if _shows_test_evidence(raw_output):
                    pass
                elif _claims_no_tests(raw_output):
                    return Result(
                        Verdict.UNVERIFIABLE,
                        command_desc,
                        output,
                        "the command exited 0 but reported that no tests were executed" + note_suffix, sandboxed=sandboxed,
                    )
                else:
                    return Result(
                        Verdict.UNVERIFIABLE,
                        command_desc,
                        output,
                        "the command exited 0 but its output shows no evidence that tests ran" + note_suffix, sandboxed=sandboxed,
                    )
            return Result(
                Verdict.CONFIRMED,
                command_desc,
                output,
                f"{command_str!r} exited {returncode} as claimed" + note_suffix, sandboxed=sandboxed,
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
                    f"the runner module {missing!r} is not available in this environment" + note_suffix, sandboxed=sandboxed,
                )
        if _WRITE_LIMIT_RE.search(raw_output):
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                output,
                "the run hit the per-file write limit; its outcome cannot be verified" + note_suffix, sandboxed=sandboxed,
            )
        return Result(
            Verdict.REFUTED,
            command_desc,
            output,
            f"claimed exit {claimed_exit}, actually exited {returncode}" + note_suffix, sandboxed=sandboxed,
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


REGISTRY = {
    "commit_exists": check_commit_exists,
    "branch_pushed": check_branch_pushed,
    "diff_scope": check_diff_scope,
    "tests_green": check_tests_green,
    "tests_exit": check_tests_green,
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
                Verdict.UNVERIFIABLE, reason="claim field contains an embedded NUL byte"
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

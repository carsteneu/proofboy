"""The ``[LEAN: <path.lean> -> <theorem>]`` claim type: a formal proof
certificate.

A LEAN claim asserts that in the report's pinned commit the named Lean source
file exists and the named declaration is proved there without ``sorry`` or
``admit``. The verifier re-derives the claim with the real toolchain: it
resolves the report's single hash-shaped ``[COMMIT]`` marker (the same
binding rule as :mod:`bemyself.claimtypes.compute`), checks the file against
that commit's tree (``git cat-file``), copies the pinned source out of a
throwaway checkout, appends ``#print axioms <theorem>`` and elaborates the
copy inside the bwrap sandbox. The verdict cites the kernel evidence: the
``#print axioms`` line names every axiom the declaration rests on, and a
proof that used ``sorry``/``admit`` shows ``sorryAx`` -- REFUTED with that
line quoted verbatim. All remaining axioms are listed in full; a non-logical
axiom in that list is exactly as visible as ``sorryAx``, and what the list
means for the claim is documented in README/SPEC.

Proof depth (what CONFIRMED means): the pinned source was *re-elaborated*
with the toolchain named in the verdict; Lean's kernel checks every
declaration during elaboration, so the proof term was kernel-checked -- this
is not an "independent kernel recheck" of a compiled artifact. ``leanchecker``
(re-checks ``.olean`` files) was evaluated and is not used: it silently
accepts a module whose proof depends on ``sorryAx`` (verified 2026-09-13 with
Lean 4.33.1), so it cannot replace the ``#print axioms`` evidence. The
verdict wording says "re-elaborated" for exactly this reason.

Isolation: elaboration executes code (tactics, metaprograms, ``#eval``), and
``lake`` fetches missing dependencies over the network, so a working bwrap
sandbox is required: ``auto`` and ``require`` behave alike and leave the
claim UNVERIFIABLE when bwrap cannot start; only an explicit
``--sandbox=off`` runs unsandboxed (and says so in the verdict). The sandbox
binds the filesystem root read-only (which keeps the toolchain under
``~/.elan`` reachable), gives the run its own network/PID/UTS namespaces and
writable space only in the throwaway checkout. ``ELAN_HOME`` points at the
toolchain root so the elan shim works with ``HOME=<checkout>``; when no
``lean-toolchain`` file is in reach, the sole installed toolchain is pinned
as ``ELAN_TOOLCHAIN`` so the shim does not query its release server (no
network in the sandbox). When the checked repository has a working-tree
``.lake`` cache next to the project and the fresh checkout has none, its
``packages`` directory is bound read-only into the same path -- named in the
verdict. Dependencies are not part of the commit and the sandbox has no
network: an unresolvable dependency (or a cache without compiled artifacts)
leaves the claim UNVERIFIABLE (never REFUTED, never CONFIRMED), and a
dependency error only counts when the missing module is one the file itself
imports.

Limits: ``LEAN_TIMEOUT`` bounds one build/elaboration run. Path and theorem
come from an untrusted report and are validated before any argv is built:
the path must be a plain repository-relative ``.lean`` path (no ``..``, no
absolute path, ASCII-safe), the theorem must be a Lean identifier (unicode
letters/digits/underscore, dots and ``!?``). No shell is involved anywhere.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import namedtuple

from bemyself.claimtypes.halt import _ARROW, _UNICODE_ARROW
from bemyself.model import ClaimType, Result, Verdict

# One build or elaboration run must finish within this many seconds. Like
# COMPUTE_TIMEOUT this is a fixed bound, not a CLI option.
LEAN_TIMEOUT = 600
# The toolchain preflight is a version print, not a run.
PREFLIGHT_TIMEOUT = 60
# The window of the run log searched for the FIRST error line; the verdict
# line (#print axioms) is read from the tail by the shared helper.
MAX_ERROR_BYTES = 1 << 18

# One lazy "anything but a bracket" capture, fields split out of it afterwards
# (same shape as [COMPUTE], see bemyself/claimtypes/halt.py for the reasoning).
_LEAN_RE = re.compile(r"\[LEAN:(?P<body>[^\]\[]*?)\]")

# A claim path must be a plain repository-relative path to a .lean file. The
# character set is deliberately narrow: the path reaches argv and the copied
# driver's file name, so anything unusual stays UNVERIFIABLE instead of being
# guessed about.
_PATH_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9_./-]*\.lean\Z")
# A declaration name: a Lean identifier (unicode letters, digits, underscore)
# with namespace dots and the trailing !/? Lean allows. Nothing that could
# end a Lean command can pass, so the generated #print line is safe.
_NAME_RE = re.compile(r"\A[^\W\d][\w'.!?]*\Z", re.UNICODE)
_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^ \t\r\n]+)[ \t]*$", re.MULTILINE)
_ERROR_RE = re.compile(r"\berror\b")
_UNKNOWN_MODULE_RE = re.compile(r"unknown module prefix '([^']+)'")
_UNKNOWN_IDENTIFIER_RE = re.compile(r"unknownIdentifier|Unknown constant|unknown identifier")
_SANDBOX_FAILURE_RE = re.compile(r"\bbwrap\b")
_READONLY_CACHE_RE = re.compile(r"(?i)read-?only file system")
_ENV_FAILURE_RE = re.compile(
    r"(?i)(could not resolve host|unable to access|failed to fetch|"
    r"network is unreachable|connection refused|no default toolchain|"
    r"failed to download|failed to install)"
)
_LAKEFILES = ("lakefile.toml", "lakefile.lean")
_DRIVER_PREFIX = "BemyselfCheck_"

# returncode None means the run timed out; error is set for setup failures
# (the process could not even start) and otherwise None.
_Run = namedtuple("_Run", "returncode head tail truncated error")


def _split_body(match):
    """(path, theorem) of one marker: the last arrow separates them."""
    body = match.group("body")
    index = max(body.rfind(_ARROW), body.rfind(_UNICODE_ARROW))
    if index < 0:
        return None
    arrow = _UNICODE_ARROW if index == body.rfind(_UNICODE_ARROW) else _ARROW
    return body[:index].strip(), body[index + len(arrow) :].strip()


def parse(match, raw):
    """Fields of one [LEAN] marker: the source path and the declaration."""
    parts = _split_body(match)
    if parts is None:
        # An arrow-less marker names no claim.
        return None
    path, theorem = parts
    # The commit stays None until the report parser binds the report's single
    # commit (ClaimType.binds_commit).
    return {"path": path, "theorem": theorem, "commit": None}


def _valid_path(path):
    """A repository-relative .lean path with no escaping component."""
    if path.startswith("./"):
        path = path[2:]
    if not path or not _PATH_RE.match(path):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def _valid_theorem(name):
    return bool(name) and _NAME_RE.match(name) is not None


def _first_error_line(text):
    """The first line that reads as a Lean error, else the first line."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if _ERROR_RE.search(line):
            return line
    return lines[0] if lines else ""


def _toolchain_name(text):
    """A short toolchain name from a ``lean --version`` answer, else "".

    Elan prints a ``warning: failed to query latest release, using existing
    version ...`` line before the answer when the sandbox has no network;
    that warning is not the toolchain name.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("warning"):
            continue
        match = re.search(r"version\s+([0-9][^\s,)]*)", line)
        if match:
            return f"Lean {match.group(1)}"
        if "version" in line.lower():
            return line
    return ""


def _imports_of(source_text):
    return _IMPORT_RE.findall(source_text)


def _missing_dependency(text, imports):
    """The module name of a dependency error, when the file imports it.

    A hostile report controls its file, so an error line that merely names a
    module the file does NOT import must not downgrade a refutation: the
    missing module has to be one of the file's own import roots, or an
    environment failure (network, toolchain) -- otherwise this is None and
    the caller treats the output as a real failure.
    """
    roots = {name.split(".")[0] for name in imports}
    for match in _UNKNOWN_MODULE_RE.finditer(text):
        module = match.group(1)
        if module.split(".")[0] in roots:
            return module
    if _ENV_FAILURE_RE.search(text):
        return True
    return None


def _elan_home(lean_path):
    """The elan root for the toolchain, when the binary is an elan shim.

    The shim resolves its toolchains through ``$HOME/.elan``; runs use
    ``HOME=<checkout>`` for isolation, so the root must be passed explicitly.
    """
    candidate = os.environ.get("ELAN_HOME")
    if candidate and os.path.isdir(candidate):
        return candidate
    binary = os.path.realpath(lean_path)
    bin_dir = os.path.dirname(binary)
    root = os.path.dirname(bin_dir)
    if os.path.basename(bin_dir) == "bin" and os.path.isdir(os.path.join(root, "toolchains")):
        return root
    return None


def _sole_toolchain(elan_home):
    """The one installed elan toolchain as ``authority/name:version``, or None.

    Without a ``lean-toolchain`` file elan asks its release server for the
    default toolchain; in the sandbox (no network) that query burns seconds
    and falls back to the installed version anyway. When exactly one
    toolchain is installed, its directory name is unambiguous, so it is
    passed as ``ELAN_TOOLCHAIN`` and the fallback stays deterministic and
    offline.
    """
    toolchains = os.path.join(elan_home, "toolchains")
    try:
        names = sorted(os.listdir(toolchains))
    except OSError:
        return None
    names = [name for name in names if os.path.isdir(os.path.join(toolchains, name))]
    if len(names) != 1:
        return None
    return names[0].replace("---", ":").replace("--", "/")


def _project_toolchain_file(start_dir):
    """The ``lean-toolchain`` file elan would find from ``start_dir``, or None."""
    current = os.path.realpath(start_dir)
    while True:
        candidate = os.path.join(current, "lean-toolchain")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _find_tool(name):
    """An absolute path to ``name`` from PATH, or None."""
    path = shutil.which(name)
    if path is None or not os.path.isabs(path):
        return None
    return path


def _lake_project(checkout, start_dir):
    """The nearest directory at or above ``start_dir`` with a lakefile.

    The search stays inside the checkout; outside it there is no project.
    """
    root = os.path.realpath(checkout)
    current = os.path.realpath(start_dir)
    while current == root or current.startswith(root + os.sep):
        if any(os.path.isfile(os.path.join(current, name)) for name in _LAKEFILES):
            return current
        if current == root:
            return None
        current = os.path.dirname(current)
    return None


def _module_name(project, file_path):
    """The Lake module name of ``file_path``, or None when not derivable."""
    relative = os.path.relpath(file_path, project)
    if relative.startswith(".."):
        return None
    parts = relative[: -len(".lean")].split(os.sep)
    if not all(re.match(r"\A[A-Za-z_][A-Za-z0-9_']*\Z", part) for part in parts):
        return None
    return ".".join(parts)


def _run(argv, cwd, env, timeout, tmp_dir, prefix):
    """Run a tool under the log discipline of checks.py.

    The output goes to a private, size-capped file and is read back through
    the same descriptor: the head for the first error line, the tail for the
    verdict line. The child gets its own process group and file-size limit
    (checks._child_preexec), so a timeout can take the whole tree down.
    """
    from bemyself import checks  # lazy: checks imports the type registry

    try:
        log_fd, log_path = tempfile.mkstemp(prefix=prefix, suffix=".log", dir=tmp_dir)
    except OSError as exc:
        return _Run("setup", "", "", False, f"cannot create a log file under {tmp_dir}: {exc}")
    handle = os.fdopen(log_fd, "w+b")
    try:
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=env,
                preexec_fn=checks._child_preexec,
            )
        except FileNotFoundError as exc:
            return _Run("missing", "", "", False, f"command not found: {exc}")
        except OSError as exc:
            return _Run("setup", "", "", False, f"the run could not start: {exc}")
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            checks._kill_process_group(proc)
            proc.wait()
            return _Run(None, "", "", False, None)
        handle.seek(0)
        head = handle.read(MAX_ERROR_BYTES).decode("utf-8", "replace")
        tail, size = checks._tail_open(handle)
        return _Run(returncode, head, tail, size >= checks.MAX_LOG_BYTES, None)
    finally:
        try:
            handle.close()
        except OSError:
            pass
        try:
            os.unlink(log_path)
        except OSError:
            pass


def _axioms_line(text, theorem):
    """The last full ``#print axioms`` answer line for ``theorem``, or None."""
    pattern = re.compile(
        r"^'" + re.escape(theorem) + r"' (?:does not depend on any axioms"
        r"|depends on axioms: \[[^\]\n]*\])\s*$",
        re.MULTILINE,
    )
    matches = [match.group(0).strip() for match in pattern.finditer(text)]
    return matches[-1] if matches else None


def check(claim, ctx):
    from bemyself import checks  # lazy: checks imports the type registry

    guard = checks._repo_guard(ctx)
    if guard is not None:
        return guard
    path = (claim.fields.get("path") or "").strip()
    if not _valid_path(path):
        return Result(Verdict.UNVERIFIABLE, reason=f"not a valid Lean source path: {path!r}")
    if path.startswith("./"):
        path = path[2:]
    theorem = (claim.fields.get("theorem") or "").strip()
    if not _valid_theorem(theorem):
        return Result(Verdict.UNVERIFIABLE, reason=f"not a valid declaration name: {theorem!r}")
    value = (claim.fields.get("commit") or "").strip()
    if not value:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="no commit hash to pin the Lean check; the report needs one hash-shaped [COMMIT] marker",
        )
    commit = checks._resolve_commit(ctx, value)
    if commit is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"commit {value!r} does not resolve to a commit in {ctx.repo}",
        )

    # The file must be a blob in the pinned commit -- not just in the working
    # tree, which untracked or later edits could have changed.
    exists_args = ("cat-file", "-e", f"{commit}:{path}")
    exists = checks._git(ctx, *exists_args)
    exists_command = checks._format(checks._repo_command(ctx, *exists_args))
    if exists.returncode != 0:
        return Result(
            Verdict.REFUTED,
            exists_command,
            checks._output(exists),
            f"the file {path!r} does not exist in commit {commit[:12]}",
        )
    type_args = ("cat-file", "-t", f"{commit}:{path}")
    type_proc = checks._git(ctx, *type_args)
    if type_proc.returncode != 0:
        return Result(
            Verdict.UNVERIFIABLE,
            checks._format(checks._repo_command(ctx, *type_args)),
            checks._output(type_proc),
            f"cannot determine the object type of {path!r} in commit {commit[:12]}",
        )
    object_type = type_proc.stdout.strip()
    if object_type != "blob":
        return Result(
            Verdict.REFUTED,
            exists_command,
            object_type,
            f"{path!r} is not a file in commit {commit[:12]} (object type {object_type!r})",
        )

    lean = _find_tool("lean")
    if lean is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="lean is not available in PATH; the Lean proof cannot be checked",
        )

    # `auto` deliberately behaves like `require` here: elaborating Lean source
    # executes code and a run outside the sandbox could fetch dependencies
    # over the network. Only an explicit --sandbox=off leaves the sandbox.
    mode = ctx.sandbox
    if mode not in checks.SANDBOX_MODES:
        return Result(Verdict.UNVERIFIABLE, reason=f"unknown sandbox mode: {mode!r}")
    bwrap = None if mode == "off" else checks.find_bwrap()
    if mode != "off" and bwrap is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="a working sandbox is required to elaborate Lean source "
            "(it executes code and lake may fetch dependencies); bwrap is not "
            "available in PATH. Pass --sandbox=off to run unsandboxed",
        )
    note = "sandboxed with bwrap" if bwrap is not None else "not sandboxed: --sandbox=off"
    note_suffix = f" ({note})"

    try:
        os.makedirs(ctx.tmp_dir, exist_ok=True)
        checkout = tempfile.mkdtemp(prefix="lean-", dir=ctx.tmp_dir)
    except OSError as exc:
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"cannot create a throwaway checkout under {ctx.tmp_dir}: {exc}",
        )
    command_desc = f"git clone --no-hardlinks <repo> <checkout> && git checkout {commit} && "
    try:
        clone = checks._run_git(
            ["git", "clone", "--quiet", "--no-hardlinks", ctx.repo, checkout],
            checks.GIT_TIMEOUT,
        )
        if clone.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                checks._output(clone),
                reason="could not create a clean checkout",
            )
        co = checks._run_git(
            ["git", "-C", checkout, "checkout", "--quiet", commit], checks.GIT_TIMEOUT
        )
        if co.returncode != 0:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                checks._output(co),
                reason=f"could not check out {commit}",
            )

        file_path = os.path.join(checkout, path)
        real_file = os.path.realpath(file_path)
        checkout_real = os.path.realpath(checkout)
        if real_file != checkout_real and not real_file.startswith(checkout_real + os.sep):
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"the path {path!r} resolves outside the checkout",
            )
        if not os.path.isfile(real_file):
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"the file {path!r} is not in the checkout",
            )
        with open(real_file, encoding="utf-8", errors="replace") as handle:
            source_text = handle.read()
        imports = _imports_of(source_text)

        project = _lake_project(checkout, os.path.dirname(real_file))
        lake = None
        module = None
        if project is not None:
            lake = _find_tool("lake")
            if lake is None:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"the file is part of a Lake project at "
                    f"{os.path.relpath(project, checkout)!r} but lake is not available in PATH",
                )
            module = _module_name(project, real_file)

        # A working-tree dependency cache is bound read-only when the fresh
        # checkout has none: dependencies are not part of the commit and the
        # sandbox has no network, so without it an unresolvable dependency
        # ends UNVERIFIABLE. Only the packages directory is bound -- the
        # checkout keeps its own writable .lake for the project's build -- and
        # the bind is named in the verdict command.
        extra_binds = []
        if bwrap is not None and project is not None:
            packages = os.path.join(
                ctx.repo or "", os.path.relpath(project, checkout), ".lake", "packages"
            )
            packages_dest = os.path.join(project, ".lake", "packages")
            if os.path.isdir(packages) and not os.path.exists(packages_dest):
                extra_binds.append((packages, packages_dest))

        sandboxed = bwrap is not None

        def wrapped(argv, display, cwd):
            """(argv to run, display text) with the sandbox and its note."""
            if sandboxed:
                prefix = checks._sandbox_prefix(bwrap, checkout, tuple(extra_binds), cwd)
                return list(prefix) + list(argv), checks._sandbox_display(display)
            return list(argv), display + note_suffix

        env = checks._test_env(checkout)
        elan_home = _elan_home(lean)
        if elan_home is not None:
            env["ELAN_HOME"] = elan_home
            # The operator's explicit choice wins; otherwise pin the sole
            # installed toolchain when no lean-toolchain file is in reach, so
            # the shim does not query its release server (no network here).
            operator_choice = os.environ.get("ELAN_TOOLCHAIN")
            if operator_choice:
                env["ELAN_TOOLCHAIN"] = operator_choice
            elif _project_toolchain_file(project or os.path.dirname(real_file)) is None:
                sole = _sole_toolchain(elan_home)
                if sole is not None:
                    env["ELAN_TOOLCHAIN"] = sole

        cache_note = ""
        if extra_binds:
            cache_note = (
                " (with the working tree's dependency cache bound read-only "
                f"from {extra_binds[0][0]})"
            )

        def unverifiable(run, shown, reason):
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc + shown + cache_note,
                checks._last_lines(run.tail or run.head),
                reason + note_suffix,
                sandboxed=sandboxed,
            )

        # Preflight: separate "the toolchain cannot run here" from "the file
        # failed". The version print also names the toolchain in the verdict
        # (the elaborator is Lean; lake is only the environment wrapper).
        preflight = [lean, "--version"]
        run_argv, shown = wrapped(preflight, " ".join(preflight), project or checkout)
        run = _run(run_argv, checkout, env, PREFLIGHT_TIMEOUT, ctx.tmp_dir, "lean-preflight-")
        if run.error is not None:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
        if run.returncode != 0:
            detail = _first_error_line(run.head or run.tail) or f"exit status {run.returncode}"
            return unverifiable(
                run,
                shown,
                f"the Lean toolchain could not run ({preflight[0]} --version): {detail}",
            )
        toolchain = _toolchain_name(run.head) or _toolchain_name(run.tail) or "Lean"
        if lake is not None:
            lake_preflight = [lake, "--version"]
            run_argv, shown = wrapped(lake_preflight, " ".join(lake_preflight), project)
            run = _run(
                run_argv, project, env, PREFLIGHT_TIMEOUT, ctx.tmp_dir, "lake-preflight-"
            )
            if run.error is not None:
                return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
            if run.returncode != 0:
                detail = _first_error_line(run.head or run.tail) or f"exit status {run.returncode}"
                return unverifiable(
                    run,
                    shown,
                    f"the Lake toolchain could not run ({lake_preflight[0]} --version): {detail}",
                )

        def failed(run, shown, what):
            """Classify a non-zero run: environment gap or real failure."""
            combined = run.head + "\n" + run.tail
            first = _first_error_line(combined)
            if sandboxed and _SANDBOX_FAILURE_RE.search(combined):
                return unverifiable(run, shown, f"the sandbox could not run the command: {first}")
            if extra_binds and _READONLY_CACHE_RE.search(combined):
                return unverifiable(
                    run,
                    shown,
                    f"the dependency packages bound read-only from {extra_binds[0][0]} "
                    f"cannot serve this run (a write into the read-only cache was "
                    f"refused); the proof was not checked: {first}",
                )
            if _missing_dependency(combined, imports) is not None:
                return unverifiable(
                    run,
                    shown,
                    f"a dependency of {path!r} is not available in the checkout "
                    f"(no network, no complete dependency cache); {what} was not "
                    f"checked: {first}",
                )
            if _UNKNOWN_IDENTIFIER_RE.search(combined):
                return Result(
                    Verdict.REFUTED,
                    command_desc + shown + cache_note,
                    checks._last_lines(combined),
                    f"declaration not found: {first}{note_suffix}",
                    sandboxed=sandboxed,
                )
            return Result(
                Verdict.REFUTED,
                command_desc + shown + cache_note,
                checks._last_lines(combined),
                f"{what} failed: {first}{note_suffix}",
                sandboxed=sandboxed,
            )

        if module is not None:
            build = [lake, "build", module]
            run_argv, shown = wrapped(build, " ".join(build), project)
            run = _run(run_argv, project, env, LEAN_TIMEOUT, ctx.tmp_dir, "lean-build-")
            if run.error is not None:
                return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
            if run.returncode is None:
                return unverifiable(
                    run, shown, f"the Lean build timed out after {LEAN_TIMEOUT}s"
                )
            if run.truncated:
                return unverifiable(
                    run, shown, "the Lean build exceeded the output limit; its outcome cannot be verified"
                )
            if run.returncode != 0:
                combined = run.head + "\n" + run.tail
                first = _first_error_line(combined)
                if sandboxed and _SANDBOX_FAILURE_RE.search(combined):
                    return unverifiable(
                        run, shown, f"the sandbox could not run the command: {first}"
                    )
                if extra_binds and _READONLY_CACHE_RE.search(combined):
                    return unverifiable(
                        run,
                        shown,
                        f"the dependency packages bound read-only from {extra_binds[0][0]} "
                        f"carry no compiled artifacts for this build; the project cannot "
                        f"be built offline: {first}",
                    )
                if _missing_dependency(combined, imports) is not None:
                    return unverifiable(
                        run,
                        shown,
                        f"a dependency of {path!r} is not available in the checkout "
                        f"(no network, no complete dependency cache); the build was "
                        f"not checked: {first}",
                    )
                rel = os.path.relpath(real_file, checkout)
                if first and (rel in first or os.path.basename(rel) in first):
                    return Result(
                        Verdict.REFUTED,
                        command_desc + shown + cache_note,
                        checks._last_lines(combined),
                        f"the file does not compile: {first}{note_suffix}",
                        sandboxed=sandboxed,
                    )
                return unverifiable(
                    run,
                    shown,
                    f"the project did not build; the first reported problem is "
                    f"outside {path!r}: {first}",
                )

        # The driver is a copy of the pinned source plus the question: Lean
        # re-elaborates the file's own declarations, so the answer is about
        # the committed source text, not about a stale .olean.
        driver_name = f"{_DRIVER_PREFIX}{os.urandom(4).hex()}.lean"
        driver_path = os.path.join(os.path.dirname(real_file), driver_name)
        try:
            with open(driver_path, "w", encoding="utf-8") as handle:
                handle.write(source_text)
                handle.write(f"\n\n#print axioms {theorem}\n")
        except OSError as exc:
            return Result(
                Verdict.UNVERIFIABLE,
                command_desc,
                "",
                f"cannot write the check driver next to {path!r}: {exc}",
            )

        if lake is not None:
            elaborate = [lake, "env", "lean", driver_path]
            cwd = project
        else:
            elaborate = [lean, driver_path]
            cwd = os.path.dirname(real_file)
        run_argv, shown = wrapped(elaborate, " ".join(elaborate), cwd)
        run = _run(run_argv, cwd, env, LEAN_TIMEOUT, ctx.tmp_dir, "lean-run-")
        if run.error is not None:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
        if run.returncode is None:
            return unverifiable(
                run, shown, f"the Lean elaboration timed out after {LEAN_TIMEOUT}s"
            )
        if run.truncated:
            return unverifiable(
                run, shown, "the Lean elaboration exceeded the output limit; its outcome cannot be verified"
            )
        if run.returncode != 0:
            return failed(run, shown, "the elaboration")

        line = _axioms_line(run.tail, theorem) or _axioms_line(run.head, theorem)
        if line is None:
            return unverifiable(
                run,
                shown,
                f"the elaboration exited 0 but printed no #print axioms line for "
                f"{theorem!r}; the proof was not checked",
            )
        if "sorryAx" in line:
            return Result(
                Verdict.REFUTED,
                command_desc + shown + cache_note,
                checks._last_lines(run.tail),
                f"the proof depends on sorry: #print axioms reports {line}{note_suffix}",
                sandboxed=sandboxed,
            )
        return Result(
            Verdict.CONFIRMED,
            command_desc + shown + cache_note,
            checks._last_lines(run.tail),
            f"'{theorem}' is proved in {path} at {commit[:12]}: re-elaborated with "
            f"{toolchain} (the kernel checked every declaration during elaboration); "
            f"#print axioms: {line}{note_suffix}",
            sandboxed=sandboxed,
        )
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


LEAN = ClaimType(
    kind="lean",
    pattern=_LEAN_RE,
    parse=parse,
    check=check,
    needs_repo=True,
    binds_commit=True,
)

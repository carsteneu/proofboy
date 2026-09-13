"""The ``[LEAN: <path.lean> -> <theorem>]`` claim type: a formal proof
certificate.

A LEAN claim asserts that in the report's pinned commit the named Lean source
file exists and the named declaration is proved there without ``sorry`` or
``admit``. The verifier re-derives the claim with the real toolchain in three
stages, all inside the bwrap sandbox:
1. **Build.** The pinned commit is checked out into a throwaway directory,
   the project's own build artifacts are discarded (a symlinked build
   directory is unlinked, not emptied), and the file's module is built from
   the pinned source (``lake build <module>`` for a Lake project, ``lean -o``
   for a standalone file). The build executes repository code (tactics,
   ``#eval``, initializers); nothing it prints is evidence, and a successful
   build must leave a freshly written artifact behind (existence and mtime
   after the build started) or the claim stays unverifiable.
2. **Kernel re-check.** ``leanchecker <module>`` re-checks the compiled
   artifact's declarations with Lean's kernel. Re-check and query call the
   toolchain directly -- never ``lake``, whose lakefile is repository code
   that would share the evidence channel -- with a search path whose first
   entry is the toolchain's own library directory (``lean --print-libdir``),
   so the inspected tree cannot shadow the query program's imports.
3. **Axiom query.** The checker's own program (``bemyself/tools/lean_axioms.lean``)
   loads the artifact as *data* at runtime (``importModules``, the module is
   never imported at elaboration time) and prints the declaration's axiom
   list; an AXIOMS line only counts together with exit status 0. No
   repository code executes in that process -- not a tactic, not a macro,
   not an ``initialize`` block -- so the answer cannot be forged or
   suppressed by the inspected project: the only writer is the query
   program, and the axiom data comes from the artifact the kernel just
   re-checked.

Verdicts. CONFIRMED only when the query answers for exactly that declaration
(with exit status 0) and the list names no ``sorryAx``; the canonical
evidence line (``'name' depends on axioms: [...]`` or ``'name' does not
depend on any axioms``) is quoted in the verdict, with every axiom named --
logical foundations such as ``propext``, ``Quot.sound`` or
``Classical.choice`` included: CONFIRMED does not mean axiom-free. REFUTED
on ``sorryAx`` (``depends on axioms: [sorryAx]``), on ``lcProof`` (the
kernel did not check the body, e.g. an ``unsafe`` declaration), on a
declaration that is itself an axiom (its own name in its axiom list), on a
declaration missing from the artifact, and on a build error that names the
checked file. UNVERIFIABLE otherwise: no toolchain, no sandbox, no commit,
invalid path or name, timeout, a failed kernel re-check, a missing fresh
artifact, an unreadable answer, and any dependency problem -- a missing
dependency is never evidence against the theorem, and a failed build that
does not name the checked file is never a refutation.

Execution policy. The build runs repository code and cannot avoid it (it
delivers the artifact the kernel re-checks). Files -- and a
``lakefile.lean`` -- that visibly execute code at elaboration time
(``#eval``, ``#exec``, ``run_cmd``, ``run_elab``) are therefore not checked
and stay UNVERIFIABLE: their build chain cannot be vouched for. Hidden
forms of execution (custom elaborators, ``native_decide``, code inside
dependency modules) are not caught by that policy; a repository using them
can decouple the artifact's provenance from the checked file and lies
outside what this check guarantees. Build output can only downgrade a
verdict, never lift one to CONFIRMED.

Isolation. Elaboration and building execute code, and ``lake`` would fetch
missing dependencies over the network, so a working bwrap sandbox is
required: ``auto`` and ``require`` behave alike and leave the claim
UNVERIFIABLE when bwrap cannot start; only an explicit ``--sandbox=off`` runs
unsandboxed (and says so in the verdict). The sandbox binds the filesystem
root read-only (which keeps the toolchain under ``~/.elan`` reachable), gives
the run its own network/PID/UTS namespaces and writable space only in the
throwaway checkout. ``ELAN_HOME`` points at the toolchain root so the elan
shim works with ``HOME=<checkout>``; when no ``lean-toolchain`` file is in
reach, the sole installed toolchain is pinned as ``ELAN_TOOLCHAIN`` so the
shim does not query its release server (no network in the sandbox). When the
checked repository has a working-tree ``.lake`` cache next to the project and
the fresh checkout has none, its ``packages`` directory is bound read-only
into the same path -- named in the verdict.

Limits: ``LEAN_TIMEOUT`` bounds each build/query/re-check run. Path and
theorem come from an untrusted report and are validated before any argv is
built: the path must be a plain repository-relative ``.lean`` path (no
``..``, no absolute path, ASCII-safe), the declaration must be its full Lean
name (namespace dots, unicode letters/digits/underscore, trailing ``!?``).
No shell is involved anywhere.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import namedtuple

from bemyself.claimtypes.halt import _ARROW, _UNICODE_ARROW
from bemyself.model import ClaimType, Result, Verdict

# One build, query or re-check run must finish within this many seconds. Like
# COMPUTE_TIMEOUT this is a fixed bound, not a CLI option.
LEAN_TIMEOUT = 600
# The toolchain preflight is a version print, not a run.
PREFLIGHT_TIMEOUT = 60
# The window of the build log searched for the FIRST error line; the query
# answer is read from the same log by the marker protocol below.
MAX_ERROR_BYTES = 1 << 18

# One lazy "anything but a bracket" capture, fields split out of it afterwards
# (same shape as [COMPUTE], see bemyself/claimtypes/halt.py for the reasoning).
_LEAN_RE = re.compile(r"\[LEAN:(?P<body>[^\]\[]*?)\]")

# A claim path must be a plain repository-relative path to a .lean file. The
# character set is deliberately narrow: the path reaches argv and the
# generated build command, so anything unusual stays UNVERIFIABLE instead of
# being guessed about.
_PATH_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9_./-]*\.lean\Z")
# A declaration name: its full Lean name (unicode letters, digits, underscore)
# with namespace dots and the trailing !/? Lean allows. Nothing that could
# end a Lean command can pass.
_NAME_RE = re.compile(r"\A[^\W\d][\w'.!?]*\Z", re.UNICODE)
# `import X`, `public import X Y`, `import X.sub`, optionally with a trailing
# comment: the module names of every import line, braced forms excluded.
_IMPORT_RE = re.compile(
    r"^[ \t]*(?:public[ \t]+|private[ \t]+|protected[ \t]+|noncomputable[ \t]+)?"
    r"import[ \t]+([^ \t\r\n]+(?:[ \t]+[^ \t\r\n]+)*)",
    re.MULTILINE,
)
_ERROR_RE = re.compile(r"\berror\b")
_UNKNOWN_MODULE_RE = re.compile(r"unknown module prefix '([^']+)'")
_SANDBOX_FAILURE_RE = re.compile(r"(?m)^bwrap: ")
_READONLY_CACHE_RE = re.compile(r"(?i)read-?only file system")
_ENV_FAILURE_RE = re.compile(
    r"(?i)(could not resolve host|unable to access|failed to fetch|"
    r"network is unreachable|connection refused|no default toolchain|"
    r"failed to download|failed to install)"
)
# The query program's protocol: one of these lines is the whole answer.
_ANSWER_RE = re.compile(
    r"\ABEMYSELF-LEAN-AXIOMS (?P<name>[^\s]+) \[(?P<axioms>[^\]\n]*)\]\s*\Z"
)
_UNKNOWN_RE = re.compile(r"\ABEMYSELF-LEAN-UNKNOWN (?P<name>[^\s]+)\s*\Z")
_QUERY_ERROR_RE = re.compile(r"\ABEMYSELF-LEAN-ERROR (?P<detail>.*)\Z")
# An axiom name that means "this proof was not kernel-checked": `lcProof` is
# what an `unsafe` declaration's dependency list carries.
_LC_PROOF = re.compile(r"(?:\A|\.)lcProof\Z")
# Commands that execute code while the file is elaborated. A file containing
# them cannot be vouched for: the build it drives may write artifacts or
# terminate early, so the claim stays unverifiable (documented policy).
_EXEC_RE = re.compile(r"(?m)(^|[^\w])#(?:eval|exec)\b|\brun_(?:cmd|elab)\b")
_LAKEFILES = ("lakefile.toml", "lakefile.lean")
# Where the standalone-file build puts its artifact, inside the checkout so
# the sandbox keeps it writable.
_BUILD_DIR = ".bemyself-build"
_QUERY_PROGRAM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "lean_axioms.lean"
)

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
    """The module names of the file's import lines, comments dropped."""
    names = []
    for line in _IMPORT_RE.findall(source_text):
        line = line.split("--")[0]
        # `import A B` imports A and B; `import A.B` is one module.
        names.extend(part for part in line.split() if part and not part.startswith("{("))
    return names


def _missing_dependency(text, imports):
    """The module name of a dependency error, when the file imports it.

    A hostile project controls its file, so an error line that merely names a
    module the file does NOT import must not downgrade a refutation: the
    missing module has to be one of the file's own import roots, or an
    environment failure (network, toolchain) -- otherwise this is None and the
    caller treats the output as a real failure.
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


def _module_part(name):
    return re.match(r"\A[A-Za-z_][A-Za-z0-9_']*\Z", name) is not None


def _module_name(project, file_path):
    """The Lake module name of ``file_path``, or None when not derivable."""
    relative = os.path.relpath(file_path, project)
    if relative.startswith("..") or not relative.endswith(".lean"):
        return None
    parts = relative[: -len(".lean")].split(os.sep)
    if not all(_module_part(part) for part in parts):
        return None
    return ".".join(parts)


def _standalone_module(file_path):
    """The module name a standalone file gets when compiled with ``-o``."""
    stem = os.path.basename(file_path)[: -len(".lean")]
    return stem if _module_part(stem) else None


def _run(argv, cwd, env, timeout, tmp_dir, prefix):
    """Run a tool under the log discipline of checks.py.

    The output goes to a private, size-capped file and is read back through
    the same descriptor: the head for the first error line, the tail for the
    query answer. The child gets its own process group and file-size limit
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


def _query_answer(text, theorem):
    """Parse the query program's protocol out of one run log.

    Returns ``("axioms", [names])``, ``("unknown", None)``,
    ``("error", detail)`` or ``(None, None)`` -- the last when the log carries
    no (or more than one) protocol line, which must never happen in a clean
    run and is treated as an unreadable answer.
    """
    found = []
    for line in text.splitlines():
        line = line.rstrip()
        match = _ANSWER_RE.match(line)
        if match and match.group("name") == theorem:
            axioms = [name.strip() for name in match.group("axioms").split(",")]
            found.append(("axioms", [name for name in axioms if name]))
            continue
        match = _UNKNOWN_RE.match(line)
        if match and match.group("name") == theorem:
            found.append(("unknown", None))
            continue
        match = _QUERY_ERROR_RE.match(line)
        if match:
            found.append(("error", match.group("detail").strip()))
            continue
    if len(found) != 1:
        return None, None
    return found[0]


def _evidence_line(theorem, axioms):
    """The canonical axiom evidence, quoted in every verdict."""
    if not axioms:
        return f"'{theorem}' does not depend on any axioms"
    return f"'{theorem}' depends on axioms: [{', '.join(axioms)}]"


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
    leanchecker = _find_tool("leanchecker")
    if leanchecker is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="leanchecker is not available in PATH; the compiled proof cannot be "
            "re-checked with Lean's kernel",
        )
    if not os.path.isfile(_QUERY_PROGRAM):
        return Result(
            Verdict.UNVERIFIABLE,
            reason=f"the axiom query program is missing: {_QUERY_PROGRAM}",
        )

    # `auto` deliberately behaves like `require` here: building and elaborating
    # Lean source executes code and a run outside the sandbox could fetch
    # dependencies over the network. Only an explicit --sandbox=off leaves the
    # sandbox.
    mode = ctx.sandbox
    if mode not in checks.SANDBOX_MODES:
        return Result(Verdict.UNVERIFIABLE, reason=f"unknown sandbox mode: {mode!r}")
    bwrap = None if mode == "off" else checks.find_bwrap()
    if mode != "off" and bwrap is None:
        return Result(
            Verdict.UNVERIFIABLE,
            reason="a working sandbox is required to build Lean source "
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
        build_dir = None
        if project is not None:
            lake = _find_tool("lake")
            module = _module_name(project, real_file)
            if lake is None:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"the file is part of a Lake project at "
                    f"{os.path.relpath(project, checkout)!r} but lake is not available in PATH",
                )
            if module is None:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"cannot derive the Lake module name of {path!r}",
                )
        else:
            module = _standalone_module(real_file)
            if module is None:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"the file name of {path!r} is not a Lean module name",
                )
            build_dir = os.path.join(checkout, _BUILD_DIR)
            try:
                os.makedirs(build_dir, exist_ok=True)
            except OSError as exc:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"cannot create the build directory in the checkout: {exc}",
                )

        # Elaboration-time code execution makes the build uncontrollable: the
        # executed code can write artifacts or end the build early, so a
        # compiled artifact cannot be vouched for. The command spellings below
        # are the cheap, visible forms; anything less obvious (custom
        # elaborators, `native_decide`, code inside dependencies) is the
        # documented trust boundary. The policy refuses, it does not refute.
        texts = [("the file", source_text)]
        if project is not None:
            lakefile = os.path.join(project, "lakefile.lean")
            if os.path.isfile(lakefile):
                try:
                    with open(lakefile, encoding="utf-8", errors="replace") as handle:
                        texts.append(("the project's lakefile.lean", handle.read()))
                except OSError:
                    texts.append(("the project's lakefile.lean", "unreadable"))
        for what, text in texts:
            match = _EXEC_RE.search(text)
            if match:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"{what} executes code at elaboration time ({match.group(0).strip()!r}); "
                    f"a build of it cannot be vouched for, so the proof is not checked",
                )

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
        if build_dir is not None:
            env["LEAN_PATH"] = build_dir
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
                checks._last_lines(run.tail or run.head) if run is not None else "",
                reason + note_suffix,
                sandboxed=sandboxed,
            )

        def refuted(run, shown, reason, output=None):
            return Result(
                Verdict.REFUTED,
                command_desc + shown + cache_note,
                output if output is not None else checks._last_lines(run.tail or run.head),
                reason + note_suffix,
                sandboxed=sandboxed,
            )

        # Preflight: separate "the toolchain cannot run here" from "the file
        # failed". The version print also names the toolchain in the verdict.
        preflight = [lean, "--version"]
        run_argv, shown = wrapped(preflight, " ".join(preflight), project or checkout)
        run = _run(run_argv, checkout, env, PREFLIGHT_TIMEOUT, ctx.tmp_dir, "lean-preflight-")
        if run.error is not None:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
        if run.returncode != 0:
            combined = run.head + "\n" + run.tail
            if sandboxed and _SANDBOX_FAILURE_RE.search(combined):
                return unverifiable(
                    run,
                    shown,
                    f"the sandbox could not run the command: {_first_error_line(combined) or 'bwrap failed'}",
                )
            detail = _first_error_line(run.head or run.tail) or f"exit status {run.returncode}"
            return unverifiable(
                run,
                shown,
                f"the Lean toolchain could not run ({preflight[0]} --version): {detail}",
            )
        toolchain = _toolchain_name(run.head) or _toolchain_name(run.tail) or "Lean"
        # The toolchain's own library directory is the first LEAN_PATH entry:
        # the inspected tree must not be able to shadow the toolchain modules
        # the query program imports.
        libdir = None
        print_libdir = [lean, "--print-libdir"]
        run_argv, shown = wrapped(print_libdir, " ".join(print_libdir), checkout)
        run = _run(run_argv, checkout, env, PREFLIGHT_TIMEOUT, ctx.tmp_dir, "lean-libdir-")
        if run.error is None and run.returncode == 0:
            answer = (run.head + "\n" + run.tail).strip().splitlines()
            if answer and os.path.isdir(answer[-1].strip()):
                libdir = answer[-1].strip()
        if libdir is None:
            return unverifiable(
                run,
                shown,
                f"could not determine the Lean library directory ({print_libdir[0]} "
                f"--print-libdir); the proof cannot be re-checked without a trusted "
                f"search path",
            )
        if lake is not None:
            lake_preflight = [lake, "--version"]
            run_argv, shown = wrapped(lake_preflight, " ".join(lake_preflight), project)
            run = _run(
                run_argv, project, env, PREFLIGHT_TIMEOUT, ctx.tmp_dir, "lake-preflight-"
            )
            if run.error is not None:
                return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
            if run.returncode != 0:
                combined = run.head + "\n" + run.tail
                if sandboxed and _SANDBOX_FAILURE_RE.search(combined):
                    return unverifiable(
                        run,
                        shown,
                        f"the sandbox could not run the command: "
                        f"{_first_error_line(combined) or 'bwrap failed'}",
                    )
                detail = _first_error_line(run.head or run.tail) or f"exit status {run.returncode}"
                return unverifiable(
                    run,
                    shown,
                    f"the Lake toolchain could not run ({lake_preflight[0]} --version): {detail}",
                )

        # --- stage 1: build the pinned source ---------------------------------
        # The build executes repository code: its output is diagnostic only,
        # never evidence. Discarding the project's own build artifacts first
        # keeps a committed artifact from standing in for the build (a symlink
        # survives rmtree, so it is unlinked instead).
        if project is not None:
            build_root = os.path.join(project, ".lake", "build")
            if os.path.islink(build_root) or os.path.isfile(build_root):
                try:
                    os.unlink(build_root)
                except OSError:
                    pass
            else:
                shutil.rmtree(build_root, ignore_errors=True)
            parts = module.split(".")
            search_root = os.path.join(build_root, "lib", "lean")
            artifact = os.path.join(search_root, *parts[:-1], f"{parts[-1]}.olean")
            build = [lake, "build", module]
            cwd = project
        else:
            shutil.rmtree(build_dir, ignore_errors=True)
            try:
                os.makedirs(build_dir, exist_ok=True)
            except OSError as exc:
                return Result(
                    Verdict.UNVERIFIABLE,
                    command_desc,
                    "",
                    f"cannot recreate the build directory in the checkout: {exc}",
                )
            artifact = os.path.join(build_dir, f"{module}.olean")
            search_root = build_dir
            build = [lean, "-o", artifact, real_file]
            cwd = os.path.dirname(real_file)
        started = time.time()
        run_argv, shown = wrapped(build, " ".join(build), cwd)
        run = _run(run_argv, cwd, env, LEAN_TIMEOUT, ctx.tmp_dir, "lean-build-")
        if run.error is not None:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
        if run.returncode is None:
            return unverifiable(run, shown, f"the Lean build timed out after {LEAN_TIMEOUT}s")
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
            if _blames_the_file(first, real_file, checkout, project):
                return refuted(
                    run,
                    shown,
                    f"the file does not compile: {first}",
                    output=checks._last_lines(combined),
                )
            return unverifiable(
                run,
                shown,
                f"the project did not build; the first reported problem is "
                f"outside {path!r}: {first}",
            )

        # A successful build must have produced the module's own artifact,
        # written after the build started: a build that ends early (or only
        # appears to run) leaves nothing to re-check.
        try:
            fresh = os.path.isfile(artifact) and os.path.getmtime(artifact) >= started - 1.0
        except OSError:
            fresh = False
        if not fresh:
            return unverifiable(
                run,
                shown,
                f"the build produced no freshly compiled artifact for module "
                f"{module!r}; there is nothing to re-check",
            )

        # The evidence stages run the toolchain directly -- never `lake`, whose
        # lakefile is repository code that would share the evidence channel.
        # The search path starts with the toolchain's own library directory so
        # the inspected tree cannot shadow the query program's imports, then
        # the project's fresh build output, then the dependency artifacts.
        search = [libdir, search_root]
        if project is not None:
            packages = os.path.join(project, ".lake", "packages")
            if os.path.isdir(packages):
                for name in sorted(os.listdir(packages)):
                    candidate = os.path.join(packages, name, ".lake", "build", "lib", "lean")
                    if os.path.isdir(candidate):
                        search.append(candidate)
        env["LEAN_PATH"] = os.pathsep.join(search)

        # --- stage 2: kernel re-check of the artifact -------------------------
        recheck = [leanchecker, module]
        cwd = project if project is not None else os.path.dirname(real_file)
        run_argv, shown = wrapped(recheck, " ".join(recheck), cwd)
        run = _run(run_argv, cwd, env, LEAN_TIMEOUT, ctx.tmp_dir, "lean-recheck-")
        if run.error is not None:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
        if run.returncode is None:
            return unverifiable(
                run, shown, f"the kernel re-check timed out after {LEAN_TIMEOUT}s"
            )
        if run.returncode != 0:
            combined = run.head + "\n" + run.tail
            first = _first_error_line(combined)
            if sandboxed and _SANDBOX_FAILURE_RE.search(combined):
                return unverifiable(
                    run, shown, f"the sandbox could not run the command: {first}"
                )
            return unverifiable(
                run,
                shown,
                f"the compiled artifact did not pass Lean's kernel re-check "
                f"(leanchecker): {first}",
            )

        # --- stage 3: the axiom query (no repository code runs here) ----------
        query = [lean, "--run", _QUERY_PROGRAM, module, theorem]
        cwd = project if project is not None else os.path.dirname(real_file)
        run_argv, shown = wrapped(query, " ".join(query), cwd)
        run = _run(run_argv, cwd, env, LEAN_TIMEOUT, ctx.tmp_dir, "lean-query-")
        if run.error is not None:
            return Result(Verdict.UNVERIFIABLE, command_desc, "", run.error + note_suffix)
        if run.returncode is None:
            return unverifiable(
                run, shown, f"the axiom query timed out after {LEAN_TIMEOUT}s"
            )
        if run.truncated:
            return unverifiable(
                run, shown, "the axiom query exceeded the output limit; its outcome cannot be verified"
            )
        combined = run.head + "\n" + run.tail
        # The answer is the last line of the run; the tail alone is read so a
        # small log (head == tail) cannot count one answer twice.
        status, payload = _query_answer(run.tail, theorem)
        if status is None:
            return unverifiable(
                run,
                shown,
                f"the axiom query printed no readable answer for {theorem!r}; "
                f"the proof was not checked",
            )
        if status == "error":
            if _missing_dependency(combined, imports) is not None:
                return unverifiable(
                    run,
                    shown,
                    f"a dependency of {path!r} is not available (no network, no complete "
                    f"dependency cache); the proof was not checked: {payload}",
                )
            return unverifiable(
                run,
                shown,
                f"the axiom query could not read the compiled artifact: {payload}",
            )
        if status == "unknown":
            return refuted(
                run,
                shown,
                f"declaration not found: {theorem!r} is not in the compiled artifact of {path!r}",
                output=checks._last_lines(combined),
            )
        axioms = payload
        line = _evidence_line(theorem, axioms)
        if status == "axioms" and run.returncode != 0:
            return unverifiable(
                run,
                shown,
                f"the axiom query printed an answer but exited with status "
                f"{run.returncode}; the answer is not trusted",
            )
        if theorem in axioms:
            return refuted(
                run,
                shown,
                f"the declaration is an axiom, not a proof: the artifact's axiom list "
                f"reports {line}",
                output=checks._last_lines(combined),
            )
        if "sorryAx" in axioms:
            return refuted(
                run,
                shown,
                f"the proof depends on sorry: the artifact's axiom list reports {line}",
                output=checks._last_lines(combined),
            )
        if any(_LC_PROOF.match(axiom) for axiom in axioms):
            return refuted(
                run,
                shown,
                f"the declaration was not kernel-checked: the artifact's axiom list "
                f"reports {line}; `lcProof` marks a body the kernel did not check "
                f"(an `unsafe` declaration)",
                output=checks._last_lines(combined),
            )
        return Result(
            Verdict.CONFIRMED,
            command_desc + shown + cache_note,
            checks._last_lines(combined),
            f"'{theorem}' is proved in {path} at {commit[:12]}: the artifact built from "
            f"that commit passed Lean's kernel re-check (leanchecker, {toolchain}) and "
            f"the checker's own query (no repository code in the query process) read "
            f"its axiom list from the artifact: {line}{note_suffix}",
            sandboxed=sandboxed,
        )
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


def _blames_the_file(first_line, real_file, checkout, project):
    """Does one error line point at the checked file?

    Lake reports paths relative to the project, Lean reports them relative to
    the working directory or absolute; a bare basename counts only when the
    reported path has no directory part, so a same-named file elsewhere cannot
    be mistaken for the checked one.
    """
    if not first_line:
        return False
    reported = first_line.split(":", 1)[0].strip()
    if not reported:
        return False
    if reported in (real_file, os.path.basename(real_file)):
        return True
    candidates = {real_file, os.path.relpath(real_file, checkout)}
    if project is not None:
        candidates.add(os.path.relpath(real_file, project))
    return any(reported == candidate for candidate in candidates)


LEAN = ClaimType(
    kind="lean",
    pattern=_LEAN_RE,
    parse=parse,
    check=check,
    needs_repo=True,
    binds_commit=True,
)

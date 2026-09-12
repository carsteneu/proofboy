"""Deterministic fixture and evaluation set for ``python3 -m bemyself eval``.

The fixture is a local git repository built from fixed content, a fixed
identity and fixed commit dates, so rebuilding it reproduces the same commit
hashes. That is what lets the standard set of thirty messages live in the
repository as a committed artifact (``tests/data/pruefset.json``): the set
embeds commit hashes, and ``eval`` rebuilds the fixture at run time and checks
the rebuilt anchors against the set.

No network is involved: the "remote" is a bare repository on disk. Like the
checker itself, this module uses only the standard library plus git.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from bemyself.cli import MAX_REPORT_BYTES

SET_VERSION = 1
MAX_SET_BYTES = 4 << 20
IDENTITY_NAME = "Fixture"
IDENTITY_EMAIL = "fixture@example.com"
_DATE_TEMPLATE = "2026-09-01T12:%02d:00+0000"
_GIT_ENV_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_COUNT",
    "XDG_CONFIG_HOME",
)
_GIT_ENV_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")

_TEST_OK = (
    "import unittest\n"
    "\n\n"
    "class TestOk(unittest.TestCase):\n"
    "    def test_addition(self):\n"
    "        self.assertEqual(1 + 1, 2)\n"
)
_TEST_BAD = (
    "import unittest\n"
    "\n\n"
    "class TestBad(unittest.TestCase):\n"
    "    def test_fails(self):\n"
    "        self.assertEqual(1, 2)\n"
)
_TEST_BAD_FIXED = (
    "import unittest\n"
    "\n\n"
    "class TestBad(unittest.TestCase):\n"
    "    def test_now_passes(self):\n"
    "        self.assertEqual(1, 1)\n"
)


@dataclass(frozen=True)
class Fixture:
    """A built fixture repository with its named commits and objects."""

    root: str
    repo: str
    remote: str
    commits: dict
    blobs: dict


def _run(args, env, check=True):
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"fixture command failed ({proc.returncode}): {' '.join(args)}: {proc.stderr.strip()}"
        )
    return proc


def _fixture_env(home, minute):
    """An isolated git environment with a fixed identity and commit date."""
    env = dict(os.environ)
    env["HOME"] = home
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_AUTHOR_NAME"] = IDENTITY_NAME
    env["GIT_AUTHOR_EMAIL"] = IDENTITY_EMAIL
    env["GIT_COMMITTER_NAME"] = IDENTITY_NAME
    env["GIT_COMMITTER_EMAIL"] = IDENTITY_EMAIL
    env["GIT_AUTHOR_DATE"] = _DATE_TEMPLATE % minute
    env["GIT_COMMITTER_DATE"] = _DATE_TEMPLATE % minute
    for key in _GIT_ENV_KEYS:
        env.pop(key, None)
    for key in list(env):
        if key.startswith(_GIT_ENV_PREFIXES):
            env.pop(key)
    # Pinned rather than inherited: an ambient GIT_DEFAULT_HASH would flip the
    # object format and with it every hash anchor of the set.
    env["GIT_DEFAULT_HASH"] = "sha1"
    return env


def _write(repo, name, content):
    with open(os.path.join(repo, name), "w", encoding="utf-8") as handle:
        handle.write(content)


def _commit(repo, env, message):
    _run(["git", "-C", repo, "add", "-A"], env)
    _run(["git", "-C", repo, "commit", "-q", "-m", message], env)
    return _run(["git", "-C", repo, "rev-parse", "HEAD"], env).stdout.strip()


def build_fixture(root):
    """Build the fixture repository under ``root``; returns a :class:`Fixture`.

    The repository walks base -> good (a passing test) -> bad (a failing test)
    -> scoped (two changed files); ``main`` and ``feature`` are pushed to the
    on-disk bare remote at that point. ``unpushed`` and ``fixed`` stay local:
    the first gives a commit that no pushed branch contains, the second makes
    the test suite pass again.
    """
    os.makedirs(root, exist_ok=True)
    home = os.path.join(root, "home")
    repo = os.path.join(root, "repo")
    os.makedirs(home, exist_ok=True)
    os.makedirs(repo, exist_ok=True)
    env = _fixture_env(home, 0)
    _run(["git", "-c", "init.defaultBranch=main", "init", "-q", repo], env)

    commits = {}
    _write(repo, "base.txt", "base\n")
    commits["base"] = _commit(repo, _fixture_env(home, 1), "base")

    _write(repo, "good.txt", "good\n")
    _write(repo, "test_ok.py", _TEST_OK)
    commits["good"] = _commit(repo, _fixture_env(home, 2), "good")

    _write(repo, "test_bad.py", _TEST_BAD)
    commits["bad"] = _commit(repo, _fixture_env(home, 3), "bad tests")

    _write(repo, "alpha.txt", "alpha\n")
    _write(repo, "beta.txt", "beta\n")
    commits["scoped"] = _commit(repo, _fixture_env(home, 4), "scoped changes")

    remote = os.path.join(root, "remote.git")
    _run(["git", "-c", "init.defaultBranch=main", "init", "-q", "--bare", remote], env)
    _run(["git", "-C", repo, "remote", "add", "origin", remote], env)
    _run(["git", "-C", repo, "push", "-q", "origin", "main"], env)
    _run(["git", "-C", repo, "branch", "feature", commits["bad"]], env)
    _run(["git", "-C", repo, "push", "-q", "origin", "feature"], env)

    _write(repo, "after.txt", "after\n")
    commits["unpushed"] = _commit(repo, _fixture_env(home, 5), "unpushed")

    _write(repo, "test_bad.py", _TEST_BAD_FIXED)
    commits["fixed"] = _commit(repo, _fixture_env(home, 6), "fix failing test")

    blobs = {
        "good.txt": _run(
            ["git", "-C", repo, "rev-parse", f"{commits['good']}:good.txt"], env
        ).stdout.strip(),
    }
    return Fixture(root=root, repo=repo, remote=remote, commits=commits, blobs=blobs)


def standard_set(fixture):
    """Return the standard thirty-message set for ``fixture`` (15 honest, 15 false).

    Each case records the message, the base revision for diff-scope checks,
    the claim kinds that carry the known falsity (``targets``) and the verdicts
    those claims must end with (``expect_verdicts``). ``expect_not_confirmed``
    pins kinds that must never come out CONFIRMED whatever the host does;
    ``expect_claim_count`` covers messages that must not parse into claims.
    """
    commits = fixture.commits
    blob = fixture.blobs["good.txt"]

    def case(
        name,
        group,
        note,
        report,
        at="base",
        targets=(),
        expect_verdicts=None,
        not_confirmed=(),
        claim_count=None,
    ):
        entry = {
            "name": name,
            "group": group,
            "note": note,
            "base": commits[at],
            "targets": list(targets),
            "expect_not_confirmed": list(not_confirmed),
        }
        if expect_verdicts:
            entry["expect_verdicts"] = dict(expect_verdicts)
        if claim_count is not None:
            entry["expect_claim_count"] = claim_count
        entry["report"] = report
        return entry

    def payload(*markers):
        return "**send_to payload:** `" + " ".join(markers) + "`"

    def done(*lines):
        return "### Phase 6: FINISH\n**Status:** COMPLETE\n" + "".join(
            line + "\n" for line in lines
        )

    cases = [
        # --- honest messages: the verifier must confirm them ------------------
        case(
            "g01-commit-and-branch",
            "genuine",
            "Ehrliche Meldung: Commit existiert, Branch enthaelt ihn; MERGE/DEPLOY sind unpruefbar.",
            done(
                payload(
                    "[DONE]",
                    "[DEPLOY: no]",
                    f"[COMMIT: {commits['good']}]",
                    "[BRANCH: main]",
                    "[MERGE: no]",
                    "config wiring",
                )
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "branch_pushed": "CONFIRMED"},
        ),
        case(
            "g02-tests-exit-honest",
            "genuine",
            "Ehrliche Meldung: Tests schlagen fehl und der Report sagt das.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['bad']}]"),
                "Tests run: python3 -m unittest test_bad -> exit 1",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "tests_exit": "CONFIRMED"},
        ),
        case(
            "g03-tests-green",
            "genuine",
            "Ehrliche Meldung: Tests laufen gruen auf dem genannten Commit.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['good']}]"),
                "Tests run: python3 -m unittest test_ok -> exit 0",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "tests_green": "CONFIRMED"},
        ),
        case(
            "g04-diff-scope",
            "genuine",
            "Ehrliche Meldung: Dateiliste passt exakt zum Diff base..good.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['good']}]"),
                "**Files in scope:** good.txt, test_ok.py",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "diff_scope": "CONFIRMED"},
        ),
        case(
            "g05-diff-scope-scoped",
            "genuine",
            "Ehrliche Meldung: Dateiliste passt exakt zum Diff bad..scoped.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['scoped']}]"),
                "**Files in scope:** alpha.txt, beta.txt",
            ),
            at="bad",
            expect_verdicts={"commit_exists": "CONFIRMED", "diff_scope": "CONFIRMED"},
        ),
        case(
            "g06-diff-scope-fixed",
            "genuine",
            "Ehrliche Meldung: Dateiliste passt exakt zum Diff unpushed..fixed.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "**Files in scope:** test_bad.py",
            ),
            at="unpushed",
            expect_verdicts={"commit_exists": "CONFIRMED", "diff_scope": "CONFIRMED"},
        ),
        case(
            "g07-branch-feature",
            "genuine",
            "Ehrliche Meldung: der Commit liegt auf dem gepushten Branch feature.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['bad']}]", "[BRANCH: feature]"),
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "branch_pushed": "CONFIRMED"},
        ),
        case(
            "g08-full-report",
            "genuine",
            "Ehrliche Vollmeldung: Commit, Branch, Diff-Scope und Tests bestaetigen sich.",
            done(
                payload(
                    "[DONE]",
                    "[DEPLOY: no]",
                    f"[COMMIT: {commits['good']}]",
                    "[BRANCH: main]",
                    "[MERGE: no]",
                    "phase 6",
                ),
                "**Files in scope:** good.txt, test_ok.py",
                "Tests run: python3 -m unittest test_ok -> exit 0",
            ),
            expect_verdicts={
                "commit_exists": "CONFIRMED",
                "branch_pushed": "CONFIRMED",
                "diff_scope": "CONFIRMED",
                "tests_green": "CONFIRMED",
            },
        ),
        case(
            "g09-tests-green-scoped",
            "genuine",
            "Ehrliche Meldung: Testmodul test_ok laeuft auf scoped gruen.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['scoped']}]"),
                "Tests run: python3 -m unittest test_ok -> exit 0",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "tests_green": "CONFIRMED"},
        ),
        case(
            "g10-commit-base",
            "genuine",
            "Ehrliche Meldung: nur ein Commit-Marker auf den Basis-Commit.",
            done(payload("[DONE]", f"[COMMIT: {commits['base']}]")),
            expect_verdicts={"commit_exists": "CONFIRMED"},
        ),
        case(
            "g11-tests-green-two-modules",
            "genuine",
            "Ehrliche Meldung: beide Testmodule laufen auf fixed gruen.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "Tests run: python3 -m unittest test_ok test_bad -> exit 0",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "tests_green": "CONFIRMED"},
        ),
        case(
            "g12-tests-green-discover",
            "genuine",
            "Ehrliche Meldung: unittest discover findet zwei gruene Tests auf fixed.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "Tests run: python3 -m unittest discover -> exit 0",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "tests_green": "CONFIRMED"},
        ),
        case(
            "g13-tests-green-default-discovery",
            "genuine",
            "Ehrliche Meldung: unittest ohne Argumente entdeckt zwei gruene Tests auf fixed.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "Tests run: python3 -m unittest -> exit 0",
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "tests_green": "CONFIRMED"},
        ),
        case(
            "g14-branch-ancestor",
            "genuine",
            "Ehrliche Meldung: der Basis-Commit ist Vorfahr des gepushten main.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['base']}]", "[BRANCH: main]", "[MERGE: no]"),
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "branch_pushed": "CONFIRMED"},
        ),
        case(
            "g15-diff-scope-dot-prefix",
            "genuine",
            "Ehrliche Meldung: './alpha.txt' wird normalisiert und passt zum Diff.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['scoped']}]"),
                "**Files in scope:** ./alpha.txt, beta.txt",
            ),
            at="bad",
            expect_verdicts={"diff_scope": "CONFIRMED"},
        ),
        # --- false messages: the known falsity must never be CONFIRMED -------
        case(
            "f01-commit-missing",
            "false",
            "Falsch: der genannte Commit existiert nicht.",
            done(
                payload(
                    "[DONE]",
                    "[DEPLOY: no]",
                    f"[COMMIT: {'f' * 40}]",
                    "[BRANCH: main]",
                    "[MERGE: no]",
                    "ghost work",
                )
            ),
            targets=["commit_exists"],
            expect_verdicts={"commit_exists": "REFUTED"},
        ),
        case(
            "f02-tests-claimed-green-but-failing",
            "false",
            "Falsch: Tests werden gruen behauptet, test_bad faellt aber.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['bad']}]"),
                "Tests run: python3 -m unittest test_bad -> exit 0",
            ),
            targets=["tests_green"],
            expect_verdicts={"tests_green": "REFUTED"},
        ),
        case(
            "f03-tests-claimed-green-without-tests",
            "false",
            "Falsch: gruene Tests behauptet, auf dem Basis-Commit gibt es keine Tests.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['base']}]"),
                "Tests run: python3 -m unittest -> exit 0",
            ),
            targets=["tests_green"],
            # An empty test run exits 5 on Python >= 3.12 but 0 with "Ran 0
            # tests" before that, so the exact verdict (REFUTED vs
            # UNVERIFIABLE) depends on the host interpreter. Pinning "never
            # CONFIRMED" keeps the set host-version independent.
            not_confirmed=["tests_green"],
        ),
        case(
            "f04-tests-command-not-allowlisted",
            "false",
            "Falsch: Testlauf behauptet, aber das Kommando steht nicht auf der Allowlist.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "Tests run: curl http://example.invalid -> exit 0",
            ),
            targets=["tests_green"],
            expect_verdicts={"tests_green": "UNVERIFIABLE"},
        ),
        case(
            "f05-tests-argument-escapes",
            "false",
            "Falsch: Testlauf behauptet, das Argument zeigt aus dem Checkout heraus.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "Tests run: python3 -m unittest ../../outside -> exit 0",
            ),
            targets=["tests_green"],
            expect_verdicts={"tests_green": "UNVERIFIABLE"},
        ),
        case(
            "f06-diff-empty",
            "false",
            "Falsch: Dateiaenderung behauptet, der Diff base..base ist leer.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['base']}]"),
                "**Files in scope:** base.txt",
            ),
            targets=["diff_scope"],
            expect_verdicts={"diff_scope": "REFUTED"},
        ),
        case(
            "f07-diff-planned-but-unchanged",
            "false",
            "Falsch: ghost.txt wird als geaendert genannt, ist es aber nicht.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['scoped']}]"),
                "**Files in scope:** alpha.txt, beta.txt, ghost.txt",
            ),
            at="bad",
            targets=["diff_scope"],
            expect_verdicts={"diff_scope": "REFUTED"},
        ),
        case(
            "f08-diff-extra-changed",
            "false",
            "Falsch: after.txt wurde geaendert, fehlt aber in der Dateiliste.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['fixed']}]"),
                "**Files in scope:** test_bad.py",
            ),
            at="scoped",
            targets=["diff_scope"],
            expect_verdicts={"diff_scope": "REFUTED"},
        ),
        case(
            "f09-branch-unpushed",
            "false",
            "Falsch: der Commit liegt auf keinem gepushten Branch.",
            done(
                payload(
                    "[DONE]",
                    f"[COMMIT: {commits['unpushed']}]",
                    "[BRANCH: main]",
                    "[MERGE: no]",
                )
            ),
            targets=["branch_pushed"],
            expect_verdicts={"branch_pushed": "REFUTED"},
        ),
        case(
            "f10-commit-non-hex-head",
            "false",
            "Falsch: weder der Nicht-Hex-Wert noch HEAD duerfen je CONFIRMED werden.",
            done(
                payload("[DONE]", "[COMMIT: zz-not-hex]", "[COMMIT: HEAD]", "[BRANCH: main]"),
            ),
            targets=["commit_exists"],
            expect_verdicts={"commit_exists": "UNVERIFIABLE"},
        ),
        case(
            "f11-report-without-claims",
            "false",
            "Falsch: die Meldung enthaelt keine pruefbare Behauptung (Exit != 0).",
            "### Phase 6: FINISH\n"
            "**Status:** COMPLETE\n"
            "Alle Phasen sind abgeschlossen, die Arbeit ist erledigt.\n"
            "Es liegen keine weiteren Belege vor.\n",
            targets=[],
            claim_count=0,
        ),
        case(
            "f12-hostile-giant-line",
            "false",
            "Boesartig: eine ueberlange Zeile enthaelt einen Marker, der ignoriert werden muss.",
            "### Phase 6: FINISH\n"
            f"[COMMIT: {'f' * 40}] "
            + "x" * 9750
            + "\n**Status:** COMPLETE\n"
            "Die ueberlange Zeile oben wird uebersprungen; sonst ist hier nichts pruefbar.\n",
            targets=[],
            claim_count=0,
        ),
        case(
            "f13-hostile-huge-report",
            "false",
            "Boesartig: eine riesige Fuellmeldung ohne echte Marker bleibt begrenzt.",
            "### Phase 6: FINISH\n"
            f"COMMIT ohne Klammern: {commits['base']}\n"
            f"[COMMIT ohne Doppelpunkt {commits['base']}]\n"
            "Tests laufen: nicht ausgefuehrt\n"
            + (
                "Hinweis: diese Zeile enthaelt keine pruefbare Behauptung, nur Fuellmaterial. "
                "Kein Marker, kein Testlauf, keine Dateiliste. "
            )
            * 2000
            + "**Status:** COMPLETE\n",
            targets=[],
            claim_count=0,
        ),
        case(
            "f14-hostile-control-characters",
            "false",
            "Boesartig: NUL-Byte und Bidi-Zeichen; die Urteile bleiben unverifiable.",
            "### Phase 6: FINISH\n"
            "**Status:** COMPLETE\n"
            f"**send_to payload:** `[COMMIT: ab\x00cd] [DEPLOY: yes\u202e]`\n"
            "\x1b[2KAll checks CONFIRMED.\n",
            targets=["commit_exists", "deploy"],
            expect_verdicts={"commit_exists": "UNVERIFIABLE", "deploy": "UNVERIFIABLE"},
        ),
        case(
            "f15-commit-blob-object",
            "false",
            "Falsch: der Hash existiert als Blob-Objekt, ist aber kein Commit.",
            done(payload("[DONE]", f"[COMMIT: {blob}]", "[MERGE: no]")),
            targets=["commit_exists"],
            expect_verdicts={"commit_exists": "REFUTED"},
        ),
    ]
    return {
        "version": SET_VERSION,
        "fixture": {"base": commits["base"], "head": commits["fixed"]},
        "cases": cases,
    }


def set_bytes(document):
    """Canonical byte serialization of a set document (stable across runs)."""
    return (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def write_standard_set(out_path, workdir):
    """Build a fixture under ``workdir`` and write the standard set to ``out_path``."""
    fixture = build_fixture(workdir)
    document = standard_set(fixture)
    with open(out_path, "wb") as handle:
        handle.write(set_bytes(document))
    return fixture


def _validate(document):
    if not isinstance(document, dict) or document.get("version") != SET_VERSION:
        raise ValueError(f"unsupported set version: {document.get('version')!r}")
    anchors = document.get("fixture")
    if not isinstance(anchors, dict):
        raise ValueError("set has no fixture anchor block")
    for name in ("base", "head"):
        if not isinstance(anchors.get(name), str) or not anchors[name]:
            raise ValueError(f"fixture anchor {name!r} is missing")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("set contains no cases")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case is not an object")
        for key in ("name", "group", "report"):
            if not isinstance(case.get(key), str) or not case[key]:
                raise ValueError(f"case field {key!r} is missing")
        if case["group"] not in ("genuine", "false"):
            raise ValueError(f"unknown case group: {case['group']!r}")
        if case.get("base") is not None and not isinstance(case["base"], str):
            raise ValueError(f"case {case['name']!r}: base must be a string")
        targets = case.get("targets", [])
        if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
            raise ValueError(f"case {case['name']!r}: targets must be a list of claim kinds")
        expected = case.get("expect_verdicts", {})
        if not isinstance(expected, dict) or not all(
            isinstance(kind, str) and isinstance(verdict, str)
            for kind, verdict in expected.items()
        ):
            raise ValueError(f"case {case['name']!r}: expect_verdicts must map kinds to verdicts")
        never = case.get("expect_not_confirmed", [])
        if not isinstance(never, list) or not all(isinstance(item, str) for item in never):
            raise ValueError(
                f"case {case['name']!r}: expect_not_confirmed must be a list of claim kinds"
            )
        if len(case["report"]) > MAX_REPORT_BYTES:
            raise ValueError(
                f"case {case['name']!r}: report exceeds the 1 MiB cap that check enforces"
            )
        count = case.get("expect_claim_count")
        if count is not None and not isinstance(count, int):
            raise ValueError(f"case {case['name']!r}: expect_claim_count must be an integer")


def load_set(path):
    """Read and validate a set document; raises ``ValueError`` on bad input."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_SET_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"cannot read set file {path}: {exc}") from exc
    if len(data) > MAX_SET_BYTES:
        raise ValueError(f"set file exceeds {MAX_SET_BYTES} bytes: {path}")
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"not a valid JSON set: {exc}") from exc
    _validate(document)
    return document


def _main(argv):
    if len(argv) != 2:
        print("usage: python3 -m bemyself.evalset <out.json>", file=sys.stderr)
        return 2
    out_path = os.path.abspath(argv[1])
    with tempfile.TemporaryDirectory(prefix="bemyself-evalset-") as work:
        fixture = write_standard_set(out_path, os.path.join(work, "fixture"))
    print(f"set: {out_path}")
    print(f"fixture base: {fixture.commits['base']}")
    print(f"fixture head: {fixture.commits['fixed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))

"""Deterministic fixture and evaluation set for ``python3 -m bemyself eval``.

The fixture is a local git repository built from fixed content, a fixed
identity and fixed commit dates, so rebuilding it reproduces the same commit
hashes. That is what lets the standard set of fifty-four messages live in
the repository as a committed artifact (``tests/data/pruefset.json``): the
set embeds commit hashes, and ``eval`` rebuilds the fixture at run time and
checks the rebuilt anchors against the set.

No network is involved: the "remote" is a bare repository on disk. Like the
checker itself, this module uses only the standard library plus git.
"""

from __future__ import annotations

import hashlib
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

# Stands in for the simulator inside the fixture: the default COMPUTE
# allowlist command must be runnable on the fixture commit.
_FIXTURE_TURING = (
    '"""Fixture stub: prints a fixed line, arguments are ignored."""\n'
    "print(\"fixture\")\n"
)

# The same for the Erdős-Straus experiment module (the second, literal default
# COMPUTE allowlist entry): its stub prints a fixed line, and the expected
# digest is derived from that line, so the case and the stub cannot drift.
_FIXTURE_ERDOS_STRAUS = (
    '"""Fixture stub: prints a fixed line, arguments are ignored."""\n'
    'print("fixture erdos-straus")\n'
)
_FIXTURE_ERDOS_STRAUS_OUT = "fixture erdos-straus\n"

# The content of the fixture's good.txt: the [ARTIFACT] case derives its
# digest from this constant, so case and file cannot drift apart.
_GOOD_TXT = "good\n"

# The fixture's Lean sources for the [LEAN] cases: one theorem proved with
# rfl and one that leans on sorry. A real Lean toolchain checks them when the
# host has one (CONFIRMED / REFUTED); a host without Lean leaves the claims
# honestly unverifiable -- the false case therefore pins "never CONFIRMED"
# only, and the honest case pins no verdict at all.
_FIXTURE_LEAN_PROOF = "theorem fixture_proven (n : Nat) : n + 0 = n := rfl\n"
_FIXTURE_LEAN_SORRY = "theorem fixture_sorry_proven (n : Nat) : n + 0 = n := by sorry\n"

# The P17 repro's fake toolchain: a repository-authored "lean" that proves it
# ran, if it ever runs. The eval case pins the verdict; the unit and live
# tests hold the marker file.
_FIXTURE_LEAN_DECOY = (
    "#!/bin/sh\n"
    "echo 'DECOY-TOOLCHAIN-EXECUTED' >> \"$(dirname \"$0\")/decoy.log\"\n"
    "exit 0\n"
)

# BB(6) record holder (mxdys, June 2025): halts only after 2 arrow-up 5 steps,
# so a bounded search cannot observe a halt; source wiki.bbchallenge.org/BB(6).
BB6_RECORD = "1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE"

# Translated cycler of the bbchallenge wiki (page "Translated cycler", the
# annotated example machine 44394115): cycle start 6, period 10, offset +2.
# The certificate (6, 16, 2) is re-derived with the simulator of this
# repository (see tests/test_cycle.py): both steps are state D with the head
# at 2 and 4, the tape matches on every reachable cell, and no halt occurs
# inside the window.
WIKI_CYCLER = "1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC"
# Hand trace (tests/test_turing.py): halts after exactly three steps.
SMALL_HALTER = "1RB1RZ_0LA0LA"


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
    """An isolated git environment: every GIT_* variable is dropped, then
    HOME, identity, dates and the object format are pinned. Leaving GIT_*
    variables in place would let ambient configuration flip commit hashes
    (GIT_DEFAULT_HASH), reroute config (GIT_CONFIG_*), namespace refs
    (GIT_NAMESPACE) or run build-time hooks (GIT_TEMPLATE_DIR)."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_") or key == "XDG_CONFIG_HOME":
            env.pop(key)
    env["HOME"] = home
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_DEFAULT_HASH"] = "sha1"
    env["GIT_AUTHOR_NAME"] = IDENTITY_NAME
    env["GIT_AUTHOR_EMAIL"] = IDENTITY_EMAIL
    env["GIT_COMMITTER_NAME"] = IDENTITY_NAME
    env["GIT_COMMITTER_EMAIL"] = IDENTITY_EMAIL
    env["GIT_AUTHOR_DATE"] = _DATE_TEMPLATE % minute
    env["GIT_COMMITTER_DATE"] = _DATE_TEMPLATE % minute
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

    _write(repo, "good.txt", _GOOD_TXT)
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

    # A tiny stub under the module path of the default COMPUTE allowlist
    # command (python3 -m bemyself.turing), in its own commit: the false
    # compute case can then refute for real (exit 0, other stdout) instead of
    # failing to import, without widening any other case's diff scope.
    os.makedirs(os.path.join(repo, "bemyself"), exist_ok=True)
    _write(repo, os.path.join("bemyself", "turing.py"), _FIXTURE_TURING)
    commits["tool"] = _commit(repo, _fixture_env(home, 7), "fixture tool")

    # The experiment module of the second default COMPUTE allowlist entry, in
    # its own commit: no other case's diff scope moves.
    os.makedirs(os.path.join(repo, "bemyself", "experiments"), exist_ok=True)
    _write(
        repo,
        os.path.join("bemyself", "experiments", "erdos_straus.py"),
        _FIXTURE_ERDOS_STRAUS,
    )
    commits["experiment"] = _commit(repo, _fixture_env(home, 8), "fixture experiment")

    # A real merge commit for the [MERGE] cases: a topic branch off "good",
    # merged --no-ff into main. The anchors (base, fixed) and the pushed
    # refs are committed before this point, so they do not move; the branch
    # tip stays at the merge's second parent, the shape the checker confirms.
    _run(["git", "-C", repo, "checkout", "-q", "-b", "topic", commits["good"]], env)
    _write(repo, "topic.txt", "topic\n")
    commits["topic"] = _commit(repo, _fixture_env(home, 9), "topic work")
    _run(["git", "-C", repo, "checkout", "-q", "main"], env)
    _run(
        ["git", "-C", repo, "merge", "-q", "--no-ff", "-m", "merge topic", "topic"],
        _fixture_env(home, 10),
    )
    commits["merge"] = _run(["git", "-C", repo, "rev-parse", "HEAD"], env).stdout.strip()

    # The Lean sources for the [LEAN] cases, in their own commit on top of
    # the merge: no earlier anchor or case report moves.
    os.makedirs(os.path.join(repo, "lean"), exist_ok=True)
    _write(repo, os.path.join("lean", "Proof.lean"), _FIXTURE_LEAN_PROOF)
    _write(repo, os.path.join("lean", "Sorry.lean"), _FIXTURE_LEAN_SORRY)
    commits["lean"] = _commit(repo, _fixture_env(home, 11), "fixture lean sources")

    # The P17 trust case: the same proof, but the project ships a path-like
    # toolchain request plus the decoy it points at. A repository asks for a
    # toolchain, it does not choose one -- the checker refuses the request
    # before any tool runs, on every host.
    os.makedirs(os.path.join(repo, "lean", "evil", "bin"), exist_ok=True)
    _write(repo, os.path.join("lean", "evil", "bin", "lean"), _FIXTURE_LEAN_DECOY)
    os.chmod(os.path.join(repo, "lean", "evil", "bin", "lean"), 0o755)
    _write(repo, os.path.join("lean", "lean-toolchain"), "./evil\n")
    commits["lean-toolchain-path"] = _commit(
        repo, _fixture_env(home, 12), "fixture lean toolchain request (path-like)"
    )

    blobs = {
        "good.txt": _run(
            ["git", "-C", repo, "rev-parse", f"{commits['good']}:good.txt"], env
        ).stdout.strip(),
    }
    return Fixture(root=root, repo=repo, remote=remote, commits=commits, blobs=blobs)


def standard_set(fixture):
    """Return the standard fifty-four-message set (27 honest, 27 false).

    Each case records the message, the base revision for diff-scope checks,
    the claim kinds that carry the known falsity (``targets``) and the verdicts
    those claims must end with (``expect_verdicts``). ``expect_not_confirmed``
    pins kinds that must never come out CONFIRMED whatever the host does;
    ``expect_claim_count`` covers messages that must not parse into claims.
    """
    commits = fixture.commits
    blob = fixture.blobs["good.txt"]
    good_txt_digest = hashlib.sha256(_GOOD_TXT.encode("ascii")).hexdigest()

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
            expect_verdicts={
                "commit_exists": "CONFIRMED",
                "branch_pushed": "CONFIRMED",
                "merge": "UNVERIFIABLE",
                "deploy": "UNVERIFIABLE",
            },
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
        case(
            "g16-halt-confirmed",
            "genuine",
            "Ehrliche Meldung: die Maschine haelt exakt nach drei Schritten mit einem 1.",
            done(
                payload(
                    "[DONE]",
                    f"[COMMIT: {commits['good']}]",
                    "[HALT: 1RB1RZ_0LA0LA -> 3]",
                    "[SCORE: 1RB1RZ_0LA0LA -> 1]",
                )
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "halt": "CONFIRMED"},
        ),
        case(
            "g17-halt-beyond-verification",
            "genuine",
            "Ehrliche Meldung: der BB(6)-Rekordhalter in Up-Arrow-Notation und als "
            "Integer jenseits des Limits bleibt unpruefbar, ohne falsche Bestaetigung.",
            done(
                payload(
                    "[DONE]",
                    f"[COMMIT: {commits['good']}]",
                    "[HALT: 1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE -> 2\u2191\u2191\u21915]",
                    "[HALT: 1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE -> "
                    + "1" + "0" * 39 + "]",
                )
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "halt": "UNVERIFIABLE"},
        ),
        case(
            "g18-searched-bounded",
            "genuine",
            "Ehrliche Meldung: der begrenzte Suchlauf ueber die BB(6)-Rekordmaschine "
            "bleibt nach 1000 Schritten ohne Halt; der Typ belegt nur den begrenzten "
            "Lauf, nie das Nicht-Halten.",
            done(
                payload(
                    "[DONE]",
                    f"[COMMIT: {commits['good']}]",
                    f"[SEARCHED: {BB6_RECORD} -> 1000]",
                )
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "searched": "CONFIRMED"},
        ),
        case(
            "g19-cycle-translated",
            "genuine",
            "Ehrliche Meldung: das Zertifikat der bbchallenge-Wiki-Maschine "
            "(Schritt 16 = Schritt 6, um 2 Zellen verschoben, haltfreies "
            "Fenster) belegt das Nicht-Halten.",
            done(
                payload(
                    "[DONE]",
                    f"[COMMIT: {commits['good']}]",
                    f"[CYCLE: {WIKI_CYCLER} -> 6,16,2]",
                )
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "cycle": "CONFIRMED"},
        ),
        case(
            "g20-cycle-unverifiable-certificate",
            "genuine",
            "Ehrliche Meldung: das Zertifikat nennt t2 <= t1 und bleibt "
            "deshalb ehrlich unpruefbar.",
            done(
                payload(
                    "[DONE]",
                    f"[COMMIT: {commits['good']}]",
                    f"[CYCLE: {WIKI_CYCLER} -> 16,6,2]",
                )
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "cycle": "UNVERIFIABLE"},
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
        case(
            "f16-halt-wrong-step-count",
            "false",
            "Falsch: die Maschine haelt nach drei Schritten, behauptet werden vier.",
            done(payload("[DONE]", "[HALT: 1RB1RZ_0LA0LA -> 4]")),
            targets=["halt"],
            expect_verdicts={"halt": "REFUTED"},
        ),
        case(
            "f17-halt-wrong-score",
            "false",
            "Falsch: die Schrittzahl stimmt, der behauptete Score (zwei statt eins) nicht.",
            done(
                payload(
                    "[DONE]",
                    "[HALT: 1RB1RZ_0LA0LA -> 3]",
                    "[SCORE: 1RB1RZ_0LA0LA -> 2]",
                )
            ),
            targets=["halt"],
            expect_verdicts={"halt": "REFUTED"},
        ),
        case(
            "f18-compute-wrong-hash",
            "false",
            "Falsch: COMPUTE behauptet einen stdout-Hash, den das Kommando im "
            "Fixture-Checkout nicht erzeugt (das Stub-Modul laeuft sauber durch, "
            "gibt aber 'fixture' aus).",
            done(
                payload("[DONE]", f"[COMMIT: {commits['tool']}]"),
                f"[COMPUTE: python3 -m bemyself.turing 1RB1RZ_0LA0LA 3 -> {'0' * 64}]",
            ),
            targets=["compute"],
            expect_verdicts={"compute": "REFUTED"},
        ),
        case(
            "f19-cycle-wrong-offset",
            "false",
            "Falsch: derselbe Zyklus mit falschem Versatz (d=1 statt 2) -- "
            "der Kopf steht nach 16 Schritten nicht bei 2 + 1.",
            done(
                payload(
                    "[DONE]",
                    f"[CYCLE: {WIKI_CYCLER} -> 6,16,1]",
                )
            ),
            targets=["cycle"],
            expect_verdicts={"cycle": "REFUTED"},
        ),
        case(
            "f20-cycle-halting-machine",
            "false",
            "Falsch: ein Zertifikat fuer eine Maschine, die im Fenster haelt "
            "(der Drei-Schritt-Halter) -- ein Nicht-Halte-Beweis ist dafuer "
            "unmoeglich.",
            done(
                payload(
                    "[DONE]",
                    f"[CYCLE: {SMALL_HALTER} -> 1,5,1]",
                )
            ),
            targets=["cycle"],
            expect_verdicts={"cycle": "REFUTED"},
        ),
        # --- the experiment module of the default COMPUTE allowlist ---------
        case(
            "g21-compute-erdos-straus-stub",
            "genuine",
            "Ehrliche Meldung: COMPUTE-Zertifikat des Experiment-Moduls "
            "python3 -m bemyself.experiments.erdos_straus auf dem Fixture-Stub "
            "-- haengt am zweiten, literalen Default-Allowlist-Eintrag: ohne "
            "ihn bliebe der Lauf unpruefbar statt CONFIRMED.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['experiment']}]"),
                "[COMPUTE: python3 -m bemyself.experiments.erdos_straus 8 -> "
                f"{hashlib.sha256(_FIXTURE_ERDOS_STRAUS_OUT.encode('ascii')).hexdigest()}]",
            ),
            at="experiment",
            expect_verdicts={"compute": "CONFIRMED"},
        ),
        # --- parameterized identities ([IDENT], repo-free) -------------------
        case(
            "g22-ident-affine-progression",
            "genuine",
            "Ehrliche Meldung: parameterisierte Identitaet fuer die Progression "
            "n=3t (1/t + 1/(4t) + 1/(12t) = 4/(3t)) -- exakt als rationale "
            "Funktion in t geprueft, repo-frei: ohne --repo lauffaehig.",
            done(
                payload("[DONE]"),
                "[IDENT: n=3t ; a=t, b=4t, c=12t]",
            ),
            expect_verdicts={"ident": "CONFIRMED"},
        ),
        case(
            "f21-ident-falsified-coefficient",
            "false",
            "Falsch: dieselbe Identitaet mit verfaelschtem Koeffizienten "
            "(b=4t+1 statt 4t) -- die beiden Seiten unterscheiden sich als "
            "rationale Funktionen (Zaehler -9t^2), die Meldung wird REFUTED.",
            done(
                payload("[DONE]"),
                "[IDENT: n=3t ; a=t, b=4t+1, c=12t]",
            ),
            targets=["ident"],
            expect_verdicts={"ident": "REFUTED"},
        ),
        # --- Schur colorings ([COLORING], repo-free) -------------------------
        case(
            "g23-coloring-schur-certificate",
            "genuine",
            "Ehrliche Meldung: Schur-Faerbungs-Zertifikat der Zahlen 1..44 mit "
            "vier Farben (Golomb-Baumert-Zerlegung aus OEIS A045652) -- repo-frei: "
            "alle Tripel x+y=z werden nachgezaehlt, ohne --repo lauffaehig. Das "
            "Urteil traegt die Grenze: nur die untere Schranke S(4) >= 44.",
            done(
                payload("[DONE]"),
                "[COLORING: k=4 ; 12131322444434141213233231214343444422313121]",
            ),
            expect_verdicts={"coloring": "CONFIRMED"},
        ),
        case(
            "f22-coloring-monochromatic-witness",
            "false",
            "Falsch: dieselbe Art Behauptung mit einer manipulierten Farbfolge "
            "-- 1+1=2 liegt komplett in Farbe 1, die Meldung wird REFUTED und "
            "nennt den ersten Verstoss in kanonischer Reihenfolge.",
            done(
                payload("[DONE]"),
                "[COLORING: k=2 ; 1111]",
            ),
            targets=["coloring"],
            expect_verdicts={"coloring": "REFUTED"},
        ),
        # --- file digests ([ARTIFACT], root defaults to the fixture repo) -----
        case(
            "g24-artifact-digest",
            "genuine",
            "Ehrliche Meldung: der SHA-256 von good.txt unter der Wurzel "
            "(Default: das Repo) stimmt -- der Pfad kommt aus der Meldung und "
            "wird auf die Wurzel konfiniert.",
            done(payload("[DONE]"), f"[ARTIFACT: good.txt -> {good_txt_digest}]"),
            expect_verdicts={"artifact": "CONFIRMED"},
        ),
        case(
            "f23-artifact-wrong-digest",
            "false",
            "Falsch: [ARTIFACT] behauptet einen falschen SHA-256 fuer eine "
            "Datei, die existiert; das Urteil nennt beide Werte.",
            done(payload("[DONE]"), f"[ARTIFACT: good.txt -> {'0' * 64}]"),
            targets=["artifact"],
            expect_verdicts={"artifact": "REFUTED"},
        ),
        case(
            "f24-artifact-path-escapes-root",
            "false",
            "Boesartig: der [ARTIFACT]-Pfad zeigt mit '..' aus der Wurzel "
            "heraus; kein Lesevorgang ausserhalb, die Behauptung bleibt "
            "unpruefbar.",
            done(payload("[DONE]"), f"[ARTIFACT: ../outside.txt -> {'a' * 64}]"),
            targets=["artifact"],
            expect_verdicts={"artifact": "UNVERIFIABLE"},
        ),
        # --- merge commits ([MERGE], bound to the report's [COMMIT]) ----------
        case(
            "g25-merge-commit",
            "genuine",
            "Ehrliche Meldung: der gemeldete Commit ist der Merge des Branches "
            "topic; ein Parent ist dessen Tip, der andere liegt auf main.",
            done(payload("[DONE]", f"[COMMIT: {commits['merge']}]", "[MERGE: topic]")),
            expect_verdicts={"commit_exists": "CONFIRMED", "merge": "CONFIRMED"},
        ),
        case(
            "f25-merge-wrong-branch",
            "false",
            "Falsch: [MERGE: main] nennt den Zielbranch statt des gemergten "
            "Branches; main zeigt auf den Merge-Commit selbst, keiner seiner "
            "Parents ist sein Tip -- REFUTED mit den echten Parents.",
            done(payload("[DONE]", f"[COMMIT: {commits['merge']}]", "[MERGE: main]")),
            targets=["merge"],
            expect_verdicts={"merge": "REFUTED"},
        ),
        # --- placeholder markers are not claims --------------------------------
        case(
            "g26-placeholder-lines",
            "genuine",
            "Ehrliche Meldung mit den Vorlagenzeilen eines Briefings: "
            "Platzhalter-Marker (<hash>, <machine>, TODO, abgeschnittene "
            "Digests) ergeben keine Behauptung und keine UNVERIFIABLE-Zeile, "
            "auch nicht in der gemischten Scope-Zeile; expect_claim_count "
            "pinnt, dass nur der echte Commit und das literale [MERGE: no] "
            "zaehlen.",
            done(
                payload(
                    "[DONE]",
                    "[DEPLOY: <status>]",
                    "[COMMIT: <hash>]",
                    "[BRANCH: <name>]",
                    "[MERGE: <branch>]",
                    "<zusammenfassung>",
                ),
                "[HALT: <machine> -> <steps>]",
                "[COMPUTE: <cmd> -> <sha256>]",
                "[ARTIFACT: <pfad> -> <sha256>]",
                "[LEAN: <pfad.lean> -> <satz>]",
                "[COLORING: k=<k> ; <digits>]",
                "[COMMIT: e5b68dd1\u2026]",
                "[COMMIT: TODO]",
                "Tests run: <cmd> -> exit 0",
                # A mixed scope line (a real entry beside a placeholder) is
                # dropped as a whole: the placeholder makes the claim a
                # template, and the real entry alone would be a different,
                # untruthful scope.
                "**Files in scope:** bemyself/model.py, <pfad2>",
                payload("[DONE]", f"[COMMIT: {commits['good']}]", "[MERGE: no]"),
            ),
            expect_verdicts={"commit_exists": "CONFIRMED", "merge": "UNVERIFIABLE"},
            claim_count=2,
        ),
        # --- formal proofs ([LEAN], bound to the report's [COMMIT]) ----------
        case(
            "g27-lean-proven",
            "genuine",
            "Ehrliche Meldung: der Satz fixture_proven ist in lean/Proof.lean "
            "auf dem gepinnten Commit ohne sorry bewiesen. Mit einer echten "
            "Lean-Toolchain im PATH wird das Modul gebaut, das Artefakt "
            "kernel-nachgeprueft und die Axiomliste per eigener Abfrage "
            "gelesen; die Behauptung ist CONFIRMED (Axiomliste im Urteil). "
            "Auf einem Host ohne Lean bleibt "
            "sie ehrlich unpruefbar -- der Fall pinnt deshalb kein Urteil und "
            "nie eine Bestaetigung per Annahme.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['lean']}]"),
                "[LEAN: lean/Proof.lean -> fixture_proven]",
            ),
            at="lean",
        ),
        case(
            "f26-lean-sorry",
            "false",
            "Falsch: lean/Sorry.lean gibt den Beweis nur mit sorry an -- "
            "die Axiomliste des Artefakts nennt sorryAx, die Behauptung ist "
            "REFUTED (auf "
            "einem Host ohne Lean ehrlich unpruefbar). In keinem Fall darf "
            "sie CONFIRMED werden.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['lean']}]"),
                "[LEAN: lean/Sorry.lean -> fixture_sorry_proven]",
            ),
            at="lean",
            targets=["lean"],
            not_confirmed=["lean"],
        ),
        case(
            "f27-lean-toolchain-path-request",
            "false",
            "Boesartig: das Repo committet lean-toolchain='./evil' samt Attrappe "
            "lean/evil/bin/lean -- elan wuerde den Pfad direkt ausfuehren. Der "
            "Pruefer lehnt die Anfrage vor jedem Werkzeuglauf ab (nur "
            "authority/name:version, nur installiert), das Urteil ist UNVERIFIABLE "
            "und nennt den Grund (den Wert selbst zitiert es nicht: die Datei "
            "kann ein Symlink sein) -- nie CONFIRMED, nie REFUTED.",
            done(
                payload("[DONE]", f"[COMMIT: {commits['lean-toolchain-path']}]"),
                "[LEAN: lean/Proof.lean -> fixture_proven]",
            ),
            targets=["lean"],
            expect_verdicts={"lean": "UNVERIFIABLE"},
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
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        # Deeply nested input raises RecursionError, not JSONDecodeError; it
        # must end in the documented exit 2, not a traceback.
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

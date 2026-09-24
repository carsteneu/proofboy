"""Tests for the [LEAN: <path.lean> -> <declaration>] claim type.

A LEAN claim is a formal proof certificate: in the report's pinned commit the
named Lean source file exists and the named declaration is proved there
without sorry/admit. The checker builds the pinned module in a throwaway
checkout, re-checks the compiled artifact with Lean's kernel (leanchecker) and
reads the declaration's axiom list with its own query program -- which loads
the module as data, so no repository code runs in the evidence process.

The hermetic matrix below drives every verdict through fake
lean/lake/leanchecker binaries (no real toolchain needed) and pins the
regression cases of the 5.2/5.4 reviews: forged evidence lines in build
output, `public import`, same-named files elsewhere, `lcProof`/unsafe, and the
`bwrap`-word downgrade. The live tests exercise the real toolchain, including
hostile modules that try to forge their own evidence.
"""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from proofboy import claimtypes, toolmanifest
from proofboy.claimtypes import lean
from proofboy.checks import Ctx, kind_needs_repo, run_claim
from proofboy.cli import EXIT_DEFECT, exit_code
from proofboy.model import Cause, Verdict
from proofboy.report import parse_report
from tests.fixtures import _git, commit_probe, make_repo

_ELAN_BIN = os.path.join(os.path.expanduser("~"), ".elan", "bin")
_LEAN = shutil.which("lean")
if _LEAN is None and os.path.isfile(os.path.join(_ELAN_BIN, "lean")):
    # The test process may not carry the operator's PATH; the live tests
    # patch it in (the checker itself finds the toolchain via PATH).
    _LEAN = os.path.join(_ELAN_BIN, "lean")
_BWRAP = shutil.which("bwrap")

_PROOF = "theorem fixture_proven (n : Nat) : n + 0 = n := rfl\n"
_SORRY = "theorem fixture_sorry (n : Nat) : n + 0 = n := by sorry\n"
_BROKEN = "theorem fixture_broken : True := by\n"

_LAKEFILE = (
    'name = "proofs"\n'
    'version = "0.1.0"\n'
    'defaultTargets = ["Proofs"]\n'
    "\n"
    "[[lean_lib]]\n"
    'name = "Proofs"\n'
)
_LAKE_PROOF = "theorem lake_proven (n : Nat) : n + 0 = n := rfl\n"

_COMMIT_40 = "a" * 40

# A stand-in for a repository-authored toolchain binary -- the shape the P17
# repro planted at ./evil/bin/lean. The hermetic tests only need a file that
# exists; the live decoy writes a marker to prove it (never) ran.
_DECOY_TOOL = "#!/bin/sh\nexit 0\n"

_FAKE_TOOL = """#!/bin/sh
dir='{bin_dir}'
mode=
artifact=
prev=
for a in "$@"; do
  if [ "$prev" = "-o" ]; then artifact="$a"; fi
  prev="$a"
done
case "$1" in
  --version) mode=version ;;
  --print-libdir) mode=libdir ;;
  build) mode=build ;;
  --run) mode=query ;;
  *)
    if [ -n "$artifact" ]; then mode=build; else mode=recheck; fi
    ;;
esac
if [ "$mode" = version ]; then
  if [ -f "$dir/version.out" ]; then cat "$dir/version.out"; else printf '%s\\n' 'Lean (version 4.33.1, fake, Release)'; fi
  exit 0
fi
if [ "$mode" = libdir ]; then
  printf '%s\\n' "$dir"
  exit 0
fi
printf '%s|%s\\n' "$mode" "$*" >> "$dir/calls.log"
case "$mode" in
  build) f=build ;;
  query) f=query ;;
  recheck) f=recheck ;;
  *) f=unknown ;;
esac
if [ "$mode" = build ] && [ -d .lake/build ]; then
  printf 'builddir-present\\n' >> "$dir/calls.log"
fi
if [ "$mode" = query ] && [ -f "$dir/dump.env" ]; then
  printf '%s|%s|%s|%s\\n' "$ELAN_HOME" "$ELAN_TOOLCHAIN" "$LEAN_PATH" "$HOME" >> "$dir/env.copy"
fi
if [ "$mode" = recheck ] && [ -f "$dir/derive.path" ]; then
  # The launcher resolves `lean` by name from PATH; the test asserts where
  # that lookup lands.
  command -v lean > "$dir/derive.path" 2>/dev/null || true
fi
[ -f "$dir/$f.sleep" ] && sleep 30
[ -f "$dir/$f.out" ] && cat "$dir/$f.out"
if [ "$mode" = build ] && [ -f "$dir/build.dirty" ]; then
  printf '\\n-- dirtied by another module\\n' >> "$(cat "$dir/build.dirty")"
fi
if [ "$mode" = build ] && [ -f "$dir/build.plant" ]; then
  # Repository code can plant files while the build runs; line 1 is the
  # target, line 2 the content.
  target=$(head -n 1 "$dir/build.plant")
  content=$(sed -n '2p' "$dir/build.plant")
  printf '%s\\n' "$content" > "$target"
fi
if [ -f "$dir/$f.rc" ] && [ "$(cat "$dir/$f.rc")" != "0" ]; then
  # A failing build compiles nothing; a failing run produces no artifact.
  exit "$(cat "$dir/$f.rc")"
fi
if [ "$mode" = build ] && [ ! -f "$dir/build.skip-artifact" ]; then
  if [ -n "$artifact" ]; then
    mkdir -p "$(dirname "$artifact")"; : >> "$artifact"
  else
    m="$2"; d=$(printf '%s' "$m" | tr '.' '/')
    mkdir -p ".lake/build/lib/lean/$(dirname "$d")" && touch ".lake/build/lib/lean/$d.olean"
  fi
fi
if [ -f "$dir/$f.rc" ]; then exit "$(cat "$dir/$f.rc")"; fi
exit 0
"""


def _write_fake_tools(bin_dir):
    for name in ("lean", "lake", "leanchecker"):
        path = os.path.join(bin_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_FAKE_TOOL.format(bin_dir=bin_dir))
        os.chmod(path, 0o755)


def _answer(name, axioms):
    return f"PROOFBOY-LEAN-AXIOMS {name} [{axioms}]\n"


def _sha256(path):
    with open(path, "rb") as handle:
        return "sha256:" + hashlib.sha256(handle.read()).hexdigest()


def _write_manifest(root, name, entries):
    """A manifest file for {tool: (path, version or None, digest or None)}."""
    lines = []
    for tool, (path, version, digest) in sorted(entries.items()):
        lines.append(f"[tool.{tool}]")
        lines.append(f'path = "{path}"')
        if version is not None:
            lines.append(f'version = "{version}"')
        if digest is not None:
            lines.append(f'digest = "{digest}"')
        lines.append("")
    os.makedirs(root, exist_ok=True)
    manifest = os.path.join(root, name)
    with open(manifest, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return manifest


class LeanParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report("[LEAN: lean/Proof.lean -> fixture_proven]\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "lean")
        self.assertEqual(claim.fields["path"], "lean/Proof.lean")
        self.assertEqual(claim.fields["theorem"], "fixture_proven")
        self.assertIsNone(claim.fields["commit"])

    def test_unicode_arrow_parses(self):
        claims = parse_report("[LEAN: lean/Proof.lean \u2192 fixture_proven]\n")
        self.assertEqual(claims[0].fields["theorem"], "fixture_proven")

    def test_marker_without_arrow_is_no_claim(self):
        self.assertEqual(parse_report("[LEAN: lean/Proof.lean]\n"), [])

    def test_placeholder_marker_is_no_claim(self):
        # The briefing template of a section must not become a claim.
        self.assertEqual(parse_report("[LEAN: <pfad.lean> -> <satz>]\n"), [])

    def test_the_claim_binds_to_the_reports_single_commit(self):
        text = f"[COMMIT: {_COMMIT_40}]\n[LEAN: lean/Proof.lean -> fixture_proven]\n"
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertEqual(claims[0].fields["commit"], _COMMIT_40)

    def test_several_commits_bind_nothing(self):
        text = (
            f"[COMMIT: {_COMMIT_40}]\n"
            f"[COMMIT: {'b' * 40}]\n"
            "[LEAN: lean/Proof.lean -> fixture_proven]\n"
        )
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertIsNone(claims[0].fields["commit"])


class LeanRegistryTest(unittest.TestCase):
    def test_lean_is_registered(self):
        self.assertIn(lean.LEAN, claimtypes.CLAIM_TYPES)
        self.assertEqual(lean.LEAN.kind, "lean")

    def test_the_check_declares_a_repository_need(self):
        self.assertTrue(kind_needs_repo("lean"))

    def test_the_claim_binds_to_the_report_commit(self):
        self.assertTrue(lean.LEAN.binds_commit)

    def test_the_checker_is_the_registered_callable(self):
        self.assertIs(claimtypes.checker_for("lean"), lean.check)


class LeanImportParsingTest(unittest.TestCase):
    """Import lines: every spelling counts, comments do not (review 5.2 #1)."""

    def test_public_import_is_seen(self):
        self.assertEqual(lean._imports_of("public import Mathlib\n"), ["Mathlib"])

    def test_several_modules_on_one_line_are_seen(self):
        self.assertEqual(lean._imports_of("import A B\n"), ["A", "B"])

    def test_a_trailing_comment_does_not_become_a_module(self):
        self.assertEqual(lean._imports_of("import Mathlib -- why\n"), ["Mathlib"])

    def test_imports_inside_the_file_are_found(self):
        source = "import Lean\nimport Mathlib.Algebra\n\ntheorem x : True := trivial\n"
        self.assertEqual(lean._imports_of(source), ["Lean", "Mathlib.Algebra"])


class LeanToolchainTest(unittest.TestCase):
    """The elan fallback pinning (offline toolchain resolution)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def elan_root(self, name, toolchains=()):
        root = os.path.join(self._tmp.name, name)
        os.makedirs(os.path.join(root, "toolchains"), exist_ok=True)
        for toolchain in toolchains:
            os.makedirs(os.path.join(root, "toolchains", toolchain), exist_ok=True)
        return root

    def test_a_sole_toolchain_directory_name_is_mapped_back(self):
        root = self.elan_root("one", ("leanprover--lean4---v4.33.1",))
        self.assertEqual(lean._sole_toolchain(root), "leanprover/lean4:v4.33.1")

    def test_without_exactly_one_toolchain_nothing_is_pinned(self):
        self.assertIsNone(lean._sole_toolchain(self.elan_root("none")))
        two = self.elan_root("two", ("leanprover--lean4---v4.33.1", "leanprover--lean4---v4.34.0"))
        self.assertIsNone(lean._sole_toolchain(two))

    def test_a_project_toolchain_file_is_found_upwards(self):
        root = os.path.join(self._tmp.name, "proj")
        nested = os.path.join(root, "a", "b")
        os.makedirs(nested, exist_ok=True)
        with open(os.path.join(root, "lean-toolchain"), "w", encoding="utf-8") as handle:
            handle.write("leanprover/lean4:v4.33.1\n")
        self.assertEqual(
            lean._project_toolchain_file(nested), os.path.join(root, "lean-toolchain")
        )


class LeanAnswerParsingTest(unittest.TestCase):
    """The query program's protocol is read strictly (review 5.4 #3)."""

    def test_one_answer_is_read(self):
        text = _answer("fixture_proven", "propext")
        self.assertEqual(lean._query_answer(text, "fixture_proven"), ("axioms", ["propext"]))

    def test_an_empty_list_is_read(self):
        text = _answer("fixture_proven", "")
        self.assertEqual(lean._query_answer(text, "fixture_proven"), ("axioms", []))

    def test_two_answers_are_unreadable(self):
        text = _answer("fixture_proven", "") + _answer("fixture_proven", "sorryAx")
        self.assertEqual(lean._query_answer(text, "fixture_proven"), (None, None))

    def test_an_answer_for_another_name_is_ignored(self):
        self.assertEqual(lean._query_answer(_answer("other", ""), "fixture_proven"), (None, None))

    def test_the_unknown_marker_is_read(self):
        text = "PROOFBOY-LEAN-UNKNOWN fixture_proven\n"
        self.assertEqual(lean._query_answer(text, "fixture_proven"), ("unknown", None))

    def test_the_error_marker_is_read(self):
        text = "PROOFBOY-LEAN-ERROR unknown module prefix 'Ghost'\n"
        status, payload = lean._query_answer(text, "fixture_proven")
        self.assertEqual(status, "error")
        self.assertIn("Ghost", payload)


class LeanCheckTest(unittest.TestCase):
    """Hermetic matrix: fake toolchain, unsandboxed, real git fixtures."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def ctx(self, repo, **kw):
        work = os.path.join(self._tmp.name, "work", self._testMethodName)
        os.makedirs(work, exist_ok=True)
        kw.setdefault("tmp_dir", work)
        kw.setdefault("sandbox", "off")
        return Ctx(repo=repo, **kw)

    def probe_repo(self, name, source, filename="lean/Proof.lean"):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit = commit_probe(repo, filename, source)
        return repo, commit

    def lake_repo(self, name, target="proofs/Proofs.lean"):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit = commit_probe(repo, target, _LAKE_PROOF)
        return repo, commit

    def fake(self, **files):
        bin_dir = os.path.join(self._tmp.name, "bin", self._testMethodName)
        os.makedirs(bin_dir, exist_ok=True)
        for name, content in files.items():
            with open(os.path.join(bin_dir, name), "w", encoding="utf-8") as handle:
                handle.write(content)
        _write_fake_tools(bin_dir)
        return bin_dir

    def patched_path(self, bin_dir):
        # The fake dir first, the real PATH behind it (git, cat, python3).
        path = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return mock.patch.dict(os.environ, {"PATH": path})

    def check_report(self, path, theorem, commit, ctx, repo=None):
        return self.check_report_pair(path, theorem, commit, ctx, repo)[1]

    def check_report_pair(self, path, theorem, commit, ctx, repo=None):
        """The claim and its result -- for tests that pin the run's exit code."""
        text = f"[LEAN: {path} -> {theorem}]\n"
        if commit is not None:
            text = f"**send_to payload:** `[COMMIT: {commit}]`\n" + text
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertEqual(len(claims), 1)
        return claims[0], run_claim(claims[0], ctx)

    # --- the verdicts ------------------------------------------------------
    def test_an_empty_axiom_list_confirms(self):
        repo, commit = self.probe_repo("confirm", _PROOF)
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("does not depend on any axioms", result.reason)
        self.assertIn("passed Lean's kernel re-check", result.reason)
        self.assertIn("no repository code in the query process", result.reason)
        self.assertIn("not sandboxed: --sandbox=off", result.reason)
        self.assertIn("git checkout", result.command)
        self.assertIs(result.sandboxed, False)

    def test_foundation_axioms_are_named_in_full(self):
        repo, commit = self.probe_repo("axioms", _PROOF)
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", "propext, Quot.sound")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("depends on axioms: [propext, Quot.sound]", result.reason)

    def test_sorry_axiom_refutes_with_the_exact_wording(self):
        repo, commit = self.probe_repo("sorry", _SORRY)
        bin_dir = self.fake(**{"query.out": _answer("fixture_sorry", "sorryAx")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("depends on axioms: [sorryAx]", result.reason)

    def test_sorry_with_more_axioms_refutes_and_names_all(self):
        repo, commit = self.probe_repo("sorry-mix", _SORRY)
        bin_dir = self.fake(**{"query.out": _answer("fixture_sorry", "sorryAx, propext")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("[sorryAx, propext]", result.reason)

    def test_lc_proof_refutes_because_the_kernel_did_not_check(self):
        repo, commit = self.probe_repo("unsafe", "unsafe def fixture_cheat : False := unsafeCast ()\n")
        bin_dir = self.fake(**{"query.out": _answer("fixture_cheat", "lcProof")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_cheat", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("not kernel-checked", result.reason)
        self.assertIn("lcProof", result.reason)

    def test_an_unknown_declaration_refutes(self):
        repo, commit = self.probe_repo("unknown", _PROOF)
        bin_dir = self.fake(**{"query.out": "PROOFBOY-LEAN-UNKNOWN no_such\n", "query.rc": "1\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "no_such", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("declaration not found", result.reason)

    def test_a_build_error_naming_the_file_refutes(self):
        repo, commit = self.probe_repo("broken", _BROKEN)
        bin_dir = self.fake(
            **{
                "build.out": "lean/Proof.lean:1:0: error: unsolved goals\n"
                "lean/Proof.lean:2:0: error: second failure\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_broken", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("does not compile", result.reason)
        self.assertIn("error: unsolved goals", result.reason)
        self.assertNotIn("second failure", result.reason)

    # --- the regression cases of the reviews -------------------------------
    def test_build_output_claiming_evidence_never_confirms(self):
        # The forged line belongs to the build log; the verdict must come from
        # the query answer alone (review 5.4 #1).
        repo, commit = self.probe_repo("forged", _SORRY)
        bin_dir = self.fake(
            **{
                "build.out": "'fixture_sorry' does not depend on any axioms\n",
                "query.out": _answer("fixture_sorry", "sorryAx"),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertNotIn("does not depend on any axioms", result.reason)
        self.assertIn("depends on axioms: [sorryAx]", result.reason)

    def test_the_word_bwrap_in_build_output_does_not_downgrade(self):
        # A checked file may print anything; only bwrap's own lines ("bwrap: ")
        # classify a sandbox failure (review 5.2 #2).
        repo, commit = self.probe_repo("bwrap-word", _BROKEN)
        bin_dir = self.fake(
            **{
                "build.out": "lean/Proof.lean:1:0: error: #eval IO.println \"bwrap\" failed\n"
                "note: the word bwrap appears in repository output\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_broken", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("does not compile", result.reason)

    def test_a_real_bwrap_failure_is_unverifiable(self):
        repo, commit = self.probe_repo("bwrap-fail", _BROKEN)
        bin_dir = self.fake(
            **{
                "build.out": "bwrap: Creating new namespace failed: Operation not permitted\n",
                "build.rc": "1\n",
            }
        )
        broken = os.path.join(bin_dir, "broken-bwrap")
        with open(broken, "w", encoding="utf-8") as handle:
            handle.write(
                "#!/bin/sh\n"
                "echo 'bwrap: Creating new namespace failed: Operation not permitted' >&2\n"
                "exit 1\n"
            )
        os.chmod(broken, 0o755)
        with self.patched_path(bin_dir), mock.patch(
            "proofboy.checks.find_bwrap", return_value=broken
        ):
            result = self.check_report(
                "lean/Proof.lean", "fixture_broken", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("sandbox could not run", result.reason)

    def test_a_same_named_file_elsewhere_does_not_refute(self):
        # `other/Proofs.lean` is not `proofs/Proofs.lean` (review 5.2 #3).
        repo, commit = self.lake_repo("same-name")
        bin_dir = self.fake(
            **{
                "build.out": "other/Proofs.lean:1:0: error: dependency is broken\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("outside", result.reason)

    def test_a_public_import_of_a_missing_module_is_unverifiable(self):
        # `public import Mathlib` is an import (review 5.2 #1).
        repo, commit = self.probe_repo("public-import", "public import Mathlib\n\n" + _PROOF)
        bin_dir = self.fake(
            **{
                "build.out": "error: unknown module prefix 'Mathlib'\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("Mathlib", result.reason)

    def test_a_forged_module_error_downgrades_at_most(self):
        # The file's own compile is repository code: a forged
        # `unknown module prefix` line turns its refutation into UNVERIFIABLE
        # (the documented downgrade class) but never into CONFIRMED.
        repo, commit = self.probe_repo("dep-lies", _BROKEN)
        bin_dir = self.fake(
            **{
                "build.out": "lean/Proof.lean:1:0: error: unknown module prefix 'Mathlib'\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_broken", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("not available", result.reason)

    # --- the stages --------------------------------------------------------
    def test_the_kernel_recheck_runs_before_the_query_and_guards_it(self):
        repo, commit = self.probe_repo("recheck", _PROOF)
        bin_dir = self.fake(
            **{
                "recheck.out": "error: (kernel) declaration has met a fatal error\n",
                "recheck.rc": "1\n",
                "query.out": _answer("fixture_proven", ""),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("did not pass Lean's kernel re-check", result.reason)
        with open(os.path.join(bin_dir, "calls.log"), encoding="utf-8") as handle:
            calls = handle.read()
        self.assertIn("recheck|", calls)
        self.assertNotIn("query|", calls)

    def test_a_lake_project_builds_rechecks_and_queries(self):
        repo, commit = self.lake_repo("lake")
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "calls.log"), encoding="utf-8") as handle:
            calls = handle.read()
        self.assertIn("build|build Proofs", calls)
        self.assertIn("recheck|Proofs", calls)
        self.assertIn("query|--run ", calls)
        self.assertIn("Proofs lake_proven", calls)

    def test_the_lakefile_and_lake_stay_out_of_the_evidence_stages(self):
        # `lake` evaluates the repository's lakefile; the re-check and the
        # query run the toolchain directly (reviews 5.2/5.4 round 2, F1/N1).
        repo, commit = self.lake_repo("lake-noenv")
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "calls.log"), encoding="utf-8") as handle:
            calls = handle.read()
        self.assertNotIn("env", calls)

    def test_the_toolchain_library_dir_comes_first_in_the_search_path(self):
        # A repository-planted `Lean.olean` must not shadow the query
        # program's own imports (review 5.4 round 2, N2).
        repo, commit = self.probe_repo("search-path", _PROOF)
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", ""), "dump.env": "1\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "env.copy"), encoding="utf-8") as handle:
            line = handle.read().splitlines()[-1]
        lean_path = line.split("|")[2]
        self.assertEqual(lean_path.split(os.pathsep)[0], bin_dir)

    def test_a_build_without_an_artifact_is_unverifiable(self):
        # A build that ends early leaves nothing to re-check (review 5.2
        # round 2, F2).
        repo, commit = self.probe_repo("no-artifact", _PROOF)
        bin_dir = self.fake(
            **{"query.out": _answer("fixture_proven", ""), "build.skip-artifact": "1\n"}
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no freshly compiled artifact", result.reason)

    def test_an_answer_without_exit_zero_is_not_trusted(self):
        repo, commit = self.probe_repo("rc-answer", _PROOF)
        bin_dir = self.fake(
            **{"query.out": _answer("fixture_proven", ""), "query.rc": "1\n"}
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("exited with status", result.reason)

    def test_a_declared_axiom_refutes(self):
        # `axiom foo : False` proves nothing (review 5.2 round 2, F3).
        repo, commit = self.probe_repo("axiom-decl", "axiom fixture_axiom : False\n")
        bin_dir = self.fake(**{"query.out": _answer("fixture_axiom", "fixture_axiom")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_axiom", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("is an axiom, not a proof", result.reason)

    def test_a_file_executing_code_at_elaboration_time_is_unverifiable(self):
        # The build is only controllable when the file does not run code
        # (documented policy; review 5.2 round 2, F2).
        repo, commit = self.probe_repo(
            "eval-file", '#eval IO.println "hi"\n\n' + _PROOF
        )
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("#eval", result.reason)
        self.assertFalse(os.path.exists(os.path.join(bin_dir, "calls.log")))

    def test_a_lakefile_executing_code_makes_the_claim_unverifiable(self):
        repo = make_repo(os.path.join(self._tmp.name, "lakefile-exec"))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit_probe(repo, "proofs/lakefile.lean", '#eval IO.println "hi"\n')
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("lakefile", result.reason)

    def test_a_symlinked_build_directory_is_discarded(self):
        # rmtree does not follow a symlink; the deletion must (review 5.4
        # round 2, N3).
        repo = make_repo(os.path.join(self._tmp.name, "lake-symlink"))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit_probe(repo, "proofs/decoy/keep.txt", "decoy\n")
        os.makedirs(os.path.join(repo.path, "proofs", ".lake"), exist_ok=True)
        os.symlink(
            os.path.join(repo.path, "proofs", "decoy"),
            os.path.join(repo.path, "proofs", ".lake", "build"),
        )
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "calls.log"), encoding="utf-8") as handle:
            calls = handle.read()
        self.assertNotIn("builddir-present", calls)

    def test_a_committed_build_artifact_is_discarded_before_the_build(self):
        repo = make_repo(os.path.join(self._tmp.name, "lake-stale"))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit_probe(repo, "proofs/.lake/build/lib/lean/Proofs.olean", "stale artifact\n")
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "calls.log"), encoding="utf-8") as handle:
            calls = handle.read()
        self.assertNotIn("builddir-present", calls)

    def test_a_standalone_file_builds_with_o_and_queries_with_run(self):
        repo, commit = self.probe_repo("standalone", _PROOF, filename="Proof.lean")
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "calls.log"), encoding="utf-8") as handle:
            calls = handle.read()
        self.assertIn("-R ", calls)
        self.assertIn("-o ", calls)
        self.assertIn("query|--run ", calls)

    def test_a_declaration_from_another_module_refutes(self):
        # The claim says "proved in <file>"; a declaration that only lives in
        # an imported module is not (review 5.2 round 3, N3).
        repo, commit = self.probe_repo("foreign", _PROOF)
        bin_dir = self.fake(
            **{
                "query.out": "PROOFBOY-LEAN-FOREIGN fixture_proven Helper\n",
                "query.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("not defined in", result.reason)
        self.assertIn("Helper", result.reason)

    def test_a_file_changed_by_the_project_build_is_unverifiable(self):
        # Another module's elaboration-time code can rewrite the checked file
        # (review 5.4 round 3, F2): the artifact must describe the pinned
        # source, so a modified file refuses.
        repo, commit = self.lake_repo("dirty-file")
        bin_dir = self.fake(
            **{"query.out": _answer("lake_proven", ""), "build.dirty": "Proofs.lean\n"}
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("changed during", result.reason)

    def test_a_lake_error_prefix_does_not_hide_the_attribution(self):
        # Lake prefixes Lean's error lines with `error: ` (review 5.2 round 3,
        # N1).
        repo, commit = self.lake_repo("lake-prefix")
        bin_dir = self.fake(
            **{
                "build.out": "error: proofs/Proofs.lean:1:0: error: unsolved goals\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("does not compile", result.reason)

    def test_a_build_directory_pointing_outside_the_checkout_is_refused(self):
        # `.lake` as a committed symlink must not let the checker delete host
        # files (review 5.2 round 3, N2).
        repo = make_repo(os.path.join(self._tmp.name, "lake-outside"))
        outside = os.path.join(self._tmp.name, "lake-outside-outside")
        os.makedirs(os.path.join(outside, "build"), exist_ok=True)
        canary = os.path.join(outside, "build", "canary.txt")
        with open(canary, "w", encoding="utf-8") as handle:
            handle.write("keep me\n")
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        os.symlink(outside, os.path.join(repo.path, "proofs", ".lake"))
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("outside the checkout", result.reason)
        self.assertTrue(os.path.exists(canary), "the checker deleted a host file")

    # --- the guards --------------------------------------------------------
    def test_without_lean_the_claim_is_unverifiable(self):
        repo, commit = self.probe_repo("nolean", _PROOF)
        bin_dir = self.fake()
        os.remove(os.path.join(bin_dir, "lean"))
        path = bin_dir + os.pathsep + os.pathsep.join(["/usr/bin", "/bin"])
        with mock.patch.dict(os.environ, {"PATH": path}):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("lean is not available in PATH", result.reason)

    def test_without_leanchecker_the_claim_is_unverifiable(self):
        repo, commit = self.probe_repo("nochecker", _PROOF)
        bin_dir = self.fake()
        os.remove(os.path.join(bin_dir, "leanchecker"))
        path = bin_dir + os.pathsep + os.pathsep.join(["/usr/bin", "/bin"])
        with mock.patch.dict(os.environ, {"PATH": path}):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("leanchecker is not available in PATH", result.reason)

    def test_auto_without_bwrap_is_unverifiable_and_runs_nothing(self):
        repo, commit = self.probe_repo("nosandbox", _PROOF)
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", "")})
        with self.patched_path(bin_dir), mock.patch(
            "proofboy.checks.find_bwrap", return_value=None
        ):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.ENVIRONMENT, result.reason)
        self.assertIn("bwrap", result.reason)
        self.assertFalse(os.path.exists(os.path.join(bin_dir, "calls.log")))

    def test_a_missing_file_in_the_pinned_commit_refutes(self):
        repo, commit = self.probe_repo("missing", _PROOF)
        bin_dir = self.fake()
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Ghost.lean", "fixture_proven", repo["base"], self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("does not exist in commit", result.reason)

    def test_without_a_commit_the_claim_is_unverifiable(self):
        repo, commit = self.probe_repo("nocommit", _PROOF)
        bin_dir = self.fake()
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", None, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no commit hash", result.reason)

    def test_a_path_leaving_the_checkout_is_unverifiable(self):
        repo, commit = self.probe_repo("badpath", _PROOF)
        bin_dir = self.fake()
        with self.patched_path(bin_dir):
            result = self.check_report(
                "../outside.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("not a valid Lean source path", result.reason)

    def test_a_non_identifier_declaration_is_unverifiable(self):
        repo, commit = self.probe_repo("badname", _PROOF)
        bin_dir = self.fake()
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "foo; #eval 1", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("not a valid declaration name", result.reason)

    def test_a_timeout_is_unverifiable(self):
        repo, commit = self.probe_repo("timeout", _PROOF)
        bin_dir = self.fake(**{"query.out": _answer("fixture_proven", ""), "query.sleep": "1\n"})
        with self.patched_path(bin_dir), mock.patch.object(lean, "LEAN_TIMEOUT", 1):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("timed out", result.reason)

    def test_an_unreadable_answer_is_unverifiable(self):
        repo, commit = self.probe_repo("noline", _PROOF)
        bin_dir = self.fake(**{"query.out": "some unrelated output\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no readable answer", result.reason)

    def test_an_error_answer_is_unverifiable(self):
        repo, commit = self.probe_repo("qerror", _PROOF)
        bin_dir = self.fake(
            **{
                "query.out": "PROOFBOY-LEAN-ERROR cannot load olean for Proof\n",
                "query.rc": "2\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("could not read the compiled artifact", result.reason)

    def test_a_sole_installed_toolchain_is_pinned_for_offline_runs(self):
        repo, commit = self.probe_repo("elan-pin", _PROOF)
        elan = os.path.join(self._tmp.name, "fake-elan", self._testMethodName)
        bin_dir = os.path.join(elan, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        os.makedirs(
            os.path.join(elan, "toolchains", "leanprover--lean4---v4.33.1"), exist_ok=True
        )
        _write_fake_tools(bin_dir)
        with open(os.path.join(bin_dir, "query.out"), "w", encoding="utf-8") as handle:
            handle.write(_answer("fixture_proven", ""))
        with open(os.path.join(bin_dir, "dump.env"), "w", encoding="utf-8") as handle:
            handle.write("dump\n")
        with self.patched_path(bin_dir):
            os.environ.pop("ELAN_TOOLCHAIN", None)
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "env.copy"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertTrue(lines)
        elan_home, toolchain, _, home = lines[-1].split("|")
        self.assertEqual(elan_home, elan)
        self.assertEqual(toolchain, "leanprover/lean4:v4.33.1")
        self.assertNotEqual(home, os.path.expanduser("~"))

    # --- the toolchain trust boundary (P17) --------------------------------
    def elan_with_fake_tools(self, toolchains=()):
        """A fake elan root: bin/ with the fake tools, toolchains/ with dirs."""
        root = os.path.join(self._tmp.name, "fake-elan", self._testMethodName)
        bin_dir = os.path.join(root, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        for toolchain in toolchains:
            os.makedirs(os.path.join(root, "toolchains", toolchain), exist_ok=True)
        _write_fake_tools(bin_dir)
        return bin_dir

    def toolchain_repo(self, name, toolchain, decoy=False):
        """A standalone proof whose project commits a ``lean-toolchain`` file."""
        repo = make_repo(os.path.join(self._tmp.name, name))
        if decoy:
            commit_probe(repo, "evil/bin/lean", _DECOY_TOOL)
        commit_probe(repo, "lean/Proof.lean", _PROOF)
        commit = commit_probe(repo, "lean/lean-toolchain", toolchain + "\n")
        return repo, commit

    def answering(self, bin_dir, theorem="fixture_proven", axioms=""):
        with open(os.path.join(bin_dir, "query.out"), "w", encoding="utf-8") as handle:
            handle.write(_answer(theorem, axioms))
        return bin_dir

    def test_a_path_like_toolchain_request_is_refused(self):
        # P17 (a), P18b: the repository asks for a toolchain, it does not
        # choose one. A path-like value violates the form a toolchain request
        # must have, and that violation lies in the checked thing itself --
        # so the claim cannot bind: a defect, exit 5, with and without
        # --strict. It must never reach the toolchain environment.
        repo, commit = self.toolchain_repo("tc-path", "./evil", decoy=True)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        with self.patched_path(bin_dir):
            claim, result = self.check_report_pair(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertEqual(exit_code([(claim, result)], strict=True), EXIT_DEFECT)
        # The value itself is never quoted into the verdict: the committed
        # file may be a symlink to any host file the checker can read.
        self.assertNotIn("./evil", result.reason)
        self.assertIn("does not hold a toolchain name", result.reason)
        self.assertIn("is not quoted", result.reason)

    def test_a_path_like_request_is_still_a_defect_without_bwrap(self):
        # Review finding 5.2/5.3: the form question is answered before the
        # sandbox gate -- a host without bwrap cannot turn the defect into a
        # boundary, and the gate still keeps every tool from starting.
        repo, commit = self.toolchain_repo("tc-path-nobwrap", "./evil", decoy=True)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        with self.patched_path(bin_dir), mock.patch(
            "proofboy.checks.find_bwrap", return_value=None
        ):
            claim, result = self.check_report_pair(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertEqual(exit_code([(claim, result)], strict=True), EXIT_DEFECT)
        self.assertIn("does not hold a toolchain name", result.reason)
        self.assertFalse(os.path.exists(os.path.join(bin_dir, "calls.log")))

    def test_a_toolchain_request_that_is_not_installed_is_refused(self):
        # P17 (a): only a request that resolves to an installed toolchain is
        # followed; the checker does not substitute a different toolchain.
        repo, commit = self.toolchain_repo("tc-missing", "leanprover/lean4:v9.99.9")
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        # The boundary: a well-formed request that is merely absent stays the
        # environment's -- only the wrong form is a defect.
        self.assertIs(result.cause, Cause.ENVIRONMENT, result.reason)
        self.assertIn("leanprover/lean4:v9.99.9", result.reason)
        self.assertIn("not installed", result.reason)

    def test_an_installed_toolchain_request_is_followed(self):
        # The positive control: an installed authority/name:version request
        # still reaches the shim as ELAN_TOOLCHAIN (offline determinism).
        repo, commit = self.toolchain_repo("tc-installed", "leanprover/lean4:v4.33.1")
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        with open(os.path.join(bin_dir, "dump.env"), "w", encoding="utf-8") as handle:
            handle.write("dump\n")
        with self.patched_path(bin_dir):
            os.environ.pop("ELAN_TOOLCHAIN", None)
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "env.copy"), encoding="utf-8") as handle:
            toolchain = handle.read().splitlines()[-1].split("|")[1]
        self.assertEqual(toolchain, "leanprover/lean4:v4.33.1")

    def test_a_toolchain_resolution_failure_at_the_compile_stage_is_unverifiable(self):
        # P17 (b): a broken environment is no error of the claim -- the exact
        # elan line from the repro must not be reported as a compile error.
        # The request is well-formed and installed, so only the run-time
        # failure is under test here. For a standalone file the fake tool's
        # build mode IS the compile run.
        repo, commit = self.toolchain_repo("tc-compile", "leanprover/lean4:v4.33.1")
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        elan_line = (
            "error: no Lean toolchain found at '././evil': "
            "expected '././evil/bin/lean' to exist\n"
        )
        with open(os.path.join(bin_dir, "build.out"), "w", encoding="utf-8") as handle:
            handle.write(elan_line)
        with open(os.path.join(bin_dir, "build.rc"), "w", encoding="utf-8") as handle:
            handle.write("1\n")
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no Lean toolchain found", result.reason)
        self.assertNotIn("does not compile", result.reason)

    def test_a_path_like_request_is_refused_without_an_elan_root_too(self):
        # The refusal does not depend on elan being in play: a path-like
        # request is never honored, on any host -- and it is a form violation
        # in the checked thing, so the class is defect, not environment.
        repo, commit = self.toolchain_repo("tc-path-plain", "./evil", decoy=True)
        bin_dir = self.answering(self.fake())
        with self.patched_path(bin_dir):
            claim, result = self.check_report_pair(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        # The value itself is never quoted into the verdict: the committed
        # file may be a symlink to any host file the checker can read.
        self.assertNotIn("./evil", result.reason)
        self.assertIn("does not hold a toolchain name", result.reason)
        self.assertIn("is not quoted", result.reason)

    def test_a_toolchain_file_above_the_checkout_is_not_a_defect(self):
        # Review finding 5.3: the lookup follows elan's upward search, so an
        # *untracked* lean-toolchain in the tree the throwaway checkout lives
        # in is found too. It is not part of the pinned commit -- the checked
        # thing violates no form -- so the refusal stays the environment's,
        # even though elan would find that value at run time (fail closed).
        repo, commit = self.probe_repo("tc-above", _PROOF)
        with open(os.path.join(repo.path, "lean-toolchain"), "w", encoding="utf-8") as handle:
            handle.write("./evil\n")
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        ctx = self.ctx(repo.path, tmp_dir=os.path.join(repo.path, ".yesmem", "tmp", "check"))
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, ctx
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.ENVIRONMENT, result.reason)
        self.assertIn("above the checkout", result.reason)
        self.assertNotIn("./evil", result.reason)

    def test_a_committed_file_above_the_checkout_is_still_a_defect(self):
        # Re-review finding (NEW-F3): the throwaway checkout lives under the
        # tested repository (--tmp), so the repository can commit the very
        # directory the checkout is made in. That file IS part of the pinned
        # commit -- a defect, not a host boundary.
        repo, commit = self.probe_repo("tc-committed-above", _PROOF)
        commit = commit_probe(repo, ".yesmem/tmp/check/lean-toolchain", "./evil\n")
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        ctx = self.ctx(repo.path, tmp_dir=os.path.join(repo.path, ".yesmem", "tmp", "check"))
        with self.patched_path(bin_dir):
            claim, result = self.check_report_pair(
                "lean/Proof.lean", "fixture_proven", commit, ctx
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertIn("does not hold a toolchain name", result.reason)
        self.assertNotIn("./evil", result.reason)

    def test_a_toolchain_resolution_failure_at_the_build_stage_is_unverifiable(self):
        # P17 (b) at stage 1: the lake build fails because the toolchain
        # cannot be resolved; the verdict names that reason.
        repo, commit = self.lake_repo("tc-build")
        elan_line = "error: no such release: 'v9.99.9'\n"
        bin_dir = self.fake(
            **{
                "build.out": elan_line,
                "build.rc": "1\n",
                "query.out": _answer("lake_proven", ""),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no such release", result.reason)
        self.assertIn("toolchain", result.reason.lower())

    def test_a_confirmation_names_the_tool_identity(self):
        # P17 (c): every verdict names the tools that judged -- name, version
        # and the digest short form of the file that ran.
        repo, commit = self.probe_repo("identity", _PROOF)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        with open(os.path.join(bin_dir, "leanchecker"), "a", encoding="utf-8") as handle:
            handle.write("# a different leanchecker build\n")
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "lean"), "rb") as handle:
            lean_digest = hashlib.sha256(handle.read()).hexdigest()[:12]
        with open(os.path.join(bin_dir, "leanchecker"), "rb") as handle:
            checker_digest = hashlib.sha256(handle.read()).hexdigest()[:12]
        self.assertIn(f"lean 4.33.1 sha256:{lean_digest}", result.reason)
        self.assertIn(f"leanchecker 4.33.1 sha256:{checker_digest}", result.reason)
        self.assertIn("(toolchain leanprover/lean4:v4.33.1)", result.reason)

    def test_a_refutation_names_the_tool_identity_too(self):
        repo, commit = self.probe_repo("identity-refuted", _SORRY)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",)),
            "fixture_sorry",
            "sorryAx",
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("lean 4.33.1 sha256:", result.reason)
        self.assertIn("leanchecker 4.33.1 sha256:", result.reason)

    # --- the --tools manifest (P17 c/d) ------------------------------------
    def write_manifest(self, entries, name="tools.toml"):
        """A manifest: {tool: (path, version or None, digest or None)}."""
        manifest = _write_manifest(
            os.path.join(self._tmp.name, "manifests", self._testMethodName), name, entries
        )
        return toolmanifest.load(manifest)

    def sha(self, path):
        return _sha256(path)

    def test_a_manifest_pin_beats_the_repositorys_toolchain_request(self):
        # P17 (c): the manifest is host authority. The repository requests a
        # toolchain that is not installed; the manifest settles the toolchain,
        # so the request is not even consulted and the claim is judged.
        repo, commit = self.toolchain_repo(
            "manifest-wins", "leanprover/lean4:v9.99.9", decoy=True
        )
        bin_dir = self.answering(self.fake())
        tools = self.write_manifest(
            {
                "lean": (os.path.join(bin_dir, "lean"), None, None),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("[pinned]", result.reason)
        self.assertNotIn("not installed", result.reason)

    def test_a_path_like_request_is_refused_even_with_a_manifest_pin(self):
        # A path-like value is never a legitimate toolchain request, so it is
        # refused before the manifest is consulted at all.
        repo, commit = self.toolchain_repo("manifest-path", "./evil", decoy=True)
        bin_dir = self.answering(self.fake())
        tools = self.write_manifest(
            {
                "lean": (os.path.join(bin_dir, "lean"), None, None),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            claim, result = self.check_report_pair(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertIn("does not hold a toolchain name", result.reason)

    def test_elan_is_recognized_through_a_shim_beside_a_concrete_lean(self):
        # Fix for the review finding: with lean pinned to a concrete binary
        # and leanchecker left on an elan shim, the toolchain root must still
        # be handed over -- otherwise the shim resolves its toolchain through
        # HOME=<checkout>, which the repository owns.
        repo, commit = self.probe_repo("shim-beside-pin", _PROOF)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        concrete = os.path.join(self._tmp.name, "concrete-bin", self._testMethodName)
        os.makedirs(concrete, exist_ok=True)
        shutil.copyfile(os.path.join(bin_dir, "lean"), os.path.join(concrete, "lean"))
        os.chmod(os.path.join(concrete, "lean"), 0o755)
        with open(os.path.join(bin_dir, "dump.env"), "w", encoding="utf-8") as handle:
            handle.write("dump\n")
        tools = self.write_manifest(
            {
                "lean": (os.path.join(concrete, "lean"), None, None),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            os.environ.pop("ELAN_HOME", None)
            os.environ.pop("ELAN_TOOLCHAIN", None)
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "env.copy"), encoding="utf-8") as handle:
            elan_home, toolchain = handle.read().splitlines()[-1].split("|")[:2]
        self.assertEqual(elan_home, os.path.dirname(bin_dir))
        self.assertEqual(toolchain, "leanprover/lean4:v4.33.1")

    def test_a_version_pin_without_a_readable_version_is_unverifiable(self):
        # A pinned version must be confirmed by the running tool; a tool that
        # reports nothing parseable cannot confirm anything.
        repo, commit = self.probe_repo("version-unreadable", _PROOF)
        bin_dir = self.answering(
            self.fake(**{"version.out": "Lean (development build)\n"})
        )
        tools = self.write_manifest(
            {
                "lean": (
                    os.path.join(bin_dir, "lean"),
                    "4.33.1",
                    self.sha(os.path.join(bin_dir, "lean")),
                ),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no parseable version", result.reason)

    def test_a_leanchecker_version_pin_is_confirmed_by_the_toolchain(self):
        # leanchecker has no version probe; a pinned version counts when it
        # matches the toolchain beside lean, and the verdict names it.
        repo, commit = self.probe_repo("checker-version-pin", _PROOF)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        tools = self.write_manifest(
            {
                "lean": (os.path.join(bin_dir, "lean"), None, None),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), "4.33.1", None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("leanchecker 4.33.1 sha256:", result.reason)
        self.assertIn("[pinned]", result.reason)

    def test_a_concrete_manifest_pair_confirms_the_checker_version(self):
        # Review finding: the derivation must not depend on a recognizable
        # elan root -- two concrete binaries from one directory are the same
        # toolchain, and a version pin on the checker must be confirmable.
        repo, commit = self.probe_repo("concrete-pair", _PROOF)
        # The copies keep reading their control files from the directory the
        # fake tools were created in, so the answers live there.
        bin_dir = self.answering(self.fake())
        concrete = os.path.join(self._tmp.name, "pair-bin", self._testMethodName)
        os.makedirs(concrete, exist_ok=True)
        for name in ("lean", "leanchecker"):
            shutil.copyfile(os.path.join(bin_dir, name), os.path.join(concrete, name))
            os.chmod(os.path.join(concrete, name), 0o755)
        tools = self.write_manifest(
            {
                "lean": (os.path.join(concrete, "lean"), "4.33.1", None),
                "leanchecker": (os.path.join(concrete, "leanchecker"), "4.33.1", None),
            }
        )
        with self.patched_path(concrete):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("lean 4.33.1 sha256:", result.reason)
        self.assertIn("leanchecker 4.33.1 sha256:", result.reason)

    def test_an_unrecognized_shim_gets_a_neutral_elan_root(self):
        # Review finding: a copied or wrapped elan binary cannot be told from
        # a plain one, and runs use HOME=<checkout> -- which repository code
        # could plant with an elan home while the build runs. The neutral root
        # is therefore handed over regardless of what the checkout contains.
        repo = make_repo(os.path.join(self._tmp.name, "neutral-root"))
        commit = commit_probe(repo, "lean/Proof.lean", _PROOF)
        bin_dir = self.answering(self.fake())
        with open(os.path.join(bin_dir, "dump.env"), "w", encoding="utf-8") as handle:
            handle.write("dump\n")
        with self.patched_path(bin_dir):
            os.environ.pop("ELAN_HOME", None)
            os.environ.pop("ELAN_TOOLCHAIN", None)
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "env.copy"), encoding="utf-8") as handle:
            elan_home, toolchain, _lean_path, home = handle.read().splitlines()[-1].split("|")
        self.assertIn("elan-home", elan_home)
        # The neutral root is checker-owned: it lives next to the run's tools,
        # never inside a tree the repository controls -- and never derived from
        # the run's HOME (the throwaway checkout, which repository code could
        # plant while the build runs). A substring check on "checkout" asked
        # the wrong question: it failed whenever the neutral root's own path
        # contained that word (the verifier's sandbox uses HOME=<tmp>/checkout-XXXX).
        self.assertTrue(
            os.path.basename(os.path.dirname(elan_home)).startswith("lean-tool-bin-"),
            elan_home,
        )
        self.assertFalse(elan_home.startswith(os.path.realpath(repo.path) + os.sep), elan_home)
        self.assertFalse(
            os.path.abspath(elan_home).startswith(os.path.abspath(home) + os.sep),
            f"the neutral elan root {elan_home} lies under the run's HOME {home}",
        )
        self.assertEqual(toolchain, "")

    def test_a_request_with_an_unrecognized_shim_is_refused(self):
        # The neutral root cannot vouch for a requested toolchain, so such a
        # run is refused instead of guessed.
        repo = make_repo(os.path.join(self._tmp.name, "neutral-request"))
        commit_probe(repo, "lean/Proof.lean", _PROOF)
        commit = commit_probe(
            repo, "lean/lean-toolchain", "leanprover/lean4:v4.33.1\n"
        )
        bin_dir = self.answering(self.fake())
        with self.patched_path(bin_dir):
            os.environ.pop("ELAN_HOME", None)
            os.environ.pop("ELAN_TOOLCHAIN", None)
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.ENVIRONMENT, result.reason)
        self.assertIn("cannot be confirmed against the host", result.reason)
        self.assertIn("leanprover/lean4:v4.33.1", result.reason)

    def test_a_toolchain_file_planted_during_the_build_is_refused(self):
        # Review finding (security round 2): repository code runs in the
        # build; a `lean-toolchain` planted then would be read by an elan
        # shim, and elan executes a path-like value directly -- without
        # consulting ELAN_HOME. The file is looked up again before any
        # further stage.
        repo = make_repo(os.path.join(self._tmp.name, "late-toolchain"))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        bin_dir = self.fake(
            **{
                "query.out": _answer("lake_proven", ""),
                "build.plant": "../lean-toolchain\n./evil\n",
            }
        )
        with self.patched_path(bin_dir):
            claim, result = self.check_report_pair(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        # P18b: the planted value is path-like -- a form violation in the
        # checked thing, whatever stage sees it first. Defect, exit 5.
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertIn("lean-toolchain file", result.reason)
        self.assertNotIn("./evil", result.reason)

    def test_a_path_like_file_planted_during_the_build_is_a_defect_with_elan_too(self):
        # Review finding 5.2: the late re-check is a single code path now --
        # a tree with a host-side elan root takes the same defect route.
        repo = make_repo(os.path.join(self._tmp.name, "late-toolchain-elan"))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        bin_dir = self.answering(
            self.elan_with_fake_tools(("leanprover--lean4---v4.33.1",))
        )
        with open(os.path.join(bin_dir, "build.plant"), "w", encoding="utf-8") as handle:
            handle.write("../lean-toolchain\n./evil\n")
        with self.patched_path(bin_dir):
            claim, result = self.check_report_pair(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertIn("lean-toolchain file", result.reason)
        self.assertNotIn("./evil", result.reason)

    def test_the_launchers_resolve_lean_through_the_checker_owned_path(self):
        # The launchers call `lean` by name; that lookup must land on the
        # identified tool, not on whatever PATH offers.
        repo, commit = self.probe_repo("derive-path", _PROOF)
        bin_dir = self.answering(self.fake())
        probe = os.path.join(bin_dir, "derive.path")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("")
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(probe, encoding="utf-8") as handle:
            derived = handle.read().strip()
        self.assertEqual(os.path.basename(derived), "lean")
        self.assertNotEqual(os.path.dirname(derived), bin_dir)
        # The run's own tool directory (cleaned up afterwards) was the one
        # that answered the lookup.
        self.assertIn("lean-tool-bin-", os.path.dirname(derived))

    def test_a_file_quoting_a_toolchain_phrase_is_still_refuted(self):
        # The review finding: quoting one of elan's lines must not turn a
        # refutation into UNVERIFIABLE. The file's own error wins.
        repo, commit = self.probe_repo("phrase-dodge", _SORRY)
        output = (
            "error: lean/Proof.lean:3:9: Application type mismatch\n"
            '  exact "error: invalid toolchain name"\n'
            "error: invalid toolchain name\n"
        )
        bin_dir = self.fake(**{"build.out": output, "build.rc": "1\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)

    def test_a_symlinked_toolchain_file_does_not_leak_host_content(self):
        # The committed file may be a symlink to any host file the checker
        # can read; its content must never reach the verdict.
        repo, commit = self.probe_repo("symlink-leak", _PROOF)
        secret = os.path.join(self._tmp.name, "host-secret.txt")
        with open(secret, "w", encoding="utf-8") as handle:
            handle.write("P17-CANARY-SECRET=sk-live-abcdef123456\n")
        link = os.path.join(repo.path, "lean", "lean-toolchain")
        if os.path.exists(link):
            os.unlink(link)
        os.symlink(secret, link)
        _git(repo.path, "add", "-A")
        _git(repo.path, "commit", "-q", "-m", "toolchain file as a symlink")
        commit = _git(repo.path, "rev-parse", "HEAD").stdout.strip()
        bin_dir = self.answering(self.fake())
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertNotIn("P17-CANARY-SECRET", result.reason)
        self.assertIn("does not hold a toolchain name", result.reason)

    def test_tool_bin_dir_cleans_up_after_a_failed_link(self):
        # A half-built tool directory must not stay behind: the second link
        # fails (its name has a path part), the first one is already there.
        before = set(os.listdir(self._tmp.name))
        with self.assertRaises(OSError):
            lean._tool_bin_dir(
                self._tmp.name,
                [
                    lean._Tool("lean", "/bin/echo", "sha256:" + "a" * 64, None, False),
                    lean._Tool("sub/lake", "/bin/true", "sha256:" + "b" * 64, None, False),
                ],
            )
        left = [
            name
            for name in set(os.listdir(self._tmp.name)) - before
            if name.startswith("lean-tool-bin-")
        ]
        self.assertEqual(left, [])

    def test_a_manifest_pin_names_the_pinned_digest_in_the_verdict(self):
        repo, commit = self.probe_repo("manifest-identity", _PROOF)
        bin_dir = self.answering(self.fake())
        digest = self.sha(os.path.join(bin_dir, "lean"))
        tools = self.write_manifest(
            {
                "lean": (os.path.join(bin_dir, "lean"), "4.33.1", digest),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn(
            f"lean 4.33.1 sha256:{digest.split(':', 1)[1][:12]} [pinned]", result.reason
        )

    def test_a_manifest_pin_to_a_missing_tool_is_unverifiable(self):
        # P17 (c): a pinned path that does not exist is an environment
        # defect; the claim is not refuted, and no other lean is run.
        repo, commit = self.probe_repo("manifest-missing", _PROOF)
        bin_dir = self.answering(self.fake())
        missing = os.path.join(self._tmp.name, "nowhere", "lean")
        tools = self.write_manifest(
            {
                "lean": (missing, None, None),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn(missing, result.reason)
        self.assertIn("does not exist", result.reason)

    def test_a_manifest_digest_mismatch_is_unverifiable(self):
        # The pinned content is the promise; a different binary is refused.
        repo, commit = self.probe_repo("manifest-digest", _PROOF)
        bin_dir = self.answering(self.fake())
        tools = self.write_manifest(
            {
                "lean": (os.path.join(bin_dir, "lean"), None, "sha256:" + "0" * 64),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("sha256:000000000000", result.reason)

    def test_a_manifest_version_mismatch_is_unverifiable(self):
        repo, commit = self.probe_repo("manifest-version", _PROOF)
        bin_dir = self.answering(self.fake())
        tools = self.write_manifest(
            {
                "lean": (os.path.join(bin_dir, "lean"), "9.9.9", None),
                "leanchecker": (os.path.join(bin_dir, "leanchecker"), None, None),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("9.9.9", result.reason)
        self.assertIn("4.33.1", result.reason)

    def test_a_tool_the_manifest_does_not_allow_is_unverifiable(self):
        # P17 (d): with a manifest the allowed tools come from the manifest;
        # there is no silent PATH fallback.
        repo, commit = self.probe_repo("manifest-narrow", _PROOF)
        bin_dir = self.answering(self.fake())
        tools = self.write_manifest(
            {"lean": (os.path.join(bin_dir, "lean"), None, None)}
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, tools=tools)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("leanchecker", result.reason)
        self.assertIn("does not allow", result.reason)

    def test_a_project_toolchain_file_without_a_host_pin_is_refused(self):
        # An elan whose toolchain is not pinned resolves it from the inspected
        # tree; that path is refused instead of judged.
        repo, commit = self.toolchain_repo("tc-unpinned", "")
        bin_dir = self.answering(
            self.elan_with_fake_tools(
                ("leanprover--lean4---v4.33.1", "leanprover--lean4---v4.34.0")
            )
        )
        with self.patched_path(bin_dir):
            os.environ.pop("ELAN_TOOLCHAIN", None)
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.ENVIRONMENT, result.reason)
        self.assertIn("no host-side toolchain", result.reason)
        self.assertIn("lean-toolchain", result.reason)

    def test_the_tool_names_are_pinned_in_a_checker_owned_directory(self):
        # The launchers resolve `lean` by name from PATH; the run's PATH leads
        # with a directory that points every name at the identified tool.
        directory = lean._tool_bin_dir(
            self._tmp.name,
            [
                lean._Tool("lean", "/bin/echo", "sha256:" + "a" * 64, None, False),
                lean._Tool("leanchecker", "/bin/true", "sha256:" + "b" * 64, None, False),
            ],
        )
        self.assertEqual(os.readlink(os.path.join(directory, "lean")), "/bin/echo")
        self.assertEqual(os.readlink(os.path.join(directory, "leanchecker")), "/bin/true")

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox boundary tests")
    def test_the_working_tree_cache_is_bound_read_only_when_present(self):
        repo, commit = self.lake_repo("lake-cache")
        packages = os.path.join(repo.path, "proofs", ".lake", "packages")
        os.makedirs(packages, exist_ok=True)
        with open(os.path.join(packages, "marker"), "w", encoding="utf-8") as handle:
            handle.write("cache\n")
        bin_dir = self.fake(**{"query.out": _answer("lake_proven", "")})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("read-only", result.command)
        self.assertIn(packages, result.command)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIs(result.sandboxed, True)

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox boundary tests")
    def test_a_read_only_cache_build_failure_is_unverifiable(self):
        repo, commit = self.lake_repo("lake-cache-ro")
        packages = os.path.join(repo.path, "proofs", ".lake", "packages")
        os.makedirs(packages, exist_ok=True)
        bin_dir = self.fake(
            **{
                "build.out": "error: read-only file system (error code: 30)\n",
                "build.rc": "1\n",
                "query.out": _answer("lake_proven", ""),
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("read-only", result.reason)
        self.assertNotIn("does not compile", result.reason)


@unittest.skipUnless(_LEAN and _BWRAP, "lean and bwrap are required for the live tests")
class LeanLiveTest(unittest.TestCase):
    """Live runs against the real toolchain, sandboxed."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        proc = subprocess.run([_LEAN, "--version"], capture_output=True, text=True)
        match = re.search(r"version (\d+\.\d+\.\d+)", proc.stdout)
        if match is None:
            raise unittest.SkipTest(f"cannot parse lean --version: {proc.stdout!r}")
        cls.toolchain = match.group(1)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._path = mock.patch.dict(
            os.environ,
            {"PATH": os.path.dirname(_LEAN) + os.pathsep + os.environ.get("PATH", "")},
        )
        self._path.start()
        self.addCleanup(self._path.stop)

    def ctx(self, repo, **kw):
        work = os.path.join(self._tmp.name, "work", self._testMethodName)
        os.makedirs(work, exist_ok=True)
        kw.setdefault("tmp_dir", work)
        kw.setdefault("sandbox", "auto")
        return Ctx(repo=repo, **kw)

    def probe_repo(self, name, source, extra=()):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit = commit_probe(repo, "lean/Proof.lean", source)
        for filename, content in extra:
            commit = commit_probe(repo, filename, content)
        return repo, commit

    def check_report(self, path, theorem, commit, ctx):
        return self.check_report_pair(path, theorem, commit, ctx)[1]

    def check_report_pair(self, path, theorem, commit, ctx):
        """The claim and its result -- for tests that pin the run's exit code."""
        text = f"[LEAN: {path} -> {theorem}]\n**send_to payload:** `[COMMIT: {commit}]`\n"
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertEqual(len(claims), 1)
        return claims[0], run_claim(claims[0], ctx)

    def lake_repo(self, name, source=_LAKE_PROOF):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit_probe(repo, "proofs/lean-toolchain", f"leanprover/lean4:v{self.toolchain}\n")
        commit = commit_probe(repo, "proofs/Proofs.lean", source)
        return repo, commit

    def decoy(self, marker):
        """A repository-authored toolchain binary: it proves it ran, or not."""
        return (
            "#!/bin/sh\n"
            f'echo "decoy-ran $*" >> "{marker}"\n'
            "case \"$1\" in\n"
            "  --version) echo 'Lean (version 4.33.1, decoy, Release)' ;;\n"
            "  --print-libdir) echo '/bin' ;;\n"
            "  *) echo 'decoy' ;;\n"
            "esac\n"
            "exit 0\n"
        )

    def hostile_repo(self, name, marker, toolchain="./evil", lakefile=None):
        """A proof whose project ships a path-like toolchain request + decoy."""
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit_probe(repo, "evil/bin/lean", self.decoy(marker))
        os.chmod(os.path.join(repo.path, "evil/bin/lean"), 0o755)
        if lakefile is not None:
            commit_probe(repo, "proofs/lakefile.toml", lakefile)
            commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
            commit = commit_probe(repo, "proofs/lean-toolchain", toolchain + "\n")
        else:
            commit_probe(repo, "lean/Proof.lean", _PROOF)
            commit = commit_probe(repo, "lean-toolchain", toolchain + "\n")
        return repo, commit

    def toolchain_bin(self):
        """The toolchain's own bin directory behind the shim, else None."""
        directory = os.path.dirname(os.path.realpath(_LEAN))
        root = os.path.dirname(directory)
        if os.path.basename(directory) == "bin" and os.path.isdir(
            os.path.join(root, "toolchains")
        ):
            toolchains = os.path.join(root, "toolchains")
            names = sorted(
                name
                for name in os.listdir(toolchains)
                if os.path.isdir(os.path.join(toolchains, name))
            )
            if len(names) == 1:
                return os.path.join(toolchains, names[0], "bin")
            return None
        if os.path.isfile(os.path.join(directory, "leanchecker")):
            return directory
        return None

    def clear_marker(self, marker):
        if os.path.exists(marker):
            os.unlink(marker)

    def marker_lines(self, marker):
        if not os.path.exists(marker):
            return []
        with open(marker, encoding="utf-8") as handle:
            return handle.read().splitlines()

    # --- the P17 acceptance cases with the real toolchain ------------------
    def test_a_path_like_toolchain_request_never_runs_the_decoy(self):
        # P17 (a) / P18b: the decoy writes a marker when it runs; the checker
        # refuses the path-like request before any tool starts, so the marker
        # stays absent and the verdict is UNVERIFIABLE, never CONFIRMED. The
        # refusal is a form violation in the checked thing: class defect,
        # exit 5 in both modes. Unsandboxed on purpose: a sandboxed decoy
        # could not write the marker at all, so only outside the sandbox is
        # the marker real evidence.
        marker = os.path.join(self._tmp.name, "decoy-marker-path.txt")
        self.clear_marker(marker)
        repo, commit = self.hostile_repo("live-toolchain-path", marker)
        claim, result = self.check_report_pair(
            "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, sandbox="off")
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertEqual(exit_code([(claim, result)], strict=True), EXIT_DEFECT)
        self.assertNotIn("./evil", result.reason)
        self.assertIn("does not hold a toolchain name", result.reason)
        self.assertEqual(self.marker_lines(marker), [])

    def test_a_manifest_pin_keeps_the_decoy_out_of_the_run(self):
        # The review finding, live: lean is pinned to a concrete toolchain
        # binary while leanchecker stays an elan shim, and the repository
        # ships .elan/settings.toml pointing its default toolchain at its own
        # decoy. Left to itself, the shim would resolve through
        # HOME=<checkout> and run it; the run must hand over the host root
        # instead. Unsandboxed so the marker is observable.
        marker = os.path.join(self._tmp.name, "decoy-marker-settings.txt")
        self.clear_marker(marker)
        bin_dir = self.toolchain_bin()
        if bin_dir is None:
            self.skipTest("the toolchain's own bin directory is not derivable")
        checker_shim = os.path.join(os.path.dirname(os.path.realpath(_LEAN)), "leanchecker")
        if not os.path.isfile(checker_shim):
            self.skipTest("no leanchecker beside the lean shim")
        repo = make_repo(os.path.join(self._tmp.name, "live-toolchain-settings"))
        self.clear_marker(marker)
        commit_probe(repo, "evil/bin/lean", self.decoy(marker))
        os.chmod(os.path.join(repo.path, "evil/bin/lean"), 0o755)
        commit_probe(repo, "evil/bin/leanchecker", self.decoy(marker))
        os.chmod(os.path.join(repo.path, "evil/bin/leanchecker"), 0o755)
        commit_probe(repo, ".elan/settings.toml", 'default_toolchain = "./evil"\n')
        commit_probe(repo, "lean/Proof.lean", _PROOF)
        commit = commit_probe(
            repo, "lean/lean-toolchain", f"leanprover/lean4:v{self.toolchain}\n"
        )
        manifest = _write_manifest(
            os.path.join(self._tmp.name, "live-manifests"),
            "pins.toml",
            {
                "lean": (
                    os.path.join(bin_dir, "lean"),
                    self.toolchain,
                    _sha256(os.path.join(bin_dir, "lean")),
                ),
                "leanchecker": (
                    checker_shim,
                    None,
                    _sha256(checker_shim),
                ),
            },
        )
        result = self.check_report(
            "lean/Proof.lean",
            "fixture_proven",
            commit,
            self.ctx(repo.path, sandbox="off", tools=toolmanifest.load(manifest)),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("[pinned]", result.reason)
        self.assertEqual(self.marker_lines(marker), [])

    def test_a_shim_manifest_pin_judges_inside_the_sandbox(self):
        # The common host setup: the manifest pins the elan shims themselves.
        repo, commit = self.probe_repo("live-shim-manifest", _PROOF)
        if _BWRAP is None:
            self.skipTest("bwrap is not available")
        bin_dir = os.path.dirname(os.path.realpath(_LEAN))
        manifest = _write_manifest(
            os.path.join(self._tmp.name, "live-manifests"),
            "shims.toml",
            {
                name: (
                    os.path.join(bin_dir, name),
                    self.toolchain if name == "lean" else None,
                    _sha256(os.path.join(bin_dir, name)),
                )
                for name in ("lean", "leanchecker")
            },
        )
        result = self.check_report(
            "lean/Proof.lean",
            "fixture_proven",
            commit,
            self.ctx(repo.path, sandbox="auto", tools=toolmanifest.load(manifest)),
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIn("[pinned]", result.reason)

    def test_a_lake_projects_toolchain_request_is_refused_before_any_build(self):
        marker = os.path.join(self._tmp.name, "decoy-marker-lake.txt")
        self.clear_marker(marker)
        repo, commit = self.hostile_repo(
            "live-toolchain-lake", marker, lakefile=_LAKEFILE
        )
        claim, result = self.check_report_pair(
            "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIs(result.cause, Cause.DEFECT, result.reason)
        self.assertEqual(exit_code([(claim, result)]), EXIT_DEFECT)
        self.assertNotIn("./evil", result.reason)
        self.assertIn("does not hold a toolchain name", result.reason)
        self.assertEqual(self.marker_lines(marker), [])

    # --- the acceptance matrix --------------------------------------------
    def test_a_real_theorem_confirms(self):
        repo, commit = self.probe_repo("live-confirm", _PROOF)
        result = self.check_report(
            "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("does not depend on any axioms", result.reason)
        self.assertIn("passed Lean's kernel re-check", result.reason)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIn(f"tools: lean {self.toolchain} sha256:", result.reason)
        self.assertIn(f"leanchecker {self.toolchain} sha256:", result.reason)
        self.assertIs(result.sandboxed, True)

    def test_a_real_sorry_refutes(self):
        repo, commit = self.probe_repo("live-sorry", _SORRY)
        result = self.check_report(
            "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("depends on axioms: [sorryAx]", result.reason)

    def test_a_real_compile_error_refutes_with_the_error_line(self):
        repo, commit = self.probe_repo("live-broken", _BROKEN)
        result = self.check_report(
            "lean/Proof.lean", "fixture_broken", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("does not compile", result.reason)

    def test_a_real_unknown_declaration_refutes(self):
        repo, commit = self.probe_repo("live-unknown", _PROOF)
        result = self.check_report(
            "lean/Proof.lean", "no_such_declaration", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("declaration not found", result.reason)

    def test_a_real_lake_project_builds_offline_and_confirms(self):
        repo, commit = self.lake_repo("live-lake")
        result = self.check_report(
            "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("does not depend on any axioms", result.reason)
        self.assertIn("leanchecker", result.reason)

    def test_a_real_unsafe_declaration_is_not_confirmed(self):
        repo, commit = self.probe_repo(
            "live-unsafe", "unsafe def fixture_cheat : False := unsafeCast ()\n"
        )
        result = self.check_report(
            "lean/Proof.lean", "fixture_cheat", commit, self.ctx(repo.path)
        )
        self.assertNotEqual(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("lcProof", result.reason)

    # --- hostile modules: the evidence cannot be forged --------------------
    def test_a_module_forging_evidence_and_exiting_never_confirms(self):
        # The primitive from review 5.4 round 1: print fake evidence, then end
        # the process. The file drives its own build, which the policy refuses
        # (documented boundary); in no case may the claim be confirmed.
        hostile = (
            "#eval do\n"
            "  IO.println \"'target_claim' does not depend on any axioms\"\n"
            "  IO.Process.exit 0\n"
            "\n"
            "theorem target_claim (n : Nat) : n + 0 = n := by sorry\n"
        )
        repo, commit = self.probe_repo("live-hostile-exit", hostile)
        result = self.check_report(
            "lean/Proof.lean", "target_claim", commit, self.ctx(repo.path)
        )
        self.assertNotEqual(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("#eval", result.reason)

    def test_a_module_initializer_forging_evidence_is_refuted_on_the_merits(self):
        hostile = (
            "initialize do\n"
            "  IO.println \"'fixture_sorry' does not depend on any axioms\"\n"
            "  IO.Process.exit 0\n"
            "\n" + _SORRY
        )
        repo, commit = self.probe_repo("live-hostile-init", hostile)
        result = self.check_report(
            "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("depends on axioms: [sorryAx]", result.reason)
        self.assertNotIn("does not depend on any axioms", result.reason)


class SandboxFailureDetectionTest(unittest.TestCase):
    """P20 (A): a forged "bwrap: " line must not re-label a real tool run.

    bwrap fails before the tool starts, so a genuine sandbox failure is the
    whole output. Visible code execution (an imported module's #eval) can
    print a "bwrap: ..." line; the detection requires the line to be the
    entire output so such a line cannot masquerade as a sandbox problem.
    """

    def test_a_pure_bwrap_failure_is_recognized(self):
        self.assertTrue(
            lean._is_sandbox_failure("bwrap: Creating new namespace failed: Operation not permitted\n")
        )
        self.assertTrue(
            lean._is_sandbox_failure("bwrap: execvp lean: No such file or directory\n")
        )

    def test_a_forged_bwrap_line_beside_real_output_is_not_a_sandbox_failure(self):
        self.assertFalse(
            lean._is_sandbox_failure(
                "some lake output\nbwrap: forged by an imported initializer\nerror: build failed\n"
            )
        )
        self.assertFalse(lean._is_sandbox_failure("lean: unexpected output\nbwrap: x\n"))

    def test_empty_output_is_no_sandbox_failure(self):
        self.assertFalse(lean._is_sandbox_failure(""))
        self.assertFalse(lean._is_sandbox_failure("\n\n"))


if __name__ == "__main__":
    unittest.main()

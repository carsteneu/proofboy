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

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.claimtypes import lean
from bemyself.checks import Ctx, kind_needs_repo, run_claim
from bemyself.model import Verdict
from bemyself.report import parse_report
from tests.fixtures import commit_probe, make_repo

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
  printf '%s\\n' 'Lean (version 4.33.1, fake, Release)'
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
[ -f "$dir/$f.sleep" ] && sleep 30
[ -f "$dir/$f.out" ] && cat "$dir/$f.out"
if [ "$mode" = build ] && [ -f "$dir/build.dirty" ]; then
  printf '\\n-- dirtied by another module\\n' >> "$(cat "$dir/build.dirty")"
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
    return f"BEMYSELF-LEAN-AXIOMS {name} [{axioms}]\n"


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
        text = "BEMYSELF-LEAN-UNKNOWN fixture_proven\n"
        self.assertEqual(lean._query_answer(text, "fixture_proven"), ("unknown", None))

    def test_the_error_marker_is_read(self):
        text = "BEMYSELF-LEAN-ERROR unknown module prefix 'Ghost'\n"
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
        text = f"[LEAN: {path} -> {theorem}]\n"
        if commit is not None:
            text = f"**send_to payload:** `[COMMIT: {commit}]`\n" + text
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx)

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
        bin_dir = self.fake(**{"query.out": "BEMYSELF-LEAN-UNKNOWN no_such\n", "query.rc": "1\n"})
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
            "bemyself.checks.find_bwrap", return_value=broken
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
                "query.out": "BEMYSELF-LEAN-FOREIGN fixture_proven Helper\n",
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
            "bemyself.checks.find_bwrap", return_value=None
        ):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
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
                "query.out": "BEMYSELF-LEAN-ERROR cannot load olean for Proof\n",
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
        text = f"[LEAN: {path} -> {theorem}]\n**send_to payload:** `[COMMIT: {commit}]`\n"
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx)

    def lake_repo(self, name, source=_LAKE_PROOF):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit_probe(repo, "proofs/lean-toolchain", f"leanprover/lean4:v{self.toolchain}\n")
        commit = commit_probe(repo, "proofs/Proofs.lean", source)
        return repo, commit

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


if __name__ == "__main__":
    unittest.main()

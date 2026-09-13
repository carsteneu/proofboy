"""Tests for the [LEAN: <path.lean> -> <declaration>] claim type.

A LEAN claim is a formal proof certificate: in the report's pinned commit the
named Lean source file exists and the named declaration is proved there
without sorry/admit. The checker re-elaborates a copy of the pinned source
with Lean and reads the #print axioms line. The hermetic matrix below drives
every verdict through fake lean/lake binaries (no real toolchain needed); the
live tests exercise the real toolchain when it is present on the host.
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


def _fake_tool(bin_dir, name):
    """Write a fake ``lean``/``lake`` executable answering from files.

    The checker runs children with a minimal environment, so the canned
    answer cannot travel as an environment variable: it lives in files under
    ``bin_dir`` (``run.out``, ``run.rc``, ``build.out``, ``build.rc``,
    ``run.sleep``). The fake also logs its argv and the elaborated driver so
    a test can assert what the checker really ran.
    """
    path = os.path.join(bin_dir, name)
    script = "\n".join(
        [
            "#!/bin/sh",
            f"dir='{bin_dir}'",
            'case "$1" in',
            "  --version)",
            "    printf '%s\\n' 'Lean (version 4.33.1, fake, Release)'",
            "    exit 0",
            "    ;;",
            "  build)",
            '    printf \'%s\\n\' "build" "$2" >> "$dir/lake.args"',
            '    [ -f "$dir/build.out" ] && cat "$dir/build.out"',
            '    if [ -f "$dir/build.rc" ]; then exit "$(cat "$dir/build.rc")"; fi',
            "    exit 0",
            "    ;;",
            "  env)",
            '    printf \'%s\\n\' "env" "$2" "$3" >> "$dir/lake.args"',
            '    drv="$3"',
            "    ;;",
            "  *)",
            '    printf \'%s\\n\' "$1" >> "$dir/lean.args"',
            '    drv="$1"',
            "    ;;",
            "esac",
            '[ -f "$dir/run.sleep" ] && sleep 30',
            'if [ -n "$drv" ] && [ -f "$drv" ]; then cat "$drv" >> "$dir/driver.copy"; fi',
            '[ -f "$dir/run.out" ] && cat "$dir/run.out"',
            'if [ -f "$dir/run.rc" ]; then exit "$(cat "$dir/run.rc")"; fi',
            "exit 0",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(script)
    os.chmod(path, 0o755)
    return path


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


class LeanCheckTest(unittest.TestCase):
    """Hermetic matrix: fake lean/lake, unsandboxed, real git fixtures."""

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

    def lake_repo(self, name):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        return repo, commit

    def fake(self, **files):
        bin_dir = os.path.join(self._tmp.name, "bin", self._testMethodName)
        os.makedirs(bin_dir, exist_ok=True)
        for name, content in files.items():
            with open(os.path.join(bin_dir, name), "w", encoding="utf-8") as handle:
                handle.write(content)
        _fake_tool(bin_dir, "lean")
        _fake_tool(bin_dir, "lake")
        return bin_dir

    def patched_path(self, bin_dir):
        # The fake dir first, the real PATH behind it (git, cat, python3).
        path = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return mock.patch.dict(os.environ, {"PATH": path})

    def check_report(self, path, theorem, commit, ctx):
        text = f"[LEAN: {path} -> {theorem}]\n"
        if commit is not None:
            text = f"**send_to payload:** `[COMMIT: {commit}]`\n" + text
        claims = [claim for claim in parse_report(text) if claim.kind == "lean"]
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx)

    # --- the positive and the refuted paths --------------------------------
    def test_axioms_line_confirms(self):
        repo, commit = self.probe_repo("confirm", _PROOF)
        bin_dir = self.fake(
            **{"run.out": "'fixture_proven' depends on axioms: [propext, Quot.sound]\n"}
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("depends on axioms: [propext, Quot.sound]", result.reason)
        self.assertIn("re-elaborated", result.reason)
        self.assertIn("git checkout", result.command)
        self.assertIn("not sandboxed: --sandbox=off", result.reason)
        self.assertIs(result.sandboxed, False)

    def test_no_axioms_confirms(self):
        repo, commit = self.probe_repo("noaxioms", _PROOF)
        bin_dir = self.fake(**{"run.out": "'fixture_proven' does not depend on any axioms\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("does not depend on any axioms", result.reason)

    def test_sorry_axiom_refutes_with_the_exact_wording(self):
        repo, commit = self.probe_repo("sorry", _SORRY)
        bin_dir = self.fake(**{"run.out": "'fixture_sorry' depends on axioms: [sorryAx]\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("depends on axioms: [sorryAx]", result.reason)

    def test_sorry_with_more_axioms_refutes_and_names_all(self):
        repo, commit = self.probe_repo("sorry-mix", _SORRY)
        bin_dir = self.fake(
            **{"run.out": "'fixture_sorry' depends on axioms: [sorryAx, propext]\n"}
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_sorry", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("[sorryAx, propext]", result.reason)

    def test_a_compile_error_refutes_with_the_first_error_line(self):
        repo, commit = self.probe_repo("broken", _BROKEN)
        bin_dir = self.fake(
            **{
                "run.out": "lean/Proof.lean:1:0: error: unsolved goals\n"
                "lean/Proof.lean:2:0: error: second failure\n",
                "run.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_broken", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("error: unsolved goals", result.reason)
        self.assertNotIn("second failure", result.reason)

    def test_an_unknown_declaration_refutes(self):
        repo, commit = self.probe_repo("unknown", _PROOF)
        bin_dir = self.fake(
            **{
                "run.out": "error(lean.unknownIdentifier): Unknown constant "
                "\u00abNoSuchThing\u00bb\n",
                "run.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "NoSuchThing", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("Unknown constant", result.reason)

    def test_a_missing_imported_module_is_unverifiable_not_refuted(self):
        repo, commit = self.probe_repo("dep", "import Mathlib\n\n" + _PROOF)
        bin_dir = self.fake(
            **{
                "run.out": "error: unknown module prefix 'Mathlib'\n",
                "run.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("Mathlib", result.reason)

    def test_a_missing_module_the_file_does_not_import_still_refutes(self):
        repo, commit = self.probe_repo("dep-lies", _PROOF)
        bin_dir = self.fake(
            **{
                "run.out": "error: unknown module prefix 'Mathlib'\n",
                "run.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)

    def test_a_run_without_the_axioms_line_is_unverifiable(self):
        repo, commit = self.probe_repo("noline", _PROOF)
        bin_dir = self.fake(**{"run.out": "some unrelated output\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("no #print axioms line", result.reason)

    def test_a_timeout_is_unverifiable(self):
        repo, commit = self.probe_repo("timeout", _PROOF)
        bin_dir = self.fake(**{"run.out": "'x' does not depend on any axioms\n", "run.sleep": "1\n"})
        with self.patched_path(bin_dir), mock.patch.object(lean, "LEAN_TIMEOUT", 1):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("timed out", result.reason)

    # --- the guards --------------------------------------------------------
    def test_a_broken_file_outside_any_lake_project_needs_no_lake(self):
        repo, commit = self.probe_repo("nolake", _PROOF, filename="Proof.lean")
        bin_dir = self.fake(**{"run.out": "'fixture_proven' does not depend on any axioms\n"})
        os.remove(os.path.join(bin_dir, "lake"))
        with self.patched_path(bin_dir):
            result = self.check_report("Proof.lean", "fixture_proven", commit, self.ctx(repo.path))
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)

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

    def test_auto_without_bwrap_is_unverifiable_and_runs_nothing(self):
        repo, commit = self.probe_repo("nosandbox", _PROOF)
        bin_dir = self.fake(**{"run.out": "'x' does not depend on any axioms\n"})
        with self.patched_path(bin_dir), mock.patch(
            "bemyself.checks.find_bwrap", return_value=None
        ):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("bwrap", result.reason)
        self.assertFalse(os.path.exists(os.path.join(bin_dir, "lean.args")))

    def test_a_broken_sandbox_never_refutes(self):
        repo, commit = self.probe_repo("broken-bwrap", _PROOF)
        bin_dir = self.fake(**{"run.out": "'fixture_proven' does not depend on any axioms\n"})
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
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("bwrap", result.reason)

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

    # --- the lake path -----------------------------------------------------
    def test_a_lake_project_builds_the_module_before_elaborating(self):
        repo, commit = self.lake_repo("lake")
        bin_dir = self.fake(**{"run.out": "'lake_proven' does not depend on any axioms\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "lake.args"), encoding="utf-8") as handle:
            args = handle.read().splitlines()
        self.assertEqual(args[:2], ["build", "Proofs"])
        self.assertEqual(args[2:4], ["env", "lean"])
        self.assertIn("lake env lean", result.command)

    def test_a_build_failure_in_the_target_file_refutes(self):
        repo, commit = self.lake_repo("lake-broken")
        bin_dir = self.fake(
            **{
                "build.out": "proofs/Proofs.lean:1:0: error: unsolved goals\n",
                "build.rc": "1\n",
                "run.out": "should not run\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("error: unsolved goals", result.reason)

    def test_a_build_failure_elsewhere_is_unverifiable(self):
        repo, commit = self.lake_repo("lake-dep")
        bin_dir = self.fake(
            **{
                "build.out": "proofs/Other.lean:1:0: error: dependency is broken\n",
                "build.rc": "1\n",
            }
        )
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.reason)
        self.assertIn("dependency is broken", result.reason)

    def test_the_driver_copies_the_pinned_source_and_appends_the_question(self):
        repo, commit = self.probe_repo("driver", _PROOF)
        bin_dir = self.fake(**{"run.out": "'fixture_proven' does not depend on any axioms\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        with open(os.path.join(bin_dir, "driver.copy"), encoding="utf-8") as handle:
            driver = handle.read()
        self.assertTrue(driver.startswith(_PROOF), driver)
        self.assertIn("#print axioms fixture_proven", driver)

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox boundary tests")
    def test_the_working_tree_cache_is_bound_read_only_when_present(self):
        repo, commit = self.lake_repo("lake-cache")
        cache = os.path.join(repo.path, "proofs", ".lake")
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "marker"), "w", encoding="utf-8") as handle:
            handle.write("cache\n")
        bin_dir = self.fake(**{"run.out": "'lake_proven' does not depend on any axioms\n"})
        with self.patched_path(bin_dir):
            result = self.check_report(
                "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path, sandbox="auto")
            )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("read-only", result.command)
        self.assertIn(cache, result.command)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIs(result.sandboxed, True)


@unittest.skipUnless(_LEAN and _BWRAP, "lean and bwrap are required for the live tests")
class LeanLiveTest(unittest.TestCase):
    """Live runs against the real Lean toolchain, sandboxed."""

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

    def test_a_real_theorem_confirms(self):
        repo, commit = self.probe_repo("live-confirm", _PROOF)
        result = self.check_report(
            "lean/Proof.lean", "fixture_proven", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("does not depend on any axioms", result.reason)
        self.assertIn("re-elaborated", result.reason)
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
        self.assertIn("error", result.reason)

    def test_a_real_unknown_declaration_refutes(self):
        repo, commit = self.probe_repo("live-unknown", _PROOF)
        result = self.check_report(
            "lean/Proof.lean", "no_such_declaration", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.REFUTED, result.reason)
        self.assertIn("Unknown constant", result.reason)

    def test_a_real_lake_project_builds_offline_and_confirms(self):
        repo = make_repo(os.path.join(self._tmp.name, "live-lake"))
        commit_probe(repo, "proofs/lakefile.toml", _LAKEFILE)
        commit_probe(repo, "proofs/lean-toolchain", f"leanprover/lean4:v{self.toolchain}\n")
        commit = commit_probe(repo, "proofs/Proofs.lean", _LAKE_PROOF)
        result = self.check_report(
            "proofs/Proofs.lean", "lake_proven", commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.reason)
        self.assertIn("does not depend on any axioms", result.reason)
        self.assertIn("lake env lean", result.command)


if __name__ == "__main__":
    unittest.main()

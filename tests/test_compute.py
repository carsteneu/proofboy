"""Tests for the [COMPUTE: <command> -> <sha256>] claim type.

A COMPUTE claim is a computation certificate: the command is re-run in the
sandbox on a throwaway checkout of the report's pinned commit and the SHA-256
of its stdout is compared. The negative matrix below pins every way a run may
stay unverifiable, and the network probe proves the sandbox boundary.
"""

import hashlib
import os
import shutil
import socket
import tempfile
import time
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.claimtypes import compute
from bemyself.checks import Ctx, kind_needs_repo, run_claim
from bemyself.report import parse_report
from bemyself.model import Verdict
from tests.fixtures import commit_probe, make_repo

_BWRAP = shutil.which("bwrap")

_EMIT = "print('compute: 42')\n"
_NET_PROBE = (
    "import socket\n"
    "socket.create_connection((\"127.0.0.1\", {port}), timeout=5)\n"
    "print(\"connected\")\n"
)
_SLEEPER = "import time; time.sleep(30)\n"
_FLOODER = "import sys; sys.stdout.write('x' * 1000000)\n"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ComputeParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report(f"[COMPUTE: python3 emit.py -> {'a' * 64}]\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "compute")
        self.assertEqual(claim.fields["command"], "python3 emit.py")
        self.assertEqual(claim.fields["sha256"], "a" * 64)
        self.assertIsNone(claim.fields["commit"])

    def test_the_last_arrow_separates_command_and_digest(self):
        claims = parse_report(
            f"[COMPUTE: python3 -c \"print(1->2)\" -> {'b' * 64}]\n"
        )
        self.assertEqual(claims[0].fields["command"], 'python3 -c "print(1->2)"')
        self.assertEqual(claims[0].fields["sha256"], "b" * 64)

    def test_unicode_arrow_parses(self):
        claims = parse_report(f"[COMPUTE: python3 emit.py \u2192 {'c' * 64}]\n")
        self.assertEqual(claims[0].fields["sha256"], "c" * 64)

    def test_marker_without_arrow_is_no_claim(self):
        self.assertEqual(parse_report("[COMPUTE: python3 emit.py]\n"), [])

    def test_empty_fields_still_parse(self):
        claims = parse_report("[COMPUTE: -> ]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["command"], "")
        self.assertEqual(claims[0].fields["sha256"], "")

    def test_absurdly_long_line_is_ignored(self):
        line = f"[COMPUTE: python3 emit.py -> {'a' * 64}] " + "x" * 9000 + "\n"
        self.assertEqual(parse_report(line), [])

    def test_unterminated_marker_stays_linear(self):
        start = time.perf_counter()
        claims = parse_report("[COMPUTE:" + " " * 2000 + "\n")
        elapsed = time.perf_counter() - start
        self.assertEqual(claims, [])
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for a hostile line")


class ComputeRegistryTest(unittest.TestCase):
    def test_compute_is_registered(self):
        self.assertIn(compute.COMPUTE, claimtypes.CLAIM_TYPES)
        self.assertEqual(compute.COMPUTE.kind, "compute")

    def test_the_check_declares_a_repository_need(self):
        self.assertTrue(kind_needs_repo("compute"))

    def test_the_claim_binds_to_the_report_commit(self):
        self.assertTrue(compute.COMPUTE.binds_commit)

    def test_the_default_allowlist_is_minimal(self):
        self.assertEqual(
            compute.DEFAULT_COMPUTE_ALLOWLIST,
            (
                "python3 -m bemyself.turing",
                "python3 -m bemyself.experiments.erdos_straus",
            ),
        )

    def test_the_default_allowlist_does_not_open_the_experiments_package(self):
        # The experiment entry is literal: a future module of the package is
        # not opened implicitly.
        argv = ["python3", "-m", "bemyself.experiments.some_future_module"]
        self.assertFalse(compute._allowed_by_tokens(argv, compute.DEFAULT_COMPUTE_ALLOWLIST))


class ComputeCheckTest(unittest.TestCase):
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
        kw.setdefault("compute_allowlist", ("python3 emit.py",))
        # Most tests pin the unsandboxed path so their evidence is
        # host-independent; the sandbox boundary has its own tests.
        kw.setdefault("sandbox", "off")
        return Ctx(repo=repo, **kw)

    def probe_repo(self, name, source, filename="emit.py"):
        repo = make_repo(os.path.join(self._tmp.name, name))
        commit = commit_probe(repo, filename, source)
        return repo, commit

    def check_report(self, command, claimed, commit, ctx):
        text = f"[COMPUTE: {command} -> {claimed}]\n"
        if commit is not None:
            text = f"**send_to payload:** `[COMMIT: {commit}]`\n" + text
        claims = [claim for claim in parse_report(text) if claim.kind == "compute"]
        self.assertEqual(len(claims), 1)
        return run_claim(claims[0], ctx)

    # --- the positive and the refuted path --------------------------------
    def test_matching_digest_confirms(self):
        repo, commit = self.probe_repo("confirm", _EMIT)
        result = self.check_report(
            "python3 emit.py", digest("compute: 42\n"), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn(digest("compute: 42\n"), result.output)
        self.assertIn("exit=0", result.output)
        self.assertIn("git checkout", result.command)
        self.assertIn("--sandbox=off", result.reason)
        self.assertIs(result.sandboxed, False)

    def test_the_default_allowlist_runs_the_experiment_module(self):
        repo, commit = self.probe_repo(
            "experiment",
            "print('fixture erdos-straus')\n",
            filename=os.path.join("bemyself", "experiments", "erdos_straus.py"),
        )
        ctx = self.ctx(repo.path, compute_allowlist=compute.DEFAULT_COMPUTE_ALLOWLIST)
        result = self.check_report(
            "python3 -m bemyself.experiments.erdos_straus 8",
            digest("fixture erdos-straus\n"),
            commit,
            ctx,
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_default_auto_sandboxes_when_bwrap_is_available(self):
        repo, commit = self.probe_repo("confirm-auto", _EMIT)
        result = self.check_report(
            "python3 emit.py", digest("compute: 42\n"), commit, self.ctx(repo.path, sandbox="auto")
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIs(result.sandboxed, True)

    def test_uppercase_digest_confirms(self):
        repo, commit = self.probe_repo("confirm-upper", _EMIT)
        result = self.check_report(
            "python3 emit.py", digest("compute: 42\n").upper(), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)

    def test_wrong_digest_refutes(self):
        repo, commit = self.probe_repo("refute", _EMIT)
        result = self.check_report(
            "python3 emit.py", digest("something else\n"), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn(digest("compute: 42\n"), result.output)
        self.assertIn(digest("something else\n"), result.reason)

    def test_empty_output_is_honest(self):
        repo, commit = self.probe_repo("silent", "pass\n")
        ctx = self.ctx(repo.path, compute_allowlist=("python3 emit.py",))
        result = self.check_report("python3 emit.py", digest(""), commit, ctx)
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("bytes=0", result.output)

    # --- the negative matrix ----------------------------------------------
    def test_command_outside_the_compute_allowlist_is_unverifiable(self):
        repo, commit = self.probe_repo("not-allowed", _EMIT)
        result = self.check_report(
            "curl http://example.invalid", digest("x"), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("compute allowlist", result.reason)

    def test_test_allowlist_does_not_open_the_compute_path(self):
        repo, commit = self.probe_repo("test-allow", _EMIT)
        ctx = self.ctx(repo.path, allowlist=("python3 emit.py",), compute_allowlist=())
        result = self.check_report("python3 emit.py", digest("compute: 42\n"), commit, ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_without_a_commit_the_claim_is_unverifiable(self):
        repo, commit = self.probe_repo("no-commit", _EMIT)
        result = self.check_report("python3 emit.py", digest("compute: 42\n"), None, self.ctx(repo.path))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("no commit hash", result.reason)

    def test_unknown_commit_is_unverifiable(self):
        repo, commit = self.probe_repo("bad-commit", _EMIT)
        result = self.check_report("python3 emit.py", digest("compute: 42\n"), "0" * 40, self.ctx(repo.path))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_bad_digest_format_is_unverifiable(self):
        repo, commit = self.probe_repo("bad-digest", _EMIT)
        for claimed in ("", "abc", "z" * 64, "a" * 63, "a" * 65):
            with self.subTest(claimed=claimed[:12]):
                result = self.check_report("python3 emit.py", claimed, commit, self.ctx(repo.path))
                self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
                self.assertIn("not a sha256", result.reason)

    def test_missing_command_is_unverifiable(self):
        repo, commit = self.probe_repo("missing", _EMIT)
        ctx = self.ctx(repo.path, compute_allowlist=("definitely-missing-program",))
        result = self.check_report(
            "definitely-missing-program --version", digest("x"), commit, ctx
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("not found", result.reason)
        self.assertIsNone(result.sandboxed)

    def test_argument_escaping_the_checkout_is_unverifiable(self):
        repo, commit = self.probe_repo("escape-arg", _EMIT)
        result = self.check_report(
            "python3 emit.py ../../outside", digest("compute: 42\n"), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("unsafe command argument", result.reason)

    def test_symlink_argument_escaping_the_checkout_is_unverifiable(self):
        repo, commit = self.probe_repo("escape-link", _EMIT)
        outside = os.path.join(self._tmp.name, "outside")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "emit.py"), "w", encoding="utf-8") as handle:
            handle.write(_EMIT)
        os.symlink(outside, os.path.join(repo.path, "link"))
        head = commit_probe(repo, "marker.txt", "x\n")
        result = self.check_report(
            "python3 link/emit.py",
            digest("compute: 42\n"),
            head,
            self.ctx(repo.path, compute_allowlist=("python3 link/emit.py",)),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("outside the checkout", result.reason)

    @mock.patch("bemyself.claimtypes.compute.COMPUTE_TIMEOUT", 1)
    def test_timeout_is_unverifiable_and_leaves_no_files(self):
        repo, commit = self.probe_repo("timeout", _SLEEPER)
        ctx = self.ctx(repo.path)
        result = self.check_report("python3 emit.py", digest("x"), commit, ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("timed out after 1s", result.reason)
        self.assertEqual(os.listdir(ctx.tmp_dir), [], "throwaway files were left behind")

    @mock.patch("bemyself.claimtypes.compute.MAX_COMPUTE_BYTES", 4096)
    def test_output_beyond_the_limit_is_unverifiable(self):
        repo, commit = self.probe_repo("flood", _FLOODER)
        result = self.check_report("python3 emit.py", digest("x"), commit, self.ctx(repo.path))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("limit", result.reason)

    def test_failed_command_is_never_certified(self):
        # A run that did not complete certifies nothing, even when the claimed
        # digest is sha256 of the empty stdout it happened to produce.
        repo, commit = self.probe_repo("failed", "import sys\nsys.exit(3)\n")
        result = self.check_report("python3 emit.py", digest(""), commit, self.ctx(repo.path))
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("exited with status 3", result.reason)
        self.assertIn("bytes=0", result.output)

    def test_write_limit_abort_is_not_a_refutation(self):
        # The verifier's own RLIMIT_FSIZE kills a stderr flood before the
        # command prints; such a run must stay unverifiable, not refute a
        # possibly true claim.
        repo, commit = self.probe_repo(
            "stderr-flood", "import sys\nsys.stderr.write('x' * 20_000_000)\nprint('hello')\n"
        )
        result = self.check_report(
            "python3 emit.py", digest("hello\n"), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("did not complete", result.reason)

    def test_a_relative_path_hit_cannot_vouch_for_the_program(self):
        # A relative PATH entry resolves against the child's cwd (the
        # checkout), not the verifier's, so it must not clear the pre-flight.
        repo, commit = self.probe_repo("relative-which", _EMIT)
        ctx = self.ctx(repo.path, compute_allowlist=("mytool",))
        with mock.patch("bemyself.claimtypes.compute.shutil.which", return_value="bin/mytool"):
            result = self.check_report("mytool --version", digest("x"), commit, ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("not found", result.reason)

    def test_unicode_space_cannot_slip_through_the_allowlist(self):
        # The allowlist is matched on the argv tokens that actually execute:
        # a non-breaking space is not shell whitespace, so this command is a
        # different argv and must not inherit the allowlisted prefix.
        repo, commit = self.probe_repo("nbsp", _EMIT)
        result = self.check_report(
            "python3\u00a0emit.py", digest("compute: 42\n"), commit, self.ctx(repo.path)
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("compute allowlist", result.reason)

    def test_require_without_bwrap_never_runs_the_command(self):
        repo, commit = self.probe_repo("require-missing", _EMIT)
        ctx = self.ctx(repo.path, sandbox="require")
        with mock.patch("bemyself.checks.find_bwrap", return_value=None):
            result = self.check_report("python3 emit.py", digest("compute: 42\n"), commit, ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("bwrap is not available", result.reason)
        self.assertIn("refusing to run the command unsandboxed", result.reason)
        self.assertIsNone(result.sandboxed)

    def test_unknown_sandbox_mode_is_never_executed(self):
        repo, commit = self.probe_repo("unknown-mode", _EMIT)
        ctx = self.ctx(repo.path, sandbox="Require")
        result = self.check_report("python3 emit.py", digest("compute: 42\n"), commit, ctx)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("unknown sandbox mode", result.reason)

    # --- the sandbox boundary ---------------------------------------------
    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_sandboxed_run_confirms_and_names_the_sandbox(self):
        repo, commit = self.probe_repo("sandboxed", _EMIT)
        result = self.check_report(
            "python3 emit.py", digest("compute: 42\n"), commit, self.ctx(repo.path, sandbox="require")
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("sandboxed with bwrap", result.reason)
        self.assertIn("bwrap", result.command)
        self.assertIs(result.sandboxed, True)

    @unittest.skipUnless(_BWRAP, "bwrap is required for the sandbox isolation tests")
    def test_network_attempt_fails_in_the_sandbox(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        repo, commit = self.probe_repo("net", _NET_PROBE.format(port=port))
        command = "python3 emit.py"
        open_result = self.check_report(
            command, digest("connected\n"), commit, self.ctx(repo.path, sandbox="off")
        )
        self.assertIs(open_result.verdict, Verdict.CONFIRMED, open_result.output)
        sandboxed = self.check_report(
            command, digest("connected\n"), commit, self.ctx(repo.path, sandbox="require")
        )
        # The sandboxed attempt fails (no network) -> no completed run, hence
        # unverifiable; the contrast to the confirmed unsandboxed run above is
        # the isolation proof.
        self.assertIs(sandboxed.verdict, Verdict.UNVERIFIABLE, sandboxed.output)
        self.assertIn("did not complete", sandboxed.reason)
        self.assertIn("bytes=0", sandboxed.output)
        self.assertIs(sandboxed.sandboxed, True)


if __name__ == "__main__":
    unittest.main()

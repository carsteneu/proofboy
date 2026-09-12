"""Tests for the [ARTIFACT: <pfad> -> <sha256>] claim type.

An ARTIFACT claim asserts that a file exists and that its content has the
claimed SHA-256. The path comes from an untrusted report, so the matrix below
pins the confinement: `..` components, absolute paths outside the root and
symlinks leaving the root stay UNVERIFIABLE, while a symlink that stays inside
is followed. Absence and a differing digest are findings (REFUTED); the file
is read once, hashed in chunks and never outside the root.
"""

import hashlib
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from bemyself import claimtypes
from bemyself.claimtypes import artifact
from bemyself.checks import Ctx, kind_needs_repo, run_claim
from bemyself.model import Claim, Verdict
from bemyself.report import parse_report

DIGEST = "a" * 64


def make_claim(kind, **fields):
    return Claim(kind, 1, "<fixture>", fields)


class ArtifactParseTest(unittest.TestCase):
    def test_marker_parses(self):
        claims = parse_report(f"[ARTIFACT: dist/app.bin -> {DIGEST}]\n")
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        self.assertEqual(claim.kind, "artifact")
        self.assertEqual(claim.fields["path"], "dist/app.bin")
        self.assertEqual(claim.fields["sha256"], DIGEST)

    def test_the_last_arrow_separates_path_and_digest(self):
        claims = parse_report(f"[ARTIFACT: a->b.bin -> {DIGEST}]\n")
        self.assertEqual(claims[0].fields["path"], "a->b.bin")
        self.assertEqual(claims[0].fields["sha256"], DIGEST)

    def test_unicode_arrow_parses(self):
        claims = parse_report(f"[ARTIFACT: app.bin \u2192 {DIGEST}]\n")
        self.assertEqual(claims[0].fields["path"], "app.bin")
        self.assertEqual(claims[0].fields["sha256"], DIGEST)

    def test_marker_without_arrow_is_no_claim(self):
        self.assertEqual(parse_report("[ARTIFACT: app.bin]\n"), [])

    def test_empty_fields_still_parse(self):
        claims = parse_report("[ARTIFACT: -> ]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["path"], "")
        self.assertEqual(claims[0].fields["sha256"], "")

    def test_absurdly_long_line_is_ignored(self):
        line = f"[ARTIFACT: app.bin -> {DIGEST}] " + "x" * 9000 + "\n"
        self.assertEqual(parse_report(line), [])

    def test_unterminated_marker_stays_linear(self):
        start = time.perf_counter()
        claims = parse_report("[ARTIFACT:" + " " * 2000 + "\n")
        elapsed = time.perf_counter() - start
        self.assertEqual(claims, [])
        self.assertLess(elapsed, 0.5, f"{elapsed:.3f}s for a hostile line")


class ArtifactRegistryTest(unittest.TestCase):
    def test_artifact_is_registered(self):
        self.assertIn(artifact.ARTIFACT, claimtypes.CLAIM_TYPES)
        self.assertEqual(artifact.ARTIFACT.kind, "artifact")
        self.assertIs(claimtypes.checker_for("artifact"), artifact.check)

    def test_the_type_declares_no_repository_need(self):
        # The root is configured (--artifact-root), not implied by the repo:
        # a report with only [ARTIFACT] runs without --repo.
        self.assertFalse(artifact.ARTIFACT.needs_repo)
        self.assertFalse(kind_needs_repo("artifact"))


class ArtifactCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "root")
        os.makedirs(os.path.join(self.root, "dist"))
        self.data = b"artifact payload\n" * 1000
        with open(os.path.join(self.root, "dist", "app.bin"), "wb") as handle:
            handle.write(self.data)
        self.digest = hashlib.sha256(self.data).hexdigest()

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self, ctx=None, **fields):
        if ctx is None:
            ctx = Ctx(repo=None, tmp_dir=None, artifact_root=self.root)
        return run_claim(make_claim("artifact", **fields), ctx)

    def test_matching_digest_confirms(self):
        result = self.run_check(path="dist/app.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.CONFIRMED)
        self.assertIn(f"bytes={len(self.data)}", result.output)

    def test_uppercase_digest_confirms(self):
        result = self.run_check(path="dist/app.bin", sha256=self.digest.upper())
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_backticks_around_the_fields_are_stripped(self):
        result = self.run_check(path="`dist/app.bin`", sha256=f"`{self.digest}`")
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_repo_is_the_default_root(self):
        result = self.run_check(
            ctx=Ctx(repo=self.root, tmp_dir=None),
            path="dist/app.bin",
            sha256=self.digest,
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_absolute_path_inside_the_root_confirms(self):
        result = self.run_check(
            path=os.path.join(self.root, "dist", "app.bin"), sha256=self.digest
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_wrong_digest_refutes_and_names_both_values(self):
        result = self.run_check(path="dist/app.bin", sha256="0" * 64)
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("0" * 64, result.reason)
        self.assertIn(self.digest, result.reason)

    def test_missing_file_refutes(self):
        result = self.run_check(path="dist/ghost.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.REFUTED)
        self.assertIn("dist/ghost.bin", result.reason)

    def test_a_directory_refutes(self):
        result = self.run_check(path="dist", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.REFUTED)

    def test_a_fifo_is_refuted_and_does_not_block(self):
        os.mkfifo(os.path.join(self.root, "pipe"))
        outcome = {}

        def run():
            outcome["result"] = self.run_check(path="pipe", sha256=self.digest)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(10)
        self.assertFalse(thread.is_alive(), "the check blocked on a named pipe")
        self.assertIs(outcome["result"].verdict, Verdict.REFUTED)

    def test_dotdot_component_is_refused(self):
        result = self.run_check(path="dist/../dist/app.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("escapes", result.reason)

    def test_path_outside_the_root_is_unverifiable(self):
        outside = os.path.join(self._tmp.name, "outside.bin")
        with open(outside, "wb") as handle:
            handle.write(self.data)
        result = self.run_check(path="../outside.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("root", result.reason)

    def test_absolute_path_outside_the_root_is_unverifiable(self):
        outside = os.path.join(self._tmp.name, "outside.bin")
        with open(outside, "wb") as handle:
            handle.write(self.data)
        result = self.run_check(path=outside, sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_symlink_escaping_the_root_is_unverifiable(self):
        outside = os.path.join(self._tmp.name, "outside.bin")
        with open(outside, "wb") as handle:
            handle.write(self.data)
        os.symlink(outside, os.path.join(self.root, "escape.bin"))
        result = self.run_check(path="escape.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("outside", result.reason)

    def test_symlink_staying_inside_the_root_is_followed(self):
        os.symlink(
            os.path.join(self.root, "dist", "app.bin"), os.path.join(self.root, "alias.bin")
        )
        result = self.run_check(path="alias.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_filesystem_root_as_root_contains_every_path(self):
        # "/" is its own prefix; a root at the filesystem root is not
        # "everything is refused".
        result = self.run_check(
            ctx=Ctx(repo=None, tmp_dir=None, artifact_root=os.sep),
            path=os.path.join(self.root, "dist", "app.bin"),
            sha256=self.digest,
        )
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_missing_root_is_unverifiable(self):
        result = self.run_check(
            ctx=Ctx(repo=None, tmp_dir=None, artifact_root=os.path.join(self._tmp.name, "nope")),
            path="app.bin",
            sha256=self.digest,
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_without_any_root_is_unverifiable(self):
        result = self.run_check(
            ctx=Ctx(repo=None, tmp_dir=None), path="app.bin", sha256=self.digest
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("artifact root", result.reason)

    def test_file_beyond_the_size_limit_is_unverifiable(self):
        with mock.patch.object(artifact, "MAX_ARTIFACT_BYTES", len(self.data) - 1):
            result = self.run_check(path="dist/app.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("limit", result.reason)

    def test_a_file_at_the_size_limit_is_hashed(self):
        with mock.patch.object(artifact, "MAX_ARTIFACT_BYTES", len(self.data)):
            result = self.run_check(path="dist/app.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_the_digest_streams_in_chunks(self):
        other = os.path.join(self.root, "dist", "chunked.bin")
        with open(other, "wb") as handle:
            handle.write(self.data)
        with mock.patch.object(artifact, "_CHUNK", 7):
            result = self.run_check(path="dist/chunked.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.CONFIRMED)

    def test_bad_digest_format_is_unverifiable(self):
        result = self.run_check(path="dist/app.bin", sha256="zz-not-a-digest")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIn("sha256", result.reason)

    def test_missing_path_is_unverifiable(self):
        result = self.run_check(path="", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)

    def test_embedded_nul_is_unverifiable(self):
        result = self.run_check(path="dist/app\x00.bin", sha256=self.digest)
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)


if __name__ == "__main__":
    unittest.main()

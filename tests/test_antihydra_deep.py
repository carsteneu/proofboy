"""Tests for the Antihydra deep counter run (block divide and conquer)."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bemyself.experiments import antihydra_deep as deep  # noqa: E402

# OEIS A385902, a(0)..a(99): the counter values of the plain walk.
OEIS_A385902_PREFIX = [
    0, 2, 4, 6, 5, 7, 9, 11, 10, 12, 11, 13, 12, 11, 10, 12, 14, 16, 15, 14,
    16, 15, 17, 16, 18, 17, 19, 21, 20, 19, 21, 20, 19, 21, 23, 25, 24, 23,
    22, 21, 20, 22, 21, 20, 19, 18, 17, 19, 21, 23, 25, 27, 29, 31, 30, 29,
    31, 30, 32, 31, 33, 32, 31, 33, 35, 37, 36, 35, 37, 36, 35, 37, 39, 38,
    40, 39, 38, 40, 42, 44, 43, 42, 41, 43, 42, 44, 46, 48, 47, 46, 48, 47,
    49, 48, 47, 46, 48, 47, 49, 51, 53,
]


class BackendTest(unittest.TestCase):
    def test_python_backend_passes_its_self_check(self):
        ok, note = deep.backend_self_check(deep.PythonBackend())
        self.assertTrue(ok, note)

    def test_make_backend_auto_resolves(self):
        backend, note = deep.make_backend("auto")
        self.assertIn(backend.name, {"python", "gmp"})
        self.assertTrue(note)

    def test_gmp_backend_passes_its_self_check(self):
        try:
            backend = deep.GmpBackend()
        except OSError:
            self.skipTest("libgmp.so.10 not available")
        try:
            ok, note = deep.backend_self_check(backend)
            self.assertTrue(ok, note)
        finally:
            backend.close()


class DeepRunTest(unittest.TestCase):
    def test_matches_the_plain_recurrence(self):
        for depth in (1, 4, 8, 10):
            lines = deep.deep_lines(depth, deep.PythonBackend())
            reference = deep.brute_lines(depth)
            self.assertEqual(lines, reference, f"depth={depth}")

    def test_matches_the_plain_recurrence_for_several_base_blocks(self):
        for base in (0, 2, 4, 8):
            lines = deep.deep_lines(10, deep.PythonBackend(), base_dep=base)
            self.assertEqual(lines, deep.brute_lines(10), f"base={base}")

    def test_extra_checkpoints(self):
        extras = [200, 1000, 1024]
        lines = deep.deep_lines(10, deep.PythonBackend(), extra_targets=extras)
        self.assertEqual(lines, deep.brute_lines(10, extra_targets=extras))
        for target in extras:
            self.assertIn(f"steps={target} ", "\n".join(lines))

    def test_min_counter_is_zero_for_the_verified_prefix(self):
        lines = deep.deep_lines(12, deep.PythonBackend())
        self.assertIn("min_counter=0", lines)
        self.assertIn("total_steps=4096", lines)

    def test_brute_min_counter(self):
        self.assertEqual(deep.brute_min_counter(4096), 0)


class PrefixCheckTest(unittest.TestCase):
    def test_walk_matches_the_oeis_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b385902.txt"
            path.write_text(
                "".join(f"{n} {value}\n" for n, value in enumerate(OEIS_A385902_PREFIX)),
                encoding="utf-8",
            )
            self.assertEqual(deep.check_prefix(path), [])

    def test_walk_rejects_a_corrupted_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            rows = [f"{n} {value}\n" for n, value in enumerate(OEIS_A385902_PREFIX)]
            rows[7] = "7 999\n"
            path.write_text("".join(rows), encoding="utf-8")
            mismatches = deep.check_prefix(path)
            self.assertEqual(len(mismatches), 1)
            self.assertIn("n=7", mismatches[0])


class CliTest(unittest.TestCase):
    def test_main_prints_the_checkpoints(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = deep.main(["--depth", "8", "--backend", "python"])
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("steps=256 counter=140 deviation=12", text)
        self.assertIn("min_counter=0", text)
        self.assertIn("total_steps=256", text)

    def test_main_verifies_against_the_brute_force(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = deep.main(["--depth", "10", "--backend", "python", "--verify-brute", "10"])
        self.assertEqual(code, 0)
        self.assertIn("check.brute.depth=10", buffer.getvalue())
        self.assertIn("mismatches=none", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

"""P20 (C5): the stack detector -- a suggestion layer, never a verdict.

The detector reads only marker *file names* at the repository root and
derives command suggestions; it runs nothing and changes nothing. The
differential test pins the important half of that sentence: a check with
``--detect`` yields the same claims and the same exit code as one without.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from proofboy import stackdetect
from tests.fixtures import make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DetectUnitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def write(self, name, content=""):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    def test_an_empty_directory_detects_nothing(self):
        detection = stackdetect.detect(self.root)
        self.assertEqual(detection.stacks, ())
        self.assertIn("none", stackdetect.render(detection))

    def test_a_composer_project_detects_php_with_test_and_lint_suggestions(self):
        self.write("composer.json", "{}")
        detection = stackdetect.detect(self.root)
        self.assertEqual(detection.stacks, ("php",))
        self.assertIn("vendor/bin/phpunit", detection.commands)
        self.assertIn("composer test", detection.commands)
        self.assertIn("php -l", detection.lint_commands)
        self.assertIn("composer validate", detection.lint_commands)
        self.assertIn("bin/console lint:twig", detection.lint_commands)

    def test_a_phpunit_config_alone_detects_php(self):
        self.write("phpunit.xml.dist", "")
        self.assertEqual(stackdetect.detect(self.root).stacks, ("php",))

    def test_node_and_go_markers_both_count(self):
        self.write("package.json", "{}")
        self.write("go.mod", "module x\n")
        detection = stackdetect.detect(self.root)
        self.assertEqual(detection.stacks, ("node", "go"))
        self.assertIn("npm test", detection.commands)
        self.assertIn("go test", detection.commands)

    def test_python_markers_detect_python(self):
        self.write("pyproject.toml", "")
        self.write("pytest.ini", "")
        detection = stackdetect.detect(self.root)
        self.assertEqual(detection.stacks, ("python",))
        self.assertEqual(detection.commands, ("python3 -m pytest",))

    def test_a_makefile_suggests_make_targets(self):
        self.write("Makefile", "test:\n\t@true\n")
        self.assertEqual(stackdetect.detect(self.root).commands, ("make test", "make check"))

    def test_a_directory_with_a_marker_name_is_no_marker(self):
        os.mkdir(os.path.join(self.root, "composer.json"))
        self.assertEqual(stackdetect.detect(self.root).stacks, ())

    def test_a_manifest_symlink_is_counted_by_name_only(self):
        # A symlink to an existing file counts as present (the name is the
        # signal); its content is never read, so nothing it contains can
        # influence the detection.
        target = os.path.join(self.root, "elsewhere.json")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("not json at all {{")
        os.symlink(target, os.path.join(self.root, "composer.json"))
        detection = stackdetect.detect(self.root)
        self.assertEqual(detection.stacks, ("php",))

    def test_a_broken_symlink_is_not_a_marker(self):
        os.symlink(os.path.join(self.root, "missing"), os.path.join(self.root, "go.mod"))
        self.assertEqual(stackdetect.detect(self.root).stacks, ())


class DetectCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "fixture"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "proofboy", "check", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_detect_without_a_report_lists_the_stacks(self):
        with open(os.path.join(self.repo.path, "go.mod"), "w", encoding="utf-8") as handle:
            handle.write("module fixture\n")
        try:
            proc = self.invoke("--detect", "--repo", self.repo.path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("go", proc.stdout)
            self.assertIn("go test", proc.stdout)
        finally:
            os.unlink(os.path.join(self.repo.path, "go.mod"))

    def test_detect_without_a_repo_is_a_usage_error(self):
        proc = self.invoke("--detect")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repo", proc.stderr)

    def test_detect_changes_no_claim_and_no_exit_code(self):
        report = os.path.join(self._tmp.name, "report.md")
        with open(report, "w", encoding="utf-8") as handle:
            handle.write(
                "**send_to payload:** `[DONE] "
                f"[COMMIT: {self.repo['good']}] [MERGE: no]`\n"
                "Tests run: python3 -m unittest test_ok -> exit 0\n"
            )
        base = self.invoke("--report", report, "--repo", self.repo.path, "--json")
        with_detect = self.invoke(
            "--report", report, "--repo", self.repo.path, "--json", "--detect"
        )
        self.assertEqual(base.returncode, with_detect.returncode, with_detect.stderr)
        base_payload = json.loads(base.stdout)
        detect_payload = json.loads(with_detect.stdout)
        self.assertEqual(base_payload["claims"], detect_payload["claims"])
        self.assertNotIn("detected", base_payload)
        self.assertIn("detected", detect_payload)
        # The fixture repo carries a Makefile-less Python test file only, so
        # the detection honestly says "no marker".
        self.assertEqual(detect_payload["detected"]["stacks"], [])


if __name__ == "__main__":
    unittest.main()

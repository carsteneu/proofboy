"""P20: the ``[LINT: <command>]`` claim type.

No PHP on this host: the fixture repos carry the honest shims from
tests/data/shims/ (php -l, Symfony console lint:*, composer validate), which
emit the exact formats of the real tools. The tests pin the documented
verdicts: CONFIRMED only with the tool's own success line bound to the
checkout, REFUTED on a real failure, environment gaps and redirected runs
stay UNVERIFIABLE.
"""

import os
import shutil
import unittest
from unittest import mock

from bemyself.checks import run_claim
from bemyself.model import Cause, Claim, Verdict
from tests.fixtures import FixtureTestCase, _SHIMS, make_repo


def make_claim(kind, **fields):
    return Claim(kind, 1, "<lint>", fields)


class LintClaimTest(FixtureTestCase):
    def lint_repo(self, mode="ok", files=None):
        repo = make_repo(os.path.join(self._tmp.name, "lint-" + self._testMethodName))
        shutil.copytree(_SHIMS, repo.path, dirs_exist_ok=True)
        payload = {"fixture-mode.txt": mode + "\n"}
        payload.update(files or {})
        head = self.commit_files(repo, payload)
        return repo, head

    def run_lint(self, repo, head, command, **kw):
        return run_claim(
            make_claim("lint", command=command, commit=head),
            self.ctx(repo.path, **kw),
        )

    def php_path(self):
        return mock.patch.dict(
            os.environ, {"PATH": _SHIMS + os.pathsep + os.environ.get("PATH", "")}
        )

    # --- php -l -----------------------------------------------------------
    def test_php_l_confirms_with_the_named_file(self):
        repo, head = self.lint_repo(files={"src/app.php": "<?php echo 1;\n"})
        with self.php_path():
            result = self.run_lint(repo, head, "php -l src/app.php")
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("No syntax errors detected in src/app.php", self.evidence_text(result.reason))

    def test_php_l_refutes_a_broken_file(self):
        repo, head = self.lint_repo(files={"src/broken.php": "<?php SYNTAX-ERROR\n"})
        with self.php_path():
            result = self.run_lint(repo, head, "php -l src/broken.php")
        self.assertIs(result.verdict, Verdict.REFUTED, result.output)
        self.assertIn("Parse error", result.reason)

    def test_php_l_target_missing_from_the_commit_is_environment(self):
        repo, head = self.lint_repo(files={"src/app.php": "<?php echo 1;\n"})
        with self.php_path():
            result = self.run_lint(repo, head, "php -l src/never-committed.php")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.ENVIRONMENT)

    def test_php_l_is_bound_to_the_committed_file(self):
        repo, head = self.lint_repo(files={"src/app.php": "<?php echo 1;\n"})
        # The same claim against the earlier commit: the file is not there,
        # so the claim cannot be confirmed from this commit.
        with self.php_path():
            result = self.run_lint(repo, repo["base"], "php -l src/app.php")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.ENVIRONMENT)

    def test_php_l_success_line_naming_another_file_is_unverifiable(self):
        repo, head = self.lint_repo(
            mode="redirect", files={"src/app.php": "<?php echo 1;\n"}
        )
        with self.php_path():
            result = self.run_lint(repo, head, "php -l src/app.php")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.DEFECT)
        self.assertIn("other.php", result.reason)

    # --- Symfony console linters -----------------------------------------
    def test_lint_twig_confirms_with_the_file_count(self):
        repo, head = self.lint_repo(
            files={"templates/a.twig": "{{ a }}\n", "templates/b.twig": "{{ b }}\n"}
        )
        result = self.run_lint(repo, head, "bin/console lint:twig templates")
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("All 2 Twig files contain valid syntax", self.evidence_text(result.reason))

    def test_lint_twig_via_the_php_launcher_confirms(self):
        repo, head = self.lint_repo(files={"templates/a.twig": "{{ a }}\n"})
        with self.php_path():
            result = self.run_lint(repo, head, "php bin/console lint:twig templates")
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("All 1 Twig files contain valid syntax", self.evidence_text(result.reason))

    def test_lint_twig_reported_count_mismatch_is_unverifiable(self):
        repo, head = self.lint_repo(
            mode="misreport", files={"templates/a.twig": "{{ a }}\n"}
        )
        result = self.run_lint(repo, head, "bin/console lint:twig templates")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.DEFECT)
        self.assertIn("redirected", result.reason)

    def test_lint_twig_broken_template_refutes(self):
        repo, head = self.lint_repo(
            mode="failures", files={"templates/broken.twig": "{{ broken(\n"}
        )
        result = self.run_lint(repo, head, "bin/console lint:twig templates")
        self.assertIs(result.verdict, Verdict.REFUTED, result.output)

    def test_lint_yaml_counts_both_suffixes(self):
        repo, head = self.lint_repo(
            files={"config/a.yaml": "a: 1\n", "config/b.yml": "b: 2\n"}
        )
        result = self.run_lint(repo, head, "bin/console lint:yaml config")
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("All 2 YAML files contain valid syntax", self.evidence_text(result.reason))

    def test_lint_container_confirms(self):
        repo, head = self.lint_repo(files={"config/services.yaml": "services: {}\n"})
        result = self.run_lint(repo, head, "bin/console lint:container")
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("container was linted successfully", self.evidence_text(result.reason))

    def test_composer_validate_confirms(self):
        repo, head = self.lint_repo(files={"composer.json": '{"name": "x/y"}\n'})
        with self.php_path():
            result = self.run_lint(repo, head, "composer validate")
        self.assertIs(result.verdict, Verdict.CONFIRMED, result.output)
        self.assertIn("is valid", self.evidence_text(result.reason))

    # --- boundaries -------------------------------------------------------
    def test_a_command_outside_the_lint_allowlist_is_environment(self):
        repo, head = self.lint_repo()
        result = self.run_lint(repo, head, "php -r 'rm -rf /'")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.ENVIRONMENT)
        self.assertIn("allowlist", result.reason)

    def test_a_lint_command_cannot_use_the_test_allowlist(self):
        repo, head = self.lint_repo()
        result = self.run_lint(repo, head, "python3 -m unittest test_ok")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.ENVIRONMENT)

    def test_without_a_commit_the_claim_stays_unverifiable(self):
        repo, _head = self.lint_repo()
        result = run_claim(
            make_claim("lint", command="bin/console lint:container", commit=None),
            self.ctx(repo.path),
        )
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE)
        self.assertIs(result.cause, Cause.DEFECT)
        self.assertIn("no commit hash", result.reason)

    def test_exit_zero_without_a_success_line_is_not_confirmed(self):
        # A tool that exits 0 without its success line (aborted run) must not
        # confirm: exit 0 alone is not a lint result.
        repo, head = self.lint_repo(mode="silent", files={"src/app.php": "<?php echo 1;\n"})
        with self.php_path():
            result = self.run_lint(repo, head, "php -l src/app.php")
        self.assertIs(result.verdict, Verdict.UNVERIFIABLE, result.output)
        self.assertIs(result.cause, Cause.UNVERIFIABLE)
        self.assertIn("no success line", result.reason)


if __name__ == "__main__":
    unittest.main()

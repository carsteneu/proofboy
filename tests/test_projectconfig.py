"""P20: the project config (--project-config) and its provenance rules.

C3 of the extension model: knobs live in a JSON file, but the provenance is
one-way (explicit CLI flag > config entry > built-in default), the source of
a check is never configurable, and a config typo is a hard usage error
instead of silently changing nothing.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from proofboy import projectconfig
from proofboy.cli import _apply_project_config
from tests.fixtures import make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_args(**overrides):
    args = argparse.Namespace(
        project_config=None,
        allow=[],
        profile=None,
        sandbox=None,
        tools=None,
        tmp=None,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


class ProjectConfigLoadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write(self, payload, name="config.json"):
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload if isinstance(payload, str) else json.dumps(payload))
        return path

    def test_a_full_config_loads(self):
        path = self.write(
            {
                "allow": ["node --test"],
                "profile": "yesloop-done",
                "sandbox": "require",
                "tools": "tools.toml",
                "tmp": ".yesmem/tmp",
            }
        )
        config = projectconfig.load(path)
        self.assertEqual(config["allow"], ["node --test"])
        self.assertEqual(config["profile"], "yesloop-done")
        self.assertEqual(config["sandbox"], "require")
        self.assertEqual(config["tools"], "tools.toml")
        self.assertEqual(config["tmp"], ".yesmem/tmp")

    def test_an_empty_config_loads(self):
        self.assertEqual(projectconfig.load(self.write({})), {})

    def test_unknown_keys_are_an_error(self):
        with self.assertRaises(projectconfig.ProjectConfigError) as ctx:
            projectconfig.load(self.write({"profiles": "typo"}))
        self.assertIn("profiles", str(ctx.exception))

    def test_a_non_object_is_an_error(self):
        with self.assertRaises(projectconfig.ProjectConfigError):
            projectconfig.load(self.write([1, 2]))

    def test_broken_json_is_an_error(self):
        with self.assertRaises(projectconfig.ProjectConfigError):
            projectconfig.load(self.write("{not json"))

    def test_a_missing_file_is_an_error(self):
        with self.assertRaises(projectconfig.ProjectConfigError):
            projectconfig.load(os.path.join(self._tmp.name, "nope.json"))

    def test_invalid_allow_entries_are_an_error(self):
        for value in ([1], [""], "node", {"a": 1}):
            with self.subTest(value=value):
                with self.assertRaises(projectconfig.ProjectConfigError):
                    projectconfig.load(self.write({"allow": value}))

    def test_an_unknown_sandbox_mode_is_an_error(self):
        with self.assertRaises(projectconfig.ProjectConfigError):
            projectconfig.load(self.write({"sandbox": "Require"}))

    def test_an_unknown_profile_is_an_error(self):
        with self.assertRaises(projectconfig.ProjectConfigError):
            projectconfig.load(self.write({"profile": "does-not-exist"}))

    def test_empty_paths_are_an_error(self):
        for key in ("tools", "tmp"):
            with self.subTest(key=key):
                with self.assertRaises(projectconfig.ProjectConfigError):
                    projectconfig.load(self.write({key: "  "}))


class ProjectConfigMergeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.parser = argparse.ArgumentParser(prog="proofboy check")

    def write(self, payload):
        path = os.path.join(self._tmp.name, "config.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
        return path

    def test_without_a_config_the_defaults_are_applied(self):
        args = base_args()
        _apply_project_config(self.parser, args)
        self.assertEqual(args.sandbox, "auto")
        self.assertIsNone(args.profile)
        self.assertEqual(args.allow, [])

    def test_config_entries_fill_the_unset_flags(self):
        args = base_args(
            project_config=self.write(
                {"allow": ["node --test"], "profile": "yesloop-done", "sandbox": "off"}
            )
        )
        _apply_project_config(self.parser, args)
        self.assertEqual(args.sandbox, "off")
        self.assertEqual(args.profile, "yesloop-done")
        self.assertEqual(args.allow, ["node --test"])

    def test_an_explicit_cli_flag_wins_over_the_config(self):
        args = base_args(
            project_config=self.write({"profile": "yesloop-done", "sandbox": "require"}),
            sandbox="off",
        )
        _apply_project_config(self.parser, args)
        # The explicit --sandbox=off wins; the unset profile comes from the
        # config.
        self.assertEqual(args.sandbox, "off")
        self.assertEqual(args.profile, "yesloop-done")

    def test_allow_entries_are_additive_config_first(self):
        args = base_args(
            project_config=self.write({"allow": ["node --test"]}),
            allow=["make check"],
        )
        _apply_project_config(self.parser, args)
        self.assertEqual(args.allow, ["node --test", "make check"])

    def test_an_invalid_config_is_a_usage_error(self):
        args = base_args(project_config=self.write({"frob": 1}))
        with self.assertRaises(SystemExit) as ctx:
            _apply_project_config(self.parser, args)
        self.assertEqual(ctx.exception.code, 2)


class ProjectConfigEndToEndTest(unittest.TestCase):
    """The config through the real CLI: it changes what the run may do."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(os.path.join(cls._tmp.name, "fixture"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def write(self, name, text):
        path = os.path.join(self._tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "proofboy", "check", "--repo", self.repo.path, *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_the_config_allowlist_opens_the_command_for_the_run(self):
        command = 'python3 -c "print(\'Ran 1 test in 0.01s\')"'
        report = self.write(
            "report.md",
            "**send_to payload:** `[DONE] "
            f"[COMMIT: {self.repo['good']}] [MERGE: no]`\n"
            f"Tests run: {command} -> exit 0\n",
        )
        # Without the config the command is outside the allowlist: the claim
        # stays unverifiable -- that is the baseline the config changes.
        proc = self.invoke("--report", report, "--json")
        verdicts = {c["kind"]: c["verdict"] for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(verdicts["tests_green"], "UNVERIFIABLE")

        config = self.write("allow.json", json.dumps({"allow": ["python3 -c"]}))
        proc = self.invoke("--report", report, "--json", "--project-config", config)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        verdicts = {c["kind"]: c["verdict"] for c in json.loads(proc.stdout)["claims"]}
        self.assertEqual(verdicts["tests_green"], "CONFIRMED")

    def test_the_config_profile_enforces_its_required_classes(self):
        report = self.write(
            "report-min.md",
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n",
        )
        # Without a profile the commit alone may be confirmed...
        proc = self.invoke("--report", report, "--json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # ...with the yesloop-done profile the missing branch/test run is a
        # defect (exit 5), whether the profile comes from the CLI or the
        # config: the knobs are the same, only the spelling differs.
        config = self.write("profile.json", json.dumps({"profile": "yesloop-done"}))
        proc = self.invoke("--report", report, "--json", "--project-config", config)
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)
        proc = self.invoke("--report", report, "--json", "--profile", "yesloop-done")
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)

    def test_an_invalid_config_stops_the_run_with_a_usage_error(self):
        report = self.write(
            "report-bad.md",
            f"**send_to payload:** `[COMMIT: {self.repo['good']}]`\n",
        )
        config = self.write("bad.json", "{broken")
        proc = self.invoke("--report", report, "--json", "--project-config", config)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not valid JSON", proc.stderr)


if __name__ == "__main__":
    unittest.main()

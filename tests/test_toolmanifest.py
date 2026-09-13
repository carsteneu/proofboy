"""Tests for the ``--tools`` manifest: the host pins what a check may run.

A manifest is a TOML file with one ``[tool.<name>]`` table per tool. It pins
the path (absolute, required), the version and the sha256 content digest; a
pinned tool always wins over a repository's own toolchain request, and a tool
the manifest does not name is not run at all.
"""

import hashlib
import os
import tempfile
import unittest

from bemyself import toolmanifest


class ToolManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.dir = os.path.join(self._tmp.name, self._testMethodName)
        os.makedirs(self.dir, exist_ok=True)

    def write(self, text, name="tools.toml"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def tool_file(self, content=b"#!/bin/sh\n", name="lean"):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def test_a_valid_manifest_is_read(self):
        path = self.write(
            "[tool.lean]\n"
            f'path = "{self.tool_file()}"\n'
            'version = "4.33.1"\n'
            'digest = "sha256:' + "a" * 64 + '"\n'
            "\n"
            "[tool.leanchecker]\n"
            f'path = "{self.tool_file(name="leanchecker")}"\n'
        )
        pins = toolmanifest.load(path)
        self.assertEqual(sorted(pins), ["lean", "leanchecker"])
        self.assertEqual(pins["lean"].version, "4.33.1")
        self.assertEqual(pins["lean"].digest, "sha256:" + "a" * 64)
        self.assertIsNone(pins["leanchecker"].version)
        self.assertIsNone(pins["leanchecker"].digest)

    def test_an_unknown_tool_name_is_rejected(self):
        path = self.write(
            "[tool.leancheker]\n" f'path = "{self.tool_file()}"\n'
        )
        with self.assertRaises(toolmanifest.ToolManifestError) as caught:
            toolmanifest.load(path)
        self.assertIn("leancheker", str(caught.exception))

    def test_an_unknown_key_is_rejected(self):
        path = self.write(
            "[tool.lean]\n"
            f'path = "{self.tool_file()}"\n'
            'sha256 = "' + "a" * 64 + '"\n'
        )
        with self.assertRaises(toolmanifest.ToolManifestError) as caught:
            toolmanifest.load(path)
        self.assertIn("sha256", str(caught.exception))

    def test_a_relative_path_is_rejected(self):
        path = self.write('[tool.lean]\npath = "bin/lean"\n')
        with self.assertRaises(toolmanifest.ToolManifestError) as caught:
            toolmanifest.load(path)
        self.assertIn("absolute", str(caught.exception))

    def test_a_tool_entry_without_a_path_is_rejected(self):
        path = self.write('[tool.lean]\nversion = "4.33.1"\n')
        with self.assertRaises(toolmanifest.ToolManifestError) as caught:
            toolmanifest.load(path)
        self.assertIn("path", str(caught.exception))

    def test_a_digest_without_the_sha256_prefix_is_rejected(self):
        path = self.write(
            "[tool.lean]\n"
            f'path = "{self.tool_file()}"\n'
            f'digest = "{"a" * 64}"\n'
        )
        with self.assertRaises(toolmanifest.ToolManifestError) as caught:
            toolmanifest.load(path)
        self.assertIn("digest", str(caught.exception))

    def test_a_truncated_digest_is_rejected(self):
        path = self.write(
            "[tool.lean]\n"
            f'path = "{self.tool_file()}"\n'
            'digest = "sha256:abcd"\n'
        )
        with self.assertRaises(toolmanifest.ToolManifestError):
            toolmanifest.load(path)

    def test_a_non_toml_file_is_rejected(self):
        path = self.write("this is not a manifest\n")
        with self.assertRaises(toolmanifest.ToolManifestError):
            toolmanifest.load(path)

    def test_a_missing_file_is_rejected(self):
        with self.assertRaises(toolmanifest.ToolManifestError) as caught:
            toolmanifest.load(os.path.join(self.dir, "no-such.toml"))
        self.assertIn("no-such.toml", str(caught.exception))

    def test_a_tool_section_that_is_no_table_is_rejected(self):
        path = self.write('tool = "lean"\n')
        with self.assertRaises(toolmanifest.ToolManifestError):
            toolmanifest.load(path)


class ToolDigestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_digest_is_the_sha256_of_the_content(self):
        path = os.path.join(self._tmp.name, "tool")
        with open(path, "wb") as handle:
            handle.write(b"the content of a tool\n")
        expected = hashlib.sha256(b"the content of a tool\n").hexdigest()
        self.assertEqual(toolmanifest.digest_file(path), "sha256:" + expected)

    def test_the_short_form_is_the_first_twelve_hex(self):
        digest = "sha256:" + "0123456789ab" + "c" * 50
        self.assertEqual(toolmanifest.short_digest(digest), "0123456789ab")

    def test_a_missing_file_raises(self):
        with self.assertRaises(OSError):
            toolmanifest.digest_file(os.path.join(self._tmp.name, "gone"))


if __name__ == "__main__":
    unittest.main()

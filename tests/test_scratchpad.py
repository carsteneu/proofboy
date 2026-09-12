"""Tests for the read-only scratchpad section reader.

The tests build throwaway databases with the live schema; they never touch
``~/.claude/yesmem/yesmem.db`` itself.
"""

import os
import sqlite3
import tempfile
import unittest

from bemyself.scratchpad import ScratchpadError, default_db_path, read_section

SCHEMA = """
CREATE TABLE scratchpad_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project    TEXT NOT NULL,
    section    TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    owner      TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project, section)
);
"""


def make_db(path, rows):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    for project, section, content in rows:
        con.execute(
            "INSERT INTO scratchpad_entries (project, section, content) VALUES (?, ?, ?)",
            (project, section, content),
        )
    con.commit()
    con.close()
    return path


class ReadSectionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def db_path(self, name="scratchpad.db"):
        return os.path.join(self._tmp.name, name)

    def build(self, rows):
        return make_db(self.db_path(), rows)

    def test_known_section_is_returned(self):
        db = self.build([("/proj", "report", "hello\nworld")])
        self.assertEqual(read_section(db, "/proj", "report"), "hello\nworld")

    def test_empty_section_is_returned_as_empty_string(self):
        db = self.build([("/proj", "empty", "")])
        self.assertEqual(read_section(db, "/proj", "empty"), "")

    def test_unknown_section_returns_none(self):
        db = self.build([("/proj", "known", "x")])
        self.assertIsNone(read_section(db, "/proj", "missing"))

    def test_section_is_scoped_to_the_project(self):
        db = self.build([("/proj", "report", "x"), ("/other", "report", "y")])
        self.assertEqual(read_section(db, "/other", "report"), "y")

    def test_section_names_are_case_sensitive(self):
        db = self.build([("/proj", "Report", "x")])
        self.assertIsNone(read_section(db, "/proj", "report"))

    def test_missing_database_raises(self):
        with self.assertRaises(ScratchpadError):
            read_section(self.db_path("nope.db"), "/proj", "report")

    def test_database_without_the_table_raises(self):
        path = self.db_path("other.db")
        sqlite3.connect(path).close()
        with self.assertRaises(ScratchpadError):
            read_section(path, "/proj", "report")

    def test_reading_does_not_write(self):
        db = self.build([("/proj", "report", "x")])
        before = os.stat(db).st_mtime_ns
        os.chmod(db, 0o444)  # a write would need the write bit back
        self.addCleanup(os.chmod, db, 0o644)
        self.assertEqual(read_section(db, "/proj", "report"), "x")
        self.assertEqual(os.stat(db).st_mtime_ns, before)

    def test_default_db_path_is_the_yesmem_database(self):
        self.assertEqual(
            default_db_path(),
            os.path.expanduser(os.path.join("~", ".claude", "yesmem", "yesmem.db")),
        )


if __name__ == "__main__":
    unittest.main()

"""Read a message from a YesMem scratchpad section, read-only.

The live database is opened through a SQLite URI with ``mode=ro``: the
verifier reads the section text and must never modify the database. An
unknown section is not an error at this level -- it is ``None``, so the CLI
can decide the exit code.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = "~/.claude/yesmem/yesmem.db"


class ScratchpadError(Exception):
    """The scratchpad database could not be read."""


def default_db_path():
    """The default location of the YesMem database."""
    return os.path.expanduser(DEFAULT_DB)


def read_section(db_path, project, section):
    """Return the section text, or None when (project, section) is unknown.

    Raises :class:`ScratchpadError` when the database cannot be opened or
    queried; a stored empty section is an empty string, not an error.
    """
    path = os.path.abspath(os.path.expanduser(db_path))
    # The URI form is what carries mode=ro; as_uri also escapes characters
    # that would otherwise break the URI query (spaces, ?, #).
    uri = Path(path).as_uri() + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise ScratchpadError(f"cannot open database {path}: {exc}") from None
    try:
        try:
            row = con.execute(
                "SELECT content FROM scratchpad_entries WHERE project = ? AND section = ?",
                (project, section),
            ).fetchone()
        except sqlite3.Error as exc:
            raise ScratchpadError(f"cannot read database {path}: {exc}") from None
    finally:
        con.close()
    if row is None:
        return None
    return row[0]

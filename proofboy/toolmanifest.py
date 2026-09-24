"""The ``--tools`` manifest: host-side pins for the tools a check may run.

A manifest is a TOML file with one ``[tool.<name>]`` table per pinned tool
(``lean``, ``leanchecker``, ``lake``). ``path`` is required and must be
absolute; ``version`` and ``digest`` are optional and, when present, are
enforced before a tool runs -- ``digest`` is the sha256 of the file's content
in the form ``sha256:<64 lowercase hex>``.

The manifest is host-side authority: an entry always wins over a repository's
own toolchain request, and a manifest that does not name a required tool
leaves the claim unverifiable instead of falling back to ``PATH``. Unknown
tool names or fields are load errors, not silently ignored pins.
"""

from __future__ import annotations

import hashlib
import os
import re
import tomllib
from dataclasses import dataclass

# The tools the [LEAN] checker runs; a manifest may pin any subset of them.
TOOL_NAMES = ("lean", "leanchecker", "lake")
_FIELDS = ("path", "version", "digest")
_DIGEST_RE = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
DIGEST_PREFIX = "sha256:"


class ToolManifestError(ValueError):
    """A manifest that cannot be trusted is refused, not repaired."""


@dataclass(frozen=True)
class ToolPin:
    """One pinned tool: where it lives, and what it must be."""

    name: str
    path: str
    version: str | None = None
    digest: str | None = None


def digest_file(path):
    """The content digest of a file as ``sha256:<hex>``."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return DIGEST_PREFIX + digest.hexdigest()


def short_digest(digest):
    """The digest short form named in verdicts: the first twelve hex digits."""
    return digest.split(":", 1)[-1][:12]


def load(path):
    """Read a tool manifest; raises :class:`ToolManifestError` on any defect."""
    try:
        with open(path, "rb") as handle:
            document = tomllib.load(handle)
    except OSError as exc:
        raise ToolManifestError(f"cannot read the tool manifest {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ToolManifestError(f"the tool manifest {path} is no valid TOML: {exc}") from exc
    tools = document.get("tool")
    if not isinstance(tools, dict):
        raise ToolManifestError(f"the tool manifest {path} has no [tool.*] tables")
    pins = {}
    for name, entry in tools.items():
        if name not in TOOL_NAMES:
            raise ToolManifestError(
                f"unknown tool {name!r} in {path}; the known tools are "
                f"{', '.join(TOOL_NAMES)}"
            )
        if not isinstance(entry, dict):
            raise ToolManifestError(f"[tool.{name}] in {path} is not a table")
        unknown = sorted(set(entry) - set(_FIELDS))
        if unknown:
            raise ToolManifestError(
                f"[tool.{name}] in {path} has unknown fields: {', '.join(unknown)}; "
                f"the fields are {', '.join(_FIELDS)}"
            )
        value = entry.get("path")
        if not isinstance(value, str) or not value:
            raise ToolManifestError(f"[tool.{name}] in {path} needs a 'path'")
        if not os.path.isabs(value):
            raise ToolManifestError(
                f"[tool.{name}].path in {path} must be an absolute path: {value!r}"
            )
        version = entry.get("version")
        if version is not None and (not isinstance(version, str) or not version):
            raise ToolManifestError(
                f"[tool.{name}].version in {path} must be a non-empty string"
            )
        digest = entry.get("digest")
        if digest is not None and (
            not isinstance(digest, str) or _DIGEST_RE.match(digest) is None
        ):
            raise ToolManifestError(
                f"[tool.{name}].digest in {path} must be 'sha256:<64 lowercase hex>': "
                f"{digest!r}"
            )
        pins[name] = ToolPin(name=name, path=value, version=version, digest=digest)
    if not pins:
        raise ToolManifestError(f"the tool manifest {path} pins no tool")
    return pins

"""Project configuration: one JSON file naming the check knobs.

The file names the same knobs the CLI has, so a project can carry its own
verifier setup instead of repeating flags in every call:

* ``allow``: extra command prefixes (a list of non-empty strings; the
  entries are added before the CLI's ``--allow`` entries)
* ``profile``: a report profile name (``proofboy check --profile``)
* ``sandbox``: one of the sandbox modes (``auto``, ``require``, ``off``)
* ``tools``: path to a TOML tool manifest (like ``--tools``)
* ``tmp``: directory for throwaway checkouts (like ``--tmp``)

Provenance is fixed and one-way: an explicit CLI flag wins over the config
entry, the config entry wins over the built-in default. The check's source
(``--report``/``--section``/``--repo``/``--db``) is deliberately NOT
configurable -- where a claim comes from is the caller's decision, never a
project file's.

Unknown keys, wrong types and invalid values are a hard error: a config typo
must not silently change nothing (the same reasoning as the strict report
parsing). The file is data, never code: no imports, no includes, nothing is
executed to read it.
"""

from __future__ import annotations

import json

from proofboy import checks, profiles

# The keys the file may carry; anything else is a typo, not a feature.
KEYS = ("allow", "profile", "sandbox", "tools", "tmp")


class ProjectConfigError(ValueError):
    """The config file is unreadable, malformed or names an invalid value."""


def load(path):
    """Read and validate a project config, returning a plain dict."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ProjectConfigError(f"cannot read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProjectConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectConfigError(f"{path} must contain a JSON object")
    unknown = sorted(set(data) - set(KEYS))
    if unknown:
        raise ProjectConfigError(
            f"{path} names unknown key(s): {', '.join(unknown)} "
            f"(known: {', '.join(KEYS)})"
        )
    result = {}
    if "allow" in data:
        value = data["allow"]
        if not isinstance(value, list) or not all(
            isinstance(entry, str) and entry.strip() for entry in value
        ):
            raise ProjectConfigError(
                f"{path}: 'allow' must be a list of non-empty command prefixes"
            )
        result["allow"] = list(value)
    if "profile" in data:
        value = data["profile"]
        if not isinstance(value, str) or value not in profiles.profile_names():
            raise ProjectConfigError(
                f"{path}: 'profile' must be one of: {', '.join(profiles.profile_names())}"
            )
        result["profile"] = value
    if "sandbox" in data:
        value = data["sandbox"]
        if value not in checks.SANDBOX_MODES:
            raise ProjectConfigError(
                f"{path}: 'sandbox' must be one of: {', '.join(checks.SANDBOX_MODES)}"
            )
        result["sandbox"] = value
    if "tools" in data:
        value = data["tools"]
        if not isinstance(value, str) or not value.strip():
            raise ProjectConfigError(f"{path}: 'tools' must be a path")
        result["tools"] = value
    if "tmp" in data:
        value = data["tmp"]
        if not isinstance(value, str) or not value.strip():
            raise ProjectConfigError(f"{path}: 'tmp' must be a path")
        result["tmp"] = value
    return result

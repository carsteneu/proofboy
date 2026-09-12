"""Core data types for the claim verifier."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from bemyself.checks import Ctx


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class Claim:
    """A single verifiable assertion extracted from a report."""

    kind: str
    line: int
    raw: str
    fields: dict


@dataclass
class Result:
    """The outcome of running one claim against the world."""

    verdict: Verdict
    command: str = ""
    output: str = ""
    reason: str = ""
    # Whether a test command ran inside the sandbox: True/False for executed
    # runs, None when no command was executed. Machine-readable counterpart of
    # the note in ``reason``, which is display text and echo of report input.
    sandboxed: bool | None = None


@dataclass(frozen=True)
class ClaimType:
    """One optional claim kind: where to find it in a report line, and how to
    check it.

    ``pattern`` matches the claim's markers inside one line, ``parse`` turns
    one match into the claim's fields (or None to skip it), and ``check``
    re-derives the claim against the world. ``needs_repo`` declares whether
    that check reads a git repository (:func:`bemyself.checks.kind_needs_repo`
    resolves it) and ``binds_commit`` whether the report parser binds the
    claim to the report's single commit. Adding a kind is a new module under
    :mod:`bemyself.claimtypes` plus one entry in its ``CLAIM_TYPES``; the
    report parser and the CLI stay untouched.
    """

    kind: str
    pattern: re.Pattern[str]
    parse: Callable[[re.Match[str], str], dict | None]
    check: Callable[[Claim, "Ctx"], Result]
    # The CLI requires --repo for a report only while some occurring kind
    # declares this.
    needs_repo: bool = False
    # The report parser binds a claim of this kind to the report's single
    # commit when it has one (like the built-in tests_green and branch_pushed
    # claims).
    binds_commit: bool = False

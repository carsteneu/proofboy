"""Core data types for the claim verifier."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from proofboy.checks import Ctx


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    UNVERIFIABLE = "UNVERIFIABLE"


class Cause(str, Enum):
    """Why a claim did not end CONFIRMED: the machine-readable class.

    ``DEFECT`` is a form violation: the claim cannot be bound or executed as
    written -- in the report (a coloring that uses more colors than it
    declares, a missing commit hash, a malformed binding, an embedded NUL) or
    in the checked thing itself (a value that is present but lacks the
    required form, like a path-like ``lean-toolchain`` request). Absence is
    not a defect: payload the tool simply cannot interpret -- a prose number,
    a machine outside the notation, an unsound but internally consistent
    certificate -- keeps the claim ``UNVERIFIABLE``, and a missing capability
    stays ``ENVIRONMENT`` (no remote, no sandbox, no tool). ``LIMIT`` is a
    budget that was exhausted before the claim could be checked.
    ``UNVERIFIABLE`` is the residual: the check was attempted and could not
    decide.
    """

    DEFECT = "defect"
    ENVIRONMENT = "environment"
    LIMIT = "limit"
    UNVERIFIABLE = "unverifiable"


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
    # Why the claim did not end CONFIRMED: exactly one class per unconfirmed
    # claim, None for CONFIRMED and REFUTED. The residual class is the default
    # so every UNVERIFIABLE result carries a class without each caller having
    # to name one.
    cause: Cause | None = None

    def __post_init__(self):
        if self.verdict is Verdict.UNVERIFIABLE and self.cause is None:
            self.cause = Cause.UNVERIFIABLE


@dataclass(frozen=True)
class ClaimType:
    """One optional claim kind: where to find it in a report line, and how to
    check it.

    ``pattern`` matches the claim's markers inside one line, ``parse`` turns
    one match into the claim's fields (or None to skip it), and ``check``
    re-derives the claim against the world. ``needs_repo`` declares whether
    that check reads a git repository (:func:`proofboy.checks.kind_needs_repo`
    resolves it) and ``binds_commit`` whether the report parser binds the
    claim to the report's single commit. Adding a kind is a new module under
    :mod:`proofboy.claimtypes` plus one entry in its ``CLAIM_TYPES``; the
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
    # The marker tokens this type claims in a report line. Empty means the
    # upper-cased kind, the convention every built-in type follows; a type
    # whose second marker rides along in ``parse`` (halt claims ``SCORE``)
    # declares both. A marker token no registered type claims is a defect:
    # silently ignoring it would let a report smuggle an unknown claim shape
    # past the verifier.
    markers: tuple[str, ...] = ()

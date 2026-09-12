"""Registry of the optional claim types.

A claim type is one module in this package plus one entry in
:data:`CLAIM_TYPES`: ``pattern`` finds its markers in a report line, ``parse``
turns one match into the claim's fields, ``check`` re-derives the claim
against the world, and ``needs_repo`` declares whether that check reads a git
repository. The report parser (:mod:`bemyself.report`) and the checker
dispatcher (:func:`bemyself.checks.run_claim`) both consult this registry, so
a new type needs no change to either -- see README, "Neuen Behauptungstyp
hinzufuegen".
"""

from __future__ import annotations

from typing import Callable

from bemyself.claimtypes import halt
from bemyself.model import ClaimType

CLAIM_TYPES: tuple[ClaimType, ...] = (halt.HALT,)


def _find(kind: str) -> ClaimType | None:
    for claim_type in CLAIM_TYPES:
        if claim_type.kind == kind:
            return claim_type
    return None


def checker_for(kind: str) -> Callable | None:
    """The checker of a registered optional claim kind, or None."""
    claim_type = _find(kind)
    return claim_type.check if claim_type is not None else None


def type_needs_repo(kind: str) -> bool:
    """Whether the registered optional claim kind declares a repo need."""
    claim_type = _find(kind)
    return claim_type is not None and claim_type.needs_repo

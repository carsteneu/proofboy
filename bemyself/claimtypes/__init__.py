"""Registry of the optional claim types.

A claim type is one module in this package plus one entry in
:data:`CLAIM_TYPES`: ``pattern`` finds its markers in a report line, ``parse``
turns one match into the claim's fields, ``check`` re-derives the claim
against the world. The report parser (:mod:`bemyself.report`) and the checker
dispatcher (:func:`bemyself.checks.run_claim`) both consult this registry, so
a new type needs no change to either -- see README, "Neuen Behauptungstyp
hinzufuegen".
"""

from __future__ import annotations

from typing import Callable

from bemyself.claimtypes import halt
from bemyself.model import ClaimType

CLAIM_TYPES: tuple[ClaimType, ...] = (halt.HALT,)


def checker_for(kind: str) -> Callable | None:
    """The checker of a registered optional claim kind, or None."""
    for claim_type in CLAIM_TYPES:
        if claim_type.kind == kind:
            return claim_type.check
    return None

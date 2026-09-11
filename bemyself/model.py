"""Core data types for the claim verifier."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

    @property
    def confirmed(self) -> bool:
        return self.verdict is Verdict.CONFIRMED

    @property
    def refuted(self) -> bool:
        return self.verdict is Verdict.REFUTED

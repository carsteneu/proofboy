"""Report profiles and the negative space of a run.

A profile declares which claim classes a report of its kind must contain: a
yesloop DONE report states a commit, a branch and a test run. A required
class the report does not yield is a defect -- the report is incomplete, not
the environment -- and fails in both modes (Exit 5). An empty or template
line yields no claim at all (P15), so a report that hides behind placeholders
loses its profile classes too: this is the hole the profile closes.

Every run reports its negative space: the classes it sought (the profile's
requirements), the classes it found (the report's claims, minus the findings
the verifier itself authors) and the classes it missed. Without a profile
nothing is sought -- "nothing found" and "nothing sought" stay
distinguishable instead of both reading as "no claims".
"""

from __future__ import annotations

from bemyself.model import Claim

PROFILE_YESLOOP_DONE = "yesloop-done"

# One requirement is a tuple of acceptable claim kinds: a report satisfies it
# when it yields at least one claim of any listed kind. The test run is the
# one requirement with two forms -- `Tests run: ... -> exit 0` is tests_green,
# a non-zero exit is tests_exit (an honest failure report still states a test
# run). The order is the declaration order of the profile.
PROFILES: dict[str, tuple[tuple[str, ...], ...]] = {
    PROFILE_YESLOOP_DONE: (
        ("commit_exists",),
        ("branch_pushed",),
        ("tests_green", "tests_exit"),
    ),
}

# The findings the verifier itself authors. They are not claims the report
# stated, so the negative space must not list them as found classes.
META_KINDS = frozenset({"profile", "unknown_marker"})


def profile_names() -> tuple[str, ...]:
    """The registered profile names, in declaration order."""
    return tuple(PROFILES)


def requirement_label(requirement: tuple[str, ...]) -> str:
    """How one requirement is written in output: its alternatives joined."""
    return "/".join(requirement)


def missing_requirements(claims, profile):
    """The profile's requirements no claim in ``claims`` satisfies."""
    kinds = {claim.kind for claim in claims}
    return tuple(
        requirement
        for requirement in PROFILES[profile]
        if not kinds.intersection(requirement)
    )


def profile_claims(claims, profile):
    """``claims`` plus one defect claim per violated profile.

    One claim per report, not per missing class: the defect is the incomplete
    report, and its reason names every class the profile required. ``None``
    (no profile asked for) and a complete report return the claims unchanged;
    an unknown profile name is a caller error (KeyError).
    """
    if profile is None:
        return claims
    missing = missing_requirements(claims, profile)
    if not missing:
        return claims
    return claims + [
        Claim(
            "profile",
            0,
            f"--profile {profile}",
            {"profile": profile, "missing": missing},
        )
    ]


def negative_space(results, profile=None):
    """The classes sought, found and missed by this run.

    ``results`` are the (claim, result) pairs the run judged. ``found`` names
    the report's claim kinds in the order they occur, without the meta kinds;
    ``sought`` and ``missing`` carry the profile's requirements as lists of
    acceptable kinds (empty without a profile).
    """
    found: list[str] = []
    for claim, _ in results:
        if claim.kind in META_KINDS or claim.kind in found:
            continue
        found.append(claim.kind)
    requirements = PROFILES[profile] if profile is not None else ()
    missing = tuple(
        requirement
        for requirement in requirements
        if not set(found).intersection(requirement)
    )
    return {
        "profile": profile,
        "sought": [list(requirement) for requirement in requirements],
        "found": found,
        "missing": [list(requirement) for requirement in missing],
    }


def render_negative_space(space) -> str:
    """One line: which classes were sought, found and missed."""

    def labels(requirements):
        return ", ".join(requirement_label(tuple(req)) for req in requirements) or "keine"

    sought = labels(space["sought"])
    if not space["sought"]:
        sought = "keine (ohne --profile)"
    return (
        f"negativraum: gesucht: {sought}; "
        f"gefunden: {', '.join(space['found']) or 'keine'}; "
        f"gefehlt: {labels(space['missing'])}"
    )

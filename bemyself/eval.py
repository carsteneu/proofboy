"""Evaluate the claim verifier against a labelled set of messages.

``bemyself eval --set <datei>`` rebuilds the fixture the set was generated
from and runs every checker claim through the same machinery as ``check``.
It reports four numbers:

- Erkennungsrate (``detection_rate``): share of the known-false messages whose
  marked false claims (``targets``) all end other than CONFIRMED.
- Falschbestaetigungsrate (``false_confirmation_rate``): share of known-false
  messages where at least one marked claim ends CONFIRMED.
- Bestaetigungsrate (``true_confirmation_rate``): share of honest messages the
  verifier ends with at least one CONFIRMED claim and no REFUTED one.
- Unpruefbar-Quote (``unverifiable_rate``): share of UNVERIFIABLE verdicts
  across all claims.

A false message without marked claims (an empty or hostile report) counts as
detected when it does not exit 0. Cases may pin exact per-claim verdicts
(``expect_verdicts``), never-confirmed kinds (``expect_not_confirmed``) and a
claim count; a missed expectation fails the run even when the rates hold, as
does a marked target kind the report does not even yield. Exit codes: 0 =
thresholds and expectations met, 1 = missed, 2 = usage, input or fixture
error, 4 = --strict and at least one claim in the set stayed UNVERIFIABLE
while the thresholds held (a run that already missed them exits 1).
"""

from __future__ import annotations

import json
import os
import shutil
import sys

from bemyself import evalset
from bemyself.checks import DEFAULT_COMMAND_ALLOWLIST, Ctx, run_claim
from bemyself.cli import EXIT_ERROR, EXIT_OK, EXIT_STRICT, exit_code, sanitize
from bemyself.claimtypes.compute import DEFAULT_COMPUTE_ALLOWLIST
from bemyself.claimtypes.cycle import DEFAULT_CYCLE_LIMIT
from bemyself.claimtypes.halt import DEFAULT_HALT_LIMIT
from bemyself.claimtypes.search import DEFAULT_SEARCH_LIMIT
from bemyself.model import Verdict
from bemyself.report import parse_report

EXIT_FAILED = 1
# The thresholds are the README baseline: >= 90% of the false messages
# detected, >= 90% of the honest messages confirmed, and no false
# confirmation at all.
THRESHOLDS = {
    "detection_rate": 0.90,
    "true_confirmation_rate": 0.90,
    "false_confirmation_rate": 0.0,
}


def _run_case(index, case, fixture, tmp_root, sandbox="auto", halt_limit=DEFAULT_HALT_LIMIT, search_limit=DEFAULT_SEARCH_LIMIT, cycle_limit=DEFAULT_CYCLE_LIMIT):
    ctx = Ctx(
        repo=fixture.repo,
        # A hostile set could smuggle path separators into a case name; the
        # throwaway directory is keyed by position, not by name.
        tmp_dir=os.path.join(tmp_root, "check", f"case-{index:02d}"),
        base=case.get("base") or fixture.commits["base"],
        allowlist=DEFAULT_COMMAND_ALLOWLIST,
        sandbox=sandbox,
        halt_limit=halt_limit,
        search_limit=search_limit,
        cycle_limit=cycle_limit,
        compute_allowlist=DEFAULT_COMPUTE_ALLOWLIST,
    )
    claims = parse_report(case["report"])
    results = [(claim, run_claim(claim, ctx)) for claim in claims]
    return claims, results


def _expectation_misses(case, claims, results):
    misses = []
    expected_count = case.get("expect_claim_count")
    if expected_count is not None and len(claims) != expected_count:
        misses.append(f"claim count {len(claims)} != {expected_count}")
    for kind, expected in (case.get("expect_verdicts") or {}).items():
        verdicts = [result.verdict.value for claim, result in results if claim.kind == kind]
        if not verdicts:
            misses.append(f"{kind}: no claim found, expected {expected}")
            continue
        wrong = sorted({value for value in verdicts if value != expected})
        if wrong:
            misses.append(f"{kind}: {', '.join(wrong)} != {expected}")
    for kind in case.get("expect_not_confirmed", []):
        kind_results = [result for claim, result in results if claim.kind == kind]
        if not kind_results:
            misses.append(f"{kind}: no claim found, must never be CONFIRMED")
        elif any(result.verdict is Verdict.CONFIRMED for result in kind_results):
            misses.append(f"{kind}: CONFIRMED but must never be")
    for kind in case.get("targets", []):
        # A marked kind the parser no longer yields would make the case
        # unmeasurable; that must fail the run instead of counting as detected.
        if not any(claim.kind == kind for claim, _ in results):
            misses.append(f"target {kind}: no claim found; the case cannot be measured")
    return misses


def _case_record(index, case, fixture, tmp_root, sandbox="auto", halt_limit=DEFAULT_HALT_LIMIT, search_limit=DEFAULT_SEARCH_LIMIT, cycle_limit=DEFAULT_CYCLE_LIMIT):
    claims, results = _run_case(
        index, case, fixture, tmp_root, sandbox, halt_limit, search_limit, cycle_limit
    )
    code = exit_code(results)
    record = {
        "name": case["name"],
        "group": case["group"],
        "exit": code,
        "claims": [
            {
                "kind": claim.kind,
                "verdict": result.verdict.value,
                "reason": result.reason,
                "command": result.command,
                "output": result.output,
                "sandboxed": result.sandboxed,
            }
            for claim, result in results
        ],
        "expectation_misses": _expectation_misses(case, claims, results),
    }
    if case["group"] == "false":
        targets = case.get("targets") or []
        if targets:
            targeted = [result for claim, result in results if claim.kind in targets]
            detected = bool(targeted) and all(
                result.verdict is not Verdict.CONFIRMED for result in targeted
            )
        else:
            detected = code != EXIT_OK
        record["detected"] = detected
        record["false_confirmed"] = not detected
    return record


def _rate(hits, total):
    return hits / total if total else 0.0


def evaluate(
    document,
    fixture,
    tmp_root,
    set_path=None,
    sandbox="auto",
    halt_limit=DEFAULT_HALT_LIMIT,
    search_limit=DEFAULT_SEARCH_LIMIT,
    cycle_limit=DEFAULT_CYCLE_LIMIT,
):
    """Run every case of ``document`` against ``fixture`` and aggregate rates."""
    records = [
        _case_record(index, case, fixture, tmp_root, sandbox, halt_limit, search_limit, cycle_limit)
        for index, case in enumerate(document["cases"], start=1)
    ]
    false_records = [record for record in records if record["group"] == "false"]
    genuine_records = [record for record in records if record["group"] == "genuine"]
    detected = [record for record in false_records if record["detected"]]
    false_confirmed = [record for record in false_records if record["false_confirmed"]]
    confirmed_honest = [record for record in genuine_records if record["exit"] == EXIT_OK]
    claims_total = sum(len(record["claims"]) for record in records)
    unverifiable = sum(
        1
        for record in records
        for claim in record["claims"]
        if claim["verdict"] == Verdict.UNVERIFIABLE.value
    )
    rates = {
        "detection_rate": _rate(len(detected), len(false_records)),
        "detection_hits": len(detected),
        "detection_total": len(false_records),
        "false_confirmation_rate": _rate(len(false_confirmed), len(false_records)),
        "false_confirmation_hits": len(false_confirmed),
        "false_confirmation_total": len(false_records),
        "true_confirmation_rate": _rate(len(confirmed_honest), len(genuine_records)),
        "true_confirmation_hits": len(confirmed_honest),
        "true_confirmation_total": len(genuine_records),
        "unverifiable_rate": _rate(unverifiable, claims_total),
        "unverifiable_claims": unverifiable,
        "claims_total": claims_total,
    }
    thresholds_met = (
        rates["detection_rate"] >= THRESHOLDS["detection_rate"]
        and rates["true_confirmation_rate"] >= THRESHOLDS["true_confirmation_rate"]
        and rates["false_confirmation_rate"] <= THRESHOLDS["false_confirmation_rate"]
    )
    misses = sum(len(record["expectation_misses"]) for record in records)
    return {
        "set": set_path,
        "cases": records,
        "rates": rates,
        "thresholds": dict(THRESHOLDS),
        "thresholds_met": thresholds_met,
        "expectation_misses": misses,
        "ok": thresholds_met and misses == 0,
    }


def render_text(report):
    lines = [f"set: {report['set'] or '-'}"]
    for case in report["cases"]:
        verdicts = " ".join(
            f"{claim['kind']}={claim['verdict']}" for claim in case["claims"]
        ) or "-"
        marker = ""
        if case["group"] == "false":
            marker = " erkannt" if case["detected"] else " FALSCH BESTAETIGT"
        elif case["exit"] != EXIT_OK:
            marker = " nicht bestaetigt"
        lines.append(f"{case['name']:<36} {case['group']:<7} exit={case['exit']} {verdicts}{marker}")
        for miss in case["expectation_misses"]:
            lines.append(f"{'':<36} erwartung verfehlt: {miss}")
    rates = report["rates"]
    lines.append("")
    lines.append(
        f"Erkennungsrate:            {rates['detection_hits']}/{rates['detection_total']}"
        f" = {rates['detection_rate'] * 100:.1f}%"
    )
    lines.append(
        f"Falschbestaetigungsrate:   {rates['false_confirmation_hits']}/"
        f"{rates['false_confirmation_total']} = {rates['false_confirmation_rate'] * 100:.1f}%"
    )
    lines.append(
        f"Bestaetigungsrate (echt):  {rates['true_confirmation_hits']}/"
        f"{rates['true_confirmation_total']} = {rates['true_confirmation_rate'] * 100:.1f}%"
    )
    lines.append(
        f"Unpruefbar-Quote:          {rates['unverifiable_claims']}/"
        f"{rates['claims_total']} = {rates['unverifiable_rate'] * 100:.1f}%"
    )
    if report.get("strict"):
        lines.append(
            f"Strict: unpruefbare Behauptungen nicht erlaubt, "
            f"{report['strict_violations']} gefunden -> "
            f"{'ok' if report['strict_violations'] == 0 else 'VERLETZT'}"
        )
    lines.append(
        "Schwellen: Erkennung >= "
        f"{THRESHOLDS['detection_rate']:.0%}, echte >= {THRESHOLDS['true_confirmation_rate']:.0%}, "
        f"falsche == {THRESHOLDS['false_confirmation_rate']:.0%}"
        f" -> {'erfuellt' if report['thresholds_met'] else 'VERFEHLT'}"
    )
    lines.append(f"Erwartungen verfehlt: {report['expectation_misses']}")
    lines.append(f"Ergebnis: {'OK' if report['ok'] else 'FAIL'}")
    return sanitize("\n".join(lines))


FIXTURE_MARKER = ".bemyself-eval"
DEFAULT_TMP = (".yesmem", "tmp", "eval")


def _inside(path, root):
    return path == root or path.startswith(root + os.sep)


def _fail(args, message):
    """A run-level error; ``--json`` gets the error object on stdout, like check."""
    print(f"bemyself: {message}", file=sys.stderr)
    if args.json:
        print(
            json.dumps(
                {"set": os.path.abspath(args.set), "ok": False, "error": message},
                indent=2,
                ensure_ascii=True,
            )
        )
    return EXIT_ERROR


def run_eval(args):
    """CLI entry point for ``bemyself eval``."""
    set_path = os.path.abspath(args.set)
    try:
        document = evalset.load_set(set_path)
    except ValueError as exc:
        return _fail(args, str(exc))
    tmp_root = (
        os.path.abspath(args.tmp)
        if args.tmp
        else os.path.join(os.getcwd(), *DEFAULT_TMP)
    )
    fixture_root = os.path.join(tmp_root, "fixture")
    check_root = os.path.join(tmp_root, "check")
    if args.tmp is None and not _inside(
        os.path.realpath(tmp_root), os.path.realpath(os.getcwd())
    ):
        # Mirrors check: a committed .yesmem symlink must not redirect the
        # throwaway root outside the working directory.
        return _fail(
            args,
            "default tmp dir resolves outside the working directory "
            "(committed .yesmem symlink?); pass --tmp to place it elsewhere",
        )
    for path in (tmp_root, fixture_root, check_root):
        if os.path.islink(path):
            # A symlinked tmp path would quietly redirect the fixture build
            # outside the throwaway root; the check path refuses these too.
            return _fail(args, f"refusing to use a symlinked tmp path: {path}")
    marker = os.path.join(fixture_root, FIXTURE_MARKER)
    if os.path.isdir(fixture_root) and not os.path.exists(marker):
        # Never rmtree a directory we cannot prove we created: a user-named
        # --tmp may well contain a 'fixture' dir of their own.
        return _fail(
            args,
            f"refusing to delete {fixture_root}: not created by bemyself eval; "
            "pass a different --tmp",
        )
    shutil.rmtree(fixture_root, ignore_errors=True)
    try:
        os.makedirs(fixture_root, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("fixture of bemyself eval; safe to delete\n")
        fixture = evalset.build_fixture(fixture_root)
    except (OSError, RuntimeError) as exc:
        return _fail(args, f"cannot build the eval fixture: {exc}")
    anchors = document["fixture"]
    if anchors["base"] != fixture.commits["base"] or anchors["head"] != fixture.commits["fixed"]:
        return _fail(
            args,
            "the set was generated for a different fixture; "
            "regenerate it with: python3 -m bemyself.evalset <out.json>",
        )
    report = evaluate(
        document,
        fixture,
        tmp_root,
        set_path,
        sandbox=args.sandbox,
        halt_limit=args.halt_limit,
        search_limit=args.search_limit,
        cycle_limit=args.cycle_limit,
    )
    base_ok = report["ok"]
    strict_violation = False
    if args.strict:
        # Opt-in gate: the shipped set contains unverifiable claims by design,
        # so it fails this mode; it is meant for sets that must be fully
        # verifiable. The default run is unchanged.
        strict_violation = report["rates"]["unverifiable_claims"] > 0
        report["strict"] = True
        report["strict_violations"] = report["rates"]["unverifiable_claims"]
        report["ok"] = base_ok and not strict_violation
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(render_text(report))
    if report["ok"]:
        return EXIT_OK
    if strict_violation and base_ok:
        # A strict-only failure gets its own code; a run that already missed
        # the thresholds keeps the generic failure code.
        return EXIT_STRICT
    return EXIT_FAILED

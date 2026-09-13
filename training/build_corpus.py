#!/usr/bin/env python3
"""Trainingskorpus v0 aus den abgeschlossenen Experiment-Laeufen bauen.

Quellen (nur lesend): die Laufverzeichnisse ``runs-v11/v12/v13-*`` unter
``.yesmem/tmp/``. Zwei Generationen von Layout:

* v11 (flach): ``<stamp>/<task>/<arm>-rep<n>/{prompt.md,parsed.json,raw.json}``
  ohne ``summary.json`` -- die Labels entstehen hier per Re-Evaluierung mit
  dem eingefrorenen Set und dem Repo-Evaluator
  (``yesdocs/deepseek-math-notation/tooling/harness.py``).
* v12/v13 (Rundenbaum): ``<tier>/<task>/<arm>-rep<n>/round<r>/...`` plus
  ``summary.json`` je Zelle -- die Labels (``solved``/``trigger``) sind dort
  maschinell vom Lauf geschrieben.

Ausgaben (jsonl, nach id sortiert, UTF-8):

* ``sft.jsonl``  -- (System-Legende + Task) -> verifiziertes Blatt verbatim,
  Arme B/C/D, je (Set-Version, Task, Arm) genau ein Datensatz; Wiederholungen
  derselben Zelle fallen weg, verschiedene Set-Versionen bleiben (sie tragen
  unterschiedliche Legenden).
* ``dpo.jsonl``  -- (prompt, chosen=verifiziert, rejected=nicht bestaetigt);
  Cross-Arm-Fallback wird in ``meta.notes`` ausgewiesen.
* ``rlvr.jsonl`` -- Task + Verifier-Kommando (``python3 -m bemyself.msheet
  run <sheet> --json``) + Erwartungswerte des verifizierten Blatts.
* ``think.jsonl``-- Task + Denkzone des verifizierten Blatts (das Material der
  Denk-Traces; Prosabegruendung nur als Laengen-Metadatum).
* ``splits.json``-- Zuordnung Task-Familie -> train/val/test (Seed dokumentiert).
* ``manifest.json`` -- sha256 je Datei, Zaehlungen, Quellen, Kommando.

Kein Netz, kein Schreiben in die Laufverzeichnisse. Die Familien-Zuordnung
haelt Set-Versionen derselben Aufgabe zusammen (``A-0007`` und ``A3-0007``
gehoeren zur Familie ``A:0007``), damit kein Task ueber Splits leckt.
"""

from __future__ import annotations

import argparse
import collections
import functools
import hashlib
import importlib.util
import json
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SETS_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"
TOOLING_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"
DEFAULT_ARMS = ("B", "C", "D")
SET_VERSION_BY_RUN = {"v11": "0.1", "v12": "0.2", "v13": "0.3"}
RATIOS = (0.70, 0.15, 0.15)
# Blaetter tragen modellgenerierte py:-Zeugen; ohne bwrap liefen sie ungecontaint.
# "require" laesst den Bau lieber scheitern (Runner: UNVERIFIABLE -> Blatt faellt
# aus SFT/DPO), statt still unsandboxed zu rechnen. --sandbox auto/off nur bewusst.
DEFAULT_SANDBOX = "require"

_TASK_RE = re.compile(r"\A(?P<tier>[A-Z]+)(?P<gen>\d*)-(?P<num>\d+)\Z")
_ARM_RE = re.compile(r"\A(?P<arm>[A-Za-z]+)-rep(?P<rep>\d+)\Z")
_RUN_VERSION_RE = re.compile(r"runs-v(\d+)")


@dataclass
class Round:
    index: int
    prompt_path: Path
    parsed_path: Path
    solved: bool | None
    trigger: str | None
    format_errors: int | None
    tokens: int | None


@dataclass
class ArmRun:
    version: str
    tier: str
    task_id: str
    arm: str
    rep: int
    run_dir: Path
    root: Path
    rounds: list[Round] = field(default_factory=list)
    solved: bool | None = None
    label_source: str = "unlabeled"


def _version_rank(version: str) -> int:
    digits = version[1:]
    return int(digits) if digits.isdigit() else 0


def task_family(task_id: str) -> str:
    match = _TASK_RE.match(task_id)
    if match is None:
        return task_id
    return f"{match.group('tier')}:{match.group('num')}"


def scan_runs(roots) -> list[ArmRun]:
    runs: list[ArmRun] = []
    for root in sorted(Path(item).resolve() for item in roots):
        match = _RUN_VERSION_RE.search(root.name)
        version = f"v{match.group(1)}" if match else root.name
        for arm_dir in sorted(path for path in root.rglob("*-rep*") if path.is_dir()):
            arm_match = _ARM_RE.match(arm_dir.name)
            if arm_match is None:
                continue
            task_id = arm_dir.parent.name
            if _TASK_RE.match(task_id) is None:
                continue
            run = _scan_arm(version, root, task_id, arm_dir, arm_match)
            if run is not None:
                runs.append(run)
    runs.sort(key=lambda run: (run.version, run.tier, run.task_id, run.arm, run.rep, str(run.run_dir)))
    return runs


def _scan_arm(version, root, task_id, arm_dir, arm_match) -> ArmRun | None:
    summary_path = arm_dir / "summary.json"
    flat = (arm_dir / "prompt.md").exists()
    rounds: list[Round] = []
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for row in summary.get("rounds", []):
            index = int(row.get("round", 0))
            directory = arm_dir if flat else arm_dir / f"round{index}"
            rounds.append(
                Round(
                    index=index,
                    prompt_path=directory / "prompt.md",
                    parsed_path=directory / "parsed.json",
                    solved=bool(row.get("solved")),
                    trigger=row.get("trigger"),
                    format_errors=row.get("format_errors"),
                    tokens=row.get("completion_tokens"),
                )
            )
        solved = bool(summary.get("final_solved"))
        tier = summary.get("tier") or task_id[0]
        label_source = "summary.json"
    else:
        directory = arm_dir / "round0" if (arm_dir / "round0").is_dir() else arm_dir
        if not (directory / "prompt.md").exists() and not (directory / "parsed.json").exists():
            return None
        rounds = [Round(0, directory / "prompt.md", directory / "parsed.json", None, None, None, None)]
        solved = None
        tier = _TASK_RE.match(task_id).group("tier")
        label_source = "unlabeled"
    return ArmRun(
        version=version,
        tier=tier,
        task_id=task_id,
        arm=arm_match.group("arm"),
        rep=int(arm_match.group("rep")),
        run_dir=arm_dir,
        root=root,
        rounds=rounds,
        solved=solved,
        label_source=label_source,
    )


def load_sets(sets_dir: Path | str = SETS_DIR) -> dict:
    """Alle Set-Versionen laden: version -> {tier: {task_id: task}, "sha256": {}}."""
    directory = Path(sets_dir)
    versions: dict[str, dict] = {}
    for version in sorted(set(SET_VERSION_BY_RUN.values())):
        entry: dict = {"sha256": {}}
        for tier, name in (("A", f"tier_a_v11-a-{version}.json"), ("B", f"tier_b_v11-b-{version}.json")):
            path = directory / name
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            payload = json.loads(text)
            entry[tier] = {task["id"]: task for task in payload["tasks"]}
            entry["sha256"][tier] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if len(entry) > 1:
            versions[version] = entry
    return versions


def task_for(run: ArmRun, sets: dict) -> dict | None:
    version = SET_VERSION_BY_RUN.get(run.version)
    if version is None or version not in sets:
        return None
    tier = run.task_id[0]
    return sets[version].get(tier, {}).get(run.task_id)


def read_answer(round_: Round) -> str | None:
    if not round_.parsed_path.exists():
        return None
    try:
        payload = json.loads(round_.parsed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    answer = payload.get("answer")
    return answer if isinstance(answer, str) and answer.strip() else None


def read_meta(round_: Round) -> dict:
    if not round_.parsed_path.exists():
        return {}
    try:
        payload = json.loads(round_.parsed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "reasoning_chars": payload.get("reasoning_chars")
        if payload.get("reasoning_chars") is not None
        else len(payload.get("reasoning") or ""),
        "finish_reason": payload.get("finish_reason"),
    }


def parse_prompt_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    name: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("# "):
            if name is not None:
                sections.append((name, "\n".join(buffer).strip("\n")))
            name = line[2:].strip()
            buffer = []
        else:
            buffer.append(line)
    if name is not None:
        sections.append((name, "\n".join(buffer).strip("\n")))
    return sections


def prompt_messages(prompt_path: Path) -> list[dict] | None:
    try:
        sections = parse_prompt_sections(prompt_path.read_text(encoding="utf-8"))
    except OSError:
        return None
    system = next((body for name, body in sections if name == "system"), None)
    user = next((body for name, body in sections if name == "user"), None)
    if system is None or user is None:
        return None
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def default_evaluator():
    spec = importlib.util.spec_from_file_location("bemyself_training_harness", TOOLING_DIR / "harness.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.evaluate_answer


def verify_runs(runs, *, evaluator, sets=None) -> dict:
    """Runs ohne summary.json (v11) per Re-Evaluierung labeln (nur lesend)."""
    sets = sets if sets is not None else load_sets()
    checked = solved = unresolved = 0
    for run in runs:
        if run.solved is not None:
            continue
        task = task_for(run, sets)
        answer = read_answer(run.rounds[0]) if run.rounds else None
        if task is None or answer is None:
            run.label_source = "unresolved"
            unresolved += 1
            continue
        fragment = evaluator(run.arm, task, answer)
        run.solved = bool(fragment.get("solved"))
        run.label_source = "reevaluation"
        checked += 1
        solved += bool(run.solved)
    return {"checked": checked, "solved": solved, "unresolved": unresolved}


def _source_meta(run: ArmRun) -> dict:
    try:
        relative = run.run_dir.relative_to(run.root)
    except ValueError:
        relative = run.run_dir
    return {
        "version": run.version,
        "set_version": SET_VERSION_BY_RUN.get(run.version),
        "root": run.root.name,
        "run": str(relative),
        "rep": run.rep,
        "label_source": run.label_source,
    }


def _pick_preferred(runs):
    """Je (task, arm) den Run der hoechsten Set-Version (bei Gleichstand rep 1)."""
    best: dict[tuple[str, str], ArmRun] = {}
    for run in runs:
        key = (run.task_id, run.arm)
        current = best.get(key)
        if current is None or (
            _version_rank(run.version), -run.rep
        ) > (
            _version_rank(current.version), -current.rep
        ):
            best[key] = run
    return best


def build_sft(runs, arms=DEFAULT_ARMS, splits: dict | None = None, stats: dict | None = None,
              sandbox: str = DEFAULT_SANDBOX) -> list[dict]:
    # Dedup je (Set-Version, Task, Arm): Wiederholungen derselben Zelle fallen
    # weg, verschiedene Set-Versionen bleiben -- sie tragen unterschiedliche
    # Legenden (v0.1 vs. v0.2), sind also verschiedene Beispiele derselben
    # Aufgabe, keine Duplikate. Zusaetzlich muss das Blatt selbst sauber sein
    # (keine widerlegten/unpruefbaren Behauptungen).
    records: dict[tuple[str, str, str], dict] = {}
    for run in runs:
        if run.arm not in arms or run.solved is not True:
            continue
        key = (run.version, run.task_id, run.arm)
        if key in records:
            continue
        solved_round = next((round_ for round_ in run.rounds if round_.solved), run.rounds[0])
        answer = read_answer(solved_round)
        messages = prompt_messages(run.rounds[0].prompt_path)
        if answer is None or messages is None:
            continue
        if not _clean_sheet(answer, sandbox):
            if stats is not None:
                stats["sft_dropped_unverified"] = stats.get("sft_dropped_unverified", 0) + 1
            continue
        verdicts = sheet_verdicts(answer, sandbox)
        records[key] = {
            "id": f"sft:{run.version}:{run.task_id}:{run.arm}",
            "task_key": task_family(run.task_id),
            "task_id": run.task_id,
            "tier": run.tier,
            "arm": run.arm,
            "split": (splits or {}).get(task_family(run.task_id)),
            "messages": messages + [{"role": "assistant", "content": answer}],
            "meta": {
                **_source_meta(run),
                "round": solved_round.index,
                "rounds_total": len(run.rounds),
                "tokens": solved_round.tokens,
                "format_errors": solved_round.format_errors,
                "sheet": {
                    "claims": len(verdicts["claims"]),
                    "confirmed": verdicts["confirmed"],
                    "refuted": verdicts["refuted"],
                    "unverifiable": verdicts["unverifiable"],
                    "sandbox": verdicts["sandbox"],
                    "sandboxed": verdicts["sandboxed"],
                },
            },
        }
    return sorted(records.values(), key=lambda record: record["id"])


def build_dpo(runs, arms=DEFAULT_ARMS, splits: dict | None = None, stats: dict | None = None,
              sandbox: str = DEFAULT_SANDBOX) -> list[dict]:
    verified = _pick_preferred([run for run in runs if run.arm in arms and run.solved is True])
    rejected: dict[tuple[str, str], tuple[ArmRun, Round]] = {}
    for run in runs:
        if run.arm not in arms:
            continue
        for round_ in run.rounds:
            # v11 traegt das Urteil auf Run-Ebene (round0 ohne Label) --
            # ein re-evaluierter ungeloester Lauf ist trotzdem ein Kandidat.
            rejected_here = round_.solved is False or (
                round_.solved is None and run.solved is False and round_.index == run.rounds[0].index
            )
            if not rejected_here:
                continue
            key = (run.task_id, run.arm)
            current = rejected.get(key)
            if current is None or (
                (_version_rank(run.version), -run.rep, -round_.index)
                > (_version_rank(current[0].version), -current[0].rep, -current[1].index)
            ):
                rejected[key] = (run, round_)
    records: list[dict] = []
    for (task_id, rejected_arm) in sorted(rejected):
        rejected_run, rejected_round = rejected[(task_id, rejected_arm)]
        chosen_run = verified.get((task_id, rejected_arm))
        notes: list[str] = []
        if chosen_run is None:
            candidates = sorted(
                (key for key in verified if key[0] == task_id),
                key=lambda key: (key[1] != rejected_arm, verified[key].version != rejected_run.version, key[1]),
            )
            if not candidates:
                continue
            chosen_run = verified[candidates[0]]
            notes.append(f"rejected_from_arm={rejected_arm}")
        if chosen_run.version != rejected_run.version:
            notes.append(f"rejected_from_version={rejected_run.version}")
        chosen_round = next((round_ for round_ in chosen_run.rounds if round_.solved), chosen_run.rounds[0])
        chosen = read_answer(chosen_round)
        rejected_answer = read_answer(rejected_round)
        messages = prompt_messages(chosen_run.rounds[0].prompt_path)
        if chosen is None or rejected_answer is None or messages is None:
            continue
        if not _clean_sheet(chosen, sandbox):
            if stats is not None:
                stats["dpo_dropped_unverified_chosen"] = (
                    stats.get("dpo_dropped_unverified_chosen", 0) + 1
                )
            continue
        records.append(
            {
                "id": f"dpo:{task_id}:{rejected_arm}",
                "task_key": task_family(task_id),
                "task_id": task_id,
                "tier": chosen_run.tier,
                "split": (splits or {}).get(task_family(task_id)),
                "messages": messages,
                "chosen": chosen,
                "rejected": rejected_answer,
                "meta": {
                    "chosen_arm": chosen_run.arm,
                    "rejected_arm": rejected_arm,
                    "chosen_round": chosen_round.index,
                    "rejected_round": rejected_round.index,
                    "chosen_source": _source_meta(chosen_run),
                    "rejected_source": _source_meta(rejected_run),
                    "notes": notes,
                },
            }
        )
    return sorted(records, key=lambda record: record["id"])


def thinking_zone(answer: str) -> list[str]:
    from bemyself.msheet.sheet import parse_sheet

    sheet = parse_sheet(answer)
    lines = answer.splitlines()
    numbers = sorted(
        {line.line for line in (*sheet.think, *sheet.statuses, *sheet.vlines)}
    )
    return [lines[number - 1] for number in numbers if 1 <= number <= len(lines)]



def _sandbox_state(flags) -> dict:
    """True/False nur bei py:-Zeugen; None = das Blatt hatte keine py:-Zeugen."""
    if any(flag is False for flag in flags):
        return {"unsandboxed": True, "sandboxed": False}
    if any(flag is True for flag in flags):
        return {"unsandboxed": False, "sandboxed": True}
    return {"unsandboxed": False, "sandboxed": None}


@functools.lru_cache(maxsize=None)
def sheet_verdicts(answer: str, sandbox: str = DEFAULT_SANDBOX) -> dict:
    """Die Verdikte des Blatts aus dem echten Runner (gecached je Antwort).

    ``unsandboxed`` wird mitgeliefert, damit ein stiller Verlust der bwrap-
    Sandbox sichtbar bleibt (bei ``sandbox="require"`` liefert der Runner
    stattdessen UNVERIFIABLE und das Blatt faellt aus SFT/DPO).
    """
    from bemyself.msheet.runner import run_sheet
    from bemyself.msheet.sheet import parse_sheet

    sheet = parse_sheet(answer)
    result = run_sheet(sheet, sandbox=sandbox, timeout=20.0)
    counter = collections.Counter(claim.verdict.value for claim in result.claim_results)
    flags = [
        item.sandboxed for item in (*result.v_results, *result.claim_results)
    ]
    return {
        "claims": [
            {"id": claim.cid, "verdict": claim.verdict.value} for claim in result.claim_results
        ],
        "confirmed": counter.get("CONFIRMED", 0),
        "refuted": counter.get("REFUTED", 0),
        "unverifiable": counter.get("UNVERIFIABLE", 0),
        "sandbox": sandbox,
        **_sandbox_state(flags),
    }


def _clean_sheet(answer: str, sandbox: str = DEFAULT_SANDBOX) -> bool:
    """Wahr, wenn das Blatt keine widerlegten/unpruefbaren Behauptungen traegt
    und (falls py:-Zeugen liefen) die Sandbox gegriffen hat.

    Ein Lauf kann auf Trace-Aufgaben ``solved`` sein (Checkpoint-Gleichheit),
    waehrend das Blatt selbst z.B. eine ``sim``-Zeuge ohne Maschinenbindung
    traegt. Solche Blaetter taugen nicht als SFT-Ziel (sie lehren eine
    unverifizierbare Form) -- sie bleiben aber als RLVR-/Think-Beleg erhalten.
    """
    try:
        verdicts = sheet_verdicts(answer, sandbox)
    except Exception:  # noqa: BLE001 -- ein nicht ausfuehrbares Blatt ist nie "sauber"
        return False
    return (
        verdicts["refuted"] == 0
        and verdicts["unverifiable"] == 0
        and not verdicts["unsandboxed"]
    )


def _dedup_cells(runs, arms):
    """Je (Set-Version, Task, Arm) der erste verifizierte Run (Wiederholungen fallen weg)."""
    seen: set[tuple[str, str, str]] = set()
    out: list[ArmRun] = []
    for run in runs:
        if run.arm not in arms or run.solved is not True:
            continue
        key = (run.version, run.task_id, run.arm)
        if key in seen:
            continue
        seen.add(key)
        out.append(run)
    return out


def build_rlvr(runs, arms=DEFAULT_ARMS, splits: dict | None = None, sets: dict | None = None,
               sandbox: str = DEFAULT_SANDBOX) -> list[dict]:
    gold_keys = ("tier_b_kind", "expected", "checkpoints_gold", "checkpoints_t", "machine",
                 "certificate", "certificate_given")
    records: list[dict] = []
    for run in _dedup_cells(runs, arms):
        solved_round = next((round_ for round_ in run.rounds if round_.solved), run.rounds[0])
        answer = read_answer(solved_round)
        messages = prompt_messages(run.rounds[0].prompt_path)
        if answer is None or messages is None:
            continue
        try:
            verdicts = sheet_verdicts(answer, sandbox)
        except Exception as exc:  # noqa: BLE001 -- ein kaputtes Blatt darf den Bau nicht killen
            verdicts = {"claims": [], "confirmed": 0, "refuted": 0, "unverifiable": 0,
                        "sandbox": sandbox, "unsandboxed": None, "sandboxed": None,
                        "error": f"{type(exc).__name__}: {exc}"}
        task = task_for(run, sets) if sets else None
        gold = {key: task[key] for key in gold_keys if task is not None and key in task}
        verifier: dict = {
            "command": ["python3", "-m", "bemyself.msheet", "run", "{sheet}", "--json"],
        }
        if gold.get("tier_b_kind") == "trace" and gold.get("checkpoints_gold"):
            # Trace-Aufgaben werden ueber ihre Konfigurationspunkte geprueft
            # (genau so hat der Original-Harness sie bewertet); ein
            # Behauptungsblock ist dort nicht verlangt.
            verifier["expect"] = {
                "checkpoints_all_matched": True,
                "checkpoints_total": len(gold["checkpoints_gold"]),
            }
            verifier["note"] = (
                "ohne Behauptungszone (v0.1-Format): Belohnung per Checkpoint-Abgleich "
                "in training/rlvr.py"
            )
        elif verdicts["claims"]:
            verifier["expect"] = {
                "all_claims_confirmed": True,
                "min_claims": max(1, len(verdicts["claims"])),
            }
        else:
            verifier["expect"] = {"all_claims_confirmed": True, "min_claims": 1}
        records.append(
            {
                "id": f"rlvr:{run.version}:{run.task_id}:{run.arm}",
                "task_key": task_family(run.task_id),
                "task_id": run.task_id,
                "tier": run.tier,
                "arm": run.arm,
                "split": (splits or {}).get(task_family(run.task_id)),
                "messages": messages,
                "verifier": verifier,
                "gold": gold,
                "reference": {
                    "claims": verdicts["claims"],
                    "fully_confirmed": verdicts["refuted"] == 0 and verdicts["unverifiable"] == 0,
                    "sandbox": verdicts["sandbox"],
                    "sandboxed": verdicts["sandboxed"],
                    "unsandboxed": verdicts["unsandboxed"],
                    "error": verdicts.get("error"),
                },
                "meta": {**_source_meta(run), "round": solved_round.index},
            }
        )
    return sorted(records, key=lambda record: record["id"])


def build_think(runs, arms=DEFAULT_ARMS, splits: dict | None = None) -> list[dict]:
    records: list[dict] = []
    for run in _dedup_cells(runs, arms):
        solved_round = next((round_ for round_ in run.rounds if round_.solved), run.rounds[0])
        answer = read_answer(solved_round)
        messages = prompt_messages(run.rounds[0].prompt_path)
        if answer is None or messages is None:
            continue
        records.append(
            {
                "id": f"think:{run.version}:{run.task_id}:{run.arm}",
                "task_key": task_family(run.task_id),
                "task_id": run.task_id,
                "arm": run.arm,
                "split": (splits or {}).get(task_family(run.task_id)),
                "messages": messages,
                "thinking_zone": thinking_zone(answer),
                "meta": {**_source_meta(run), "prose_reasoning_chars": read_meta(solved_round).get("reasoning_chars")},
            }
        )
    return sorted(records, key=lambda record: record["id"])


def assign_splits(families, seed: int, ratios=RATIOS) -> dict[str, str]:
    unique = sorted(set(families))
    if not unique:
        return {}
    rng = random.Random(seed)
    shuffled = list(unique)
    rng.shuffle(shuffled)
    count = len(shuffled)
    if count == 1:
        return {shuffled[0]: "train"}
    if count == 2:
        return {shuffled[0]: "train", shuffled[1]: "test"}
    n_val = max(1, int(round(count * ratios[1])))
    n_test = max(1, int(round(count * ratios[2])))
    while n_val + n_test >= count:
        if n_test > 1:
            n_test -= 1
        elif n_val > 1:
            n_val -= 1
        else:
            break
    assignment: dict[str, str] = {}
    for index, family in enumerate(shuffled):
        if index < count - n_val - n_test:
            assignment[family] = "train"
        elif index < count - n_test:
            assignment[family] = "val"
        else:
            assignment[family] = "test"
    return assignment


def _write_jsonl(path: Path, records) -> str:
    text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_corpus(
    runs,
    out_dir,
    *,
    seed: int,
    arms=DEFAULT_ARMS,
    sets_dir: Path | str = SETS_DIR,
    verify: bool = True,
    evaluator=None,
    built_at: str | None = None,
    sandbox: str = DEFAULT_SANDBOX,
) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sets = load_sets(sets_dir)
    verification = {"checked": 0, "solved": 0, "unresolved": 0}
    if verify:
        verification = verify_runs(runs, evaluator=evaluator or default_evaluator(), sets=sets)
    families = [
        task_family(run.task_id)
        for run in runs
        if run.solved is True and run.arm in arms
    ]
    splits = assign_splits(families, seed)
    stats: dict = {}
    sft = build_sft(runs, arms=arms, splits=splits, stats=stats, sandbox=sandbox)
    dpo = build_dpo(runs, arms=arms, splits=splits, stats=stats, sandbox=sandbox)
    rlvr = build_rlvr(runs, arms=arms, splits=splits, sets=sets, sandbox=sandbox)
    think = build_think(runs, arms=arms, splits=splits)
    digests = {
        "sft.jsonl": _write_jsonl(out / "sft.jsonl", sft),
        "dpo.jsonl": _write_jsonl(out / "dpo.jsonl", dpo),
        "rlvr.jsonl": _write_jsonl(out / "rlvr.jsonl", rlvr),
        "think.jsonl": _write_jsonl(out / "think.jsonl", think),
    }
    splits_payload = {
        "seed": seed,
        "ratios": {"train": RATIOS[0], "val": RATIOS[1], "test": RATIOS[2]},
        "families": splits,
    }
    splits_text = json.dumps(splits_payload, ensure_ascii=False, indent=2) + "\n"
    (out / "splits.json").write_text(splits_text, encoding="utf-8")
    digests["splits.json"] = hashlib.sha256(splits_text.encode("utf-8")).hexdigest()

    by_root: dict[str, dict] = {}
    for run in runs:
        entry = by_root.setdefault(run.root.name, {"root": run.root.name, "runs": 0, "labeled": 0,
                                                   "reevaluated": 0, "unresolved": 0})
        entry["runs"] += 1
        if run.label_source == "summary.json":
            entry["labeled"] += 1
        elif run.label_source == "reevaluation":
            entry["reevaluated"] += 1
        elif run.label_source == "unresolved":
            entry["unresolved"] += 1
    manifest = {
        "built_at": built_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "arms": list(arms),
        "sandbox": sandbox,
        "command": " ".join(sys.argv),
        "counts": {
            "runs_scanned": len(runs),
            "sft": len(sft),
            "dpo": len(dpo),
            "rlvr": len(rlvr),
            "think": len(think),
            "splits": {
                split: sum(1 for value in splits.values() if value == split)
                for split in ("train", "val", "test")
            },
            "verification": verification,
            "filtered": {
                "sft_dropped_unverified": stats.get("sft_dropped_unverified", 0),
                "dpo_dropped_unverified_chosen": stats.get("dpo_dropped_unverified_chosen", 0),
            },
        },
        "files": {
            name: {"sha256": digest, "records": count}
            for name, digest, count in (
                ("sft.jsonl", digests["sft.jsonl"], len(sft)),
                ("dpo.jsonl", digests["dpo.jsonl"], len(dpo)),
                ("rlvr.jsonl", digests["rlvr.jsonl"], len(rlvr)),
                ("think.jsonl", digests["think.jsonl"], len(think)),
                ("splits.json", digests["splits.json"], len(splits)),
            )
        },
        "sources": sorted(by_root.values(), key=lambda entry: entry["root"]),
        "sets": {
            version: {"sha256": entry["sha256"]} for version, entry in sorted(sets.items())
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Trainingskorpus v0 aus den Laufordnern bauen.")
    parser.add_argument("--runs", action="append", required=True,
                        help="Laufwurzel (mehrfach angebbar), z.B. .yesmem/tmp/runs-v13-20260912")
    parser.add_argument("--out", required=True, help="Zielverzeichnis, z.B. training/corpus")
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    parser.add_argument("--sets-dir", default=str(SETS_DIR))
    parser.add_argument("--no-verify", action="store_true",
                        help="Runs ohne summary.json nicht re-evaluieren (werden ausgelassen)")
    parser.add_argument("--sandbox", choices=("require", "auto", "off"), default=DEFAULT_SANDBOX,
                        help="Sandbox fuer py:-Zeugen der Blaetter (Default: require)")
    parser.add_argument("--built-at", default=None)
    args = parser.parse_args(argv)
    arms = tuple(part.strip() for part in args.arms.split(",") if part.strip())
    runs = scan_runs(args.runs)
    manifest = write_corpus(
        runs,
        args.out,
        seed=args.seed,
        arms=arms,
        sets_dir=args.sets_dir,
        verify=not args.no_verify,
        built_at=args.built_at,
        sandbox=args.sandbox,
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

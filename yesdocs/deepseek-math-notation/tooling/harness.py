#!/usr/bin/env python3
"""Pilot-Harness: fuehrt Aufgaben x Arme gegen die lokale Modell-Instanz aus.

Transport ist der **direkte HTTP-Pfad**: per Default ueber den lokalen Proxy
(``http://localhost:9099/v1/chat/completions``), per ENV ``BEMYSELF_TARGET``
auch direkt gegen DeepSeek (``deepseek``) oder den Cluster (``cluster``,
privateTomMax). Der Schluessel kommt aus ``~/.local/share/opencode/auth.json``
(deepseek- bzw. gateway-Eintrag). Verifiziert am 2026-09-12:

- Der Aufruf kennt **keine Werkzeuge** — gemessen wird die Notation, nicht
  Tool-Nutzung; der Modell-Aufruf enthaelt nur unseren System- und User-Text.
- Der opencode-Systemprompt-Sockel (~21–28k Tokens, 05-04) faellt weg; Input,
  Output und Reasoning stehen als direkte Usage-Felder bereit
  (``completion_tokens_details.reasoning_tokens``).
- ``reasoning_content`` kommt als eigenes Feld der Antwort zurueck.
- Auth: ``Authorization: Bearer <key>`` und ``x-api-key: <key>`` liefern
  beide HTTP 200 (der 05-04-Vorbehalt ,,Auth ungeklaert'' ist damit
  ausgeraeumt — Abweichung dokumentiert im Pilotbericht).

Logs je Lauf: ``<runs>/<ts>/<task>/<arm>-rep<r>/`` mit ``round<n>/`` je
Runde (``prompt.md`` = gesamter Verlauf, ``raw.json`` = vollstaendige Antwort,
``parsed.json`` = Metriken + Verdikte + Feedback) und ``summary.json`` je
Lauf (Runden, Endzustand, Tokens).

Runde 2 (V12): Reparatur-Loop. Runde 0 laeuft wie der Pilot; ist der
Endzustand danach nicht bestaetigt, folgt eine Reparaturrunde (max.
``--max-repairs``, Default 2) mit dem Verdikt-Appendix des Runners im
Verlauf. K erhaelt stattdessen eine neutrale Selbstpruefung; die Formel-Arme
(B/C/D und die RC-Varianten C0/C1/C2) erhalten ihre eigenen maschinell
geprueften Verdikte -- niemals Referenzwerte (Gold-Leak-Schutz in
:func:`feedback_lines`).

Runde 3 (V13, Haerte): zwei Begriffe, getrennt gefuehrt --

- **Erfolg** ist der tier-typisierte Endzustand einer Runde: Zahl exakt (K)
  bzw. Beleg-Blatt bestaetigt (B/C/D, C0/C1/C2), alle Checkpoints exakt (trace),
  Zyklus-Zertifikat maschinenverifiziert (cyc, auch ohne Vorgabe).
- **Trigger** ist das Ereignis, das die *naechste* Runde ausloest:
  ``end_state_not_confirmed`` (siehe :data:`TRIGGER_NOT_CONFIRMED`). Er steht
  als Feld ``trigger`` in jeder Rundenzeile. Formfehler sind kein *eigener*
  Trigger (05-09 section 7.1 bleibt offener Kandidat fuer eine reine
  Blattqualitaets-Metrik): eine formfehlerhafte Runde traegt den Trigger nur,
  wenn ihr typisierter Endzustand unbestaetigt bleibt. Transportfehler
  bekommen den einen Retry der 05-05-Stopregel; ein Lauf ohne auswertbare
  Modellausgabe endet.

Dazu: das Zyklus-Scoring prueft die vom Modell genannten Werte gegen die
Maschine (``claimtypes.cycle``) statt gegen den Goldstring, und die
Rueckmeldung geht durch eine Default-Deny-Allowlist
(:func:`_sanitize_reason`): nur die geprueften Beleg-Arten duerfen ihre
Befunde durchreichen.

Runde 4 (V14, Lokalisierung): die Rueckmeldung folgt einer Leiter
``--feedback G0|G1|G2`` (Default G0). G0 ist der V13-Stand. G1 nennt die
Klasse des Befunds ohne Werte (Maschinenbindung fehlt / Werte widerlegt /
Form-Konvention) und schuetzt ungeprueste, aber gueltige Werte mit einer
ausdruecklichen "Werte nicht aendern"-Anweisung; G2 ergaenzt die
Positions-Klasse des Checkers (welche Vergleichs-Bedingung traegt nicht:
Zustand / Kopf-Translation / Bandfenster). Jede Klasse ist aus der
Checker-Semantik abgeleitet und traegt keine Referenzwerte; alles Unbekannte
faellt auf den Default-Deny-Sanitizer zurueck.

Aufrufe::

    python3 harness.py batch --arms K,B,C,D --reps 2 --tier-a 16 --tier-b 8
    python3 harness.py batch --arms C0,C1,C2 --task-ids B3-0001,B3-0005,A3-0016 --reps 1
    python3 harness.py one --arm C --task A3-0008 --rep 1
    python3 harness.py dry --arm C --task B3-0005

Die Sets kommen aus ``_TIER_A_SET``/``_TIER_B_SET`` (Default: Tier A v0.3,
Tier B v0.4); fuer eine Reproduktion alter Runden muessen diese Konstanten
bewusst umgestellt werden (die alten Set-Dateien liegen unveraendert im
Sets-Ordner).

Transport-Umstellung (V16): ``BEMYSELF_TARGET=proxy|deepseek|cluster`` waehlt
Endpoint und Modell (Default ``proxy``, V11-V15-kompatibel);
``BEMYSELF_MAX_TOKENS`` (Default 8192) und ``BEMYSELF_REASONING_EFFORT``
(Default: Feld wird nicht gesendet) ueberschreiben den Request-Body.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from bemyself.claimtypes import cycle  # noqa: E402
from bemyself.model import Claim  # noqa: E402
from bemyself.msheet.runner import run_sheet  # noqa: E402
from bemyself.msheet.sheet import parse_sheet  # noqa: E402
from bemyself.msheet.witnesses import _CP_RE, find_bwrap  # noqa: E402
from prompts import build_messages, build_repair_message  # noqa: E402

DEFAULT_PROXY_URL = "http://localhost:9099/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
CLUSTER_URL = "https://llm.ccm19.app/v1/chat/completions"

# Die drei Transport-Ziele (V16): `url` + `model` bestimmen den Aufruf,
# `auth` den Eintrag in auth.json. `proxy` bleibt der V11-V15-Pfad.
TARGETS = {
    "proxy": {"url": DEFAULT_PROXY_URL, "model": "deepseek-flash", "auth": "deepseek"},
    "deepseek": {"url": DEEPSEEK_URL, "model": "deepseek-flash", "auth": "deepseek"},
    "cluster": {"url": CLUSTER_URL, "model": "privateTomMax", "auth": "gateway"},
}


def proxy_url():
    """Der OpenAI-kompatible Endpunkt; per ENV umstellbar (Default: lokaler Proxy).

    Auf einer gemieteten GPU zeigt ``BEMYSELF_PROXY_URL`` auf die eigene
    vLLM-/SGLang-Instanz, damit dieselben Arme/Sets gegen das trainierte
    Modell laufen (Runbook: training/README.md). Ein leerer/whitespace-Wert
    zaehlt als "nicht gesetzt" -- so bricht ein versehentlich leeres ENV den
    Lauf nicht mit einem ValueError, sondern nutzt den Default.
    """
    value = os.environ.get("BEMYSELF_PROXY_URL", "").strip()
    return value or DEFAULT_PROXY_URL


def target_name():
    """Das gewaehlte Transport-Ziel: ``BEMYSELF_TARGET`` (Default ``proxy``)."""
    value = os.environ.get("BEMYSELF_TARGET", "").strip().lower()
    return value or "proxy"


def target_config(name=None):
    """(url, model, auth) des Ziels -- unbekannte Ziele brechen ab.

    ``proxy`` bleibt ueber ``BEMYSELF_PROXY_URL`` umstellbar (Runbook:
    gemietete GPU); die Direktziele ignorieren die Variable bewusst.
    """
    resolved = (name or target_name()).strip().lower()
    entry = TARGETS.get(resolved)
    if entry is None:
        known = ", ".join(sorted(TARGETS))
        raise SystemExit(f"unknown BEMYSELF_TARGET {resolved!r} (known: {known})")
    config = dict(entry)
    if resolved == "proxy":
        config["url"] = proxy_url()
    return config


def display_url(url):
    """Die URL ohne Zugangsdaten -- fuer Manifest und Protokollzeilen.

    ``BEMYSELF_PROXY_URL`` darf Userinfo tragen (``http://user:pass@host``);
    im Manifest hat weder Passwort noch Token etwas zu suchen.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password:
        host = parts.hostname or ""
        netloc = host if parts.port is None else f"{host}:{parts.port}"
        parts = parts._replace(netloc=netloc)
    return urllib.parse.urlunsplit(parts)


def _int_env(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from None


def max_tokens():
    """Ausgabe-Budget je Aufruf (``BEMYSELF_MAX_TOKENS``, Default 8192).

    Vorsicht beim Vergleich Proxy vs. Direkt: der YesMem-Proxy ersetzt
    ``max_tokens`` durch ``max_completion_tokens``, das DeepSeek ignoriert --
    ueber den Proxy ist das Budget faktisch wirkungslos (V16-Bericht 05-13).
    """
    return _int_env("BEMYSELF_MAX_TOKENS", 8192)


def reasoning_effort():
    """Optionales ``reasoning_effort`` (``BEMYSELF_REASONING_EFFORT``).

    Leer = Feld wird nicht gesendet. Der Proxy injiziert fuer deepseek-flash
    ``max`` (Config ``proxy.reasoning_effort``); der Direktpfad sendet nur,
    was hier explizit steht.
    """
    return os.environ.get("BEMYSELF_REASONING_EFFORT", "").strip()


AUTH_PATH = os.path.expanduser("~/.local/share/opencode/auth.json")
SETS_DIR = ROOT / "yesdocs" / "deepseek-math-notation" / "sets"
RUNS_DIR = ROOT / ".yesmem" / "tmp" / "runs"

_TIER_A_SET = "tier_a_v11-a-0.3.json"
_TIER_B_SET = "tier_b_v11-b-0.4.json"

# Runde-2-Fairness-Design: Diese Arme erhalten in der Reparaturrunde ihre
# eigenen maschinellen Verdikte (Appendix + Befunde). K erhaelt die neutrale
# Selbstpruefung -- Verdikte, die es nicht gibt, werden nicht erfunden.
# C0/C1/C2 (V15) sind C-Varianten der RC-Umstellung und erben den Rueckkanal;
# H (V16) ist die Zwangsprompt-Variante und erbt ihn ebenfalls; L0/L1/L2
# (V18, Lean-Taktik-Denkspur) sind C-Varianten und erben ihn ebenso.
MACHINE_FEEDBACK_ARMS = ("B", "C", "D", "C0", "C1", "C2", "H", "L0", "L1", "L2")

# Der einzige Trigger der Rundenkette (Haerte-Runde V13): der typisierte
# Endzustand der Runde ist nicht bestaetigt, es folgt die naechste Runde.
TRIGGER_NOT_CONFIRMED = "end_state_not_confirmed"


def _api_key(target=None):
    """Der Key-Eintrag des Ziels; die Fehlermeldung traegt nie einen Key."""
    entry = target_config(target)["auth"]
    try:
        with open(AUTH_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)[entry]["key"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"cannot read the {entry} key from {AUTH_PATH}: {type(exc).__name__}"
        ) from None


def _load_set(filename):
    path = SETS_DIR / filename
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    payload["_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload["_path"] = str(path.relative_to(ROOT))
    return payload


def call_model(messages, timeout):
    """One chat completion (messages array, selected target); returns
    (payload, raw, duration, error)."""
    config = target_config()
    fields = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": max_tokens(),
    }
    effort = reasoning_effort()
    if effort:
        fields["reasoning_effort"] = effort
    body = json.dumps(fields).encode("utf-8")
    start = time.monotonic()
    try:
        # Der Request-Bau gehoert in den try: eine ungueltige
        # BEMYSELF_PROXY_URL (z.B. Leerzeichen) muss als Transportfehler
        # zurueckkommen, nicht als Traceback.
        request = urllib.request.Request(
            config["url"],
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_api_key()}",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.load(response)
        duration = time.monotonic() - start
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        return None, None, time.monotonic() - start, f"{type(exc).__name__}: {exc}"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, None, time.monotonic() - start, f"malformed response: {exc}"
    try:
        message = raw["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        return None, raw, time.monotonic() - start, f"unexpected response shape: {exc!r}"
    payload = {
        "content": message.get("content") or "",
        "reasoning": message.get("reasoning_content") or "",
        "usage": raw.get("usage", {}),
        "finish_reason": raw["choices"][0].get("finish_reason"),
    }
    return payload, raw, duration, None


def extract_sheet_text(answer):
    """The sheet inside an answer: the largest fenced block, else the text."""
    fences = re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", answer, flags=re.DOTALL)
    if fences:
        return max(fences, key=len)
    return answer


def extract_endanswer(answer):
    matches = re.findall(r"Endantwort\s*:\s*(.+)", answer)
    if not matches:
        return None
    value = matches[-1].strip().split()[0] if matches[-1].strip() else None
    return value


def _normalize_value(value):
    if value is None:
        return None
    cleaned = value.strip().rstrip(".,;:)")
    cleaned = cleaned.replace(",", "").replace("_", "")
    return cleaned


def _contains_token(text, expected):
    return re.search(r"(?<![0-9])" + re.escape(expected) + r"(?![0-9])", text) is not None


def _to_int(text):
    """A model-supplied integer, or None when it is not convertible.

    CPython caps ``int(str)`` at 4300 digits and raises ValueError beyond it;
    such a token is no configuration/certificate value, and it must never end
    the run (review 5.2/1, 5.4 NEW). Fail-closed like ``claimtypes.cycle``.
    """
    try:
        return int(text)
    except ValueError:
        return None


def _checkpoint_pairs(text):
    pairs = {}
    for match in _CP_RE.findall(text):
        step = _to_int(match[0])
        head = _to_int(match[2])
        if step is None or head is None:
            continue
        pairs[step] = (match[1], head, match[3])
    return pairs


def _tape_key(tape):
    """Tape comparison up to leading/trailing zeros (value-equal windows)."""
    return tape.strip("0")


def _checkpoint_score(answer, gold):
    pairs = _checkpoint_pairs(answer)
    matched = 0
    first_deviation = None
    for step, state, head, tape in gold:
        got = pairs.get(step)
        if got is not None and got[0] == state and got[1] == head and _tape_key(got[2]) == _tape_key(tape):
            matched += 1
        elif first_deviation is None:
            first_deviation = step
    return matched, first_deviation, {str(k): v for k, v in sorted(pairs.items())}


def _certificate_holds(machine_text, values):
    """True when (t1,t2,d) verifies as a translation cycle of the machine.

    The verdict comes from the same checker as the sheet path
    (``claimtypes.cycle``): a valid *other* certificate is a solved task, a
    made-up one never is (V13).
    """
    t1, t2, d = (str(value) for value in values)
    claim = Claim(
        kind="cycle",
        line=0,
        raw="harness-score",
        fields={
            "machine": machine_text,
            "values": f"{t1},{t2},{d}",
            "t1": t1,
            "t2": t2,
            "d": d,
        },
    )

    class _Ctx:
        cycle_limit = cycle.DEFAULT_CYCLE_LIMIT

    try:
        result = cycle.check(claim, _Ctx())
    except Exception:  # noqa: BLE001 -- a broken certificate is never solved
        return False
    return result.verdict.value == "CONFIRMED"


_CERT_RE = re.compile(
    r"t1\s*=\s*(-?[0-9]+)[,;\s]+t2\s*=\s*(-?[0-9]+)[,;\s]+d\s*=\s*(-?[0-9]+)"
)


def _sheet_evaluation(answer):
    sheet = parse_sheet(extract_sheet_text(answer))
    result = run_sheet(sheet, sandbox="auto", timeout=20.0)
    return sheet, result


def _sheet_block(sheet, result):
    """The persisted sheet evidence: verdicts, witness kind/text, errors."""
    kinds = {v.vid: (v.spec.kind if v.spec else "unparsable") for v in sheet.vlines}
    texts = {v.vid: v.witness_text for v in sheet.vlines}
    block = {
        "format_errors": result.format_errors,
        "appendix": result.appendix,
        "v": [
            {
                "id": v.vid,
                "target": v.target,
                "verdict": v.verdict.value,
                "kind": kinds.get(v.vid, "?"),
                "witness": texts.get(v.vid, ""),
            }
            for v in result.v_results
        ],
    }
    if result.claim_results:
        block["claims"] = [
            {
                "id": c.cid,
                "verdict": c.verdict.value,
                "reason": c.reason,
                "witness": (
                    sheet.witness_for(c.cid).text if sheet.witness_for(c.cid) else ""
                ),
            }
            for c in result.claim_results
        ]
    return block


def evaluate_answer(arm, task, answer, evidence_out=None):
    """Score one answer by the pilot conventions.

    Fills ``evidence_out`` (when given) with the parsed sheet and its runner
    result whenever a sheet was evaluated -- the repair round builds its
    feedback from exactly this evidence.
    """
    fragment = {"solved": False}

    if task["tier"] == "A":
        if arm == "K":
            value = _normalize_value(extract_endanswer(answer))
            fragment["endanswer"] = value
            fragment["solved"] = value == task["expected"]
        else:
            sheet, result = _sheet_evaluation(answer)
            if evidence_out is not None:
                evidence_out["sheet"] = sheet
                evidence_out["result"] = result
            fragment.update(_sheet_block(sheet, result))
            claim_texts = {claim.cid: claim.text for claim in sheet.claims}
            confirmed = [
                c
                for c in result.claim_results
                if c.verdict.value == "CONFIRMED"
                and _contains_token(claim_texts.get(c.cid, ""), task["expected"])
            ]
            fragment["solved"] = (
                bool(result.claim_results)
                and all(c.verdict.value == "CONFIRMED" for c in result.claim_results)
                and bool(confirmed)
            )
    elif task.get("tier_b_kind") == "trace":
        matched, first_deviation, pairs = _checkpoint_score(answer, task["checkpoints_gold"])
        fragment["checkpoints_matched"] = matched
        fragment["checkpoints_total"] = len(task["checkpoints_gold"])
        fragment["first_deviation"] = first_deviation
        fragment["checkpoints"] = pairs
        fragment["solved"] = matched == len(task["checkpoints_gold"])
        if arm in ("B", "C", "D", "C0", "C1", "C2", "H"):
            sheet, result = _sheet_evaluation(answer)
            if evidence_out is not None:
                evidence_out["sheet"] = sheet
                evidence_out["result"] = result
            fragment.update(_sheet_block(sheet, result))
    elif task.get("tier_b_kind") == "cyc":
        if arm in ("K", "B"):
            # Maschinenverifiziert statt Goldstring-Vergleich: das Modell darf
            # jedes gueltige Zertifikat nennen (die Nicht-Vorgabe-Variante
            # findet regelmaessig ein anderes als das eingefrorene). Der Regex
            # ist bewusst nachsichtig (letzter Treffer, auch ueber Zeilen);
            # ein maschinenverifiziertes Zertifikat beweist die NICHT-HALTEND-
            # Aussage selbst, ein nicht konvertierbares zaehlt nicht.
            matches = _CERT_RE.findall(answer)
            certificate = None
            if matches:
                values = tuple(_to_int(value) for value in matches[-1])
                if all(value is not None for value in values):
                    certificate = values
            fragment["certificate_claimed"] = list(certificate) if certificate else None
            fragment["solved"] = (
                "NICHT-HALTEND" in answer
                and certificate is not None
                and _certificate_holds(task["machine"], certificate)
            )
        else:
            sheet, result = _sheet_evaluation(answer)
            if evidence_out is not None:
                evidence_out["sheet"] = sheet
                evidence_out["result"] = result
            fragment.update(_sheet_block(sheet, result))
            # The sheet must reason about the task's machine: a self-consistent
            # sheet about another machine must not count as an answer (and no
            # extra unrelated bindings either).
            task_machine = _machine_key(task["machine"])
            bound = _bound_machines(sheet)
            fragment["machine_bound"] = bool(bound) and bound == {task_machine}
            fragment["solved"] = (
                bool(result.claim_results)
                and all(c.verdict.value == "CONFIRMED" for c in result.claim_results)
                and fragment["machine_bound"]
            )
    return fragment


def evaluate_run(arm, task, payload, duration, error, args, evidence_out=None):
    record = {
        "arm": arm,
        "task_id": task["id"],
        "tier": task["tier"],
        "tier_b_kind": task.get("tier_b_kind"),
        "duration_s": round(duration, 2),
        "error": error,
        "usage": payload.get("usage") if payload else {},
        "finish_reason": payload.get("finish_reason") if payload else None,
    }
    answer = payload.get("content", "") if payload else ""
    reasoning = payload.get("reasoning", "") if payload else ""
    record["answer"] = answer[:20000]
    record["reasoning_chars"] = len(reasoning)
    record["reasoning"] = reasoning[:20000]
    record["solved"] = False

    if payload is None:
        return record

    record.update(evaluate_answer(arm, task, answer, evidence_out=evidence_out))
    return record


_SIM_STEP_RE = re.compile(r"sim: at step ([0-9]+)")


# Default-Deny-Allowlist der Rueckmeldung (V13, 05-09 section 7.7). Nur die
# Beleg-Arten hier duerfen ihre Befunde durchreichen, und ihre nicht-REFUTED-
# Texte wurden darauf geprueft, keine berechneten Referenzwerte zu tragen
# (Fehlertexte des Runners, Modell-eigene Werte). Eine neue Beleg-Art muss
# bewusst aufgenommen *und* geprueft werden; ohne Eintrag kommt sie nur als
# Marker zurueck -- ein kuenftiger Beleg-Typ kann die Referenzwerte damit
# nicht versehentlich durchlassen.
_ALLOWED_REASON_KINDS = frozenset({"auto", "ref", "sim", "cyc", "py", "range"})
# ``range`` gehoert dazu, weil witnesses._execute_range seine Formel baut und
# durch denselben _run_formula-Pfad schickt wie ``auto`` -- die nicht-REFUTED-
# Texte sind strukturell identisch und wertfrei (Audit 5.2/2; vorher
# ueberblockiert).
# Refutations-Texte, die die Referenz selbst benennen (Zustand/Kopf/Band bzw.
# Zertifikat-Groessen), bleiben immer gesanitisiert -- auch fuer erlaubte Arten.
_WITHHELD_VERDICTS = frozenset({("sim", "REFUTED"), ("cyc", "REFUTED")})
_DEFAULT_DENY_REASON = "{kind}: der Beleg traegt nicht (Rueckmeldung ohne Referenzwerte)"


def _sanitize_reason(kind, verdict, reason):
    """The reason as safe to hand back: error texts stay, computed reference
    values do not (no gold leak). ``sim``/``cyc`` refutations name the actual
    state/head/tape or certificate parts -- the sheet owner must find its own
    values again. Everything outside the reviewed kinds is withheld: the
    allowlist is default-deny, so a future witness kind cannot leak."""
    if verdict == "CONFIRMED":
        return reason
    if kind not in _ALLOWED_REASON_KINDS:
        return _DEFAULT_DENY_REASON.format(kind=kind or "unbekannt")
    if (kind, verdict) in _WITHHELD_VERDICTS:
        if kind == "sim":
            match = _SIM_STEP_RE.search(reason)
            where = f" bei Schritt {match.group(1)}" if match else ""
            return (
                f"sim: die Konfiguration{where} stimmt nicht mit der "
                "Referenzsimulation ueberein"
            )
        return "cyc: das Zertifikat traegt fuer diese Maschine nicht"
    return reason


# ---------------------------------------------------------------------------
# Runde 4 (V14): die Feedback-Leiter G0/G1/G2.
#
# G0 = der V13-Stand (oben): die sanitisierten Befunde, nicht weiter
# lokalisiert. G1 = Klassen-Befunde ohne Werte (Bindung fehlt / Werte
# widerlegt / Form-Konvention), inklusive der Schutzanweisung fuer
# ungepruefte, aber gueltige Werte. G2 = G1 plus die Positions-Klasse des
# Checkers (welche Vergleichs-Bedingung zuerst traegt nicht) -- abgeleitet
# aus der Branch-Reihenfolge von ``claimtypes.cycle``/``witnesses._run_sim``,
# niemals aus Referenzwerten. Alles, was keine der bekannten Klassen trifft,
# faellt auf :func:`_sanitize_reason` zurueck (Default-Deny bleibt).
#
# Nicht darstellbar und deshalb bewusst gestrichen: eine Klasse "t1 liegt
# nicht am Zyklus-Eintritt" -- der Checker kennt keinen solchen Zweig, und
# jede Aussage darueber braeuchte den (Gold-nahen) echten Eintritt.

FEEDBACK_LEVELS = ("G0", "G1", "G2")

_BINDING_MISSING_MARKER = "no machine binding in the sheet"
_BINDING_AMBIGUOUS_MARKERS = (
    "several machine names appear in the target",
    "multiple machine bindings but none referenced in the target",
)

_CLASS_BINDING_MISSING = (
    "keine Maschinenbindung im Blatt: die genannten Werte sind nicht "
    "widerlegt, nur nicht geprueft (erwartet 'a: M = <machine>')"
)
_HINT_BINDING_MISSING = (
    "Hinweis: ergaenze nur die Maschinenbindung und aendere die genannten "
    "Werte nicht - sie sind nicht widerlegt, nur ungeprueft."
)
_CLASS_BINDING_WRONG = (
    "das Blatt bindet eine andere Maschine als die Aufgabe; belege die "
    "Aufgaben-Maschine ('a: M = <machine>')"
)
_CLASS_VALUES_REFUTED = "das Zertifikat ist widerlegt (es traegt fuer diese Maschine nicht)"

# Die Positions-Klassen (G2): welche *Vergleichs*-Bedingung des Checkers
# traegt nicht? Die Liste spiegelt die Vergleichs-Branches (Zustand, Kopf,
# Band); der Halt-Zweig steht vor allen Vergleichen im Checker und ist hier
# als eigener Fall dabei. Alle Phrasen sind digit-frei.
_LEG_CYC = {
    "state": (
        "widerlegt an der Zustands-Bedingung: die Zustaende an den beiden "
        "Zyklus-Zeitpunkten stimmen nicht ueberein"
    ),
    "head": (
        "widerlegt an der Translations-Bedingung: die Kopfdistanz zwischen "
        "den beiden Zyklus-Zeitpunkten ist nicht die genannte Verschiebung d"
    ),
    "tape": (
        "widerlegt an der Band-Bedingung: die Baender stimmen im erreichbaren "
        "Fenster nicht ueberein"
    ),
    "halt": "widerlegt: die Maschine haelt innerhalb des Zertifikat-Fensters",
}
_SIM_LEG = {
    "state": "bei Schritt {step} traegt der Zustand nicht (Referenzsimulation)",
    "head": "bei Schritt {step} traegt die Kopfposition nicht (Referenzsimulation)",
    "tape": "bei Schritt {step} traegt das Bandfenster nicht (Referenzsimulation)",
}

# Die Reason-Texte der Checker-Branches (cycle.check / witnesses._run_sim).
# Lineare Muster (ReDoS-Lehre), gepinnt durch tests/test_v14_harness.py gegen
# die echten Texte. Ein unbekannter Text faellt auf _sanitize_reason zurueck.
_CYC_LEG_RES = (
    (
        "state",
        re.compile(
            r"\Acyc: the state at step [0-9]+ is [A-Z], not the state at step [0-9]+ \([A-Z]\)\Z"
        ),
    ),
    (
        "head",
        re.compile(
            r"\Acyc: the head at step [0-9]+ is at cell -?[0-9]+, not at cell -?[0-9]+ "
            r"\+ -?[0-9]+ = -?[0-9]+\Z"
        ),
    ),
    (
        "tape",
        re.compile(
            r"\Acyc: the tape at step [0-9]+ differs from the tape at step [0-9]+ at "
            r"relative position -?[0-9]+ inside the reachable window; so it is not the "
            r"configuration at step [0-9]+ translated by -?[0-9]+\Z"
        ),
    ),
    (
        "halt",
        re.compile(
            r"\Acyc: the machine halted after [0-9]+ steps, inside the certificate "
            r"window of [0-9]+ steps\Z"
        ),
    ),
)
_SIM_LEG_RES = (
    ("state", re.compile(r"\Asim: at step ([0-9]+) the state is [A-Z], not [A-Z]\Z")),
    ("head", re.compile(r"\Asim: at step ([0-9]+) the head is at -?[0-9]+, not -?[0-9]+\Z")),
    ("tape", re.compile(r"\Asim: at step ([0-9]+) the written window is '[01]*', not '[01]*'\Z")),
)


def _row_class(kind, verdict, reason):
    """(class, leg, step) of one row -- aus der Checker-Semantik, ohne Werte.

    ``class`` ist eine der Klassen der Feedback-Leiter:
    ``binding_missing`` (sim/cyc ohne Maschinenbindung),
    ``binding_ambiguous`` (mehrere/namenlose Bindungen),
    ``values_refuted`` (sim/cyc widerlegt; ``leg`` nennt die tragende
    Vergleichs-Bedingung: state/head/tape/halt, ``step`` den modell-eigenen
    sim-Schritt), ``chain`` (ref_unconfirmed), ``formula_refuted`` (auto/
    range/py falsch), ``not_checkable`` (uebrige UNVERIFIABLE), ``other``.
    """
    if verdict == "CONFIRMED":
        return ("ok", None, None)
    if verdict == "REFUTED" and kind == "cyc":
        for leg, pattern in _CYC_LEG_RES:
            if pattern.match(reason):
                return ("values_refuted", leg, None)
        return ("values_refuted", None, None)
    if verdict == "REFUTED" and kind == "sim":
        for leg, pattern in _SIM_LEG_RES:
            match = pattern.match(reason)
            if match:
                return ("values_refuted", leg, match.group(1))
        return ("values_refuted", None, None)
    if verdict == "UNVERIFIABLE":
        if _BINDING_MISSING_MARKER in reason:
            return ("binding_missing", None, None)
        if any(marker in reason for marker in _BINDING_AMBIGUOUS_MARKERS):
            return ("binding_ambiguous", None, None)
        if kind == "ref":
            return ("chain", None, None)
        return ("not_checkable", None, None)
    if kind == "ref":
        return ("chain", None, None)
    if kind in ("auto", "range", "py"):
        return ("formula_refuted", None, None)
    return ("other", None, None)


def _render_note(kind, verdict, reason, level="G0"):
    """The note text of one non-confirmed row at the given level.

    G0 returns the V13-sanitized text unchanged. G1/G2 localize the known
    classes; everything unrecognized goes through :func:`_sanitize_reason`
    (default-deny). The class texts carry no digits of their own; the only
    digits that can appear are model-owned (ids, the sim step).
    """
    if level == "G0":
        return _sanitize_reason(kind, verdict, reason)
    cls, leg, step = _row_class(kind, verdict, reason)
    if cls == "binding_missing":
        return f"{kind}: {_CLASS_BINDING_MISSING}"
    if cls == "values_refuted":
        if kind == "cyc":
            if level == "G2" and leg:
                return f"cyc: {_LEG_CYC[leg]}"
            return f"cyc: {_CLASS_VALUES_REFUTED}"
        if level == "G2" and leg:
            return f"sim: {_SIM_LEG[leg].format(step=step)}"
        return _sanitize_reason(kind, verdict, reason)
    return _sanitize_reason(kind, verdict, reason)


def _machine_key(text):
    """A machine source compared name-insensitively (as evaluate_answer does)."""
    return re.sub(r"[\s_]", "", text or "").upper()


def _bound_machines(sheet):
    """The normalized machine sources bound in the sheet (``a: M = ...``)."""
    return {_machine_key(machine.source) for machine in getattr(sheet, "machines", {}).values()}


def feedback_bundle(arm, task, evidence, *, level="G0"):
    """(appendix, notes, hints, classes) of the repair round -- never gold.

    K (and any arm without machine-checked evidence) gets nothing: verdicts
    that do not exist are not invented. The classes are computed for every
    level (the run data records them); the note texts follow the ladder.
    """
    if level not in FEEDBACK_LEVELS:
        raise ValueError(f"unknown feedback level {level!r}")
    if arm not in MACHINE_FEEDBACK_ARMS or not evidence:
        return [], [], [], []
    sheet = evidence.get("sheet")
    result = evidence.get("result")
    if result is None:
        return [], [], [], []
    # Getrennte Lookups: Claim-ids wie "v1" sind parserlegal; ein gemeinsames
    # Dict ueber nackte ids wuerde den v-Line-Kind umetikettieren und den
    # Sanitizer die Referenzwerte durchlassen.
    kinds_v = {vline.vid: (vline.spec.kind if vline.spec else None) for vline in sheet.vlines}
    kinds_c = {}
    for claim in sheet.claims:
        witness = sheet.witness_for(claim.cid)
        kinds_c[claim.cid] = witness.spec.kind if witness is not None and witness.spec else None
    notes = []
    hints = []
    classes = []

    def _add(row_id, kind, verdict, reason):
        cls, leg, _step = _row_class(kind, verdict, reason)
        notes.append(f"{row_id}: {_render_note(kind, verdict, reason, level)}")
        entry = {"id": row_id, "class": cls}
        if leg:
            entry["leg"] = leg
        classes.append(entry)
        if cls == "binding_missing" and level != "G0" and _HINT_BINDING_MISSING not in hints:
            hints.append(_HINT_BINDING_MISSING)

    for row in result.v_results:
        if row.verdict.value == "CONFIRMED":
            continue
        _add(row.vid, kinds_v.get(row.vid), row.verdict.value, row.reason)
    for row in result.claim_results:
        if row.verdict.value == "CONFIRMED":
            continue
        _add(row.cid, kinds_c.get(row.cid), row.verdict.value, row.reason)
    # Harness-Ebene (G1+): das Blatt ist in sich bestaetigt, bindet aber eine
    # fremde Maschine -- ohne diese Note bliebe der Fall stumm ("nichts
    # geprueft"), obwohl er nicht geloest ist.
    if level != "G0" and not notes and task.get("tier_b_kind") == "cyc":
        bound = _bound_machines(sheet)
        task_machine = _machine_key(task.get("machine"))
        if bound and task_machine and bound != {task_machine}:
            notes.append(f"a: {_CLASS_BINDING_WRONG}")
            classes.append({"id": "a", "class": "binding_wrong"})
    return list(result.appendix), notes, hints, classes


def feedback_lines(arm, task, evidence):
    """(appendix, notes) of the repair round in the G0 (V13) shape.

    Kept as the stable two-tuple wrapper for the older rounds' tests; the
    level-aware path is :func:`feedback_bundle`.
    """
    verdicts, notes, _hints, _classes = feedback_bundle(arm, task, evidence, level="G0")
    return verdicts, notes


def _render_messages(messages):
    parts = [f"# {message['role']}\n\n{message.get('content', '')}" for message in messages]
    return "\n\n".join(parts) + "\n"


def run_rounds(arm, task, rep, runs_root, args, call=None):
    """One task x arm x rep over round 0 + up to ``max_repairs`` repair rounds.

    Round 0 runs like the pilot. When the end state is not confirmed, the next
    round continues the same conversation: the model's own answer plus the
    verdict feedback (or, for K, the neutral self-check). Stops as soon as the
    end state is confirmed. Transport errors get the single retry of the 05-05
    stop rule; a round without model output ends the run.
    """
    call = call or call_model
    max_repairs = getattr(args, "max_repairs", 2)
    level = getattr(args, "feedback", "G0")
    if level not in FEEDBACK_LEVELS:
        raise ValueError(f"unknown feedback level {level!r}")
    # G0 laeuft unter dem V13-Verzeichnisnamen (Bestandslogs bleiben lesbar);
    # die Level-Zellen tragen ihr Level im Namen.
    base = runs_root / task["id"] / _run_dir_name(arm, rep, level)
    base.mkdir(parents=True, exist_ok=True)
    system, user = build_messages(arm, task)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    rounds = []
    retries = 0
    feedback_in = None

    for round_index in range(max_repairs + 1):
        out_dir = base / f"round{round_index}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "prompt.md").write_text(_render_messages(messages), encoding="utf-8")
        payload = raw = None
        duration = 0.0
        error = "not called"
        for attempt in (0, 1):
            payload, raw, duration, error = call(messages, args.timeout)
            if error is None:
                break
            if attempt == 0:
                retries += 1
        if raw is not None:
            (out_dir / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

        evidence = {}
        record = evaluate_run(arm, task, payload, duration, error, args, evidence_out=evidence)
        record["round"] = round_index
        record["feedback_in"] = feedback_in
        # Im Verlauf wird die volle Antwort zurueckgespielt, nicht die im
        # Protokoll gekuerzte Fassung (record["answer"] ist bei 20000 Zeichen
        # beschnitten; max_tokens 8192 kann laenger werden).
        answer_full = (payload.get("content") or "") if payload else ""
        solved = bool(record["solved"])
        usage = record.get("usage") or {}

        # Erfolg und Trigger getrennt (V13): der Endzustand der Runde ist der
        # Erfolg; der Trigger ist das Ereignis, das die *naechste* Runde
        # ausloest. Formfehler allein loesen nichts aus, Transportfehler
        # bekommen den einen Retry der 05-05-Stopregel.
        stop = solved or payload is None or round_index == max_repairs
        trigger = None
        repair_text = None
        classes = []
        if not stop:
            trigger = TRIGGER_NOT_CONFIRMED
            result = evidence.get("result")
            verdicts, notes, hints, classes = feedback_bundle(arm, task, evidence, level=level)
            format_errors = list(result.format_errors) if result is not None else []
            repair_text = build_repair_message(arm, task, verdicts, notes, format_errors, hint_lines=hints)
        record["trigger"] = trigger
        record["next_feedback"] = repair_text
        record["feedback_level"] = level
        record["feedback_classes"] = classes
        rounds.append(
            {
                "round": round_index,
                "solved": solved,
                "trigger": trigger,
                "error": error,
                "duration_s": record["duration_s"],
                "completion_tokens": usage.get("completion_tokens", 0),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get(
                    "reasoning_tokens", 0
                ),
                "format_errors": len(record.get("format_errors") or []),
            }
        )
        (out_dir / "parsed.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

        if stop:
            break
        messages.append({"role": "assistant", "content": answer_full})
        messages.append({"role": "user", "content": repair_text})
        feedback_in = repair_text

    rounds_to_ok = next((row["round"] for row in rounds if row["solved"]), None)
    summary = {
        "task_id": task["id"],
        "arm": arm,
        "tier": task["tier"],
        "rep": rep,
        "feedback": level,
        "max_repairs": max_repairs,
        "rounds": rounds,
        "final_solved": bool(rounds and rounds[-1]["solved"]),
        "rounds_to_ok": rounds_to_ok,
        "repairs_used": len(rounds) - 1,
        "triggered_rounds": [row["round"] for row in rounds if row["trigger"]],
        "transport_retries": retries,
        "total_completion_tokens": sum(row["completion_tokens"] for row in rounds),
        "total_reasoning_tokens": sum(row["reasoning_tokens"] for row in rounds),
        "total_duration_s": round(sum(row["duration_s"] for row in rounds), 2),
    }
    (base / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _select_tasks(tier_a, tier_b, args):
    """The task list of one batch.

    ``--task-ids`` (comma list) selects exactly the named tasks, in the given
    order -- the reproducible-subset path (V15). ``--tasks`` (operator input)
    selects in the given order, bypassing the tier caps (V14). Without either,
    the seeded shuffle of the historical rounds applies unchanged.
    """
    task_ids = getattr(args, "task_ids", None)
    if task_ids:
        wanted = [part.strip() for part in task_ids.split(",") if part.strip()]
        if len(wanted) != len(set(wanted)):
            raise ValueError(
                f"duplicate task ids: {', '.join(sorted({t for t in wanted if wanted.count(t) > 1}))}"
            )
        by_id = {task["id"]: task for task in tier_a["tasks"] + tier_b["tasks"]}
        missing = [task_id for task_id in wanted if task_id not in by_id]
        if missing:
            raise ValueError(f"unknown task ids: {', '.join(missing)}")
        return [by_id[task_id] for task_id in wanted]
    wanted = [
        name.strip()
        for name in (getattr(args, "tasks", None) or "").split(",")
        if name.strip()
    ]
    if wanted:
        # Explizite Aufgaben-Liste (Operator-Eingabe): Auswahl in der
        # angegebenen Reihenfolge, die Tier-Limits entfallen.
        by_id = {task["id"]: task for task in tier_a["tasks"] + tier_b["tasks"]}
        missing = [name for name in wanted if name not in by_id]
        if missing:
            raise SystemExit(f"unknown task id(s): {', '.join(missing)}")
        return [by_id[name] for name in wanted]
    rng = random.Random(args.seed)
    a_tasks = list(tier_a["tasks"])
    b_tasks = list(tier_b["tasks"])
    rng.shuffle(a_tasks)
    rng.shuffle(b_tasks)
    if args.tier_a is not None:
        a_tasks = a_tasks[: args.tier_a]
    if args.tier_b is not None:
        b_tasks = b_tasks[: args.tier_b]
    return a_tasks + b_tasks


def _runs_root(args):
    """The run root of a batch/one invocation (override for resuming runs).

    Without ``--runs-root`` every invocation opens a fresh timestamped root;
    with it, chunks can be re-run into the same root (replacing exactly the
    (task, arm) cells they name).
    """
    override = getattr(args, "runs_root", None)
    root = Path(override) if override else RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")
    root = root.resolve()  # relative overrides are CWD-relative, then absolute
    root.mkdir(parents=True, exist_ok=True)
    return root


def _display_path(path):
    """Path for log lines: relative to the repo when possible, else absolute."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def _run_dir_name(arm, rep, level):
    """The run directory of one cell: G0 keeps the V13 name (no level)."""
    return f"{arm}-rep{rep}" if level == "G0" else f"{arm}-{level}-rep{rep}"


def cmd_batch(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = _select_tasks(tier_a, tier_b, args)
    arms = [arm.strip().upper() for arm in args.arms.split(",") if arm.strip()]
    runs_root = _runs_root(args)
    rng = random.Random(args.seed)
    transport = target_config()
    print(
        f"transport: {target_name()} -> {display_url(transport['url'])}"
        f" ({transport['model']}, max_tokens={max_tokens()},"
        f" reasoning_effort={reasoning_effort() or 'default'})"
    )
    manifest = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": transport["model"],
        "mode": "repair",
        "feedback": args.feedback,
        "max_repairs": args.max_repairs,
        "transport": {
            "target": target_name(),
            "url": display_url(transport["url"]),
            "model": transport["model"],
            "max_tokens": max_tokens(),
            "reasoning_effort": reasoning_effort() or None,
        },
        "reasoning_history": "strip",
        "arms": arms,
        "reps": args.reps,
        "tier_a_set": {"version": tier_a["set_version"], "sha256": tier_a["_sha256"]},
        "tier_b_set": {"version": tier_b["set_version"], "sha256": tier_b["_sha256"]},
        "tasks": [task["id"] for task in tasks],
        "seed": args.seed,
    }
    (runs_root / "manifest.json" if not (runs_root / "manifest.json").exists()
     else runs_root / f"manifest-{time.strftime('%H%M%S')}.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"runs root: {_display_path(runs_root)}")
    print(f"tasks: {len(tasks)} ({len([t for t in tasks if t['tier']=='A'])} A, "
          f"{len([t for t in tasks if t['tier']=='B'])} B), arms {arms}, reps {args.reps}, "
          f"max_repairs {args.max_repairs}")

    if not args.skip_warmup:
        _payload, _raw, duration, error = call_model(
            [
                {"role": "system", "content": "Du bist ein Test."},
                {"role": "user", "content": "Antworte mit exakt einem Wort: OK"},
            ],
            args.timeout,
        )
        print(f"warmup: {duration:.1f}s error={error}")

    solved = 0
    runs = 0
    for task in tasks:
        for rep in range(1, args.reps + 1):
            order = list(arms)
            rng.shuffle(order)
            for arm in order:
                runs += 1
                summary = run_rounds(arm, task, rep, runs_root, args)
                solved += bool(summary["final_solved"])
                marker = "OK " if summary["final_solved"] else "   "
                r0 = summary["rounds"][0] if summary["rounds"] else {"solved": False}
                print(
                    f"{marker}{task['id']} rep{rep} {arm}: "
                    f"rounds={len(summary['rounds'])} r0={'ok' if r0['solved'] else 'no'} "
                    f"r2ok={summary['rounds_to_ok']} "
                    f"tok={summary['total_completion_tokens']} "
                    f"({summary['total_duration_s']:.1f}s)"
                    + (f" ERR={summary['rounds'][-1]['error']}" if summary["rounds"][-1]["error"] else "")
                )
    print(f"done: {runs} runs, final solved {solved}/{runs}")
    return 0


def cmd_one(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = {t["id"]: t for t in tier_a["tasks"] + tier_b["tasks"]}
    task = tasks[args.task]
    runs_root = _runs_root(args)
    level = getattr(args, "feedback", "G0")
    summary = run_rounds(args.arm.upper(), task, args.rep, runs_root, args)
    print(json.dumps(summary, indent=2))
    print(
        "logs: "
        + _display_path(runs_root / task["id"] / _run_dir_name(args.arm.upper(), args.rep, level))
    )
    return 0


def cmd_dry(args):
    tier_a = _load_set(_TIER_A_SET)
    tier_b = _load_set(_TIER_B_SET)
    tasks = {t["id"]: t for t in tier_a["tasks"] + tier_b["tasks"]}
    system, user = build_messages(args.arm.upper(), tasks[args.task])
    print(f"# system\n{system}\n\n# user\n{user}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p):
        p.add_argument("--timeout", type=float, default=300.0, help="seconds per model call")
        p.add_argument(
            "--max-repairs",
            type=int,
            default=2,
            help="repair rounds after a not-confirmed round 0 (default 2)",
        )
        p.add_argument(
            "--feedback",
            choices=FEEDBACK_LEVELS,
            default="G0",
            help="repair-feedback ladder: G0 = V13 text, G1 = value-free classes, "
            "G2 = G1 + checker leg classes (default G0)",
        )
        p.add_argument(
            "--runs-root",
            default=None,
            help="write into an existing run root (resume chunks) instead of a new "
            "timestamped one; naming a (task, arm, level) cell again replaces it",
        )

    batch = sub.add_parser("batch", help="run the pilot matrix")
    batch.add_argument("--arms", default="K,B,C")
    batch.add_argument("--reps", type=int, default=2)
    batch.add_argument("--task-ids", default=None, help="comma list of exact task ids (in order; skips the seeded shuffle and the tier caps; empty string falls back to the shuffle)")
    batch.add_argument("--tier-a", type=int, default=None, help="max Tier-A tasks")
    batch.add_argument("--tier-b", type=int, default=None, help="max Tier-B tasks")
    batch.add_argument(
        "--tasks",
        default="",
        help="comma-separated task ids (overrides the tier limits; order is kept)",
    )
    batch.add_argument("--seed", type=int, default=20260912)
    batch.add_argument("--skip-warmup", action="store_true")
    _common(batch)
    batch.set_defaults(func=cmd_batch)

    one = sub.add_parser("one", help="run one task x arm x rep")
    one.add_argument("--arm", required=True)
    one.add_argument("--task", required=True)
    one.add_argument("--rep", type=int, default=1)
    _common(one)
    one.set_defaults(func=cmd_one)

    dry = sub.add_parser("dry", help="print the messages of one run")
    dry.add_argument("--arm", required=True)
    dry.add_argument("--task", required=True)
    dry.set_defaults(func=cmd_dry)

    args = parser.parse_args(argv)
    # ``dry`` kennt kein --max-repairs; der Check gilt nur fuer die Lauf-Kommandos.
    if getattr(args, "max_repairs", 0) < 0:
        parser.error("--max-repairs must be >= 0")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

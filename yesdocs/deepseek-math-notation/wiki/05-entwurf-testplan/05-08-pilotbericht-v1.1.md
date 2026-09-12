---
topic: deepseek-math-notation
cluster: 05-entwurf-testplan
title: "Pilotlauf V1.1: Werkzeuge, Arme K/B/C, erste Messung der Denk-Sprache"
language: de
status: Verifiziert
last_updated: 2026-09-12
created_at: 2026-09-12
sources_count: 6
citations_count: 6
images_count: 0
diagrams_count: 0
related:
  - 05-07-denksprache-v1.1.md
  - 05-05-ablation-protokoll.md
  - 05-04-test-harness.md
  - 05-02-notations-spezifikation.md
  - ../01-modellprofil/01-03b-tokenizer-v11-lexeme.md
tags:
  - pilot
  - denksprache
  - v1.1
  - harness
  - msheet
  - messung
persona_review:
  personas_tested: ["Engineer (Baustufe W2/W3)", "Statistiker (Metrik-Sicht)"]
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Bau-/Pilotzyklus V1.1 (W5, 2026-09-12). Zahlen sind Rohdaten der Läufe; keine Signifikanz-Claims."
---

# Pilotlauf V1.1: Werkzeuge, Arme K/B/C, erste Messung der Denk-Sprache

Dieser Bericht schließt den Bau- und Pilotzyklus ab, den [05-07](05-07-denksprache-v1.1.md) (Entwurf), [05-05](05-05-ablation-protokoll.md) (Protokoll + Leiter) und [05-04](05-04-test-harness.md) (Harness-Spezifikation) vorbereitet haben. Er beschreibt zuerst die gebauten Werkzeuge (W1–W5), dann den Lauf, dann die Ergebnisse — deskriptiv, ohne Signifikanzbehauptungen (05-05 §5, Multiplizitätsregel).

## 1. Gebaute Werkzeuge (W1–W5)

| Werkzeug | Ort | Was es tut |
|---|---|---|
| **W1 Sonde** | `assets/01-03-messskript.py` (erweitert), Bericht [01-03b](../01-modellprofil/01-03b-tokenizer-v11-lexeme.md) | Misst die V1.1-Lexeme gegen den echten Tokenizer (168 Rohdaten-Zeilen; 42/42 Validierungsvektoren reproduziert). |
| **W2 msheet** | `bemyself/msheet/` (Package) | Der Runner: Blatt-Parser (Denkzone/Status/Behauptungszone), V1-Formelfragment (exakt, voll geklammert), Zeugen-Registry (`auto py range ref sim cyc`), Verdikt-Appendix, CLI. |
| **W3 Harness + Sets** | `yesdocs/deepseek-math-notation/tooling/`, `sets/` | Prompt-Builder der Arme, Aufgaben-Sets Tier A (16) und Tier B (12) mit eingefrorenem Gold, Batch-Runner mit Logs, Auswertung mit Wilson-Intervallen. |
| **W4 Pilot** | Dieser Bericht, Rohdaten unter `.yesmem/tmp/runs/` (gitignored) | 120 Läufe: Tier A 16×3×2, Tier B 8×3×1. |
| **W5 Doku** | Diese Datei + INDEX | Ergebnisse, Abweichungen, Grenzen, offene Punkte. |

**Zeugen** (05-07 §4) sind vollständig implementiert und getestet; die Erweiterbarkeit ist ein Rezept plus ein laufender Test (`tests/test_msheet_witnesses.py::RegistryTest`): ein neuer Zeuge = ein Recognizer + ein Executor + eine Registry-Zeile.

**Verdikt-Doktrin im Betrieb:** CONFIRMED nur bei exakter Prüfung. Belege aus dem Lauf: 12 REFUTED-`v`-Zeilen und 0 falsch-bestätigte Claims; `ref`-Promotionen wurden 5× mit `ref_unconfirmed` blockiert (Status `+` ohne ok-Prüfung); Guard-, Timeout- und Parse-Fälle liefen als `#?:`.

**Suite:** 554 Tests (Baseline vor dem Zyklus: 443, alle grün).

## 2. Lauf-Setup

- **Modell:** `deepseek-flash` (lokale Instanz). **Datum:** 2026-09-12, Tier A 16:39–16:50, Tier B 16:47–17:12 (Wanduhr, aus Logs).
- **Transport:** direkter HTTP-Pfad (`localhost:9099/v1/chat/completions`), nur unsere System-/User-Nachricht — **keine Werkzeuge**, kein YesMem-Sockel (~21–28k Tokens gespart; Abweichung zu [05-04](05-04-test-harness.md), dort „Auth ungeklärt": siehe §6). Reasoning-Tokens via `completion_tokens_details.reasoning_tokens`, Denktext via `reasoning_content`.
- **Sets:** Tier A `v11-a-0.1` (sha256 `50c985e169aa5007…`), Tier B `v11-b-0.1` (sha256 `074ab6bf5ebfc213…`). Tier A: deterministisch-generierte Bibliotheksaufgaben (Rechnung + Prüfformel). Tier B: 7 Trace-Aufgaben (bbchallenge-Maschinen, Gold-Konfigurationen zur Bauzeit per `turing.py` eingefroren) + 1 Zyklus-Aufgabe; gesampelt per Seed-Shuffle (8 von 12 — der schwere Übersetzer-Zyklus B-0011 wurde **nicht** gezogen, §5).
- **Arme:** K (übliche Prosa), B (V1: S-Zeilen, Langnamen), C (V1.1: Tag-Kopfzeilen, Kurz-Aliase, v-Zeugen). D (Zeugenpflicht) nicht gelaufen (Budget; §6).
- **Umfang:** Tier A 16 Aufgaben × 3 Arme × 2 Wiederholungen = 96; Tier B 8 × 3 × 1 = 24. Gesamt 120 Läufe, 554.537 Tokens (inkl. Reasoning). Pilot-Dauer ~33 min (Budget ≤2 h eingehalten).

## 3. Ergebnisse

### 3.1 Tier A (Mikro-Aufgaben; 96 Läufe)

| Arm | gelöst | Rate (95%-CI Wilson) | Dauer ø | Output ø | davon Reasoning ø | Formfehler-Blätter | Verdikte bestätigt/refutiert/unprüfbar |
|---|---|---|---|---|---|---|---|
| K | 32/32 | 1.00 (0.89–1.00) | 4.0 s | 1062 | 1055 | — | — |
| B | 29/32 | 0.906 (0.76–0.97) | 6.9 s | 1835 | 1682 | 0 | 29/0/3 |
| C | 27/32 | 0.844 (0.68–0.93) | 4.9 s | 1262 | 1198 | 0 | 54/0/10 |

**Fehleranatomie Tier A.** Kein einziger Formatfehler (Metrik d = 0 für B/C) — beide Notationsarme schrieben strukturell gültige Blätter. Alle Ausfälle sind **Zeugen-Ausfälle**:
- **B (3×):** `formula: expected ')', found '='` — der Beleg wurde wie `powmod(2,10,1000) = 24` ohne äußere Klammer in die CLAIM-Zeile geschrieben. Die strikte Behauptungszone lehnt ab (statt zu raten) → `#?:`.
- **C (5×):** `ref_unconfirmed` — das eigene `v`-Zeuge war unprüfbar (s. u.), `h1+` wurde trotzdem gesetzt, `ref` blockierte. Genau der Schutzwall, den die Promotion-Regel bezweckt.
- **Klammer-Reibung (Top-1-Befund):** Die unprüfbaren C-Zeugen sind fast alle Formeln der Art `((2^10)%1000 = 24)` — ein Klammerpaar zu wenig. Die Modell-Intuition setzt `(A % B = C)`; V1 verlangt `((A % B) = C)`. Betroffen: die `%`/`//`-Aufgaben (powmod). Achtung: das ist ein Messsignal, keine Panne — die Notation verlangt volle Klammerung, das Modell liefert sie bei `%`-Formeln nicht spontan.

### 3.2 Tier B (Testfeld-Fragmente; 24 Läufe)

| Arm | gelöst | Rate (95%-CI) | Dauer ø | Output ø | Formfehler-Blätter | Trace-Checkpoints exakt | Verdikte bestätigt/refutiert/unprüfbar |
|---|---|---|---|---|---|---|---|
| K | 8/8 | 1.00 (0.68–1.00) | 34.2 s | 8581 | — | **20/20** | — |
| B | 5/8 | 0.625 (0.31–0.86) | 71.0 s | 17791 | 6 | 13/20 | 0/0/0 (K-analog, ohne v) |
| C | 3/8 | 0.375 (0.14–0.69) | 78.4 s | 18672 | 0 | **8/20** | 7/12/3 |

**Befund:** Im harten Tier dreht sich das Bild: K (Prosa) simuliert die 2-Symbol-Maschinen fehlerfrei (20/20 Checkpoints), B und C verbrauchen mehr als doppelt so viele Output-Tokens, brauchen länger — und treffen weniger. C's `sim`-Zeugen **refuteten 12 eigene Checkpoint-Behauptungen** (der Runner lehnte sie korrekt ab; das Blatt war also ehrlich, aber falsch). Ohne Reparaturrunde (Single-Turn!) kann das Modell seine eigene Verifikation nicht nutzen — die Verifikation deckt Fehler auf, aber der Lauf endet mit ihnen.

**Muster in den Abweichungen:** C lief mehrfach in einen nahezu konstanten Kopfpositions-Offset (+2 nach dem ersten Checkpoint, z. B. B-0005: t=5 exakt, t=10/20 je +2; B-0003: +2/+2). Ein Teil der Fehler ist damit systematisch (Fenster-/Kopfzählung), nicht zufällig — Kandidat für eine Folgeuntersuchung (Kopf-Origin-Konvention im Legendentext präzisieren).

**Zyklus-Aufgabe:** Der einzige gesampelte Zyklus-Fall (B-0012, `0LA0LA`, Zertifikat (0,1,-1)) wurde von allen drei Armen gelöst; C am schnellsten (4,7 s; K 18,1 s, B 34,6 s) — und C lieferte als einziger Arm einen **maschinell geprüften** Beleg (`cyc(0,1,-1)` → CONFIRMED) statt einer Endantwort-Behauptung. Der schwere Übersetzer-Zyklus (44394115, (6,16,2), Aufgaben-ID B-0011) wurde vom Seed-Shuffle nicht gezogen — das Zertifikat-Werkzeug dafür ist aber gebaut und getestet (Test-Vektor aus P10).

## 4. Was die Werkzeuge geleistet haben (belegt)

1. **exakte Ausführung entscheidet Verdikte:** 12 REFUTED-Verdikte in C-B (falsche Checkpoints), 5 blockierte `ref`-Promotionen in C-A, 0 Falschbestätigungen — der Rückkanal `#ok/#xx/#?` ist im Einsatz.
2. **Formatstrenge messbar machen:** B's CLAIM-Klammerfehler und C's `%`-Klammerfehler wurden nicht „geheilt", sondern als UNVERIFIABLE gemessen — genau das ist die Messgröße d/e.
3. **Ende-zu-Ende-Verifikation** vom Blatt über Zeugen (`sim` gegen `turing.py`, `cyc` gegen die P10-Maschinerie) bis zur Promotion; die Beispielprüfungen aus [05-07](05-07-denksprache-v1.1.md) §9 laufen (Test + `tests/data/beispielblatt.msheet`).

## 5. Rohdaten und Reproduktion

- Läufe: `.yesmem/tmp/runs/20260912-163929/` (Tier A) und `.yesmem/tmp/runs/20260912-164755/` (Tier B), je `<task>/<arm>-rep<r>/{prompt.md,raw.json,parsed.json}`; `manifest.json` mit Set-Hashes. Auswertung: `evaluate.py --runs <dir>`.
- Sets: `sets/tier_a_v11-a-0.1.json`, `sets/tier_b_v11-b-0.1.json` (+ `build_sets.py` zur Neuerzeugung; Tier-B-Gold per `turing.py`, Zyklus-Zertifikate zur Bauzeit gegen `claimtypes.cycle` verifiziert).
- Harness: `tooling/harness.py` (Transport §2), `tooling/prompts.py` (Legenden aller vier Arme), `tooling/evaluate.py`.
- Beispiel für Zeugen-Durchlauf: `python3 -m bemyself.msheet run tests/data/beispielblatt.msheet` → `#ok: v1 v2 c1`, `#xx: c2`, `#?: c3`.

## 6. Abweichungen und Präzisierungen (dokumentiert)

| # | Abweichung/Präzisierung | Warum / Umfang |
|---|---|---|
| 1 | **Direkter Proxy-Transport** statt `opencode run` | Werkzeugfreiheit (Messintegrität), kein Systemprompt-Sockel, direkte Usage-Felder; verifiziert (HTTP 200 mit Bearer und x-api-key). Löst den 05-04-Vorbehalt „Auth ungeklärt" — Abweichung von der dort skizzierten CLI-Route. |
| 2 | **Arm D nicht gelaufen** | Budget (≤2 h) nach Kalibrierung; D ist implementiert (Legende + Aufgabenkonvention) und nachholbar. |
| 3 | **Tier B R=1** (statt 2) | Tier-B-Läufe dauern 26–167 s; Budget-Regel der Leiter („skalieren nach Kalibrierung"). |
| 4 | **Metrik c (Turns) nicht messbar** | Single-Call-Transport kennt keine Turn-Events; ersetzt durch Denkzeilen-/Marker-Zählung (Marker-Treue B-A 0.995, C-A 0.855) und `v`-Zeilen pro Blatt. Für Turn-Metriken wäre der Event-Stream der CLI nötig. |
| 5 | **Kanonisches Checkpoint-Format `cp t: (Q,p,T)` in allen Armen** | Ohne gemeinsame Extraktion wäre Trace-„Fidelity" nicht vergleichbar; K erhält es als Antwortkonvention, B/C als Zeugen-Syntax. |
| 6 | **Toleranzen im Blatt-Parser** (Interleaving von Denk-/Claim-Zeilen; `[HALT] c1,c2` mit Kommas) | Im Smoke beobachtete Modell-Gewohnheiten; als Stil, nicht als Formatfehler gewertet (Implementierungspräzisierung; Tests vorhanden). |
| 7 | **Tape-Vergleich bis auf führende/nachfolgende Nullen** | Modelle zählen geschriebene 0-Zellen zum Fenster; Wert ist identisch. Wertgleichheit, keine Näherung (Test). |
| 8 | **Zählregel für Zyklus-Aufgaben nachgeschärft** | Der Score verlangt zusätzlich, dass das Blatt die **Aufgaben-Maschine** bindet (ein selbstkonsistentes Blatt über eine andere Maschine zählt nicht). Nach dem Lauf ergänzt; der gesampelte Fall (B-0012) bindet die richtige Maschine, das Ergebnis ändert sich nicht. |
| 9 | **Generierte Tier-B-Maschinen aus Fenster [6, 500] Schritte** | Die Halte-Verteilung zufälliger Maschinen ist bimodal (fast nur ≤5 oder >500); lange Läufe liefern die kuratierten Maschinen (BB(5)-Champion etc.; S(6) > `2^^^5`, kein Halt im Horizont). |

## 7. Ehrliche Grenzen

- **Stichprobe klein** (32 bzw. 8 Läufe je Arm-Zelle), **ein Modell**, **ein Tag**, **eine Wiederholung** in Tier B; die Wilson-Intervalle überlappen breit. Keine Signifikanz-Aussagen, keine Verallgemeinerung über Arme.
- Der schwere Zyklus-Fall fehlt im Sample (Shuffle); Zyklus-Ergebnis ist ein Einzelpunkt.
- Tier A „gelöst" verlangt einen bestätigten Beleg, der den Erwartungswert enthält — K wird über die Endantwort geprüft. Das ist die dokumentierte Set-Konvention, kein Gütevergleich der Formate.
- Der Serving-Stand des Tokenizers ist wie in [01-03](../01-modellprofil/01-03-tokenizer-zahlen.md) nicht unabhängig verifiziert; die Sonde misst den veröffentlichten Stand.
- Der Lauf misst **eine Antwort** je Aufgabe (kein Reparatur-Loop); die Verifikationskraft der Notation kann sich in Single-Turn nicht entfalten (s. §3.2).

## 8. Offene Punkte (Kandidaten für die nächste Runde)

1. **Klammerregel für `%`/`//`-Vergleiche** präzisieren (Legendentext) oder eine eng definierte Toleranzklammer einführen — vorher: Reibung im Feld messen (D-Lauf).
2. **Arm D** laufen lassen (Zeugenpflicht) und mit C vergleichen.
3. **Kopf-Origin-Konvention** im Trace-Format expliziter machen (systematischer +2-Offset bei C).
4. **Reparaturrunde** (Multi-Turn oder Feed des `#xx/#?:`-Appendizes zurück ins Modell) — erst dann ist die Verifikations-These testbar.
5. Schweren Übersetzer-Zyklus (B-0011) gezielt in den nächsten Lauf zwingen.

## Quellen

1. Lokale Messung (2026-09-12): Pilot-Läufe `.yesmem/tmp/runs/20260912-163929`, `.yesmem/tmp/runs/20260912-164755` (120 Läufe, 554.537 Tokens); Auswertung `tooling/evaluate.py`.
2. Lokale Quelle: [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Entwurf, Lexeme, Kosten-Nullprobe, Doktrin.
3. Lokale Quelle: [05-05-ablation-protokoll.md](05-05-ablation-protokoll.md) — Arme/Legenden, A/B-Leiter, Metriken a–k, Multiplizitätsregel.
4. Lokale Quelle: [05-04-test-harness.md](05-04-test-harness.md) — Harness-Spezifikation (Transport, Sets, Artefakt-Regeln; Abweichung §6.1).
5. Lokale Quelle: [01-03b-tokenizer-v11-lexeme.md](../01-modellprofil/01-03b-tokenizer-v11-lexeme.md) — Tokenizer-Sonde der Lexeme (W1).
6. Lokale Quelle: `bemyself/msheet/` + `tests/test_msheet*.py`, `tests/test_v11_harness.py` — Engine, Zeugen, Harness-Tests (554 Tests grün).

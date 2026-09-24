---
topic: deepseek-math-notation
cluster: 05-entwurf-testplan
title: "Rückkanal-Runde V12: Reparatur-Loop, Arme K/B/C/D und die Messung des Rückkanals"
language: de
status: Verifiziert
last_updated: 2026-09-12
created_at: 2026-09-12
sources_count: 7
citations_count: 7
images_count: 0
diagrams_count: 0
related:
  - 05-08-pilotbericht-v1.1.md
  - 05-07-denksprache-v1.1.md
  - 05-05-ablation-protokoll.md
  - 05-04-test-harness.md
  - ../01-modellprofil/01-03b-tokenizer-v11-lexeme.md
tags:
  - reparatur-loop
  - rueckkanal
  - denksprache
  - v11
  - v12
  - harness
  - msheet
  - messung
persona_review:
  personas_tested: ["Engineer (Baustufe W6/R2)", "Statistiker (Metrik-Sicht)"]
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Runde-2-Zyklus (V12, 2026-09-12). Zahlen sind Rohdaten der Läufe; keine Signifikanz-Claims. Die Fairness-Entscheidung zu Arm B ist in §3 dokumentiert."
---

# Rückkanal-Runde V12: Reparatur-Loop, Arme K/B/C/D und die Messung des Rückkanals

[Diese Runde](../INDEX.md) schließt die in [05-08](05-08-pilotbericht-v1.1.md) §8 skizzierte Lücke: Der Pilot maß **eine Antwort** je Aufgabe — die Verifikationskraft der Denk-Sprache konnte sich in Single-Turn nicht entfalten (05-08 §3.2; dort refutierte C in Tier B zwölf eigene Checkpoints, ohne sie korrigieren zu können). Runde 2 baut den **Reparatur-Loop**: Nach jeder Runde prüft der Zeugen-Runner das Blatt; ist der Endzustand nicht bestätigt, folgt eine Reparaturrunde mit dem Verdikt-Appendix. Dieser Bericht beschreibt Werkzeuge, Design (inkl. Fairness-Entscheidungen), Lauf und Ergebnisse — deskriptiv, ohne Signifikanzbehauptungen (05-05 §5).

## 1. Auftrag und Kernfrage

Kernfrage: **Wird mit Rückkanal ein Effekt der Arme messbar?** Genauer: Können die Arme ihre eigenen maschinell geprüften Verdikte (bzw. K eine neutrale Selbstprüfung) nutzen, um nicht bestätigte Endzustände in Reparaturrunden zu korrigieren — und unterscheiden sich die Arme dabei?

## 2. Was gebaut wurde

| Werkzeug | Ort | Was es tut |
|---|---|---|
| Reparatur-Loop im Harness | `tooling/harness.py` (`run_rounds`) | Runde 0 wie der Pilot; ist der Endzustand nicht bestätigt, folgt eine Reparaturrunde mit dem Verdikt-Appendix (max. `--max-repairs 2`, Default). Multi-Turn über direkten Proxy; `messages`-Array mit eigener Antwort und Feedback. Stop, sobald bestätigt; Transport-Retry einmalig (05-05-Stopregel). Logs: `round<n>/{prompt.md,raw.json,parsed.json}` + `summary.json` je Lauf. |
| Rückkanal-Builder | `tooling/prompts.py` (`build_repair_message`) | K: neutrale Selbstprüfung („Prüfe deine Lösung erneut“, ohne Verdikte). B/C/D: „Der Zeugen-Runner hat dein Blatt geprüft“ +Appendix +Befunde +Formfehler. |
| Gold-Leak-Sanitizer | `tooling/harness.py` (`feedback_lines`) | `#xx`-Befunde werden saniert: `sim`-Refutungen nennen die echten Zustands-/Kopf-/Bandwerte, `cyc`-Refutungen Zertifikatsteile — beides **nicht** zurückfüttern. `#?`-Fehlertexte bleiben vollständig (Parser-/Formatgründe; enthalten keine Referenzwerte). |
| Legenden v0.2 | `tooling/prompts.py` | `%`-Klammerregel explizit (operandenweise `((A % B) = C)`); das frühere Legend-Beispiel `((2 ^ 10) % 1000 = 24)` war parser-invalid (Repro „expected ')', found '='“) und ist durch `(((2 ^ 10) % 1000) = 24)` ersetzt; cp-Zeitpunkt präzisiert: Konfiguration ist der Zustand **nach** dem Schritt (Schritt 0 = Startzustand). |
| Sets v0.2 | `tooling/build_sets.py`, `sets/tier_{a,b}_v11-*-0.2.json` | Neue `set_version` + sha256; Inhalte v0.1-gleich bis auf Hygiene: Lizenz generierter Tier-B-Maschinen CC0, Memory-ID in einer `source`-Zeile durch externe Referenz ersetzt. v0.1 eingefroren (Hash-Test). **B-0011** (schwerer Übersetzer-Zyklus) ist enthalten und wurde ohne Shuffle-Ausschluss gefahren. |
| Runden-Auswertung | `tooling/evaluate.py` | End-Trefferquote, Runden bis ok, Reparaturgewinn (R0 vs. final), `#xx`-Auflösungsrate, Tokens je Ergebnis; V11-Läufe (flaches Layout) bleiben auswertbar. |

Engine unverändert (`proofboy/msheet/`); Änderungen liegen in Tooling, Sets und Tests. Tests: `tests/test_v12_harness.py` (28 neue), Gesamt 607 Tests grün.

## 3. Design-Entscheidungen (Fairness)

- **K — gleiche Rundenzahl, keine Verdikte.** K bekommt denselben Reparatur-Loop (dieselbe Rundenzahl), aber eine neutrale Selbstprüfung ohne `#ok/#xx/#?`; Verdikte, die es für K nicht gibt, werden nicht erfunden. Ohne gleiche Rundenzahl wäre „Rückkanal“ mit „mehr Rechenzeit“ konfundiert.
- **C/D — maschineller Appendix.** Genau das Instrument der Runde: die eigenen, maschinell geprüften Verdikte.
- **B — eigener Claim-Appendix (deklarierte Entscheidung).** Der Auftrag ordnete nur K (neutral) und C/D (maschineller Appendix) zu; für B traf die Session die Entscheidung, B seine **eigenen maschinell geprüften Claim-Verdikte** zu geben — der Runner prüft B-Claims seit Pilot 1 (`ref`/`auto`), das Prinzip „keine Verdikte, die es nicht gibt“ bleibt. Damit steht der Notation-Kontrast B↔C↔D in **beiden Phasen** (R0 und Reparatur) identisch zur Verfügung; die Alternative (B wie K) hätte Notation und Rückkanal gleichzeitig variiert. Die Entscheidung wurde vor dem Lauf gestellt und nicht widersprochen.
- **Reparatur-Trigger.** Nur der **Endzustand** triggert (Tier A: alle Claims bestätigt und Erwartungswert im Claim; Tier B trace: alle Gold-Checkpoints exakt; Tier B cyc: Claim bestätigt und Maschinenbindung; K jeweils über die Endantwort). Einzige Ausnahme, um im Kostenmaß fair zu bleiben: Läufe ohne auswertbare Modellausgabe werden nicht wiederholt außer dem einen Transport-Retry. **Formfehler** triggern nicht automatisch (Erfolgsdefinition der Aufgabe), sie sind aber Teil des Rückkanals, wenn eine Reparatur stattfindet. Konsequenz, ehrlich: C/D verifizieren im Trace-Fall ihre cp-Zeilen auch bei formfehlerfreiem Blatt, erhalten also in Runde 0 mehr Maschinenchecks als B — das ist genau der dokumentierte Unterschied der Notationsstufen (05-05), nicht des Rückkanals.
- **Gold-Leak-Schutz** (s. §2): referenzwertfreie Rückfütterung; die Beispiele in §5 zeigen, dass die Korrektur aus eigenem Nachrechnen stammt.
- **Kein Gold-Leak durch die Legenden selbst:** unverändert; K sah in keiner Runde `#`-Verdikte.

## 4. Lauf

- Modell `deepseek-flash`, direkter Proxy `localhost:9099` (Transport aus Pilot 1), Reasoning-Verlauf beim Rückkanal ausgelassen (DeepSeek-Konvention; Smoke: beide Varianten HTTP 200).
- Tier A 16 Aufgaben × 4 Arme × 2 Wiederholungen; Tier B 12 Aufgaben × 4 Arme × 1 Wiederholung; max. 2 Reparaturrunden. Tier B zuerst (dort sitzt die These).
- Wall-Clock: Tier B 18:25–19:02 (~37 min), Tier A 19:03–19:15 (~11,5 min); zusammen **~48 min** (Budget ≤2 h eingehalten). Modellzeit zusammen ~42 min.
- Ausfälle: **0** Rundenergebnisse mit Transportfehler; **1** Transport-Retry (B-0011/K, danach erfolgreich). Keine abgebrochenen Läufe.
- Rohdaten: `.yesmem/tmp/runs-v12-20260912/{tier-b-182506,tier-a-190257}/` (Kopien; Auswertungs-Assets [05-09-eval-tierA.md](assets/05-09-eval-tierA.md), [05-09-eval-tierB.md](assets/05-09-eval-tierB.md)).
- Sets: v11-a-0.2 sha256 `007424292fd10129…`, v11-b-0.2 sha256 `68eb917ebd26ae2d…` (im `manifest.json` beider Läufe).

## 5. Ergebnisse

### 5.1 Tabellen (Auszug; vollständig in den Assets)

Tier A (n = 32 je Arm):

| Arm | R0 gelöst | Final gelöst | repariert | Runden bis ok (0/1/2/offen) | Tokens gesamt |
|---|---|---|---|---|---|
| K | 32 | 32 | 0 | 32/0/0/0 | 25 667 |
| B | 31 | 32 | 1 | 31/1/0/0 | 72 204 |
| C | 32 | 32 | 0 | 32/0/0/0 | 46 774 |
| D | 32 | 32 | 0 | 32/0/0/0 | 46 971 |

Tier B (n = 12 je Arm):

| Arm | R0 gelöst | Final gelöst | repariert | Runden bis ok (0/1/2/offen) | `#xx`-Auflösung | Tokens gesamt |
|---|---|---|---|---|---|---|
| K | 11 | 12 | 1 | 11/1/0/0 | 0/0 | 107 830 |
| B | 12 | 12 | 0 | 12/0/0/0 | 0/0 | 124 690 |
| C | 11 | 12 | 1 | 11/1/0/0 | **3/3** | 131 924 |
| D | 12 | 12 | 0 | 12/0/0/0 | 0/0 | 94 693 |

Trace-Ebene (Tier B, R0, exakt getroffene Gold-Checkpoints über die 10 Trace-Aufgaben, 29 Prüfpunkte): K 27/29, B 29/29, C 26/29, D 29/29.

**Falschbestätigungen: 0** über alle 179 Runden (176 Läufe + 3 Reparaturrunden; Definition wie Pilot: alle Verdikte bestätigt, aber der Endzustand ist es nicht — kein solcher Fall).

### 5.2 Der Rückkanal wurde dreimal live gebraucht — und löste jedes Mal

1. **A-0012/B (Tier A, Wiederholung 2):** R0 schrieb die Behauptung mit ungeklammertem Vergleich `((…) * 10) = 3628800` → `#?: c1` mit Fehlertext „formula: trailing text after the formula: '='“. Runde 1 antwortete `(factorial(10) = 3628800)` → `#ok: c1`. Der Fehlertext (ohne Gold) trug die Korrektur.
2. **B-0003/C (Tier B trace, Marxen&Buntrock):** R0 hatte alle drei Checkpoints falsch (u. a. `(D,1,111)` statt `(B,-1,1111)`); Rückkanal: `#xx: v1 v2 v3`, `#?: c1 c2 c3` + sanierte sim-Befunde („die Konfiguration bei Schritt 5 stimmt nicht mit der Referenzsimulation überein“ — ohne Werte). Runde 1 korrigierte alle drei Checkpoints, verifizierte sie erneut mit `sim(0..5/10/20)` → 3/3 Gold-Checkpoints. **`#xx`-Auflösung 3/3.**
3. **B-0001/K (Tier B trace):** R0 `(A,-1,0)`/`(A,-2,0)` falsch; neutrale Selbstprüfung ohne Verdikte; Runde 1 `(B,1,1)`/`(A,0,1)` → 2/2. Zeigt: der Loop selbst (gleiche Rundenzahl) hilft auch ohne Maschinenverdikte — K wird durch das Design nicht benachteiligt.

Dazu (nicht Teil des Laufs): eine Live-Probe vor dem Lauf, die das echte Pilot-1-Fehlerblatt (A-0006/C, kaputte `%`-Klammer) mit echtem Feedback und echter Proxy-Runde 1 konfrontierte → korrigiert, `#ok` (2,2 s).

### 5.3 Beobachtung: B-0011 wird von der Notation getragen

Der in 05-08 §8.5 geforderte schwere Übersetzer-Zyklus (5 Zustände, Zertifikat (6,16,2)) lief ohne Shuffle-Ausschluss. Ergebnis R0, je Arm ein Lauf:

| Arm | Antwortform | completion Tokens | Dauer |
|---|---|---|---|
| K | `cp 6: … cp 16: … Endantwort: NICHT-HALTEND (t1=6,t2=16,d=2)` | 25 654 | 103,8 s |
| B | Trace + Zertifikat in Prosa | 24 073 | 102,1 s |
| C | `a: M = …` `h1: M zyklisch (Translation)` `v h1: cyc(6,16,2)` `h1+` `CLAIM c1: …` `[HALT] c1` | **576** | **3,0 s** |
| D | wie C (Zeugenpflicht) | **852** | 3,9 s |

Auch K und B lösten die Aufgabe (R0) — aber C/D formulierten sie in einem Bruchteil der Tokens und Zeit. Das Zertifikat war in der Aufgabenstellung vorgegeben; die Arme prüfen es (C/D per `cyc`-Zeugen). Einzeldaten, keine Signifikanz — aber es ist die bislang stärkste Beobachtung zur Token-Ökonomie der Notation.

### 5.4 Vergleich mit Pilot 1 (mit Vorsicht)

| Arm | Tier A R0 Pilot (v0.1) | Tier A R0 V12 (v0.2) | Tier B R0 Pilot (8 Aufgaben) | Tier B R0 V12 (12 Aufgaben) |
|---|---|---|---|---|
| K | 32/32 | 32/32 | 8/8 | 11/12 |
| B | 29/32 | 31/32 | 5/8 | 12/12 |
| C | 27/32 | 32/32 | 3/8 | 11/12 |
| D | — | 32/32 | — | 12/12 |

Zwischen den Läufen liegen **zwei Änderungen**: Legenden v0.2 (`%`-Regel, cp-Zeitpunkt) und der Rückkanal. Die R0-Zeilen sind vom Rückkanal unberührt — sie spiegeln die Legend-Korrekturen. Vorsicht: verschiedene Legenden-Versionen, teils andere Aufgaben-Unterauswahl in Tier B (8 vs. 12 inkl. B-0011), eine Wiederholung in Tier B, ein Modell, ein Tag. Die Pilot-Fehler von B/C in Tier A waren fast alle `%`-Klammerfälle; die v0.2-Regel adressiert exakt sie, und beide Arme liefern nun 31–32/32. K blieb unverändert bei 32/32 (kein Formelpfad) — konsistent damit, dass die Legend-Korrektur und nicht die Runde den Ausschlag gab.

## 6. Was belegt ist — und was nicht

Belegt (Rohdaten in `.yesmem/tmp/runs-v12-20260912/`, Assets):
1. Der Reparatur-Loop funktioniert über den echten Proxy: 3 Live-Reparaturen, alle drei erfolgreich; `#xx`-Auflösung 3/3 im einzigen Fall mit Refutationen (C/B-0003).
2. Kein Gold-Leak: die sanierten Befunde nannten keine Referenzwerte; die Korrekturen kamen aus eigenem Nachrechnen (B-0003: erneutes `sim`).
3. 0 Falschbestätigungen über 179 Runden (176 Läufe + 3 Reparaturrunden).
4. Endzustände: **176/176 Läufe final bestätigt** (Tier A 128/128, Tier B 48/48), 4 Reparaturen nötig und erfolgreich (A-0012/B, B-0001/K, B-0003/C; plus die Vorsonde).

Nicht belegt:
- **Kein Arm-Unterschied in der End-Trefferquote** — sie ist überall 1,0. Die Stichproben sind klein (Tier B n = 12), die Wilson-Intervalle überlappen breit; die Zellen sind nicht unabhängig (dieselben Aufgaben je Arm).
- **R0-Unterschiede zwischen den Legend-Versionen sind nicht kausal isoliert** (V12 änderte Legenden und Runde zugleich; Vergleich in §5.4 ist deskriptiv).
- **Rückkanal wurde selten gebraucht** (3 von 176): R0-Raten liegen mit v0.2 bei 92–100 %. Die Runde zeigt vor allem, *dass* der Loop repariert, wenn er nötig ist — nicht, wie stark er bei schwereren Aufgaben trägt.
- Tier B „Formfehler“ bei Arm B (10/12 R0-Läufe) sind die beabsichtigte claim-lose Trace-Konvention (B verifiziert die cp-Zeilen nicht maschinell); sie sind kein Fehlerbild der Aufgabe, aber ein Instrumentierungs-Hinweis fürs nächste Set.

## 7. Offene Punkte (Kandidaten für die nächste Runde)

1. **Erfolgs-/Triggerdefinition trennen:** In B-Trace-Läufen mit 3/3 Checkpoints und Formfehlern („no claim zone“) wurde nicht repariert — bewusst (Erfolgsdefinition), aber für ein „Blattqualitäts“-Ziel wäre ein Formfehler-Trigger als eigene Metrik sinnvoll.
2. **Schwerere Zellen:** R0 sättigt mit v0.2 an der Decke (92–100 %). Die nächste Runde braucht Aufgaben, bei denen R0 messbar scheitert (längere Horizonte, mehrere CPs, Zertifikate selbst suchen), sonst ist der Reparaturgewinn nicht messbar.
3. **Rückkanal-Varianten:** (a) nur `#xx/#?`-Zeilen ohne Befunde, (b) Befunde mit, (c) Rückkanal ohne eigene Vorrunden-Antwort („frischer Versuch mit Appendix“) — welche Komponente trägt?
4. **K-Fairness weiter messen:** K fiel in Tier B auf 11/12 (R0) und reparierte selbst; bei größerem n prüfen, ob gleiche Rundenzahl für K über die Zelle hinweg fair trägt.
5. **B-0011-Instrumentierung:** Der Fall zeigte die Token-Ökonomie; Zyklus-Aufgaben ohne vorgegebenes Zertifikat wären der härtere Test.
6. **Sanitizer als Allowlist statt Denylist:** Der Gold-Leak-Schutz deckt heute die bekannten werthaltigen Refutationsgründe ab (`sim`, `cyc`); eine neue Zeugenart mit Referenzwerten würde per Default durchgelassen. Vor der nächsten Reparaturrunde auf „standardmäßig saniert, Allowlist für Inhalt“ umstellen; der in der Review gefundene Kollisionsfall (Claim-id = v-Line-id) ist bereits behoben und getestet.

## Quellen

1. Lokale Messung (2026-09-12): V12-Läufe `.yesmem/tmp/runs/20260912-182506` (Tier B, 48 Läufe) und `.yesmem/tmp/runs/20260912-190257` (Tier A, 128 Läufe), gesichert unter `.yesmem/tmp/runs-v12-20260912/`; 650 753 Tokens; Auswertung `tooling/evaluate.py`.
2. [05-08-pilotbericht-v1.1.md](05-08-pilotbericht-v1.1.md) — Pilot 1 (Arme K/B/C, Single-Turn; Single-Turn-Grenze §3.2, offene Punkte §8).
3. [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Denk-Sprache V1.1 (Tags, Status, Zeugenformen).
4. [05-05-ablation-protokoll.md](05-05-ablation-protokoll.md) — Arme/Legenden, Metriken, Multiplizitätsregel.
5. [05-04-test-harness.md](05-04-test-harness.md) — Harness-Spezifikation (Transport, Sets, Artefakt-Regeln).
6. `tests/test_v12_harness.py`, `tooling/{harness,prompts,build_sets,evaluate}.py`, `proofboy/msheet/` — Implementierung + Tests (607 Tests grün).
7. [../01-modellprofil/01-03b-tokenizer-v11-lexeme.md](../01-modellprofil/01-03b-tokenizer-v11-lexeme.md) — Tokenizer-Sonde der Lexeme.

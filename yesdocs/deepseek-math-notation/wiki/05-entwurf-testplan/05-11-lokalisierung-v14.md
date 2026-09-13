---
topic: deepseek-math-notation
cluster: 05-entwurf-testplan
title: "Lokalisierungs-Runde V14: der Rückkanal lernt Klassen — Feedback-Leiter G0/G1/G2, Bindungsschutz und Sets v0.4"
language: de
status: Verifiziert
last_updated: 2026-09-13
created_at: 2026-09-13
sources_count: 8
citations_count: 12
images_count: 0
diagrams_count: 0
related:
  - 05-10-haerte-runde-v13.md
  - 05-09-rueckkanal-runde-v12.md
  - 05-07-denksprache-v1.1.md
  - 05-05-ablation-protokoll.md
  - 05-04-test-harness.md
  - ../01-modellprofil/01-03b-tokenizer-v11-lexeme.md
tags:
  - lokalisierung
  - rueckkanal
  - feedback-leiter
  - bindungsschutz
  - reparatur-loop
  - denksprache
  - v11
  - v14
  - harness
  - sets
persona_review:
  personas_tested: ["Engineer (Baustufe W6/R3)", "Statistiker (Metrik-Sicht)"]
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Runde-4-Zyklus (V14, 2026-09-13). Zahlen sind Rohdaten des Laufs; keine Signifikanz-Claims (Zellgröße 1). Abweichungen (B4-0001-Timeouts, G2 nicht live konfrontiert, paralleler Fremdlauf am Endpunkt) sind in §4 und §6 offengelegt."
---

# Lokalisierungs-Runde V14: der Rückkanal lernt Klassen — Feedback-Leiter G0/G1/G2, Bindungsschutz und Sets v0.4

[Diese Runde](../INDEX.md) zieht den offenen Punkt 7 aus [05-10](05-10-haerte-runde-v13.md) §7 („Der Reparatur-Rückkanal schützt Werte nicht“) und den Varianten-Strang aus [05-09](05-09-rueckkanal-runde-v12.md) §7.3: Der Rückkanal soll **lokalisieren statt verschweigen** — der Runner kennt den Unterschied zwischen „nicht geprüft“ (`UNVERIFIABLE`) und „widerlegt“ (`REFUTED`) und soll ihn aussprechen, ohne je Referenzwerte zu nennen. Gebaut ist eine dreistufige Feedback-Leiter (G0 = V13-Stand, G1 = wertfreie Klassen, G2 = Klassen + Positions-Legs), ein Bindungsschutz für maschinengültige, aber ungebundene Funde, die erweiterte harte Zyklus-Familie als Set v0.4 und ein empirischer Leck-Scan über die Feedback-Logs. Deskriptiv, ohne Signifikanzbehauptungen ([05-05](05-05-ablation-protokoll.md) §5).

## 1. Auftrag und Kernfrage

Zwei Fragen: **(1) Leckfrei lokalisieren** — kann der Rückkanal sagen, *welche Art* von Befund vorliegt (Bindung fehlt / Werte widerlegt / welche Vergleichs-Bedingung trägt nicht), ohne ein einziges Gold-Token zu nennen? **(2) Reparaturen retten** — hilft die Lokalisierung auf harten Zyklus- und Bindungsfällen, oder zerstört sie wie in V13 validen Fundwert? Der V13-Befund war die Negativ-Referenz: im Bindungsfall adressierte die Rückmeldung die Form („no machine binding“) und das Blatt änderte beim Neuformulieren die — nie widerlegten — Zertifikatswerte.

## 2. Was gebaut wurde

1. **Feedback-Leiter (`--feedback G0|G1|G2`, Default G0)** in `tooling/harness.py`: G0 ist der V13-Text unverändert (Regressionstest pinnt die Originalzeilen, s. §5.5). G1 ersetzt die vier bekannten Befund-Klassen durch wertfreie Klassenphrasen: `binding_missing` („keine Maschinenbindung im Blatt: die genannten Werte sind nicht widerlegt, nur nicht geprüft“), `values_refuted` („das Zertifikat ist widerlegt“), `binding_wrong` (Blatt bindet eine fremde Maschine — Harness-Ebene, G1+), Form-/Kettenbefunde unverändert. G2 ergänzt die Positions-Klasse aus der **Branch-Reihenfolge des Checkers** (`claimtypes.cycle` prüft Zustand → Kopf/Translation → Band → Halt; `witnesses._run_sim` analog): „widerlegt an der Zustands-Bedingung / der Translations-Bedingung / der Band-Bedingung“. Die sim-Schrittnummer bleibt (modell-eigen, [05-10](05-10-haerte-runde-v13.md) §5.3).
2. **Bindungsschutz:** Bei reinem Bindungsmangel (Zertifikat maschinengültig, nur die `a: M = …`-Zeile fehlt) hängt G1/G2 eine eigene Hinweis-Zeile an: „ergänze nur die Maschinenbindung und ändere die genannten Werte nicht — sie sind nicht widerlegt, nur ungeprüft.“ Der Unterschied `UNVERIFIABLE` vs. `REFUTED` wird in den Texten jetzt ausgesprochen.
3. **Sets v0.4** (`tooling/build_sets.py`, `sets/tier_b_v11-b-0.4.json`): Marxen-Trace-Kontrolle (B3-0002), Bindungs-/Ankerfälle B3-0005/B3-0008 (aus v0.3 übernommen, IDs erhalten) und drei neue Uebersetzer-Zyklen: B4-0001 `1RB1LC_1RD0LC_1RB1LB_1LC1RD` (Zertifikat 65,81,−2), B4-0002 `1LC1RD_1RZ0LZ_1RA1LC_0RC1RC` (14,21,−1) — beide aus einem **deterministischen Suchlauf** mit eingefrorener Saat (Attempt-Zählung statt Wall-Clock, Zertifikat in `source` dokumentiert; Reproduktion per `build_sets.py --search`) — sowie B4-0003 `1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC` (6,16,2; bbchallenge-Wiki „Translated cycler“, Zertifikat lokal re-deriviert). Alle Zertifikate zur Bauzeit per `cycle.check` bestätigt; v0.1–v0.3 bleiben byte-identisch (Hash-Test). Damit ist auch [05-10](05-10-haerte-runde-v13.md) §7.6 (Suchskript statt Prosa-Angabe) geschlossen.
4. **Leck-Scan (`tooling/scan_feedback.py`)**: prüft jeden `next_feedback`-Text eines Lauf-Baums gegen die Referenzwerte der Aufgabe (Zertifikatswerte; bei Trace-Aufgaben Gold-Bandfenster ab 4 Zeichen und Kopfpositionen). Id-/Schritt-Kontexte (Ziffer klebt an Buchstabe: `v1`, `h1`; Schlüsselwörter „Schritt/Step/Zeile/Line“; Schritt in Klammern: `sim(0..2)`) gelten als modell-eigen und werden als erklärt berichtet — **alles andere zählt als Verletzung** (konservativ, nachgeschärft in dieser Runde: die erste Fassung hätte „Zertifikat 34“ als id-Kontext durchgewinkt — der Unterschied ist testgepinnt).
5. **Auswertung:** `evaluate.py` gruppiert G1/G2-Zellen als `Arm-Level-Tier` (G0 bleibt `Arm-Tier`), meldet zusätzlich die **Bindungsschutz-Metrik** (Runde 0 mit maschinengültigem Zertifikat, aber ungelöstem Endzustand; „geschützt“ = final gelöst) und ein Klassen-Histogramm der Leiter.

## 3. Design-Entscheidungen (Leckfreiheit und Fairness)

- **G0 bleibt die Referenz.** Der CLI-Default ist G0; die V13-Texte werden byte-identisch erzeugt (Beweis §5.5). Alle Aussagen der Runde sind Vorher-Nachher-Vergleiche gegen diesen Anker.
- **Lokalisierung nur aus Checker-Semantik, nie aus Werten.** Jede Klassenphrase ist digit-frei; die Klassifikation liest ausschließlich die Reason-Branches, deren Texte in Tests gegen die echten Checker-Ausgaben gepinnt sind. Trifft keine Klasse, fällt der Text auf den V13-Default-Deny-Sanitizer zurück — die Leiter kann keine neue Leck-Fläche öffnen.
- **Bewusst gestrichen:** eine Klasse „t1 liegt nicht am Zyklus-Eintritt“ — der Checker kennt keinen solchen Zweig, und die Aussage bräuchte den echten (Gold-nahen) Eintritt. Ebenso bleibt der ganze `sim`-Step modell-eigen (nie Gold).
- **Bindungsschutz nur als Anweisung, nie als Beweis.** Der Hinweis behauptet nichts über die Werte — er sagt, dass sie *nicht widerlegt* sind (wahr: der Runner hat sie nicht geprüft) und dass die Bindung fehlt (wahr).
- **Verdikt-Doktrin unangetastet:** die Leiter ändert keinen Text der Erfolgsdefinition; `evaluate`-Zahlen bleiben über alle Level vergleichbar.

## 4. Lauf

- **Lauf:** `.yesmem/tmp/runs/20260913-095428` (Modell `deepseek-flash`, Arme K/B/C/D, 1 Wiederholung, `max_repairs 2`, Timeout 300 s je Call, Saat 20260913; Set v0.4 sha256 `cafc8aa8…`; Tier A unverändert v0.3, keine A-Aufgaben gelaufen).
- **Zellen:** G0-Matrix = 6 Aufgaben × 4 Arme (B4-0001 nur C/D versucht, beide Timeouts); Leiter-Zellen = C@G1 × {B3-0008, B4-0003}, C@G2 × {B3-0008, B4-0003}, D@G2 × {B4-0003}. **25 gültige Läufe, 1 776 851 Completion-Tokens, 6 403 s Modellzeit (107 min).**
- **Abweichungen (offengelegt):** (a) **B4-0001 ist nicht messbar**: alle vier Versuche (C, D, je zweimal) liefen in den 300-s-Call-Timeout ohne Tokens; K/B wurden aus Budgetgründen nicht gefahren. Der Fall bleibt im Set (nächste Runde: höherer Timeout). (b) **4 Timeout-Läufe** insgesamt; zwei wurden erfolgreich wiederholt (B3-0008/B, B4-0003/C), zwei bleiben ungültig (B4-0001 C/D, als Artefakt unter `.yesmem/tmp/runs-invalid-20260913/` gesichert). (c) Zeitweise lief ein **paralleler Fremdlauf** (anderer Worktree, gleicher Modell-Endpunkt) — plausibler Mitverursacher der Timeouts; dokumentiert, nicht weggerechnet. (d) Ein Hintergrund-Start des Laufs wurde vom Shell-Timeout mitgekillt; der Lauf wurde mit neuem `--runs-root`/`--tasks`/`one`-Resume in Chunks gefahren (Harness dafür um `--runs-root` und Task-Filter erweitert).
- **Kostenlage:** 107 min gültige Modellzeit liegen unter dem Runden-Budget von 2,5 h; die Wanduhr des Laufblocks betrug 09:54–13:10 (inkl. Chunk-Neustarts und Fremdlauf-Kontention).

## 5. Ergebnisse

### 5.1 G0-Matrix (Rohdaten; vollständig in den Assets)

| Aufgabe | K | B | C | D |
|---|---|---|---|---|
| B3-0002 (Marxen-Trace, Kontrolle) | R0 ok (89 s) | R0 ok (65 s) | R0 ok (67 s) | R0 ok (89 s) |
| B3-0005 (Anker 0LA0LA) | R0 ok (66 s) | R0 ok (35 s) | R0 ok (39 s) | R0 ok (25 s) |
| B3-0008 (t2=37, hart) | **offen** (3 Rd, 780 s) | R0 ok (215 s) | **repariert** (2 Rd, 449 s) | R0 ok (272 s) |
| B4-0002 (t2=21, neu) | **offen** (3 Rd, 729 s) | **offen** (3 Rd, 507 s) | R0 ok (257 s) | R0 ok (246 s) |
| B4-0003 (5-Block, lang) | R0 ok (178 s) | R0 ok (201 s) | **repariert** (2 Rd, 403 s) | **repariert** (2 Rd, 552 s) |
| B4-0001 (t2=81, neu) | — | — | Timeout | Timeout |

Aggregat (Assets): C: R0 3/5, final **5/5** (+40 pp Reparaturgewinn); D: R0 4/5, final 5/5; K: 3/5 final (beide harten neuen Zyklen offen); B: 4/5 final. Die neuen Aufgaben trennen die Arme: B4-0002 offen für K und B, gelöst für C und D — während K und B auf B4-0003 (lange Maschine, kurzes Zertifikat) bestehen.

### 5.2 Die V13-Regression ist weg — vorerst

Alle drei G0-Reparaturfälle dieser Runde (B3-0008/C, B4-0003/C, B4-0003/D) starteten exakt im V13-Muster: maschinengültiges Zertifikat, keine `a: M = …`-Zeile, Rückmeldung „`v1: cyc: no machine binding in the sheet (expected 'a: M = <machine>')`“ plus Ketten-Note — und **behielten die Werte**; nach Ergänzen der Bindung war die Runde gelöst. Der in V13 beobachtete Wertverlust trat in dieser Runde nicht auf (Zellgröße 1 — ein Beleg für „tritt nicht deterministisch auf“, kein Beweis für „behoben“). Die Bindungsschutz-Metrik zählt genau solche Fälle: **G0: C 2/2, D 1/1 geschützt.**

### 5.3 Leitervergleich (die Reparaturfälle, Zellgröße 1)

| Zelle | G0 (V13-Text) | G1 (Klassen) | G2 (Klassen + Leg) |
|---|---|---|---|
| B3-0008 · C | 2 Runden, 449 s, 123 k Tok | 2 Runden, 485 s, 157 k Tok | **1 Runde**, 180 s, 51 k Tok |
| B4-0003 · C | 2 Runden, 403 s, 114 k Tok | 1 Runde, 169 s, 47 k Tok | 1 Runde, 173 s, 44 k Tok |
| B4-0003 · D | 2 Runden, 552 s, 175 k Tok | — | 1 Runde, 133 s, 34 k Tok |

Kein Rückschritt in keiner Zelle; alle sieben Leiter-Zellen final gelöst. Interessant: Die R0-Fehlbilder **wechseln** zwischen Wiederholungen derselben Zelle — B3-0008/C scheiterte unter G0 als `binding_missing` (gültiger Fund ohne Bindung, repariert) und unter G1 als `values_refuted:state` (echt falscher Wert, ebenfalls repariert). Die Klassen treffen also beide Fehlbilder, die der V13-Sanitizer beide nur als „trägt nicht“ zeigte.

### 5.4 Der Live-G1-Text (wörtlich)

```
Befunde:
v1: cyc: das Zertifikat ist widerlegt (es traegt fuer diese Maschine nicht)
c1: ref h1: ref_unconfirmed (last status '+', last verdict REFUTED)
```
— gegenüber G0 im Bindungsfall: `v1: cyc: no machine binding in the sheet (expected 'a: M = <machine>')` + `#?: v1 c1`. Der Unterschied, den die Runde will: „widerlegt“ heißt widerlegt, „ungeprüft“ heißt ungeprüft — und im Bindungsfall steht die „Werte nicht ändern“-Zeile daneben. **G2 wurde im Lauf nie mit einer Rückmeldung konfrontiert** (alle drei G2-Zellen lösten in Runde 0); die G2-Texte sind über Property-/Integrationstests (echte Checker-Reasons durch `run_rounds`) und Dry-Runs belegt, nicht über einen Live-Zyklus — offener Punkt §7.

### 5.5 Leck-Eigenschaft (Property + Empirie)

- **Property (Tests, `tests/test_v14_harness.py`, 41 Tests):** synthetische Verletzungsserien über alle Legs und Bindungslücken für G0/G1/G2 — kein Gold-Token im Feedback; Klassenphrasen digit-frei; unbekannte Beleg-Arten bleiben Default-Deny-zurückgehalten; G0-Ausgabe zeilengleich mit dem rekonstruierten V13-Text.
- **Empirie (Scan):** V14-Lauf 10 Rückmeldungstexte → **0 Verletzungen, 0 erklärte Treffer**; Querprobe V13-Lauf (`runs-v13-20260912/tier-b-hard`) 7 Texte → 0 Verletzungen, 2 erklärte Treffer (`line 0:`-Formatzeilen). Der Scan ist als Werkzeug getestet (injizierte Gold-Nennung wird gefunden; id-Kontexte erzeugen keine Fehlalarme).
- Gesamtsuite: **859 Tests grün** (vor der Runde 818).

## 6. Was belegt ist — und was nicht

**Belegt:** Die Leiter existiert, G0 ist byte-treu der V13-Stand; alle Klassen sind aus Checker-Semantik abgeleitet und wertfrei (Property-Tests + Log-Scan); die Schutzanweisung erscheint genau im Bindungsfall; im Lauf wurde keine Rückmeldung mit Gold-Token erzeugt; die neuen Zyklus-Aufgaben sind maschinen-verifiziert, deterministisch erzeugt und leckfrei im Prompt; Reparaturen auf harten Fällen gelangen in allen Leveln (7/7 Leiter-Zellen final gelöst), K/B scheitern an den neuen harten Zyklen.

**Nicht belegt (Zellgröße 1, kein Signifikanz-Claim):** dass G1/G2 *ursächlich* schneller retten als G0 (die R0-Erfolge der G2-Zellen sind Stichproben-Varianz); dass die V13-Regression „behoben“ ist (nur: in diesem Lauf nicht aufgetreten); die G2-Leg-Texte im Live-Rückkanal (nie konfrontiert); B4-0001 (nicht messbar, s. §4).

## 7. Offene Punkte (Kandidaten für die nächste Runde)

1. **G2 live konfrontieren:** Zellen mit erwarteten R0-Fehlern wählen (z. B. hartes Zertifikat auf dem schwächeren Feedback-Arm oder mehrere Wiederholungen je Zelle), damit die Leg-Texte einen echten Reparaturzyklus durchlaufen.
2. **B4-0001 messbar machen:** Timeout-Zelle je Aufgabe (z. B. 600–900 s) oder Kosten-Obergrenze je Zelle; bis dahin bleibt der Fall ohne Datenpunkt.
3. **Wiederholungen statt Breite:** Die R0-Fehlbilder streuen zwischen Wiederholungen (binding_missing vs. values_refuted:state auf derselben Zelle). Für die Reparatur-Frage wären 2–3 Wiederholungen auf wenigen harten Zellen aussagekräftiger als eine breite Matrix.
4. **Rückkanal-Varianten (05-10 §7.2):** „nur `#xx`/`#?`-Zeilen ohne Befunde“ ist jetzt abgedeckt (G0 vs. G1/G2), offen bleibt „frischer Versuch mit Appendix“.
5. **Formfehler-Trigger (05-09 §7.1, weiter offen):** Formverletzungen als eigene Metrik ziehen.
6. **Grenzen der Lokalisierung:** Was der Checker strukturell nicht weiß, kann er nicht lokalisieren (t1-Eintrittszeit; Ursachen jenseits der Vergleichs-Bedingungen). Die nächste Stufe wäre eine *abgeleitete* Position („Differenz zeigt nach links/rechts“) — nach denselben Regeln: aus Checker-Semantik, digit-frei, property-getestet.

## Quellen

1. Lokale Messung (2026-09-13): V14-Lauf `.yesmem/tmp/runs/20260913-095428` (25 gültige Läufe Tier B, 1 776 851 Tokens, 6 403 s Modellzeit); Timeout-Artefakte `.yesmem/tmp/runs-invalid-20260913/`; Auswertung `tooling/evaluate.py`, Leck-Scan `tooling/scan_feedback.py` (Assets `assets/05-11-eval.md`).
2. [05-10-haerte-runde-v13.md](05-10-haerte-runde-v13.md) — Härte-Runde V13 (Sets v0.3; offener Punkt §7.7: Rückkanal schützt Werte nicht).
3. [05-09-rueckkanal-runde-v12.md](05-09-rueckkanal-runde-v12.md) — V12 (Reparatur-Loop, Arme K/B/C/D; offene Punkte §7.1/§7.3).
4. [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Denk-Sprache V1.1 (Tags, Status, Zeugenformen).
5. [05-05-ablation-protokoll.md](05-05-ablation-protokoll.md) — Arme/Legenden, Metriken, Multiplizitätsregel.
6. [05-04-test-harness.md](05-04-test-harness.md) — Harness-Spezifikation (Transport, Sets, Artefakt-Regeln).
7. `tests/test_v14_harness.py`, `tooling/{harness,prompts,build_sets,evaluate,scan_feedback}.py`, `bemyself/{turing,msheet,claimtypes}/` — Implementierung + Tests (859 Tests grün).
8. [../01-modellprofil/01-03b-tokenizer-v11-lexeme.md](../01-modellprofil/01-03b-tokenizer-v11-lexeme.md) — Tokenizer-Sonde der Lexeme.

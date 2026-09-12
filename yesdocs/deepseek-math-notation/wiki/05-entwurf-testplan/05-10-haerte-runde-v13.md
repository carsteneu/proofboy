---
topic: deepseek-math-notation
cluster: 05-entwurf-testplan
title: "Härte-Runde V13: Zahlen-Regime, lange Läufe und die Zyklus-Suche — Sets v0.3 und die Protokoll-Fixes"
language: de
status: Verifiziert
last_updated: 2026-09-12
created_at: 2026-09-12
sources_count: 8
citations_count: 8
images_count: 0
diagrams_count: 0
related:
  - 05-09-rueckkanal-runde-v12.md
  - 05-08-pilotbericht-v1.1.md
  - 05-07-denksprache-v1.1.md
  - 05-05-ablation-protokoll.md
  - 05-04-test-harness.md
  - ../01-modellprofil/01-03b-tokenizer-v11-lexeme.md
tags:
  - haerte
  - zahlen-regime
  - zyklus-suche
  - reparatur-loop
  - denksprache
  - v11
  - v13
  - harness
  - sets
persona_review:
  personas_tested: ["Engineer (Baustufe W6/R3)", "Statistiker (Metrik-Sicht)"]
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Runde-3-Zyklus (V13, 2026-09-12). Zahlen sind Rohdaten der Läufe; keine Signifikanz-Claims. Die Abweichungen vom geplanten Laufprotokoll (Tier B mit einer Wiederholung; verworfene Neustart-Läufe) sind in §4 offengelegt."
---

# Härte-Runde V13: Zahlen-Regime, lange Läufe und die Zyklus-Suche — Sets v0.3 und die Protokoll-Fixes

[Diese Runde](../INDEX.md) zieht drei Stränge aus dem Fahrplan von [05-09](05-09-rueckkanal-runde-v12.md) §7, [05-08](05-08-pilotbericht-v1.1.md) §8.5 und dem Auftrag: (1) **härtere Zellen** — Tier A-hard als Zahlen-Regime mit mehrstelligen Rechnungen, Tier B-hard mit tiefen Prüfpunkten auf langen Läufen; (2) **Zyklus-Aufgaben ohne vorgegebenes Zertifikat** (das Zertifikat wird gesucht, nicht geprüft); (3) **Protokoll-Fixes** — Erfolg und Trigger als getrennte Begriffe, Gold-Leak-Sanitizer als Default-Deny-Allowlist, Zyklus-Scoring maschinenverifiziert statt Gold-Stringvergleich. Deskriptiv, ohne Signifikanzbehauptungen (05-05 §5).

## 1. Auftrag und Kernfrage

Kernfragen: **Bricht die Härte die Decke?** Genauer: (a) Überlebt das Modell das Zahlen-Regime (mehrstellige Arithmetik, lange Ziffernläufe) — und was kostet es? (b) Tragen die Arme lange Läufe mit vielen Prüfpunkten? (c) Findet das Modell Translationszyklus-Zertifikate, wenn sie **nicht** vorgegeben sind — und trägt der Rückkanal in den harten Zellen? (d) Tragen die Protokoll-Fixes (Erfolg ≠ Trigger, Allowlist, Maschinenprüfung)?

## 2. Was gebaut wurde

| Werkzeug | Ort | Was es tut |
|---|---|---|
| Sets v0.3 (Tier A-hard) | `tooling/build_sets.py`, `sets/tier_a_v11-a-0.3.json` | 16 mehrstellige Aufgaben: Additionen (12/12/16/20-stellig), Multiplikationen (8×8/12×12/16×16/20×20), mod/mulmod auf großen Zahlen, ein 12-stelliger ggT (Bibliotheks-Guard 10^12), vier lange Ziffernläufe (fc(40), fb(300), ch(200,100), 2^200). Gold aus einer Quelle (Bibliothek/Python-Ints); der V1-Zeuge im Feld `witness` wird zur Bauzeit unter dem Fragment ausgewertet und muss True ergeben. |
| Sets v0.3 (Tier B-hard) | `tooling/build_sets.py`, `sets/tier_b_v11-b-0.3.json` | Vier Trace-Aufgaben mit **tiefen** Prüfpunkten (t bis 150, 4–7 Punkte je Aufgabe) auf langen bbchallenge-Läufen (BB(5)-Champion, Marxen & Buntrock, Uhing, BB(6)-Champion); vier Zyklus-Aufgaben — drei **ohne** vorgegebenes Zertifikat (`certificate_given: false`), eine mit. Zertifikate zur Bauzeit per `cycle.check` verifiziert (Abbruch, wenn nicht CONFIRMED); in der Nicht-Vorgabe-Variante steht kein Wert im Prompt. |
| Nicht-Vorgabe-Zyklusaufgabe | `tooling/prompts.py` (`_answer_instruction`, `_k_selfcheck`) | Neue Antwort-Konvention für `certificate_given=false`: K/B „bestimme t1, t2, d selbst“ mit wertfreiem `Endantwort`-Muster; C/D „bestimme die Zykluswerte selbst“ mit `cyc(<t1>,<t2>,<d>)`-Platzhaltern. Auch der **Reparaturpfad** ist wertfrei (K-Selbstprüfung nennt keine Zertifikatswerte). |
| Zyklus-Scoring maschinenverifiziert | `tooling/harness.py` (`_certificate_holds`, `_CERT_RE`) | K/B-Zyklusantworten werden über die Maschine geprüft (`claimtypes.cycle` auf den vom Modell genannten Werten), nicht per Gold-Stringvergleich. Ein gültiges *anderes* Zertifikat ist gelöst; ein erfundenes nie. |
| Erfolg vs. Trigger | `tooling/harness.py` (`TRIGGER_NOT_CONFIRMED`, `run_rounds`), `tooling/evaluate.py` | Der Erfolg ist der tier-typisierte Endzustand je Runde; der Trigger ist das Ereignis, das die nächste Runde auslöst, und steht als Feld `trigger` in jeder Rundenzeile, als `triggered_rounds` in `summary.json` und als `triggered_runs` im Aggregat. Definition im Modulkopf. |
| Sanitizer: Default-Deny-Allowlist | `tooling/harness.py` (`_sanitize_reason`) | Nur die geprüften Beleg-Arten (`auto`, `ref`, `sim`, `cyc`, `py`) dürfen ihre Befunde durchreichen (ihre nicht-REFUTED-Texte wurden auf Referenzwerte geprüft); `sim`/`cyc`-Refutungen bleiben immer gesanitisiert; **unbekannte Arten werden per Default zurückgehalten** (Marker ohne Werte). |
| Runden-Auswertung v0.3 | `tooling/evaluate.py` | Aggregat um `triggered_runs` und die Markdown-Spalte „Trigger-Läufe“ ergänzt (der Renderer-Titel wird dabei versionsneutral); V11-Läufe (flaches Layout) und V12-Bäume bleiben auswertbar (Läufe ohne Trigger-Feld zählen 0). |
| Robustheit (Review-Fix) | `tooling/harness.py` (`_to_int`) | Modell-kontrollierte Zahlen jenseits des CPython-int-Stellenlimits (4300) werden fail-closed verworfen statt den Lauf abzubrechen — im Zyklus-Scoring und in der Checkpoint-Extraktion (Review 5.2/1 + 5.4 NEW; die Klasse war in `_checkpoint_pairs` vorbestehend und ist hier mitgehärtet). |
| Nebenbefund (Fix) | `tooling/harness.py` (CLI-Ende) | `harness.py dry` stürzte ab (`max_repairs` fehlt im `dry`-Namespace) — beim Benutzen gefunden, mit einer Zeile behoben (`getattr`). Kein Test hing daran. |
| Tests | `tests/test_v13_harness.py` (neu, 37), v11/v12 unverändert | Set-Form/Determinismus (inkl. Rebuild-Beweis: v0.2 byte-identisch, v0.3 reproduzierbar), Prompt-Leck-Freiheit inkl. Reparaturpfad, maschinenverifiziertes Scoring (auch: falsches Zertifikat zählt nicht, anderes gültiges zählt), Allowlist-Verhalten, Trigger-Semantik (Erfolg ≠ Trigger, Formfehler kein Trigger), `triggered_runs`. Gesamt: **744 Tests grün**. |

Engine unverändert (`bemyself/msheet/`, `bemyself/claimtypes/`, `bemyself/turing.py`); die Runde ändert Tooling, Sets, Tests und Wiki.

## 3. Design-Entscheidungen (Fairness)

- **Ziffern-Politik von Tier A-hard.** Alle Familien sind mehrstellig; die Schwellen je Familie sind im Set-Formtest verankert: Addition ≥ 6 Stellen (zwei ab 16, eine ab 20), Multiplikation ≥ 8 Stellen (zwei ab 16), `mod`/`mulmod` mit ≥ 10-stelligem Dividenden, ggT 12-stellig (Bibliotheks-Guard 10^12). Die Witness-Form folgt der Fragment-Grammatik: `((A + B) = C)`, operandenweise geklammert — der Vergleich `(A + B = C)` ist parser-invalid und war eine dokumentierte Falle der Legenden-Revision v0.2.
- **Tier B-hard: Tiefe statt Masse.** Die vier Trace-Aufgaben prüfen dieselbe Konvention wie v0.2/`_trace_task`, aber mit t bis 150 und engeren Prüfpunkt-Abständen (z. B. 10/25/50/75/100/125/150 auf dem BB(5)-Champion). Die Gold-Konfigurationen werden zur Bauzeit mit `bemyself.turing` re-derived und eingefroren (kein Handwert).
- **Zertifikat: gesucht vs. gegeben (deklariert je Aufgabe).** Drei Zyklus-Aufgaben nennen die Werte nicht (`certificate_given: false`) — darunter der triviale Anker `0LA0LA` (findbar in Sekunden) und zwei Zufalls-Maschinen aus dem Suchlauf der Runde; eine Aufgabe (5 Zustände) nennt sie (Fortsetzung der B-0011-Frage aus 05-09 §5.3 unter tieferen Bedingungen). Die Zertifikate der Zufalls-Maschinen wurden mit einem deterministischen Kopf-Profil-Suchlauf gefunden (Saat dokumentiert) und vor dem Einfrieren per `cycle.check` bestätigt.
- **Warum die Nicht-Vorgabe-Variante nicht selbstverständlich ist (Vorab-Messung).** Ein erster Vorab-Smoke hatte das Zertifikat über den alten Antwort-Text noch mitgeschickt — das Modell hat es schlicht abgeschrieben (2,7 s). Nach ehrlicher, wertfreier Instruktion fand es 3/4 Zertifikaten selbst (45 s, 39 s, 193 s; eine Antwort war falsch und wurde per `cycle.check` korrekt verworfen) — und nannte in zwei Fällen ein **anderes gültiges** Zertifikat als das eingefrorene. Genau dafür ist das maschinenverifizierte Scoring da (V12 hätte diese gültigen Antworten verworfen).
- **Erfolg ≠ Trigger (neu, präzisiert).** Erfolg = tier-typisierter Endzustand der Runde (Zahl exakt; Blatt bestätigt; alle Checkpoints exakt; Zyklus-Zertifikat maschinenverifiziert). Trigger = das Ereignis, das die **nächste** Runde auslöst: `end_state_not_confirmed`. Formfehler allein triggern **nicht** (dokumentierte Entscheidung aus 05-09 §7.1 — sie wären ein „Blattqualitäts“-Ziel, kein Erfolgsziel); Transportfehler bekommen weiter den einen Retry der 05-05-Stopregel; ein Lauf ohne auswertbare Modellausgabe endet. Die Begriffe sind im Code getrennt, in den Laufdaten sichtbar und im Modulkopf definiert.
- **Fairness der Arme unverändert.** Tier A-hard: K/B/C (D trägt gegenüber C nur die Zeugenpflicht; im Zahlen-Regime wurde auf D aus Kostengründen verzichtet — deklariert). Tier B-hard: K/B/C/D. Gleiche Rundenzahl für alle Arme (max. 2 Reparaturen), K ohne erfundene Verdikte (neutrale Selbstprüfung).
- **Wiederholungen.** Tier A-hard 2 Wiederholungen; **Tier B-hard 1 Wiederholung** — wie in V12 (05-09 §4) und aus Budgetgründen (die Projektion mit 2 Wiederholungen lag nahe an der 2,5-h-Grenze). Die Änderung wurde während des Laufs gestellt und ist in §4 offengelegt; eine abgebrochene 2-Wiederholungs-Vorversion wurde verworfen.
- **Gold-Leak-Schutz.** Zwei Aussagen, beide getestet: kein Referenzwert in Prompt/Legende/Reparaturpfad der Nicht-Vorgabe-Aufgaben; Rückmeldungen nur aus der Allowlist. Das Zyklus-Scoring füttert nichts zurück — es wertet.

## 4. Lauf

- Modell `deepseek-flash`, direkter Proxy `localhost:9099` (Transport aus Pilot 1), Reasoning-Verlauf im Rückkanal ausgelassen; keine Werkzeuge im Aufruf.
- Tier A-hard: 16 Aufgaben × 3 Arme (K/B/C) × 2 Wiederholungen = 96 Läufe, 20:46:13–21:10:00 (**~24 min**). Tier B-hard: 8 Aufgaben × 4 Arme (K/B/C/D) × **1 Wiederholung** = 32 Läufe, 21:29:54–22:49:23 (**~80 min**). Zusammen **~1 h 43 min** Wall-Clock (Budget ≤ 2,5 h eingehalten); Modellzeit ~93 min.
- Sets (im `manifest.json` beider Läufe): v11-a-0.3 sha256 `eb294ea93235e19c…`, v11-b-0.3 sha256 `a1fcac5e4c6ae568…`. v0.1/v0.2 unverändert (Rebuild-Test: byte-identisch).
- 135 Runden insgesamt (Tier A 96, Tier B 39); 5 Läufe mit mindestens einem Trigger, 2 davon repariert; 3 Läufe enden ungelöst; **1 Lauf mit Transport-Timeouts** (B3-0008/B: beide Runden liefen in den 300-s-Call-Cap, 2 Retries nach der 05-05-Stopregel; der Lauf endet ohne Modellausgabe). Keine abgebrochenen Läufe, keine Truncation (`finish_reason != length` in allen Runden).
- Offengelegte Abweichungen: (a) Tier B-hard mit **einer** Wiederholung statt zwei — wie in V12 (05-09 §4) und zur Budgetsicherung; die Entscheidung fiel während des Laufs, nachdem die Zeitprojektion mit zwei Wiederholungen die 2,5-h-Grenze touchierte. (b) Zwei Vorläufe wurden verworfen und sind **nicht** Teil der Wertung: `runs/20260912-211049` (erste Fassung mit zwei Wiederholungen; enthält u. a. den 300-s-Timeout von B3-0007/K im ersten Anlauf) und `runs/20260912-212821` (unvollständiger Neustart). Gewertet werden ausschließlich `runs/20260912-204613` (Tier A-hard) und `runs/20260912-212954` (Tier B-hard). (c) Der Harness liest die Sets jetzt standardmäßig aus **v0.3** (Konstanten `_TIER_A_SET`/`_TIER_B_SET`; es gibt keinen CLI-Schalter). Eine Reproduktion der v0.2-Runden erfordert das bewusste Umstellen dieser Konstanten — die v0.2-Dateien selbst bleiben unverändert (Hash-Test), und `one`/`dry` scheitern mit v0.2-IDs laut (KeyError) statt still eine andere Aufgabe zu fahren.
- Rohdaten: `.yesmem/tmp/runs-v13-20260912/{tier-a-hard,tier-b-hard}/` (Kopien; Auswertungs-Assets [05-10-eval-tierA.md](assets/05-10-eval-tierA.md), [05-10-eval-tierB.md](assets/05-10-eval-tierB.md)); Vorlauf-Verzeichnisse sind im Worktree erhalten.

## 5. Ergebnisse

### 5.1 Tabellen (Auszug; vollständig in den Assets)

Tier A-hard (n = 32 je Arm):

| Arm | R0 gelöst | Final gelöst | Trigger-Läufe | Runden bis ok (0/1/2/offen) | Tokens gesamt | Tokens/Lauf | Zeit gesamt |
|---|---|---|---|---|---|---|---|
| K | 32 | 32 | 0 | 32/0/0/0 | 116 724 | 3 648 | 384 s |
| B | 32 | 32 | 0 | 32/0/0/0 | 148 658 | 4 646 | 517 s |
| C | 32 | 32 | 0 | 32/0/0/0 | 157 088 | 4 909 | 525 s |

Tier B-hard (n = 8 je Arm):

| Arm | R0 gelöst | Final gelöst | Formfehler-Läufe R0 | Trigger-Läufe | repariert | Runden bis ok (0/1/2/offen) | Tokens gesamt | Zeit gesamt |
|---|---|---|---|---|---|---|---|---|
| K | 7 | 7 | 0 | 1 | 0 | 7/0/0/1 | 306 591 | 1 056 s |
| B | 6 | 7 | 4 | 2 | 1 | 6/1/0/1 | 234 683 | 1 107 s |
| C | 7 | 7 | 0 | 1 | 0 | 7/0/0/1 | 365 334 | 1 198 s |
| D | 7 | **8** | 0 | 1 | 1 | 7/1/0/0 | 236 860 | 805 s |

Trace-Ebene (Tier B-hard, exakt getroffene Gold-Checkpoints, 21 Prüfpunkte über 4 Aufgaben): **R0: C 21/21, D 21/21**, B 16/21, K 16/21. Nach allen Runden: B3-0001 7/7 (alle Arme), B3-0003 4/4 (alle), B3-0004 5/5 (alle), **B3-0002 B/C/D 5/5, K 0/5** (drei Runden, neutraler Selbstcheck).

**Falschbestätigungen: 0** über alle 135 Runden (Definition wie Pilot/V12: eine Runde, in der alle Blatt-Verdikte bestätigt sind, der tier-typisierte Endzustand aber nicht — kein solcher Fall; K hat keine Blätter).

### 5.2 Die Decke bricht — an genau drei Stellen

1. **B3-0002/K (Marxen & Buntrock, tiefe Prüfpunkte): 0/5 über drei Runden.** R0 hielt die Maschine ab Schritt 25 für angehalten (`Z`) und verfehlte schon t=10 (`(C,2,…)` statt `(A,0,11111)`); R1 und R2 drifteten weiter (u. a. `(C,-6,…)`, `(D,0,…)`). Ks Rückkanal ist die neutrale Selbstprüfung — sie sagt nicht, *wo* es falsch ist. Der Fall zeigt die Grenze des Loops für den Prosa-Arm: Ohne maschinelle Verdikte hilft „noch einmal prüfen“ nur, wenn das Modell die Simulation tatsächlich korrigiert.
2. **B3-0008/B (Zyklus ohne Vorgabe, härtere Maschine): R0 falsch (`cyc(3,3,1)`), R1 leer.** Der zweite Anlauf lief in den 300-s-Call-Cap (Timeout, leerer Inhalt) — der Lauf endet. Dazu: B verletzte im Trace R0 viermal die Zonenkonvention (4 Formfehler-Läufe; es fehlten `CLAIM`/`[HALT]`).
3. **B3-0008/C: ein gültiges Zertifikat ging im Reparaturlauf verloren** (218 075 Tokens). R0 schrieb `cyc(5,8,-1)` — **gültig** (nachträglich per `cycle.check` bestätigt), aber ohne Maschinenbindung `a: M = …`, also `UNVERIFIABLE`; der Rückkanal meldete die Bindung, keinen Wert. R1 ergänzte die Bindung, ersetzte das Zertifikat aber durch `(5,9,2)` (`REFUTED`), R2 durch `(6,10,2)` (`REFUTED`). Der wertfreie Hinweis war korrekt — und trotzdem schädlich: Er adressierte die Form, und beim Neuformulieren verlor das Blatt seinen richtigen Wert. Genau deshalb ist dieser Fall der stärkste Beleg für die Maschinenprüfung (§5.3).

Beide Reparaturen, die gelangen, sind dokumentierte Lehrfälle des wertfreien Rückkanals:

- **B3-0008/D:** R0 schrieb ein korrektes Zertifikat `cyc(3,6,-1)`, aber **ohne Maschinenbindung** (`a: M = …` fehlte) → `v1: UNVERIFIABLE`, Befund: „cyc: no machine binding in the sheet (expected 'a: M = <machine>')“ (erlaubter, wertfreier Text). R1 ergänzte die Bindung, sonst nichts — das Zertifikat verifizierte (CONFIRMED). D ist damit der einzige Arm mit final 8/8.
- **B3-0002/B:** R0 0/5 Checkpoints, keine Behauptungszone; der Rückkanal trug **nur Formfehler** (`no claim zone`, `empty [HALT] marker`) — keine Referenzwerte. R1 korrigierte alles: 5/5 exakte Checkpoints und eine wohlgeformte Zone.

### 5.3 Zyklus ohne Vorgabe: das Modell findet die Zertifikate selbst

Die drei Aufgaben ohne vorgegebene Werte wurden in Runde 0 von **mindestens einem** Arm je Aufgabe mit einem maschinenverifizierten Zertifikat gelöst (B3-0005 und B3-0006: alle vier Arme; B3-0008: K in R0, D in der Reparaturrunde) — teils mit *anderen* Zertifikaten als den zur Bauzeit eingefrorenen:

| Aufgabe (Fundmaschine) | Gold (Bauzeit) | Modell-Fund R0 | Tokens (K/B/C/D) |
|---|---|---|---|
| B3-0005 `0LA0LA` (Anker) | (0,1,-1) | (0,1,-1) | 8 909 / 11 624 / 15 123 / 6 506 |
| B3-0006 `0RB1RB_0RA0LZ` | (1,3,2) | **(0,2,2)** (alle vier Arme) | 6 701 / 13 066 / 3 399 / 5 318 |
| B3-0008 `1LB1LB_1RA0LB` (hart) | (34,37,-1) | **(4,7,-1)** (K) | 80 312 / — / — / 106 994 |

Zu B3-0008: B scheiterte in R0 mit erfundenem `(3,3,1)`; C schrieb in R0 das gültige `(5,8,-1)`, verlor es aber im Reparaturlauf (ohne Maschinenbindung nicht gewertet, §5.2); D löste nach Reparatur mit `(3,6,-1)`.

Zwei Punkte: (a) **Die Maschinenprüfung war nötig** — mit dem Gold-Stringvergleich der V12-Fassung wären die gültigen Funde `(0,2,2)` und `(4,7,-1)` als falsch gewertet worden; und ohne Prüfung wäre B3-0008/Bs erfundenes `(3,3,1)` nicht als falsch aufgefallen. (b) Die Fundkosten sind real: Der Anker kostet ~6,5–15k Tokens (das Modell simuliert von Hand), der harte Fall 80k (K) bis 218k (C, drei Runden).

### 5.4 Token-Ökonomie: die Notation trägt auch bei gefundenen Zertifikaten

Am Zyklus mit **vorgegebenem** Zertifikat (B3-0007, 5 Zustände) wiederholt sich das V12-Bild in voller Schärfe:

| Arm | Antwortform | Tokens | Dauer |
|---|---|---|---|
| K | Prosa + `Endantwort: NICHT-HALTEND (t1=133,t2=142,d=1)` | 51 168 | 181,5 s |
| B | Trace-Prosa + Endantwort | 17 045 | 68,3 s |
| C | `a:` `h1:` `v h1: cyc(…)` `h1+` `CLAIM` `WITNESS ref` `[HALT]` | **467** | **2,4 s** |
| D | wie C | **240** | **1,6 s** |

Die Zeugenarme prüfen das Zertifikat maschinell und zitieren es; die Prosa-Arme verifizieren von Hand — K braucht dafür das ~200-fache an Tokens. (Im verworfenen Vorlauf lief K in dieser Zelle sogar in den 300-s-Cap.)

### 5.5 Zahlen-Regime: alles richtig — und deutlich teurer

Tier A-hard ist ein reines **Kosten**-Regime, kein Korrektheits-Regime: 96/96 exakt, 0 Formfehler, 0 Reparaturen — aber der Aufwand steigt mit der Ziffernzahl. Beispiele (Mittel über 6 Läufe je Aufgabe, Tokens gesamt):

| Familie (Stellen) | Tokens ∎ | Anmerkung |
|---|---|---|
| Mul 8×8 | 1 547 | |
| Mul 12×12 | 6 599 | |
| Mul 16×16 | 10 165 | |
| Mul 20×20 | 22 795 | Maximum eines Einzellaufs: 34 710 Tokens / 104 s |
| Add 12-stellig (zwei Aufgaben) | 1 459 / 353 | gleiche Stellenlänge, 4× Unterschied zwischen den Aufgaben |
| Mod 18-stellig ÷ 10-stellig | 1 751 | |
| Mod 22-stellig ÷ 11-stellig | 10 455 | |
| MulMod 12×12 mod 10-stellig | 4 837 | |
| ggT 12-stellig | 1 905 | |
| fc(40) / fb(300) / ch(200,100) / 2^200 | 966 / 1 019 / 2 475 / **445** | Bibliotheks-Algorithmen, billig |

Gegenüber v0.2 (kleine Zahlen) stiegen die Tokens je Lauf: K ×4,5 (802 → 3 648), C ×3,4 (1 462 → 4 909), B ×2,1 (2 256 → 4 646). Die 96 Antworten waren ausnahmslos exakt — auch 16-stellige Multiplikationen und 2^200. Die Dehnung des „Zahlen-Regimes“ hat die Decke in Tier A also **nicht** erreicht; sie ist in Tier B-hard gefallen (5.2).

## 6. Was belegt ist — und was nicht

**Belegt (mit den Rohdaten dieser Runde):**

1. **Tier A-hard ist bei v0.3 kein Diskriminator**: 96/96 exakt in allen drei Armen, kein Formfehler, keine Reparatur; der Unterschied liegt im Preis (Token-Tabelle 5.5).
2. **Tier B-hard bricht die Decke**: 29/32 final gelöst; die drei offenen Läufe sind zwei Zyklus-Zellen und eine Trace-Zelle des schwierigsten Falls (5.2).
3. **Der wertfreie Rückkanal trägt — mit einer Nebenwirkung**: beide Reparaturläufe gelangen (B3-0008/D und B3-0002/B; §5.2); der eine brauchte nur die erlaubte Binding-Meldung, der andere nur Formfehlertexte. Gleichzeitig zeigt B3-0008/C die Grenze: Der wertfreie Hinweis adressierte die Form, das Blatt ersetzte dabei ein *gültiges* Zertifikat durch falsche. Die Sanitizer-Allowlist (Default-Deny) hat im Lauf nie Referenzwerte durchgelassen — die Befundtexte in den Läufen sind auf die geprüften Formen beschränkt.
4. **Das Modell findet Translations-Zyklus-Zertifikate selbst** — auch wenn sie vom eingefrorenen Gold abweichen; die Maschinenprüfung ist dafür die richtige Wertung (5.3).
5. **Erfolg und Trigger sind getrennt und sichtbar**: 135 Runden, 5 Läufe mit Trigger, 2 repariert, 3 offen; Formfehler haben nicht getriggert (4 Formfehler-Läufe, davon einer über eine Reparatur gelöst, weil der Endzustand fehlte) — die Zählung steht in `summary.json`/Aggregat (`triggered_runs`).
6. **0 Falschbestätigungen** über 135 Runden.

**Nicht belegt / mit Vorsicht:**

- Keine Signifikanzaussagen: n = 8 je Arm in Tier B, eine Wiederholung; Tier A mit zwei Wiederholungen ist gesättigt. Unterschiede zwischen Armen sind in dieser Runde **Anschauungsmaterial**, keine Statistik (05-05 §5).
- Der Reparaturgewinn (+12,5 pp für B und D in Tier B) hängt an je **einem** reparierten Lauf je Arm; die Grundrate liegt bei 6–7/8.
- Die Kosten-Unterschiede aus 5.4/5.5 sind Einzelzellen bzw. Mittel über 6 Läufe — belastbar ist die Größenordnung (Faktor ~10–200), nicht die Nachkommastelle.
- Ob Ks B3-0002-Scheitern (0/5 in drei Runden) an der Maschine, am Format oder am Loop-Design liegt, ist mit einem Lauf nicht entschieden (B löste dieselbe Zelle im Reparaturlauf 5/5).
- Die Zertifikat-„Findbarkeit“ ist maschinenabhängig: Der Anker (0LA0LA) ist trivial, der harte Fall (1LB1LB_1RA0LB) brauchte 80–218k Tokens und scheiterte zweimal.

## 7. Offene Punkte (Kandidaten für die nächste Runde)

1. **Formfehler als eigener Trigger (05-09 §7.1, wieder offen):** B produzierte im Trace R0 viermal dieselbe Formverletzung („no claim zone“) — mit einem Formfehler-Trigger (eigene Metrik, nicht Erfolgsdefinition) wäre der Blattzustand früher adressiert. Die Trennung Erfolg/Trigger macht das jetzt zu einer reinen Zusatz-Metrik; die Runde hat sie bewusst nicht gezogen.
2. **Rückkanal-Varianten im Zyklus (aus 05-09 §7.3):** unverändert offen — nur `#xx/#?`-Zeilen ohne Befunde vs. Befunde vs. frischer Versuch mit Appendix. Der B3-0008/C-Fall (3 Runden, kein Befund enthalten Werten) ist der natürliche Testfall für „wie viel Rückkanal ist genug, ohne Gold zu leaken“.
3. **Zertifikat-Vorgabe dosieren:** Der Mix (3 ohne / 1 mit) hat funktioniert; für eine Wiederholung wäre eine Zell-Skalierung nach erwarteter Fundkosten (Anker/mittel/hart) sinnvoll, plus eine Kosten-Obergrenze je Zelle (Call-Cap war zweimal der Lauf-Ende-Grund).
4. **K ohne Verdikte im Trace:** Ks 0/5 (B3-0002) und sein 300-s-Cap-Vorfall im Zyklus sind die zwei Stellen, an denen der Kontrollarm strukturell benachteiligt sein *könnte*; für die Fairness-Aussage der nächsten Runde wäre ein „K mit Wiederholungsbudget statt Selfcheck“ sauber abzugrenzen.
5. **Tier A-hard als Kosten-Messinstrument ausbauen:** Statt noch längerer Ziffernketten (Kosten steigen, Treffer bleiben 100 %) wären Aufgaben mit *zusätzlicher* Struktur (verschachtelte Reste über mehrere Schritte, große Kombinatorik-Folgen) der nächste Hebel — und eine feste Kosten-Statistik je Familie im Bericht.
6. **Testdaten-Hygiene der Sets:** Die Zufalls-Maschinen der Zyklus-Aufgaben tragen ihre Suchsaat in `source`; für Nachvollziehbarkeit wäre ein kleines Suchskript (`tooling/`) besser als die Prosa-Angabe.
7. **Der Reparatur-Rückkanal schützt Werte nicht (neu, aus dem korrigierten B3-0008/C-Fall):** Ein korrektes Zertifikat ging verloren, weil der Hinweis die *Form* adressierte und das Blatt beim Neuformulieren den Wert änderte. Kandidaten: eine Rückmeldung, die „Form unvollständig“ von „Aussage widerlegt“ unterscheidet (der Runner kennt den Unterschied: `UNVERIFIABLE` vs. `REFUTED`, und die Meldung trägt ihn), oder die ausdrückliche Anweisung, bestätigte Werte beim Neuformulieren zu erhalten.

## Quellen

1. Lokale Messung (2026-09-12): V13-Läufe `.yesmem/tmp/runs/20260912-204613` (Tier A-hard, 96 Läufe) und `.yesmem/tmp/runs/20260912-212954` (Tier B-hard, 32 Läufe), gesichert unter `.yesmem/tmp/runs-v13-20260912/`; 1 565 938 Tokens (Tier A 422 470, Tier B 1 143 468); Auswertung `tooling/evaluate.py`.
2. [05-09-rueckkanal-runde-v12.md](05-09-rueckkanal-runde-v12.md) — V12 (Reparatur-Loop, Arme K/B/C/D; offene Punkte §7).
3. [05-08-pilotbericht-v1.1.md](05-08-pilotbericht-v1.1.md) — Pilot 1 (Sets v0.1, Token-Ökonomie §8.5).
4. [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Denk-Sprache V1.1 (Tags, Status, Zeugenformen).
5. [05-05-ablation-protokoll.md](05-05-ablation-protokoll.md) — Arme/Legenden, Metriken, Multiplizitätsregel.
6. [05-04-test-harness.md](05-04-test-harness.md) — Harness-Spezifikation (Transport, Sets, Artefakt-Regeln).
7. `tests/test_v13_harness.py`, `tooling/{harness,prompts,build_sets,evaluate}.py`, `bemyself/{turing,msheet,claimtypes}/` — Implementierung + Tests (744 Tests grün).
8. [../01-modellprofil/01-03b-tokenizer-v11-lexeme.md](../01-modellprofil/01-03b-tokenizer-v11-lexeme.md) — Tokenizer-Sonde der Lexeme.

---
topic: deepseek-math-notation
cluster: 05-entwurf-testplan
title: "RC-Umstellung V15: Die Denkspur in V1.1 — Fidelity-Metrik, Instruction-only-Arme C0/C1/C2 und die Prefill-Grenze"
language: de
status: Verifiziert
last_updated: 2026-09-13
created_at: 2026-09-13
sources_count: 12
citations_count: 12
images_count: 0
diagrams_count: 0
related:
  - 05-10-haerte-runde-v13.md
  - 05-09-rueckkanal-runde-v12.md
  - 05-08-pilotbericht-v1.1.md
  - 05-07-denksprache-v1.1.md
  - 05-05-ablation-protokoll.md
  - 05-04-test-harness.md
  - ../01-modellprofil/01-03b-tokenizer-v11-lexeme.md
tags:
  - rc-umstellung
  - denkspur
  - reasoning-content
  - fidelity-metrik
  - instruction-only
  - prefill
  - v15
  - harness
  - sets
persona_review:
  personas_tested: []
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Runde-4-Zyklus (V15, 2026-09-13). Zahlen sind Rohdaten der Läufe; keine Signifikanz-Claims (05-05 §5). Abweichungen vom geplanten Protokoll sind in §4 offengelegt."
---

# RC-Umstellung V15: Die Denkspur in V1.1 — Fidelity-Metrik, Instruction-only-Arme C0/C1/C2 und die Prefill-Grenze

[Diese Runde](../INDEX.md) zieht den Strang aus [05-07](05-07-denksprache-v1.1.md) §8 (weiche RC-Empfehlung) und die offenen Punkte aus [05-10](05-10-haerte-runde-v13.md) §7: Bis V13 galt die V1.1-Sprache nur für die *sichtbare* Denkzone; der Denkkanal `reasoning_content` (RC) — der Ort, an dem über 90 % der generierten Tokens liegen — blieb Prosa. Diese Runde misst die RC-Treue erstmals systematisch (neue Metrik, TDD-gebaut), prüft den V13-Stand als Baseline und zieht die Umstellung **instruction-only**: C1 (starke RC-Instruktion) und C2 (plus vollständiges RC-Beispiel) gegen eine byte-identische Kontrolle C0 — ohne Training, ohne Werkzeuge. Der geplante dritte Hebel (Pre-Fill der Denkspur) wurde als Machbarkeitsprobe gefahren und ist an der API-Grenze gestorben (§5.4). Deskriptiv, ohne Signifikanzbehauptungen (05-05 §5).

## 1. Auftrag und Kernfrage

Kernfragen: **Wie weit kommt die V1.1-Notation in den Denkkanal — mit Bordmitteln?** Genauer: (a) Wie treu ist die Denkspur im V13-Stand? (b) Verschiebt eine starke Instruktion (C1) die RC-Zeilen in die Tag-Sprache? (c) Bringt ein vollständiges RC-Beispiel (C2) mehr — oder nur längere Denkspuren? (d) Was kostet die Umstellung an Tokens und Korrektheit? (e) Lässt sich die Denkspur per API prefillen (C3)?

## 2. Was gebaut wurde

| Werkzeug | Ort | Was es tut |
|---|---|---|
| RC-Fidelity-Metrik | `tooling/rcfidelity.py` (neu) | Heuristischer Parser des `reasoning_content`: Zeilenklassen (Tag-Köpfe g/d/a/c/h/v/q/=, v-Zeilen, Status-Mini-Zeilen, V1-Altzeilen `S<n>:`, Claim-Zeilen des Blatt-Entwurfs, Prosa), Anteile im Sinne der Metrik h (05-05), Zeichen-Proxy für den Token-Anteil, Degenerations-Marker (leere Tag-Köpfe, identische Zeilenläufe, längster Prosa-Lauf, Draft-Block). Kopf-Erkennung als linearer Scanner (keine Regex-Backtracking-Klasse); CLI `--runs/--json/--markdown`. |
| RC-Arme C0/C1/C2 | `tooling/prompts.py` | C0 = C (byte-identisch, V13-Stand als Kontrolle); C1 = C + starker RC-Absatz (Denkspur in V1.1-Zeilen, „keine Prosa"); C2 = C1 + vollständiges RC-Beispiel (Form-Few-Shot). Adressiert wird ausschließlich der Denkkanal; sichtbare Zone, Antwortkonventionen und Rückkanal bleiben identisch zu C. |
| Gezielte Teilmenge | `tooling/harness.py` (`--task-ids`) | Exakte, geordnete Aufgabenauswahl statt Shuffle — reproduzierbare 12-Task-Teilmenge; die C-Varianten erben den maschinellen Rückkanal und den Trace-Blattpfad (Guard-Tests). |
| Tests | `tests/test_v15_rcfidelity.py` (19), `tests/test_v15_rc_arms.py` (14) | Synthetische RC-Fixtures (Prosa/strikt/gemischt/degeneriert), synthetischer Lauf-Baum, CLI-Pfad, Robustheit (korrupte raw.json, Laufzeit-Schranke); Legend-Staffelung, C0≡C, Gold-Leak-Freiheit, Rückkanal-Verhalten, task-ids-Auswahl. |

Engine unverändert (`proofboy/msheet/`, `proofboy/claimtypes/`); die Runde ändert Tooling, Tests, Laufdaten und Wiki. Gesamtsuite: **851 Tests grün** (818 vor dieser Runde + 33 neue).

## 3. Design-Entscheidungen

### 3.1 Kontrolle doppelt: frisch und historisch

Derselbe Arm kann an zwei Tagen verschiedene Spuren ziehen (B3-0001, Reasoning-Tokens: V13-C 51 870, frisches C0 32 761). Darum läuft C0 **frisch neben** C1/C2 (Treatment-Effekt) — und der V13-C-Stand dient als historische Baseline für die Frage „wie treu war die Denkspur bisher" (Kontext, nicht Treatment-Kontrolle).

### 3.2 Nur Instruktion, kein Training

Fine-Tuning und Werkzeuge stehen außerhalb des Auftrags; die Runde prüft ausdrücklich die *instruction-only*-Grenze. Ergebnis ist die Messung dieser Grenze, keine Konvergenzaussage.

### 3.3 Zeichen-Proxy statt Token-Tokenizer

Ein lokaler Modell-Tokenizer steht nicht bereit (01-03b nutzte Zeichen-/Byte-Zählung). Der Anteil „Notationszeichen / alle Zeichen" ist der dokumentierte Proxy; er *unterschätzt* die Notation, weil Prosa-Leerzeichen zusätzliche Token-Kosten tragen.

### 3.4 Bekannter Konfund: der Blatt-Entwurf im RC

Das Modell entwirft in der Denkspur regelmäßig das sichtbare Blatt — gültige Tag-Zeilen, Statuszeilen und die Claim-Zone (CLAIM/WITNESS/[HALT]) mitten im RC. Die Metrik weist den zusammenhängenden Notations-/Claim-Block am RC-Ende als `trailing_notation_block` aus und zählt Zeilen-/Zeichenanteile über den ganzen Text; die Anteile sind darum Obergrenzen der „echten" Denkspur-Notation. Die V15-Läufe zeigen beide Formen: meist liegt der Entwurf mitten im RC (Kontrollarm C0 in beiden Tiers ohne Trailing-Block), teils steht Notation am RC-Ende (C1: ø 0,8 bzw. 1,0 Zeilen; C2-A ø 1,1), und im Extremfall ist der RC das ganze Blatt (B3-0007/C1: Trailing-Block 8 von 8 Zeilen).

### 3.5 Prefill als Probe, nicht als Annahme (C3)

Statt auf Doku-Zitate zu bauen, lief eine Live-Probe gegen denselben Transport (assistant-Prefix in der Nachrichtenliste, mit/ohne `prefix: True`, zusätzlich Top-Level `prefix`). Ergebnis in §5.4.

### 3.6 Fairness der Arme

Zwischen C0/C1/C2 differiert **nur** der RC-Absatz (Guard-Test: C0 byte-identisch zu C; alle C-Arme teilen Antwortkonventionen und Rückkanal). Die RC-Zusätze tragen keine Aufgabenwerte (Test); B3-0007 ist die Vorgabe-Variante — dort steht das Zertifikat by design im geteilten Aufgaben-Prompt aller Arme. Die Teilmenge (4 schnelle Tier-A-Zellen, alle 8 Tier-B-Zellen) und die Wiederholungszahlen (Tier A 2, Tier B 1 wie V13) ändern die Bedingungen der Vorrunde nicht.

## 4. Protokoll und Läufe

| Lauf | Wurzel | Umfang |
|---|---|---|
| V13-Baseline (historisch, rückwirkend metrisiert) | `.yesmem/tmp/runs-v13-20260912/{tier-a-hard,tier-b-hard}` | 128 Läufe (K/B/C/D); hier ohne Neuläufe ausgewertet |
| V15 Tier A | `.yesmem/tmp/runs/20260913-093541` | 4 Aufgaben (A3-0001/0013/0014/0016) × Arme C0/C1/C2 × 2 Wiederholungen = 24 Läufe |
| V15 Tier B | `.yesmem/tmp/runs/20260913-094057` | 8 Aufgaben (B3-0001..0008, Sets v0.3) × Arme C0/C1/C2 × 1 Wiederholung = 24 Läufe |

Transport: direkter HTTP-Pfad `localhost:9099/v1/chat/completions` (Bearer; Modell `deepseek-flash`), wie in [05-08](05-08-pilotbericht-v1.1.md) §2 — kein Werkzeugzugriff, kein Sockel. `max_repairs=2` (Reparaturrunde = Wiederholung derselben Bitte plus maschinelle Verdikte, unverändert aus V13). Reproduktion: `harness.py batch --arms C0,C1,C2 --task-ids … --reps …`.

**Abweichungen (dokumentiert):** (1) B3-0008/C1 riss in der Reparaturrunde den 300-s-Call-Cap (0 Tokens, `TimeoutError`); die Zelle zählt als nicht gelöst — die anderen Arme liefen unter demselben Cap, C0 und C2 lösten die Zelle in der Reparatur. (2) Die V13-Baseline ist rückwirkend metrisiert (kein Neulauf); sie dient als Kontext, nicht als Kontrolle. (3) Keine Neustart-Läufe; alle 48 V15-Läufe sind Erstläufe des jeweiligen Arms. (4) Die Rohdaten liegen (wie in den Vorrunden) unter dem gitignorierten `.yesmem/tmp/` und sind darum nur lokal verfügbar; im Repo stehen die Auswertungs-Assets.

## 5. Ergebnisse

### 5.1 V13-Baseline: die Denkspur war Prosa

Rückwirkend über alle V13-Läufe (Metrik auf `raw.json`, volle RC-Länge):

| Arm | Tier A (n=32 Runden): Tag-Zeilen ø / Notations-Zeichen ø | Tier B (n=9–10 Runden): Tag-Zeilen ø / Notations-Zeichen ø |
|---|---|---|
| K | 1,9 % / 1,6 % | 0,0 % / 0,0 % |
| B (V1) | 1,4 % / 0,6 % | 0,0 % / 0,0 % |
| C (V1.1) | 8,2 % / 6,0 % | 7,3 % / 1,9 % |
| D (V1.1 + Zeugenpflicht) | — | 5,3 % / 1,4 % |

Auch der V1.1-Arm C bleibt unter 10 % — die Denkspur war strukturell Prosa, in langen Tier-B-Zellen praktisch vollständig (1,9 % Zeichenanteil). Ursache belegbar: die V13-Legenden enthielten **keinen** RC-Satz (Stichprobe über alle V13-`prompt.md`: 0 Treffer für „reasoning"/„Denkspur"/„denke in"); die weiche Empfehlung aus 05-07 §8 war nie im Prompt. Die Denkspur trägt den Blatt-Entwurf als Inseln von Notation, dazwischen Erklärtexte.

### 5.2 Instruction-only verschiebt die Denkspur — in kurzen Zellen, nicht in langen

Tier A (alle Runden): C0 13,5 % Tag-Zeilen / 8,7 % Notations-Zeichen; C1 21,1 % / 11,6 %; C2 25,9 % / 17,8 % (C2 mit n=9, inkl. einer Reparaturrunde). Die Instruktion wirkt (in dieser Stichprobe): +7,6 pp bzw. +12,4 pp Tag-Zeilen gegenüber der frischen Kontrolle.

Tier B trennt scharf nach Aufgabentyp (nur Runde 0, je 4 Zellen):

| Zellgruppe | C0 | C1 | C2 |
|---|---|---|---|
| Trace B3-0001..04: Tag-Zeilen / Zeichen | 1,9 % / 1,0 % | 2,6 % / 0,9 % | 1,9 % / 1,5 % |
| Zyklus B3-0005..08: Tag-Zeilen / Zeichen | 10,2 % / 1,6 % | 26,6 % / 19,2 % | 21,5 % / 4,3 % |
| Zyklus ohne B3-0008 (drei kurze Zellen) | 13,6 % / 2,1 % | 34,8 % / 25,6 % | 28,0 % / 5,6 % |

Die vier Trace-Zellen — die teuren Simulationen mit rund 20–40k Reasoning-Tokens je Lauf (Runde 0) — ignorieren die Instruktion praktisch (≤2,6 %). Die kurzen Zyklus-Zellen folgen deutlich, am stärksten C1. Vollständig folgsam wird die Denkspur im Einzelfall: **B3-0007/C1 schreibt das komplette Blatt in den RC** (3 Tag-Zeilen, 1 v-Zeile, 1 Statuszeile, Claim-Zone; 8 Zeilen, 0 Prosa-Zeilen, 197 Tokens gesamt) — RC ≡ Blatt, wörtlich.

Qualitativ (Zitate aus den Läufen): C0 denkt englisch weiter („We need answer only in formal language…", B3-0003/C0); C1 denkt deutsch und *über* die Regel („Ich muss die Denkzone und die Antwort trennen? Die Aufgabe sagt: ‚Denkspur-Zusatz (reasoni…'", B3-0003/C1) — und fällt im nächsten Absatz wieder in Prosa; C2 pendelt zwischen englischer Prosa (B3-0003/C2) und deutscher Meta-Prosa („Wir müssen die Denkzone und Denkspur in V1.1-Sprache halten. Keine Prosa.", A3-0016/C2). Kurz: die Instruktion verschiebt Sprache und Selbstbeschreibung, aber nicht die Arbeitsform langer Spuren.

### 5.3 Kosten und Korrektheit

Tier A (8 Läufe je Arm): C0 6 796 Tokens gesamt (849,5 je Lauf), C1 9 904 (1 238,0), C2 14 246 (1 780,8). Erfolg 24/24 in allen Armen; C2 brauchte eine Reparaturrunde (A3-0016) und wurde in Runde 1 gelöst. Nebenbefund: 2 von 8 C1-Läufen trugen je einen Formfehler in der *sichtbaren* Zone (doppelter h1-Block nach der =-Zeile, A3-0001 beide Wiederholungen) — gelöst trotzdem; C0/C2-A hatten 0.

Tier B (8 Läufe je Arm): 

| Arm | R0 gelöst | final gelöst | Tokens gesamt | ø Tokens/Lauf | Reparaturläufe |
|---|---|---|---|---|---|
| C0 | 7/8 | 8/8 | 318 876 | 39 859,5 | 1 (B3-0008, 2 Runden → gelöst) |
| C1 | 7/8 | 7/8 | 234 499 | 29 312,4 | 1 (B3-0008, R1 Timeout) |
| C2 | 6/8 | 8/8 | 294 317 | 36 789,6 | 2 (B3-0002 in 2 Runden, B3-0008 in 1) |

C1 ist in Tier B nominell am billigsten — aber die Timeout-Zelle fehlt dort in der Summe (B3-0008/C1 verlor eine Reparaturrunde mit 0 Tokens; C0 zahlte in derselben Zelle 127k Tokens für seine zwei Reparaturrunden, C2 41k für seine eine). Die belastbare Aussage ist darum: **die drei Arme liegen in Tier B in derselben Kostenklasse** (29–40k Tokens je Lauf; B3-0008 dominiert alles). In Tier A kostet C1 rund +46 % und C2 rund +109 % gegenüber C0, bei vollständiger Korrektheit.

Die Reparaturrunden (7 Stück über alle Arme: 1 in Tier A, 6 in Tier B) sind **in Tier B** Prosa-dominiert (Tag-Anteile 0,27–1,49 %); die einzige Tier-A-Reparaturrunde (A3-0016/C2 Runde 1) ist dagegen notation-nah — 60 % Tag-Zeilen, 0 Prosa-Zeilen, das RC spiegelt sogar das Maschinen-Verdikt als `a:`-Zeile. Auffälligster Einzelfall: B3-0002/C2 produzierte in Runde 1 einen **Zeilen-Loop** (die Zeile `101101101` 11× hintereinander — von der Metrik als `repeat_extra` gefangen) und löste die Zelle in Runde 2. Gesamtkosten der Runde: 878 638 Tokens (Tier A 30 946, Tier B 847 692) in 48 Läufen / 55 Runden, ~57 Minuten Modellzeit.

Historischer Kontext (nur Größenordnung, Tag-Varianz; einheitlich Reasoning-Tokens je Runde): auf denselben 12 Aufgaben lag der V13-C-Arm bei ø 536 Tokens je Runde in Tier A und ø 36 344 in Tier B; die frische Kontrolle C0 liegt bei ø 756 (Tier A) bzw. ø 31 692 (Tier B). Die Mittel-Abweichungen (+41 % in Tier A, −13 % in Tier B; Einzelzellen von −61 % bis +346 %) bestätigen die doppelte Kontrolle (3.1).

### 5.4 Prefill-Grenze (C3): die Denkspur ist per API nicht seedbar

Probe gegen den Transport (gleicher Endpunkt wie die Läufe): (1) Kontrolle „Zaehle von 1 bis 3." → Antwort `1, 2, 3.` (2) Mit assistant-Präfix `VORSPANN-4711: ` (`prefix: True`) → Antwort `1, 2, 3.` — das Präfix wird **nicht** als Fortsetzung angewandt, sondern ignoriert (HTTP 200, identische Antwort ohne Präfix); Top-Level-`prefix` ebenso wirkungslos. (3) Eine weiche Variante (User bittet um Antwortstart „g: ") zeigt: die Form folgt der *Instruktion*, nicht dem Präfix.

Die API-Doku stützt den Befund: „If the request does not carry the `tools` parameter: `reasoning_content` … even if passed to the API, it will be ignored and will not be concatenated into the context" ([DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode, accessed 2026-09-13)); die Prefix-Completion existiert nur als Beta-Feature und adressiert den sichtbaren Inhaltskanal ([DeepSeek Chat Prefix Completion](https://api-docs.deepseek.com/guides/chat_prefix_completion, accessed 2026-09-13)). Der Denkkanal ist damit per Bordmitteln **nicht** ansteuerbar außer über die Instruktion — C3 ist gestrichen (dokumentiert statt stillschweigend weggelassen). Probe-Transkript: `.yesmem/tmp/runs-v15-20260913/c3-prefill-probe.md` (Ablage-Konvention wie §4, Punkt 4).

## 6. Was belegt ist — und was nicht

**Belegt (mit den Rohdaten dieser Runde):**

1. **Der V13-Stand war Prosa** — auch im V1.1-Arm C (8,2 %/6,0 % in Tier A, 7,3 %/1,9 % in Tier B); die Legenden trugen keinen RC-Satz (§5.1).
2. **Instruction-only verschiebt die Denkspur in kurzen Zellen deutlich** — bis 34,8 % Tag-Zeilen (C1, kurze Zyklus-Zellen) und im Einzelfall vollständige Blatt-Notation ohne Prosa (B3-0007/C1) (§5.2).
3. **Die langen Trace-Zellen widerstehen** — alle Arme ≤2,6 % Tag-Zeilen; die Form der Massen-Tokens (90 %+ des Budgets) bleibt Prosa (§5.2).
4. **Der Few-Shot-Zusatz bringt in Tier B keine Mehr-Treue** — C2 liegt dort unter C1 bei den Zeichenanteilen und über C0 nur in kurzen Zellen; in Tier A strukturiert er am stärksten, kostet aber +109 % Tokens (C0→C2) und erzeugte die Hälfte aller Reparatur-Trigger (§5.2/5.3).
5. **Korrektheit hält** — Tier A 24/24 in allen Armen (V13-A: 0 Formfehler; C1-A anekdotisch 2), Tier B 23/24 final; der einzige Ausfall ist der Infrastruktur-Timeout der Zelle B3-0008/C1 (§5.3).
6. **Die Metrik greift** — sie misst die Verschiebung, trennt Trace von Zyklus, fängt Degeneration (Zeilen-Loop B3-0002/C2) und macht den Blatt-Entwurf messbar (Trailing-Block inklusive Claim-Zone; B3-0007/C1 = 8 von 8 Zeilen, §5.2/5.3).
7. **Die Denkspur ist per API nicht prefillbar** — Live-Probe plus Doku (§5.4).

**Nicht belegt / mit Vorsicht:**

- Keine Signifikanzaussagen: Tier B n=1 je Zelle, Tier A n=2, Trace/Cyc-Split 4-vs-4-Zellen — Größenordnungen, keine Statistik (05-05 §5).
- Die RC-Anteile sind ein Zeichen-Proxy (3.3) und enthalten Blatt-Entwurfs-Inseln (3.4); Token-genaue Treue ist damit nicht gemessen.
- Der B3-0008/C1-Ausfall (Timeout) verzerrt die Tier-B-Kosten der Arme in unbekannter Richtung; die Kostenklasse „29–40k/Lauf" ist die belastbare Zusammenfassung, nicht die Rangfolge C1 < C0 < C2.
- Ob der Zeilen-Loop (B3-0002/C2) oder die C1-A-Formfehler durch die RC-Instruktion *begünstigt* wurden, ist mit je einem Fall nicht entschieden; beide wurden als Anekdoten markiert, nicht als Effekt.
- V13-Rückvergleiche sind Tag-Varianz-behaftet (Einzelzellen −61 % bis +346 %, Mittel +41 %/−13 %) und darum nur als Kontext geführt.

## 7. Offene Punkte (Kandidaten für die nächste Runde)

1. **Der Widerstandskern sind die langen Spuren:** In Trace-Zellen denkt das Modell in Prosa über Simulationen — die Instruktion erreicht nur die kurzen Zellen. Kandidaten: RC-Format als *Rückkanal-Thema* (Meta-Instruktion nach einer Prosa-Runde), SFT auf RC-Notation (Trainingsweg, außerhalb dieser Runde), oder eine Analyse *welche* RC-Inhalte sich der Notation entziehen (argumentative/strategische Schritte vs. Rechen-Schritte).
2. **Der Rückkanal hat den Denkkanal noch nie adressiert:** Reparaturrunden adressieren das Blatt; in Tier B blieben die fünf RC-tragenden Reparaturrunden Prosa-dominiert (0,27–1,49 % Tag-Zeilen; die sechste, B3-0008/C1 Runde 1, lieferte wegen des Timeouts keinen RC), doch die einzige Tier-A-Reparaturrunde (A3-0016/C2) war notation-nah (60 % Tag-Zeilen, 0 Prosa) — der Kanal folgt dem Rückkanal also in kurzen Zellen bereits von selbst. Ein *expliziter* Format-Rückkanal für den Denkkanal („deine letzte Denkspur war Prosa") ist der billigste nächste Test.
3. **C2 dosieren:** Das volle Beispiel führte zu längeren Spuren ohne Mehr-Treue in Tier B. Varianten: Beispiel nur mit Kurz-Zeilen; Gegenbeispiel (Prosa-Zeile explizit als falsch); Beispiel an die Zellgröße gekoppelt. Dazu der Wortlaut der RC-Instruktion: `v:` steht in der Kopf-Liste, obwohl v-Zeilen eigene Form haben, und das Beispiel nutzt nicht den Legenden-Klammerstil — bewusst erst für die **nächste** Arm-Generation geändert, um die Reproduzierbarkeit der V15-Arme zu erhalten.
4. **B3-0008-Zelle sauber messen:** Der 300-s-Call-Cap reißt bei 79k-Token-Denkspuren (RC-Instruktion). Repetition mit größerem Cap (>600 s) oder Token-Cap statt Zeit-Cap, damit die Zelle nicht als Infrastruktur-Artefakt endet.
5. **Metrik-Ausbau:** Regel-Spiegelung (Anteil Zeilen, die die Instruktion wörtlich zitieren — C1/C2 zeigten Meta-Zeilen), Sprachdetektion (DE/EN) als Spalte, Token-Proxy über den Modell-Tokenizer (01-03b), und Trace-vs-Cyc als feste Dimension im Renderer.
6. **Nebenwirkung auf die sichtbare Zone prüfen:** Die zwei C1-A-Formfehler (doppelter h1-Block) könnten Instruktions-Bleed sein — ein sauberer A/B (RC-Satz mit/ohne sichtbaren-Zonen-Satz) trennt das.
7. **`--task-ids`-Semantik nachschärfen** (Werkzeug-Hygiene): Duplikate überschreiben still dasselbe Lauf-Verzeichnis, `--task-ids ""` fällt still auf den Default-Sample zurück (während `" "` null Aufgaben wählt), und die Tier-Caps werden im task-ids-Pfad still ignoriert — im Help-Text dokumentieren oder ablehnen.

## Quellen

1. Lokale Messung (2026-09-13): V15-Läufe `.yesmem/tmp/runs/20260913-093541` (Tier A, 24 Läufe) und `.yesmem/tmp/runs/20260913-094057` (Tier B, 24 Läufe), gesichert unter `.yesmem/tmp/runs-v15-20260913/` (inkl. `c3-prefill-probe.md`); 48 Läufe / 55 Runden, 878 638 Tokens (Tier A 30 946, Tier B 847 692), ~57 min Modellzeit; Auswertung `tooling/evaluate.py` + `tooling/rcfidelity.py`; Assets [05-12-eval-tierA.md](assets/05-12-eval-tierA.md), [05-12-eval-tierB.md](assets/05-12-eval-tierB.md), [05-12-rc-tierA.md](assets/05-12-rc-tierA.md), [05-12-rc-tierB.md](assets/05-12-rc-tierB.md).
2. V13-Rohdaten: `.yesmem/tmp/runs-v13-20260912/` (128 Läufe; rückwirkend metrisiert).
3. [05-10-haerte-runde-v13.md](05-10-haerte-runde-v13.md) — V13 (Härte, Sets v0.3; offene Punkte §7).
4. [05-09-rueckkanal-runde-v12.md](05-09-rueckkanal-runde-v12.md) — V12 (Reparatur-Loop, Arme K/B/C/D).
5. [05-08-pilotbericht-v1.1.md](05-08-pilotbericht-v1.1.md) — Pilot 1 (Transport §2, Sets v0.1).
6. [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Denk-Sprache V1.1; RC-Empfehlung §8.
7. [05-05-ablation-protokoll.md](05-05-ablation-protokoll.md) — Arme/Legenden, Metriken h/i, Multiplizitätsregel.
8. [05-04-test-harness.md](05-04-test-harness.md) — Harness-Spezifikation (Transport, Sets, Artefakt-Regeln).
9. Implementierung + Tests: `tooling/{rcfidelity,prompts,harness,evaluate}.py`, `tests/test_v15_{rcfidelity,rc_arms}.py` (851 Tests grün, 33 neu).
10. [DeepSeek: Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode) — `reasoning_content` wird ohne `tools` nicht in den Kontext übernommen (accessed 2026-09-13).
11. [DeepSeek: Chat Prefix Completion (Beta)](https://api-docs.deepseek.com/guides/chat_prefix_completion) — Prefix nur als Beta-Feature im Inhaltskanal (accessed 2026-09-13).
12. [../01-modellprofil/01-03b-tokenizer-v11-lexeme.md](../01-modellprofil/01-03b-tokenizer-v11-lexeme.md) — Tokenizer-Sonde der Lexeme (Zeichen-Proxy-Kontext).

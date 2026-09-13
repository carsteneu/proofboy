---
topic: deepseek-math-notation
cluster: 05-entwurf-testplan
title: "Lean-Mandat-Runde V19: Prompt-Varianten-Matrix (Regeln als Lean-Kommentare, Denkspur-Beispiele, Completion-Prefill) — RC-Resistenz und die Zuverlässigkeit der Lean-Antwort"
language: de
status: Verifiziert
last_updated: 2026-09-13
created_at: 2026-09-13
sources_count: 11
citations_count: 15
images_count: 0
diagrams_count: 0
related:
  - 05-14-v1-1-lean-v18.md
  - 05-12-rc-umstellung-v15.md
  - 05-07-denksprache-v1.1.md
  - 05-05-ablation-protokoll.md
  - 05-04-test-harness.md
  - ../02-wirksame-formate/02-05-latentes-denken.md
tags:
  - lean
  - mandat
  - reasoning-content
  - prompt-matrix
  - completion-prefill
  - fence-leck
  - tokenbudget
  - v19
persona_review:
  personas_tested: []
  gaps_found: 0
  gaps_fixed: 0
  note: "Erstellt im Lean-Mandat-Zyklus (V19, 2026-09-13, ~17:13–17:26). n klein, deskriptiv; keine Signifikanz-Claims (05-05 §5). Die Variantentexte sind aus der Inline-Session geborgen (nicht byte-reproduziert — die Inline-Calls wurden nicht abgelegt); Abweichungen und Grenzen in §3.6/§5.4."
---

# Lean-Mandat-Runde V19: Prompt-Varianten-Matrix

[Diese Runde](../INDEX.md) systematisiert einen Inline-Befund desselben Tages: Carstens Idee — ein mathematisches Problem plus Systemprompt, der per MANDATORY verlangt, in Lean zu *denken* (Thinking-Sprache Lean), direkt an die API, „mit einfachsten Themen starten, Systemprompt iterieren bis es klappt" — wurde am 2026-09-13 zwischen 17:03 und 17:05 in 10 rohen API-Proben (fünf Prompt-Stile, zwei Modelle) durchgespielt. Das Ergebnis war zweigeteilt: Die Denkspur (`reasoning_content`) blieb in **10/10** Proben **Prosa** — auch mit Lean-geschriebenem Systemprompt; die sichtbare Antwort dagegen wurde zuverlässig **pures, valid elaborierbares Lean** (leancheck auf Probe 1: `status=valid`, `sorry_used=false`). V19 baut daraus einen reproduzierbaren Runner, prüft die Inline-Beobachtungen in einer Matrix (Varianten × Aufgabengrade × Wiederholungen) und misst die Zuverlässigkeit der „Lean-Antwort"-Konfiguration.

## 1. Auftrag und Kernfrage

Kernfragen: **(a)** Kann *irgendeine* Prompt-Variante den Lean-Anteil der Denkspur deutlich heben (Schwelle der Runde: ≥ 50 % Lean-Zeilen) — oder ist die RC-Prompt-Resistenz reproduzierbar? **(b)** Ist die Konfiguration „RC frei (Prosa), sichtbare Antwort = pures Lean, `leancheck` als Verdikt" zuverlässig — mit welcher Quote je Aufgabengrad und welchen Fehlerklassen? Nebenfragen: Markdown-Fence-Leckrate, Token-/Dauer-Kosten, Verhalten eines zweiten Modells (Cluster). Erwartungsfrei: Auch „nichts Erstaunliches" ist ein Ergebnis; insbesondere darf die sichtbare Kette nicht mit „Lean-Denken klappt jetzt" verwechselt werden.

## 2. Was gebaut wurde

| Werkzeug | Ort | Was es tut |
|---|---|---|
| Lean-Mandat-Runner | `tooling/lean_mandat.py` (neu) | Matrix-Runner analog [05-14](05-14-v1-1-lean-v18.md) §2 (`lean_smoke`): fünf Varianten (**V-A** Regeln als ``--``-Kommentare, Systemprompt selbst Lean; **V-B** + ein Denkspur-Beispiel; **V-C** + drei Beispiele; **V-D** Completion-Prefill im Assistant-Content; **V-E** = V-B + Fence-Verbot) × sieben Aufgaben der Grade trivial/mechanisch/Lemma × Wiederholungen. Direkter Modellaufruf über `harness.call_model` (kein Arm, kein Sockel), Extraktion wie `lean_smoke` (größter Zaun-Block, sonst Volltext) mit Fence-Flag, Prefill-Echo-Erkennung, Statement-Echo, RC-Metriken via `leanfidelity`, Elaboration via `leancheck` (inkl. Axiom-Sonde `main_thm`), deterministische Renderer (JSON + zwei Markdown-Assets) und `render`-Subkommando. |
| Aufgaben (7) | dito | **trivial:** `2 + 3 = 5`, `1 + 1 = 2`; **mechanisch:** `(12 + 30) % 7 = 0`, `837465291837 + 192837465564 = 1030302757401`; **Lemma (Std):** `∀ n : Nat, n + 0 = n`, `[1, 2, 3].length = 3`, `∀ a b : Nat, a + b = b + a`. Jede Aufgabe trägt einen Referenzbeweis (`ref_tactic`), der im Test **real** über `leancheck` elaboriert wird (7/7 `valid`). |
| Tests | `tests/test_v19_lean_mandat.py` (neu, 28) | Varianten-Ladder (V-A ⊂ V-B ⊂ V-C; V-E = V-B + Fence-Zusatz; nur V-D mit Prefill), Prompt-Bau, Extraktion/Echo/Statement-Echo, Aggregation (inkl. Axiom-Zählung nur valider Zellen), Manifest ohne Zugangsdaten, geskripteter Transport und geskriptetes `leancheck` (kein Netz), Renderer-Determinismus (zweimal rendern ⇒ identisch), echte Referenz-Elaboration (skipWithout Toolchain). Volle Suite: **1169 Tests grün** auf dieser Basis; Basis (8832f9f): 1141 grün, `diff` der Fehlschläge: keine. |

Engine und Harness unverändert (`bemyself/`, `harness.py`, `prompts.py`); die Runde ändert Tooling, Tests, Laufdaten und Wiki.

## 3. Design-Entscheidungen

### 3.1 Variantentexte aus der Inline-Session geborgen, nicht erfunden

Die Inline-Proben wurden roh im Terminal ausgeführt und **nicht abgelegt**; die System-/User-Texte (SYS_A, SYS_B, SYS_LEAN, D-Prefill, E-Beispiele) wurden für dieses Werkzeug aus dem Session-Verlauf geborgen (deep_search) und wörtlich übernommen. V19 ist damit eine *rekonstruierende* Reproduktion derselben Stile, keine byte-identische — das ist die ehrliche Grenze (§5.4). **Deviation der Ladder:** V-C leitet monoton aus V-B ab (drei Beispiele in einem Block); inline war die Basis der Dreier-Beispiel-Variante der kürzere `SYS_LEAN`-Text. Die Ladder V-A ⊂ V-B ⊂ V-C macht den Messvergleich lesbar.

### 3.2 Artefakt-Kontrakt (dokumentierte Abweichung)

Die Inline-Proben ließen den Beweisnamen offen (`example`, beliebige Theoremnamen). V19 fordert im User-Prompt: erste Zeile `import Std`, Theoremname `main_thm`, keine weiteren Imports, Antwort = kompletter Beweis ohne Markdown. Grund: Nur mit einem stabilen Namen trägt der Schnipsel die Axiom-Sonde (`#print axioms main_thm`) und die Verdikt-Doktrin (`valid`/`invalid`/`timeout` + `sorry` + Axiome). Der Kontrakt ist zugleich der Kern des Anschluss-Vorschlags (§6.1).

### 3.3 Prefill im inline-treuen `/v1`-Modus, mit Vorspann

V-D hängt den unfertigen Beweis als Assistant-Content an (inline-Verhalten, **ohne** `prefix: true`; der Beta-Prefix-Modus der Doku [DeepSeek 2026] blieb bewusst ungetestet — eine Grenze, §5.4). Zwei Konsequenzen sind im Werkzeug abgebildet: (1) Der `content` kann den Prefill wiederholen — Feld `prefill_echo` (in V19 21/21 Wiederholungen), `continuation` = eigener Text; (2) der Prefill trägt den Theorem-Vorspann (`import Std`/`theorem main_thm … := by have h1 : … := by `) — anders als inline, wo der Prefill nackt war und damit a priori nicht elaborierbar. Der Prefill ist ein *mechanischer Hebel für den sichtbaren Kanal* (inline-Befund), also wurde er so gebaut, dass das Resultat ein elaborierbares Artefakt sein kann.

### 3.4 Vierte Messgröße: der Augenschein

Die RC-Heuristik (`leanfidelity`) klassifiziert Zeilen per erstem Wort und `:=`-Bindung. Schon der Live-Smoke zeigte beide Fehlerrichtungen: Prosa, die Lean zitiert („theorem main_thm : … := by …"), zählt als Statement-Zeile; Lean-Syntaxfortsetzungen (`| zero =>`) zählen als Prosa. Deshalb misst die Runde zusätzlich per **Augenschein-Stichprobe** (14 Zellen, ~13 % der 105) den Anteil „echter Lean-Zeilen" (Zeilen, die als Lean parsen würden) und stellt beide Zahlen nebeneinander (§5.1).

### 3.5 Kleine Matrix, volle Ehrlichkeit über n

5 Varianten × 7 Aufgaben × 3 Wiederholungen = 105 Zellen, ein Modell (`deepseek-flash`, direkter Pfad, `max_tokens 4096` wie inline), plus zwei Supplemente: Cluster-Gegencheck (`privateTomMax`, 4 Zellen) und ein Budget-Supplement (8 Zellen, 8192 Tokens, §5.2). Alle Aussagen sind deskriptiv; Zellen n=3.

## 4. Protokoll und Läufe

| Lauf | Wurzel (gitignoriert, Worktree) | Umfang |
|---|---|---|
| V19-Hauptmatrix | `.yesmem/tmp/lean-mandat/matrix-deepseek` | 105 Zellen (V-A..V-E × t1/t2/m1/m2/l1/l2/l3 × 3), 17:13–17:25 |
| V19-Cluster-Gegencheck | `.yesmem/tmp/lean-mandat/matrix-cluster` | 4 Zellen (V-B × t1/l1 × 2), `privateTomMax` via llm.ccm19.app |
| V19-Budget-Supplement | `.yesmem/tmp/lean-mandat/matrix-budget8k` | 8 Zellen (V-A/V-C × m2/l3 × 2) bei `max_tokens 8192` |

Transport: direkter HTTP-Pfad `https://api.deepseek.com/v1/chat/completions` (Bearer; Modell `deepseek-flash`, `max_tokens 4096`); Reproduktion:

```
BEMYSELF_TARGET=deepseek BEMYSELF_MAX_TOKENS=4096 \
  python3 yesdocs/deepseek-math-notation/tooling/lean_mandat.py run --out <dir> --reps 3
BEMYSELF_TARGET=cluster ... --variants V-B --tasks t1,l1 --reps 2
python3 .../lean_mandat.py render --run <dir> --summary <dir>/summary.md --raw <dir>/raw.md
```

**Abweichungen und Kontexte (dokumentiert):** (1) Variantentexte rekonstruiert, V-C-Basis abweichend (§3.1); (2) Artefakt-Kontrakt ergänzt (§3.2); (3) V-D-Prefill mit Vorspann (§3.3); (4) `max_tokens 4096` wie inline — die Budget-Wirkung ist als Befund ausgewiesen (§5.2) und mit dem 8k-Supplement geprüft; (5) Während der Hauptmatrix lief im Hintergrund der Baseline-Testlauf (einmalig 76 s) — Token-Zahlen unberührt, Dauer-Zahlen dieser 105 Zellen nicht (die Läufe waren rein API-seitig); (6) Die Rohdaten liegen unter dem gitignorierten `.yesmem/tmp/`; die Auswertungs-Assets stehen im Repo, die vollständigen Rohdaten werden im Haupt-Repo gesichert (§6.4).

## 5. Ergebnisse

### 5.1 RC-Resistenz: die Denkspur bleibt Prosa (Kernfrage a)

**Heuristik (`leanfidelity`):** Der Lean-Zeilen-Anteil der Denkspur liegt über die Varianten bei **0,44–0,52** (V-A 0,4412 · V-B 0,4884 · V-C 0,4363 · **V-D 0,5170** · V-E 0,4492); Taktik-Anteil ø 0,12–0,16. Das ist deutlich über den V18-Matrixwerten (L2: 7,6 %/0,4 % [05-14](05-14-v1-1-lean-v18.md) §5.2) und über den Inline-Proben — aber die Zahlen sind ein Artefakt der Aufgabenstellung („beweise diese Mini-Aussage in Lean"): Das Modell *entwirft* den Lean-Beweis in der Denkspur und zitiert ihn; die Metrik zählt die zitierten Zeilen mit.

**Augenschein-Stichprobe (14 Zellen, je 2 pro Variante):** echt-Lean-Zeilen (manuell, Zeile für Zeile klassifiziert) ø **0,41** gegen Heuristik ø **0,51** über dieselben Zellen. Die Heuristik überschätzt (Prosa mit `:=`-Zitaten: z. B. V-E-t1-r1: 3 RC-Zeilen, Heuristik 0,67, real ~0,0 — die Zeilen sind „Need ensure first line import Std. theorem main_thm : 2 + 3 = 5 := by decide. Is import Std allowed?"), unterschätzt selten (Fortsetzungszeilen wie `| zero =>`, V-A-l3-r1: real 0,55 vs 0,47). **Qualitativ:** In *jeder* der 14 gesampelten Zellen ist die Denkspur eine Prosa-Deliberation (Englisch/Deutsch) mit *eingebetteten* Lean-Entwürfen — nie Lean als Medium. Typischer Bauplan: (1) Paraphrase der Regeln, (2) Entwurf des Beweises, oft mehrfach, in Fence-Blöcken, (3) Format-Selbstkontrolle, (4) Ausgabe. Beispiel V-D-t1-r1 (Heuristik 0,67): „We need answer in required format. … But system requires each line be one of allowed forms … Maybe we can put theorem inside `example`? But user explicitly demands `theorem main_thm`." Der RC-Verlauf ist in allen Varianten von **Regel-Deliberation** dominiert — das Mandat beschäftigt den Denkkanal mit sich selbst.

**Antwort auf (a):** Keine Variante hebt den RC-Anteil *substanziell* über die Schwelle — die Heuristik erreicht bei V-D 0,517 knapp ≥ 50 %, der Augenschein liegt überall darunter; das Few-Shot-Beispiel (V-B/V-C) und der Prefill (V-D) erhöhen nur den Anteil *zitierter* Lean-Zeilen. Der Inline-Befund ist damit reproduziert und gehärtet: **Der Denkkanal ist per Prompt nicht biegbar; Lean erscheint im RC als zitiertes Material, nicht als Register.** Messbares Nebensymptom derselben Sache: fünf Zellen der Hauptmatrix (V-A m2 r2/r3, V-A l3 r2, V-C m2 r2, V-C l3 r1) verbrauchten das **gesamte 4096-Token-Budget in der Denkspur** (`completion_tokens = reasoning_tokens = 4096`, sichtbare Antwort leer) — auf den schweren Graden frisst die Format-Deliberation das Budget.

### 5.2 Die Lean-Antwort-Konfiguration: zuverlässig, mit drei benannten Fehlerklassen (Kernfrage b)

**Systematisch:** 105 Zellen, kein Transportfehler. **94 valid · 6 invalid · 5 ohne Code** (Budget, s. o.); `sorry` 0×; unter den 94 validen sind **88 axiomfrei** (5 × `propext`/`Quot.sound`, 1 × `native_decide`-Axiom; das Axiom-Aggregat zählt nur valide Zellen — die Sonde der angehängten Zeile kann auch bei invalidem Schnipsel bestehen). **Statement-Echo 100/105** (jede Antwort mit Inhalt trägt die geforderte Aussage, nur die 5 Budget-Leerzellen nicht). **Fence-Rate 21/105 = 20 %** trotz expliziter Verbote: V-A 3/21, V-B **9/21**, V-C 6/21, V-D **0/21**, V-E 3/21 (der Fence-Zusatz halbiert das Leck gegenüber V-B, beseitigt es nicht; nur der Prefill ist fence-frei).

| Variante | n | valid | invalid | ohne Code | Fence | Statement-Echo | RC-Lean ø (Heuristik) |
|---|---|---|---|---|---|---|---|
| V-A (Regeln Lean) | 21 | 18 | 0 | 3 | 3 | 18 | 0,4412 |
| V-B (+1 Beispiel) | 21 | 21 | 0 | 0 | 9 | 21 | 0,4884 |
| V-C (+3 Beispiele) | 21 | 17 | 2 | 2 | 6 | 19 | 0,4363 |
| V-D (Prefill) | 21 | **21** | 0 | 0 | **0** | 21 | 0,5170 |
| V-E (V-B + Fence-Verbot) | 21 | 17 | 4 | 0 | 3 | 21 | 0,4492 |

**Je Aufgabengrad** (alle Varianten gepoolt): trivial 29/30 valid (1 invalid), mechanisch 25/30 (2 invalid, 3 Budget-Leerzellen), Lemma 40/45 (3 invalid, 2 Budget-Leerzellen). Der Abfall liegt *nicht* an der sichtbaren Lean-Komposition (Statement-Echo ~100 %), sondern an (i) Budget und (ii) den zwei Formfehler-Klassen.

**Fehlerklassen (alle code-anchoriert, `leancheck`-Diagnose):**

1. **Form-Leak „Top-Level-`have`/`example`-Muster"** (4 Zellen in der Matrix: V-C-l2-r1, V-E-l3-r2, V-E-l3-r3, V-E-t1-r3; + je 1 im 8k-Supplement und im Cluster-Lauf): Das Modell kopiert die *Beispiel-Form* (Regel 4 bzw. Few-Shot: Top-Level-`have h1 …` mit `exact h1`) in die sichtbare Antwort → `unexpected token 'have'; expected command`, teils zusätzlich `invalid 'import' command, it must be used in the beginning of the file`. Beispiel V-E-t1-r3 (wörtlich): `-- Denkspur (Lean-4-Taktikzeilen):\n-- goal: 2 + 3 = 5\nhave h1 : 2 + 3 = 5 := by decide\nexact h1` + danach ein korrekter Theorem-Block — die Denkspur-Zeilen leckten in die Antwort. Die Beispiele der Prompts sind Denkspur-*Formen*, keine elaborierbaren Lean-Dateien; das Modell übernimmt sie wörtlich, wenn kein Fence sie als „Zitat" rahmt. (V-E-Pattern: Fence-Verbot → Beispielzeilen landen ungerahmt im Code.)
2. **Mathlib-Taktik** (2 Zellen: V-C-m2-r1, V-E-m2-r1): `norm_num` — ohne Mathlib `unknown tactic` + `unsolved goals`. Das Modell weiß prinzipiell, dass `norm_num` nicht Core ist (im RC von V-A-m1-r1 explizit erwogen), wählt es unter Rechenlast aber trotzdem.
3. **Tokenbudget 4096** (5 Zellen, s. §5.1): kein Prompt-Fehler — die RC-Deliberation allein füllt das Budget, die Antwort bleibt leer. **8k-Supplement:** dieselben Zelltypen (V-A/V-C × m2/l3 × 2) bei `max_tokens 8192`: **7/8 valid, 0 ohne Code** (1 invalid = Klasse 1) — die Leerzellen sind damit vollständig als Budget-Effekt erklärt.

**Zuverlässigste Konfiguration der Runde:** **V-D** (Lean-Regeln + Completion-Prefill) 21/21 valid, 0 Fence-Lecks, Statement-Echo 21/21, `prefill_echo` 21/21 — der Prefill macht den sichtbaren Kanal *mechanisch* Lean-förmig (der Inline-Befund „Completion-Prefill funktioniert im content-Kanal" ist reproduziert). V-B 21/21 valid, aber 9 Fence-Lecks — der sichtbare Kanal bleibt valide, die Konvention „pures Lean" hält dort nicht gegen das Fence-Verbot.

**Cluster-Gegencheck** (`privateTomMax`, V-B, t1/l1 × 2): 3/4 valid (1 × Klasse 1), Fences 2/4, Statement-Echo 4/4, RC-Lean ø 0,31; das Gateway meldet **kein** `reasoning_tokens`-Feld (RC-Text vorhanden) — RC-Prosa auch bei anderer Modellfamilie, wie inline. Keine Verallgemeinerung (4 Zellen).

### 5.3 Kosten

| Variante | Reasoning-Tokens Σ | Completion-Tokens Σ (inkl. Reasoning) | Dauer Σ |
|---|---|---|---|
| V-A | 28 687 | 29 237 | 147 s |
| V-B | 21 783 | 22 434 | 120 s |
| V-C | 28 285 | 28 928 | 146 s |
| V-D | 23 116 | 23 756 | 118 s |
| V-E | 17 181 | 18 094 | 101 s |
| **Σ** | **119 052** | **122 449** | **632 s** (ø 6,0 s je Call) |

Die Kosten sind pro Variante vergleichbar (Faktor 1,7 zwischen billigster V-E und teuerster V-A; Streuung innerhalb der Zellen groß — dieselbe Aufgabe streut um Faktor ~3). Keine Aussage über Effizienz der Varianten (n klein). Der 8k-Supplement-Lauf braucht für 8 Zellen 11 867 Reasoning- + 12 299 Completion-Tokens — dieselben Zelltypen gelingen dort *billiger* als die Budget-Verbraucher der Hauptmatrix, d. h. die 4096-Fälle waren Ausreißer nach oben, nicht die Regel.

### 5.4 Grenzen

- **n klein, deskriptiv:** 105 + 4 + 8 Zellen, 3 Wiederholungen je Zelle; keine Signifikanz-Claims; Zellquoten sind Momentaufnahmen.
- **Rekonstruktion, nicht Byte-Kopie:** Die Inline-Texte wurden geborgen, die Ladder V-C weicht in der Basis ab (§3.1); die Inline-Rohdaten existieren nicht.
- **Ein Modell, ein Transport, ein Budget:** `deepseek-flash` direkt; Cluster nur 4 Zellen; Hauptmatrix bei 4096 Tokens (Budget-Effekt separat ausgewiesen, nicht vollständig ersetzt — das 8k-Supplement deckt nur 8 Zellen ab).
- **Heuristik + Stichprobe:** Der RC-Anteil ist (a) eine Schlüsselwort-Heuristik und (b) ein Augenschein über 14 Zellen; die „echte" RC-Lean-Quote aller 105 Zellen ist ungeklärt. Beide Zahlen sind im Bericht getrennt ausgewiesen.
- **`leancheck` ist kein Sandkasten:** Wie in [05-14](05-14-v1-1-lean-v18.md) §5.4; hier lief nur Modell-Output der eigenen Pipeline.
- **Antwort-Korrektheit:** Gemessen wurden „elaboriert" (Kernel) + Statement-Echo (Whitespace-normiert); *ob* ein valider Beweis die *gemeinte* Aussage formalisiert, prüft nur das Echo — die Aussagen sind klein und maschinell entschieden (7/7 Referenzbeweise real elaboriert).
- **Beta-Prefill ungetestet:** der `prefix: true`-Modus (`/beta`, [DeepSeek 2026]) wurde nicht gefahren; V-D gilt nur für den inline-treuen `/v1`-Modus.
- **Cluster-Metrik:** ohne `reasoning_tokens`-Feld ist der Token-Vergleich zum Cluster nicht möglich.

## 6. Anschluss und offene Punkte

1. **LEAN-output-Taskkonvention (Vorschlag, aus §5.2 abgeleitet).** Für theorem-förmige Aufgaben: (i) sichtbare Antwort = kompletter Lean-Beweis, `import Std`, fester Theoremname, keine Fences; (ii) RC ausdrücklich frei (Prosa) — kein Mandat; (iii) Verdikt = `leancheck` (`valid`, `sorry`, Axiome), nicht der Prompt; (iv) Beispiele im Prompt immer als *komplette Theorem-Dateien* zeigen und Top-Level-`have`/`example` explizit verbieten (Fehlerklasse 1); (v) „nur Std/Core, kein Mathlib" nennen (Fehlerklasse 2); (vi) Budget ≥ 8192 für Grad ≥ mechanisch (Fehlerklasse 3); (vii) Prefill als mechanischer Konformitätshebel zulässig — er verbessert die Konventionstreue messbar (V-D), ändert aber den RC nicht. Ein Satz „Lean-taugliche Aufgaben" wäre der nächste saubere Schritt (Aufgaben-Klassen wie in [05-14](05-14-v1-1-lean-v18.md) §5.5.5 vorgeschlagen).
2. **RC-Register braucht Training, keinen Prompt.** Die Runde ist der vierte unabhängige Beleg (V15/V16/V18 + Inline + V19): Der Denkkanal folgt keinem Register-Mandat. Der Hebel bleibt der Trainings-Pfad ([05-07](05-07-denksprache-v1.1.md) §13, `training/`): öffentliche Lean-Taktik-Korpora (mathlib, LeanDojo, Wettbewerbs-Formalisierungen) sind für ein LoRA „Denken in Lean-Taktik" besser datenversorgt als die eigene Prosa-RC — die V19-Läufe liefern dafür (a) saubere **Lean-Antworten** mit Kernel-Verdikt als SFT/DPO-Kandidaten für die *Antwort*-Seite und (b) eine ehrliche Negativ-Evidenz für die *Denk*-Seite.
3. **Verdikt- statt Prompt-Doktrin bestätigt.** `leancheck` trägt die Qualitätsaussage: 94 valide, 0 `sorry`, Axiome je Beweis ausgewiesen; die Prompt-Konvention „pures Lean" trägt nur 80 % (Fences) — die maschinelle Prüfung bleibt der Anker ([04-05](../04-offene-probleme/04-05-bruecke-pruefer.md)).
4. **Rohdaten.** Vollständige Zell-JSONs (RC, Antwort, Usage, Verdikt) liegen unter `.yesmem/tmp/lean-mandat/` im V19-Worktree und werden vor einem Worktree-Abbau ins Haupt-Repo gesichert (Präzedenz V18, [05-14](05-14-v1-1-lean-v18.md) §4).
5. **Test-Inventar.** Die Runde hebt die Suite auf 1169 Tests (+28; Basis 1141); `make test` bleibt der Eingang.

## Quellen

1. Lokale Messung (2026-09-13, 17:13–17:25): V19-Hauptmatrix `.yesmem/tmp/lean-mandat/matrix-deepseek` (105 Zellen); Assets [05-15-mandat.md](assets/05-15-mandat.md) (Roh-Tabelle), [05-15-grades.md](assets/05-15-grades.md) (Aggregate je Zelle/Variante).
2. Lokale Messung (2026-09-13): Cluster-Gegencheck `.yesmem/tmp/lean-mandat/matrix-cluster` (4 Zellen, `privateTomMax`); Budget-Supplement `.yesmem/tmp/lean-mandat/matrix-budget8k` (8 Zellen, 8192 Tokens).
3. Lokale Messung (2026-09-13, 17:03–17:05): Inline-Proben (10 API-Calls, 5 Stile, 2 Modelle) — Ausgangsbefund; Texte per Session-Bergung rekonstruiert (Rohdaten nicht abgelegt).
4. Werkzeuge: `tooling/lean_mandat.py` (neu), `tooling/leancheck.py`, `tooling/leanfidelity.py`, `tooling/harness.py`; Tests `tests/test_v19_lean_mandat.py`.
5. Lean 4.33.1 + Std: lokale Toolchain `~/.elan/toolchains/leanprover--lean4---v4.33.1`; Std-Minimalprojekt ohne Dependencies.
6. [05-14-v1-1-lean-v18.md](05-14-v1-1-lean-v18.md) — leancheck/leanfidelity, Latent-Lean-Smoke, Taktik-Denkspur-Arme, RC-Anteile 7,6 %/0,4 %.
7. [05-12-rc-umstellung-v15.md](05-12-rc-umstellung-v15.md) — RC-Umstellung, Prefill-Grenze, Instruction-only-Befunde.
8. [05-07-denksprache-v1.1.md](05-07-denksprache-v1.1.md) — Denk-Sprache V1.1, Trainings-Einordnung §13.
9. [05-05-ablation-protokoll.md](05-05-ablation-protokoll.md) — Multiplizitätsregel: keine Signifikanz-Claims bei kleinem n.
10. DeepSeek-AI (2026): Chat Prefix Completion (Beta). DeepSeek API Docs. https://api-docs.deepseek.com/guides/chat_prefix_completion (abgerufen 2026-09-13; `prefix: true` + `/beta`-Basis-URL, in dieser Runde bewusst nicht genutzt).
11. [04-05-bruecke-pruefer.md](../04-offene-probleme/04-05-bruecke-pruefer.md) — Verdikt-Doktrin (maschinell prüfen statt glauben).

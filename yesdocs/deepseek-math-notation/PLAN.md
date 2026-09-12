---
topic: deepseek-math-notation
language: de
min_sources_per_file: 2
max_concurrent_agents: 5
default_max_runtime: 3h
default_backend: opencode
default_model: deepseek/deepseek-flash
saturation_limit: 3
---

# Masterplan — Modell-native Mathematik-Notation (Zielmodell: DeepSeek V4.1 Flash)

## Auftrag (von Carsten, 2026-09-12)

Hypothese: Eine mathematische Notation, die auf den Attention-/Tokenizer-Apparat *dieses* Modells zugeschnitten ist, macht das Modell beim Arbeiten an Mathematik besser und/oder schneller — und ist rücküberführbar in reine formale Mathematik (Zeugen, nicht Glauben).

Das Wiki muss vier Fragen beantworten:
1. **Was ist über das Modell bekannt?** (öffentlich: Architektur, Tokenizer, Training, Benchmarks, Grenzen; lokal: Betriebsgrenzen)
2. **Was macht Repräsentationen wirksam?** (Forschungsliteratur zu Tokenisierung, Formatierung, Struktur, latentem Denken)
3. **Welches komplexe offene mathematische Problem** eignet sich als Testfeld — und warum?
4. **Notations-Entwurf + Mapping in formale Mathematik + ausführbarer Testplan** für genau diese Maschine.

Hinweis: Dieses Wiki ist die LERN- und ENTWURFSPHASE. Die Umsetzung (Bau der Werkzeuge, Durchführung der A/B-Tests) folgt als separate Phase nach dem Merge; der Testplan muss dafür präzise genug sein (reproduzierbare Kommandos, Aufgaben-Sets, Metriken).

## Harte Regeln (für alle Bereichs-Agenten)

- Sprache: **Deutsch** (technische Begriffe englisch ok). Quellen dürfen beliebige Sprache sein.
- **Jede Tatsachenbehauptung mit Inline-Zitat** `[Titel](URL, accessed YYYY-MM-DD)`. Min. **2 Quellen je Datei**; für zentrale Zahlen (Benchmarks, Kontextlänge, Parameter) **Primärquellen** (Paper, Model Card, offizielle Docs, GitHub) — Wikipedia nur als Einstieg, nie als einzige Quelle.
- Konflikte zwischen Quellen **doppelt** darstellen, nicht auflösen.
- Lokale Quellen (z. B. `~/.config/opencode/opencode.json`, `~/.cache/opencode/models.json`, Repo-Inhalte) erlaubt, aber klar als **„lokale Quelle"** kennzeichnen (kein Web-Zitat vortäuschen).
- **Kein Push, kein Merge, kein Deploy, kein sudo, kein systemctl.** Keine Schreibzugriffe außerhalb des Worktrees; `~/.claude/**` bleibt unberührt. Temp nur in `.yesmem/tmp/`.
- Visuals nach Skill-Regeln: Architektur-Diagramme / Charts / Docs-Screenshots als `assets/…` capturen (Chromium-Kaskade), Caption + Quelle unter jedem Bild.
- Zielmodell-IDs: Instanz läuft als `deepseek/deepseek-flash` (opencode-Config; Nutzer nennt es „DeepSeek V4.1 Flash"). Kanonischen öffentlichen Namen/Version ermitteln und dokumentieren; Abweichungen festhalten.

## Ausgabe

- Wiki: `yesdocs/deepseek-math-notation/wiki/<cluster>/<datei>.md`
- Frontmatter je Datei: topic, cluster, status, last_updated, sources_count, language
- INDEX.md + 99-sources/bibliography.md erzeugt der Orchestrator in INTEGRATE.
- Phase-6-Commit des Orchestrators: `git add yesdocs/deepseek-math-notation/` (inkl. PLAN.md).

## Cluster und Dateien

### 01-modellprofil — Was ist über das Modell bekannt?
- 01-01-offizielle-quellen.md — Releases, Model Card, API-Doku, Provider (z.ai/DeepSeek), Versionsgeschichte, kanonischer Name inkl. Datum; Kontextlänge, Output-Limits.
- 01-02-architektur-attention.md — Architektur (MoE? Attention-Variante, MLA/sparse?), Parameter, Kontextmechanik, KV-Cache; offiziell vs. spekulativ getrennt.
- 01-03-tokenizer-zahlen.md — Tokenizer-Eigenschaften, Zahlen-Tokenisierung, dokumentierte Behandlung von Ziffern/Sonderzeichen; bekannte Implikationen für Arithmetik.
- 01-04-training-faehigkeiten.md — Pretraining/Post-Training/RL, Reasoning-Modus (`reasoning_content`, interleaved thinking), Mathe-/Code-Fähigkeiten laut Berichten.
- 01-05-benchmarks-grenzen.md — Benchmarks (Mathe/Code/Reasoning), Vergleich zu Vorgängern, dokumentierte Schwächen, Halluzinations-/Zuverlässigkeitsberichte.
- 01-06-betrieb-umgebung.md — LOKAL: Betriebsgrenzen dieser Instanz (Kontext 1.000.000 Tokens, Output 8.192 Tokens Flash / 65.536 Pro, Proxy-Routing, interleaved reasoning); Relevanz für Notationsdesign (Output-Budget!).

### 02-wirksame-formate — Repräsentations-Forschung
- 02-01-tokenisierung-arithmetik.md — Ziffern-Tokenisierung vs. Arithmetik (u. a. „Tokenization counts", Meta 2024); belegte Effektgrößen.
- 02-02-embedding-position.md — Embedding-/Positions-Interventionen (xVal u. a.) für Zahlenverarbeitung.
- 02-03-format-sensitivitaet.md — Format-Ablations-Studien (ASCII vs. Unicode, Klammerung, Whitespace, Struktur), belegte Genauigkeits-Deltas.
- 02-04-lokalitaet-struktur.md — Attention-Lokalität, Schritt-/Scratchpad-Formate, Kontext-Distanz-Effekte, Implikationen für Notationsdesign.
- 02-05-latentes-denken.md — Continuous/Latent Reasoning (Coconut u. a.): Belege, Eigenschaften, und warum es die Prüfbarkeit verliert.
- 02-06-code-tools-schnittstelle.md — Code/Zahlen als Schnittstelle (Python/SymPy in-the-loop), Tactic-Sprachen (Lean) als LLM-Interface, Ausführung als Prüfanker.

### 03-formale-bruecke — Rücküberführbarkeit
- 03-01-formale-systeme.md — Lean4/mathlib, Metamath, Coq, Isabelle, SMT: Grammatik-Regelmäßigkeit, Ökosystem, LLM-Eignung im Vergleich.
- 03-02-autoformalisierung.md — NL→formell: Verfahren, Benchmarks, Fehlertaxonomie, Spezifikationsproblem.
- 03-03-llm-prover-stand.md — AlphaProof, DeepSeek-Prover(-Varianten), Gödel-Prover, Hilbert u. a.; RL aus Verifier-Signal.
- 03-04-zeugen-zertifikate.md — Was „prüfbar" konkret heißt: Beweisterme, Zertifikate, SAT/UNSAT-Kerne, HALT-Zeugen (Anschluss: Prüfer + `[HALT]`/claimtypes).
- 03-05-roundtrip-anforderungen.md — Definition Rücküberführbarkeit (Notation→formal, formal→Notation), Konservativität/Beweislast, Compiler-Skizze, Round-Trip-Tests.

### 04-offene-probleme — Testfeld-Auswahl
- 04-01-wahlkriterien.md — Kriterien: echt offen + komplex; zeugen-/rechenfähige Teilfragmente; Datenlage/Community; auf dieser Maschine testbar; Notationseffekt messbar.
- 04-02-kandidaten-katalog.md — Katalog (Start: BB(6); Collatz; Goldbach; Erdős-Probleme; Hadwiger-Nelson; weitere via Recherche) je mit Status, Teilresultaten, Quellen.
- 04-03-rechenfragmente-daten.md — Ausführbare/verifizierbare Teilfragmente, Datenquellen, Tools, Communities (z. B. bbchallenge, SAT-Solver, OEIS).
- 04-04-empfehlung.md — Shortlist 2–3 mit begründeter Empfehlung und Testeignung für die Notations-Hypothese.
- 04-05-bruecke-pruefer.md — Anschluss an vorhandene Infrastruktur: Prüfer (yesdocs/pruefer/wiki), `[HALT]`/`[SCORE]` (P7, Branch yesloop/bemyself-p7-halt), claimtypes-Registry; was steht, was fehlt.

### 05-entwurf-testplan — Notation + Testprotokoll
- 05-01-designprinzipien.md — Prinzipien aus 01-03 + 02-*: je Regel, Begründung, Belegquelle, testbare Vorhersage.
- 05-02-notations-spezifikation.md — Der Entwurf: Lexik (Zahlen, Operatoren, ASCII), Syntax (kanonisch, lokal, explizit), Beispiele (Satz, Beweisschritt, HALT-Trace); Output-Budget beachten.
- 05-03-mapping-formal.md — Mapping-Tabellen Notation↔Lean/Metamath/Witness; sauber abbildbar vs. nicht; Verluste; Parser/Renderer-Skizze.
- 05-04-test-harness.md — Harness für diese Maschine: Aufgaben-Sets, Ausführung (opencode/API/bemyself), Sandbox, Logging, Determinismus.
- 05-05-ablation-protokoll.md — A/B: Notation vs. Standard bei gleichen Aufgaben; Kontrollen, Wiederholungen, Metriken (Trefferquote, Tokens/Aufgabe, Schritte bis Ergebnis), Auswertung.
- 05-06-erfolgskriterien-risiken.md — Bestätigung/Widerlegung der Hypothese; Risiken (Spezifikationsproblem, Modellwechsel, Nichtübertragbarkeit).

## Erfolgsbild (Definition of Good)

Ein Leser soll nach dem Wiki: (a) die praktischen Grenzen des Modells kennen; (b) V1 der Notation aus 05-02 bauen können; (c) den A/B-Test aus 05-05 auf dieser Maschine laufen lassen können; (d) die Problemwahl aus 04-04 nachvollziehen; (e) die formale Brücke aus 03-05/05-03 prüfen können. Wo Belege fehlen, steht das explizit als Lücke, nicht als Behauptung.

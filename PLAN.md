# PLAN proofboy: der Pruefer

Diese Datei ist die kanonische Quelle. Der Suborchestrator liest sie und leitet jeden naechsten Run daraus ab.

## Ziel

Ein ausfuehrbarer Pruefer fuer Behauptungen ueber den Zustand der Welt, mit gemessener Trefferquote auf einem Pruefset. Erfolg ist eine Zahl, keine Meinung.

## Harte Regeln (immer)

- Nur lesend auf `~/.claude/yesmem` (SQLite URI `mode=ro`).
- Kein `make deploy`, kein `restart-services`, kein `sudo`, kein `systemctl`.
- Kein Schreibzugriff ausserhalb von `/home/carsten/projects/proofboy`.
- Kein Anfassen von `~/.claude/skills` und der Live-Daten.
- Keine neuen Abhaengigkeiten: Python 3 Standardbibliothek.
- Pruefungen in Wegwerf-Checkouts, nie im Arbeitsverzeichnis des Nutzers.
- Worker mergen nie selbst. Nur der Suborchestrator mergt nach `master`.
- Arbeit immer im Worktree, Branch `yesloop/<slug>` bzw. `yesresearch/<slug>`.

## Phasen

### P0 Bootstrap (Orchestrator, erledigt vor dem ersten Spawn)
git init, README.md, SPEC.md, PLAN.md, Conveyor-Section, Suborchestrator-Briefing, Watchdog-Job.

### P1 Pruefer-Kern (yesloop)
Ziel: `python3 -m proofboy check --report <datei> --repo <pfad>` prueft die Behauptungen einer Meldung und gibt je Behauptung `CONFIRMED` / `REFUTED` / `UNVERIFIABLE` mit Beweis aus.
Erste Pruefer: Commit existiert, Branch auf Remote gepusht, Diff-Scope gegen Dateiliste, Tests gruen auf sauberem Checkout.
TDD: Fixtures aus einem Wegwerf-Repo mit bekannt gutem und bekannt falschem Commit. Tests laufen ohne Netz.
Abnahme: Kommando laeuft, Tests gruen, Ausgabe ist maschinenlesbar (JSON).

### P2 Research-Wiki (yesresearch)
Ziel: belegte Recherche zur unabhaengigen Verifikation von Behauptungen. Was macht eine Behauptung pruefbar, wie verifizieren andere Systeme (CI, reproduzierbare Builds, Provenienz, Fact-Checking, Truth-Maintenance, LLM-Selbstpruefung), und was ist uebertragbar.
Output: `yesdocs/pruefer/wiki/`
Abnahme: INDEX.md mit Mermaid, mindestens 2 Quellen je Datei, jede Aussage zitiert.

### P3 Evaluations-Harness (yesloop), abhaengig von P1
Ziel: ein Pruefset aus dreissig Meldungen, die Haelfte auf bekannte Weise falsch, generiert aus einem Fixture-Repo. `python3 -m proofboy eval --set <datei>` fuehrt den Pruefer aus und berichtet Erkennungsrate, Falschbestaetigungsrate, Unpruefbar-Quote.
Abnahme: `eval` liefert die Zahlen, die Schwellen aus der SPEC sind als Test hinterlegt.

### P4 CLI, Integration, Doku (yesloop), abhaengig von P1 und P3
Ziel: `python3 -m proofboy check --section <name> --project <pfad>` liest eine YesMem-Scratchpad-Section als Meldung, Makefile (`make check`, `make eval`, `make test`), README vollstaendig.
Abnahme: `make` laeuft, README erklaert Nutzung, ein echter Done-Bericht aus einem Beispiel-Repo wird geprueft.

## NEXT-SPAWN Regeln

- Nach P0: P1 und P2 parallel spawnen.
- P3 erst nachdem P1 gemergt ist.
- P4 erst nachdem P1 und P3 gemergt sind.
- P2 jederzeit mergbar.

## Zeitbudget

12 Stunden ab 2026-09-12 00:00. Phase bis 08:00 nicht in REVIEW: `ESCALATION:` in der Conveyor-Section.

## Eskalation

Zeilen mit Prefix `ESCALATION:` in der Conveyor-Section sind fuer den Nutzer.

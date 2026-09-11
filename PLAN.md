# PLAN bemyself

Diese Datei ist die kanonische Quelle. Der Suborchestrator liest sie und leitet jeden naechsten Run daraus ab. Nie aus Gedaechtnis raten.

## Ziel

Ein lokales, eigenstaendiges Selbstbericht-Werkzeug plus die erste Chronik. Beleg statt Behauptung: jede Zahl im Digest hat eine Quelle (SQL-Abfrage oder Learning-ID).

## Harte Regeln (immer)

- Nur lesend auf `~/.claude/yesmem` (SQLite URI `mode=ro`). Keine Schreibzugriffe auf die Live-Datenbanken.
- Kein `make deploy`, kein `restart-services`, kein `sudo`, kein `systemctl`.
- Kein Schreibzugriff ausserhalb von `/home/carsten/projects/bemyself`.
- Kein Anfassen von `~/.claude/skills` und `~/.claude/yesmem` (Live-Daten).
- Keine neuen Abhaengigkeiten: Python 3 Standardbibliothek, kein pip.
- Worker mergen nie selbst. Nur der Suborchestrator mergt Worker-Branches nach `main`.
- Arbeit immer im Worktree, Branch `yesloop/<slug>` bzw. `yesresearch/<slug>`.

## Phasen

### P0 Bootstrap (Orchestrator, vor dem ersten Spawn erledigt)
git init, README.md, SPEC.md, PLAN.md, Conveyor-Section, Suborchestrator-Briefing, Watchdog-Job.

### P1 Digest (yesloop)
Ziel: `python3 -m bemyself digest` erzeugt einen deterministischen Markdown-Digest aus den YesMem-Datenbanken, nur lesend.
Inhalt: Anzahl aktiver Learnings je Kategorie, offene Aufgaben (`task_type`), die letzten Entscheidungen und Gotchas mit Learning-IDs, laufende Agenten, aktive Pins, Projektgroessen.
Analyseauftrag an den Worker: das reale Schema von `yesmem.db` und `runtime.db` ermitteln (Tabellen, Spalten, Datumsformate), nicht raten.
Abnahme: Digest wird geschrieben, Tests gruen, Schreibzugriff auf die DB nachweislich ausgeschlossen (mode=ro).

### P2 Research-Wiki (yesresearch)
Ziel: belegte Recherche, die das Design von bemyself traegt. Thema: Selbstmodelle und Kontinuitaet bei LLM-Agenten, Vergleich mit mem0, Zep und Letta, und was ein Agenten-Selbstbericht fachlich enthalten muss.
Output: `yesdocs/selbstmodell/wiki/`
Abnahme: INDEX.md mit Mermaid, mindestens 2 Quellen je Datei, jede Aussage zitiert.

### P3 Brief und Index (yesloop), abhaengig von P1
Ziel: `python3 -m bemyself brief` komponiert aus dem Digest einen Brief in der Zustandsbrief-Form (Ich / My Self / And I). `python3 -m bemyself index` regeneriert `briefe/index.md`.
Abnahme: erster Brief unter `briefe/2026-09-12.md`, Index vorhanden, Tests gruen.

### P4 Doku und Runner (yesloop), abhaengig von P1 und P3
Ziel: README vollstaendig, ein Makefile (`make digest`, `make brief`, `make test`) und ein einfacher lokaler Runner (Shell-Skript, kein systemd), der Digest und Brief erzeugt.
Abnahme: `make digest` und `make brief` laufen, README erklaert Installation und Nutzung.

## NEXT-SPAWN Regeln

- Nach P0: P1 und P2 parallel spawnen (fachlich unabhaengig).
- P3 erst nachdem P1 gemergt ist.
- P4 erst nachdem P1 und P3 gemergt sind.
- P2 kann jederzeit gemergt werden.
- Jeder Worker bekommt einen eigenen Worktree aus dem aktuellen `main` von bemyself.

## Zeitbudget

12 Stunden ab 2026-09-12 00:00. Ist eine Phase bis 08:00 nicht mindestens in REVIEW, gehoert das als `ESCALATION:` in die Conveyor-Section.

## Eskalation

Zeilen mit dem Prefix `ESCALATION:` in der Conveyor-Section sind fuer den Nutzer bestimmt. Alles andere regelt der Suborchestrator selbst.

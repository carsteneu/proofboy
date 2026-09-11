# SPEC bemyself: der Pruefer

## Zweck

Ein lokales Kommandozeilen-Werkzeug, das eine Meldung ueber den Zustand der Welt gegen die Welt prueft. Die Meldung stammt typischerweise aus dem DONE-Bericht eines Agenten (Phase 6 eines Yesloop-Laufs) oder aus einem Learning. Der Pruefer glaubt nichts, er leitet neu her.

## Eingabe

Eine Meldung in Textform oder als Scratchpad-Section, die Behauptungen enthaelt, typischerweise:

- `[COMMIT: <hash>]`, `[BRANCH: <name>]`, `[MERGE: ...]`, `[DEPLOY: ...]`
- "Tests run: <command> -> exit 0"
- "Regression baseline: ..."
- "send_to orchestrator: yes"
- Phasen-Bloecke mit `**Status:** COMPLETE`

## Behauptungstypen und Pruefungen

| Typ | Pruefung |
|---|---|
| Commit existiert | `git cat-file -e <hash>^{commit}` im Repo |
| Branch gepusht | `git log origin/<branch> -1` enthaelt den Hash |
| Diff-Scope | `git diff --stat <base>..<head>` gegen die im Plan genannten Dateien |
| Tests gruen | sauberer Checkout des Commits, Testkommando ausfuehren, Exitcode und letzte Zeilen |
| Beleg-ID existiert | Nachschlagen in der angegebenen Quelle (Datei, DB, Session-Registry) |
| Deploy erfolgt | Artefakt-Metadaten (mtime, Version) gegen den behaupteten Stand |

Jede Pruefung liefert ein Ergebnis `CONFIRMED`, `REFUTED` oder `UNVERIFIABLE` mit dem ausgeführten Kommando und der rohen Ausgabe.

## Kommandos (Ziel)

| Kommando | Wirkung |
|---|---|
| `python3 -m bemyself check --report <datei> --repo <pfad>` | Alle Behauptungen der Meldung pruefen, Urteil je Behauptung ausgeben |
| `python3 -m bemyself check --section <name> --project <pfad>` | Meldung aus einer YesMem-Scratchpad-Section ziehen und pruefen |
| `python3 -m bemyself eval --set <datei>` | Pruefset auswerten, Erkennungsraten berichten |
| `python3 -m bemyself --json` | Maschinenlesbare Ausgabe fuer alle Kommandos |

## Harte Regeln

- Nur lesend auf `~/.claude/yesmem`. Keine Schreibzugriffe auf Live-Datenbanken.
- Pruefungen laufen in einem Wegwerf-Checkout, nie im Arbeitsverzeichnis des Nutzers.
- Kein Netzwerk ausser `git fetch` gegen das eigene Remote.
- Keine neuen Abhaengigkeiten, Python 3 Standardbibliothek.
- Eine falsche Bestaetigung ist der schwerste Fehler. Im Zweifel `UNVERIFIABLE`, nie `CONFIRMED`.

## Nicht-Ziele

- Keine Reparatur, keine Korrektur von Meldungen. Der Pruefer urteilt, er handelt nicht.
- Kein Ersatz fuer den Done-Guard. Der Guard prueft Form, der Pruefer prueft Substanz.
- Keine Ausfuehrung von Befehlen, die die Meldung selbst vorschlaegt, ohne Whitelist.

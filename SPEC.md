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
| `python3 -m bemyself check --report <datei> --repo <pfad> [--strict] [--sandbox auto\|require\|off]` | Alle Behauptungen der Meldung pruefen, Urteil je Behauptung ausgeben |
| `python3 -m bemyself check --section <name> --project <pfad> [--strict] [--sandbox auto\|require\|off]` | Meldung aus einer YesMem-Scratchpad-Section ziehen und pruefen |
| `python3 -m bemyself eval --set <datei> [--strict] [--sandbox auto\|require\|off]` | Pruefset auswerten, Erkennungsraten berichten |
| `python3 -m bemyself --json` | Maschinenlesbare Ausgabe fuer alle Kommandos |

## Harte Regeln

- Nur lesend auf `~/.claude/yesmem`. Keine Schreibzugriffe auf Live-Datenbanken.
- Pruefungen laufen in einem Wegwerf-Checkout, nie im Arbeitsverzeichnis des Nutzers.
- Der Pruefer selbst nutzt kein Netzwerk ausser `git fetch` gegen das eigene Remote und `git clone` aus dem lokalen Repo. Erlaubte Testkommandos laufen standardmaessig in einem bwrap-Sandkasten (`--sandbox=auto`, wenn bwrap vorhanden ist und startet): Wurzel read-only, nur der Wegwerf-Checkout beschreibbar, eigener Netz-/PID-/UTS-Namensraum. Ohne nutzbares bwrap laufen sie ungesandboxt, und jedes Ergebnis nennt den Grund; `--sandbox=require` laesst sie dann gar nicht laufen (die Testbehauptung bleibt `unpruefbar`, mit `--strict` faellt der Lauf), `--sandbox=off` schaltet den Sandkasten ab. Der Sandkasten ersetzt die Allowlist nicht (nur erlaubte Kommandos laufen ueberhaupt) und schuetzt nicht gegen Kernel-Exploits.
- Keine neuen Abhaengigkeiten, Python 3 Standardbibliothek. bwrap ist ein optionales Systemprogramm, wird zur Laufzeit erkannt und ist nie Voraussetzung fuer den Pruefer selbst.
- Eine falsche Bestaetigung ist der schwerste Fehler. Im Zweifel `UNVERIFIABLE`, nie `CONFIRMED`.

## Strict-Modus

Ohne `--strict` bedeutet Exit 0 "mindestens eine Behauptung bestaetigt, keine widerlegt"; unpruefbare Behauptungen sind erlaubt. Fuer ein Merge-Gate ist das zu schwach: eine Meldung, deren Kernbehauptung (etwa "Tests gruen") nie geprueft wurde, kann Exit 0 liefern, solange eine andere Behauptung (etwa ein existierender Commit) bestaetigt ist.

`check --strict` schliesst die Luecke: Exit 0 nur, wenn jede Behauptung bestaetigt ist. Jede unpruefbare Behauptung ergibt Exit 4, sofern nichts widerlegt wurde und mindestens eine Behauptung bestaetigt ist; widerlegte Behauptungen bleiben Exit 1, und ein Bericht ohne bestaetigte Behauptung bleibt Exit 3. Die Codes 0-3 behalten in beiden Modi dieselbe Bedeutung, 4 ist der strict-spezifische Code. Ohne Flag ist das Verhalten unveraendert. Empfehlung: Merge-Gates mit `check --strict` fahren und nur bei Exit 0 mergen.

`eval --strict` ist ein Opt-in mit derselben Doktrin auf Set-Ebene: der Lauf schlaegt mit Exit 4 fehl, sobald eine Behauptung des Sets unpruefbar bleibt und die Schwellen erfuellt sind; ein Lauf, der die Schwellen verfehlt, bleibt Exit 1. Das ausgelieferte Pruefset besteht diesen Modus bewusst nicht (unpruefbare Behauptungen sind Teil des Designs); `make eval` bleibt unveraendert Exit 0.

## Nicht-Ziele

- Keine Reparatur, keine Korrektur von Meldungen. Der Pruefer urteilt, er handelt nicht.
- Kein Ersatz fuer den Done-Guard. Der Guard prueft Form, der Pruefer prueft Substanz.
- Keine Ausfuehrung von Befehlen, die die Meldung selbst vorschlaegt, ohne Whitelist.

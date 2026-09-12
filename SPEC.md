# SPEC bemyself: der Pruefer

## Zweck

Ein lokales Kommandozeilen-Werkzeug, das eine Meldung ueber den Zustand der Welt gegen die Welt prueft. Die Meldung stammt typischerweise aus dem DONE-Bericht eines Agenten (Phase 6 eines Yesloop-Laufs) oder aus einem Learning. Der Pruefer glaubt nichts, er leitet neu her.

## Eingabe

Eine Meldung in Textform oder als Scratchpad-Section, die Behauptungen enthaelt, typischerweise:

- `[COMMIT: <hash>]`, `[BRANCH: <name>]`, `[MERGE: ...]`, `[DEPLOY: ...]`
- `[HALT: <machine> -> <steps>]` und optional `[SCORE: <machine> -> <ones>]`
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
| HALT/SCORE | Turingmaschine der bbchallenge-Notation mit eigenem Simulator neu ausfuehren (in-process); CONFIRMED nur bei exakt der behaupteten Schrittzahl und, wenn behauptet, exakt dem Score |
| Beleg-ID existiert | Nachschlagen in der angegebenen Quelle (Datei, DB, Session-Registry) |
| Deploy erfolgt | Artefakt-Metadaten (mtime, Version) gegen den behaupteten Stand |

Jede Pruefung liefert ein Ergebnis `CONFIRMED`, `REFUTED` oder `UNVERIFIABLE` mit dem ausgeführten Kommando und der rohen Ausgabe.

## Halten von Turingmaschinen (`HALT`/`SCORE`)

`[HALT: <machine> -> <steps>]` behauptet, dass die Maschine der
bbchallenge-Standardnotation exakt nach `<steps>` Schritten haelt; ein
optionales `[SCORE: <machine> -> <ones>]` auf derselben Zeile fuer dieselbe
Maschine behauptet zusaetzlich den Score. Semantik: Start in A auf leerem
Band, jede Transition zaehlt als Schritt, auch die in den Halt-Zustand `Z`;
der Score ist die Zahl der 1en auf dem Band beim Halt, inklusive des
Schreibzugriffs der Halt-Transition.

Was pruefbar ist und was nicht: Halten ist per Zeuge pruefbar -- die exakte
Schrittzahl ist eine endliche, nachvollziehbare Beobachtung. Nicht-Halten
ist per endlicher Suche grundsaetzlich nicht beweisbar: "nach n Schritten
kein Halt" widerlegt die Behauptung "haelt exakt bei n" (endlicher Zeuge),
ist aber kein Beweis fuer "haelt nie" und wird nie so ausgegeben.

Urteile:

- `CONFIRMED`: exakt die behauptete Schrittzahl (und, falls behauptet, exakt der Score)
- `REFUTED`: frueherer Halt, kein Halt innerhalb der behaupteten Schritte, oder anderer Score
- `UNVERIFIABLE`: die Maschine parst nicht, die Schrittzahl ist keine schlichte
  nichtnegative Ganzzahl (etwa `2↑↑↑5`), sie liegt ueber dem ausfuehrbaren Limit,
  oder widersprechende `[SCORE]`-Marker machen die Behauptung mehrdeutig

Das ausfuehrbare Limit ist die groesste Schrittzahl, die der Simulator fuer
eine Behauptung ausfuehren darf: Default 47.176.870 (traegt den
BB(5)-Champion), konfigurierbar ueber `--halt-limit N` bei `check` und
`eval`. Eine Behauptung ueber dem Limit wird nicht ausgefuehrt und bleibt
`UNVERIFIABLE`. Der Simulator (`bemyself/turing.py`, API `parse(machine)` und
`run(machine, max_steps)`) laeuft in-process in reiner
Standardbibliothek: kein Subprozess, kein Netz-, Repo- oder Sandkastenbezug
(es entsteht kein ungesandboxtes Fremdkommando); der Speicher waechst linear
mit den ausgefuehrten Schritten. Das Limit begrenzt die einzelne Behauptung,
nicht den Report; ein Claim am Limit kostet wenige Sekunden, viele HALT-Zeilen
summieren sich.

Erweiterbarkeit: Behauptungstypen liegen als Registry vor
(`bemyself/claimtypes/`): ein neuer Typ ist ein Modul plus ein Eintrag in
`CLAIM_TYPES`, ohne Aenderung an Parser (`bemyself/report.py`) oder CLI
(`bemyself/cli.py`). Rezept mit durchgerechnetem Mini-Beispiel: README,
Abschnitt "Neuen Behauptungstyp hinzufuegen".

## Kommandos (Ziel)

| Kommando | Wirkung |
|---|---|
| `python3 -m bemyself check --report <datei> --repo <pfad> [--strict] [--sandbox auto\|require\|off] [--halt-limit N]` | Alle Behauptungen der Meldung pruefen, Urteil je Behauptung ausgeben |
| `python3 -m bemyself check --section <name> --project <pfad> [--strict] [--sandbox auto\|require\|off] [--halt-limit N]` | Meldung aus einer YesMem-Scratchpad-Section ziehen und pruefen |
| `python3 -m bemyself eval --set <datei> [--strict] [--sandbox auto\|require\|off] [--halt-limit N]` | Pruefset auswerten, Erkennungsraten berichten |
| `python3 -m bemyself --json` | Maschinenlesbare Ausgabe fuer alle Kommandos |

## Harte Regeln

- Nur lesend auf `~/.claude/yesmem`. Keine Schreibzugriffe auf Live-Datenbanken.
- Pruefungen laufen in einem Wegwerf-Checkout, nie im Arbeitsverzeichnis des Nutzers.
- Der Pruefer selbst nutzt kein Netzwerk ausser `git fetch` gegen das eigene Remote und `git clone` aus dem lokalen Repo. Erlaubte Testkommandos laufen standardmaessig in einem bwrap-Sandkasten (`--sandbox=auto`, wenn bwrap vorhanden ist und startet): Wurzel read-only, nur der Wegwerf-Checkout beschreibbar, eigener Netz-/PID-/UTS-Namensraum, `/run` als leeres tmpfs (Socket-Pfade des Rechners fehlen). Ohne nutzbares bwrap laufen sie ungesandboxt, und jedes Ergebnis nennt den Grund; `--sandbox=require` laesst sie dann gar nicht laufen (die Testbehauptung bleibt `unpruefbar`, mit `--strict` faellt der Lauf), `--sandbox=off` schaltet den Sandkasten ab. Der Sandkasten ersetzt die Allowlist nicht (nur erlaubte Kommandos laufen ueberhaupt), ist keine vollstaendige Isolationsgrenze gegen feindlichen Code (sichtbare Dateien bleiben lesbar) und schuetzt nicht gegen Kernel-Exploits.
- Keine neuen Abhaengigkeiten, Python 3 Standardbibliothek. bwrap ist ein optionales Systemprogramm, wird zur Laufzeit erkannt und ist nie Voraussetzung fuer den Pruefer selbst. Die HALT-Pruefung laeuft in-process im Simulator und braucht weder Netz noch Sandkasten.
- Eine falsche Bestaetigung ist der schwerste Fehler. Im Zweifel `UNVERIFIABLE`, nie `CONFIRMED`.

## Strict-Modus

Ohne `--strict` bedeutet Exit 0 "mindestens eine Behauptung bestaetigt, keine widerlegt"; unpruefbare Behauptungen sind erlaubt. Fuer ein Merge-Gate ist das zu schwach: eine Meldung, deren Kernbehauptung (etwa "Tests gruen") nie geprueft wurde, kann Exit 0 liefern, solange eine andere Behauptung (etwa ein existierender Commit) bestaetigt ist.

`check --strict` schliesst die Luecke: Exit 0 nur, wenn jede Behauptung bestaetigt ist. Jede unpruefbare Behauptung ergibt Exit 4, sofern nichts widerlegt wurde und mindestens eine Behauptung bestaetigt ist; widerlegte Behauptungen bleiben Exit 1, und ein Bericht ohne bestaetigte Behauptung bleibt Exit 3. Die Codes 0-3 behalten in beiden Modi dieselbe Bedeutung, 4 ist der strict-spezifische Code. Ohne Flag ist das Verhalten unveraendert. Empfehlung: Merge-Gates mit `check --strict` fahren und nur bei Exit 0 mergen.

`eval --strict` ist ein Opt-in mit derselben Doktrin auf Set-Ebene: der Lauf schlaegt mit Exit 4 fehl, sobald eine Behauptung des Sets unpruefbar bleibt und die Schwellen erfuellt sind; ein Lauf, der die Schwellen verfehlt, bleibt Exit 1. Das ausgelieferte Pruefset besteht diesen Modus bewusst nicht (unpruefbare Behauptungen sind Teil des Designs); `make eval` bleibt unveraendert Exit 0.

## Nicht-Ziele

- Keine Reparatur, keine Korrektur von Meldungen. Der Pruefer urteilt, er handelt nicht.
- Kein Ersatz fuer den Done-Guard. Der Guard prueft Form, der Pruefer prueft Substanz.
- Keine Ausfuehrung von Befehlen, die die Meldung selbst vorschlaegt, ohne Whitelist.

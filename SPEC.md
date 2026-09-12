# SPEC bemyself: der Pruefer

## Zweck

Ein lokales Kommandozeilen-Werkzeug, das eine Meldung ueber den Zustand der Welt gegen die Welt prueft. Die Meldung stammt typischerweise aus dem DONE-Bericht eines Agenten (Phase 6 eines Yesloop-Laufs) oder aus einem Learning. Der Pruefer glaubt nichts, er leitet neu her.

## Eingabe

Eine Meldung in Textform oder als Scratchpad-Section, die Behauptungen enthaelt, typischerweise:

- `[COMMIT: <hash>]`, `[BRANCH: <name>]`, `[MERGE: ...]`, `[DEPLOY: ...]`
- `[HALT: <machine> -> <steps>]` und optional `[SCORE: <machine> -> <ones>]`
- `[SEARCHED: <machine> -> <n>]` (begrenzter Suchlauf ohne Halt, kein Nicht-Halte-Beweis)
- `[CYCLE: <machine> -> t1,t2,d]` (uebersetzter Zyklus, Nicht-Halte-Beweis fuer diese Maschine mit diesem Zertifikat)
- `[COMPUTE: <kommando> -> <sha256 des stdout>]` (Rechenzertifikat, gepinnter Commit)
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
| SEARCHED | Maschine n Schritte neu ausfuehren (in-process); CONFIRMED nur fuer den begrenzten Lauf ohne Halt, ausdruecklich kein Nicht-Halte-Beweis |
| CYCLE | Maschine bis t2 neu ausfuehren (in-process): haltfreies Fenster, gleicher Zustand, Kopfdistanz d, Band gleich im erreichbaren Fenster; Nicht-Halte-Beweis fuer diese Maschine mit diesem Zertifikat |
| COMPUTE | Kommando im Wegwerf-Checkout des gepinnten Commits im bwrap-Sandkasten ausfuehren, sha256(stdout) streamen und vergleichen |
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
(es entsteht kein ungesandboxtes Fremdkommando; ein Report aus lauter
HALT-Behauptungen laeuft ohne `--repo`); der Speicher waechst linear
mit den ausgefuehrten Schritten. Das Limit begrenzt die einzelne Behauptung,
nicht den Report; ein Claim am Limit kostet wenige Sekunden, viele HALT-Zeilen
summieren sich.

Erweiterbarkeit: Behauptungstypen liegen als Registry vor
(`bemyself/claimtypes/`): ein neuer Typ ist ein Modul plus ein Eintrag in
`CLAIM_TYPES` samt `needs_repo`, das den Repository-Bedarf deklariert, und
`binds_commit`, das die Bindung an den `[COMMIT]`-Marker der Meldung
deklariert, ohne Aenderung an Parser (`bemyself/report.py`) oder CLI
(`bemyself/cli.py`) --
`check --report` verlangt `--repo` nur, wenn ein vorkommender Typ ihn
deklariert. Rezept mit durchgerechnetem Mini-Beispielen (`[EVEN]`,
`[COMPUTE]`): README, Abschnitt "Neuen Behauptungstyp hinzufuegen".

## Begrenzter Suchlauf (`SEARCHED`)

`[SEARCHED: <machine> -> <n>]` behauptet eine endliche Beobachtung: die
Maschine wurde neu ausgefuehrt und hielt innerhalb von `<n>` Schritten nicht.
Die Simulation laeuft in-process im selben Simulator wie HALT (kein
Subprozess, kein Netz, kein Repo-, kein Sandkastenbezug). Urteile:
`CONFIRMED` nur fuer genau diesen begrenzten Lauf ohne Halt; `REFUTED`, wenn
die Maschine frueher haelt (der Halt ist der Beleg); `UNVERIFIABLE` bei
unparsebarer Maschine, ungueltiger Schrittzahl, einem Wert von 0 (ein
Nullschritt-Lauf beobachtet nichts) oder einem Wert ueber dem ausfuehrbaren
Limit.

Die Grenze ist Doktrin-Kern: Eine endliche Suche kann Nicht-Halten nicht
beweisen. Der Urteilstext sagt das ausdruecklich ("a bounded search of N
steps found no halt; this does not prove that the machine never halts"),
README und SPEC dokumentieren es, und ein Test fixiert die Formulierung; der
Typ darf nie als Nicht-Halte-Beweis lesbar sein.

Das ausfuehrbare Limit ist Default 10.000.000 Schritte (bewusst begrenzt,
nicht das HALT-Limit), konfigurierbar mit `--search-limit N` bei `check` und
`eval`; eine Behauptung ueber dem Limit wird nicht ausgefuehrt und bleibt
`UNVERIFIABLE`.

## Uebersetzte Zyklen (`CYCLE`)

`[CYCLE: <machine> -> t1,t2,d]` behauptet einen uebersetzten Zyklus
(translated cycler, Lin-Rekurrenz -- dieselbe Klasse wie der
bbchallenge-Decider "Translated Cyclers"): Zustand und Band relativ zum Kopf
nach `t2` Schritten sind Zustand und Band nach `t1` Schritten, um `d` Zellen
verschoben, und die Maschine liest zwischen den beiden Schritten keine Zelle
ausserhalb des dabei erreichbaren Fensters. Damit wiederholt sich der
Abschnitt Schub um Schub uebersetzt (Determinismus), und ein Halt nach `t2`
muesste schon im haltfreien Fenster liegen: Die Maschine haelt nie. Die
Simulation laeuft in-process im selben Simulator wie HALT/SEARCHED (kein
Subprozess, kein Netz, kein Repo-, kein Sandkastenbezug).

Urteile: `CONFIRMED` nur bei haltfreiem Fenster bis `t2`, gleichem Zustand,
Kopfdistanz exakt `d` und exakt gleichem Band im erreichbaren Fenster; der
Urteilstext nennt den Beweisgrund in fester Formulierung ("the configuration
at step t2 equals the configuration at step t1 translated by d on every cell
the machine can still reach (it never goes more than L cells left/right of
the head at step t1); therefore by determinism the machine never halts"). `REFUTED` bei
Halt im Fenster, abweichendem Zustand, falscher Kopfdistanz oder abweichender
Zelle (die erste abweichende relative Position im erreichbaren Fenster steht
im Urteil). `UNVERIFIABLE` bei unparsebarer Maschine, ungueltigen Werten
(`t1`/`t2` schlicht nichtnegativ, `d` schlicht ganzzahlig und nicht `0`),
`t2 <= t1`, Wert ueber dem ausfuehrbaren Limit (Default 10.000.000,
`--cycle-limit N` bei `check` und `eval`) oder einem Band jenseits der
Materialisierungsschranke `TAPE_LIMIT` (`2**24` Zellen, beide Bandhaelften
zusammen) -- der Vergleich muss wirklich durchgefuehrt worden sein, es gibt
keine Bestaetigung durch Auslassung.

Abgrenzung: `CONFIRMED` ist ein vollstaendiger Nicht-Halte-Beweis fuer diese Maschine mit diesem Zertifikat;
der Typ ist kein allgemeiner Nicht-Halte-Pruefer (er sucht keine Zertifikate, er
rechnet das vorgelegte nach) und kein Ersatz fuer SEARCHED: Ein SEARCHED-Lauf wird nie zu einem CYCLE-Zertifikat aufgewertet.
Der SEARCHED-Urteilstext bleibt unveraendert ("does not prove that the machine
never halts").

## Rechenzertifikate (`COMPUTE`)

`[COMPUTE: <kommando> -> <sha256>]` behauptet, dass das Kommando auf stdout
genau die Bytes ausgibt, deren SHA-256 behauptet wird. Der Pruefer checkt den
Commit der Meldung (genau ein hash-foermiger `[COMMIT]`-Marker -- Platzhalter
wie `<hash>` zaehlen nicht; die Bindung deklariert der Typ mit
`binds_commit=True`) in einen Wegwerf-Checkout aus
(`git clone --no-hardlinks` + `git checkout`) und fuehrt das Kommando dort im
Sandkasten aus (dieselbe bwrap-Semantik wie bei Testkommandos: read-only
Wurzel, beschreibbarer Checkout, eigener Netz-/PID-/UTS-Namensraum,
`--die-with-parent`). stdout wird beim Lesen gehasht (Streaming), der
SHA-256 mit dem behaupteten verglichen.

Urteile: `CONFIRMED` nur, wenn der Lauf mit Exit 0 abgeschlossen wurde UND der
Hash exakt stimmt -- ein fehlgeschlagenes Kommando wird nie zertifiziert
(Exit-Code als Abschluss-Gate, nicht als Hash-Kriterium); `REFUTED` bei
abweichendem Hash nach sauberem Abschluss; `UNVERIFIABLE` bei Kommando
ausserhalb der COMPUTE-Allowlist (Abgleich auf den ausgefuehrten
argv-Tokens), fehlendem/nicht aufloesbarem Commit, nicht gefundenem Programm
(Vorabpruefung), abgelehnten Argumenten (dieselben Escape-Regeln), nicht
nutzbarem Sandkasten bei `--sandbox=require`, Timeout (300 s), stdout ueber
64 MiB (mehr wird abgelehnt, nie gekuerzt) oder Exit-Status ungleich 0. Kein
Kommando laeuft je ohne Allowlist, ohne Shell-Interpretation und ohne
Sandkastenpfad. Die Limits begrenzen einen Lauf, nicht die Meldung.

Die COMPUTE-Allowlist ist getrennt und minimal: Default
`python3 -m bemyself.turing` (der Simulator dieses Repos; in einem anderen
Repo laeuft er nur, wenn der gepinnte Commit das Paket mitbringt);
`--allow <prefix>` (wiederholbar) erweitert sie zusammen mit der
Test-Allowlist. Das Netzwerk ist im Sandkasten aus (bestehende
`--unshare-net`-Semantik).

Grenze: Der Hash belegt die Ausgabe des Kommandos auf dem gepinnten Commit,
nicht die Bedeutung der Rechnung; der Checkout bringt seinen eigenen Code
mit, wer den Commit kontrolliert, kontrolliert die Ausgabe.

## Kommandos (Ziel)

| Kommando | Wirkung |
|---|---|
| `python3 -m bemyself check --report <datei> [--repo <pfad>] [--strict] [--sandbox auto\|require\|off] [--halt-limit N] [--search-limit N] [--cycle-limit N]` | Alle Behauptungen der Meldung pruefen, Urteil je Behauptung ausgeben; `--repo` ist Pflicht, sobald eine vorkommende Behauptung ein Repository deklariert |
| `python3 -m bemyself check --section <name> --project <pfad> [--strict] [--sandbox auto\|require\|off] [--halt-limit N] [--search-limit N] [--cycle-limit N]` | Meldung aus einer YesMem-Scratchpad-Section ziehen und pruefen |
| `python3 -m bemyself eval --set <datei> [--strict] [--sandbox auto\|require\|off] [--halt-limit N] [--search-limit N] [--cycle-limit N]` | Pruefset auswerten, Erkennungsraten berichten |
| `python3 -m bemyself --json` | Maschinenlesbare Ausgabe fuer alle Kommandos |

`--repo` verlangt `check --report` nur, wenn mindestens eine vorkommende
Behauptung ein Repository deklariert (COMMIT, BRANCH, Tests, Diff-Scope; eine
per `--files` ergaenzte Diff-Scope-Behauptung zaehlt mit). Der
Bedarf steht am Checker bzw. am `ClaimType.needs_repo` in der Registry, nicht
als Liste im CLI; HALT/SCORE und unbekannte Typen ohne Checker laufen ohne
`--repo` (und bleiben gegebenenfalls `UNVERIFIABLE`).

## Harte Regeln

- Nur lesend auf `~/.claude/yesmem`. Keine Schreibzugriffe auf Live-Datenbanken.
- Pruefungen laufen in einem Wegwerf-Checkout, nie im Arbeitsverzeichnis des Nutzers.
- Der Pruefer selbst nutzt kein Netzwerk ausser `git fetch` gegen das eigene Remote und `git clone` aus dem lokalen Repo. Erlaubte Testkommandos laufen standardmaessig in einem bwrap-Sandkasten (`--sandbox=auto`, wenn bwrap vorhanden ist und startet): Wurzel read-only, nur der Wegwerf-Checkout beschreibbar, eigener Netz-/PID-/UTS-Namensraum, `/run` als leeres tmpfs (Socket-Pfade des Rechners fehlen). Ohne nutzbares bwrap laufen sie ungesandboxt, und jedes Ergebnis nennt den Grund; `--sandbox=require` laesst sie dann gar nicht laufen (die Testbehauptung bleibt `unpruefbar`, mit `--strict` faellt der Lauf), `--sandbox=off` schaltet den Sandkasten ab. Der Sandkasten ersetzt die Allowlist nicht (nur erlaubte Kommandos laufen ueberhaupt), ist keine vollstaendige Isolationsgrenze gegen feindlichen Code (sichtbare Dateien bleiben lesbar) und schuetzt nicht gegen Kernel-Exploits.
- Keine neuen Abhaengigkeiten, Python 3 Standardbibliothek. bwrap ist ein optionales Systemprogramm, wird zur Laufzeit erkannt und ist nie Voraussetzung fuer den Pruefer selbst. Die HALT-, SEARCHED- und CYCLE-Pruefungen laufen in-process im Simulator und brauchen weder Netz noch Sandkasten. COMPUTE-Kommandos laufen unter derselben Sandkasten-Semantik wie Testkommandos, nur ueber die getrennte, standardmaessig minimale COMPUTE-Allowlist (`--allow` erweitert); ohne nutzbaren Sandkasten bei `--sandbox=require` laufen sie gar nicht.
- Eine falsche Bestaetigung ist der schwerste Fehler. Im Zweifel `UNVERIFIABLE`, nie `CONFIRMED`. Fuer COMPUTE heisst das: kein Lauf ohne Allowlist, kein Lauf ohne aufloesbaren Commit, ausdrueckliche Vorabpruefung des Programms, Ausgabe- und Zeitlimits statt Kuerzung, und ein Urteil nur ueber den Hash des stdout.

## Strict-Modus

Ohne `--strict` bedeutet Exit 0 "mindestens eine Behauptung bestaetigt, keine widerlegt"; unpruefbare Behauptungen sind erlaubt. Fuer ein Merge-Gate ist das zu schwach: eine Meldung, deren Kernbehauptung (etwa "Tests gruen") nie geprueft wurde, kann Exit 0 liefern, solange eine andere Behauptung (etwa ein existierender Commit) bestaetigt ist.

`check --strict` schliesst die Luecke: Exit 0 nur, wenn jede Behauptung bestaetigt ist. Jede unpruefbare Behauptung ergibt Exit 4, sofern nichts widerlegt wurde und mindestens eine Behauptung bestaetigt ist; widerlegte Behauptungen bleiben Exit 1, und ein Bericht ohne bestaetigte Behauptung bleibt Exit 3. Die Codes 0-3 behalten in beiden Modi dieselbe Bedeutung, 4 ist der strict-spezifische Code. Ohne Flag ist das Verhalten unveraendert. Empfehlung: Merge-Gates mit `check --strict` fahren und nur bei Exit 0 mergen.

`eval --strict` ist ein Opt-in mit derselben Doktrin auf Set-Ebene: der Lauf schlaegt mit Exit 4 fehl, sobald eine Behauptung des Sets unpruefbar bleibt und die Schwellen erfuellt sind; ein Lauf, der die Schwellen verfehlt, bleibt Exit 1. Das ausgelieferte Pruefset besteht diesen Modus bewusst nicht (unpruefbare Behauptungen sind Teil des Designs); `make eval` bleibt unveraendert Exit 0.

## Nicht-Ziele

- Keine Reparatur, keine Korrektur von Meldungen. Der Pruefer urteilt, er handelt nicht.
- Kein Ersatz fuer den Done-Guard. Der Guard prueft Form, der Pruefer prueft Substanz.
- Keine Ausfuehrung von Befehlen, die die Meldung selbst vorschlaegt, ohne Whitelist.

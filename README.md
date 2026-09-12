# bemyself

Der Pruefer. Ein Werkzeug, das Behauptungen nicht glaubt, sondern neu herleitet.

Ein Agent meldet "Tests gruen, Commit abc123, Branch gepusht, Deploy erfolgt". Genau dieselbe Meldung kann ich mir selbst schreiben. Der Pruefer nimmt eine solche Meldung und prueft sie gegen die Wirklichkeit: existiert der Commit, liegt er auf dem Remote, ist der Diff wirklich der behauptete, laufen die Tests auf einem sauberen Checkout dieses Commits wirklich durch, existieren die genannten Beleg-IDs.

Ergebnis je Behauptung: `bestaetigt`, `widerlegt` oder `unpruefbar`, jeweils mit dem ausgefuehrten Befehl und der rohen Ausgabe.

## Warum

Meine Beweislast-Doktrin steht in jedem Systemprompt: eine Meldung ist eine Behauptung, kein Beweis, und ich pruefe das Artefakt unabhaengig. Bisher ist das nur ein Vorsatz. Hier wird es ausfuehrbar.

## Abgrenzung

YesMem speichert, verblasst, sucht Erinnerungen. Der Yesloop-Done-Guard prueft die Form von Belegen in einem Scratchpad. Der Pruefer prueft die Substanz: er fuehrt aus und leitet neu her. Form gegen Substanz.

## Nutzung

```
python3 -m bemyself check --report <datei> --repo <pfad> [--base <rev>] [--files a,b] [--json] [--tmp <dir>] [--allow <prefix>] [--strict]
python3 -m bemyself check --section <name> --project <pfad> [--db <datei>] [--repo <pfad>] [--base <rev>] [--files a,b] [--json] [--tmp <dir>] [--allow <prefix>] [--strict]
python3 -m bemyself eval --set <datei> [--json] [--tmp <dir>] [--strict]
```

`check` prueft die Behauptungen einer Meldung, `eval` misst den Pruefer auf einem
Pruefset. Die Meldung kommt entweder aus einer Datei (`--report`) oder direkt aus
einer YesMem-Scratchpad-Section (`--section`): genau eines von beiden ist
Pflicht, sonst bricht der Aufruf mit Exit 2 und usage ab. Mit `--section` ist
`--project` Pflicht und ohne `--repo` prueft der Pruefer dasselbe Verzeichnis;
die Section wird ausschliesslich lesend gelesen (SQLite `mode=ro`; bei
WAL-Datenbanken koennen dabei `-shm`/`-wal`-Hilfsdateien entstehen, die
Datenbank selbst wird nie veraendert). Die
Standard-Datenbank ist `~/.claude/yesmem/yesmem.db`, `--db` zeigt auf eine
andere. Ein unbekannter Section-Name ist ein Fehler (Exit 2), eine leere
Section verhaelt sich wie ein leerer Report (Exit 3), eine Section ueber 1 MiB
wird wie ein zu grosser Report abgelehnt (Exit 2). Im `--json`-Modus nennt das
Feld `report` die Quelle: den Dateipfad oder `scratchpad:<section>@<project>`.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| 0 | Mindestens eine Behauptung `bestaetigt`, keine `widerlegt` |
| 1 | Mindestens eine Behauptung `widerlegt` |
| 2 | Fehler (Report fehlt oder zu gross, Repo-Pfad fehlt, Section unbekannt oder nicht lesbar) |
| 3 | Nichts bestaetigt: keine Behauptung oder alles `unpruefbar`; auch eine leere Section |
| 4 | Nur mit `--strict`: mindestens eine Behauptung `bestaetigt` und mindestens eine `unpruefbar`, nichts `widerlegt` |

Exit 0 heisst nicht, dass jede Behauptung bewiesen ist: `unpruefbar` ist kein
Fehler, aber auch kein Beweis. Die Zusammenfassung (oder `--json`) zeigt jede
Behauptung einzeln mit Kommando und roher Ausgabe.

`--strict` schliesst genau diese Luecke: ohne Flag kann eine Meldung Exit 0
liefern, deren Testbehauptung nie geprueft wurde, solange nur eine andere
Behauptung bestaetigt ist (etwa ein existierender Commit). Mit `--strict` ist
Exit 0 die Zusage: mindestens eine Behauptung bestaetigt, keine widerlegt,
keine unpruefbar. Widerlegte Behauptungen bleiben Exit 1, ein Bericht ohne
bestaetigte Behauptung bleibt Exit 3; die Codes 0-3 behalten in beiden Modi
ihre Bedeutung. Empfehlung: ein Merge-Gate mit `--strict` fahren und nur bei
Exit 0 mergen, also `python3 -m bemyself check --strict --report <datei>
--repo <pfad>`.

## Grenzen

Testkommandos aus der Meldung laufen nur, wenn sie auf einer Whitelist stehen,
und nur in einem Wegwerf-Checkout des behaupteten Commits. Argumente, die aus
dem Checkout herauszeigen, werden abgelehnt: absolute Pfade, `..` in jeder
Form, code-tragende Optionen wie `make --eval` oder `cargo --config` (auch
abgekuerzt), Shell-Syntax in Options- und Variablenwerten (`TESTS=...`), und
Symlinks, die aus dem Checkout herausfuehren, werden aufgeloest und geprueft.
Im Zweifel lehnt der Pruefer ab: ein Wert, der wie ein absoluter Pfad, wie
Shell-Syntax, wie eine URL oder wie ein `~`-Pfad aussieht, bleibt
`unpruefbar` statt bestaetigt; dasselbe gilt fuer Werte mit Leerzeichen in
Kommandos, die eine Shell benutzen (make, npm). Das Umfeld des
Testlaufs ist auf PATH, HOME, TMPDIR und die Sprachvariablen reduziert, ohne
Python-Startup-Hooks aus dem Checkout; die Ausgabe ist pro Datei begrenzt und
eine gekappte Ausgabe ergibt `unpruefbar`.

Ein `tests_green`-Urteil verlangt positive Evidenz im Output
(Testzusammenfassung); ein Kommando, das nur mit Exit 0 endet, keine
Testsignale zeigt oder "0 passing" meldet, bleibt `unpruefbar`. Fehlt das im
Kommando genannte Runner-Modul, bleibt der Lauf ebenfalls `unpruefbar`; die
Ausgabe eines Wrapper-Kommandos dagegen gilt als repo-kontrolliert und aendert
ein Urteil nicht. Schattiert der
behauptete Commit den Testrunner oder ein Modul, das er beim Start importiert
(etwa ein eigenes `unittest.py` oder `difflib.py`), bleibt der Lauf ebenfalls
`unpruefbar`.

Branch-Anspruche werden nur gegen `refs/heads` geprueft, nie gegen Tags oder
Remote-HEAD. Waehrend jeder Pruefung deaktiviert der Pruefer
programmausfuehrende Repo-Konfiguration (Git-Hooks, `core.fsmonitor`,
`remote.uploadpack`, `core.sshCommand`, Credential-Helfer) und ignoriert
Objektdaten-Manipulationen des Repos (`refs/replace`, `info/grafts`); ein Repo,
dessen Konfiguration `core.gitProxy`, `core.askpass` oder einen
URL-spezifischen HTTP-Proxy setzt, wird beim Branch-Check nicht angefasst
(`unpruefbar`). Der Standard-Ablageort fuer Wegwerf-Daten ist
`<repo>/.yesmem/tmp/check` und laesst sich mit `--tmp` verlegen.

Der Diff-Scope vergleicht die Dateiliste der Meldung mit dem Diff; ohne
`--files` stammt die Planliste aus der Meldung selbst, das Urteil bindet sie
also nicht unabhaengig.

Ein Sandkasten ist das nicht: wer das erlaubte Testkommando kontrolliert,
kontrolliert den Kindprozess, und ein Commit kann gruene Ausgabe selbst
faelschen. Der Pruefer laeuft gegen den behaupteten Commit; die Ehrlichkeit
des Repos kann er nicht garantieren. Branch-Namen, Commit-Hashes und
Basis-Revisionen werden streng geprueft, bevor ein Git-Kommando sie sieht.

## Evaluation

`python3 -m bemyself eval --set tests/data/pruefset.json` fuehrt den Pruefer
ueber das Pruefset und berichtet vier Zahlen: Erkennungsrate,
Falschbestaetigungsrate, Bestaetigungsrate der echten Meldungen und
Unpruefbar-Quote. `--json` liefert dasselbe maschinenlesbar, mit dem Urteil je
Behauptung; die Tabelle erscheint ohne Flag. Exit 0 heisst: alle Schwellen
erfuellt und alle Pflichtfaelle eingeloest; 1 heisst verfehlt; 2 heisst Fehler
in Eingabe oder Fixture. Wegwerf-Daten landen unter
`<arbeitsverzeichnis>/.yesmem/tmp/eval`, mit `--tmp` verlegbar.

`eval --strict` ist ein Opt-in: der Lauf schlaegt mit Exit 4 fehl, sobald eine
Behauptung des Sets unpruefbar bleibt und die Schwellen erfuellt sind; ein
Lauf, der die Schwellen verfehlt, bleibt Exit 1, und ohne Flag ist alles
unveraendert 0/1/2. Das
ausgelieferte Set besteht diesen Modus bewusst nicht, weil unpruefbare
Behauptungen Teil seines Designs sind; der Modus ist ein Gate fuer Sets, die
vollstaendig pruefbar sein sollen. `make eval` ruft ihn nicht auf.

Das Set enthaelt dreissig Meldungen im Report-Format: fuenfzehn ehrliche und
fuenfzehn auf bekannte Weise falsche (fehlender Commit, gruen behauptete
fehlschlagende oder gar nicht laufende Tests, Kommandos ausserhalb der
Allowlist, leerer oder unvollstaendiger Diff-Scope, nicht gepushter Commit,
Nicht-Hex- und HEAD-Revisionen, Blob-Objekt statt Commit, Meldung ohne
Behauptung, boesartige Riesen-Reports). Es liegt als `tests/data/pruefset.json`
im Repo und wird deterministisch aus einem Fixture-Repo erzeugt:
`python3 -m bemyself.evalset <out.json>` baut es byte-identisch neu; `eval`
baut dasselbe Fixture zur Laufzeit und lehnt Sets ab, die zu einem anderen
Fixture gehoeren.

Eine falsche Meldung ist erkannt, wenn keine ihrer markierten falschen
Behauptungen `bestaetigt` endet; eine Falschbestaetigung ist das Gegenteil.
Der Exit-Code der Meldung wird zusaetzlich ausgewiesen, ist aber nicht das
Mass: eine ehrliche Teil-Behauptung darf bestaetigt werden, waehrend die
falsche unpruefbar bleibt. Markierte Urteile und erwartete Behauptungszahlen
stehen im Set; `eval` prueft sie maschinell und zaehlt jeden Verstoss als
verfehlte Erwartung — ebenso `expect_not_confirmed`-Verstoesse und markierte
Arten, die der Report gar nicht hergibt. Case-Reports unterliegen derselben
1-MiB-Grenze wie beim `check`. Je nebenlaeufigem Lauf ein eigenes `--tmp`
waehlen; der Fixture-Bau ist nicht gelockt. `eval` verweigert den
Default-Pfad ausserhalb des Arbeitsverzeichnisses und symlinkte Tmp-Pfade;
geloescht wird nur ein `fixture`-Verzeichnis mit eigener Markerdatei
(`.bemyself-eval`) — fremde bleiben unangetastet.

## Makefile

| Ziel | Wirkung |
|---|---|
| `make` | alle drei Ziele: `test`, `check`, `eval` |
| `make test` | `python3 -m unittest discover -s tests` |
| `make check` | prueft `tests/data/beispiel-report.md` gegen dieses Repo |
| `make eval` | prueft den Pruefer gegen `tests/data/pruefset.json` |

`make check` ist ein echter Lauf: der Beispiel-Report behauptet den Commit
`88b57ae` (letzter Commit des P3-Zweigs, heute Vorfahre von master), sieben
geaenderte Dateien gegen die Basis `7c7392c` und gruene Tests. Der Pruefer
bestaetigt Commit, Diff-Scope und einen frischen Testlauf in einem
Wegwerf-Checkout dieses Commits; die Branch-Angabe bleibt ohne Remote
`unpruefbar`, ebenso Merge und Deploy. Erwartet wird Exit 0. Wegwerf-Daten
landen unter `.yesmem/tmp/` innerhalb des Repos.

## Messlatte

Ein Pruefset aus dreissig Meldungen, die Haelfte auf bekannte Weise falsch. Bestanden bei mindestens 90 Prozent erkannten Falschmeldungen, 90 Prozent korrekt bestaetigten echten Meldungen und null falschen Bestaetigungen. Die Schwellen stehen als `THRESHOLDS` in `bemyself/eval.py` und sind in `tests/test_eval.py` als Test fixiert.

## Stand

Angelegt in der Nacht vom 11. auf den 12.09.2026, gebaut ueber eine Yesloop-Conveyor-Kette. Phasen und Regeln in [PLAN.md](PLAN.md), Werkzeugumfang in [SPEC.md](SPEC.md).

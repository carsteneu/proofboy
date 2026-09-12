# bemyself

Der Pruefer. Ein Werkzeug, das Behauptungen nicht glaubt, sondern neu herleitet.

Ein Agent meldet "Tests gruen, Commit abc123, Branch gepusht, Deploy erfolgt". Genau dieselbe Meldung kann ich mir selbst schreiben. Der Pruefer nimmt eine solche Meldung und prueft sie gegen die Wirklichkeit: existiert der Commit, liegt er auf dem Remote, ist der Diff wirklich der behauptete, laufen die Tests auf einem sauberen Checkout dieses Commits wirklich durch, existieren die genannten Beleg-IDs.

Ergebnis je Behauptung: `bestaetigt`, `widerlegt` oder `unpruefbar`, jeweils mit dem ausgefuehrten Befehl und der rohen Ausgabe.

## Warum

Meine Beweislast-Doktrin steht in jedem Systemprompt: eine Meldung ist eine Behauptung, kein Beweis, und ich pruefe das Artefakt unabhaengig. Bisher ist das nur ein Vorsatz. Hier wird es ausfuehrbar.

## Abgrenzung

YesMem speichert, verblasst, sucht Erinnerungen. Der Yesloop-Done-Guard prueft die Form von Belegen in einem Scratchpad. Der Pruefer prueft die Substanz: er fuehrt aus und leitet neu her. Form gegen Substanz.

## Exit-Codes

| Code | Bedeutung |
|---|---|
| 0 | Mindestens eine Behauptung `bestaetigt`, keine `widerlegt` |
| 1 | Mindestens eine Behauptung `widerlegt` |
| 2 | Fehler (Report fehlt oder zu gross, Repo-Pfad fehlt) |
| 3 | Nichts bestaetigt: keine Behauptung oder alles `unpruefbar` |

Exit 0 heisst nicht, dass jede Behauptung bewiesen ist: `unpruefbar` ist kein
Fehler, aber auch kein Beweis. Die Zusammenfassung (oder `--json`) zeigt jede
Behauptung einzeln mit Kommando und roher Ausgabe.

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
waehlen; der Fixture-Bau ist nicht gelockt.

## Messlatte

Ein Pruefset aus dreissig Meldungen, die Haelfte auf bekannte Weise falsch. Bestanden bei mindestens 90 Prozent erkannten Falschmeldungen, 90 Prozent korrekt bestaetigten echten Meldungen und null falschen Bestaetigungen. Die Schwellen stehen als `THRESHOLDS` in `bemyself/eval.py` und sind in `tests/test_eval.py` als Test fixiert.

## Stand

Angelegt in der Nacht vom 11. auf den 12.09.2026, gebaut ueber eine Yesloop-Conveyor-Kette. Phasen und Regeln in [PLAN.md](PLAN.md), Werkzeugumfang in [SPEC.md](SPEC.md).

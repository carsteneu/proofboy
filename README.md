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
python3 -m bemyself check --report <datei> [--repo <pfad>] [--base <rev>] [--files a,b] [--artifact-root <dir>] [--json] [--tmp <dir>] [--allow <prefix>] [--strict] [--sandbox auto|require|off] [--halt-limit N] [--search-limit N] [--cycle-limit N]
python3 -m bemyself check --section <name> --project <pfad> [--db <datei>] [--repo <pfad>] [--base <rev>] [--files a,b] [--artifact-root <dir>] [--json] [--tmp <dir>] [--allow <prefix>] [--strict] [--sandbox auto|require|off] [--halt-limit N] [--search-limit N] [--cycle-limit N]
python3 -m bemyself eval --set <datei> [--json] [--tmp <dir>] [--strict] [--sandbox auto|require|off] [--halt-limit N] [--search-limit N] [--cycle-limit N]
```

`check` prueft die Behauptungen einer Meldung, `eval` misst den Pruefer auf einem
Pruefset. Die Meldung kommt entweder aus einer Datei (`--report`) oder direkt aus
einer YesMem-Scratchpad-Section (`--section`): genau eines von beiden ist
Pflicht, sonst bricht der Aufruf mit Exit 2 und usage ab. Mit `--report` ist
`--repo` nur dann Pflicht, wenn die Meldung eine Behauptung enthaelt, deren
Pruefer ein Repository braucht (`COMMIT`, `BRANCH`, Tests, Diff-Scope,
`COMPUTE`, `LEAN`; eine per
`--files` ergaenzte Diff-Scope-Behauptung zaehlt mit); ein
Report aus repo-freien Behauptungen (etwa `[HALT]`) laeuft ohne `--repo`. Fehlt
`--repo` fuer einen repo-beduerftigen Report, bricht der Aufruf mit Exit 2 und
usage ab und nennt den Behauptungstyp. `[MERGE]` und `[ARTIFACT]` verlangen
kein `--repo`: ohne Repository bleibt eine Merge-Behauptung `unpruefbar`, und
`[ARTIFACT]` loest seine Pfade gegen die Artefakt-Wurzel auf
(`--artifact-root`, Default das Repository; ohne beides `unpruefbar`). Mit `--section` ist
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
| 2 | Fehler (Report fehlt oder zu gross, benoetigtes `--repo` fehlt oder ist ungueltig, Section unbekannt oder nicht lesbar) |
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

Die Zusage gilt den Behauptungen, die die Meldung aufstellt: eine Zeile, die
als Vorlage gelesen wird (siehe "Grenzen"), stellt keine auf und erscheint in
keiner Ausgabe -- weder im JSON noch im Exit-Code ist unterscheidbar, ob sie
fehlte oder als Platzhalter dastand. Ein Gate darf das Fehlen einer Zeile
deshalb nicht als Nachweis lesen; wo eine Zeile Pflicht ist, muss das Gate sie
fordern (etwa als Pflichtzeile im Report-Template), nicht ihre Abwesenheit
messen.

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
Objektdaten-Manipulationen des Repos (`refs/replace`, `info/grafts`) sowie den
abgeleiteten Commit-Graph (`core.commitGraph=false` -- eine gepatchte
Commit-Graph-Datei kann Parents erfinden, die das Objekt nicht hat); ein Repo,
dessen Konfiguration `core.gitProxy`, `core.askpass` oder einen
URL-spezifischen HTTP-Proxy setzt, wird beim Branch-Check nicht angefasst
(`unpruefbar`). Der Standard-Ablageort fuer Wegwerf-Daten ist
`<repo>/.yesmem/tmp/check` und laesst sich mit `--tmp` verlegen.

Der Diff-Scope vergleicht die Dateiliste der Meldung mit dem Diff; ohne
`--files` stammt die Planliste aus der Meldung selbst, das Urteil bindet sie
also nicht unabhaengig.

Eine Zeile, deren Marker-Rumpf ein Platzhalter ist -- ein Winkel-Token wie
`<hash>`, `<machine>` oder `<pfad>`, ein woertliches `TODO` oder eine
abgeschnittene Ellipse (`e5b68dd1…`, `...`) -- ist eine Vorlage und keine
Behauptung: der Pruefer ignoriert sie wie eine Zeile ganz ohne Marker und
meldet sie nicht als `unpruefbar`. Die Regel greift auf jeder Parser-Flaeche
(`COMMIT`, `BRANCH`, `MERGE`, `DEPLOY`, `HALT`/`SCORE`, `SEARCHED`, `CYCLE`,
`COMPUTE`, `LEAN`, `IDENT`, `COLORING`, `ARTIFACT`, Diff-Scope und
Testbehauptung) und pro Behauptung: traegt eine Vorlagenzeile daneben
literale Marker -- etwa `[DEPLOY: no]` oder `[MERGE: no]` neben
`[COMMIT: <hash>]` --, bleiben diese Behauptungen bestehen und behalten ihr
bisheriges Urteil.

Grenzfaelle sind ausgemessen und festgelegt. Erhalten bleiben: `go test ./...`
und `src/...` (die ASCII-Ellipse ist das Ende eines Pfadmusters), ein leeres
`<>` (etwa die Shell-Umleitung `3<>file`) und ein `<` ohne schliessendes `>`
(etwa ein Dateiname `a<b.txt`), sowie jeder ausgeschriebene Wert (`e5b68dd1`,
`HEAD`, die Beispielmaschine `M`). Bewusst ignoriert wird dagegen ein Wert,
dessen Text einen Winkel-Token enthaelt -- auch wenn er echt ist, etwa das
Kommando `sed 's/<[^>]*>//g' data.html` --, ein Wert, der mit einer
abschneidenden Ellipse endet (`weird...`, `docs/…`, `pkg/...` als Pfadmuster
ausgenommen), und ein Wert, der genau `TODO` lautet (auch ein Branch oder
eine Datei dieses Namens): diese Formen sind von einer Vorlage nicht zu
unterscheiden, und die Form allein entscheidet. Traegt eine Behauptung den
Platzhalter in einem Feld, entfaellt die ganze Behauptung -- auch ein `[HALT]`
mit echter Maschine und echtem Schrittzahl-Wert, wenn das angehaengte
`[SCORE]` einen Platzhalter traegt. Umschliessende Backticks aendern die
Erkennung nicht.

Der Sandkasten (siehe unten) haertet den Lauf, aendert aber nichts an der
Grundregel: wer das erlaubte Testkommando kontrolliert, kontrolliert den
Kindprozess, und ein Commit kann gruene Ausgabe selbst faelschen. Der Pruefer
laeuft gegen den behaupteten Commit; die Ehrlichkeit des Repos kann er nicht
garantieren. Branch-Namen, Commit-Hashes und
Basis-Revisionen werden streng geprueft, bevor ein Git-Kommando sie sieht.

## Sandkasten

Testkommandos laufen in einem Sandkasten, wenn `bwrap` (bubblewrap)
installiert ist und startet: die Wurzel wird read-only gebunden, nur der
Wegwerf-Checkout des behaupteten Commits ist beschreibbar
(`git clone --no-hardlinks`), das Kommando bekommt einen eigenen Netz-,
PID- und UTS-Namensraum, und `/run` wird durch ein leeres tmpfs maskiert.
Damit ist kein IP-Netzwerk und kein Host-Prozess erreichbar, und die
Socket-Pfade des Rechners (D-Bus, systemd, docker.sock unter `/run` und
`/var/run`) fehlen im Sandkasten; ein Schreibversuch ausserhalb des
Checkouts scheitert mit `Read-only file system` (ausser auf den frisch
eingehaengten privaten tmpfs unter `/run` und `/dev`, die nichts mit dem
Rechner teilen). Unix-Sockets an anderen
sichtbaren Pfaden (etwa unter `/tmp`) bleiben erreichbar, und die Wurzel
ist lesbar: der Sandkasten begrenzt Schreiben, IP-Netz und Prozesssicht,
nicht Lesezugriffe.

| Wert | Wirkung |
|---|---|
| `--sandbox=auto` | Standard: sandboxen, wenn bwrap vorhanden ist und einen Sandkasten startet; sonst laeuft das Kommando ungesandboxt |
| `--sandbox=require` | sandboxen oder ablehnen: ohne nutzbares bwrap laeuft das Kommando gar nicht, die Testbehauptung bleibt `unpruefbar`, und mit `--strict` faellt der Lauf (Exit 4) |
| `--sandbox=off` | nie sandboxen |

Jeder ausgefuehrte Testlauf nennt seinen Zustand: `sandboxed with bwrap` oder
`not sandboxed: <Grund>` (bwrap fehlt, bwrap kann keinen Sandkasten starten,
Sandkasten abgeschaltet); das JSON nennt ihn zusaetzlich maschinenlesbar als
Feld `sandboxed` (`true`/`false`/`null`). Vor jedem Lauf prueft der Pruefer
den Sandkasten mit einem Probeaufruf, damit ein vorhandenes, aber
unbrauchbares bwrap (etwa durch AppArmor oder Kernelschalter) nicht als
fehlgeschlagener Test fehlgedeutet wird. `--sandbox=require` kennt keinen
stillen Rueckfall: ohne nutzbaren Sandkasten wird das Kommando nicht
ausgefuehrt.

Fuer `[LEAN]` gilt eine Verschaerfung: Bauen und Elaborieren fuehren Code
aus, und `lake` wuerde fehlende Abhaengigkeiten ueber das Netz holen --
darum verhaelt sich `auto` dort wie `require`: ohne nutzbaren Sandkasten
bleibt die Behauptung `unpruefbar` statt ungesandboxt zu laufen. Nur ein
ausdrueckliches `--sandbox=off` laeuft ohne bwrap und sagt das im Urteil.
Details im Abschnitt "Formale Beweise".

Der Sandkasten ersetzt die Allowlist nicht: nur erlaubte Testkommandos werden
ueberhaupt ausgefuehrt, und alle uebrigen Beschraenkungen (Wegwerf-Checkout,
Argumentpruefung, reduzierte Umgebung, Ausgabegrenze) gelten unveraendert.
bwrap ist eine Abschottung gegen Fehler und Neugier des getesteten Codes,
keine Grenze gegen Kernel-Exploits und keine vollstaendige Isolationsgrenze
fuer feindlichen Code: Luecken im Kernel oder in bwrap selbst faengt er
nicht ab, und sichtbare Dateien bleiben lesbar. `bwrap` selbst wird per
`PATH` gefunden und gehoert wie `git` und `python3` zur vertrauenswuerdigen
Umgebung des Aufrufers; wer diesen `PATH` kontrolliert, kontrolliert den
Pruefer. `eval` nimmt dieselbe Option und reicht sie an jeden Testlauf des
Sets weiter.

## Halten von Turingmaschinen (`[HALT]` / `[SCORE]`)

Eine Meldung kann behaupten, dass eine Turingmaschine der
bbchallenge-Standardnotation haelt:

```
[HALT: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 47176870] [SCORE: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 4098]
```

Der Pruefer fuehrt die Maschine mit einem eigenen Simulator neu aus
(`bemyself/turing.py`, unabhaengig importierbar: `parse(machine)` und
`run(machine, max_steps) -> (halts, steps, score)`), im eigenen Prozess:
kein Repo, kein Subprozess, kein Netz, kein Sandkasten beteiligt. Gezaehlt
wird jede Transition, auch die in den Halt-Zustand `Z`; der Score ist die
Zahl der 1en auf dem Band beim Halt, inklusive des Schreibzugriffs der
letzten Transition. Start ist Zustand A auf leerem Band.

Die Notation kennt auch die undefinierte Transition `---` (etwa in der
Antihydra-Kanonform der bbchallenge-Wiki): Ihr Erreichen haelt die Maschine,
ohne selbst als Schritt zu zaehlen -- gezaehlt werden nur ausgefuehrte
Transitionen. Als Kommando druckt der Simulator eine Ergebniszeile:
`python3 -m bemyself.turing <maschine> <schritte>` gibt
`halts=<bool> steps=<n> score=<n>` aus.

Urteile: `bestaetigt` nur, wenn die Maschine exakt nach der behaupteten
Schrittzahl haelt (mit exakt dem behaupteten Score, wenn ein `[SCORE]`
daneben steht); `widerlegt`, wenn sie frueher haelt, innerhalb der
behaupteten Schritte gar nicht haelt oder mit anderem Score endet;
`unpruefbar`, wenn die Maschine nicht parst, die Schrittzahl keine schlichte
nichtnegative Ganzzahl ist oder das ausfuehrbare Limit uebersteigt.

Was das heisst: **Halten ist per Zeuge pruefbar** -- die exakte Schrittzahl
ist eine endliche, nachvollziehbare Beobachtung. **Nicht-Halten ist per
endlicher Suche nicht beweisbar**: "nach n Schritten kein Halt" widerlegt
die Behauptung "haelt exakt bei n" und wird nie als "haelt nie" ausgegeben;
eine Behauptung jenseits des Limits (etwa die Groessenordnung des
BB(6)-Rekordhalters, `2↑↑↑5`) bleibt ehrlich `unpruefbar`. Ein `[SCORE]`
ohne `[HALT]` derselben Maschine auf derselben Zeile ist keine Behauptung;
dasselbe gilt fuer einen `[HALT]`-Marker ohne Pfeil. Widersprechende
`[SCORE]`-Marker (zwei verschiedene Werte fuer dieselbe
Maschine) machen die Behauptung `unpruefbar`.

Das ausfuehrbare Limit ist die groesste Schrittzahl, die der Simulator fuer
eine Behauptung ausfuehren darf: Default 47.176.870, konfigurierbar mit
`--halt-limit N` (auch fuer `eval`); eine Behauptung darueber wird gar nicht
erst ausgefuehrt und bleibt `unpruefbar`. Der Speicher waechst linear mit
den ausgefuehrten Schritten (zwei Bytearrays, worst case wenige zehn
Megabyte), nicht mit der Bandposition. Das Limit begrenzt die einzelne
Behauptung, nicht den Report: eine Behauptung am Limit kostet wenige
Sekunden, und viele HALT-Zeilen in einem Report summieren sich. Die Testdaten stammen aus der
bbchallenge-Wiki und werden nachgerechnet: BB(5)-Champion (47.176.870
Schritte, 4098 Einsen; Coq-BB5, arXiv:2509.12337), der Halter von Marxen &
Buntrock 1989 (23.554.764/4097), Uhing 1984 (2.133.492/1915) und der
BB(6)-Rekord von mxdys 2025.

## Begrenzter Suchlauf (`[SEARCHED]`)

Ein SEARCHED-Marker behauptet genau eine endliche Beobachtung: Die Maschine
der bbchallenge-Standardnotation wurde neu ausgefuehrt und hielt innerhalb der
behaupteten Schrittzahl nicht:

```
[SEARCHED: 1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE -> 1000]
```

Der Pruefer fuehrt die Maschine mit demselben Simulator wie `[HALT]` erneut
aus (in-process, ohne Repo, Subprozess und Sandkasten). Urteile: `bestaetigt`,
wenn der Lauf nach genau den behaupteten Schritten ohne Halt endet;
`widerlegt`, wenn die Maschine frueher haelt (der Halt ist der Beleg);
`unpruefbar`, wenn die Maschine nicht parst, die Schrittzahl keine schlichte
nichtnegative Ganzzahl ist, bei 0 liegt (ein Nullschritt-Lauf beobachtet
nichts) oder das ausfuehrbare Limit uebersteigt.

Was ein `bestaetigt` hier ausdruecklich **nicht** bedeutet: Es ist kein
Beweis, dass die Maschine nie haelt. Eine endliche Suche kann Nicht-Halten
grundsaetzlich nicht beweisen. Der Urteilstext nennt diese Grenze ausdruecklich
("a bounded search of N steps found no halt; this does not prove that the
machine never halts"), README und SPEC dokumentieren sie, und ein Test fixiert
genau diese Formulierung: Der Typ ist fuer ehrliche Laufberichte gedacht, nie
als Nicht-Halte-Beweis lesbar. Ein `[SEARCHED]`-Claim ohne Halt im geprueften
Fenster ist also eine wahre Aussage ueber den Lauf -- nicht ueber die Maschine.

Das ausfuehrbare Limit ist die groesste Schrittzahl, die eine
SEARCHED-Behauptung ausfuehren darf: Default 10.000.000 (bewusst begrenzt,
nicht das HALT-Limit), konfigurierbar mit `--search-limit N` (auch fuer
`eval`). Eine Behauptung darueber wird gar nicht erst ausgefuehrt und bleibt
`unpruefbar`.

Ein `[CYCLE]`-Zertifikat (naechster Abschnitt) ist der andere Weg zu einem
Nicht-Halte-Beweis: Aus einem SEARCHED-Lauf wird nie abgeleitet, dass ein
solcher Zyklus vorliegt; ein SEARCHED-Lauf wird nie zu einem CYCLE-Zertifikat aufgewertet.

## Uebersetzte Zyklen (`[CYCLE]`)

Nicht-Halten ist ohne Zertifikat unpruefbar -- mit Zertifikat nachrechenbar.
Ein `[CYCLE]`-Marker behauptet einen *uebersetzten Zyklus* (translated cycler,
die Lin-Rekurrenz und damit die Klasse des bbchallenge-Deciders "Translated
Cyclers"): Die Konfiguration nach `t2` Schritten ist die Konfiguration nach
`t1` Schritten, um `d` Zellen verschoben -- gleicher Zustand, Kopf um exakt `d`
verschoben, Band gleich auf jeder Zelle, die die Maschine noch erreichen kann:

```
[CYCLE: 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC -> 6,16,2]
```

Der Pruefer fuehrt die Maschine mit demselben Simulator wie `[HALT]` neu aus
(in-process, ohne Repo, Subprozess und Sandkasten) und schliesst zuerst einen
Halt im Fenster bis `t2` aus: Eine Maschine, die innerhalb des Fensters haelt,
ist `widerlegt` (der Halt ist der Beleg). Danach vergleicht er Zustand,
Kopfdistanz (`head(t2) == head(t1) + d`) und das Band relativ zum Kopf. Der
Vergleich laeuft konservativ: Er umfasst genau die Zellen, die die Maschine
noch lesen kann -- Zellen hinter der groessten Kopf-Auslenkung des Fensters
werden nie wieder gelesen und bleiben aus dem Vergleich heraus (bei `d > 0`
ist das die linke Seite; die Maschine der bbchallenge-Wiki-Seite "Translated
cycler", Abbildung 44394115, laesst genau dort einen 1er als Gedaechtnis der
Vorgeschichte stehen). Ist der Vergleich nicht vollstaendig durchfuehrbar
(Band jenseits der Materialisierungsschranke `TAPE_LIMIT` von `2**24`
Zellen), bleibt die Behauptung `unpruefbar` -- ein `bestaetigt` gibt es nur
fuer einen wirklich durchgefuehrten Vergleich.

Der Beweisgrund im Urteilstext ist fixiert:

```
the configuration at step 16 equals the configuration at step 6 translated by 2
on every cell the machine can still reach (it never goes more than 2 cells left
of the head at step 6); therefore by determinism the machine never halts
```

Warum das ein vollstaendiger Beweis ist: Das Verhalten der Maschine haengt nur
von Zustand und Band ab; der Abschnitt von `t1` nach `t2` liest nur Zellen des
erreichbaren Fensters, das am zweiten Punkt identisch (um `d` verschoben)
vorliegt -- also wiederholt sich derselbe Abschnitt Schub um Schub, nur
verschoben. Ein Halt nach `t2` waere damit ein Halt im bereits geprueften
Fenster. Die Argumentation ist endlich nachvollziehbar: wenige Schritte
Simulation und ein exakter Bandvergleich.

Urteile: `bestaetigt` nur, wenn das Fenster bis `t2` haltfrei ist, Zustand und
Kopfdistanz exakt stimmen und das Band im erreichbaren Fenster exakt gleich
ist; `widerlegt`, wenn die Maschine im Fenster haelt, der Zustand abweicht,
der Kopf nicht um exakt `d` wandert oder eine Zelle im erreichbaren Fenster
abweicht (die erste abweichende relative Position steht im Urteil);
`unpruefbar`, wenn die Maschine nicht parst, `t1`/`t2` keine schlichten
nichtnegativen Ganzzahlen sind, `t2 <= t1` gilt, `d` nicht schlicht
ganzzahlig oder `0` ist, das ausfuehrbare Limit ueberstiegen wird oder ein
Band beziehungsweise das Vergleichsfenster selbst die
Materialisierungsschranke `TAPE_LIMIT` reisst.

Was das heisst -- und was nicht: Ein `bestaetigt` ist ein vollstaendiger
Nicht-Halte-Beweis **fuer diese Maschine mit diesem Zertifikat**. Der Typ
rechnet genau das vorgelegte Zertifikat nach und entscheidet nicht, ob eine
Maschine ueberhaupt einen uebersetzten Zyklus besitzt: kein allgemeiner Nicht-Halte-Pruefer,
er sucht nicht, er prueft. Und er ersetzt `[SEARCHED]` nicht: Ein SEARCHED-Lauf
beobachtet endlich und beweist nichts; ein SEARCHED-Lauf wird nie zu einem CYCLE-Zertifikat aufgewertet.

Das ausfuehrbare Limit ist die groesste Schrittzahl, die eine
CYCLE-Behauptung ausfuehren darf: Default 10.000.000 (bewusst begrenzt wie
das SEARCHED-Limit), konfigurierbar mit `--cycle-limit N` (auch fuer `eval`).
Eine Behauptung darueber wird gar nicht erst ausgefuehrt und bleibt
`unpruefbar`. Die Testdaten stammen aus der bbchallenge-Wiki (Seite
"Translated cycler", die dort abgebildete Maschine 44394115); das Zertifikat
`(6,16,2)` ist mit dem Simulator dieses Repos nachgerechnet.

## Parameterisierte Identitaeten (`[IDENT]`)

Ein IDENT-Marker behauptet eine Identitaet, die fuer **alle** Parameterwerte
gilt: fuer affine Funktionen `n(t)`, `a(t)`, `b(t)`, `c(t)` in der
ganzzahligen Variablen `t` soll

    4/n(t) = 1/a(t) + 1/b(t) + 1/c(t)

fuer jedes ganze `t >= <Schranke>` exakt gelten (Default `t >= 1`):

```
[IDENT: n=3t ; a=t, b=4t, c=12t]
[IDENT: n=3t+3 ; a=t+1, b=4t+4, c=12t+12 ; t >= 0]
```

Der Rumpf hat die Form `n=<affine> ; a=<affine>, b=<affine>, c=<affine>`
(optional `; t >= <nichtnegative Ganzzahl>`); affin heisst: ganzzahliger
Koeffizient von `t` (Default 1) plus ganzzahliger Summand, ohne
Leerzeichen im Ausdruck, ohne andere Buchstaben als `t`, ohne quadratische
oder gebrochene Terme. Die Probe sind zwei Bedingungen zugleich: die
rationale Identitaet und der Bereich, in dem sie gelten soll.

Der Pruefer rechnet exakt, ohne Gleitkomma: beide Seiten werden als
rationale Funktionen in `t` dargestellt, ihre Differenz gebildet, und der
Zaehler -- ein Polynom in `t` -- muss identisch null sein. Zusaetzlich
muessen die Bereichsbedingungen fuer jedes `t >= <Schranke>` beweisbar
gelten: `a`, `b`, `c` positiv und `n >= 2`. Ein Bereich, der das nicht
absichert (eine Nullstelle im Parameterbereich, eine fallende Gerade, eine
Schranke, die `n < 2` zulaesst), bleibt `unpruefbar` -- der Pruefer nimmt
keine Bedingung an, die er nicht zeigen kann.

Urteile: `bestaetigt` nur, wenn der Zaehler identisch null ist **und** alle
Bereichsbedingungen fuer alle `t >= <Schranke>` gelten; `widerlegt`, wenn
sich die beiden Seiten als rationale Funktionen unterscheiden (der Zaehler
der Differenz steht als Zeuge im Urteil, etwa `numerator=-9t^2` fuer
`b=4t+1` statt `b=4t`); `unpruefbar` bei falscher Rumpfform, nicht-affinen
Ausdruecken, einem anderen Parameter als `t`, zu grossen Zahlen oder nicht
sauber abgesichertem Bereich.

Was das heisst -- und was nicht: Ein `bestaetigt` ist eine Aussage ueber
unendlich viele Parameterwerte -- die Progression `n(t)` ist fuer alle
Parameter durch den expliziten Zeugen abgedeckt. Eine verifizierte
Identitaet deckt eine Progression fuer alle Parameter ab; sie ist kein
Beweis der Vermutung, solange nicht alle Restklassen abgedeckt sind. Der
Beweistext sagt das ausdruecklich ("holds as a rational identity in t for
every t >= ...", "this is not a proof of the conjecture") und nennt die
Progression. Die Bewertung fuer Erdos-Straus -- welche Progressionsklassen
heute parametrisch abgedeckt sind, aus Quellen belegt und mit dem Werkzeug
nachgerechnet -- steht unter [yesdocs/erdos-straus/](yesdocs/erdos-straus/).

Der Typ ist repo-frei (wie `[SEARCHED]` und `[CYCLE]`): `check --report`
laeuft ohne `--repo`. Die Pruefung ist eine Handvoll Polynommultiplikationen
kleinen Grades im selben Prozess -- kein Subprozess, kein Netz, nichts zu
sanden; kein neues Limit, kein CLI-Schalter.

```
$ python3 -m bemyself check --report ident-report.md
ident  CONFIRMED     4/n(t) = 1/a(t) + 1/b(t) + 1/c(t) holds as a rational identity in t for every t >= 1 with n = 3t, a = t, b = 4t, c = 12t; ...
    cmd: expand 1/(t) + 1/(4t) + 1/(12t) - 4/(3t) as one rational function in t
    out: numerator=0
```

## Schur-Faerbungen (`[COLORING]`)

Ein COLORING-Marker behauptet, dass eine explizite Faerbung der Zahlen
`1..N` mit `k` Farben keine monochromatische Loesung von `x + y = z`
enthaelt:

```
[COLORING: k=2 ; 1221]
[COLORING: k=4 ; 12131322444434141213233231214343444422313121]
```

Der Rumpf ist `k=<Farben> ; <Farbziffern>`: eine Ziffer pro Zahl, die
Ziffer an Position `i` ist die Farbe der Zahl `i`, die Laenge der
Ziffernfolge ist `N`. `k` ist eine einzelne Ziffer `1..9` (die Farben
selbst sind die Ziffern `1..9`); jede Ziffer der Folge muss eine Farbe
der Behauptung sein (`1..k`). Der Pruefer zaehlt ALLE Tripel `x <= y`
mit `x + y <= N` nach (`x == y` eingeschlossen) und prueft jedes auf
Monochromie -- im selben Prozess, ohne Repository, Subprozess oder Netz.

Urteile: `bestaetigt`, wenn kein Tripel monochromatisch ist; `widerlegt`,
wenn eines gefunden wird -- der ERSTE Verstoss in kanonischer Reihenfolge
(x aufsteigend, dann y aufsteigend) steht als Zeuge im Urteil, z. B.
`first violation: 1 + 1 = 2 with 1, 1, 2 all in color 1`; `unpruefbar`
bei falscher Rumpfform, einer Farbanzahl ausserhalb `1..9`, einer Ziffer
ausserhalb `1..k`, einer leeren Folge oder einem Zertifikat laenger als
das ausfuehrbare Limit.

Was das heisst -- und was nicht: Ein `bestaetigt` belegt die untere
Schranke `S(k) >= N` -- und sonst nichts. Es beweist keine Gleichheit
(`S(k) = N` braucht zusaetzlich, dass es keine gueltige k-Faerbung von
`1..N+1` gibt) und sagt nichts ueber die obere Schranke. Diese Asymmetrie
ist der Kern des Typs: eine Faerbung ist ein endliches, vollstaendig
nachpruefbares Zeugnis; die obere Seite hat kein kompaktes Zertifikat
(der Beweis `S(5) = 160` ist eine SAT-Refutation ueber Petabytes). Der
englische Urteilstext traegt die Grenze ausdruecklich: "this
certificates the lower bound ... only -- it does not prove equality and
says nothing about the upper bound".

Das ausfuehrbare Limit ist die groesste Laenge `N`, die ein COLORING
nachrechnen darf: Default 4096 (die Tripelaufzaehlung ist quadratisch,
etwa `N^2/4` Paare), konfigurierbar mit `--coloring-limit N` (auch fuer
`eval`); eine laengere Behauptung wird nicht ausgefuehrt und bleibt
`unpruefbar`. Zu beachten: Der Report-Leser ignoriert Zeilen ueber 8192
Zeichen vollstaendig -- ein Zertifikat dieser Laenge erscheint gar nicht
erst als Behauptung, ein Limit oberhalb dieser Grenze kann daher nie
greifen. Der Typ ist repo-frei (wie `[SEARCHED]`, `[CYCLE]`, `[IDENT]`):
`check --report` laeuft ohne `--repo`.

Die Landkarte der belegten Schranken -- pro `k` die untere Schranke mit
Zertifikat und Pruefbefehl, der obere Rand mit Quelle, und was dieses
Werkzeug davon kann und nicht kann -- steht unter
[yesdocs/schur/](yesdocs/schur/); die Zertifikate dort sind
`[COLORING]`-Marker, die Dokumentation verifiziert sich selbst
(`check --report yesdocs/schur/README.md --strict`).

## Rechenzertifikate (`[COMPUTE]`)

Jede endliche Rechnung wird pruefbar, ohne neuen Code pro Problem: Ein
COMPUTE-Marker behauptet, dass ein Kommando auf stdout genau die Bytes
ausgibt, deren SHA-256 behauptet wird:

```
[COMPUTE: python3 -m bemyself.turing 1RB1RZ_0LA0LA 3 -> fcc2762419d8f4f3a1b1129170e13837c21722505ad8a6f5b40d9164cb7c92df]
```

Der Pruefer checkt den Commit der Meldung in einen Wegwerf-Checkout aus
(`git clone --no-hardlinks` + `git checkout`, wie ein Testlauf) und fuehrt das
Kommando dort im Sandkasten aus (dieselbe bwrap-Abschottung wie bei
Testkommandos: Wurzel read-only, nur der Checkout beschreibbar, eigener
Netz-, PID- und UTS-Namensraum, `--die-with-parent`). stdout wird waehrend
des Laufs gehasht (Streaming: die Ausgabegroesse kostet weder Gedaechtnis
noch Platte); verglichen wird der SHA-256.

Urteile: `bestaetigt` nur, wenn der Lauf sauber endete (Exit-Code 0) und der
Hash des stdout exakt dem behaupteten entspricht -- ein fehlgeschlagenes
Kommando wird nie zertifiziert, egal wie seine Bytes aussehen (der Exit-Code
ist nicht das Hash-Kriterium, aber das Abschluss-Gate: kein Zertifikat ohne
abgeschlossenen Lauf); `widerlegt`, wenn ein sauber abgeschlossener Lauf einen
anderen Hash hat. `unpruefbar` bleibt: ein Kommando ausserhalb der
COMPUTE-Allowlist, ein fehlender oder nicht aufloesbarer Commit, ein nicht
gefundenes Programm (Vorabpruefung vor dem Lauf), abgelehnte Argumente
(dieselben Escape-Regeln wie bei Tests), ein nicht nutzbarer Sandkasten bei
`--sandbox=require`, ein Timeout nach 300 s, mehr als 64 MiB stdout (mehr wird
abgelehnt, nie gekuerzt in ein Urteil) oder ein Exit-Status ungleich 0.

Die COMPUTE-Allowlist ist bewusst minimal: standardmaessig nur die
Repo-eigenen Module als literale Eintraege -- `python3 -m bemyself.turing`
(der Simulator) und `python3 -m bemyself.experiments.erdos_straus` (das
Erdős-Straus-Experiment, s. u.). Kein Wildcard: ein kuenftiges Modul des
Experiment-Pakets wird nicht implizit geoeffnet. Weitere Rechnungen
werden explizit geoeffnet: `--allow "praefix"` (wiederholbar) erweitert die
Allowlist fuer Testlaeufe und COMPUTE gemeinsam; ein nicht erlaubtes Kommando
wird nie ausgefuehrt. Fuer COMPUTE laeuft der Abgleich auf den argv-Tokens, die
wirklich ausgefuehrt werden -- nicht auf normalisiertem Text, damit ein
allowlist-aehnlich aussehender String nie als etwas anderes laeuft. Das
Netzwerk ist im Sandkasten aus (bestehende `--unshare-net`-Semantik): ein
Netzversuch scheitert. Die Default-Eintraege passen zum bemyself-Repo: in einem
anderen Repo laufen sie nur, wenn der gepinnte Commit das Paket mitbringt
(sonst `unpruefbar`, nicht `bestaetigt`).

Ein COMPUTE braucht das Repo (den gepinnten Commit): ohne `--repo` bricht
`check --report` mit Exit 2 und einer Meldung ab, die den Typ nennt. Der
Commit kommt wie bei Testlaeufen aus dem genau einen hash-foermigen
`[COMMIT]`-Marker der Meldung (Platzhalter wie `<hash>` zaehlen nicht, sie
stehen nur in Vorlagen); mehrere verschiedene Commits binden nichts, und der
Claim bleibt `unpruefbar`.

```
$ python3 -m bemyself check --report compute-report.md --repo <repo>
compute        CONFIRMED     sha256 of stdout matches the claimed digest (exit 0, 27 bytes) (sandboxed with bwrap)
    cmd: git clone --no-hardlinks <repo> <checkout> && git checkout <hash> && bwrap ... -- python3 -m bemyself.turing 1RB1RZ_0LA0LA 3
    out: sha256=fcc2762419d8f4f3a1b1129170e13837c21722505ad8a6f5b40d9164cb7c92df bytes=27 exit=0
```

**Grenzen:** Der Hash belegt, dass genau dieses Kommando auf genau diesem
Commit diese Bytes auf stdout ausgibt -- und nur, wenn der Lauf mit Exit 0
endete. Er belegt nicht, dass die Rechnung "stimmt" -- die Bedeutung der Bytes
bleibt die Aussage der Meldung. Der Checkout bringt seinen eigenen Code mit
(das ist der Zweck: der Code des gepinnten Commits rechnet); wer den Commit
kontrolliert, kontrolliert die Ausgabe. Der Sandkasten begrenzt wie bei
Testlaeufen Schreiben, IP-Netz und Prozesssicht, nicht Lesezugriffe. Die
Limits (Zeit, Ausgabe) begrenzen einen Lauf, nicht die Meldung: eine Meldung
kann viele COMPUTE-Behauptungen tragen, jede mit eigenem Lauf.

## Formale Beweise (`[LEAN]`)

Der staerkste Zeuge, den das Werkzeug kennt: `[LEAN: <pfad.lean> -> <satz>]`
behauptet, dass im gepinnten Commit die Datei `<pfad.lean>` existiert und die
Deklaration `<satz>` dort ohne `sorry`/`admit` bewiesen ist:

```
[LEAN: lean/cycle-bridge/CycleBridge/Cycle.lean -> CycleBridge.cycle_never_halts]
```

Die Bindung an den Commit ist dieselbe wie bei `[COMPUTE]`: genau ein
hash-foermiger `[COMMIT]`-Marker der Meldung pinnt den Commit (Platzhalter wie
`<hash>` zaehlen nicht); mehrere verschiedene Commits binden nichts, und die
Behauptung bleibt `unpruefbar`. Als `<satz>` gilt der volle Lean-Name der
Deklaration, also inklusive Namensraum (`CycleBridge.cycle_never_halts`).

Der Pruefer arbeitet in einem Wegwerf-Checkout des Commits in drei Stufen,
alle im Sandkasten:

1. **Abhaengigkeiten bauen** (nur Lake-Projekte). Die eigenen
   Build-Artefakte des Projekts werden verworfen (ein symlinktes
   Build-Verzeichnis wird entfernt, nicht geleert), dann baut
   `lake build <modul>` den Abhaengigkeitsgraph. Diese Stufe fuehrt
   Repo-Code aus; **ihr Artefakt ist nie die Evidenz** -- die lakefile
   bestimmt ueber `srcDir`/Ziele selbst, welche Quelle ein Modul ist.
2. **Die gepruefte Datei selbst kompilieren.** Der Pruefer kopiert die
   Datei aus dem Commit in sein eigenes Verzeichnis im Checkout und
   kompiliert **die Kopie** (`lean -o`); das so entstandene Artefakt ist die
   Evidenz. Vorher prueft er, dass die Datei der Build-Stufe unveraendert
   entstammt (`git status` sauber -- ein importiertes Modul koennte sie
   sonst per `#eval` umschreiben), und danach, dass das Artefakt frisch
   geschrieben wurde. Ein Kompilierfehler der Datei widerlegt die
   Behauptung (erste Fehlerzeile im Urteil).
3. **Kernel-Recheck.** `leanchecker <modul>` prueft die Deklarationen des
   Artefakts mit dem Lean-Kernel nach. Recheck und Abfrage rufen die
   Toolchain **direkt** auf, nie ueber `lake`: die lakefile ist
   Repo-Code und wuerde denselben Ausgabekanal teilen. Der Suchpfad beginnt
   mit dem Libverzeichnis der Toolchain, damit der gepruefte Baum die
   Imports des Abfrageprogramms nicht verschatten kann.
4. **Axiom-Abfrage.** Das eigene Abfrageprogramm
   (`bemyself/tools/lean_axioms.lean`) laedt das Artefakt als **Daten**
   (`importModules`) und druckt die Axiomliste der Deklaration; eine
   AXIOMS-Zeile gilt nur zusammen mit Exit 0, und die Deklaration muss im
   geprueften Modul selbst definiert sein (kommt sie aus einem importierten
   Modul, ist die Behauptung widerlegt). In diesem
   Prozess laeuft kein Repo-Code -- keine Taktik, kein Makro, kein
   Initializer -- darum kann das gepruefte Projekt die Antwort weder
   faelschen noch unterdruecken: einziger Schreiber ist das Abfrageprogramm,
   und die Axiomdaten stammen aus dem Artefakt, das der Kernel gerade
   nachgeprueft hat.

```
$ python3 -m bemyself check --report lean-report.md --repo <repo>
lean           CONFIRMED     'CycleBridge.cycle_never_halts' is proved in lean/cycle-bridge/CycleBridge/Cycle.lean at 5885fcfad823: the artifact built from that commit passed Lean's kernel re-check (leanchecker, Lean 4.33.1) and the checker's own query (no repository code in the query process) read its axiom list from the artifact: 'CycleBridge.cycle_never_halts' depends on axioms: [propext, Quot.sound] (sandboxed with bwrap)
```

Urteile: `bestaetigt` nur, wenn die Abfrage mit Exit 0 genau fuer diese
Deklaration antwortet und die Liste kein `sorryAx` nennt; die Axiomzeile
steht vollstaendig im Urteil (logische Grundaxiome wie `propext`,
`Quot.sound` oder `Classical.choice` inklusive -- `bestaetigt` heisst nicht
"axiomfrei"). `widerlegt` bei `sorryAx`, bei `lcProof` (der Kernel hat den
Rumpf nicht geprueft, etwa bei `unsafe`), bei einer Deklaration, die selbst
ein Axiom ist (ihr Name steht in der eigenen Axiomliste -- da ist kein
Beweis), bei einer Deklaration, die aus einem importierten Modul stammt und
nicht in der geprueften Datei definiert ist, bei fehlender Deklaration im
Artefakt, bei fehlender Datei im
Commit und bei einem Kompilierfehler der Datei. `unpruefbar` bleibt die
Behauptung ohne `lean`/`lake`/`leanchecker`
im `PATH`, ohne funktionierenden Sandkasten (auch bei `--sandbox=auto`),
ohne Commit-Bindung, bei ungueltigem Pfad oder Satznamen, bei Timeout
(600 s je Stufe), bei einem Artefakt, das den Kernel-Recheck nicht besteht,
bei unlesbarer Abfrageantwort und immer dann, wenn eine Abhaengigkeit des
Projekts im Checkout fehlt -- der Urteilstext nennt dann Modul und erste
Fehlerzeile; eine fehlende Abhaengigkeit ist nie ein Beweis gegen den Satz.

Prueftiefe -- was ein `bestaetigt` zusichert: Die Deklarationen des
geprueften Moduls wurden von Lean selbst kompiliert, das Artefakt wurde mit
`leanchecker` kernel-nachgeprueft, und die Axiomliste ist aus diesem
Artefakt gelesen (nicht aus der Ausgabe des Builds). `leanchecker`
akzeptiert `sorryAx`-Beweise -- die sorry-Erkennung kommt darum nicht von
ihm, sondern aus der Axiomliste der eigenen Abfrage; beide zusammen tragen
das Urteil. Grenze der Aussage: die Abhaengigkeiten des Moduls stammen
nicht aus dem Commit -- ihre Artefakte kommen aus dem read-only
eingebundenen Arbeitsbaum-Cache (im Urteil benannt) oder liegen im Repo;
der Kernel-Recheck deckt die Deklarationen des geprueften Moduls, nicht die
seiner Abhaengigkeiten. Ebenso stammt das Artefakt aus der Build-Stufe, die
Repo-Code ausfuehrt (siehe oben): sichtbare Codeausfuehrung wird verweigert,
aber ein Repository, das die Herkunft des Artefakts verdeckt manipuliert,
bleibt ausserhalb der Zusicherung. Das Urteil belegt damit, dass die
Deklaration vom
Lean-Kernel akzeptiert ist und an genau den genannten Axiomen haengt --
nicht die Wahrheit der Axiome, nicht die Bedeutung des Satzes und nicht die
Herkunft der Abhaengigkeits-Artefakte.

Was eine feindselige Datei nicht kann: weil Evidenz nur aus dem Artefakt
und der eigenen Abfrage kommt, kann Build-Ausgabe ein Urteil nur
herabstufen (auf `unpruefbar`), niemals auf `bestaetigt` heben. Der
Evidenzprozess selbst fuehrt keinen Repo-Code aus -- weder Taktiken noch
Makros noch Initializer; die Live-Tests in `tests/test_lean.py` pinnen
genau diese Faelle. Das Artefakt entsteht aus einer Kopie der geprueften
Datei, nicht aus dem lakefile-getriebenen Projektbuild: eine lakefile, die
`srcDir` auf eine andere Quelle umbiegt, oder ein importiertes Modul, das
die gepruefte Datei waehrend des Builds umschreibt, kann die Evidenz nicht
mehr auf eine fremde Quelle lenken (die Integritaetspruefung verweigert
dann). Die Build-Stufe fuer Abhaengigkeiten fuehrt trotzdem Repo-Code aus,
und das laesst sich nicht vermeiden. Darum gilt eine dokumentierte Politik:
die gepruefte Datei und eine `lakefile.lean`, die zur Elaborationszeit
sichtbar Code ausfuehren (`#eval`, `#exec`, `run_cmd`, `run_elab`), werden
nicht geprueft und bleiben `unpruefbar` -- ihre Build-Kette ist nicht zu
verbuergen; importierte Module werden von dieser Politik **nicht** erfasst
(und koennen ein Urteil nur herabstufen). Die Politik sucht Textstellen:
auch ein `#eval` in einem Kommentar oder String verweigert die Pruefung
(die sichere Richtung). Verdeckte Formen der
Codeausfuehrung (eigene Elaboratoren, `native_decide`) erkennt sie
ebenfalls nicht; wer sie einsetzt, kann die Abhaengigkeits-Artefakte
manipulieren und liegt ausserhalb dessen, was dieses Werkzeug zusichert.

Toolchain und Abhaengigkeiten: `lean`, `lake` (fuer Lake-Projekte) und
`leanchecker` muessen im `PATH` liegen (eine elan-Installation erfuellt
das); das Werkzeug selbst braucht sie nicht. Fehlt eine
`lean-toolchain`-Datei in Reichweite, pinnt der Pruefer die einzige
installierte Toolchain als `ELAN_TOOLCHAIN` -- der elan-Shim fragt dann
nicht im netzlosen Sandkasten nach der Standardversion. Ein frischer
Checkout bringt nur die getrackten Dateien mit -- Abhaengigkeiten wie
Mathlib sind nicht Teil des Commits. Hat das gepruefte Repository neben dem
Lake-Projekt einen `.lake`-Cache im Arbeitsbaum und der Checkout keinen,
wird dessen `packages`-Verzeichnis read-only in denselben Pfad gebunden
(der Checkout baut in sein eigenes, beschreibbares `.lake`); das Urteil
nennt den Pfad im Kommando. Fehlt der Cache, traegt er keine kompilierten
Artefakte, oder laesst sich die Abhaengigkeit nicht aufloesen, bleibt die
Behauptung `unpruefbar` (nie `widerlegt`): das Netz ist im Sandkasten aus,
und `lake` wuerde fehlende Abhaengigkeiten sonst per `git clone` nachladen.

Isolation: Bauen und Elaborieren fuehren Code aus (Taktiken, Metaprogramme,
`#eval`, Initializer); darum verlangt der Typ den Sandkasten auch im Modus
`auto` -- anders als bei Testkommandos gibt es keinen stillen ungesandboxten
Rueckfall. Der Sandkasten bindet die Wurzel read-only (so bleibt die
Toolchain unter `~/.elan` erreichbar), gibt dem Lauf eigenen Netz-, PID- und
UTS-Namensraum und nur den Wegwerf-Checkout beschreibbar.

**Grenzen:** `bestaetigt` heisst: die Datei steht so im gepinnten Commit,
ihr Modul baute, das Artefakt bestand den Kernel-Recheck, und die
Deklaration haengt an genau den Axiomen im Urteil. Es heisst nicht: die
Aussage des Satzes ist wahr, die Abhaengigkeits-Artefakte sind
vertrauenswuerdig, oder die Behauptung waere unabhaengig von Lean
nachgeprueft. Als `<satz>` zulaessig sind volle Lean-Namen mit
Unicode-Buchstaben, Ziffern, Unterstrich, Punkten und abschliessendem
`!`/`?`; alles andere bleibt `unpruefbar`.

## Merges (`[MERGE]`)

`[MERGE: <branch>]` behauptet, dass der Commit der Meldung der Merge des
genannten Branches ist. Der Commit kommt wie bei `[COMPUTE]` aus dem genau
einen hash-foermigen `[COMMIT]`-Marker der Meldung (Platzhalter wie `<hash>`
zaehlen nicht; mehrere verschiedene Commits binden nichts, dann bleibt die
Behauptung `unpruefbar`). Geprueft wird die Struktur des Commits, lokal und
ohne Netz:

- Der Commit existiert und hat genau zwei Parents; null, ein oder mehr als
  zwei Parents heissen: kein Merge-Commit, `widerlegt`.
- Einer der Parents ist der Tip des genannten Branches (zuerst
  `refs/heads/<branch>`, dann der Origin-Tracking-Ref
  `refs/remotes/origin/<branch>`).
- Der andere Parent liegt auf der Zielbranch oder ist ihr Tip. Zielbranch ist
  die Default-Branch des Remotes (`origin/HEAD`), sonst eine lokale `main`
  oder `master`, sonst die aktuelle Branch; laesst sich keine bestimmen,
  bleibt die Behauptung `unpruefbar`.

Widerspricht der Commit der Behauptung, wird sie `widerlegt` und das Urteil
nennt die Parents, die es wirklich gibt (kurze Hashes) sowie den Tip des
genannten Branches. `widerlegt` ist auch ein Commit, der selbst auf dem
genannten Branch liegt (eine Branch wird nicht in einen Commit gemergt, den
sie schon enthaelt -- so faellt der Zielbranch auf, wenn er als gemergter
Branch genannt wird) und ein Commit, dessen kein Parent zur Geschichte des
genannten Branches gehoert. `unpruefbar` bleiben ausserdem: ein Wert ohne
Branchnamen (`[MERGE: no]`, `pending-PR`, `blocked-PR` sind Statuswerte des
Yesloop-DONE-Payloads, keine Branches; auch `HEAD` ist eine Revision, keine
Branch), ein Branch, der weder lokal noch auf `origin` aufloest (ein nach dem
Merge geloeschter Branch wird nicht erraten), ein Branch, dessen Tip nach dem
Merge weiterlief (kein Objekt haelt fest, wo eine Branch beim Merge zeigte --
das Urteil nennt den Parent, der in der Branch-Geschichte liegt), ein
fehlender Commit und ein nicht aufloesbarer Commit-Hash. Ein
`[MERGE]`-Claim verlangt kein `--repo`: eine Meldung, die nur `[MERGE: no]`
traegt, laeuft weiter ohne Repository (und bleibt `unpruefbar`); mit `--repo`
wird die Behauptung geprueft.

**Grenzen:** Der Check belegt die Merge-Struktur, nicht die Absicht. Er liest
den Tip des Branches zum Pruefzeitpunkt; ein Branch, der nach dem Merge
weiterlief, macht die Behauptung `unpruefbar` statt `widerlegt` (das Urteil
nennt den Parent, der in seiner Geschichte liegt). Ein geloeschter Branch
macht sie `unpruefbar` -- solange kein Origin-Tracking-Ref desselben Namens
mehr aufloest; ist die Branch nur auf dem Remote geloescht und der
Tracking-Ref noch nicht gepruned, prueft der Check gegen diesen. Geprueft
wird der andere Parent gegen die Zielbranch, nicht der gemeldete Commit
selbst: ein Merge, der die Zielbranch nie erreicht hat (etwa ein Merge in
einer weggeworfenen Branch), wird `bestaetigt`, wenn der andere Parent auf
der Zielbranch liegt -- die Behauptung nennt dann eine wahre Merge-Struktur,
aber keinen Merge auf der Zielbranch.

```
$ python3 -m bemyself check --report merge-report.md --repo <repo>
merge          CONFIRMED     79aaa8161516 is a merge of 'topic': parent 1487f8796175 is its tip and parent 7954a3c59f69 lies on main
```

## Artefakte (`[ARTIFACT]`) und Deploys (`[DEPLOY]`)

`[ARTIFACT: <pfad> -> <sha256>]` behauptet, dass die Datei existiert und ihr
Inhalt genau den behaupteten SHA-256 hat -- die ehrliche Form von "das
Deploy-Artefakt ist da":

```
[ARTIFACT: dist/app.bin -> 106675dc1490d5cdd6d1f0410731316ce93fc964c6cf6726e2b0d53e19688feb]
```

Der Pfad kommt aus einer Meldung, also aus untrusted Input: er wird unter der
Artefakt-Wurzel aufgeloest und nie ausserhalb gelesen. Die Wurzel ist
standardmaessig das Repository (`--repo`), `--artifact-root <dir>` setzt eine
andere; ohne Wurzel (kein `--repo`, kein `--artifact-root`) bleibt die
Behauptung `unpruefbar`. Der Pfad wird mit `realpath` aufgeloest und nur
akzeptiert, wenn er in der Wurzel bleibt: `..`-Bestandteile werden abgelehnt
(auch wenn sie rechnerisch wieder hineinfuehren), und ein Symlink innerhalb
der Wurzel, der nach aussen zeigt, bleibt `unpruefbar`. Ein Symlink, dessen
Ziel in der Wurzel bleibt, wird verfolgt. Die Datei wird genau einmal
geoeffnet (`O_NONBLOCK`, damit eine Named Pipe den Pruefer nicht blockiert),
per `fstat` als regulaere Datei bestaetigt und durch diesen Deskriptor
gehasht; der SHA-256 streamt in Bloecken, das Gedaechtnis bleibt konstant. Ein
Groessenlimit von 256 MiB begrenzt die Zeit pro Behauptung: eine groessere
Datei bleibt `unpruefbar` (nie gekuerzt in ein Urteil), und eine Datei, die
waehrend des Lesens ueber das Limit waechst, ebenfalls.

Urteile: `bestaetigt` nur, wenn die Datei vollstaendig gelesen wurde und ihr
Digest exakt dem behaupteten entspricht (Gross-/Kleinschreibung des Digests
ist egal). `widerlegt` bei fehlender Datei, bei einem Pfad, der keine
regulaere Datei ist (Verzeichnis, Named Pipe, Geraet), und bei abweichendem
Digest -- Abwesenheit und Abweichung sind Befunde, kein Unwissen; das Urteil
nennt Pfad, tatsaechlichen Digest und Groesse. `unpruefbar` bei fehlender oder
nicht existierender Wurzel, bei einem Pfad ausserhalb der Wurzel (auch ueber
einen Symlink), bei einem Pfad, den der Pruefer nicht oeffnen darf
(fehlende Rechte), bei einem leeren Pfad, bei einem Digest, der keine 64
Hex-Ziffern sind, und bei einer Datei ueber dem Limit.

**Grenzen:** Die Wurzel ist der Vertrauensbereich des Aufrufers. Bleibt die
Konfinierung auch gewahrt -- gelesen wird nur, was unter der Wurzel liegt --
so ist der Inhalt der Wurzel nicht gegen einen Schreiber geschuetzt, der
Zugriff darin hat: eine Datei kann zwischen der Aufloesung des Pfades und dem
Oeffnen ausgetauscht werden (derselbe Vertrauensbereich, keine neue
Faehigkeit), und ein Hardlink in der Wurzel ist von einer eigenen Datei nicht
zu unterscheiden (gleicher Inode).

`[DEPLOY: ...]` bleibt bewusst ohne Pruefer und damit dauerhaft `unpruefbar`:
"Deploy" hat keinen generischen, nachrechenbaren Sinn -- je nach Ziel ist
"deployed" ein neuer Prozess, ein DNS-Eintrag, ein Artefakt in einer fremden
Registry oder eine Nachricht an eine dritte Partei, und eine Pruefung, die
davon nichts anfasst, waere eine Scheinpruefung. Wer "Deploy erfolgt"
behaupten will, behauptet stattdessen, was wirklich pruefbar ist: das
Artefakt und seinen Digest (`[ARTIFACT: ... -> <sha256>]`) -- das ist der
ehrliche Ersatz.

## Experimente (`bemyself/experiments/`)

Ein Experiment ist ein Modul unter `bemyself/experiments/`, das eine endliche
Rechnung deterministisch auf stdout ausgibt; ein `[COMPUTE]`-Merkmal macht das
Ergebnis ueber Kommando, gepinnten Commit und SHA-256 des stdout nachpruefbar
-- ohne neuen Behauptungstyp.

### Erdős–Straus bis N (`python3 -m bemyself.experiments.erdos_straus <N>`)

Die Vermutung von Erdős–Straus: Fuer jedes `n >= 2` gibt es positive ganze
Zahlen `a, b, c` mit `4/n = 1/a + 1/b + 1/c`. Die Vermutung ist offen; das
Experiment beweist sie nicht. Es rechnet ein endliches Fenster durch: fuer
jedes `n` von 2 bis `N` schreibt es den Zeugen in einer Zeile `n a b c`
(aufsteigendes `n`), die Schlusszeile ist `ok <N> <count>` mit
`count = N - 1` Zeugen.

Kanonisch ist das lexikografisch kleinste Tripel `(a, b, c)` in der
natuerlichen Ordnung der ganzen Zahlen. Die Suche ist pro `n` vollstaendig:
`a` durchlaeuft `floor(n/4) + 1 .. floor(3n/4)` -- jedes Tripel, sortiert,
hat seine kleinste Komponente in diesem Fenster, denn `1/a < 4/n` (der Rest
ist positiv) und `4/n <= 3/a` (die Komponente ist die kleinste) -- und fuer
festes `a` entscheidet das Divisor-Kriterium vollstaendig, ob sich der Rest
als `1/b + 1/c` schreiben laesst (`(pb - q)(pc - q) = q^2` nach Kuerzen von
`(4a - n)/(n a)`; das kleinste passende Divisor-`X` mit
`X == -q (mod p)` liefert das kleinste `b`). Eine Luecke waere damit kein
Suchabbruch, sondern ein echter Gegenbeispiel-Kandidat fuer dieses `n`;
Zeugen werden nie erfunden.

Determinismus: keine Zufallsquellen, kein Netz, kein stdin; zwei Laeufe
liefern byte-identisches stdout.

**Was die Aussage IST und was nicht:** "fuer jedes `n <= N` steht ein
expliziter Zeuge in der gepinnten, deterministischen Ausgabe" ist endlich und
vollstaendig nachrechenbar; der `[COMPUTE]`-Hash bindet genau diese Bytes an
Kommando und Commit. Das heisst: endlich verifiziert bis `N`, kein Beweis.
Es ist kein Beweis der Vermutung fuer alle `n` und keiner fuer `n > N`; der
Hash belegt die Bytes, nicht "die Mathematik" -- die Bedeutung der Bytes
bleibt die Aussage dieser Doku. Does not prove the conjecture.

Luecken-Semantik: findet die Suche fuer ein `n` keinen Zeugen, erscheint statt
der Zeugenzeile `gap <n>` an genau der Stelle dieses `n` (kein stilles
Ueberspringen), die Schlusszeile ist `gaps <N> <found> <missing>`, der
Exit-Code ist 1. Exit 0 gibt es nur bei vollstaendigem Lauf, Exit 2 bei
Nutzungsfehlern (fehlendes, nicht-schlichtes, `< 2` oder auf dieser Maschine
nicht rechenbares Limit).

Laufzeit (diese Maschine, CPython, ein Prozess, stdlib): `N = 100.000`
schreibt 3,9 MB in etwa 1 s, `N = 1.000.000` schreibt 46,9 MB in etwa 14 s;
der CHECKER-Gegenlauf (frischer Checkout + bwrap + Lauf) braucht dafuer
insgesamt etwa 15 s. Die Laufzeit ist empirisch, keine Schranke. Der
Speicherbedarf waechst linear mit `N`: die Merktabelle der kleinsten
Primfaktoren hat `2N` Eintraege (gemessen: `N = 1.000.000` etwa 90 MB
Peak-RSS); ein weit groesseres `N` kann am Speicher scheitern -- der Lauf
endet dann mit einem Fehl-Exit (Exit 2 aus dem Modul oder vom Kernel
beendet), nie mit einer erfundenen Aussage.

Artefakt dieses Branches: `python3 -m bemyself.experiments.erdos_straus
1000000` -> sha256
`e5b68dd1818d89f2c66d0e7b5a68bf906dbe7adc77c64dba015bf27058a4f89d`.
Das Paar `[COMMIT: <finaler Branch-HEAD>]` + `[COMPUTE: ... -> <sha256>]`
steht im Artefakt-Report des Zweigs (ungetrackt unter `.yesmem/tmp/`, wie bei
den bisherigen Artefakten); nachrechenbar mit
`python3 -m bemyself check --report <artefakt> --repo . --sandbox require
--strict`.

## Neuen Behauptungstyp hinzufuegen

Ein optionaler Behauptungstyp ist ein Modul in `bemyself/claimtypes/` plus
ein Eintrag in `CLAIM_TYPES`; Parser (`bemyself/report.py`) und CLI
(`bemyself/cli.py`) bleiben unveraendert. Durchgerechnetes Mini-Beispiel
`[EVEN: <zahl>]`:

```python
# bemyself/claimtypes/even.py
import re
from bemyself.model import ClaimType, Result, Verdict

def parse(match, raw):          # Felder aus dem Marker
    return {"value": match.group(1)}

def check(claim, ctx):          # Urteil gegen die Welt
    even = int(claim.fields["value"]) % 2 == 0
    return Result(Verdict.CONFIRMED if even else Verdict.REFUTED,
                  reason="even" if even else "odd")

EVEN = ClaimType(kind="even",
                 pattern=re.compile(r"\[EVEN:[ \t]*(\d+)[ \t]*\]"),
                 parse=parse, check=check)
```

```python
# bemyself/claimtypes/__init__.py
from bemyself.claimtypes import even, halt
CLAIM_TYPES = (halt.HALT, even.EVEN)
```

Danach findet `parse_report` den Marker `[EVEN: 42]` und `run_claim` fuehrt
`check` aus. `tests/test_claimtypes.py` fuehrt diesen Weg als Test durch
(Eintrag zur Laufzeit registriert, beide Bestandsmodule unveraendert).

Ein Typ deklariert am Eintrag ausserdem, ob sein `check` ein Git-Repository
liest: `ClaimType(..., needs_repo=True)`. Ohne die Angabe (Default `False`)
laeuft `check --report` auch ohne `--repo`; mit `needs_repo=True` verlangt ein
Report, der eine solche Behauptung enthaelt, `--repo` (usage-Fehler, Exit 2,
mit dem Typ in der Meldung). Den Bedarf liest der Pruefer aus der Registry
(`bemyself.checks.kind_needs_repo`), nicht aus einer Typ-Liste im CLI-Code.

Und ob die Behauptung an den Commit der Meldung bindet:
`ClaimType(..., binds_commit=True)`. Dann setzt der Parser das Feld `commit`
der Behauptung auf den genau einen `[COMMIT]`-Hash der Meldung (mehrere
verschiedene Hashes binden nichts); ohne die Angabe bleibt `commit` `None`.

Durchgerechnetes COMPUTE-Mini-Beispiel (der Typ, an dem beides zusammenkommt):

```python
# bemyself/claimtypes/compute.py (Auszug)
COMPUTE = ClaimType(kind="compute",
                    pattern=re.compile(r"\[COMPUTE:(?P<body>[^\]\[]*?)\]"),
                    parse=parse, check=check,
                    needs_repo=True,      # gepinnter Commit-Checkout
                    binds_commit=True)    # bindet an den [COMMIT]-Marker
```

Meldung mit genau einem Commit-Marker und einem Rechenzertifikat (der Hash
ist sha256 von `halts=True steps=3 score=1\n`):

```
**send_to payload:** `[DONE] [COMMIT: <hash>]`
[COMPUTE: python3 -m bemyself.turing 1RB1RZ_0LA0LA 3 -> fcc2762419d8f4f3a1b1129170e13837c21722505ad8a6f5b40d9164cb7c92df]
```

```
$ python3 -m bemyself check --report compute-report.md --repo <repo>
compute        CONFIRMED     sha256 of stdout matches the claimed digest (exit 0, 27 bytes) (sandboxed with bwrap)
```

Fehlt `--repo`, bricht der Aufruf mit Exit 2 ab und nennt `compute`; ein
Kommando ausserhalb der Allowlist bleibt `unpruefbar` (der Standard-Eintrag
ist `python3 -m bemyself.turing`, `--allow` erweitert); ein falscher Hash ist
`widerlegt`.

Durchgerechnetes IDENT-Mini-Beispiel (ein weiterer Typ ohne Repo-Bedarf,
wie `[HALT]`, `[SEARCHED]` und `[CYCLE]`):

```python
# bemyself/claimtypes/ident.py (Auszug)
IDENT = ClaimType(kind="ident",
                  pattern=re.compile(r"\[IDENT:(?P<body>[^\]\[]*?)\]"),
                  parse=parse, check=check)
```

Die Probe der Identitaet `[IDENT: n=3t ; a=t, b=4t, c=12t]` laeuft ohne
`--repo` und endet `bestaetigt`; ein verfaelschter Koeffizient ist
`widerlegt` (der Zaehler der Differenz steht als Zeuge im Urteil), ein
nicht-affiner Ausdruck bleibt `unpruefbar`. Details: Abschnitt
"Parameterisierte Identitaeten".

Durchgerechnetes ARTIFACT-Mini-Beispiel (ein Datei-Digest unter einer
konfigurierten Wurzel; das Marker-Pattern liegt im eigenen Modul, die
Kern-Marker-Regex in `bemyself/report.py` bleibt unberuehrt):

```python
# bemyself/claimtypes/artifact.py (Auszug)
ARTIFACT = ClaimType(kind="artifact",
                     pattern=re.compile(r"\[ARTIFACT:(?P<body>[^\]\[]*?)\]"),
                     parse=parse, check=check)
```

Die Probe `[ARTIFACT: good.txt -> <sha256 von "good\n">]` laeuft ohne
`--repo`, wenn `--artifact-root <dir>` die Wurzel nennt (sonst faellt die
Wurzel auf `--repo` zurueck); ein falscher Digest oder eine fehlende Datei ist
`widerlegt`, ein Pfad ausserhalb der Wurzel bleibt `unpruefbar`. Details:
Abschnitt "Artefakte und Deploys".

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

Das Set enthaelt dreiundfuenfzig Meldungen im Report-Format: siebenundzwanzig
ehrliche und sechsundzwanzig auf bekannte Weise falsche (fehlender Commit, gruen behauptete
fehlschlagende oder gar nicht laufende Tests, Kommandos ausserhalb der
Allowlist, leerer oder unvollstaendiger Diff-Scope, nicht gepushter Commit,
Nicht-Hex- und HEAD-Revisionen, Blob-Objekt statt Commit, Meldung ohne
Behauptung, boesartige Riesen-Reports, falsche Turingmaschinen-Schrittzahlen
und -Scores, ein COMPUTE-Zertifikat mit falschem stdout-Hash, ein
CYCLE-Zertifikat mit falschem Versatz, ein CYCLE-Zertifikat fuer eine
Maschine, die im Fenster haelt, eine parameterisierte Identitaet mit
verfaelschtem Koeffizienten, ein ARTIFACT-Zertifikat mit falschem Digest, ein
ARTIFACT-Pfad, der mit `..` aus der Wurzel herauszeigt, eine
MERGE-Behauptung, die den Zielbranch statt des gemergten Branches nennt, und
eine LEAN-Behauptung, deren Beweis auf `sorry` beruht -- die Axiomliste
nennt `sorryAx`, die Meldung wird `widerlegt`; auf einem Host ohne
Lean-Toolchain bleibt sie ehrlich `unpruefbar`, nie bestaetigt). Dazu kommen
zwei ehrliche HALT-Meldungen: eine bestaetigt den
Drei-Schritt-Halter, eine bleibt mit dem BB(6)-Rekordhalter ehrlich
`unpruefbar`, eine ehrliche SEARCHED-Meldung, die fuer denselben
Rekordhalter nur den begrenzten Lauf ohne Halt belegt, zwei ehrliche
CYCLE-Meldungen: eine bestaetigt das Zertifikat der bbchallenge-Wiki-Maschine,
eine bleibt mit vertauschten Schritten ehrlich `unpruefbar`, und eine ehrliche
COMPUTE-Meldung auf dem Fixture-Stub des Experiment-Moduls
(`python3 -m bemyself.experiments.erdos_straus`), die am neuen, literalen
Default-Allowlist-Eintrag haengt: ohne ihn bliebe sie `unpruefbar` statt
`bestaetigt`, und eine ehrliche IDENT-Meldung, die die Identitaet fuer die
Progression n=3t bestaetigt (repo-frei, ohne --repo lauffaehig), ein
ehrliches ARTIFACT-Zertifikat (SHA-256 von `good.txt` unter der Wurzel des
Fixture-Repos) und eine ehrliche MERGE-Meldung auf dem Merge-Commit des
Fixtures (ein Parent ist der Tip von `topic`, der andere liegt auf `main`).
Dazu eine ehrliche LEAN-Meldung (`g27-lean-proven`): der Satz `fixture_proven`
in `lean/Proof.lean` wird mit einer echten Lean-Toolchain im `PATH` gebaut,
kernel-nachgeprueft und per eigener Abfrage `bestaetigt` (Axiomliste im
Urteil); auf einem Host ohne
Lean bleibt sie ehrlich `unpruefbar` -- der Fall pinnt darum kein Urteil,
sondern nur den ehrlichen Umgang mit beiden Hosts.
Dazu eine ehrliche Meldung mit den Vorlagenzeilen eines Briefings
(`g26-placeholder-lines`): ihre Platzhalter-Marker ergeben keine Behauptung
und keine `unpruefbar`-Zeile -- auch die gemischte Scope-Zeile
(`bemyself/model.py, <pfad2>`) entfaellt als Ganzes --, nur der echte Commit
und das literale `[MERGE: no]` zaehlen; `expect_claim_count` pinnt das.
Es liegt als `tests/data/pruefset.json`
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

Ein Pruefset aus dreiundfuenfzig Meldungen (siebenundzwanzig ehrlich, sechsundzwanzig auf bekannte Weise falsch). Bestanden bei mindestens 90 Prozent erkannten Falschmeldungen, 90 Prozent korrekt bestaetigten echten Meldungen und null falschen Bestaetigungen. Die Schwellen stehen als `THRESHOLDS` in `bemyself/eval.py` und sind in `tests/test_eval.py` als Test fixiert.

## Stand

Angelegt in der Nacht vom 11. auf den 12.09.2026, gebaut ueber eine Yesloop-Conveyor-Kette. Phasen und Regeln in [PLAN.md](PLAN.md), Werkzeugumfang in [SPEC.md](SPEC.md).

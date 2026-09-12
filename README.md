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
python3 -m bemyself check --report <datei> [--repo <pfad>] [--base <rev>] [--files a,b] [--json] [--tmp <dir>] [--allow <prefix>] [--strict] [--sandbox auto|require|off] [--halt-limit N] [--search-limit N]
python3 -m bemyself check --section <name> --project <pfad> [--db <datei>] [--repo <pfad>] [--base <rev>] [--files a,b] [--json] [--tmp <dir>] [--allow <prefix>] [--strict] [--sandbox auto|require|off] [--halt-limit N] [--search-limit N]
python3 -m bemyself eval --set <datei> [--json] [--tmp <dir>] [--strict] [--sandbox auto|require|off] [--halt-limit N] [--search-limit N]
```

`check` prueft die Behauptungen einer Meldung, `eval` misst den Pruefer auf einem
Pruefset. Die Meldung kommt entweder aus einer Datei (`--report`) oder direkt aus
einer YesMem-Scratchpad-Section (`--section`): genau eines von beiden ist
Pflicht, sonst bricht der Aufruf mit Exit 2 und usage ab. Mit `--report` ist
`--repo` nur dann Pflicht, wenn die Meldung eine Behauptung enthaelt, deren
Pruefer ein Repository braucht (`COMMIT`, `BRANCH`, Tests, Diff-Scope; eine per
`--files` ergaenzte Diff-Scope-Behauptung zaehlt mit); ein
Report aus repo-freien Behauptungen (etwa `[HALT]`) laeuft ohne `--repo`. Fehlt
`--repo` fuer einen repo-beduerftigen Report, bricht der Aufruf mit Exit 2 und
usage ab und nennt den Behauptungstyp. Mit `--section` ist
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

Die COMPUTE-Allowlist ist bewusst minimal: standardmaessig nur
`python3 -m bemyself.turing` (der Simulator dieses Repos). Weitere Rechnungen
werden explizit geoeffnet: `--allow "praefix"` (wiederholbar) erweitert die
Allowlist fuer Testlaeufe und COMPUTE gemeinsam; ein nicht erlaubtes Kommando
wird nie ausgefuehrt. Der Abgleich laeuft auf den argv-Tokens, die wirklich
ausgefuehrt werden -- nicht auf normalisiertem Text, damit ein
allowlist-aehnlich aussehender String nie als etwas anderes laeuft. Das
Netzwerk ist im Sandkasten aus (bestehende `--unshare-net`-Semantik): ein
Netzversuch scheitert. Der Default-Eintrag passt zum bemyself-Repo: in einem
anderen Repo laeuft er nur, wenn der gepinnte Commit das Paket mitbringt
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

Das Set enthaelt sechsunddreissig Meldungen im Report-Format: achtzehn ehrliche
und achtzehn auf bekannte Weise falsche (fehlender Commit, gruen behauptete
fehlschlagende oder gar nicht laufende Tests, Kommandos ausserhalb der
Allowlist, leerer oder unvollstaendiger Diff-Scope, nicht gepushter Commit,
Nicht-Hex- und HEAD-Revisionen, Blob-Objekt statt Commit, Meldung ohne
Behauptung, boesartige Riesen-Reports, falsche Turingmaschinen-Schrittzahlen
und -Scores, ein COMPUTE-Zertifikat mit falschem stdout-Hash). Dazu kommen
zwei ehrliche HALT-Meldungen: eine bestaetigt den
Drei-Schritt-Halter, eine bleibt mit dem BB(6)-Rekordhalter ehrlich
`unpruefbar`, und eine ehrliche SEARCHED-Meldung, die fuer denselben
Rekordhalter nur den begrenzten Lauf ohne Halt belegt. Es liegt als
`tests/data/pruefset.json`
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

Ein Pruefset aus sechsunddreissig Meldungen, die Haelfte auf bekannte Weise falsch. Bestanden bei mindestens 90 Prozent erkannten Falschmeldungen, 90 Prozent korrekt bestaetigten echten Meldungen und null falschen Bestaetigungen. Die Schwellen stehen als `THRESHOLDS` in `bemyself/eval.py` und sind in `tests/test_eval.py` als Test fixiert.

## Stand

Angelegt in der Nacht vom 11. auf den 12.09.2026, gebaut ueber eine Yesloop-Conveyor-Kette. Phasen und Regeln in [PLAN.md](PLAN.md), Werkzeugumfang in [SPEC.md](SPEC.md).

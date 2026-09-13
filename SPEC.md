# SPEC bemyself: der Pruefer

## Zweck

Ein lokales Kommandozeilen-Werkzeug, das eine Meldung ueber den Zustand der Welt gegen die Welt prueft. Die Meldung stammt typischerweise aus dem DONE-Bericht eines Agenten (Phase 6 eines Yesloop-Laufs) oder aus einem Learning. Der Pruefer glaubt nichts, er leitet neu her.

## Eingabe

Eine Meldung in Textform oder als Scratchpad-Section, die Behauptungen enthaelt, typischerweise:

- `[COMMIT: <hash>]`, `[BRANCH: <name>]`, `[MERGE: <branch>]`, `[DEPLOY: ...]`
- `[HALT: <machine> -> <steps>]` und optional `[SCORE: <machine> -> <ones>]`
- `[SEARCHED: <machine> -> <n>]` (begrenzter Suchlauf ohne Halt, kein Nicht-Halte-Beweis)
- `[CYCLE: <machine> -> t1,t2,d]` (uebersetzter Zyklus, Nicht-Halte-Beweis fuer diese Maschine mit diesem Zertifikat)
- `[IDENT: n=<affine> ; a=<affine>, b=<affine>, c=<affine>]` (parameterisierte Identitaet, exakt als rationale Funktion in `t`; optional `; t >= <Schranke>`)
- `[COLORING: k=<k> ; <farbziffern>]` (Schur-Faerbung: explizites k-Faerbungs-Zertifikat fuer `1..N`; belegt nur die untere Schranke `S(k) >= N`)
- `[COMPUTE: <kommando> -> <sha256 des stdout>]` (Rechenzertifikat, gepinnter Commit)
- `[LEAN: <pfad.lean> -> <satz>]` (formaler Beweis, gepinnter Commit)
- `[ARTIFACT: <pfad> -> <sha256>]` (Datei-Digest unter der Artefakt-Wurzel)
- "Tests run: <command> -> exit 0"
- "Regression baseline: ..."
- "send_to orchestrator: yes"
- Phasen-Bloecke mit `**Status:** COMPLETE`

Ein Marker, dessen Rumpf ein Platzhalter ist -- ein Winkel-Token (`<hash>`,
`<machine>`, `<pfad>`), das woertliche `TODO` oder eine abgeschnittene
Ellipse (`e5b68dd1…`, `...`) -- ist eine Vorlage und keine Behauptung: er
wird wie eine Zeile ohne Marker ignoriert und nie als `UNVERIFIABLE`
gemeldet. Die Regel gilt auf allen Parser-Flaechen (die Marker oben, die
`Tests run:`-Zeile, die `Files in scope:`-Zeile und die Felder jedes
registrierten Behauptungstyps) und pro Behauptung: literale Marker auf
derselben Zeile bleiben Behauptungen, ein Platzhalter in einem Feld laesst
die ganze Behauptung entfallen. Umschliessende Backticks aendern die
Erkennung nicht. `./...` und `src/...` (ASCII-Ellipse am Pfadmuster-Ende)
sind keine Platzhalter, ein leeres `<>` und ein `<` ohne schliessendes `>`
ebenso wenig. Eine Vorlage erscheint in keiner Ausgabe (kein JSON-Eintrag,
kein Exit-Code-Effekt): das Fehlen einer Zeile und eine als Vorlage
gelesene Zeile sind nicht unterscheidbar. Siehe README, Abschnitt
"Grenzen", fuer die ausgemessenen Grenzfaelle.

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
| IDENT | beide Seiten als rationale Funktionen in t expandieren, Differenz bilden, Zaehler identisch null pruefen; dazu Bereichsbedingungen (a,b,c positiv, n >= 2 fuer alle t >= Schranke) -- eine Progression fuer alle Parameter, kein Beweis der Vermutung |
| COLORING | alle Tripel x <= y mit x + y <= N nachzaehlen (in-process); CONFIRMED nur ohne monochromatisches Tripel, REFUTED mit dem ersten Verstoss in kanonischer Reihenfolge -- ein Zertifikat der unteren Schranke S(k) >= N, keine Gleichheit, nichts ueber die obere Schranke |
| COMPUTE | Kommando im Wegwerf-Checkout des gepinnten Commits im bwrap-Sandkasten ausfuehren, sha256(stdout) streamen und vergleichen |
| LEAN | Datei existiert im gepinnten Commit; Datei (bzw. ihr Lake-Modul) im Wegwerf-Checkout bauen, Kopie mit angehaengtem `#print axioms <satz>` im bwrap-Sandkasten re-elaborieren; eine `#print axioms`-Zeile mit `sorryAx` widerlegt, sonst bestaetigt mit vollstaendiger Axiomliste |
| MERGE | Commit existiert, genau zwei Parents, ein Parent ist der Tip des genannten Branches, der andere liegt auf der Zielbranch; Widerspruch nennt die echten Parents |
| ARTIFACT | Datei existiert unter der Artefakt-Wurzel und ihr SHA-256 stimmt; Pfad per realpath konfiniert, Streaming mit Groessenlimit |
| Beleg-ID existiert | Nachschlagen in der angegebenen Quelle (Datei, DB, Session-Registry) |
| Deploy erfolgt | Kein Checker (absichtlich): ein generischer Deploy-Begriff fehlt; `[ARTIFACT]` ist die pruefbare Form |

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
`[COMPUTE]`, `[ARTIFACT]`): README, Abschnitt "Neuen Behauptungstyp hinzufuegen".

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
`--cycle-limit N` bei `check` und `eval`) oder einem Band beziehungsweise
einem Vergleichsfenster jenseits der Materialisierungsschranke `TAPE_LIMIT`
(`2**24` Zellen, beide Bandhaelften zusammen) -- der Vergleich muss wirklich
durchgefuehrt worden sein, es gibt keine Bestaetigung durch Auslassung.

Abgrenzung: `CONFIRMED` ist ein vollstaendiger Nicht-Halte-Beweis fuer diese Maschine mit diesem Zertifikat;
der Typ ist kein allgemeiner Nicht-Halte-Pruefer (er sucht keine Zertifikate, er
rechnet das vorgelegte nach) und kein Ersatz fuer SEARCHED: Ein SEARCHED-Lauf wird nie zu einem CYCLE-Zertifikat aufgewertet.
Der SEARCHED-Urteilstext bleibt unveraendert ("does not prove that the machine
never halts").

## Parameterisierte Identitaeten (`IDENT`)

`[IDENT: n=<affine> ; a=<affine>, b=<affine>, c=<affine>]` (optional mit
`; t >= <Schranke>`, Default `t >= 1`) behauptet, dass
`4/n(t) = 1/a(t) + 1/b(t) + 1/c(t)` fuer jedes ganze `t >= <Schranke>` exakt
gilt, wobei `n`, `a`, `b`, `c` affine Funktionen der ganzzahligen Variablen
`t` mit ganzzahligen Koeffizienten sind. Die Pruefung ist exakt, ohne
Gleitkomma und ohne Repo-Bedarf: beide Seiten werden als rationale Funktionen
in `t` dargestellt, ihre Differenz gebildet und der Zaehler als Polynom in
`t` geprueft (alle Koeffizienten null). Zusaetzlich wird der deklarierte
Bereich geprueft: `a`, `b`, `c` positiv und `n >= 2` fuer alle
`t >= <Schranke>`; ein Bereich, der das nicht beweisbar absichert, ergibt
`UNVERIFIABLE` -- der Pruefer nimmt keine Bedingung an, die er nicht zeigen
kann.

Urteile: `CONFIRMED` nur, wenn der Zaehler identisch null ist und die
Bereichsbedingungen fuer alle `t >= <Schranke>` nachweislich gelten; der
Urteilstext nennt die Progression und traegt die feste Formulierung "holds as
a rational identity in t for every t >= <Schranke>" samt ausdruecklicher
Abgrenzung ("this is not a proof of the conjecture"). `REFUTED`, wenn sich
die beiden Seiten als rationale Funktionen unterscheiden (der Zaehler der
Differenz steht als Zeuge im Urteil; ein nicht verschwindendes Polynom hat
nur endlich viele Nullstellen, die Identitaet scheitert also fuer unendlich
viele `t` eines unbeschraenkten Bereichs). `UNVERIFIABLE` bei falscher
Rumpfform, fehlenden, doppelten oder unbekannten Feldern, nicht-affinen
Ausdruecken (quadratische oder gebrochene Terme, ein anderer Parameter als
`t`, Leerzeichen im Ausdruck), Zahlen jenseits der Interpreter-Grenze fuer
`int(text)` oder nicht sauber abgesichertem Bereich (Nullstelle im
Parameterbereich, fallende Gerade, Schranke mit `n < 2`).

Abgrenzung: Ein `CONFIRMED` ist eine Aussage ueber unendlich viele
Parameterwerte -- die Progression `n(t)` ist fuer alle Parameter durch den
expliziten Zeugen abgedeckt, anders als das endliche Fenster eines
SEARCHED-Laufs. Eine verifizierte Identitaet deckt eine Progression fuer alle
Parameter ab; sie ist kein Beweis der Vermutung, solange nicht alle
Restklassen abgedeckt sind. README und SPEC dokumentieren es, und ein Test
fixiert die Formulierung (analog SEARCHED/CYCLE).

Beispiel: `[IDENT: n=3t ; a=t, b=4t, c=12t]` -> `CONFIRMED`
(`numerator=0`); ein verfaelschter Koeffizient (`b=4t+1`) -> `REFUTED`
(`numerator=-9t^2`); `[IDENT: n=3t ; a=t, b=4t, c=12t ; t >= 0]` ->
`UNVERIFIABLE`, weil `a` bei `t = 0` nicht positiv ist. Die Bewertung fuer
Erdos-Straus (welche Progressionsklassen parametrisch abgedeckt sind, aus
Quellen belegt) steht unter `yesdocs/erdos-straus/`.

## Schur-Faerbungen (`COLORING`)

`[COLORING: k=<k> ; <farbziffern>]` behauptet, dass die explizite
Faerbung der Zahlen `1..N` mit `k` Farben keine monochromatische Loesung
von `x + y = z` enthaelt. `k` ist eine einzelne Ziffer `1..9`, die
Farbfolge hat die Laenge `N` (eine Ziffer pro Zahl, Ziffer `i` ist die
Farbe der Zahl `i`), jede Ziffer liegt in `1..k`. Die Pruefung ist
in-process und ohne Repo-Bedarf: der Pruefer zaehlt alle Tripel `x <= y`
mit `x + y <= N` nach und prueft jedes auf Monochromie.

Urteile: `CONFIRMED`, wenn kein monochromatisches Tripel existiert; der
Urteilstext nennt die Zahl der geprueften Tripel und die feste Abgrenzung
("certificates the lower bound S(k) >= N only -- it does not prove
equality and says nothing about the upper bound"). `REFUTED` beim ersten
Verstoss in kanonischer Reihenfolge (x aufsteigend, dann y aufsteigend);
der Verstoss steht als Zeuge im Urteil
(`<x> + <y> = <z> with <x>, <y>, <z> all in color <c>`). `UNVERIFIABLE`
bei falscher Rumpfform, einer Farbanzahl ausserhalb `1..9`, einer Ziffer
ausserhalb `1..k`, einer leeren Folge oder einer Laenge ueber dem
ausfuehrbaren Limit (Default 4096, `--coloring-limit`; Zeilen jenseits
von 8192 Zeichen ignoriert der Report-Leser, sodass ein hoeheres Limit
nicht greifen kann).

Abgrenzung: Ein `CONFIRMED` belegt nur die untere Schranke `S(k) >= N`;
es beweist keine Gleichheit und sagt nichts ueber die obere Schranke.
Eine Faerbung ist ein kompaktes Zeugnis; die obere Seite (keine
k-Faerbung von `1..N+1`) hat kein kompaktes Zertifikat. README und SPEC
dokumentieren es, und ein Test fixiert die Formulierung.

Beispiele: `[COLORING: k=2 ; 1221]` -> `CONFIRMED` (4 Tripel, kein
Verstoss); `[COLORING: k=2 ; 1121]` -> `REFUTED` mit `1 + 1 = 2 with
1, 1, 2 all in color 1`; `[COLORING: k=2 ; 123]` -> `UNVERIFIABLE`
(Ziffer 3 ist keine Farbe der Behauptung). Die Landkarte der belegten
Schranken -- untere Schranken `S(1..4) = 1, 4, 13, 44`, `S(5) = 160`
exakt (SAT, Heule 2018), `S(6) >= 536` und `S(7) >= 1696` offen -- mit
Zertifikaten, Quellen und Pruefbefehlen steht unter `yesdocs/schur/`.

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

Die COMPUTE-Allowlist ist getrennt und minimal: Default sind die
Repo-eigenen Module als literale Eintraege -- `python3 -m bemyself.turing`
(der Simulator dieses Repos) und `python3 -m bemyself.experiments.erdos_straus`
(das beschraenkte Erdős-Straus-Experiment, s. README "Experimente"); in einem
anderen Repo laufen sie nur, wenn der gepinnte Commit das Paket mitbringt.
`--allow <prefix>` (wiederholbar) erweitert sie zusammen mit der
Test-Allowlist. Kein Wildcard: ein kuenftiges Modul des Experiment-Pakets
wird nicht implizit geoeffnet. Das Netzwerk ist im Sandkasten aus (bestehende
`--unshare-net`-Semantik).

Grenze: Der Hash belegt die Ausgabe des Kommandos auf dem gepinnten Commit,
nicht die Bedeutung der Rechnung; der Checkout bringt seinen eigenen Code
mit, wer den Commit kontrolliert, kontrolliert die Ausgabe.

## Formale Beweise (`LEAN`)

`[LEAN: <pfad.lean> -> <satz>]` behauptet, dass im gepinnten Commit des
Reports die Datei `<pfad.lean>` existiert und die Deklaration `<satz>` dort
ohne `sorry`/`admit` bewiesen ist. Die Bindung an den Commit ist dieselbe wie
bei COMPUTE und MERGE: genau ein hash-foermiger `[COMMIT]`-Marker bindet
(Platzhalter wie `<hash>` zaehlen nicht); mehrere verschiedene Commits binden
nichts und die Behauptung bleibt `UNVERIFIABLE`. Der Typ deklariert
`needs_repo=True` (die Datei wird gegen den Commit-Baum geprueft) und
`binds_commit=True`.

Pruefkette: `git cat-file -e <commit>:<pfad>` (fehlt die Datei dort:
`REFUTED`), `git cat-file -t` muss `blob` liefern (eine Tree-Objekt-Antwort
ist `REFUTED`); Pfad und Satzname werden streng validiert, bevor argv oder
generierter Lean-Quelltext entstehen (Pfad: repository-relativ, nur
`[A-Za-z0-9_./-]`, Endung `.lean`, kein `..`/Leerbestandteil; Satzname:
Lean-Identifier mit Unicode-Buchstaben/Ziffern/Unterstrich, Punkten und
`!?`). Danach: Wegwerf-Checkout (`git clone --no-hardlinks` +
`git checkout`, wie bei Tests/COMPUTE); liegt die Datei in einem
Lake-Projekt (lakefile in ihrem Verzeichnis oder darueber), baut
`lake build <modul>` das Modul aus dem Checkout-Quelltext, dann wird eine
Kopie der Datei mit angehaengtem `#print axioms <satz>` mit `lean` bzw.
`lake env lean` re-elaboriert (beides aus dem `PATH`; `ELAN_HOME` wird aus
dem elan-Installationspfad abgeleitet, weil der Lauf mit `HOME=<checkout>`
isoliert ist; ohne `lean-toolchain`-Datei in Reichweite wird die einzige
installierte Toolchain als `ELAN_TOOLCHAIN` gepinnt, damit der Shim im
netzlosen Sandkasten nicht nach der Standardversion fragt). Kein `#print
axioms`-Ergebnis fuer genau diesen Satz macht
die Behauptung `UNVERIFIABLE` -- es gibt keine Bestaetigung durch Auslassung.

Urteile: `CONFIRMED` nur mit einer `#print axioms`-Zeile fuer genau diesen
Satz, die `sorryAx` NICHT nennt; die Zeile mit der vollstaendigen
Axiomliste steht im Urteil (logische Grundaxiome wie `propext`,
`Quot.sound`, `Classical.choice` werden also sichtbar; `CONFIRMED` heisst
nicht "axiomfrei"). `REFUTED` bei `depends on axioms: [sorryAx]` (genau
diese Zeile im Urteil), bei fehlender Deklaration (`Unknown constant`), bei
fehlender Datei im Commit und bei einem Kompilierfehler der Datei (erste
Fehlerzeile im Urteil; auch ein Build-Fehler, dessen erste Fehlerzeile die
Zieldatei nennt). `UNVERIFIABLE` ohne `lean` im `PATH`, ohne nutzbaren
Sandkasten, bei unbekanntem Sandkasten-Modus, ohne gebundenen Commit, bei
ungueltigem Pfad oder Satznamen, bei Timeout (600 s je Build/Elaboration),
bei Ausgabe ueber dem Limit, ohne `#print axioms`-Zeile trotz Exit 0 und
immer dann, wenn eine Abhaengigkeit des Projekts im Checkout fehlt -- der
Urteilstext nennt Modul und erste Fehlerzeile, und ein Dependency-Fehler
zaehlt nur, wenn der fehlende Modulname in den `import`-Zeilen der Datei
steht (oder eine Netz-/Toolchain-Meldung vorliegt): eine Fehlermeldung im
repo-kontrollierten Output darf eine Widerlegung nicht zu `UNVERIFIABLE`
herabstufen.

Prueftiefe (Doktrin): Das Urteil heisst "re-elaboriert mit Lean <version>":
der gepinnte Quelltext wurde erneut elaboriert, und der Lean-Kernel prueft
jede Deklaration waehrend der Elaboration. Ein separater Kernel-Recheck des
kompilierten `.olean` durch `leanchecker` wurde untersucht und wird NICHT
genutzt: `leanchecker` akzeptiert Module, deren Beweis auf `sorryAx` beruht
(mit Lean 4.33.1 verifiziert, rc 0 ohne Ausgabe), kann die
`#print axioms`-Evidenz also nicht ersetzen und stuetzt sich auf dieselbe
Kernel-Implementierung; der Urteilstext behauptet darum nie ein
"unabhaengiges" oder blosses "kernelgeprueftes" Urteil ohne diese
Praezisierung. Grenze der Aussage: die Axiomliste macht sichtbar, worauf der
Beweis beruht (auch nicht-logische Axiome und `Lean.ofReduceBool` aus
`native_decide` stehen dort) -- der Pruefer beurteilt nicht, ob diese Axiome
wahr oder wunschenswert sind, nicht die Bedeutung des Satzes, und nicht die
Herkunft der Datei (wer den Commit kontrolliert, kontrolliert die Datei).

Isolation: Die Elaboration fuehrt Code aus (Taktiken, Metaprogramme,
`#eval`), und `lake` wuerde fehlende Abhaengigkeiten per Netz nachladen --
darum verhaelt sich `--sandbox=auto` fuer diesen Typ wie `require`: ohne
nutzbaren bwrap bleibt die Behauptung `UNVERIFIABLE`, es gibt keinen stillen
ungesandboxten Rueckfall; nur ein ausdrueckliches `--sandbox=off` laeuft
ohne Sandkasten und nennt das im Urteil. Der Sandkasten ist die bestehende
bwrap-Semantik (Wurzel read-only -- die Toolchain unter `~/.elan` bleibt
dadurch lesbar --, nur der Checkout beschreibbar, eigener Netz-/PID-/UTS-
Namensraum, `/run` als leeres tmpfs). Hat das gepruefte Repository neben dem
Lake-Projekt einen `.lake`-Cache im Arbeitsbaum und der Checkout keinen,
wird dessen `packages`-Verzeichnis read-only in denselben Pfad gebunden (der
Checkout baut in sein eigenes, beschreibbares `.lake`); das Kommando im
Urteil nennt den Pfad. Die `.lake`-Wahl ist eine Naeherung, die das Urteil
benennt: Abhaengigkeiten sind nicht Teil des Commits, ein Cache ohne
kompilierte Artefakte kann den Build nicht tragen, und ohne Cache plus
ausgeschaltetem Netz (Sandkasten) bleibt eine fehlende Abhaengigkeit
`UNVERIFIABLE` statt erfunden zu werden.

## Merges (`MERGE`)

`[MERGE: <branch>]` behauptet, dass der Commit der Meldung der Merge des
genannten Branches ist. Die Bindung an den Commit ist dieselbe wie bei
COMPUTE: genau ein hash-foermiger `[COMMIT]`-Marker bindet (Platzhalter wie
`<hash>` zaehlen nicht); mehrere verschiedene Commits binden nichts und die
Behauptung bleibt `UNVERIFIABLE`. Geprueft wird lokal, ohne Netz und ohne
Fetch:

- Der Commit existiert und hat genau zwei Parents; null, ein oder mehr als
  zwei Parents ergeben `REFUTED` (kein Zwei-Parents-Merge).
- Einer der Parents ist der Tip des genannten Branches (`refs/heads/<branch>`,
  sonst `refs/remotes/origin/<branch>`).
- Der andere Parent liegt auf der Zielbranch oder ist ihr Tip; Zielbranch ist
  `origin/HEAD`, sonst eine lokale `main` oder `master`, sonst die aktuelle
  Branch. Ohne bestimmbare Zielbranch bleibt die Behauptung `UNVERIFIABLE`.

Ein Widerspruch ergibt `REFUTED` und das Urteil nennt die tatsaechlichen
Parents und den Tip des genannten Branches (kurze Hashes). `REFUTED` ist
ausserdem ein Commit, der selbst auf dem genannten Branch liegt (so faellt
der Zielbranch auf, wenn er als gemergter Branch genannt wird), und ein
Commit, dessen kein Parent zur Geschichte des genannten Branches gehoert.
`UNVERIFIABLE` bleiben ausserdem: ein Wert ohne Branchnamen
(`[MERGE: no]`, `pending-PR`, `blocked-PR` sind Statuswerte des
Yesloop-DONE-Payloads, keine Branches; `HEAD` ist eine Revision, keine
Branch), ein Branch, der weder lokal noch auf `origin` aufloest (ein nach dem
Merge geloeschter Branch wird nicht erraten), ein Branch, dessen Tip nach dem
Merge weiterlief (kein Objekt haelt fest, wo eine Branch beim Merge zeigte;
das Urteil nennt den Parent, der in der Branch-Geschichte liegt), ein
fehlender Commit und ein nicht aufloesbarer Commit-Hash.

Abgrenzung: Der Check belegt die Merge-Struktur, nicht die Absicht. Er liest
den Tip des Branches zum Pruefzeitpunkt; ein Branch, der nach dem Merge
weiterlief, macht die Behauptung `UNVERIFIABLE` statt `REFUTED`. Geprueft
wird der andere Parent gegen die Zielbranch, nicht der gemeldete Commit
selbst: ein Merge, der die Zielbranch nie erreicht hat, wird `CONFIRMED`,
wenn der andere Parent auf der Zielbranch liegt -- die Behauptung nennt dann
eine wahre Merge-Struktur, aber keinen Merge auf der Zielbranch. Ein
`MERGE`-Claim deklariert keinen
Repo-Bedarf: eine Meldung, die nur `[MERGE: no]` traegt, laeuft ohne `--repo`
weiter (Exit-Codes unveraendert), und ohne Repository bleibt die Behauptung
`UNVERIFIABLE` statt eines Usage-Fehlers.

## Artefakte (`ARTIFACT`) und die Grenze von `DEPLOY`

`[ARTIFACT: <pfad> -> <sha256>]` behauptet, dass die Datei existiert und ihr
Inhalt genau den behaupteten SHA-256 hat. Der Pfad stammt aus einer
untrusted Meldung und wird darum konfiniert: er wird unter der Artefakt-Wurzel
aufgeloest und nur akzeptiert, wenn der ueber `realpath` aufgeloeste Pfad in
der Wurzel bleibt. `..`-Bestandteile werden abgelehnt (auch wenn sie
rechnerisch wieder in die Wurzel fuehren); ein Symlink innerhalb der Wurzel,
der nach aussen zeigt, bleibt `UNVERIFIABLE`; ein Symlink, dessen Ziel in der
Wurzel bleibt, wird verfolgt. Ausserhalb der Wurzel findet kein Lesevorgang
statt. Die Datei wird einmal geoeffnet (`O_NONBLOCK` gegen blockierende Named
Pipes), per `fstat` als regulaere Datei geprueft und durch diesen Deskriptor
in Bloecken gehasht (konstantes Gedaechtnis); das Limit
`MAX_ARTIFACT_BYTES = 256 MiB` begrenzt die Zeit pro Behauptung, eine
groessere Datei bleibt `UNVERIFIABLE`, ebenso eine Datei, die waehrend des
Lesens ueber das Limit waechst. Ein Hardlink in der Wurzel ist von einer
eigenen Datei nicht unterscheidbar (gleicher Inode); der Inhalt der Wurzel
ist der Vertrauensbereich des Aufrufers -- die Konfinierung schuetzt vor
Lesezugriffen ausserhalb, nicht vor einem Schreiber mit Zugriff innerhalb:
eine Datei kann zwischen der `realpath`-Aufloesung und dem Oeffnen
ausgetauscht werden (derselbe Vertrauensbereich, keine neue Faehigkeit).

Urteile: `CONFIRMED` nur bei vollstaendig gelesener Datei mit exakt dem
behaupteten Digest (Gross-/Kleinschreibung egal); `REFUTED` bei fehlender
Datei, bei einem Pfad, der keine regulaere Datei ist (Verzeichnis, Named
Pipe, Geraet), und bei abweichendem Digest -- das Urteil nennt Pfad,
tatsaechlichen Digest und Groesse, denn Abwesenheit und Abweichung sind
Befunde. `UNVERIFIABLE` ohne Wurzel (kein `--artifact-root`, kein `--repo`),
bei fehlender oder nicht-Verzeichnis-Wurzel, bei einem Pfad ausserhalb der
Wurzel, bei einem Pfad, den der Pruefer nicht oeffnen darf (fehlende Rechte),
bei einem leeren Pfad, bei einem Digest, der keine 64 Hex-Ziffern sind, und
bei einer Datei
ueber dem Limit. Der Typ deklariert keinen Repo-Bedarf: die Wurzel ist
konfiguriert (`--artifact-root <dir>`, Default das Repository), nicht das
Repository.

`DEPLOY` bleibt absichtlich ohne Pruefer: Ein generischer, nachrechenbarer
Deploy-Begriff existiert nicht (ein neuer Prozess, ein DNS-Eintrag, ein
Artefakt in einer fremden Registry, eine Nachricht an Dritte), und eine
Pruefung, die den Deploy nicht wirklich anfasst, waere eine Scheinpruefung.
`[DEPLOY: ...]` bleibt darum dauerhaft `UNVERIFIABLE` (kein Checker
registriert); das ehrliche Werkzeug fuer "Deploy erfolgt" ist `[ARTIFACT]`
samt Digest.

## Kommandos (Ziel)

| Kommando | Wirkung |
|---|---|
| `python3 -m bemyself check --report <datei> [--repo <pfad>] [--strict] [--sandbox auto\|require\|off] [--artifact-root <dir>] [--halt-limit N] [--search-limit N] [--cycle-limit N] [--coloring-limit N]` | Alle Behauptungen der Meldung pruefen, Urteil je Behauptung ausgeben; `--repo` ist Pflicht, sobald eine vorkommende Behauptung ein Repository deklariert |
| `python3 -m bemyself check --section <name> --project <pfad> [--strict] [--sandbox auto\|require\|off] [--artifact-root <dir>] [--halt-limit N] [--search-limit N] [--cycle-limit N] [--coloring-limit N]` | Meldung aus einer YesMem-Scratchpad-Section ziehen und pruefen |
| `python3 -m bemyself eval --set <datei> [--strict] [--sandbox auto\|require\|off] [--halt-limit N] [--search-limit N] [--cycle-limit N] [--coloring-limit N]` | Pruefset auswerten, Erkennungsraten berichten |
| `python3 -m bemyself --json` | Maschinenlesbare Ausgabe fuer alle Kommandos |

`--repo` verlangt `check --report` nur, wenn mindestens eine vorkommende
Behauptung ein Repository deklariert (COMMIT, BRANCH, Tests, Diff-Scope,
COMPUTE, LEAN; eine
per `--files` ergaenzte Diff-Scope-Behauptung zaehlt mit). Der
Bedarf steht am Checker bzw. am `ClaimType.needs_repo` in der Registry, nicht
als Liste im CLI; HALT/SCORE, SEARCHED, CYCLE, IDENT und COLORING sowie unbekannte
Typen ohne Checker laufen ohne `--repo` (und bleiben gegebenenfalls
`UNVERIFIABLE`). MERGE und ARTIFACT deklarieren ebenfalls keinen Bedarf: eine
Merge-Behauptung bleibt ohne Repository `UNVERIFIABLE` (kein Usage-Fehler),
und ARTIFACT loest seine Pfade gegen die Artefakt-Wurzel auf
(`--artifact-root <dir>`, Default das Repository).

## Harte Regeln

- Nur lesend auf `~/.claude/yesmem`. Keine Schreibzugriffe auf Live-Datenbanken.
- ARTIFACT liest nur unter der konfigurierten Wurzel: der Pfad wird mit `realpath` aufgeloest, `..`-Bestandteile und Ausbrueche (absoluter Pfad draussen, Symlink nach draussen) werden abgelehnt, gelesen wird eine regulaere Datei und nur einmal (Streaming, Limit 256 MiB).
- Pruefungen laufen in einem Wegwerf-Checkout, nie im Arbeitsverzeichnis des Nutzers.
- Der Pruefer selbst nutzt kein Netzwerk ausser `git fetch` gegen das eigene Remote und `git clone` aus dem lokalen Repo. Erlaubte Testkommandos laufen standardmaessig in einem bwrap-Sandkasten (`--sandbox=auto`, wenn bwrap vorhanden ist und startet): Wurzel read-only, nur der Wegwerf-Checkout beschreibbar, eigener Netz-/PID-/UTS-Namensraum, `/run` als leeres tmpfs (Socket-Pfade des Rechners fehlen). Ohne nutzbares bwrap laufen sie ungesandboxt, und jedes Ergebnis nennt den Grund; `--sandbox=require` laesst sie dann gar nicht laufen (die Testbehauptung bleibt `unpruefbar`, mit `--strict` faellt der Lauf), `--sandbox=off` schaltet den Sandkasten ab. Der Sandkasten ersetzt die Allowlist nicht (nur erlaubte Kommandos laufen ueberhaupt), ist keine vollstaendige Isolationsgrenze gegen feindlichen Code (sichtbare Dateien bleiben lesbar) und schuetzt nicht gegen Kernel-Exploits.
- Keine neuen Abhaengigkeiten, Python 3 Standardbibliothek. bwrap ist ein optionales Systemprogramm, wird zur Laufzeit erkannt und ist nie Voraussetzung fuer den Pruefer selbst. Die HALT-, SEARCHED- und CYCLE-Pruefungen laufen in-process im Simulator und brauchen weder Netz noch Sandkasten. COMPUTE-Kommandos laufen unter derselben Sandkasten-Semantik wie Testkommandos, nur ueber die getrennte, standardmaessig minimale COMPUTE-Allowlist (`--allow` erweitert); ohne nutzbaren Sandkasten bei `--sandbox=require` laufen sie gar nicht.
- LEAN prueft in einem Wegwerf-Checkout mit der Toolchain aus dem `PATH` (`lean`, fuer Lake-Projekte `lake`; `ELAN_HOME` wird abgeleitet). Die Elaboration verlangt denselben bwrap-Sandkasten wie COMPUTE, aber ohne stillen Rueckfall: `auto` verhaelt sich wie `require` (die Elaboration fuehrt Code aus, und `lake` wuerde fehlende Abhaengigkeiten ueber das Netz nachladen); nur `--sandbox=off` laeuft ohne Sandkasten und nennt das im Urteil. Ein `.lake`-Cache des Arbeitsbaums wird nur read-only in den Checkout gebunden und im Urteil benannt; fehlende Abhaengigkeiten bleiben `UNVERIFIABLE`. Kein Urteil behauptet einen unabhaengigen Kernel-Recheck: der Urteilstext nennt die Re-Elaboration mit Toolchain-Version und die Axiomliste.
- Eine falsche Bestaetigung ist der schwerste Fehler. Im Zweifel `UNVERIFIABLE`, nie `CONFIRMED`. Fuer COMPUTE heisst das: kein Lauf ohne Allowlist, kein Lauf ohne aufloesbaren Commit, ausdrueckliche Vorabpruefung des Programms, Ausgabe- und Zeitlimits statt Kuerzung, und ein Urteil nur ueber den Hash des stdout.

## Strict-Modus

Ohne `--strict` bedeutet Exit 0 "mindestens eine Behauptung bestaetigt, keine widerlegt"; unpruefbare Behauptungen sind erlaubt. Fuer ein Merge-Gate ist das zu schwach: eine Meldung, deren Kernbehauptung (etwa "Tests gruen") nie geprueft wurde, kann Exit 0 liefern, solange eine andere Behauptung (etwa ein existierender Commit) bestaetigt ist.

`check --strict` schliesst die Luecke: Exit 0 nur, wenn jede Behauptung bestaetigt ist. Jede unpruefbare Behauptung ergibt Exit 4, sofern nichts widerlegt wurde und mindestens eine Behauptung bestaetigt ist; widerlegte Behauptungen bleiben Exit 1, und ein Bericht ohne bestaetigte Behauptung bleibt Exit 3. Die Codes 0-3 behalten in beiden Modi dieselbe Bedeutung, 4 ist der strict-spezifische Code. Ohne Flag ist das Verhalten unveraendert. Empfehlung: Merge-Gates mit `check --strict` fahren und nur bei Exit 0 mergen.

`eval --strict` ist ein Opt-in mit derselben Doktrin auf Set-Ebene: der Lauf schlaegt mit Exit 4 fehl, sobald eine Behauptung des Sets unpruefbar bleibt und die Schwellen erfuellt sind; ein Lauf, der die Schwellen verfehlt, bleibt Exit 1. Das ausgelieferte Pruefset besteht diesen Modus bewusst nicht (unpruefbare Behauptungen sind Teil des Designs); `make eval` bleibt unveraendert Exit 0.

## Nicht-Ziele

- Keine Reparatur, keine Korrektur von Meldungen. Der Pruefer urteilt, er handelt nicht.
- Kein Ersatz fuer den Done-Guard. Der Guard prueft Form, der Pruefer prueft Substanz.
- Keine Ausfuehrung von Befehlen, die die Meldung selbst vorschlaegt, ohne Whitelist.

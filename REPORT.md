# proofboy — Statusreport

2026-09-12, 16:00, nachgetragen um 18:35, 23:05 und 23:10 sowie am 13.09. um 09:15. Geschrieben von einem Dokumentations-Agenten (Auftrag: eine Datei, keine Commits, keine Änderungen am System). Alle Messwerte in Abschnitt 2 wurden selbst in Wegwerf-Klonen erzeugt: erster Durchgang am 12.09. von 15:56 bis 15:59 auf `47301fc` (`/tmp/opencode/report-clone`), Nachträge von 18:30 bis 18:35 auf `3025c29` und von 22:50 bis 23:00 auf `b85de12` (`/home/carsten/projects/.tmp-proofboy/report-clone`, außerhalb von `/tmp` — Grund in Abschnitt 2), zuletzt von 23:03 bis 23:10 auf `7edf993` und am 13.09. von 09:13 bis 09:15 auf `ec5b4ab` (selber Klon). Zahlen aus Merge-Nachrichten und aus dem Koordinationsprotokoll sind als solche gekennzeichnet.

**Stand jetzt (13.09., 09:15):** master = `ec5b4ab`. Die Prüfer-Kette steht unverändert bei P1–P15 plus Flaky-Fix; die beiden Merges seit `7edf993` gehören zur separat beauftragten Spur (ihr Diff berührt `proofboy/` und das Prüfset nicht). Testsuite des Masters (selbst gemessen): 818 Tests, alle grün (781 Prüfer-Stand, +37 aus der fremden Spur); Eval-Schwellen erfüllt. Das retrospektive Audit (Abschnitt 6) gilt unverändert: 21 bestätigte, 0 widerlegte DONE-Behauptungen, 55 unprüfbare. Offene Prüfer-Arbeiten: keine. Ein Remote gibt es nicht; es wurde nichts gepusht.

## 1. Was das ist

Der Prüfer (proofboy) ist ein Werkzeug, das die Meldung eines Agenten nicht glaubt, sondern sie neu herleitet. Aus „Tests grün, Commit abc123, Branch gepusht, Deploy erfolgt“ wird jede Behauptung einzeln gegen die Wirklichkeit geprüft: Existiert der Commit, liegt er auf dem Remote, ist der Diff wirklich der behauptete, laufen die Tests auf einem sauberen Checkout dieses Commits wirklich durch. Dazu kommen mathematische Behauptungen: Halten einer Turingmaschine (per Zeuge, der exakten Schrittzahl), begrenzte Suchläufe (ehrlich als solche gekennzeichnet), übersetzte Zyklen (endliches Nicht-Halte-Zertifikat) und generische Rechenzertifikate (SHA-256 der Kommandoausgabe). Das Urteil ist je Behauptung bestätigt, widerlegt oder unprüfbar, jeweils mit ausgeführtem Kommando und roher Ausgabe. Eine falsche Bestätigung gilt als schwerster Fehler; im Zweifel lautet das Urteil unprüfbar. Das Werkzeug nutzt nur die Python-Standardbibliothek, prüft in Wegwerf-Checkouts, liest YesMem-Sections ausschließlich lesend und betreibt Testkommandos in einem bwrap-Sandkasten.

## 2. Was gemessen ist

Messort: zwei Wegwerf-Klone von `/home/carsten/projects/proofboy`; Durchgänge 15:56–15:59 auf `47301fc` und 18:30–18:35 auf `3025c29` im Klon `/tmp/opencode/report-clone`, Durchgänge 22:50–23:00 auf `b85de12` und 23:03–23:10 auf `7edf993` im Klon `/home/carsten/projects/.tmp-proofboy/report-clone`. Der Umzug aus `/tmp` hat einen Grund: Der msheet-Witness-Sandkasten mountet `--tmpfs /tmp` und macht Klone unter `/tmp` für sandboxed py-Witnesses unsichtbar (der Grund steht bei der Testanzahl unten). `bwrap` ist vorhanden, Testläufe liefen also im Sandkasten. Jede Zeile nennt das Kommando; die Belegausgaben stehen darunter.

| Messgröße | Kommando | Ergebnis |
|---|---|---|
| Testanzahl | `python3 -m unittest discover -s tests` | 818 Tests, alle grün; 49,2 s |
| Eval-Raten | `python3 -m proofboy eval --set tests/data/pruefset.json` | Erkennung 25/25 = 100 %, Falschbestätigung 0/25 = 0 %, echte Meldungen 26/26 = 100 %, unprüfbar 22/96 = 22,9 %; Schwellen erfüllt; Laufzeit 1,6 s |
| [HALT] BB(5)-Champion | `python3 -m proofboy check --report halt-champion.md` | CONFIRMED nach 47.176.870 Schritten, Score 4098; 5,4 s |
| [CYCLE] Beweis | `python3 -m proofboy check --report cycle-report.md` | CONFIRMED mit Nicht-Halte-Beweis; 0,04 s |
| [SEARCHED] Lauf | `python3 -m proofboy check --report searched-report.md` | CONFIRMED für den begrenzten Lauf (ohne Nicht-Halte-Anspruch); 0,05 s |
| [COMPUTE] Zertifikat | `python3 -m proofboy check --report compute-report.md --repo /tmp/opencode/report-clone` | CONFIRMED, sandboxed, SHA-256 stimmt (27 Bytes); 0,2 s |
| Beispiel-Lauf | `make check` | 4 bestätigt / 0 widerlegt / 2 unprüfbar, Exit 0; 16,1 s (inkl. 162 Tests im Sandkasten) |
| Section-Lauf (live) | `python3 -m proofboy check --section yesloop-proofboy-flaky-fix --project /home/carsten/projects/proofboy --repo /home/carsten/projects/.tmp-proofboy/report-clone --base 0f14154` | 3/0/2, Exit 0; mit `--strict` Exit 4 |
| Gegenbeispiel | `python3 -m proofboy check --report halt-wrong.md` | REFUTED, Exit 1 |
| Schur-Selbstprüfung | `python3 -m proofboy check --report yesdocs/schur/README.md --strict` | 6× CONFIRMED, Exit 0; 0,05 s |
| MERGE-Demo | `python3 -m proofboy check --report merge-report.md --repo .` | CONFIRMED: `b85de127e82e` ist der Merge von `yesloop/proofboy-p14-merge-artifact` (Tip-Parent `3e44f857b72a`, Master-Parent `27387fe35308`) |
| ARTIFACT-Demo | `python3 -m proofboy check --report artifact-report.md --repo .` | CONFIRMED: `good.txt`, 5 Bytes, Digest stimmt |
| Retrospektives Audit | `check --section …` über die 14 Worker-Sections (Abschnitt 6) | 21 bestätigt / 0 widerlegt / 55 unprüfbar; kein DONE-Bericht widerlegt |
| Merge-Kette | `git log --oneline --merges master` | 21 Merges (P1–P15, Flaky-Fix; dazu fünf Merges außerhalb der Prüfer-Kette) |

### Belegausgaben

**Testanzahl** — `python3 -m unittest discover -s tests` (im Klon außerhalb von `/tmp`):

```
Ran 818 tests in 49.171s

OK
```

Warum außerhalb von `/tmp`: Der msheet-Witness-Sandkasten (`proofboy/msheet/witnesses.py`, `_sandbox_prefix`) mountet `--tmpfs /tmp`; ein Klon unter `/tmp` verliert dadurch im Sandkasten seine eigene Datei `proofboy/msheet/_pyexec.py`, und `test_msheet_witnesses.test_sandboxed_run` schlägt fehl (UNVERIFIABLE statt CONFIRMED). Im 18:35-Durchgang reproduziert und beidseitig gegengeprüft (im Original-Repo läuft der Test grün, in der /tmp-Variante nicht); der neue Klon liegt deshalb außerhalb von `/tmp`, dort läuft die volle Suite grün.

**Eval-Raten** — `python3 -m proofboy eval --set tests/data/pruefset.json` (Schlusszeilen; Eingabe ist das eingecheckte Prüfset aus 51 Meldungen: 26 ehrliche, 25 auf bekannte Weise falsche):

```
Erkennungsrate:            25/25 = 100.0%
Falschbestaetigungsrate:   0/25 = 0.0%
Bestaetigungsrate (echt):  26/26 = 100.0%
Unpruefbar-Quote:          22/96 = 22.9%
Schwellen: Erkennung >= 90%, echte >= 90%, falsche == 0% -> erfuellt
Erwartungen verfehlt: 0
Ergebnis: OK
```

**Schur-Selbstprüfung** — `python3 -m proofboy check --report yesdocs/schur/README.md --strict` (Auszug; erste, dritte und letzte der sechs Marker):

```
coloring  CONFIRMED     all 0 triples x + y = z with x <= y and x + y <= 1 are checked: no monochromatic solution in the 1-coloring of 1..1; this certificates the lower bound S(1) >= 1 only -- it does not prove equality and says nothing about the upper bound
coloring  CONFIRMED     all 42 triples x + y = z with x <= y and x + y <= 13 are checked: no monochromatic solution in the 3-coloring of 1..13; this certificates the lower bound S(3) >= 13 only -- it does not prove equality and says nothing about the upper bound
coloring  CONFIRMED     all 6400 triples x + y = z with x <= y and x + y <= 160 are checked: no monochromatic solution in the 5-coloring of 1..160; this certificates the lower bound S(5) >= 160 only -- it does not prove equality and says nothing about the upper bound

summary: CONFIRMED: 6, REFUTED: 0, UNVERIFIABLE: 0
```

Exit-Code 0. Die übrigen drei Zeilen (S(2) >= 4, S(4) >= 44 und ein zweiter, gleichlautender S(4)-Eintrag) verlaufen gleichförmig.

**MERGE- und ARTIFACT-Demo** — zwei kleine Meldungen im Klon (`merge-report.md`: `[COMMIT: b85de127…] [MERGE: yesloop/proofboy-p14-merge-artifact]`; `artifact-report.md`: `[ARTIFACT: good.txt -> 106675dc…]` für die 5-Byte-Datei `good.txt`), dann:

```
$ python3 -m proofboy check --report merge-report.md --repo .
commit_exists  CONFIRMED     commit b85de127e82e40e67e1d7b03b9cdcafd548e6ab2 resolves to b85de127e82e40e67e1d7b03b9cdcafd548e6ab2
merge          CONFIRMED     b85de127e82e is a merge of 'yesloop/proofboy-p14-merge-artifact': parent 3e44f857b72a is its tip and parent 27387fe35308 lies on origin/master

summary: CONFIRMED: 2, REFUTED: 0, UNVERIFIABLE: 0

$ python3 -m proofboy check --report artifact-report.md --repo .
artifact  CONFIRMED     good.txt has the claimed sha256 (5 bytes)

summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0
```

Beide Exit-Codes 0.

**BB(5)-Champion** — Eingabe `[HALT: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 47176870] [SCORE: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 4098]`, dann `check --report`:

```
halt  CONFIRMED     the machine halted after 47176870 steps with score 4098
    cmd: simulate 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA for at most 47176870 steps
    out: halts=True steps=47176870 score=4098

summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0
```

**Übersetzter Zyklus** — Eingabe `[CYCLE: 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC -> 6,16,2]` (die Maschine 44394115 aus der bbchallenge-Wiki):

```
cycle  CONFIRMED     the configuration at step 16 equals the configuration at step 6 translated by 2 on every cell the machine can still reach (it never goes more than 2 cells left of the head at step 6); therefore by determinism the machine never halts
    cmd: simulate 1RB0RE_0LC1RC_0RD1LA_1LE---_1LB1RC up to 16 steps and compare the configurations at steps 6 and 16
    out: halts=False steps=16 score=2

summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0
```

**Begrenzter Suchlauf** — Eingabe `[SEARCHED: 1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE -> 1000]`:

```
searched  CONFIRMED     a bounded search of 1000 steps found no halt; this does not prove that the machine never halts
    cmd: simulate 1RB1RA_1RC1RZ_1LD0RF_1RA0LE_0LD1RC_1RA0RE for at most 1000 steps
    out: halts=False steps=1000 score=38

summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0
```

**Rechenzertifikat** — Eingabe `[COMMIT: 47301fc194ad689cf01edc0dd8642dd397c4f9b6]` plus `[COMPUTE: python3 -m proofboy.turing 1RB1RZ_0LA0LA 3 -> fcc2762419d8f4f3a1b1129170e13837c21722505ad8a6f5b40d9164cb7c92df]`, dann `check --report … --repo …`:

```
commit_exists  CONFIRMED     commit 47301fc194ad689cf01edc0dd8642dd397c4f9b6 resolves to 47301fc194ad689cf01edc0dd8642dd397c4f9b6
compute        CONFIRMED     sha256 of stdout matches the claimed digest (exit 0, 27 bytes) (sandboxed with bwrap)
    cmd: git clone --no-hardlinks <repo> <checkout> && git checkout 47301fc194ad689cf01edc0dd8642dd397c4f9b6 && bwrap --die-with-parent --ro-bind / / --dev /dev --proc /proc --tmpfs /run --bind <checkout> <checkout> --unshare-net --unshare-pid --unshare-uts --chdir <checkout> -- python3 -m proofboy.turing 1RB1RZ_0LA0LA 3
    out: sha256=fcc2762419d8f4f3a1b1129170e13837c21722505ad8a6f5b40d9164cb7c92df bytes=27 exit=0

summary: CONFIRMED: 2, REFUTED: 0, UNVERIFIABLE: 0
```

**Gegenbeispiel (falsche Schrittzahl)** — Eingabe `[HALT: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 5]`:

```
halt  REFUTED       the machine did not halt within the claimed 5 steps; it cannot halt exactly at step 5
    cmd: simulate 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA for at most 5 steps
    out: halts=False steps=5 score=4

summary: CONFIRMED: 0, REFUTED: 1, UNVERIFIABLE: 0
```

Exit 1.

**Merge-Kette** — `git log --oneline --merges master` (Betreffs gekürzt, neueste zuerst):

```
ec5b4ab merge: V1.1-Demo-Artefakt — B3-0005 Arm D …
5b05de7 merge: V13 Härte-Runde — Sets v0.3 … 744 Tests
7edf993 merge: P15 placeholder lines are not claims … 781 tests
b85de12 merge: P14 MERGE + ARTIFACT checkers … 724 tests
27387fe merge: V12 Rückkanal-Runde — Repair-Loop, Sets v0.2, 176 Läufe …
dd0767c merge: P13 [COLORING] Schur colorings — lower-bound-only wording … 670 tests
3025c29 merge: P12 [IDENT] parameterized identities … 494 tests
b8fa034 merge: V1.1 Denk-Sprache — msheet-Engine (Parser/Zeugen/Runner) … 568 tests
28609e0 merge: P11 Erdos-Straus exhaustive-witness experiment via [COMPUTE] … 454 tests
c6ba55a merge: P10 translated-cycler certificates ([CYCLE]) … 443 tests
8766e37 merge: P9 compute certificates ([COMPUTE]) + honest bounded search ([SEARCHED]) … 377 tests
ff9b775 merge: deepseek-math-notation research wiki … (fremdbeauftragt)
14dec7c merge: P8 --repo only when a claim kind needs it … 291 tests
4fd2b30 merge: P7 testable halting claims ([HALT]/[SCORE]) … 278 tests
6d82c4b merge: P6 test-command sandbox via bwrap … 214 tests
b8f437f merge: P5 --strict exit-code gap closed … 193 tests
5068e5f merge: flaky timeout-kill test fix …
0f14154 merge: P4 CLI integration … 184 tests
ead3dc7 merge: P3 eval harness … 162 tests
7c7392c merge: P1 Pruefer core … 111 tests
bb234fe merge: P2 research wiki … (106 Quellen)
```

Die Eingabedateien der Beispiele liegen in den Wegwerf-Klonen: `halt-champion.md`, `cycle-report.md`, `searched-report.md`, `compute-report.md`, `halt-wrong.md` im Klon unter `/tmp/opencode/report-clone/`; `merge-report.md`, `artifact-report.md` und `good.txt` im Klon unter `/home/carsten/projects/.tmp-proofboy/report-clone/`.

### Erdős–Straus-Landkarte (P11/P12)

Die Auswertung `yesdocs/erdos-straus/README.md` ordnet Progressionsklassen von `n` drei Zustände zu:

1. **Für alle `n` der Progression verifiziert:** sechs Identitäten stehen als `[IDENT]`-Marker in der Datei und werden beim Nachrechnen exakt als Rationalfunktionen in `t` geprüft — alle geraden `n` (`n = 2t`) sowie alle Vielfachen von 3, 5, 7, 11 und 13.
2. **Endlich belegt:** das P11-Artefakt deckt `n <= 1.000.000` mit expliziten Zeugen ab — endlich verifiziert, kein Beweis darüber hinaus.
3. **Keine Parametrisierung bekannt:** die 840-Ausnahmeklassen (siehe Abschnitt 8).

Kein Zustand davon ist ein Beweis der Vermutung; das Urteil sagt es selbst (`one progression, not all of them: this is not a proof of the conjecture`).

Selbstprüfung (Beleg vom 18:35-Durchgang auf `3025c29`; im 22:52-Durchgang auf `b85de12` erneut gelaufen: Exit 0, 0,05 s):

```
$ python3 -m proofboy check --report yesdocs/erdos-straus/README.md --strict
ident  CONFIRMED     4/n(t) = 1/a(t) + 1/b(t) + 1/c(t) holds as a rational identity in t for every t >= 1 with n = 2t, a = t, b = 2t, c = 2t; every integer t >= 1 has n >= 2 and positive denominators, so the progression n = 2t is covered for every parameter -- one progression, not all of them: this is not a proof of the conjecture
    cmd: expand 1/(t) + 1/(2t) + 1/(2t) - 4/(2t) as one rational function in t
    out: numerator=0
    [... die fünf weiteren Marker (n = 3t, 5t, 7t, 11t, 13t) verlaufen gleichförmig: CONFIRMED, numerator=0 ...]

summary: CONFIRMED: 6, REFUTED: 0, UNVERIFIABLE: 0
```

Exit-Code 0. Die P11-Zeile zusätzlich selbst nachgerechnet:

```
$ python3 -m proofboy.experiments.erdos_straus 1000000 > es.out   # 12,9 s
$ sha256sum es.out
e5b68dd1818d89f2c66d0e7b5a68bf906dbe7adc77c64dba015bf27058a4f89d  es.out
$ wc -c es.out
46906788 es.out
$ tail -1 es.out
ok 1000000 999999
```

Der Hash stimmt mit dem in der README und im Merge `28609e0` gepinnten Wert überein.

## 3. Wie man es benutzt

Fünf Beispiele mit echter Ausgabe, alle im Klon ausgeführt. Exit-Code jeweils dahinter.

**Beispiel 1 — Meldedatei prüfen, ohne Repository (HALT):**

```
$ cat halt-champion.md
**send_to payload:** `[DONE]`

[HALT: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 47176870] [SCORE: 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA -> 4098]

$ python3 -m proofboy check --report halt-champion.md
halt  CONFIRMED     the machine halted after 47176870 steps with score 4098
    cmd: simulate 1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA for at most 47176870 steps
    out: halts=True steps=47176870 score=4098

summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0
$ echo $?
0
```

**Beispiel 2 — Rechenzertifikat im Sandkasten (COMPUTE; braucht `--repo`):**

```
$ python3 -m proofboy check --report compute-report.md --repo /tmp/opencode/report-clone
compute        CONFIRMED     sha256 of stdout matches the claimed digest (exit 0, 27 bytes) (sandboxed with bwrap)
    cmd: git clone --no-hardlinks <repo> <checkout> && git checkout 47301fc… && bwrap … -- python3 -m proofboy.turing 1RB1RZ_0LA0LA 3
    out: sha256=fcc2762419d8f4f3a1b1129170e13837c21722505ad8a6f5b40d9164cb7c92df bytes=27 exit=0

summary: CONFIRMED: 2, REFUTED: 0, UNVERIFIABLE: 0
$ echo $?
0
```

**Beispiel 3 — eine echte Agenten-Section prüfen (live, nur lesend):**

```
$ python3 -m proofboy check --section yesloop-proofboy-flaky-fix --project /home/carsten/projects/proofboy --repo /home/carsten/projects/.tmp-proofboy/report-clone --base 0f14154
diff_scope     CONFIRMED     the 1 changed files match the planned scope exactly
    out: tests/test_checks.py
deploy         UNVERIFIABLE  no checker registered for claim kind 'deploy'
commit_exists  CONFIRMED     commit d734599 resolves to d73459998e371fcef6960264b02c8a34be946235
branch_pushed  CONFIRMED     d734599… is reachable from yesloop/proofboy-flaky-fix on origin
merge          UNVERIFIABLE  the claim names no branch to check: 'no'

summary: CONFIRMED: 3, REFUTED: 0, UNVERIFIABLE: 2
```

Ohne `--strict` ist der Exit-Code 0 (es gibt Bestätigungen, keine Widerlegung); mit `--strict` ist er 4, weil unprüfbare Behauptungen dabei sind. Ein Merge-Gate fährt `--strict`: Exit 0 heißt dann „jede Behauptung bestätigt“; in der Praxis der Nacht wurden `deploy` und (bis P14) `merge` als bekannt-nicht-prüfbar behandelt. Seit P14 hat `merge` einen Checker — hier bleibt die Zeile nur deshalb `UNVERIFIABLE`, weil die Meldung mit `[MERGE: no]` keinen Branch nennt (ein Statuswert, keine Branch).

**Beispiel 4 — `make check` (Beispiel-Report im Repo):**

```
$ make check
python3 -m proofboy check --report tests/data/beispiel-report.md --repo . --base 7c7392c…
deploy         UNVERIFIABLE  no checker registered for claim kind 'deploy'
commit_exists  CONFIRMED     commit 88b57ae… resolves to …
branch_pushed  CONFIRMED     88b57ae… is reachable from yesloop/proofboy-p3-eval on origin
merge          UNVERIFIABLE  the claim names no branch to check: 'no'
diff_scope     CONFIRMED     the 7 changed files match the planned scope exactly
tests_green    CONFIRMED     'python3 -m unittest discover -s tests' exited 0 as claimed (sandboxed with bwrap)
    out: Ran 162 tests in 14.135s
    out: OK

summary: CONFIRMED: 4, REFUTED: 0, UNVERIFIABLE: 2
$ echo $?
0
```

Hinweis zu den Beispielen: Diese Läufe liefen im Klon, dessen `origin` auf das lokale Original zeigt; deshalb ist `branch_pushed` dort prüfbar. Im Original ohne Remote bleibt `branch_pushed` in jedem Lauf `UNVERIFIABLE`. Beispiel 5 ist neu seit P14 (`merge` und `artifact` sind die jüngsten Behauptungstypen).

**Beispiel 5 — Merge-Struktur und Datei-Digest prüfen (MERGE/ARTIFACT, seit P14):**

```
$ cat merge-report.md
**send_to payload:** `[DONE]`

[COMMIT: b85de127e82e40e67e1d7b03b9cdcafd548e6ab2] [MERGE: yesloop/proofboy-p14-merge-artifact]

$ python3 -m proofboy check --report merge-report.md --repo .
commit_exists  CONFIRMED     commit b85de127e82e40e67e1d7b03b9cdcafd548e6ab2 resolves to b85de127e82e40e67e1d7b03b9cdcafd548e6ab2
merge          CONFIRMED     b85de127e82e is a merge of 'yesloop/proofboy-p14-merge-artifact': parent 3e44f857b72a is its tip and parent 27387fe35308 lies on origin/master

summary: CONFIRMED: 2, REFUTED: 0, UNVERIFIABLE: 0
$ echo $?
0
```

```
$ cat artifact-report.md
**send_to payload:** `[DONE]`

[ARTIFACT: good.txt -> 106675dc1490d5cdd6d1f0410731316ce93fc964c6cf6726e2b0d53e19688feb]

$ python3 -m proofboy check --report artifact-report.md --repo .
artifact  CONFIRMED     good.txt has the claimed sha256 (5 bytes)

summary: CONFIRMED: 1, REFUTED: 0, UNVERIFIABLE: 0
$ echo $?
0
```

Exit-Codes insgesamt: 0 = mindestens eine Behauptung bestätigt, keine widerlegt; 1 = mindestens eine widerlegt; 2 = Fehler (Aufruf, Eingabe); 3 = nichts bestätigt; 4 = nur mit `--strict`: bestätigt, aber mindestens eine unprüfbar.

## 4. Was es nicht kann

- **Deploy hat keinen Checker — absichtlich.** `[DEPLOY: ...]` bleibt dauerhaft `UNVERIFIABLE`: „Deploy“ hat keinen generischen, nachrechenbaren Sinn; die ehrliche, prüfbare Form ist das Artefakt (`[ARTIFACT: <pfad> -> <sha256>]`). Merge ist seit P14 prüfbar — geprüft wird die Struktur (genau zwei Parents, einer ist der Tip des genannten Branches, der andere liegt auf der Zielbranch), nicht die Absicht.
- **Schur-Zertifikate sind untere Schranken.** `[COLORING]` bestätigt „S(k) >= n“ für ein endliches `n` — nie die Gleichheit; S(1..5) sind als untere Schranken selbst geprüft. Die Gleichheit bei S(5) (obere Schranke zitiert, Exoo via OEIS) und die Schranken S(6) >= 536 (Fredrickson & Sweet 2000) und S(7) >= 1696 (Rowley 2021) stehen als Quellenangaben ohne eigenes Zertifikat in der Karte.
- **Die Merge-Prüfung ist Struktur, kein Absichts-Beweis — und nur so gut wie das Repo.** Ein Merge, der die Zielbranch nie erreichte, kann bestätigt werden; ein gelöschter Branch macht die Behauptung unprüfbar. Nach einem HIGH-Befund der Reviews läuft jeder Git-Befehl im geprüften Repo mit `core.commitGraph=false` und liest den Objekt-Store direkt (eine gefälschte Commit-Graph hatte ein falsches CONFIRMED erzeugt; das Repro endet inzwischen `REFUTED`). Wer das Repo kontrolliert, kontrolliert weiterhin die Objekte.
- **„Branch gepusht“ ist ohne Remote nicht prüfbar.** Das Repo hat kein Remote (`git remote -v` ist leer); die Arbeitszweige liegen nur lokal. Gegen das Original bleibt `branch_pushed` deshalb `UNVERIFIABLE`.
- **Eine endliche Suche beweist kein Nicht-Halten.** `[SEARCHED]` bestätigt nur: der Lauf lief N Schritte ohne Halt. Der Urteilstext sagt das ausdrücklich („does not prove that the machine never halts“), README und SPEC dokumentieren es, und ein Test fixiert den Wortlaut.
- **Ein begrenzter Lauf ist eine Aussage über den Lauf, nicht über die Maschine.** Das ist Doktrin, nicht Implementierungsdetail.
- **Falsifikations-Asymmetrie.** Ein Gegenbeispiel widerlegt sicher; die Abwesenheit eines Gegenbeispiels beweist nichts. Halten braucht einen Zeugen (die exakte Schrittzahl), Nicht-Halten braucht ein Zertifikat (`[CYCLE]` für übersetzte Zyklen). Ohne Zeuge oder Zertifikat bleibt es unentschieden.
- **`[CYCLE]` ist kein allgemeiner Nicht-Halte-Prüfer.** Er rechnet genau das vorgelegte Zertifikat nach; er sucht keine Zertifikate und entscheidet nicht, ob eine Maschine überhaupt einen übersetzten Zyklus besitzt.
- **Der Sandkasten ist keine vollständige Isolationsgrenze.** Er begrenzt Schreiben, IP-Netz und Prozesssicht; die Wurzel bleibt lesbar, und Lücken im Kernel oder in bwrap fängt er nicht ab. Wer den `PATH` des Aufrufers kontrolliert, kontrolliert den Prüfer.
- **„Tests grün“ bleibt eine Aussage des Repos.** Das Urteil verlangt positive Evidenz in der Ausgabe, aber der geprüfte Commit bringt seinen eigenen Code mit: Wer den Commit kontrolliert, kontrolliert die Ausgabe. Dasselbe gilt für COMPUTE — der Hash belegt die Bytes, nicht ihre Bedeutung.
- **Eine falsche Bestätigung ist der schwerste Fehler.** So steht es in der SPEC: im Zweifel `UNVERIFIABLE`, nie `CONFIRMED`. Die Eval-Rate von 0 % falscher Bestätigungen ist der Wert, der zählt.

## 5. Chronik

Merges auf master, verifiziert per `git log --oneline --merges master`; Testzahlen aus den Merge-Nachrichten (Zweigstände; Master-Zahl in Abschnitt 2); Zeiten aus dem Protokoll und aus den Commit-Zeitstempeln. Die Liste enthält fünf Merges außerhalb der Prüfer-Kette (separat beauftragte Spur; nicht Teil dieses Berichts).

- **P0 Bootstrap** (kein Merge; Commits `dd29a37` und Retarget `91bd125`): Gerüst (README, SPEC, PLAN), Conveyor-Section, Suborchestrator-Briefing, Watchdog.
- **P2 Research-Wiki** — Merge `bb234fe` (00:41): belegte Recherche zur unabhängigen Verifikation (INDEX mit Mermaid, Bibliography; 106 Quellen), Branch `yesresearch/pruefer`.
- **P1 Prüfer-Kern** — Merge `7c7392c` (01:55): Behauptungs-Checker (Commit, Branch, Diff-Scope, Tests) plus CLI/JSON; 111 Tests, 6 Review-Runden.
- **P3 Eval-Harness** — Merge `ead3dc7` (02:52): Prüfset plus Qualitätsmetriken; 162 Tests, 3 Review-Runden.
- **P4 CLI/Integration/Doku** — Merge `0f14154` (03:29): `check --section` liest YesMem-Sections, Makefile, README; 184 Tests.
- **Flaky-Fix** — Merge `5068e5f` (04:08): der unter Last flakige Timeout-Test wurde deterministisch (eindeutiger Marker, exaktes pgrep/pkill, begrenzter Poll); vorher 4/6 Runden FAIL unter zwei parallelen Läufen, danach 12/12 OK.
- **P5 --strict** — Merge `b8f437f` (05:06): schließt die Exit-Code-Lücke (ein Bericht mit nie geprüfter Testbehauptung konnte Exit 0 liefern); Exit 4 für unprüfbare Behauptungen; 193 Tests.
- **P6 Sandkasten** — Merge `6d82c4b` (09:25): Testkommandos laufen via bwrap (read-only Wurzel, eigener Netz-/PID-/UTS-Namensraum; `--sandbox=require` fällt hart ohne Sandkasten); 214 Tests.
- **P7 Halten** — Merge `4fd2b30` (10:45): `[HALT]`/`[SCORE]` mit eigenem Turingmaschinen-Simulator und Claim-Typ-Registry (neue Typen ohne Parser-/CLI-Änderung); 278 Tests.
- **P8 Repo-optional** — Merge `14dec7c` (11:26): `--repo` nur noch Pflicht, wenn ein vorkommender Behauptungstyp ein Repository deklariert; 291 Tests.
- **P9 Rechenzertifikate und ehrlicher Suchlauf** — Merge `8766e37` (13:38): `[COMPUTE]` (SHA-256 der Ausgabe, Sandkasten, gepinnter Commit) und `[SEARCHED]` (begrenzter Lauf, ausdrücklich kein Nicht-Halte-Beweis); Antihydra-Artefakt mit 10⁷ Schritten; 377 Tests.
- **P10 Übersetzte Zyklen** — Merge `c6ba55a` (15:28): `[CYCLE]` als endlicher Nicht-Halte-Beweis; reales Wiki-Artefakt (Maschine 44394115, Zertifikat 6,16,2); 443 Tests.
- **P11 Erdős–Straus-Experiment** — Merge `28609e0` (17:18): `[COMPUTE]`-Experiment, das deterministisch für alle `n <= 10^6` explizite Zeugen ausrechnet; stdout an Commit `07c166f` gepinnt (46.906.788 Bytes, sha256 `e5b68dd1…`), ehrliche No-Proof-Formulierung; 454 Tests.
- **P12 `[IDENT]`** — Merge `3025c29` (18:01): parametrisierte Identitäten (Erdős–Straus-Progressionszertifikate), exakt als Rationalfunktionen in `t` geprüft; selbstprüfende Landkarte `yesdocs/erdos-straus/README.md`; 494 Tests (Zweig-Suite; kombinierter Master: siehe Abschnitt 2).
- **P13 Schur-Färbungen** — Merge `dd0767c` (19:15): neuer, repofreier Typ `[COLORING: k=<k>; <digits>]` als kompaktes Zertifikat für untere Schranken (alle Tripel `x+y=z` auf x <= y und x+y <= N aufgezählt, erste Verletzung benannt, Wortlaut nur „untere Schranke, kein Beweis der Gleichheit“); deterministischer MRV-Sucher (`proofboy/experiments/schur.py`) findet S(1..4) = 1, 4, 13, 44 selbst; selbstprüfende Karte `yesdocs/schur/README.md` (selbst geprüft: 6× CONFIRMED, Exit 0); 670 Tests (Zweig).
- **P14 `[MERGE]` + `[ARTIFACT]`** — Merge `b85de12` (20:48): Merge-Struktur prüfbar, gebunden an den `[COMMIT]`-Marker (genau zwei Parents; einer ist der Tip des genannten Branches, der andere liegt auf der Zielbranch; Widerlegung nennt die echten Parents). `[ARTIFACT: <pfad> -> <sha256>]` prüft Datei-Digests mit realpath-Konfinierung, Streaming und 256-MiB-Limit. Ein HIGH-Security-Befund (gefälschte Commit-Graph → mögliches falsches CONFIRMED) wurde vor dem Merge geschlossen (`3e44f85`: `core.commitGraph=false`, direkter Objekt-Store-Zugriff; das Repro endet `REFUTED`). DEPLOY bleibt absichtlich ohne Checker. 724 Tests (Zweig).
- **P15 Platzhalter-Regel** — Merge `7edf993` (23:01): `<...>`-Platzhalter, `TODO`- und Ellipsen-Werte zählen über alle Parser-Flächen nicht mehr als Behauptungen (ein gemeinsamer Helfer; Grenzfall `go test ./...` bleibt konservativ Claim); Audit-Effekt 77 → 54 unprüfbare Marker bei unverändertem C/R; 781 Tests (Zweig).
- **Nicht Teil dieses Berichts:** Auf master liegen außerdem Merges einer separat beauftragten Spur (eigene Zweige, `yesdocs/…`); sie werden hier bewusst nicht beschrieben.
- **Offene Prüfer-Arbeiten: keine.** P1–P15 sind gemergt.

## 6. Retrospektives Audit

Die P15-Regel macht die Meldungen der Nacht heute fair messbar (Platzhalter zählen nicht mehr als Behauptungen). Über die 14 Worker-Sections (P1, P3–P15; P2 war der Research-Lauf) ergeben die DONE-Berichte zusammen **21 bestätigte, 0 widerlegte und 55 unprüfbare Behauptungen** — kein DONE-Bericht der Nacht wurde widerlegt. Selbst gemessen am 12.09.2026 um 23:04 auf Master `7edf993` (Klon außerhalb von `/tmp`); die Prüfer-Dateien sind seither unverändert, die Zahlen gelten weiter.

Das eingecheckte Skript `python3 yesdocs/audit/audit_sections.py` liest die Sections P1 sowie P3–P14 mit ihren dokumentierten Baselines (p1 ohne Baseline) und meldet `TOTAL 19 1 54` plus die Exit-Matrix; die Matrix pinnt, dass echte Werte ihre Exit-Codes behalten (`strict-mixed-real` 0/4) und nur Platzhalter-Zeilen die gewollte Ausnahme sind (`strict-mixed-placeholder` 0/0). Sein einzelnes `REFUTED` gehört zur p5-Section: Der Parser liest deren Prosa-Zeile „the 6 files above“ als `diff_scope`, und die alte Baseline umspannt heute alle späteren Phasen (`planned but unchanged: the 6 files above`). Vor und nach P15 identisch; läuft dieselbe Zeile ohne Baseline, ist die Gesamtzahl 21/0/55.

Die Unprüfbaren sind fast vollständig Systemgrenzen: `merge` ohne Branch-Nennung (18), `deploy` (12, absichtlich ohne Checker), `branch_pushed` (11, kein Remote), `diff_scope` ohne passende Baseline (8), dazu einzelne Sonderfälle (`commit_exists` auf nach Rebases nicht mehr auflösbare Hashes, 2; `halt` 2; `compute` 1; `artifact` 1).

Wiederholbar: Die 14-Section-Zahl entsteht mit denselben Aufrufen wie im Skript (Baseline-Zuordnung im `SECTIONS`-Dict; zusätzlich P15 mit `--base b85de12`), für p5 ohne `--base`; ganz ohne Baselines ergibt derselbe Lauf 16 bestätigt / 0 widerlegt / 60 unprüfbar.

## 7. Infrastruktur

Die Nacht lief nicht als einzelner Agent, sondern als Kette von Agenten über einen gemeinsamen Zustand.

- **Suborchestrator.** Ein langlaufender Agent koordinierte alles: Conveyor und PLAN lesen, Worker spawnen (ein Worker pro Phase, eigener Git-Worktree), DONE-Berichte prüfen, erst dann mergen, LOG schreiben, 600 s schlafen, wiederholen. Worker mergen nie selbst; nur der Suborchestrator mergt nach master. Aktuell läuft Instanz `agent-20260912-05`; eine zweite Instanz („Standby B“) bleibt passiv und übernimmt nur bei Ausfall.
- **Watchdog.** Scheduler-Job `proofboy-suborch-watcher`, cron `*/30` (letzter Lauf laut Scheduler 13.09., 09:00). Er prüft, ob der Suborchestrator lebt, und spawnt sonst einen neuen — so entstand die Nachmittags-Instanz um 08:37.
- **Conveyor.** Scratchpad-Section `proofboy-conveyor` (Projekt `/home/carsten/projects/proofboy`) ist die Statusdatei: harte Verbote (kein Deploy, kein sudo, kein force-push, kein Schreiben in `~/.claude/skills` oder `~/.claude/yesmem`), Spawn-Regeln, ein LOG mit Zeitstempeln. Nach einer Panne um ~04:40 (ein Auftrag lag ~2,5 h unbemerkt in der Section) gilt: jeder Check liest den Tail der Section.
- **Resume-Protokoll nach Daemon-Neustart.** Um 00:27:22 wurde der YesMem-Daemon neu gestartet und tötete die komplette Flotte. Seitdem: nicht der Registry glauben, sondern dem Worktree (`git -C <worktree> log --oneline -1`); Worker mit Resume-Auftrag neu spawnen und ab ihrem HEAD weiterarbeiten, kein Neuanfang. P1 wurde so ab `e4db275` fortgesetzt und 01:55 fertig.
- **Bekannte Fehler der Agent-Registry** (im Protokoll mehrfach belegt; Punkt 1 habe ich beim Schreiben und bei allen Nachträgen (18:35, 22:52, 13.09. 09:14) live gegen die Registry und per `ps` geprüft):
  1. Zeilen melden „stopped“ für lebende oder aktive Prozesse. Beispiel jetzt (13.09., 09:14): `agent-20260911-08` steht seit dem 12.09. um 00:04 auf `stopped`, trägt aber Aktivität bis zum 13.09. um 05:49 Uhr. Beim ersten Durchgang (15:59) war der gegenteilige Fall belegt: Die Zeile von `agent-20260911-10` meldete „stopped“/`orphaned`, während der zugehörige Prozess (PID 343796) nachweislich noch lief (15 h 30 min Laufzeit; inzwischen beendet). Auch Idle-Fehlalarme für arbeitende Worker kamen mehrfach vor.
  2. Nach einem Daemon-Neustart werden Agent-IDs wiederverwendet bzw. neu vergeben; Session-IDs in Registry, Proxy und Selbstbericht können auseinanderlaufen. Konsequenz: Agenten strikt über den Section-Namen tracken, nie über die ID.
  3. Orphan-Reaping: Ein Agent wird getötet, wenn der Agent stirbt, über dessen Session er gespawnt wurde („orphaned: parent … dead“). Ausweg ist ein neutraler `caller_session` (`opencode:ses_…_neutral`); der Watchdog verlangt ihn ausdrücklich, „otherwise the agent is orphan-reaped within minutes“. Dieser Report-Lauf selbst wurde mit neutralem Caller gestartet.
  4. Nebenwirkung des Watchdogs: Bei lügender Registry kann er eine Doppel-Instanz erzeugen (passiert um 00:36). Etablierte Regel: Die Registry-`running`-Instanz handelt, alle anderen sind passiv.
- **Praktischer Zwischenfall (aus dem Protokoll, nicht selbst nachgestellt):** Ein Worker pausierte um ~22:02 mit hängendem Subagenten-Aufruf (Idle-Eskalation + hängendes `task()`); Relays an ihn queuten nur; die Rettung war ein PERM-KICK (Auto-Unpause) um 22:28. Lehre: pausiert + hängender Subagent = Deadlock; Abhilfe ist Unpause/ESC, nicht weiteres Zureden.
- **Merge-Gate.** Vor jedem Merge verifizierte der Suborchestrator den DONE-Bericht am sauberen Checkout (eigener Testlauf) und ließ zusätzlich den Prüfer selbst auf den echten Worker-Bericht laufen (Dogfood, `--strict`): „das Werkzeug, das diese Nacht gebaut wurde, entscheidet über die Merges derselben Nacht“. Ein `REFUTED` blockierte hart; `UNVERIFIABLE` blockierte nur bei Kernbehauptungen (Commit, Tests, Diff-Scope). Die Standby-Instanz auditierte jeden Merge unabhängig nach.

## 8. Offene Punkte

- **Kein Remote.** `git remote -v` ist leer; es wurde nichts gepusht. `branch_pushed` bleibt damit grundsätzlich unprüfbar, solange kein Remote eingerichtet ist. Die Arbeitszweige (`yesloop/…`, `yesresearch/…`) liegen lokal und sind bewusst nicht aufgeräumt.
- **Kein Checker nur noch für Deploy (absichtlich).** Merge ist seit P14 prüfbar; `[DEPLOY]` bleibt bewusst dauerhaft unprüfbar (ehrliche Form: `[ARTIFACT: <pfad> -> <sha256>]`). Im Merge-Gate bis P13 galten `deploy` und `merge` als bekannt-nicht-prüfbar.
- **Kein Budget pro Report.** Viele Behauptungen in einer Meldung summieren sich (eine HALT-Prüfung am Limit kostet rund 5 s). Das war eine bewusste, dokumentierte Entscheidung aus den Reviews (P7/P10): die Limits begrenzen einen Lauf, nicht die Meldung.
- **`eval --strict` besteht das ausgelieferte Set absichtlich nicht** — unprüfbare Behauptungen sind Teil des Set-Designs; der Modus ist für Sets gedacht, die vollständig prüfbar sein sollen.
- **Erdős–Straus — was nach P11/P12 offen bleibt.** Offen sind die 840-Ausnahmen `n ≡ 1, 121, 169, 289, 361, 529 (mod 840)` (Stand nach Mordell 1967; kleinste nicht abgedeckte Primzahl `1009`). Mordells Schranke: eine Polynomidentität für `n ≡ r (mod p)` kann nur existieren, wenn `r` kein quadratischer Rest modulo `p` ist — ein vollständiges Überdeckungssystem aus Identitäten gibt es daher nicht (`1 bleibt immer unbedeckt`). Ein `[IDENT]`-CONFIRMED deckt immer nur eine Progression ab, nie die Vermutung. Quellen: Wikipedia (en), `Erdős–Straus conjecture`; L. J. Mordell, Diophantine Equations, Academic Press 1967, S. 287–290 (zitiert nach Wikipedia); E. J. Ionascu, A. Wilson, arXiv:1001.1100, Theorem 1.6.
- **Schur: S(6) offen.** Der exakte Wert von `S(6)` ist unbekannt; die Karte zitiert nur `S(6) >= 536` (Fredrickson & Sweet 2000) als untere Schranke ohne eigenes Zertifikat — ebenso `S(7) >= 1696` (Rowley 2021).
- **Speicher-Skalierung von `erdos_straus` (aus dem P11-Review, nicht selbst nachgestellt).** Der Speicherbedarf wächst linear mit `N` (~74 Bytes pro `n`; `N = 10^6` → ~89 MB Peak). Der COMPUTE-Checker begrenzt nur Zeit (300 s) und stdout (64 MiB), kein Speicherlimit — ein Report mit `N = 10^8` kann den Prüf-Host Richtung OOM treiben. Kandidat: `N`-Obergrenze oder dokumentierter Hinweis in den Grenzen.
- **Dieser Report** wurde am 13.09. um 12:41 auf Wunsch des Nutzers committet; zuvor lag er als ungetrackte Datei vor (Stand 13.09., 09:15; seit dem 18:35-Stand ergänzt um P13–P15, das retrospektive Audit und die neuen Selbstchecks, am Morgen um den Lage-Nachtrag). Außer diesem Commit wurde am Repo nichts geändert, an `~/.claude/yesmem` und an den Skills nichts. Die Wegwerf-Klone (`/tmp/opencode/report-clone`, `/home/carsten/projects/.tmp-proofboy/report-clone`) bleiben als Messorte liegen.

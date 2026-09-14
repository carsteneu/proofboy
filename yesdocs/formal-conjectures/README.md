# formal-conjectures — Katalog-Scan, Shortlist, erster umgrenzter Angriff

Diese Datei dokumentiert die E2-Phase des Yesloop-Auftrags vom 2026-09-13
(„Katalog-Scan, Shortlist, erster umgrenzter Angriff“; nicht Teil der P-Kette).
Gegenstand ist die Sammlung
[formal-conjectures](https://github.com/google-deepmind/formal-conjectures)
(Google DeepMind; Apache-2.0 / CC-BY), geklont nach
`.yesmem/tmp/formal-conjectures` (gitignored, **nicht** vendored) auf Commit
`a2f4a1bb12a28e04a969da78feefac7d1ce49565` (Abruf 2026-09-13).

Ergebnis in einem Satz: Der Katalog ist vollständig statisch erfasst
(1268 Dateien, 1466 offene Statements; `data/scan.json` reproduzierbar), die
Shortlist für unsere Prüfkette sind vier offene Kandidaten der
Busy-Beaver-/Zahlen-Familie, und der erste umgrenzte Angriff liefert
**endliche, maschinell bestätigte Beobachtungen** — keine Lösung einer offenen
Frage.

## 1. Katalog-Scan

**Methode.** Statischer Text-Scan (kein Lean-Build nötig):
`tools/scan_catalog.py` liest jede `.lean`-Datei unter
`FormalConjectures/`, extrahiert je `@[category …]`-Annotation die
Deklaration (Kind, Name, Kategorien, AMS-Zahlen, `answer`-Polarität,
`formal_proof`-Link, Statement-Features) und die Referenz-URLs der Datei.
Das Ergebnis ist **deterministisch** (keine Zeitstempel, keine lokalen Pfade,
sortierte Felder) — eine Wiederholung liefert byte-identische Daten
(`cmp` exit 0; siehe „Reproduktion“ unten). Entwicklung testgetrieben:
`tools/test_scan_catalog.py` (Fixtures + Determinismus + Abgleich gegen den
realen Klon), 12 Tests, grün.

**Kennzahlen** (Commit `a2f4a1b`, gemessen 2026-09-13):

| Kennzahl | Wert |
|---|---|
| .lean-Dateien unter `FormalConjectures/` | 1268 |
| kategorie-annotierte Deklarationen | 5445 |
| `research open` | **1466** |
| `research solved` | 1661 |
| `test` / `textbook` / `API` | 1822 / 175 / **321** |
| `answer(sorry)` auf Statement-Ebene | 901 (davon 895 in `research open`) |
| `answer(True)` / `answer(False)` | 227 / 157 |
| nicht zuordenbare `@[category]`-Vorkommen | 0 |

Methodische Notiz zur `answer(sorry)`-Zahl: Der Rohtext enthält 918
Vorkommen; 17 davon stehen in Prosa/Docstrings (z. B. „recorded here as
`answer(sorry)`“) und sind keine Statement-Nutzungen. Der Scan trennt beide
Fälle (Statement-Bereich endet am ersten `:=`, das nicht zu einem
`let`-Binding im Theorem-Typ gehört); die 17 Prosa-Fälle wurden per
Offset-Abgleich einzeln klassifiziert.

Methodische Notiz zu den Deklarationszahlen: 5446 Rohzeilen tragen eine
`@[`-Annotation mit `category`-Feld (Zählung per
`grep -rE '@\[[^]]*category'`); eine ist eine Docstring-Erwähnung
(`OpenQuantumProblems/23.lean`), bleibt also 5445. Seit der kalten Abnahme
(§6) erfasst der Scan auch geteilte Klammern mit vorangestellten Modifikatoren
(`@[simp, category API, AMS 5]`, 25 Deklarationen — alle `API`, daher
unverändert 1466 offene Statements); vorher fehlten diese 25.

**Sammlungen** (nach offenen Statements):

| Sammlung | Dateien | Deklarationen | open | solved |
|---|---|---|---|---|
| ErdosProblems | 671 | 2097 | **660** | 1089 |
| Wikipedia | 156 | 680 | 264 | 177 |
| OEIS | 227 | 1533 | 208 | 106 |
| GreensOpenProblems | 57 | 241 | 112 | 103 |
| Paper | 30 | 181 | 84 | 36 |
| Arxiv | 30 | 140 | 34 | 46 |
| OpenQuantumProblems | 3 | 123 | 34 | 14 |
| Books | 9 | 32 | 15 | 9 |
| Millennium | 5 | 30 | 12 | 5 |
| Mathoverflow | 13 | 65 | 11 | 14 |
| Other | 7 | 28 | 11 | 15 |
| WrittenOnTheWallII | 49 | 242 | 9 | 39 |
| Kourovka | 5 | 5 | 5 | 0 |
| OptimizationConstants | 1 | 5 | 3 | 2 |
| HilbertProblems | 2 | 13 | 2 | 5 |
| LittProblems | 1 | 5 | 2 | 1 |
| Subsets | 2 | 0 | 0 | 0 |

**Struktur-Flags** unter den 1466 offenen Statements (grob, als Filter):
`ℕ` 856, `∀` 607, `∃` 571, `ℝ` 490, asymptotisch (Tendsto/O-Notation) 388,
`Prime` 207, `Set` 200, `Finset` 133, `ℤ` 92, `∑` 75, `sSup/sInf` 19.
Davon ohne `answer`-Gadget (direkte Aussage): 571; mit `answer(sorry)`:
895.

**Bezug zur Erdős–Straus-Frage aus E1.** Das Statement **existiert** im
Katalog: `ErdosProblems/242.lean`, `erdos_242`
(`@[category research open, AMS 11]`, angelehnt an Mathesis 1956):
`∀ n > 2 ∃ x y z, 1 ≤ x < y < z ∧ 4/n = 1/x + 1/y + 1/z`, dazu die Variante
`erdos_242.variants.schinzel_generalization` (Schinzel). E1s offene Frage ist
damit **positiv** beantwortet (Erdős–Straus ist Katalog-Material!) — ein
früherer Stand dieser Datei behauptete das Gegenteil, weil die Suchliterale
(`4 / n =` als Zeichenfolge, `1 / a + 1 / b + 1 / c` mit genau diesen
Variablennamen) die Lean-Formatierung (`(4 / n : ℚ) = 1 / x + 1 / y + 1 / z`)
verfehlten; die kalte Abnahme fand den Treffer namensbasiert
(`scan.json`-Eintrag `erdos_242`, §6 Finding 1).

**Was der Scan nicht sagt.** Er elaboriert kein Lean: Statement-Grenzen sind
eine `:=`-Heuristik mit dokumentierter Sonderregel für `let`-Bindings im
Theorem-Typ (die Korpus-Idiomatik `let f := answer(sorry)`); Feature-Flags
sind Textindikatoren, keine Typanalyse; ob eine Datei kompiliert, sagt der
Scan nicht.

**Reproduktion.**

```bash
git clone --depth 1 https://github.com/google-deepmind/formal-conjectures \
    .yesmem/tmp/formal-conjectures
git -C .yesmem/tmp/formal-conjectures checkout a2f4a1b   # Pin der Messung
python3 yesdocs/formal-conjectures/tools/scan_catalog.py \
    .yesmem/tmp/formal-conjectures --json .yesmem/tmp/scan.json
cmp .yesmem/tmp/scan.json yesdocs/formal-conjectures/data/scan.json  # byte-identisch
python3 -m unittest discover -s yesdocs/formal-conjectures/tools
```

**Voll-Build des Repos.** Toolchain `leanprover/lean4:v4.33.1` und
mathlib-Rev `v4.33.1` stimmen exakt mit der lokalen Installation überein; der
mathlib-Oleancache (`~/.cache/mathlib`, 8690 Dateien) war aus dem E1-Lauf
vorhanden, `lake exe cache get` meldete „Already decompressed 8690 file(s)“.
Ein vollständiger `lake build` lief danach in **~11 min durch** (12:31:34 →
12:42:17, 16 Kerne): `Build completed successfully (10180 jobs)`, EXIT 0,
1140 gebaute Repo-Module, keine Fehler/Warnungen im Log
(Log `build2.log`; ein erster, beim Shell-Timeout abgebrochener Lauf hatte
davor bereits 9039/10180 Jobs gebaut). Der Voll-Build ist auf
dieser Maschine also billig (Klon 13 MB + vorhandener mathlib-Cache) — er ist
trotzdem **kein** Träger der Scan-Aussagen oben; der Scan bleibt statisch und
läuft ohne Lean.

## 2. Shortlist

Kriterien sind die Gates und Kernkriterien aus
[04-01](../deepseek-math-notation/wiki/04-offene-probleme/04-01-wahlkriterien.md):
K2 ≥ 1 (maschineller Prüfpfad) und K4 = 2 (lokal testbar) sind harte Gates;
K1 = 0 (nicht offen) schließt aus. Bewertung ehrlich, nicht wohlwollend.

| # | Kandidat (Quelle im Katalog) | K1 | K2 | K3 | K4 | K5 | K6 | K7 |
|---|---|---|---|---|---|---|---|---|
| 1 | BMO#1 `1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE` (Other/BeaverMathOlympiad.lean) | 2 | 2 frag. | 2 | 2 | 2 | 2 | 1 |
| 2 | BMO#5 `1RB0LD_1LC0RA_1RA1LB_1LA1LE_1RF0LC_---0RE` (ebd.) | 2 | 2 frag. | 2 | 2 | 2 | 2 | 2 |
| 3 | BMO#2 Antihydra `1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA` (ebd.) | 2 | 2 frag. | 2 | 2 | 2 | 2 | 1 |
| 4 | OEIS A34693 — kleinste `k` mit `k·n+1` prim (OEIS/34693.lean) | 1 | 2 | 2 | 2 | 1 | 2 | 1 |
| 5 | Rule-30-Zentralspalte, Prize 1+2 (Other/Rule30.lean) | 2 | 2 frag. | 2 | 2 | 2 | 2 | 2 |
| 6 | Erdős–Straus `erdos_242` (ErdosProblems/242.lean) | 2 | 2 | 2 | 2 | 2 | 2 | 1 |

„K2 frag.“ = der Prüfpfad deckt **endliche Fragmente** vollständig
(„die Maschine läuft N Schritte ohne Halt“; „für dieses n existiert das k“),
aber es gibt keinen Zertifikatspfad für die jeweilige Gesamtaussage — genau
das unterscheidet ein Testfeld-Fragment von einer lösbaren Aufgabe.

### 2.1 BMO#1 — `1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE` (offen)

- **Was es ist.** Ein BB(6)-Holdout („Potential Cryptid“): 6-Zustands-,
  2-Symbol-Maschine; die Wiki dokumentiert das Modell
  `A(a,b): a>b → (a−b, 4b+2); a<b → (2a+1, b−a); a=b → Halt`, Start `A(1,2)`;
  die Katalog-Aussage ist die äquivalente Sequenzfrage
  `∃i: a_i = b_i` (`answer(sorry)`).
- **Anschluss an unsere Kette.** Direkt: `bemyself.turing` (bbchallenge-Notation)
  für `[HALT]`/`[SEARCHED]`-Fragmente und msheet-`sim`-Checkpoints;
  `[CYCLE]` formal verfügbar, aber es gibt kein Zertifikat — die Maschine
  ist von den bbchallenge-Decidern unentschieden.
- **Was fehlt.** Für die Gesamtfrage braucht es ein ergodisches/Entropie-
  Argument auf der 1D-Grenzabbildung (Wiki-Review 2026-04-19) — **keine**
  Maschinerie dieser Kette.
- **Nötige neue Maschinerie.** Keine für endliche Fragmente; für die
  Sequenzseite keine (bigint-Iteration); für einen echten Angriff: nichts
  Verfügbares.
- **Ehrliches Urteil.** Als Testfeld-Fragment sehr stark (dieselbe Frage in
  mindestens drei Notationen: Maschinenstring, `(a,b)`-Rekurrenz,
  Olympiaden-Prosa; beliebig abstufbar). Als *Lösungsangriff* im Budget
  aussichtslos.

### 2.2 BMO#5 — `1RB0LD_1LC0RA_1RA1LB_1LA1LE_1RF0LC_---0RE` (offen)

- **Was es ist.** Ebenfalls ein 6-Zustands-2-Symbol-Holdout; die
  Reformulierung `(a,b)` mit `f(x)=10·2^x−1` und der Frage
  `∃i: b_i = f(a_i)−1` ist auf der Wiki dokumentiert; die Äquivalenz
  Maschine ↔ Reformulierung ist **in Rocq verifiziert** (busycoq-Branch
  `BB6`, dauerhaft verlinkt). Katalog: `answer(sorry)`.
- **Anschluss.** Wie BMO#1; zusätzlich: weil die Äquivalenz formal belegt
  ist, lassen sich Aufgaben rein algebraisch stellen und trotzdem per
  Maschinensimulation nachprüfen (zwei unabhängige Kanäle).
- **Was fehlt.** Dasselbe wie bei #1 — kein Zertifikatspfad für die
  Gesamtfrage.
- **Ehrliches Urteil.** Stärkste „saubere“ Testfeld-Zelle der Familie, weil
  der Äquivalenz-Vertrauensfrage hier ausgewichen werden kann.

### 2.3 BMO#2 Antihydra — `1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA` (offen)

- **Was es ist.** Die Collatz-artige Sequenz `a_0=8, a_{n+1}=⌊3a_n/2⌋`;
  die Katalog-Aussage ist direkt die Vermutung `∀n: b_n ≥ 0`, wobei `b`
  je Geradem +2 und je Ungeradem −1 zählt (kumulierte Ungleichheit der
  Paritäten). Gleichwertig: Nicht-Halten der 6-Zustands-Maschine.
- **Anschluss.** Bigint-Iteration (endliche Beobachtung), Maschinenlauf;
  **kein** Translationszyklus-Kandidat (`[CYCLE]` greift nicht — die
  Maschine ist ein Cryptid, kein TC).
- **Was fehlt.** Ein Beweis der Nichtnegativität — dieselbe Klasse von
  Hindernis wie Collatz.
- **Ehrliches Urteil.** Gute Testfeld-Zelle (bekannt und dokumentiert,
  probabilistische Argumente auf der Wiki); als Angriffsziel offen und hart.

### 2.4 OEIS A34693 — kleinste `k` mit `k·n+1` prim (offen)

- **Was es ist.** `a(n)` = kleinstes `k` mit `k·n+1` prim. Katalog-Vermutung 1:
  `∀n>1 ∃k<n: (k·n+1) prim`. Vermutung 2 (stärker):
  `∃k < 1+n^{3/4}`; die Datei dokumentiert selbst, dass `1+n^{0.74}` nicht
  reicht (Zeuge `n=19`).
- **Anschluss.** Jede Instanz ist eine endliche Suche; Zeuge = das `k`
  selbst; mit V1-Bibliothek („range“-Zeuge) direkt im msheet prüfbar —
  **demonstriert** (§3.2).
- **Was fehlt.** Der Schluss von endlich auf unendlich; die Schranke
  `n^{3/4}` entspricht `(k−1)^4 < n^3` und ist damit exakt prüfbar.
- **Ehrliches Urteil.** Bestes „zahlen-theoretisches“ Geschwister der
  TM-Familie: endliche Zeugen, triviale Lokal-Prüfbarkeit, saubere
  Abstufung; Notationseffekt geringer als bei Traces.

### 2.5 Rule 30 — Zentralspalte, Prize 1+2 (offen; in §3.4 mitgemessen)

- **Was es ist.** `Other/Rule30.lean` formalisiert Wolframs Rule 30 samt
  `centerColumn` und einem `[category test]`-Theorem
  `centerColumn_prefix`, das die ersten acht Bits per `decide` gegen die
  bekannte Folge (OEIS A051023) prüft. Offen sind **Prize-Problem 1**
  (Zentralspalte ist nicht eventual-periodisch) und **Problem 2**
  (Dichte 1/2 der Einsen) als `answer(sorry)`-Statements.
- **Anschluss an unsere Kette.** Der endliche Teil ist voll maschinell:
  CA-Simulation plus externe Ankerseqzenz; die Datei liefert die Definitionen
  sogar im Repo mit. Kein Zertifikatspfad für die Gesamtaussagen
  (Periodizität/Dichte über unendliche Zeit), daher wie BMO ein
  Testfeld-Kandidat, kein Lösungsziel.
- **Was fehlt.** Ein Beweis für Unendlichkeitsaussagen über die Spalte.
- **Ehrliches Urteil.** Sehr guter Kandidat: die endliche Reproduktion ist
  zweifach unabhängig prüfbar (Lean-`decide`-Prefix im Repo, OEIS-Anker,
  zwei eigene Implementierungen) und der Sprung zur offenen Aussage ist klar
  benannt.

### 2.6 Erdős–Straus — `erdos_242` (offen; in dieser Runde nicht angegriffen)

- **Was es ist.** Die Vermutung als Katalog-Statement (§1); dazu die
  Schinzel-Variante.
- **Anschluss an unsere Kette.** Maximal: `[IDENT]` ist exakt auf die Form
  `4/n(t) = 1/a + 1/b + 1/c` zugeschnitten, `[COMPUTE]` mit
  `bemyself.experiments.erdos_straus` in der Allowlist, und der E1-Lauf hat
  sechs P12-Klassen im Kernel bewiesen. Die Katalog-Aussage ist aber die
  volle Vermutung über alle `n`; endliche/klassenweise Zertifikate decken sie
  nicht, und E1 hat die lokale Maschinerie bereits ausgeschöpft.
- **Was fehlt.** Ein Beweis für die restlichen Kongruenzklassen (offenes
  Forschungsproblem, nicht Budget-Frage).
- **Ehrliches Urteil.** Für unser Testfeld der **nächstliegende** Katalog-
  Anschluss überhaupt (die Kette wurde dafür gebaut) — aber genau deshalb in
  dieser Runde nur eingeordnet, nicht angegriffen: der Angriff wäre eine
  Wiederholung von E1 mit anderem Vorzeichen.

### 2.7 Geschwister und Solved-Seite (keine Shortlist-Einträge)

- **BMO#8** (`1RB0LD_0RC1RB_0RD0RA_1LE0RD_1LF---_0LA1LA`, offen) — dieselbe
  Klasse wie #1 (2 zusätzliche ganzzahlige Reformulierung); in §3.1
  mitgemessen.
- **BMO#3 / BMO#4** (Katalog: `research solved`) — fallen durch das
  K1-Gate. BMO#4 hat eine explizite geschlossene Form auf der Wiki
  (`a_n = (3·2^n + c(n))/5`, `c` periodisch mod 4) und ist damit ein sauberes
  **Autoformalisierungs-Ziel** (Lean); BMO#3s Nicht-Halte-Aussage ist
  informell gelöst, externe formale Beweise werden auf der Wiki berichtet.
  Der lokale `bemyself.turing` deckt diese beiden **nicht** ab: es sind
  2-Zustands-5-Symbol-Maschinen, der Simulator kann nur 2-Symbol-Notation.
- **BB(6) (`Wikipedia/BusyBeaver.lean`)** — `BB_6 = answer(sorry)`; der
  Statement-Weg dorthin verlangt eine `Turing.Machine`-Formalisierung und
  BB-Theorie (mathlib-seitig); im Budget nicht angreifbar, deshalb nicht in
  der Shortlist.
- **Drei Kuben / Hadwiger–Nelson / Goldbach-Witnesse** — bereits in E1
  (04-03) als kettenfern eingeschätzt (SAT-/Graph-Zertifikate statt
  Identitäts-/TM-Struktur); bestätigt durch den Scan (keine neuen
  Anschlüsse).

## 3. Erster umgrenzter Angriff

**Angriffslogik.** Kein Lösungsversuch (die Kandidaten sind offen), sondern:
(a) die *Recheninhalte* der Katalog-Aussagen exakt auf endlichem Budget
reproduzieren (`tools/catalog_probe.py`, deterministisch), und (b) die
mathematischen Zwischenbehauptungen in der **V1.1-Denk-Sprache** als Blatt
formulieren und vom Runner entscheiden lassen (`data/bmo-attack.msheet`).
Jede Zahl unten hat einen Prüfkommandopfad.

### 3.1 Reproduktionsprobe (`data/probe.txt`)

```text
# bounded probe of formal-conjectures shortlist candidates
# bounds: small_iterations=10000 big_iterations=1000000 sweep=10000 machine_steps=2000000 antihydra_iterations=100000
bmo1.first_ten_ok=true
bmo1.equality_index=none
bmo1.iterations=1000000
bmo1.machine.halts=False steps=2000000 score=1095
bmo2.min_b=0 at n=0
bmo2.iterations=100000
bmo2.machine.halts=False steps=2000000 score=1982
bmo3.power_of_four_hit=none
bmo3.iterations=9999
bmo4.closed_form_ok=true
bmo4.mod3_one_hit=none
bmo4.iterations=9999
bmo5.hit=none
bmo5.iterations=10000
bmo5.machine.halts=False steps=2000000 score=1246
bmo8.hit=none
bmo8.iterations=10000
bmo8.machine.halts=False steps=2000000 score=505
# bmo3/bmo4 machines are 5-symbol; bemyself.turing supports the 2-symbol notation only
rule30.oeis_a051023_prefix_ok=true
rule30.impl_cross_check_256=true
rule30.smallest_period_le_128_in_4096_bits=none
a34693.sweep=2..10000 checked=9999 max_k=84 at n=5207
a34693.not_found=none
a34693.violation_k_lt_n=none
a34693.violation_three_quarter=none
```

Was das **sagt** (jede Zeile ist eine endliche Beobachtung):

- `bmo1.first_ten_ok=true`: die im Katalog-Docstring behaupteten ersten zehn
  Paare werden von der Rekurrenz exakt reproduziert (Statement-Check gegen
  die eigene Quelle).
- `bmo1.equality_index=none` bis 10^6 Iterationen; Maschine BMO#1 ohne Halt
  in 2·10^6 Schritten (Wiederholung der bekannten Wiki-Größenordnung
  10^8, nicht mehr).
- `bmo2.min_b=0` bis 10^5 Iterationen (Antihydra-Zählung bleibt ≥ 0);
  Maschine ohne Halt in 2·10^6 Schritten.
- `bmo3/bmo4`: Rekurrenzen exakt bis n = 10^4; BMO#4: geschlossene Form
  stimmt mit der Rekurrenz überein **und** `a_n mod 3 = 1` tritt nie auf
  (beides endlich); BMO#3: nie eine 4er-Potenz bis n = 10^4.
- `bmo5`/`bmo8`: Reformulierungs-Treffer (`b_i = f(a_i)−1` bzw.
  `a_i = ⌊b_i/2⌋+1`) bis 10^4 Iterationen nicht erreicht; Maschinen ohne
  Halt in je 2·10^6 Schritten.
- `a34693`: Sweep n = 2..10^4 — jede Instanz hat ein `k < n` (Maximum
  `k = 84` bei `n = 5207`); **keine** Verletzung der schwachen **und**
  keine der starken Schranke `(k−1)^4 < n^3`. `not_found=none` heißt: kein
  Suchlauf lief in die Suchkappe (sonst stünde dort eine Liste — ein
  Kappen-Miss wird ausdrücklich **nicht** als Vermutungsverletzung gezählt).
- `rule30.oeis_a051023_prefix_ok=true`: die ersten 102 Bits der Zentralspalte
  (0..101) stimmen mit OEIS A051023 überein — unabhängig davon sind die
  ersten acht davon im Repo selbst per Lean-`decide` bewiesen
  (`centerColumn_prefix`); `impl_cross_check_256=true`: zwei verschiedene
  eigene Implementierungen (Fenster-Bytearray und sparse Live-Zellen)
  liefern dieselben 256 Bits; `smallest_period_le_128_in_4096_bits=none`:
  in den letzten 1024 der 4096 berechneten Bits wiederholt sich keine
  Periode `p ≤ 128` (endliche Evidenz gegen Prize 1, **kein** Beweis).

Was das **nicht** sagt: nichts über die offenen Gesamtaussagen. „Kein Halt
in 2·10^6 Schritten“ ist keine Nicht-Halte-Aussage; „kein Treffer bis n = 10^4“
keine Lösung der Vermutung; die Beobachtungen liegen teils **unter** den
öffentlich dokumentierten Bestwerten (bbchallenge: 10^8 Iterationen für BMO#1;
OEIS-Kommentare führen Tests weit über 10^4).

Semantik-Abgleich (BMO#8): Die Reformulierung rechnet über `ℤ`, unser Probe
spiegelt sie mit Pythons `//`. Beide Divisionssemantiken wurden gegeneinander
geprüft: `#eval ((-7 : Int) / 2)` → `-4` unter Lean 4.33.1 (Projekt
`lean/erdos-straus`, mathlib `v4.33.1`), identisch zu `(-7) // 2` in Python —
die Spiegelung ist geprüft, nicht angenommen.

Reproduktion (deterministisch, byte-identisch wiederholbar):

```bash
python3 yesdocs/formal-conjectures/tools/catalog_probe.py   # ≈ 8 s, Ausgabe: data/probe.txt
```

### 3.2 Denk-Sprache-Blatt (`data/bmo-attack.msheet`)

Das Blatt formuliert vier Zwischenbehauptungen des Angriffs mit Zeugen und
wurde vom Runner entschieden (Verdikte ausschließlich vom Runner):

```text
g: BMO#1-Maschine: Laufzeugen + A34693-Schranken (alles endlich)
d: isprime = Primzahltest der V1-Bibliothek (Guard 10^12); ** = Potenz
a: M = 1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE
h1: t=13 cp 13: (E,1,101)
v h1: sim(0..13)
h1+
h2: t=1000 cp 1000: (A,12,010101010101010101010010111111111)
v h2: sim(0..1000)
h2+
=: M lief 1000 Schritte ohne Halt (h2+)
h3: fuer jedes n in 2..1000 existiert k<n mit k*n+1 prim
v h3: range n in 2..1000: (exists k in 1..999: ((k < n) & isprime(((k * n) + 1))))
h3+
h4: fuer jedes n in 2..1000 existiert k mit (k-1)^4<n^3 und k*n+1 prim
v h4: range n in 2..1000: (exists k in 1..999: ((((k - 1) ** 4) < (n ** 3)) & isprime(((k * n) + 1))))
h4+
CLAIM c1: M erreicht t=13 (E,1,101)
WITNESS c1: ref h1
CLAIM c2: M erreicht t=1000 (A,12,010101010101010101010010111111111)
WITNESS c2: ref h2
CLAIM c3: (forall n in 2..1000: (exists k in 1..999: ((k < n) & isprime(((k * n) + 1)))))
WITNESS c3: ref h3
CLAIM c4: (forall n in 2..1000: (exists k in 1..999: ((((k - 1) ** 4) < (n ** 3)) & isprime(((k * n) + 1)))))
WITNESS c4: ref h4
[HALT] c1 c2 c3 c4
```

Runner-Ausgabe (Verdikte; `python3 -m bemyself.msheet run …`, Laufzeit 0,11 s):

```text
#ok: v1 v2 v3 v4 c1 c2 c3 c4
```

Alle acht Zeilen sind **CONFIRMED** — die Auditkette ist geschlossen:
`c1 → ref h1 → v1 → sim` (Checkpoint `(E,1,101)` wird gegen
`bemyself.turing` nachgerechnet, nicht geglaubt), `c3/c4 → ref h3/h4 →
range`-Zeuge (die endliche Allaussage wird ausgewertet; `isprime` =
Miller-Rabin der V1-Bibliothek). Die beiden `sim`-Zeugen belegen nebenbei:
BMO#1 läuft 13 und 1000 Schritte weit in exakt den angegebenen
Konfigurationen — das sind die ersten maschinenbestätigten
BMO-Zwischenbehauptungen dieser Runde. Ein `cyc`-Zeuge kommt bewusst
nicht vor: es gibt kein Translationszyklus-Zertifikat (und ein erfundenes
bekäme `#xx`).

Reproduktion:

```bash
python3 -m bemyself.msheet run yesdocs/formal-conjectures/data/bmo-attack.msheet --json
```

**Daten-Anker.** Die eingefrorenen Artefakte sind zusätzlich über
`[ARTIFACT]`-Claims an dieses Dokument gebunden; der Prüfer liest die Dateien
unter der Repo-Wurzel und vergleicht die SHA-256:

[ARTIFACT: yesdocs/formal-conjectures/data/scan.json -> 8505c975f59f26668e51791ba471385fcfa36341e4709354ae2a689208d10b58]
[ARTIFACT: yesdocs/formal-conjectures/data/probe.txt -> ca9f2943a1a5c6b6dd7b0fbd908107fb5e0c89cc5f28333312232a97e256f410]
[ARTIFACT: yesdocs/formal-conjectures/data/bmo-attack.msheet -> 7d0b37d8da2ce589fef5a32498164fa8f75d6ab8aed1d4077a5ccd133f327bef]

**Nachtrag 2026-09-13 (V17, `attack-01.md`).** Der vertiefte Angriff auf BMO#1 und
Antihydra (Reduktionen beidseitig, Deep-Läufe, Strukturjagd) friert folgende
Artefakte ein:

[ARTIFACT: yesdocs/formal-conjectures/data/reductions.txt -> b5433ec3020c5d7ca9b5554f822fbfec6b0eff60eccceea5f803d39b60a7a455]
[ARTIFACT: yesdocs/formal-conjectures/data/structure.txt -> 59c3aa9baedcd3309575266380bc645ce0dafa43842110ec2094b7467eac079e]
[ARTIFACT: yesdocs/formal-conjectures/data/bmo-phase2.msheet -> ab27ea7f6e1f0bd063cf0a07cb79a6df45991369c0ac1f06fd4c115b47d83c10]
[ARTIFACT: yesdocs/formal-conjectures/data/antihydra-deep-2p32.txt -> b777395166f2fceee2d92b5bcc6bc2033640a042d007614b447e16be7110fbe7]
[ARTIFACT: yesdocs/formal-conjectures/data/raw-antihydra-2p32.txt -> b7a74394f7210f3fc408573055f570ef312c017923f32157d194e7b3cab8a2bc]
[ARTIFACT: yesdocs/formal-conjectures/data/bmo1-run.txt -> c1338d5974bcf48068d12a549c9dae2243f03e2fb3025114105491d06c1e7498]

Die ausführbaren Prüfungen des Nachtrags (Roh-TM-Läufe, Deep-Tool im Sandkasten,
alle Artefakt-Digests) bündelt `data/attack-01-check.txt`; Verifikation mit
`python3 -m bemyself check --report yesdocs/formal-conjectures/data/attack-01-check.txt --repo . --strict`.

```bash
python3 -m bemyself check --report yesdocs/formal-conjectures/README.md --repo . --strict
```

**Nachtrag 2026-09-13 (V20, Astra-Lemma-Loop §(A)).** Der erste Satz des
Astra-Lemma-Loops liegt jetzt kernel-geprüft vor: Für jedes `k ≥ 3` hält der
Antihydra-Start `(k−1, 2^k − 3)` nach genau `k−1` legalen Übergängen; jeder
`i`-te Zustand erfüllt `A_i = k−1−i`, `b_i + 3 = 3^i·2^{k−i}`, `b_i` ungerade;
Endzustand `(0, 2·3^{k−1} − 3)` (`lean/antihydra-family`, Lean 4.33.1, Core/Std
ohne mathlib, kein `sorry`/`admit`, Axiome nur `[propext, Quot.sound]`). Das
ist **keine** Lösung einer offenen Frage, sondern eine vollständige
Halt-Familie der reduzierten Regel. Artefakt gebunden:

[ARTIFACT: lean/antihydra-family/Antihydra.lean -> 0ea9dba32b9e588e2dfcd24e988a5619ff9e72383317efb0460359173d3a985b]

**Nachtrag 2026-09-14 (V21, `attack-02.md`).** Der Antihydra-Lemma-Loop (Runden
1-18 mit externem Vorschlagsmodell `gpt-6-astra`, 2026-09-13/14) ist als
`attack-02.md` eingefroren: kantenweise 2-Byte-Potentiale sind auf der echten Bahn
durch Zeugen widerlegt, der beobachtete 3-Byte-Graph trägt ein verifiziertes
Potential der Breite 92 (Zeugenpfad 23 Knoten / -92,
`data/antihydra-wide92-cert.json`), der Chronologie-Drawdown beträgt 73, und der
gesamte Angriff reduziert sich auf eine offene Drawdown-Schranke. Dazu das
generalisierte Werkzeug `tools/fast_orbit.py` (Transfer-Identität, bit-identisch
zu den eingefrorenen Läufen, mit Tests) und die 17 Rohantworten des Loops.
**Kein Lösungsergebnis**; Antihydra bleibt offen. Artefakte gebunden:

[ARTIFACT: yesdocs/formal-conjectures/tools/fast_orbit.py -> 2847c491937a83fad673fddb665cd5352dd2066a125a55356ef4be00c5101e59]
[ARTIFACT: yesdocs/formal-conjectures/tools/test_fast_orbit.py -> 60ae388d4a3ab926681a61d50852e45e5f82ecc4241bec9637bf1ebd80c86cc0]
[ARTIFACT: yesdocs/formal-conjectures/data/antihydra-wide92-cert.json -> f28e9fcabcc45aa6a421423527af345005b19f6df18de34d6d02cef4c4eb5010]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/README.md -> 893e8f9917cacfae558c9020d5be213aabf1b6a9201185443a4a498986794e1b]

Die ausführbaren Prüfungen des Nachtrags bündelt `data/attack-02-check.txt`
(u. a. `[COMPUTE]` auf `tools/fast_orbit.py`).

**Nachtrag 2026-09-14 (V22, `attack-02.md` §N.1-§N.7).** Die Fortsetzung des
Antihydra-Lemma-Loops (Runden 19-28, 2026-09-14 00:32-08:01) ist als Nachtrag in
`attack-02.md` eingefroren: die Counter-Engine des Repos liefert exakte
Blockzähler an beliebigen Checkpoints (Tiefe 28 in 83 s statt eines
Bit-Laufs von geschätzten 8,5 h für 2^27), die orbit-spezifische lineare
Kompression (L) ist für d ≤ 12 exakt ausgeschlossen (volle Spaltenränge mit
Minor-Zeugen; die mod-2-Kandidatenrelation R0 ist widerlegt), und die
nichtlineare Invariante (N) hält mit exakt eingefrorenem Radius
R² = 1309875575/347892350976 auf allen geprüften Zellen (0 Verletzungen;
Maximum exakt an (14,4)). Die α-Messung (0,4644) wird zur Zielform
`|D| ≤ K_i·L^{2/3}` präzisiert. **Kein Lösungsergebnis**; Antihydra bleibt
offen. Die zehn neuen Astra-Rohrunden r19-r28 liegen neben den V21-Antworten
in `data/astra-antihydra-rounds/`. Artefakte gebunden:

[ARTIFACT: yesdocs/formal-conjectures/tools/deep_rank_chain.py -> 1ecb70a639ac806f38ea87710c2cc198747a65eb251927965c2b0d0eabd25305]
[ARTIFACT: yesdocs/formal-conjectures/tools/r0_sweep.py -> 328aa95ec45f91ab73800fe24b972e03735f3d81ef9281f6b183e8067cb8d9fc]
[ARTIFACT: yesdocs/formal-conjectures/tools/test_deep_rank_chain.py -> 42e38106ec8ed9f532ea2e4befa06f3864921ddfa571d64a304546438020ad66]
[ARTIFACT: yesdocs/formal-conjectures/data/deep-Cvalues-d12.json -> aef77bca04677b878db4984e9e3d31b4806718ad3f8129250d3a582d76e29b29]
[ARTIFACT: yesdocs/formal-conjectures/data/r0-sweep-result.json -> 0117349e2ebd3c41293ddd181c470af68977a8afa74076d7daa7c7ac00639272]

Die Anker dieses Nachtrags stehen in `data/attack-02-check.txt` (V21-Stand
plus die neuen Zeilen).

### 3.3 Einordnung

Der Angriff zeigt für die Shortlist, was im Testfeld **wirklich prüfbar**
ist: TM-Fragmente über `sim`/`[SEARCHED]` (Zeuge = ausgeführter Lauf),
Zahlen-Fragmente über `range`-Zeugen (Zeuge = Zeuge im Wortsinn), Zellautomaten
über zwei unabhängige Implementierungen plus Fremdanker, und er
zeigt die Grenze: die offenen Gesamtaussagen haben **keinen**
Zertifikatspfad — jede „Antwort“ auf sie ist und bleibt eine endliche
Beobachtung. Für das Notations-A/B ist genau diese Kombination interessant:
identische endliche Prüfanker, mehrere Notationen derselben Frage.

### 3.4 Rule 30 (nachtrags aus §2.5)

Der Rule-30-Kandidat kam über die kalte Abnahme in die Shortlist (das Repo
definiert den Zellautomaten selbst, `Other/Rule30.lean`); die Messung steht
in §3.1: Bits 0..101 == OEIS A051023 (und Bits 0..8 davon Lean-`decide`-fest),
zwei unabhängige Implementationen stimmen bis 256 überein, keine kleine
Periode bis 4096 Bits. Was das **nicht** ist: ein Beweis der
Nicht-Periodizität oder der Dichte 1/2 — nur gebundene Evidenz, ehrlich
beschriftet.

## 4. Grenzen (ehrlich)

1. **Keine Lösung, kein Fortschritt an einer offenen Frage.** Alle
   Ergebniszeilen sind endliche Beobachtungen mit benanntem Budget; die
   Nicht-Halte- und Unendlichkeitsaussagen bleiben offen.
2. **Bounded ≠ Bestwert.** Die Budgets (10^6 Iterationen, 2·10^6 Schritte,
   n ≤ 10^4) liegen teils unter den öffentlich dokumentierten Suchtiefen
   (BMO#1: 10^8 Iterationen; A34693: OEIS-Kommentare). Neu ist die
   Reproduzierbarkeit mit **unserer** Kette, nicht die Tiefe.
3. **5-Symbol-Maschinen fehlen.** BMO#3/#4 sind 2-Zustands-5-Symbol-Maschinen;
   `bemyself.turing` unterstützt nur die 2-Symbol-Notation. Ein Angriff auf
   diese beiden braucht zuerst eine Simulator-Erweiterung (neue Maschinerie).
4. **Äquivalenzen nicht lokal nachgeprüft.** Die Maschine↔Reformulierung-
   Äquivalenzen stammen aus externer Dokumentation (Rocq für BMO#5, Lean für
   die BMO#1-Regeln, Wiki für die übrigen); lokal wurden nur beide Seiten
   *einzeln* endlich reproduziert. — **Nachtrag 2026-09-13 (V17): für BMO#1 und
   Antihydra geschlossen**, siehe `attack-01.md` §2: `tools/reductions.py`
   prüft die dokumentierten Maps beidseitig gegen den Roh-TM-Simulator auf
   exakt beschrifteten endlichen Fenstern (Trajektorie 12 Konfigurationen je
   Maschine; Fenster a0..24 × b1..60 bzw. a0..20 × b1..40) und findet dabei
   zwei Domänen-Korrekturen (Antihydra b=1, BMO#1 b=a+2).
5. **Statement-Qualität nur stichprobenartig — mit einem belegten Fehler.**
   Der Docstring-Check (BMO#1-Erstwerte, A34693-Namen, BMO#4-Closed-Form gegen
   Wiki) lief für die Shortlist-Kandidaten; ein früherer Stand dieser Datei
   übersah außerdem das Erdős–Straus-Statement (`erdos_242`) und behauptete
   seine Abwesenheit — gefunden von der kalten Abnahme, korrigiert (§1, §2.6,
   §6). Der restliche Katalog ist nicht Statement-für-Statement gegen seine
   Quellen geprüft.
6. **Scan ist statisch.** Keine Lean-Elaboration; die Kennzahlen hängen am
   gepinnten Commit `a2f4a1b`, nicht am jeweils aktuellen `main`. Der
   Voll-Build lief zwar durch (§1), prüft aber nur das Kompilieren, nicht die
   Interpretation der Kennzahlen.
7. **Klon nur temporär.** `.yesmem/tmp/formal-conjectures` ist gitignored;
   `data/scan.json` (2,6 MB) ist das eingefrorene, hinreichend
   deterministische Abbild. Kein Push, kein Merge, kein Deploy.

## 5. Quellen

- [formal-conjectures (GitHub)](https://github.com/google-deepmind/formal-conjectures) — Katalog, Commit `a2f4a1b`, Apache-2.0/CC-BY (Abruf 2026-09-13)
- [Beaver Math Olympiad (BusyBeaverWiki)](https://wiki.bbchallenge.org/wiki/Beaver_Math_Olympiad) — BMO-Probleme 1–11, gelöste Fälle, Rocq-Verweis (Abruf 2026-09-13)
- [`1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE` (BusyBeaverWiki)](https://wiki.bbchallenge.org/wiki/1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE) — Modell, Startkonfiguration, 10^8-Iterationen, Review 2026-04-19 (Abruf 2026-09-13)
- [OEIS A34693](https://oeis.org/A34693) — kleinste `k` mit `k·n+1` prim (Abruf 2026-09-13)
- [OEIS A051023](https://oeis.org/A051023) — Zentralspalte von Rule 30 (Anker der Bits 0..101; Abruf 2026-09-13)
- Lokal: `tools/scan_catalog.py`, `tools/catalog_probe.py` samt Tests, `data/scan.json`, `data/probe.txt`, `data/bmo-attack.msheet`
- Nachtrag V17 (2026-09-13): [attack-01.md](attack-01.md) — Quellen, Reduktions-Verifikation
  (beidseitig), Deep-Läufe (Antihydra über 2^31 hinaus, BMO#1-Grenze), Strukturjagd,
  V1.1-Evaluierung; Werkzeuge `tools/reductions.py` (18 Tests), `bemyself/experiments/antihydra_deep.py`
  (12 Tests), Blatt `data/bmo-phase2.msheet`, Anker `data/attack-01-check.txt`
- Einordnung im Wiki: [04-03 Nachtrag 2026-09-13](../deepseek-math-notation/wiki/04-offene-probleme/04-03-rechenfragmente-daten.md), Kriterien aus [04-01](../deepseek-math-notation/wiki/04-offene-probleme/04-01-wahlkriterien.md)

## 6. Review-Befunde und Auflösung

Drei Abnahmen liefen nach der Fertigstellung (kalte Abnahme/5.2,
Zweitfolgen+Intent/5.3, Security/5.4). Alle Befunde:

| # | Quelle | Befund | Auflösung | Beleg |
|---|---|---|---|---|
| 1 | 5.2 [hoch] | Erdős–Straus existiert doch im Katalog (`erdos_242`); die Doku behauptete das Gegenteil | Behauptung in §1/§2.6 + Wiki korrigiert; Ursache der Fehlsuche dokumentiert | `ErdosProblems/242.lean:35-41`, `scan.json`-Eintrag `erdos_242` |
| 2 | 5.2 [mittel] | 25 Deklarationen mit geteilten Attribut-Klammern (`@[simp, category API, …]`) fehlten | Parser erweitert (geteilte Klammern, Modifikatoren), Zahlen auf 5445/321 korrigiert; Fixture-Test | `deviation fixed: scan 5445 == 5446 roh − 1 Docstring` |
| 3 | 5.2 [niedrig] | Unicode-Namen abgeschnitten (`not_lt₂_of`, `fixed_ε`) | Namens-Regex auf Delimiter-Klasse erweitert; Fixture-Test | `test_declaration_fields` (demo_unicode₂) |
| 4 | 5.2/5.3 [niedrig] | Repro-Blöcke ohne Commit-Pin, `--json` überschrieb den Anker | `git checkout a2f4a1b` + `cmp`-Schritt in §1/§3 | §1/§3 Reproduktionsblöcke |
| 5 | 5.2 [niedrig] | INDEX-Kopfzähler absolut nicht reproduzierbar (Alt-Konvention, schon an der Basis) | nicht stillschweigend umgeschrieben; Deltas exakt (+4 Quellen, +2 Zitate, +Wörter) | INDEX-Diff; 5.3-Zweitfolgenbericht |
| 6 | 5.2 [niedrig] | „~11 min“ betraf nur den zweiten Build-Lauf | Build-Log-Kontext ergänzt (erster Lauf abgebrochen bei 9039/10180) | `.yesmem/tmp/formal-conjectures/build2.log` |
| 7 | 5.2 [niedrig] | Probe-Robustheit: `iterations`-Zeile konnte überzeichnen, `not_found`-Kappung ohne Vermerk, Fehlerpfad KeyError | Ist-Iterationen ausgegeben; Kappungsvermerk „first 8 of N“; Fehlerzeile statt KeyError | `probe.txt`, `test_catalog_probe.py` |
| 8 | 5.3 [niedrig] | INDEX-Link `../../../formal-conjectures/…` eine Ebene zu tief | auf `../../` korrigiert | `INDEX.md:212` |
| 9 | 5.3 [niedrig] | Verifikationsbeleg stand auf `113a598`, Endstand war `34ace66` | Suite/Tool-Tests/`check --strict`/msheet am finalen Stand erneut ausgeführt (s. u.) | Phase-4-Block im Scratchpad |
| 10 | 5.4 [L] | Quadratische Laufzeit in `_statement_text` auf präpariertem Text (20,8 s für 3,6 MB) | Zeilen-/`let`-Offsets einmal pro Datei vorberechnet, `bisect` statt Präfix-Rescan; adversarialer Repro: 0,17 s | Security-Repro nachgestellt |
| 11 | 5.4 [L] | `_is_prime`-Docstring-Schranke falsch (12 Basen reichen nur bis 3,19·10^23; Zeuge 318665857834031151167461) | Basis 41 ergänzt, Schranke auf `< 3,317·10^24` korrigiert; Zeuge + Grenzfall als Tests | `test_known_strong_pseudoprime_is_detected` |

Aus den Reviews zusätzlich übernommen (kein Befund, aber Chance): der
Rule-30-Kandidat (§2.5, §3.4) und die Erdős–Straus-Einordnung (§2.6).

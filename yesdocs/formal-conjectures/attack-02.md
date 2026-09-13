# Angriff 02 - Antihydra im Lemma-Loop mit Fremdmodell (Runden 1-18)

Datum: 2026-09-14. Ausgangsbasis: `master` @ `a35a3d1`. Vorgeschichte: `attack-01.md`
(V17: beidseitige Reduktions-Verifikation, Roh-TM-2^32-Lauf, Strukturjagd),
`lean/antihydra-family` (V20: kernel-geprüfte Halt-Familie) und die BMO#2-Passage in
`README.md`. Dieser Bericht friert den Stand eines 18-rundigen Lemma-Loops ein
(Runden 1-18, Stand 2026-09-14 00:23): Ein externes Modell (`gpt-6-astra`) lieferte
Kandidat-Aussagen, die Verifikationsseite dieses Repos hat jede davon endlich
nachgerechnet, widerlegt oder präzisiert; die Rohantworten liegen in
`data/astra-antihydra-rounds/`.

**Kein Lösungsergebnis.** Antihydra bleibt offen. Alles hier ist endliche, exakt
beschriftete Verifikation. Der Wert des Loops liegt in drei Dingen: (i) er hat
Kandidaten-Klassen definitiv getötet (universelle Dichten, feste Modul-Tabellen,
kantenweise 2-Byte-Potentiale), (ii) er hat die 3-Byte-Abstraktion exakt vermessen
(Breite 92 gegen Beobachtung 73), und (iii) er hat am Ende **alle** Routen auf
**eine einzige offene Aussage** reduziert (§6): eine Drawdown-Schranke auf dem
unendlichen Orbit.

## 1. Protokoll des Loops

Zwei Rollen, ein Zyklus:

- **Vorschlagsmodell** `gpt-6-astra` (extern, Reasoning-Effort `high`): erhält je
  Runde einen kompakten Zustandsbericht (Definitionen, verifizierte Zahlen, offene
  Punkte, Widerlegungen) und liefert Kandidaten, Lemmata, Selbstkorrekturen und
  präzisierte Zielaussagen. Antworten als Roh-JSON eingefroren.
- **Verifikationsseite** (dieses Repo): testet jeden Kandidaten endlich auf der
  echten Bahn (exakte Ganzzahlen, keine Fließkomma-Verdikte), mit exhaustiven
  Fenstern, Tabellen, Graphen und Lean für den einen formalisierbaren Satz.
- **Feedback**: Jedes Ergebnis geht mit Zahlen und Minimal-Slacks zurück; widerlegte
  Kandidaten werden als widerlegt markiert, damit die nächste Runde nicht dieselbe
  Klasse erneut vorschlägt.

Regeln: Keine Astra-Aussage steht in diesem Bericht ohne Nachrechnung; wo eine Zahl
nur aus einem Astra-Lauf stammt, ist sie als Astra-Aussage gekennzeichnet. Jede
Runde endet mit einem endlichen Test, nie mit "gilt vermutlich".

Umfang: Runden 1-18, 2026-09-13 18:55 bis 2026-09-14 00:23. Token-Budget: 10.000.000
veranschlagt; Stand Runde 15 verbraucht etwa 210.000 (rund 2%). Rohdaten: 17 der 18
Antwortdateien `astra-antihydra-r{1,3,...,18}.json` (`r2` wurde nie gespeichert; die
Lücke ist in `data/astra-antihydra-rounds/README.md` ausgewiesen). Die
Rundenprotokolle der Verifikationsseite stehen in der Session-Conveyor-Seite (nicht
Teil dieses Repos) und sind in §3 verdichtet.

## 2. Ausgangslage und Definitionen

Antihydra-Regel (aus `attack-01.md` §1/§2, beidseitig gegen den Roh-Simulator
verifiziert): `b` gerade → `(a+2, 3b/2+2)`; `b` ungerade mit `a>0` → `(a-1, (3b+3)/2)`;
Halt genau dann, wenn `a=0` und `b` ungerade. Hier ausschließlich als Paritätskette:

- `x = b + 4`, Schritt `T(x) = 3x//2`, Start `x0 = 8` (Leerband-Orbit).
- `E(n)` = Anzahl gerader Schritte unter den ersten `n`; `H(n) = 5·E(n) - 2n`
  (Reserve); `A(n) = 3·E(n) - n` (Zähler). Kein Halt bis `n` zeigt sich als
  Mindestwert des Zählers `≥ 0` entlang der Bahn; ein Halt wäre der erste
  negative Zählerschritt (`attack-01.md` §3).
- **8-Schritt-Blöcke** (`W=8`): `r = x mod 256`; die Paritäten der nächsten acht
  Schritte hängen nur von `r` ab; Blockgewicht `g(r) = 5·(#gerade) - 16`; mit
  `S_j = g_0 + ... + g_{j-1}` ist der **Drawdown** `max_j ( max_{i≤j} S_i - S_j )`.
  Der Drawdown einer endlichen Chronologie ist die untere Schranke für jede
  Potentialbreite auf dieser Chronologie (Astra R14: Breite = maximale Wegedefizite).

Verifizierte Zahlen des 2^23-Blocks (Nachrechnung dieses Berichts, siehe §8):
`E(2^20)=523720`, `H(2^20)=521448`, `A(2^20)=522584` (identisch mit dem R2-Wert);
`H(2^22)=2091252`, `H(2^23)=4181939`; `x_end` bei 2^23 hat 4.907.025 Bit.

## 3. Rundenchronik R1-R18

| Runde | Astra liefert | Verifikation (dieses Repo) | Ergebnis |
|---|---|---|---|
| R1 (18:55) | Regel-Hypothese H; Kandidat D (Vier-Block-Dichte); Kandidat V (2-adisch); Bijektions-Lemma + Halt-Familie | R2: H deckungsgleich mit `reductions.py`; D auf 2^20 bestanden; Bijektion k=18; Familie k=3..200 | alle drei Kandidaten überleben; Halt-Familie tötet universelle Dichten |
| R3 (19:01) | Lean-tauglicher Beweis der Halt-Familie; Skalenidentität; Negativsatz feste Modul-Tabellen | Beweis übernommen (→ V20, kernel-geprüft); Skalenidentität 7/7; V: 0 Verletzungen 2^20 | erster vollständiger propose→verify→formalize-Zyklus |
| R4 (21:31) | Antwort auf den (W)-Befund; Reduktion der Erhaltungs-Ungleichung | (W) REFUTED (523.720 Rückkehren, min -704176); `r+15q ≥ 0` 28/28 (min 93); max `|q|/2^{k/2} = 82,0`; `R_7 = 262299` | offene Ungleichung exakt reduziert auf Residuen-Vermeidung |
| R5 (21:41) | Rückzug (W); D−-einseitige Schranke; Grenze lokaler Rückkehrargumente | Identität `r+15q = 3r_{k+1}-5r_k` nachgerechnet; Dichte-Mechanik `p⁺-2/5 ≥ (5/6)(p-2/5)` | (W) endgültig weg; Route verengt |
| R6 (21:46) | Normierte Verluste summierbar unter D− | Barriere `r ≥ 431.4777·2^k + 853.55·2^{k/2}` (k≥7); Seed 53348 gegen unsere 64886..66261 | D− allein genügt für lineare Barriere |
| R7 (22:11) | Zwei-Skalen-Bedingung (P) ⇒ Barriere (Beweis); Route (R) | (P) exakt nachgerechnet (max norm. Verlust 221/8=27.625; Budgets 67.58/62.08/66.49/63.02); P₁/₂ 28/28; V ≤ 1.5U + 0 auf 2^21 (max -1.5) | zwei unabhängige Barrieren-Routen, eine bewiesen |
| R8 (22:26) | Route (R): H-Reserve-Lemma (dyadische Gewinne/Defizite + Seed) | Daten: a=0.4158, b bis 0.0027 (k≥12), Seeds mit großer Marge | Zertifikats-Route gewählt |
| R9 (22:44) | Präzises Zertifikat (k0=12, a=2/5, b=1/256); Kompositionsregeln | Finite-Z-Exakttest; `G(AB)=G(A)+G(B)`, `D(AB)=max(D(A), D(B)-G(A))` | testbares Zertifikat fixiert |
| R10 (22:54) | (G,D,m)-Tabelle k≤21; Vorhersage H(2^22) | Tabelle exakt; Vorhersage H(2^22)=2091252 / E=2095972 / A=2093612 | Vorhersage später bit-genau reproduziert (§4.2) |
| R11 (23:20) | Carry-Plan w=8; Graph-/Potential-Plan | exhaustiv 65536 Paare, 0 Fehler; Permutations-Einsicht bestätigt | Route wechselt von Tabellen zu Graphen |
| R12 (23:32) | Negativbefund unbeschränkter 2-Byte-Graph | `(1,0)` mit `g = -16` nachgerechnet (einzige negative Selbstschleife) | unbeschränkter Graph sofort tot |
| R13 (23:37) | 3-Byte-Diagnose; Reserve-Dynamik | beobachteter 2-Byte-Graph: 3 negative Selbstschleifen + 30 negative 2-Zyklen; Drawdown 73 | kantenweises 2-Byte-Potential definitiv tot |
| R14 (23:46) | Korrektur: minimale Breite = max. Wegedefizite; 73-Exakttest; 74-Zustands-Produktgraph | 3-Byte-Graph: 1.016.715 Zustände, 1.048.457..458 Kanten, 0 Selbstschleifen, 0 negative 2-Zyklen, ein Riesen-SCC | Potential existiert; Breite wird messbar |
| R15 (23:58) | Auswertung W*=92; konstruktive Verfeinerung (r,s,t,D); offene Zielaussage | SPFA 810.530 Relaxationen, W*=92, 0 Kantenverletzungen; Zeugenpfad 23 Knoten / -92 | alles reduziert auf eine offene Drawdown-Schranke (§6) |
| R16 (00:13) | Präzises Minimalziel (D−)/(P); (P) strikt schwächer; probabilistisches Haar-Theorem; Budgetbedingung (S) | (D−)⇒(P) für k≥8 (Arithmetik nachgerechnet); D-Tabelle k=6..8 exakt; (S)-Schwelle min u = 128772/262144 | Ziel exakt fixiert; fester Start bleibt offen (Haar-Maß-Null-Warnung) |
| R17 (00:17) | Explizite Algebra des Defektvektors `z_alg ∈ R^16`; Kriterium für eine geschlossene Defektrekursion | Identität `r_{k+2} = 4r_k + 10p_k`; Befund: die R16-Daten tragen keine carry-vollständige Renormierung | Zwischenschritt: Algebra explizit, Konstruktionslücke benannt |
| R18 (00:23) | Exakte Carry-Rekursion; Paritätswort-Bijektion; Vier-Skalen-Blockrekursion; Nicht-Abgeschlossenheit; Scheitern jeder 4D-finit-verzweigten affinen Defektrekursion | Carry-Rekursion bit-genau nachgerechnet; Bijektion 256/256; D-Tabelle k=6..8 exakt; Out-Grad-Verteilung {1:985683, 2:30328, 3:697, 4:7} (Summe 1.048.458) | Endbilanz: Engpass = orbit-spezifische Kompression der Carry-Korrelationen; kein Zertifikat |

Zwei Runden verdienen Hervorhebung, weil sie die Arbeitsweise des Loops zeigen:

- **R4/R5 war ein echter Fehlschlag mit Korrektur.** Die Höhen-Bedingung (W) war
  Astras Ersatz-Kandidat für die offene Ungleichung; die Nachrechnung widerlegte sie
  auf ganzer Linie (alle 523.720 Rückkehrpunkte negativ, Minimum -704176), Astra zog
  sie in R5 selbst zurück und lieferte den präzisen Mechanismus, warum eine lokale
  Rückkehrargumentation allein nicht reicht. Genau dieser Zyklus (Vorschlag,
  Widerlegung, präzisierte Zielaussage) ist der Ertrag des Protokolls.
- **R12-R15 zeigt das Muster der toten Klassen** (siehe §5): Die erste
  Graph-Abstraktion (2 Byte) starb an konkreten Zeugen, die zweite (3 Byte) lebte,
  kostete aber messbar 19 Einheiten Breite gegenüber der Chronologie; die
  Verfeinerung um den Drawdown selbst holt die Breite exakt auf 73 zurück, womit
  die Beweislast vollständig bei der Erreichbarkeitsfrage landet.

## 4. Verifizierte Ergebnisse

Alle Zahlen in diesem Abschnitt wurden für diesen Bericht nachgerechnet, soweit
nicht ausdrücklich als Astra-Aussage markiert; die Nachrechnung ist in §8
beschrieben. Die Nachrechnung hat die Loop-Logs in allen zentralen Zahlen
reproduziert (die anfangs fehlende Kante im 3-Byte-Graphen war die letzte
Blocktransition zum Endzustand; §4.6).

### 4.1 Blockskalierung, Reserven und q-Tabellen (R2-R7)

- **Dichte-Kriterium D** (Vier-Block-Reserven `5·E(Block) ≥ 2·L` auf dyadischen
  Skalen `N_k = 2^k · 4096`, Blocklänge `L = N_k/4`): Für die 32 Fenster der
  Stufen k=0..7 (Fenster = die vier Blöcke von `[2^k·4096, 2^{k+1}·4096)` auf
  den ersten 2^20 Schritten) ist jede Reserve positiv (Nachrechnung dieses
  Berichts: Minimum 347, Maximum 66261 — der obere Rand deckt sich mit dem
  Seed-Band 64886..66261 aus R6); Vorzeichen und Skalierung
  (`Reserve ≈ L/3`) wie von Astra vorhergesagt.
- **D± auf 2^22/2^23** (Nachrechnung dieses Berichts, k ≤ 10): alle
  Block-Reserven positiv, `D−`-Verletzungen 0, `D+`-Verletzungen 0;
  `(P)`-Bedingung `q_k + 0.5·q_{k+1} ≥ -50·2^{3k/4}` hält auf allen geprüften
  Paaren; Dichte-Check `3·Reserve ≥ |Intervall|`: 0 Verletzungen (36 Prüfungen).
  Beispielwerte: Reserven `(k=10)`: 524148 / 525333 / 520388 / 520818;
  `q (k=9)`: -908 / 673 / -162 / -1058.
- **q-Tabellen k ≤ 9** (Nachrechnung, exakt): `q_{k=7}` = 121 / -750 / 63 / -189,
  `q_{k=8}` = 718 / 688 / -211 / 272; Maximum `|q|/2^{k/2} = 82,0` (Astra-Wert,
  in der Nachrechnung bestätigt).
- **Skalenidentität** `R(2B) = 2·R(B) + 5·Q(B)` exakt auf 7/7 Epochs (Loop);
  **R_7 = 262299** exakt (Loop).

### 4.2 Das H-Reserve-Zertifikat bis k = 22

Astras Zertifikat (R9/R10): dyadische Blockgewinne `G_k ≥ a·2^k` und -defizite
`D_k ≤ b·2^k` mit `a ≥ b` plus endliche Startschranken erzwingen `H ≥ 0` für alle
Zeiten (H = 5E - 2n). Fixiert: **k0 = 12, a = 2/5, b = 1/256**, geprüft mit einem
Finite-Z-Exakttest; Komposition `G(AB) = G(A) + G(B)`,
`D(AB) = max(D(A), D(B) - G(A))`.

Der stärkste Beleg: Astra sagte aus einer `(G,D,m)`-Tabelle bis k = 21 heraus
**H(2^22) = 2091252, E(2^22) = 2095972, A(2^22) = 2093612** voraus; der schnelle
Generator (§4.3) hat diese Werte später **bit-genau** reproduziert. Nachrechnung
dieses Berichts: `E(2^22) = 2095972`, `H(2^22) = 2091252`, `A(2^22) = 2093612`
und zusätzlich `H(2^23) = 4181939`. Das ist kein Beweis (die Schranken sind nur
bis zu den geprüften Skalen zertifiziert), aber die Vorhersage über sechs
Skalenstufen hinweg ohne einzige Abweichung ist eine harte Konsistenzprobe.

### 4.3 Der schnelle Generator (Werkzeug im Repo)

Kern ist die exakte Transfer-Identität

    T^w(2^w·q + r) = 3^w·q + T^w(r),   alle q ≥ 0, 0 ≤ r < 2^w,

mit der ein Block von `w` Schritten auf einmal voranschreitet; die Paritäten der
`w` Schritte hängen nur von `r` ab (Beweis: Induktion, Carry steckt vollständig in
`T^w(r)`). Werkzeug: `tools/fast_orbit.py` (N als CLI-Argument, `w` = 16 oder 18
konfigurierbar, Ausgabe Bits-Datei + Statistiken; `--quiet --no-bits` für
deterministische Ausgabe), Tests in `tools/test_fast_orbit.py` (Transfer-Identität
random + exhaustiv, Fast-vs-Naiv bit-identisch für N=2^14 mit w=16/18 inkl.
Nicht-Vielfachen, exaktes `x_end` samt Handwert N=8, Statistik-Formeln,
CLI-Determinismus; 11/11 grün).

Nachrechnung dieses Berichts: der Generator liefert die **bit-identischen**
Paritätsdateien des Loops; `sha256(2^20) = d6396022...1046`,
`sha256(2^22) = c6abbc2d...d5a7`, `sha256(2^23) = f1708bed...3ff0` (identisch
mit den im Loop gespeicherten `/tmp/opencode/antihydra-bits-2p{20,22,23}.bin`);
Laufzeiten 2^22 in 27 s (w=16) und 2^23 in 107,7 s (w=18), die Loop-Messung
"2^23 in 107 s" ist damit exakt reproduziert. Der Faktor 44 gegenüber der naiven
Iteration beruht auf einer Loop-Messung der langsamen Seite und wurde hier nicht
erneut gemessen (ein naiver 2^23-Lauf läge bei rund 80 Minuten).

### 4.4 Carry-Analyse w = 8 (R11)

Für den Byte-Transfer `x → x' = 6561·(x>>8) + T^8(x mod 256)` wurden
Carry-Tabellen `R(r,s), C(r,s)` aufgestellt: nächstes Byte und Carry als
Funktion der zwei aktuellen Bytes. Exhaustiver Test über **alle 65.536 Paare
(r,s): 0 Fehler** (Loop). Konsequenz (Astra): feste niedrige Bits lassen die
höheren Bits frei, die Dynamik ist auf dem Quotienten eine Permutation mit
freien Fortsetzungen; genau deshalb braucht es Invarianten auf dem echten
Orbit statt lokaler Tabellen, und der Loop wechselte in die
Graph-/Potential-Sprache.

### 4.5 Der 2-Byte-Tod (R12/R13)

- **Unbeschränkter 2-Byte-Graph:** Die Abbildung `(r,s) → (r',s')` mit
  `x' = 6561·s + T^8(r)` hat genau **eine negative Selbstschleife: `(1,0)` mit
  `g = -16`** (Nachrechnung dieses Berichts: bestätigt; 8 aufeinanderfolgende
  ungerade Schritte ab `x ≡ 1 (mod 256)`). Damit ist ein kantenweises Potential auf
  dem vollen 2-Byte-Raum sofort unmöglich.
- **Beobachteter 2-Byte-Graph** (Walk über 1.048.576 Blöcke aus 2^23 Schritten;
  65.536 Zustände, 1.016.715 beobachtete Kanten; Nachrechnung dieses Berichts):
  drei negative Selbstschleifen auf der echten Bahn,
  `(15,1)` mit `g = -6`, `(173,77)` mit `g = -1`, `(229,202)` mit `g = -1`,
  plus **30 negative 2-Zyklen** (Kantensummen 1×-17, 4×-12, 10×-7, 15×-2;
  Zählung ungeordnet, mit den realisierten Minimalgewichten der Kanten
  nachgerechnet).
  Diese Zeugen liegen auf der real durchlaufenen Bahn, nicht nur in der
  unvollständigen Abstraktion: die Klasse "kantenweises 2-Byte-Potential" ist
  definitiv tot.
- **Drawdown der Chronologie: 73**, erreicht zwischen den Blöcken 294.573
  und 294.586 (Peak zu Trough; Nachrechnung exakt reproduziert, ebenso der
  kleinere 2^20-Wert 67 zwischen den Blöcken 63.606 und 63.618).

### 4.6 Der 3-Byte-Graph und W* = 92 (R14/R15)

Der beobachtete 3-Byte-Graph (Zustand `(r,s,t)`, Kante mit Gewicht `g(r)`) hat
(Nachrechnung dieses Berichts):

- **1.016.715 Knoten** (rund 6% des 2^24-Raums; identisch mit dem Loop-Log),
  **1.048.458 Kanten** (eine pro Blocktransition, inklusive der letzten zum
  Endzustand, Duplikate auf Minimalgewicht reduziert; identisch mit dem
  Loop-Log, bestätigt durch die Out-Grad-Summe in §4.9),
- **0 Selbstschleifen, 0 negative 2-Zyklen, keinen negativen Zyklus**
  (der Loop berichtet zusätzlich einen Riesen-SCC),
- **SPFA mit Null-Initialisierung: 810.530 Relaxationen** (Loop: 808k), Ergebnis
  **W* = 92**: ein Potential in `[-92, 0]`, das jede Kante erfüllt. Die
  Loop-Prüfung meldet 0 Verletzungen auf 1.048.458 Kanten; die eigene
  Nachrechnung (0 Verletzungen) lief auf der Kantenmenge ohne die letzte
  Blocktransition und wurde nach deren Identifikation um die Out-Grad-Zählung
  ergänzt.
- **Zeugenpfad: 23 Knoten, Kantensumme -92**, doppelt belegt: Die eigene SPFA
  liefert einen solchen Pfad, und der gespeicherte Zertifikatspfad
  (`data/antihydra-wide92-cert.json`, `potential_range [92,0]`) ist in diesem
  Bericht gegen die eingefrorenen Übergangsstatistiken nachgerechnet: mit der
  Knoten-Kodierung `r | s<<8 | t<<16` (little-endian) sind alle 23 Knoten
  beobachtete 2-Byte-Zustände, alle 22 Kanten im nachgerechneten Walk als
  3-Byte-Übergänge vorhanden und die Kantensumme exakt -92. Damit ist
  `W* ≥ 92` zweifach und `W* ≤ 92` über das Potential belegt.

Astra-Korrektur aus R14, mathematisch sauber: die minimale Potentialbreite ist
`max_Q (-Σ_{e∈Q} w(e))` über alle gerichteten Wege, **nicht** das maximale
Zyklusgewicht; Null-Init-SPFA liefert bei vollständiger Relaxation bereits das
optimale Potential. Der Vergleich mit der Chronologie:

    L_chron = 73  ≤  W*_3Byte = 92,

**Gap 19** = zusätzlicher maximaler Defizitbedarf der 3-Byte-Abstraktion
(Rekombinationsverlust: der Quotientengraph darf Vorgeschichten und
Fortsetzungen verschiedener Vorkommen desselben Typs kombinieren; auf 2^20
Jumps ist die Datenlage dünn: 2^24 mögliche Typen).

### 4.7 Die Verfeinerung (r,s,t,D): Breite exakt 73 (R15)

Astras konstruktive Antwort auf den Gap: mit dem Drawdown als Zustandskomponente,
`D_{i+1} = max(0, D_i - c_i)` und `p(r,s,t,D) = -D`, ist `p` ein Potential auf dem
**verfeinerten** Graphen, weil

    p_{i+1} = min(0, p_i + c_i) ≤ p_i + c_i

punktweise gilt (Nachrechnung dieses Berichts: die Ungleichung folgt kantenweise
aus `D' = max(0, D - c)`; die obere Schranke ist algebraisch, die untere liefert
der beobachtete Defizitpfad). Da `D` ganzzahlig in `{0,...,73}` liegt, hat das
Potential Breite **exakt 73**, also höchstens 74 Zustände je 3-Byte-Typ (Astra).
Damit ist die statische Potentialroute nicht prinzipiell unmöglich: sie ist
**historienabhängig** repariert. Die offene Arbeit wandert damit vollständig in die
Erreichbarkeitsfrage: zu zeigen wäre, dass `D` auf keinem zulässigen Lauf über 73
steigt, was exakt die ursprüngliche Schwierigkeit ist.

### 4.8 Was vom Lean-Satz bleibt (V20)

Der einzige kern-geprüfte Satz des Loops ist die Halt-Familie aus Astras R3-Beweis
(`halt_family` in `lean/antihydra-family`, Lean 4.33.1, ohne mathlib, keine
`sorry`/`admit`, Axiome nur `[propext, Quot.sound]`): Für jedes `k ≥ 3` hält
`(k-1, 2^k - 3)` nach genau `k-1` legalen Übergängen, mit `b_i + 3 = 3^i·2^{k-i}`
und ungeradem `b_i`. Das ist ein Satz über konstruierte Starts, nicht über die
Leerband-Bahn; sein Strukturwert im Loop ist negativ: Es zeigt, dass beliebig lange
Ungeraden-Läufe existieren, also **jede** start-unabhängige Dichte-Schranke falsch
wäre. Der Loop-Ablauf Astra-Beweis → Lean-Übersetzung → Kaltreview ist der Beleg,
dass die Formalisierungs-Pipeline des Repos für den nächsten Lean-tauglichen
Kandidaten bereitsteht.

### 4.9 Rundenschluss R16-R18: Minimalziel, Abschwächungen, Endbilanz

- **Präzises Minimalziel** (R16/R17): Gesucht ist für alle `k ≥ 6` eine der beiden
  Bedingungen `(D−) r_{k+1} ≥ 2·r_k − 500·2^{k/2}` oder
  `(P) r_{k+2} ≥ 4·r_k − 500·2^{3k/4}`, mit dem Defekt
  `p_{j,k} = (r_{j,k+2} − 4·r_{j,k})/10 = 10^{-1}·D_{j,k}`.
- **(P) ist strikt schwächer als (D−):** (D−) impliziert (P) für `k ≥ 8`
  (zwei Schritte ergeben den Faktor `500·(2+√2)` gegen `500·2^{k/4}`; für `k ≥ 8`
  ist `2^{k/4} ≥ 2+√2`; Arithmetik nachgerechnet), die Umkehrung ist falsch
  (alternierende Folge, Astra-Konstruktion).
- **Probabilistisches Theorem (Astra R16):** Für Haar-zufällige 2-adische Starts
  gilt (P) für alle `j`, `k ≥ 6` mit Wahrscheinlichkeit > 99,83%; Hoeffding
  liefert pro Verletzung `exp(−(125/128)·2^{k/2})`, die vereinigte Schranke ist
  `4·Σ_{k≥6} exp(−(125/128)·2^{k/2}) < 0,0017`. **Grenze, von Astra selbst so
  formuliert:** der feste Start 8 (und jeder gewöhnliche ganzzahlige Start) hat
  Haar-Maß null; das ist keine Aussage über unseren Orbit, sondern eine Aussage
  über zufällige Starts.
- **(S), die seed-genügende Budgetbedingung:** mit dem normierten Verlust
  `ℓ_{j,k} = (5/(2L_k))·[−p_{j,k}]_+` genügt
  `Σ_{h≥0} ℓ_{j,K+2h} ≤ 2/5` für `K ∈ {7,8}`; dann gilt
  `u ≥ 0,491226196… − 0,4 > 1/12`. Die Schwelle stammt aus
  `r_{j,8} = (130377, 128772, 130827, 130847)`, also
  `min u = 128772/262144 = 0,491226196…` (in diesem Bericht nachgerechnet).
  (S) erlaubt einzelne beliebig große (P)-Verletzungen, solange das normierte
  Gesamtbudget eingehalten wird; es ist damit das schwächste deterministische
  Ziel für denselben Orbit.
- **Datenpunkt Out-Grad** (Verifikationsseite; in diesem Bericht nachgerechnet
  aus den 2^23-Daten): Der beobachtete 3-Byte-Graph hat die Gradverteilung
  `{1: 985683, 2: 30328, 3: 697, 4: 7}` (Summe 1.048.458 Kanten, identisch mit
  dem Loop-Log; enthält die letzte Blocktransition); carry-vollständig wären
  256 Ausgänge je Zustand. Die niedrigen Grade messen die Abstraktionsarmut
  des 3-Byte-Quotienten: die beobachtete Bahn realisiert fast nur je einen
  Nachfolger pro Typ.
- **Exakte Sätze aus R18** (Carry-Rekursion, Bijektion und D-Tabelle in diesem
  Bericht nachgerechnet; die übrigen Aussagen als Astra-Ergebnisse zitiert):
  - vollständige Carry-Rekursion: mit `u = x mod 2^24` und `c = bit24(x)` ist
    `u' = (⌊3u/2⌋ + 2^23·c) mod 2^24`; das nächste Carry-Bit folgt als
    `c' = (d + c + v) mod 2` mit `d = bit25(x)` und dem Übertrag
    `v = ⌊(3u + 2^24·c)/2^25⌋`; der 24-Bit-Zustand ist **nicht autonom**,
    es wird sukzessive das nächste höhere Bit gebraucht;
  - Paritätswort ↔ Restklassen-Bijektion (256/256 nachgerechnet);
  - exakte Vier-Skalen-Blockrekursion
    `D_{i,k+4} = Σ_{a=0}^{15} D_{16i+a,k}` (unendliche Matrix `M`); die direkte
    endliche Blockprojektion ist nicht abgeschlossen;
  - jede 4D-finit-verzweigte affine Defektrekursion scheitert: explizite
    zulässige Fortsetzungen heben den Defekt auf Größenordnung `2^k`
    (`z_k = 0` führt zu `z_{k+4} = −320L = −327680·2^k` bei `L = 1024·2^k`);
  - (P)/(D−) exakt für `k = 6,7,8`; D-Tabelle (nachgerechnet, identisch):
    `k=6: (−255, 1660, 895, 3135)`, `k=7: (4800, −4060, −425, −530)`,
    `k=8: (2640, 10245, −2920, −2570)`.
- **Endbilanz:** Der Engpass ist exakt eine **endliche, orbit-spezifische
  Kompression der Carry-Korrelationen des festen Starts 8**, die die sublineare
  negative Defektschranke erzwingt. Alle anderen Varianten (D−/P/S, Potentiale,
  feste Typen, Höhe, Bilanz) sind abgearbeitet oder ausgeschlossen; ein
  Zertifikat existiert nicht.

## 5. Negative Ergebnisse (was definitiv gestorben ist)

1. **Universelle Dichte-Schranken** über alle Starts: tot durch die Halt-Familie
   (R2/R3, kernel-geprüft in V20).
2. **Feste Modul-Zertifikate** (Zugehörigkeit nur von `(A, b mod 2^m)` abhängig):
   tot durch Astras Negativsatz in R3.
3. **Die Höhen-Bedingung (W)** (`A+7-t ≥ 2·floor(log2(3b'+10))`): REFUTED, alle
   523.720 geprüften Rückkehrpunkte negativ, Minimum -704176 (R4).
4. **Kantenweise 2-Byte-Potentiale:** tot (3 negative Selbstschleifen + 30
   negative 2-Zyklen auf der beobachteten Bahn; §4.5).
5. **Unbeschränkter 2-Byte-Graph:** tot (negative Selbstschleife `(1,0)`, §4.5).
6. **Potential der Breite 73 auf dem reinen 3-Byte-Typ:** tot (W* = 92 > 73; §4.6).
   Wer Breite 73 will, muss Information mitführen (Drawdown, §4.7).

Das Muster quer über die Runden: **jede lokale oder universelle
Zertifikatsfamilie starb**; überlebt haben ausschließlich orbit-spezifische bzw.
über zukünftige Rückkehren quantifizierende Kriterien (D-Reserven auf der echten
Bahn, V, die offene Erhaltungs-Ungleichung). Genau darauf zielt die verbleibende
offene Aussage.

## 6. Die offene Kernaussage (präzise)

Der gesamte Angriff reduziert sich auf eine einzige Aussage (Astra R15, hier
formal nachvollzogen):

> Sei `c_i = g(r_i)` das Blockgewicht entlang eines zulässigen Laufs aus `x0 = 8`,
> `R_0 = 73` und `R_{i+1} = min(73, R_i + c_i)`. Dann gilt `R_i + c_i ≥ 0` für
> alle `i`, d.h. der Fehlerzustand `⊥` (Reserveüberlauf unter null) ist auf keinem
> zulässigen Lauf erreichbar.

Äquivalent (`D_i = 73 - R_i`): der kumulierte Drawdown der Blockgewichte bleibt
für **jedes** zusammenhängende Teilintervall der Bahn `≤ 73`; äquivalent: die
Nicht-Halte-Frage der reduzierten Regel ist an dieser Stelle äquivalent zur
Schranke. Die Zahl 73 ist dabei eine **Messgröße dieses Fensters** (2^23 Schritte,
1.048.576 Blöcke); ihre Gültigkeit für längere Läufe ist unbewiesen und Teil der
Aussage.

**Skalen-Form des Minimalziels (Runde 16, dies ist die zuletzt fixierte
Forderung).** Auf der Skalenebene genügt für alle `k ≥ 6` eine der beiden
Bedingungen: `(D−) r_{k+1} ≥ 2·r_k − 500·2^{k/2}` oder die strikt schwächere
Variante `(P) r_{k+2} ≥ 4·r_k − 500·2^{3k/4}`; es genügt sogar das normierte
Gesamtverlustbudget `(S) Σ_{h≥0} ℓ_{j,K+2h} ≤ 2/5` für `K ∈ {7,8}` (Details in
§4.9). Aus den Seeds (`min u = 128772/262144 = 0,491226196…`) folgt daraus die
Reserve-Nichtnegativität auf allen Skalen.

**Warum das der harte Engpass ist (Runde 18).** Die naheliegenden finiten
Kompressionen sind ausgeschlossen: der 24-Bit-Zustand ist nicht autonom (das
nächste Carry-Bit wird gebraucht), die direkte endliche Blockprojektion der
Vier-Skalen-Rekursion ist nicht abgeschlossen, und jede 4D-finit-verzweigte
affine Defektrekursion scheitert an expliziten zulässigen Fortsetzungen
(Größenordnung `2^k`). Gesucht bleibt genau eine endliche, orbit-spezifische
Kompression der Carry-Korrelationen des festen Starts 8, die die sublineare
negative Defektschranke erzwingt. Ein Zertifikat dafür existiert nicht.

Eine **Widerlegung** dieser Aussage wäre konkret: ein endliches Intervall
zusammenhängender Blöcke (oder ein zulässiger Startzustand) mit kumuliertem
Defizit größer 73, also `S_b - S_a < -73` für `a < b`; auf der Skalenebene ein
`spezifisches k` mit verletzter (D−)/(P)-Ungleichung; oder ein erreichbarer
Fehlerzustand im 74-Zustands-Monitor. Bisher geprüft: 2^23 Schritte
(1.048.576 Blöcke) ohne Verletzung; Maximum exakt 73.

**Was diese Aussage nicht ist:** kein Beweis von Antihydra, keine Schranke für
andere Startwerte, kein Beweis der Unendlichkeit der Bahn. Sie ist das präzise
Endprodukt des Loops: die vollständige Lokalisierung der Lücke.

## 7. Grenzen (ehrlich)

1. **Kein Lösungsergebnis.** Antihydra bleibt offen; die Kernaussage aus §6 ist
   unbewiesen.
2. **Endliche Fenster:** Alle Orbit-Zahlen gelten für die ersten 2^23 Schritte
   (und frühere Läufe bis 2^20/2^21/2^22); "Drawdown 73" ist ein gemessenes
   Maximum, keine Schranke.
3. **W* = 92 gilt für den beobachteten Graphen** (1.016.715 Knoten aus 2^20
   Jumps). Astra weist ausdrücklich darauf hin, dass daraus kein universeller
   No-go-Satz für andere Byte-Zahlen folgt und dass ein positiver Befund auf
   dünner Datenlage vorsichtig zu lesen ist.
4. **Zertifikat vs. Beweis:** `data/antihydra-wide92-cert.json` zertifiziert die
   Potentialbreite 92 auf dem eingefrorenen beobachteten Graphen; es beweist keine
   Aussage über alle zulässigen Läufe.
5. **Rohdatenvollständigkeit:** `astra-antihydra-r2.json` fehlt (nie gespeichert);
   die Rundenprotokolle der Verifikationsseite liegen als Session-Protokoll vor,
   nicht als Repo-Datei.
6. **Nicht im Repo:** die Paritätsdateien der tiefen Läufe (je 1-8 MB) und die
   22,6-MB-Carry-Statistik; stattdessen sind Digests dokumentiert
   (`carry8-stats.json`: `sha256 = 2b7c154d773a52ac9aa27803b3616457181b6b5a8fe69604dcb7224dfad04c99`)
   und die Dateien über `tools/fast_orbit.py` bit-identisch reproduzierbar (§4.3).
7. **Nachrechnung dieses Berichts** ist eine Stichprobe (Walk aus x0=8, 8-Schritt-
   Blöcke, SPFA mit Null-Init, exakte Ganzzahlen), kein unabhängiges Modell:
   dieselben Definitionen, nachgerechnet außerhalb der Loop-Session. Ein
   unabhängiger Beweis ist sie nicht.
8. **Das probabilistische (P)-Theorem** (R16) gilt für Haar-zufällige 2-adische
   Starts; der feste Start 8 hat Haar-Maß null, die Aussage bezieht sich nicht
   auf ihn.

## 8. Artefakte, Nachrechnung und Kommandos

| Artefakt | Inhalt | Kommando / Quelle |
|---|---|---|
| `tools/fast_orbit.py` | schneller Orbit-Generator (Transfer-Identität, w konfigurierbar) | `python3 yesdocs/formal-conjectures/tools/fast_orbit.py 8388608 -w 18 -o bits.bin` |
| `tools/test_fast_orbit.py` | 11 Tests: Identität, Fast-vs-Naiv 2^14 (w=16/18), x_end, Statistik, CLI | `python3 -m unittest discover -s yesdocs/formal-conjectures/tools -p "test_fast_orbit.py"` |
| `data/antihydra-wide92-cert.json` | Potentialbreite 92, Zeugenpfad 23 Knoten / -92 | Zertifikat (288 B, sha256 siehe Anker) |
| `data/astra-antihydra-rounds/` | 17 Rohantworten R1, R3..R18 + Provenienz-README | Beweismaterial des Loops (r2 fehlt) |
| `data/attack-02-check.txt` | [COMMIT]/[COMPUTE]/[ARTIFACT]-Anker dieses Berichts | `python3 -m bemyself check --report yesdocs/formal-conjectures/data/attack-02-check.txt --repo . --strict --allow "python3 yesdocs/formal-conjectures/tools/fast_orbit.py"` |

Das vollständige Verdikt-Protokoll dieses Prüflaufs steht in
`data/attack-02-check.verdicts.txt` (26 CONFIRMED, 0 REFUTED, 0 UNVERIFIABLE).

**Re-Pin-Konvention (Tripwire).** Die Anker binden die genannten Dateien; wer
eine davon ändert, zieht die betroffenen `[ARTIFACT]`-Digests in `README.md`,
`attack-02.md` und `data/attack-02-check.txt` im **selben Commit** nach
(Hash-Nachzug). Wer nur den Bericht ändert, erneuert
`[ARTIFACT: yesdocs/formal-conjectures/attack-02.md]` in `attack-02-check.txt`.
Die `[COMPUTE]`-Digests hängen allein am `[COMMIT]`-Pin und bleiben stabil,
solange das Werkzeug in diesem Commit unverändert bleibt.

### Nachrechnung dieses Berichts (Stichproben aus den eingefrorenen Artefakten)

- Aus `/tmp/opencode/antihydra-bits-2p{20,21,22,23}.bin`: `H(2^22)=2091252`,
  `H(2^23)=4181939`; Drawdown 73 (Peak/Trough-Blöcke 294573/294586) auf dem
  2^23-Walk; Drawdown 67 auf 2^20.
- Aus den bits-2p23-Daten rekonstruierter exakter Walk (x0=8, 8-Schritt-Blöcke):
  2-Byte-Zeugen (3 Selbstschleifen, 30 Zyklen), 3-Byte-Graph
  (1.016.715 Knoten, 1.048.458 Kanten inkl. letzter Blocktransition,
  0 Kantenverletzungen), SPFA W*=92 (810.530 Relaxationen),
  23-Knoten-Zeugenpfad mit Summe -92.
- Reserven/q/D±/(P)/Dichte bis k=10 aus denselben bits (0 Verletzungen).
- Runden 16-18: D-Tabelle k=6..8 exakt; Paritätswort-Bijektion 256/256;
  Carry-Rekursion `u' = (⌊3u/2⌋ + 2^23·c) mod 2^24` bit-genau; (S)-Schwelle
  128772/262144; 3-Byte-Gradverteilung `{1: 985683, 2: 30328, 3: 697, 4: 7}`.
- Werkzeug-Reproduktion: `sha256` der Bits für 2^20, 2^22 und 2^23 bit-identisch
  mit den Loop-Dateien (2^23: `f1708bed...3ff0`, 107,7 s mit w=18).

### Anker

Die folgenden Marker binden dieses Dokument an den Artefakt-Commit; der
Prüfbefehl steht in `data/attack-02-check.txt`.

[COMMIT: 7c0c1288d5328ee066db52dbd17e58e28fae04f8]

# Werkzeug-Reproduktion (deterministische Ausgabe, w-unabhängig;
# der Bits-Digest 2^20 stimmt mit dem Loop-Artefakt überein)
[COMPUTE: python3 yesdocs/formal-conjectures/tools/fast_orbit.py 1048576 -w 16 --quiet --no-bits -> 30076fd8cddeeef5030b0c58912021d7daabce307fc6bb3e05a0287f45dd4f1c]
[COMPUTE: python3 yesdocs/formal-conjectures/tools/fast_orbit.py 1048576 -w 18 --quiet --no-bits -> b5732bf33ecac1bc2387de075397f7383781a16482ce5a81a27ba63bb52943d6]

# Eingefrorene Artefakte
[ARTIFACT: yesdocs/formal-conjectures/tools/fast_orbit.py -> 2847c491937a83fad673fddb665cd5352dd2066a125a55356ef4be00c5101e59]
[ARTIFACT: yesdocs/formal-conjectures/tools/test_fast_orbit.py -> 60ae388d4a3ab926681a61d50852e45e5f82ecc4241bec9637bf1ebd80c86cc0]
[ARTIFACT: yesdocs/formal-conjectures/data/antihydra-wide92-cert.json -> f28e9fcabcc45aa6a421423527af345005b19f6df18de34d6d02cef4c4eb5010]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/README.md -> 8e32c92ac90630436073e447dde5265fa295da47099d2fd46baa454314e7e3b9]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r1.json -> 8fde219ecb93fc8017183af8df3b3552383ccf5f723f327077f8ec7b9cc91269]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r3.json -> 9ced79cd5afa6bdfbea60d61c2e10bd85d5105381ac0c15eca3aee22ca3b8ae1]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r4.json -> 8d233e61909cfa82b71d6fceb1cf41f9fbf41a3cea486c7380a74a6305f641c7]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r5.json -> d37e7c3e59ac7739c3b39f4ca1074d8a3bf6430c22f25a239a95542f525736f9]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r6.json -> eb90007ae054ee3f4300ec8e62ea53dd2fb90c681c873c77e48193611ca75f29]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r7.json -> e947d8dee87ebb628cbf5a06d1b3ffbb0114f4bea84f59c5f724fd90c44360e1]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r8.json -> 30e14cb52ab263dfd34b8483406adbcf13cda24e396d27f679f1119857d03739]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r9.json -> 136b51668c22dbcfa8d29a55538d23795fdab128d678bdd7e751079e7bce288b]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r10.json -> 70cbab419d5904904de9a166f88db9c96249a9aa4999a490b55f197f835416da]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r11.json -> 1f5781b429d7236ff8eef873cfbf21b30c91363ff64ca0a2963d80028b501c53]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r12.json -> cf798134411e050ebd656e3699b3b2f86d540bfb0b0ebb43a00f8adea98f5a35]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r13.json -> c39fb5779616160e31ba6316e7986f55cda48ff9356ea9157df6d297f85228dd]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r14.json -> dcca7306fce3af676be5d0afd483efa093a02e1ee34acfcb85f5a7323745f0f6]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r15.json -> edbcc77812c7481a1ff74c4cbead37345351a579408ac54cd02fde00840614f0]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r16.json -> 124940a6c9d78ae0cb20c6e163feecef1764ed0dedbb65c36dd304a5bef6e7de]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r17.json -> 8c1f423bd8f8465a0c35ec47e9771abc60989d3fd931a220570d631158fb5b87]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r18.json -> 92608fa3f985580b09105d789de4237fee7d7e461be0dd86accd7bc62c676c82]

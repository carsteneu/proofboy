# Angriff 02 - Antihydra im Lemma-Loop mit Fremdmodell (Runden 1-33)

Datum: 2026-09-14. Ausgangsbasis: `master` @ `a35a3d1`. Vorgeschichte: `attack-01.md`
(V17: beidseitige Reduktions-Verifikation, Roh-TM-2^32-Lauf, Strukturjagd),
`lean/antihydra-family` (V20: kernel-geprüfte Halt-Familie) und die BMO#2-Passage in
`README.md`. Dieser Bericht friert den Stand eines 18-rundigen Lemma-Loops ein
(Runden 1-18, Stand 2026-09-14 00:23): Ein externes Modell (`gpt-6-astra`) lieferte
Kandidat-Aussagen, die Verifikationsseite dieses Repos hat jede davon endlich
nachgerechnet, widerlegt oder präzisiert; die Rohantworten liegen in
`data/astra-antihydra-rounds/`.

Der **Nachtrag 2026-09-14 (V22)** setzt den Loop bis Runde 28 fort
(Counter-Engine, Rangkette bis d ≤ 12, nichtlineare Invariante; Basis `master`
@ `71c89e1`). §§1-8 bleiben der eingefrorene V21-Stand; die Fortsetzung steht
in §N.1 bis §N.7 am Dateiende.

Der **Nachtrag 2026-09-14 (V23)** setzt den Loop bis Runde 33 fort (Runden
29-33, 2026-09-14 09:25 bis 12:09; Basis `master` @ `d617207`): Falsifikation
und Refit des (N)-Radius, C-Kernel mit Kreuzverifikation,
Epoch-Quantor-Entscheidung samt Korrektur der (S)→H-Schlusskette in §4.9/§6.
§N.1-§N.7 bleiben der eingefrorene V22-Stand; die Fortsetzung steht in §O.1
bis §O.7 am Dateiende.

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

Umfang: Runden 1-18 (Nachträge: Runden 19-28 und 29-33), 2026-09-13 18:55 bis 2026-09-14 12:09. Token-Budget: 10.000.000
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
- **Überholt (V23-Nachtrag, §O.4):** Die Folgerung `u ≥ 0,491226196… − 0,4 >
  1/12` trägt nur die `1/12`-Barriere für den **Halt-Zähler** `C = 2E−O`; für
  `H ≥ 0` im Zellinneren ist im Zellmittel-Bild `a > 3/11` nötig. Korrigierte
  Fassung und vollständige Epoch-only-Reparatur: §O.4.
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

**Überholt (V23-Nachtrag, §O.4).** Diese Schlussfolgerung ist unvollständig:
(S) stützt die `1/12`-Schwelle nur für den Halt-Zähler `C = 2E−O`; für
`H ≥ 0` im Zellinneren ist `a > 3/11` nötig. Vollständige Epoch-only-Reparatur
(Gesamtverlust `< 0,2184989…` oder durchgehendes Epoch-(P) mit 500 plus Seeds
beider Paritäten plus endlicher Anfangscheck) in §O.4.

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
| `data/astra-antihydra-rounds/` | 32 Rohantworten R1, R3..R33 + Provenienz-README | Beweismaterial des Loops (r2 fehlt; R19-28 im V22-Nachtrag, R29-33 im V23-Nachtrag) |
| `data/attack-02-check.txt` | [COMMIT]/[COMPUTE]/[ARTIFACT]-Anker dieses Berichts | `python3 -m bemyself check --report yesdocs/formal-conjectures/data/attack-02-check.txt --repo . --strict --allow "python3 yesdocs/formal-conjectures/tools/fast_orbit.py"` |

Das vollständige Verdikt-Protokoll steht in
`data/attack-02-check.verdicts.txt` — V21-Stand: 26 CONFIRMED, 0 REFUTED,
0 UNVERIFIABLE; mit den Ankern des V22-Nachtrags: 41 CONFIRMED, 0 REFUTED,
0 UNVERIFIABLE; mit den Ankern des V23-Nachtrags: 46 CONFIRMED, 0 REFUTED,
0 UNVERIFIABLE.

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
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/README.md -> b05fac7fc3996b3d3b564c3dffec03dc5070906794642b02c2a4f44946956758]
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

---

## Nachtrag 2026-09-14 (V22): Counter-Engine, Rangkette bis d ≤ 12, nichtlineare Invariante

Basis: `master` @ `71c89e1` (V21-Merge). Dieser Nachtrag setzt den in §§1-8
eingefrorenen Stand fort (Runden 19-28, 2026-09-14 00:32 bis 08:01). Drei
Ergebnisblöcke: (i) die **Counter-Engine** des Repos ersetzt den Bit-Generator
als Messinstrument, (ii) die **orbit-spezifische lineare Kompression (L) ist
für d ≤ 12 exakt ausgeschlossen** (und die mod-2-Kandidatenrelation R0 ist
widerlegt), (iii) die **nichtlineare Invariante (N)** hält mit eingefrorenem
exaktem Radius auf allen geprüften Zellen; die α-Messung (0,4644) wird zur
priorisierten Zielform präzisiert. Rohdaten: zehn weitere Antwortdateien
`astra-antihydra-r{19..28}.json` (Empfang 00:32-08:01).

**Kein Lösungsergebnis.** Alle Aussagen sind endliche Zertifikate auf
präfixweise exakten Läufen; „für beliebiges d ist (L) nicht bewiesen“ gilt
für jede Ausschlusszeile dieses Nachtrags.

### N.1 Rundenchronik R19-R28

| Runde | Astra liefert | Verifikation (dieses Repo) | Ergebnis |
|---|---|---|---|
| R19 (00:32) | Summenbaum D = 5·Σq_n (q_n ∈ {−4..4}); Kandidat (L); Polyederzertifikat (M⁴/8)K ⊆ K; Haar-Martingal | D-Darstellung übernommen (konstante Terme heben sich exakt); 4×4-Rangtest: det ≡ 2 (mod 3), Werte identisch mit r19 | d ≤ 3 ausgeschlossen; (L) präzise formuliert |
| R20 (00:45) | Bewertung des Ranganstiegs 4→5; Bellman-Potential-Format (endlicher gewichteter Zustandsgraph + summierbares Fehlerbudget); kumulierte normierte Defekte | 12×5-Matrix vollständig, ein ungerader 5×5-Minor; Rang 5 | d ≤ 4 ausgeschlossen |
| R21 (01:24) | (L) ⇔ P(A)f = 0 (Summenoperator A f(i) = f(2i)+f(2i+1)); Haar-fast-sicher kein endliches (L); Vier-Kontrast-Zustand Δ_r | 7×6-Matrix: Rang 6; Bijektions-/Nullmengen-Argument nachvollzogen | d ≤ 5 ausgeschlossen |
| R22 (03:36) | K6-Kongruenz h₆ ≡ Σ a_r h_r (mod 2) + 2-adischer Lift [h₀..h₅, g]; (N)-Testprotokoll (Training/Validierung, R_crit) | 2^26-Lauf: 8×7-Matrix Rang 7 über Q; K6 (eindeutige Relation h₆ ≡ h₃ mod 2, Zeilen 4..11) hält bis i = 12, verletzt ab i = 13 (1/4 im Fenster 12..15); Lift-Rang 6/7 | K6 widerlegt; d ≤ 6 ausgeschlossen; (N) spezifiziert |
| R23 (03:40) | (N)-Konsistenz-Audit: max\|z\| = 0,0436 unvereinbar mit R² = 703,44; exakter Integer-Test; 508 Frontier-Zellen; Nicht-Nachfitten-Regel | Audit ergab einen eigenen Auswertungsfehler (fehlende None-Guards → stilles Index-Truncaten); Korrektur auf R² = 1309875575/347892350976; Extremzelle (14,4) exakt auditiert | früherer (N)-Fit war ein Artefakt; Radius exakt eingefroren |
| R24 (03:44) | Bewertung der Korrektur; f-Identität z(i,4+m) = (2/3)^m·Σ_{r<2^m} f(2^m·i+r); (K_h)-Kriterium; Q-Wert; Gültigkeitsguard | 64 gültige Transitionen (2^26-Fenster): 0 Verletzungen unter dem exakten Radius | (N) auf Fitdaten bestätigt |
| R25 (06:41) | Counter-Engine-Ökonomie; Rangkette bis d = 12 abschließen, dann pausieren; Brücke D(i,k)/5 = (A_{i,k+2} − 4A_{i,k})/3; verschachtelte Zeugen W_d(j); (N)-Sicherheitsabstände; α-Methodik | Brücke exakt (D ≡ 0 (mod 5), H = D/5 ganzzahlig nachgerechnet); Tiefen-Buchhaltung: Tiefe 33 für d = 12 nötig, nicht 40 | d ≤ 9 ausgeschlossen (Tiefe 29) |
| R26 (07:00) | Baum allein erzwingt R0 nicht; Fortpflanzung R_{s+1}(i) = R_s(2i) ⊕ R_s(2i+1); Halbierte Spalte H̃_{·,8} = (H₈+H₂+H₃+H₄+H₆)/2 mit det H = 2·det H̃; XOR-Invariante J_N | Halbierungstest d = 10: transformierte Matrix mod 2 voll (11/11) → det ≡ 2 (mod 4); R0-Kern c₀ aus dem Rangbild extrahiert | 2-adischer Witness; R0-Widerlegung vorbereitet |
| R27 (07:59) | Quotientenbild mod 2: W = span{r₄..r₁₅}, dim W = 11, dim 𝔽₂¹³/W = 2; Signaturen (1,0)/(0,1)/(1,1); Abschlussabsatz der linearen Route; α-Kalibrierung; Transfersperre (D sieht C-Geradenanteil nicht) | R0-Sweep (Tiefe 32): 0 für i ≤ 15, Treffer ab i = 16, 135/252 in i = 4..255; Zusatzzeilen {16,20} vervollständigen den mod-2-Rang; Signaturen i = 16..24 tabelliert | R0 widerlegt; d ≤ 12 ausgeschlossen (Tiefen bis 33); mod-2-Defekt ist fensterbedingt |
| R28 (08:01) | Quotientenmechanismus für d = 12 vollständig bestätigt; Abschlussformulierung; Fortsetzungsalgorithmus d ≥ 13; α-Zielform als Priorität | d = 12 (Tiefe 33): Rang 13/13 über Q, mod 3/7/11/13 voll; ungerader 13×13-Minor (Zeilen 4..14,16,20) | d ≤ 12 ausgeschlossen; Rangkette pausiert |

Zwei Runden verdienen — wie ihre Vorläufer R4/R5 in §3 — eine Hervorhebung:

- **R23 war ein echter Fehler auf unserer Seite, von Astra entdeckt.** Der
  gemeldete Fit-Radius R² = 703,44 war mit dem gemeldeten Maximum
  max|z| = 0,0436 unvereinbar (jeder zulässige Radius muss
  ≤ 3·max|z|² ≈ 0,0057 sein). Die Nachrechnung zeigte: unser C(i,k)-Helfer
  ließ bei Indexüberläufen die None-Guards fallen, und Python-Slices
  truncaten still — das Extremum war Müll. Der korrigierte Radius ist exakt
  R² = 1309875575/347892350976, definiert durch Gleichheit an der Zelle
  (14,4) (§N.4).
- **R26-R28 war der Übergang von „Rangdefekt" zu einem vollständigen
  Quotientenbild.** Der mod-2-Defekt der Spaltenmatrix ist kein Hindernis,
  sondern ein zweidimensionaler Quotient mit drei Signaturen; zwei
  verschiedene nichtverschwindende Signaturen (z. B. {16,20}) liefern
  vollen Rang über 𝔽₂ und damit einen ganzzahligen Minor mit ungerader
  Determinante (Astra R27).

### N.2 Die Counter-Engine (Werkzeug)

`bemyself/experiments/antihydra_deep.py` (seit V17 im Repo, 16 Tests) ist
der exakte Tiefzähler: die Block-Divide-and-Conquer-Methode aus dem
bbchallenge-Forum (mxdys) mit libgmp über ctypes (CPython-Fallback), gegen
die naive Rekurrenz verifiziert. Im Loop wird die Checkpoint-Option
(`--also <n>` / `extra_targets`) zum **Messinstrument**: die Engine liefert
den Zähler 3E(n) − n an beliebigen Checkpoints n, ohne Paritätsbits zu
materialisieren; aus den Blockendpunkt-Zählern folgen über
E(n) = (counter(n) + n)/3 alle Berichtsgrößen C, D, H, z.

Validierung (in diesem Nachtrag aus den eingefrorenen Bit-Dateien
nachgerechnet): counter(3.145.728) = 1.569.705 und counter(2^22) = 2.093.612
sind exakt gleich den aus den Bits gerechneten Werten (E(3.145.728) =
1.571.811; E(2^22) = 2.095.972, der §4.2-Wert). Zusätzlich stimmen alle für
die d=6-Matrix benötigten C(i,k) aus dem 2^26-Bitlauf und aus der Engine
paarweise exakt überein.

Messungen (Repo-Werkzeug `tools/deep_rank_chain.py`): d = 7 (Tiefe 27,
185 Ziele): 40 s; d = 8 (Tiefe 28, 198 Ziele): 83 s; d = 9 (T 29, 211): 167 s;
d = 10 (T 30, 224): 350 s; d = 11 (T 31, 237): 726 s; d = 12 (T 33, 263):
3.217 s. Zum Vergleich der Bit-Generator: 2^25 brauchte 1.975 s, 2^26
7.681 s (quadratisch skaliert — 2^27 hätte bei ≈ 8,5 h gelegen; der
Bitlauf für 2^27, Start 03:31, wurde nicht abgewartet). Die Engine rechnet
dieselbe Tiefe 28 in 83 s.

### N.3 Rangkette: (L) ist für d ≤ 12 exakt ausgeschlossen

Gegenstand ist die orbit-spezifische lineare Kompression

    (L)  D(i,4+d) = Σ_{r<d} c_r·D(i,4+r)   für alle i ≥ 4

mit von i und k unabhängigen rationalen Koeffizienten (nur für x₀ = 8
behauptet, keine Aussage über andere Starts). Äquivalent (R21): P(A)f = 0
für ein monisches Polynom P, mit f(i) = D(i,4)/5 und
H_{i,m} = (A^m f)(i). Test: die (d+1)×(d+1)-Matrix H_{i,m} = D(i,4+m)/5,
i = 4..4+d; voller Spaltenrang schließt (L) aus, und ein
nichtverschwindender Minor modulo einer Primzahl ist ein exaktes
vollständiges Zertifikat — er zählt über ℚ und ℝ.

| d | Daten (Tiefe) | Rang über ℚ | mod 2 | Zeuge (natürlicher Minor, Zeilen 4..4+d) |
|---|---|---|---|---|
| 3 | 2^23 (R19) | 4/4 | 3/4 | det ≡ 2 (mod 3) |
| 4 | 2^24 (R20) | 5/5 | 4/5 | det ≡ 1 (mod 3) |
| 5 | 2^25 (R21) | 6/6 | 6/6 | det ≡ 6 (mod 7), ungerade |
| 6 | 2^26 (03:25) | 7/7 | 6/7 | det ≡ 5 (mod 7) |
| 7 | 27 | 8/8 | 7/8 | det ≡ 3 (mod 7) |
| 8 | 28 | 9/9 | 7/9 | det ≡ 3 (mod 7) |
| 9 | 29 | 10/10 | 9/10 | det ≡ 1 (mod 13) |
| 10 | 30 | 11/11 | 10/11 | det ≡ 8 (mod 11) |
| 11 | 31 | 12/12 | 11/12 | det ≡ 1 (mod 3) |
| 12 | 33 | 13/13 | 12/13 | det ≡ 1 (mod 3), zugleich ≢ 0 (mod 7, 11, 13) |

Alle zehn Zeilen sind aus dem eingefrorenen Dump `data/deep-Cvalues-d12.json`
(Tiefe 33) nachgerechnet; d = 7 und d = 8 zusätzlich frisch mit
`tools/deep_rank_chain.py` gerechnet (40 s / 83 s). **Korrektur zu einem
Nacht-Log:** `antihydra-2p26-rank.log` meldet für d = 6 pauschal
„Rang mod p: 6" für alle p ≤ 19; die mod-p-Schleife des damaligen Skripts
lief nur über 6 der 7 Spalten (`range(6)`). Nachgerechnet aus den
eingefrorenen Daten auf der 8×7-Nachtmatrix (Zeilen 4..11, dieselbe wie im
damaligen Lauf): mod 3/7/11/13/17/19 voll (7/7), nur mod 2 hat den Defekt
6/7; die 7×7-Tabellenmatrix desselben Absatzes hat mod 3 und mod 11
ebenfalls den Defekt 6/7 (det = −2⁴·3²·5·11²·29789385120360739).

**Das mod-2-Binnenbild bei d = 12** (nachgerechnet aus dem Dump): Die Zeilen
r_i = H_{i,·} mod 2, i = 4..15, spannen einen 11-dimensionalen Raum auf; der
Annihilator ist zweidimensional mit Basis

    c₀ = (0,0,1,1,1,0,1,0,1,0,0,0,0)    [die alte R0-Relation: H₂+H₃+H₄+H₆+H₈ ≡ 0]
    c₁ = (0,1,1,0,0,1,0,1,0,0,0,0,1)

Die Signaturen s(i) = (r_i·c₀, r_i·c₁) für i = 16..24:
(1,1), (0,1), (0,0), (0,0), (1,0), (1,1), (0,0), (1,0), (0,0). Zwei
verschiedene nichtverschwindende Signaturen schließen den Quotienten:
{16,20} = (1,1), (1,0) ist voll — die Zeilenmenge {4..14,16,20} ist über 𝔽₂
unabhängig (13 Zeilen) und liefert den Minor mit ungerader Determinante;
{16,21} = (1,1), (1,1) bleibt bei 12/13. **R0-Sweep** (`tools/r0_sweep.py`,
Tiefe 32, i = 4..255; `data/r0-sweep-result.json`): R0(i) = 0 für alle
i ≤ 15, Treffer R0(i) = 1 zuerst 16, 20, 21, 23; insgesamt 135 Treffer in
252 getesteten Zeilen — die vermutete globale Relation R0 ist widerlegt, die
Null-Verlängerung für i ≤ 15 ist ein endliches Fensterphänomen. Laufzeit der
Sweep-Logik: ≈ 3 min bei Tiefe 29 (gemessen, i ≤ 24), der Default Tiefe 32
liegt entsprechend länger; der Tiefe-33-Ranglauf derselben Engine brauchte
3.217 s.

**Halbierte Spalte** (R26): H̃_{·,8} = (H_{·,8}+H_{·,2}+H_{·,3}+H_{·,4}
+H_{·,6})/2 ist auf den Zeilen i ≤ 15 ganzzahlig (dort gilt c₀), und für
jeden quadratischen Minor gilt det H = 2·det H̃. Nachrechnung: d = 9: Rang
der transformierten Matrix mod 2 = 9/10; **d = 10: 11/11 voll** — der
natürliche 11×11-Minor (Zeilen 4..14) hat 2-adische Bewertung 1, d. h.
det ≡ 2 (mod 4); d = 11: 11/12; d = 12: 11/13 (nur 12 Zeilen mit
ganzzahliger H̃-Spalte). Der mod-2-Defekt bei d = 10 ist also genau eine
Zweierpotenz tief; für den vollen Rangnachweis bis d = 12 sind die
Halbierungstests aber durch die Zusatzzeilen und die ungeraden Minoren
überholt (R27).

**Abschlussformulierung der linearen Route** (Astra R28, sinngemäß wörtlich
übernommen):

> Im untersuchten Spaltenmodell sind sämtliche nichttrivialen homogenen
> 𝔽₂-Relationen mit Unterstützung in m = 0,...,12 ausgeschlossen. Ein
> endliches Vollrangzertifikat liegt vor: Aus den Zeilen 4,...,15,16,20
> lassen sich 13 unabhängige auswählen. Damit sind auch alle kleineren
> Spaltenfenster abgedeckt. Eine Ausschließung für beliebiges d ist nicht
> bewiesen.

Bei ganzzahligen Originaleinträgen zertifiziert derselbe ungerade Minor auch
Vollrang über ℚ bzw. ℝ. Astras längere Fassung (R27) ergänzt: die reine
Rangketten-Verlängerung wird nicht weiter priorisiert; höhere Ordnungen und
Beziehungen außerhalb des geprüften Ansatzes bleiben offen; eine quantitative
Wachstumsschranke folgt aus den Rangresultaten nicht.

### N.4 Die nichtlineare Invariante (N)

Definitionen (Astra R22, eingefroren R23/R24): δ(i,k) = D(i,k)/(4·L_k);
z(i,k) = (4/3)^{k−4}·δ(i,k); Zustand s(i,k) = (z(i,k), z(i,k+1));
V(u,v) = u² + v². Die Ungleichung

    (N)  V(s(i,k+1)) ≤ ½·V(s(i,k)) + ½·R²

wird mit dem exakt eingefrorenen Radius

    R² = 1309875575/347892350976  (≈ 0,0037651749…)

getestet; die Anfangsbedingung V(s(i,4)) ≤ R² hält auf allen Zeilen i ≤ 15
(nachgerechnet: Maximum V(s(6,4)) ≈ 0,0022674), und das Maximum T = R² wird
exakt an (i,k) = (14,4) angenommen (Gleichheit, R23).
Der rein ganzzahlige Test (R24): mit P(i,k) = −81·D(i,k)² + 36·D(i,k+1)²
+ 32·D(i,k+2)² gilt (N) ⟺ 4^{k−4}·P(i,k) ≤ 9^{k−4}·1309875575 — ohne jede
Rundungsfrage. Die z-Rekursion (R24) ist exakt:

    z(i,k+1) = (2/3)·(z(2i,k) + z(2i+1,k)).

Zellenstand (aus `data/deep-Cvalues-d12.json`, Testcode
`tools/test_deep_rank_chain.py`): im Fenster bis Tiefe 28 (k ≤ 10 für alle
i ≤ 15, k = 11 für i ≤ 7) sind 88 Zellen valide, mit 0 Verletzungen; mit dem
tieferen Datenstand (Tiefe 33, k = 4..15 für i ≤ 15) sind es 144 Zellen,
weiterhin 0 Verletzungen — das Maximum bleibt exakt R² bei (14,4).

Status: (N) ist ein endlicher Fit auf zusammenhängenden Zellen. Ein global
bewiesenes (N) würde |z| ≤ R und damit die globale Schranke
|D(i,k)| ≤ 65536·R·(3/2)^{k−4} liefern (R23); eine Verbindung zum Zielsatz
(P)/(D−) aus §4.9 und die von Astra zusätzlich vorgeschlagenen Tests
((K_h), Geschwisterkorrelation ρ, Frontier-Zellen auf 2^27) sind nicht Teil
dieses Nachtrags.

### N.5 α-Messung und Zielform (R27/R28)

Least-Squares-Fit über 56 Punkte (i = 4..7, k = 4..17) von log₂|D(i,k)|
gegen (k+10): Steigung **α = 0,4644** (Nachrechnung: 0,464390). Das ist im
gemessenen Fenster unter der √L-Skala (halber Exponent 0,5), aber kein
Beweis asymptotisch sub-√L-Wachstums: die 56 Werte sind nicht unabhängig,
Log-Fits reagieren auf Nullnähen, und vier Zeilen kontrollieren nicht alle i
(Astra R27). Astras Priorität (R27/R28) ist deshalb nicht, den Exponenten zu
„beweisen“, sondern die **Zielform |D(i,k)| ≤ K_i·L_k^{2/3}** als präzises
analytisches Teilproblem zu isolieren — mit sauberer Quantifizierung über i
(festes i / feste endliche Zeilenmenge / Uniformität; K_i unabhängig von L).
Der Abstand zu 3/4 ist reichlich; eine D-Schranke allein trägt kein
Dichteziel (Transfersperre, R27: ein proportionaler C-Geradenanteil ist für
D unsichtbar).

Ein **α/K-Sweep auf Tiefe 34** (Zielraster m·2^{k+10} für m ≤ 256,
k = 8..22; Treiber `/tmp/opencode/run-alphaK-sweep.py`, session-lokal)
lief zum Freeze-Zeitpunkt dieses Nachtrags noch; sein Ergebnis wird bei
Vorliegen separat nachgetragen.

### N.6 Grenzen des Nachtrags

1. (L) ist für d ≤ 12 **im geprüften Ansatz** ausgeschlossen (konstante
   Koeffizienten, alle i ≥ 4); für beliebiges d ist nichts bewiesen.
   Skalenabhängige Koeffizienten, Abschlüsse erst ab späterer Skala und
   andere Observable sind nicht erfasst (R20).
2. (N) ist auf 64/88/144 endlichen Zellen bestätigt, nicht bewiesen; der
   Radius ist durch Gleichheit an (14,4) definiert; die Brücke zu (P) fehlt.
3. α = 0,4644 ist eine Heuristik aus vier Zeilen.
4. Die Counter-Engine ist ein Rechenwerkzeug: sie beschleunigt Messungen,
   sie beweist nichts.
5. R0 ist als globale Relation widerlegt; die Null-Verlängerung für i ≤ 15
   bleibt ein endlicher Befund.
6. Keine Lösungsaussage: Antihydra bleibt offen; die offene Kernaussage aus
   §6 bleibt die Lücke.

### N.7 Artefakte und Kommandos des Nachtrags

| Artefakt | Inhalt | Kommando / Quelle |
|---|---|---|
| `tools/deep_rank_chain.py` | Rangkette aus Counter-Checkpoints (Tiefen 27-33) | `python3 yesdocs/formal-conjectures/tools/deep_rank_chain.py --d 7 --d 8` |
| `tools/r0_sweep.py` | Fünfblock-Parität R0(i) (Tiefe 32) | `python3 yesdocs/formal-conjectures/tools/r0_sweep.py --out r0-sweep-result.json` |
| `tools/test_deep_rank_chain.py` | 5 Tests (Extraktion, Rangkette d = 12, R0, (N)) | `python3 -m unittest discover -s yesdocs/formal-conjectures/tools -p "test_deep_rank_chain.py"` |
| `data/deep-Cvalues-d12.json` | C(i,k)-Dump des d = 12-Laufs (Tiefe 33) | `deep_rank_chain.py --d 12 --out-dir <dir>` |
| `data/r0-sweep-result.json` | Sweep-Ergebnis (135/252 Treffer) | siehe oben |
| `data/astra-antihydra-rounds/` | 27 Rohantworten R1, R3..R28 + Provenienz-README | Beweismaterial des Loops (r2 fehlt) |

#### Nachrechnung des Nachtrags (Stichproben aus dem eingefrorenen Dump)

- Rangkette: alle zehn Rangzeilen (d = 3..12) aus `data/deep-Cvalues-d12.json`
  nachgerechnet (Testcode); für d = 7 und d = 8 zusätzlich frisch gerechnet
  (40 s bzw. 83 s, `tools/deep_rank_chain.py`).
- mod-2-Binnenbild d = 12: Rang 11 der Zeilen 4..15, Annihilatorbasis c₀/c₁,
  Signaturen i = 16..24, Zeilenmengen {4..14,16,20} (13 unabhängig) und
  {4..15,16,21} (12/13) — alles aus dem Dump.
- R0: Werte für i = 4..24 aus dem Dump; Abgleich mit
  `data/r0-sweep-result.json` (Testcode).
- (N): 88 Zellen (Tiefe-28-Fenster) und 144 Zellen (Tiefe 33),
  0 Verletzungen, Maximum exakt R² bei (14,4); z-Rekursion an
  verfügbaren Zellen exakt.
- α: Least-Squares-Nachrechnung ergibt 0,464390 (56 Punkte, i = 4..7,
  k = 4..17).
- Counter-Validierung: Zähler bei n = 3.145.728 (1.569.705) und n = 2^22
  (2.093.612) identisch mit den Bit-Werten; C(i,k) der d = 6-Matrix aus
  Bits und Engine paarweise identisch.

### Anker des Nachtrags

Die folgenden Marker binden die Artefakte des Nachtrags; der Prüfbefehl
steht in `data/attack-02-check.txt` (alte 26 Anker unverändert + diese).

# V22-Nachtrag (2026-09-14): Rohrunden r19-r28 und Nachtrags-Artefakte
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r19.json -> aaed793a0de8d4d9e3811a2fec58a2f7ad5c62058f08ed600be915034ec42b33]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r20.json -> 0986afd01dd4ad3030f56ddc33a2ff2b73fefc9fd002d1570a3ddd022de078f5]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r21.json -> 1f3a72c779de370df940d6302f64712c85a76e6342cbb57c8d6c5549b0145cc3]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r22.json -> 8d3c506b547bb33e539555e67210b418e5519f65db7b5d97273e16346538989b]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r23.json -> 09762b9e3e4e00e1659f827f08d75e9371d846da10058f838bd6b73bf90e71fc]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r24.json -> b4ab27105ed508fc680c962830d9aa87b8bb6f6c98d12901a2f6226cdf049ae2]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r25.json -> 40f6f0c706c4d7e406ce69f72a446459d4e9022d5f3ff8aaa619da17ccaa62e0]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r26.json -> 789f9ddedd0a7d4f777632b51b5bf4a084cb9137f317f6d1ffbc11efe1e2d443]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r27.json -> a59d65f71008bb86293369e15ac81992635cba514346f74835d16d8f8214fb7d]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r28.json -> 5357605f44045e5b8fc97e164cd8f9feae97eac42fd721c730445466c95c198f]
[ARTIFACT: yesdocs/formal-conjectures/tools/deep_rank_chain.py -> 1ecb70a639ac806f38ea87710c2cc198747a65eb251927965c2b0d0eabd25305]
[ARTIFACT: yesdocs/formal-conjectures/tools/r0_sweep.py -> 328aa95ec45f91ab73800fe24b972e03735f3d81ef9281f6b183e8067cb8d9fc]
[ARTIFACT: yesdocs/formal-conjectures/tools/test_deep_rank_chain.py -> 42e38106ec8ed9f532ea2e4befa06f3864921ddfa571d64a304546438020ad66]
[ARTIFACT: yesdocs/formal-conjectures/data/deep-Cvalues-d12.json -> aef77bca04677b878db4984e9e3d31b4806718ad3f8129250d3a582d76e29b29]
[ARTIFACT: yesdocs/formal-conjectures/data/r0-sweep-result.json -> 0117349e2ebd3c41293ddd181c470af68977a8afa74076d7daa7c7ac00639272]

---

## Nachtrag 2026-09-14 (V23): (N)-Radius falsifiziert und refittet, C-Kernel, Epoch-Quantor-Entscheidung

Basis: `master` @ `d617207` (nach dem V22-Merge `5ee0048` und der
C-Kernel-Serie einer Parallel-Session: `dcb66b4`, `4ca5534`, `33785e7`,
`d617207`). Dieser Nachtrag setzt den in §§1-8 und §N.1-§N.7 eingefrorenen
Stand fort (Runden 29-33, 2026-09-14 09:25 bis 12:09). Drei Ergebnisblöcke:
(i) der in V22 eingefrorene (N)-Radius ist auf neuen Zellen **falsifiziert**;
der Fensterkandidat `R²_cand = 0,014016590` hält über die vollen
Skalenbereiche k = 4..17 (Holdout in k = 10..17 ohne neuen Rekord), (ii) ein
**C-Kernel** ersetzt die Python-Engine als Messwerkzeug (gegen sie
kreuzverifiziert: 1298 E-Werte, 1992 D-Zellen; T34 in 40 min statt 110 min),
(iii) die **Epoch-Quantor-Entscheidung** (R33) präzisiert das Originalziel auf
die vier Epoch-Sequenzen `j = 0..3` und **korrigiert die (S)→H-Schlusskette**
aus §4.9/§6 (der alte Satz bleibt dort als überholt stehen). Rohdaten: fünf
weitere Antwortdateien `astra-antihydra-r{29..33}.json` (Empfang 09:25-12:09).

**Kein Lösungsergebnis.** `R²_cand` ist ein Fensterkandidat (Tiefe 34, k ≤ 17),
kein bewiesener Radius; „Epoch-only" ist eine Quantoren-Präzisierung, kein
Beweis; der C-Kernel rechnet nur (§N.2 gilt unverändert).

### O.1 Rundenchronik R29-R33

| Runde | Astra liefert | Verifikation (dieses Repo) | Ergebnis |
|---|---|---|---|
| R29 (09:25) | Horizont-/Dreiecksrechnung (`D(i,k)` braucht Zähler bis `(i+1)·2^{k+12}`, Tiefe-34-Maske deckt `k ≤ 22 − log₂(i+1)`); Datenwahl (max `Q`, min (N)-Marge, Eltern/Kind-Pakete); **exakte Energie-Identität** `z_P² = (8/9)(a²+b²) − (4/9)(a−b)²`; Payoff `|D| ≤ K·L^{2/3}`, `K = 4R·2^{14/3} ≈ 6,23`; Speicher `Θ(2^dep)`; Investitionsrangfolge | Energie-Identität exakt nachgerechnet (§O.7); Horizont/Maske mit den Wide-Läufen abgeglichen | Beschleunigungs-/Strategiepaket; C-Kernel und Wide-Läufe angestoßen |
| R30 (09:45) | **exakter Induktionskern**: `t(i,k) := 2V(s(i,k+1)) − V(s(i,k))`, `(N) ⇔ t ≤ R²`; Defektfortpflanzung `t(i,k) = (8/9)(tL+tR) − (4/9)(2Δ₊−Δ₋)`; Eltern-Bedingung `2Δ₊ − Δ₋ + 2(δL+δR) ≥ (7/4)R²`; Seed-Lücke (19); Zertifikatsformat (Seed/Closure/Energiedefekt/Abstraktion); korrelationsfreie Invarianz unmöglich | Seed-Bedingung (19) auf dem T34-Sweep ausgeführt; T33-Indexliste = 148 statt 144 | Induktionskern fixiert; Seed-Lücke quantifiziert |
| R31 (10:18) | Fix-k-Sättigung; elementare Seed-Schranke `E_{i,4} ≤ 625/9` und Seed/Radius-Entkopplung; Verstärkung `t_P ≤ (16/9)R²`; Masken-Korrektur `i_max(k) = 2^{20−k}−1`; radius-freie `B* = C/(1−λ)`; Zähler `C = 2E−O = (3H+n)/5` | Zerlegung (64,9) exakt (`(8/9)(tL+tR) = 0,005902`, `−(4/9)(2Δ₊−Δ₋) = −0,000252`; Kinder (128,8)/(129,8), Slacks +0,000738/+0,003922); (P)-Residuum max 0,4145 @(164,8) | Refit-Kandidat entsteht; Wide-Läufe angestoßen |
| R32 (12:02) | Extremwertbild `u_max(N) ≈ 0,00125·log N + const`; Fenstermax ≠ Supremum; Indexformel `i_max^t(d,k) = 2^{d−k−14}−1`; Basis `t(i,4)` als Hauptengpass; Tautologie `M = Q + 2(δL+δR) − (7/4)R² = (9/4)(R² − t_P)`; Konstanten-Empfehlung (T35/36) | equal-N-Analyse (20 Subsamples à 500 Zellen): `u_max` stationär über k = 4..10; Holdout Wide-2 (k = 10..17) ohne neuen Rekord | **R²_cand = 0,014016590 fixiert** |
| R33 (12:09) | Epoch-only als Originalquantor; `a_S = u* − 2/5 = 0,091226…`; die `1/12`-Schwelle betrifft nur den Halt-Zähler `C`; für `H ≥ 0` ist `a > 3/11` nötig; vollständige Epoch-only-Reparatur (Budget `< 0,2184989…` oder Epoch-(P) mit 500); (N) epoch-only; Haar-Schranke `sup_i t(i,4) = 16400/81`; Seed-Lücke K = 7 | Originaltext §4.9/§6 wörtlich abgeglichen (j-Index von Defekt/Verlust, kein All-i-Quantor); K = 7-Seeds nachträglich gerechnet (`r_{j,7}`, min u = 0,495041); Epoch-Loss-Tabelle aus T34 (Budgetnutzung 1,5-4 %) | Zielquantor präzisiert; **Doku-Korrektur für §4.9/§6** |

### O.2 (N)-Radius: Falsifikation, Refit, volle Skalenabdeckung

**Ausgangspunkt (V22).** Der V22-Nachtrag hatte `R²_alt =
1309875575/347892350976 ≈ 0,0037651750` eingefroren, definiert durch
Gleichheit an der Zelle `(14,4)` im Fenster `i ≤ 15` (88 bzw. 144 Zellen,
§N.4). Als Aussage über dieses Fenster bleibt das korrekt; als globaler
Kandidat ist der Radius widerlegt.

**Falsifikation (T34-Sweep, zwei Engines).** Sechs von 1488 (N)-Zellen
neuer i (i ≤ 255, außerhalb des 88er-Fensters) verletzen (N) mit `R²_alt`;
Maximum `t(64,9) = 12592924675/2229025112064 = 0,0056495212… = 1,5005×R²_alt`;
weitere Verletzungen `(45,8)` 1,340×, `(128,8)` 1,305×, `(166,10)` 1,124×,
`(64,10)` 1,079×, `(31,8)` 1,028×; alle bei k = 8..10, i = 31..166
(Außenkante des Dreiecks `(i+1)·2^{k+14} ≤ 2^34`). Auch die Seed-Bedingung
(19) bricht: 6 von 252 i verletzen `R²_alt`, größtes i = 159 (0,004887995),
dann 90, 69, 48, 176, 156.

**Refit.** `R²_neu := t(64,9)`; damit 0 Verletzungen in allen 1488
(N)-Zellen und allen 252 Seed-Zellen; `K_neu = 2^{20/3}·√R²_neu = 7,6361`;
`max|z| = 0,057207 @z(85,9)`; `max Q = |D|/L^{2/3} = 4,3787 @(85,9)`.

**Volle Skalenabdeckung (Wide-1/Wide-2, Tiefe 34).** Wide-1 (r-Skalen
k = 4..13) liefert t-Zellen für k = 4..9 in vollen i-Bereichen (128.955
t-Zellen), Wide-2 (r-Skalen k = 14..21) für k = 10..17; kombiniert 1048
gemeinsame E-Werte ohne Mismatch. Fenstermaxima `T_k(∞)` (volle i-Bereiche;
`argmax` nur für k ≤ 9 ausgewiesen):

| k | T_k(∞) | u_k = (9/8)^{k−4}·T_k | argmax |
|---|---|---|---|
| 4 | 0,014016590 | 0,014017 | (7000,4) |
| 5 | 0,011858531 | 0,013341 | (23922,5) |
| 6 | 0,009807740 | 0,012413 | (12043,6) |
| 7 | 0,009739088 | 0,013867 | (6021,7) |
| 8 | 0,006442167 | 0,010319 | (2913,8) |
| 9 | 0,005649521 | 0,010181 | (64,9) |
| 10 | 0,005147605 | 0,010436 | — |
| 11 | 0,003384064 | 0,007718 | — |
| 12 | 0,003100498 | 0,007955 | — |
| 13 | 0,001956859 | 0,005648 | — |
| 14 | 0,001218397 | 0,003957 | — |
| 15 | 0,000881787 | 0,003221 | — |
| 16 | 0,000668170 | 0,002746 | — |
| 17 | 0,000487942 | 0,002256 | — |

Der Rekord ist exakt `T_4 = 304766525/21743271936` (Zelle (7000,4),
`D = (980, 4900, −11305)`; aus dem Wide-Log nachgerechnet, §O.7);
**`R²_cand = 0,014016590`, `K_cand = 12,03`**; `max|z| = 0,098267
@z(27452,4)`; Seed-Maximum `E_{i,4} = 0,010779 @i = 14000 < R²_cand`.
Es binden die Basisskalen k = 4..7; `u_k` ist über k = 4..10 quasi-konstant
(0,0102-0,0140).

**Holdout bestanden.** Wide-2 (k = 10..17) ohne neuen Rekord über `T_4`, also
bleibt `R²_cand`. Das Extremwertbild `u_max(N) ≈ 0,00125·log N` (equal-N:
`u_max ≈ 0,0076-0,0095` stationär über k = 4..10, 20 Subsamples à 500 Zellen)
erklärt den `u`-Abfall für k ≥ 11 (0,008 → 0,002) als Zellzahleffekt.
**Fenstermax ≠ Supremum:** Tiefe d erlaubt t-Zellen nur für
`i ≤ i_max^t(d,k) = 2^{d−k−14}−1` (T34: k = 4 → 65535, k = 17 → 7).

**Zähler, Residuen, Direktmessung.** Im vollen k = 4..9-Fenster verletzen 578
Zellen `t ≤ R²_neu` und 2910 `t ≤ R²_alt`; gegen `R²_cand` keine. Residuen
der R16-Ziele (alle i, Budget 1): (D−) k = 4..13 durchweg 1,36-1,74 (>1);
(P) k = 4: 1,46 / 5: 1,40 / 6: 1,04 / k ≥ 7: ≤ 0,92. Epoch-Zellen (j = 0..3):
(P) max 0,55, (D−) max 0,66. (P)-Direktmessung: max `(−D)/(500·2^{3k/4}) =
0,4145 @(164,8)` (Budget 1); `min D = −252180 @(15,18)`.

### O.3 C-Kernel: zwei Engines, Kreuzverifikation, Wide-Läufe (Werkzeug)

Die Engine `bemyself/experiments/antihydra_c.c` (C-Port des validierten
Python-Kerns `antihydra_deep.py`: fixed-limb Leaf-Loop plus GMP-Patch-up nach
dem mxdys-Blockverfahren) kam über `dcb66b4` ins Repo; eine Parallel-Session
ergänzte `4ca5534` (w18-Sprung-Leaf; byte-identisch validiert, real nur ≈6 %
Gewinn), `33785e7` (**Top-Cache** `--cache-out/--cache-in`, validiert über
d24→25 und d27→28, gemessen 2,0×: 16,4 s → 8,1 s; Ladder D35 warm ≈45 min
statt ≈85 min) und `d617207` (`run_jobs.sh`). Das instrumentierte
Kostenmodell (Learnings #99378/#99380 der Parallel-Session): GMP-Multiplies
≈75 % der Laufzeit (mulc ≈40-46 %, mulv ≈33-38 %), Leaf ≈16 %; alle
Komponenten skalieren ≈2,2× je Tiefe, die Anteile bleiben über die Tiefen
konstant. Dieser Nachtrag referenziert die Engine nur; Logs und Daten liegen
im Projekt-Archiv `.yesmem/tmp/antihydra-2026-09-14/` (gitignored).

Bauphasen-Verifikation: bit-identisch zur Python-Engine auf depth 16/20/22/24
inklusive krummer Ziele; zwei per Diff gefundene Bugs (Shift-Carry-Richtung;
Input-Overwrite: die Korrektur braucht Start UND Ende); Anker exakt: `2^22`
(counter 2.093.612), `2^31` (1.073.720.884, Abweichung −20.940), `2^32`
(2.147.493.851). **Kreuzvergleich der Tagesläufe:** 1298 E-Werte und 1992
D-Zellen identisch (die D-Dumps `alphaK-D-values.json` (Python) und
`alphaK-D-values-C.json` (C) sind byte-identisch, §O.7); C-T34 40 min (rc=0)
gegen Python-T34 110 min. Der Grid-Modus `--grid k0 k1 m0 m1` erzeugt die
Wide-Läufe (Wide-1 fertig 10:52, Wide-2 11:32, rc=0).

### O.4 R33: Epoch-Quantor und Korrektur der (S)→H-Schlusskette

**Entscheidung (Astra R33; hier am Originaltext verifiziert).** Defekt und
Verlust des Originaltexts sind mit `j` indiziert (`p_{j,k}`, `ℓ_{j,k}`), und
die R16-Ziele sind als Epoch-Vektor über die vier Sequenzen `j = 0..3`
(`i = 4..7`) formuliert; ein Quantor über alle i steht dort nicht. Auch die
Haar-Abschätzung summiert nur über vier j. Die in §O.2 gemessenen
All-i-Verletzungen der 500-Budgets liegen damit **außerhalb des
Originalziels**: im Haar-Modell treten All-i-Verletzungen von (P) mit 500 bei
festem k = 6 fast sicher auf (unendlich viele disjunkte Paritätsfenster),
ein All-i-Budget wäre nie sinnvoll.

**Korrektur zu §4.9/§6 (der alte Satz bleibt als überholt stehen).** Die
Aussage „(S) + Seeds ⇒ Reserve-Nichtnegativität auf allen Skalen" ist
**unvollständig**. (S) mit Abzug 2/5 liefert `a_S = u* − 2/5 =
0,091226196…`; die Schwelle `1/12` betrifft den **Halt-Zähler**
`C(n) = 2E−O = (n+3H)/5` (Schritte +2/−1): `a > 1/12` plus endlicher
Anfangscheck sichert `C ≥ 0`. Für **`H ≥ 0` im Zellinneren** ist dagegen bei
reiner Zellmittel-Kontrolle im schlechtesten Fall (Zelle i = 4) die
Mittelschwelle **`a > 3/11 ≈ 0,2727`** nötig; `a_S` liegt deutlich darunter.

**Vollständige Epoch-only-Reparatur für H ≥ 0:** Gesamtverlust
`Σ_h ℓ_{j,K+2h} < u* − 3/11 = 0,21849892356…` (beide Seed-Paritäten) **oder**
durchgehendes Epoch-(P) mit `C_P = 500` (plus Seeds beider Paritäten plus
endlichem Anfangscheck) ⇒ garantierter Mittelwert ≥ 0,367 > 3/11.
Budgetabzüge beim Seed-Niveau `u*`: (P) 500 → ≈0,124 (Mittel 0,367);
(P) 730 → ≈0,181 (0,310); (D−) 500 → ≈0,0521 (0,4391); (D−) 875 → ≈0,0912
(0,4000). Alternative Reparatur ohne Seed-Wechsel: Viertelzellen-Verfeinerung
(B = 16) mit `a > 3/41 ≈ 0,0732 < a_S`. Quantorenwarnung: die wörtliche
disjunktive Form `∀k[(D−)_k ∨ (P)_k]` ist nicht mit einer durchgehenden Kette
gleichwertig (eigenes Übergangslemma nötig).

### O.5 (N) epoch-only, Seeds, epochale Verlusttabelle

**l-Identität und epochales Budget (R33; in §O.7 nachgerechnet).** Mit
`ℓ_{i,k} = (3/4)^{k−4}·[−z(i,k)]₊` liefert eine uniforme Schranke `|z| ≤ Z`
nur auf den vier Epoch-Sequenzen `Σ_{h≥0} ℓ_{i,K+2h} ≤ (16/7)·Z·(3/4)^{K−4}`
(K = 7: 27Z/28; K = 8: 81Z/112). Aus (N) folgt längs der Sequenz induktiv
`|z_k| ≤ Z := max{R, |z_K|, |z_{K+1}|}` (aus `z_{k+2}² ≤ (R² + z_k²)/2`);
(N) muss dafür nur entlang der Epoch-Sequenz gelten. **(N) ist nicht ihrem
Wesen nach global.**

**Summenbaum-Warnung (R33).** Ein Beweis durch Abstieg zur Basisskala k = 4
braucht wachsende Indexmengen (Wurzelepoche auf Skala k: Blätter
`i = 4·2^{k−4} … 8·2^{k−4}−1`; über alle k wächst die Vereinigung zu allen
`i ≥ 4`). Das ist eine Verstärkung des Werkzeugs, nicht der Quantor des
Ziels, und nur mit orbit-spezifischer Kompression sinnvoll.

**Basis bei k = 4.** Haar-fast-sicher `sup_i t(i,4) = 16400/81` (extremales
Fünfertupel `(−2,−2,−2,3,3)`, per Paritätswort-Bijektion durch einen Start
realisierbar); keine für alle Starts gültige Carry-Bedingung kann das
drücken. Für den festen Start 8 wäre eine kleine All-i-Schranke eine starke
orbit-spezifische Besonderheit; der Rekord sitzt auf der Basisskala.

**Seeds (frisch verifiziert, §O.7).** `r_{j,7} = (64886, 66261, 65256,
65896)`, `min u = 0,4950408935546875`; `r_{j,8} = (130377, 128772, 130827,
130847)`, `min u = 0,4912261962890625` (bindend); Bonus: K = 6 `min u =
0,4848938`, K = 9 `min u = 0,4970531`. Beide Paritäten erreichen die
Untergrenze `u* = 128772/262144`.

**Epoch-Loss-Tabelle** (`ℓ_{j,k} = (3/4)^{k−4}·[−z(j,k)]₊`, gemessen aus den
T34-Daten; Zeilen k = 4..7 aus einem frischen Engine-Lauf):

| k | j=0 | j=1 | j=2 | j=3 |
|---|---|---|---|---|
| 4 | 0,03372192 | 0,03189087 | 0,00000000 | 0,02349854 |
| 5 | 0,00740051 | 0,00000000 | 0,00000000 | 0,00000000 |
| 6 | 0,00097275 | 0,00000000 | 0,00000000 | 0,00000000 |
| 7 | 0,00000000 | 0,00774384 | 0,00081062 | 0,00101089 |
| 8 | 0,00000000 | 0,00000000 | 0,00278473 | 0,00245094 |
| 9 | 0,00585556 | 0,00000000 | 0,00000000 | 0,00174284 |
| 10 | 0,00083685 | 0,00000000 | 0,00000000 | 0,00000000 |
| 11 | 0,00081897 | 0,00000000 | 0,00000000 | 0,00000000 |
| 12 | 0,00000000 | 0,00037998 | 0,00097483 | 0,00000000 |
| 13 | 0,00000000 | 0,00000000 | 0,00052243 | 0,00037625 |
| 14 | 0,00000000 | 0,00090972 | 0,00000000 | 0,00069477 |
| 15 | 0,00000000 | 0,00031013 | 0,00000000 | 0,00013508 |
| 16 | 0,00008373 | 0,00000000 | 0,00013568 | 0,00000000 |

Kumulierte Budgets über die jeweilige Parität (partiell bis k = 16; je
j = 0..3): K = 7: 0,00667453 / 0,00805397 / 0,00133306 / 0,00326507;
K = 8: 0,00092058 / 0,00128970 / 0,00389524 / 0,00314571. Das ist eine
Nutzung der Reparaturschranke 0,2184989… von **1,5-4 %** auf endlichem
Fenster. (P)-Epoch-Residuum derselben Daten: max 0,5525 @(4,4) (Budget 1).

**Endbilanz (R33).** Der Beweisengpass ist präzisiert: eine unendliche,
start-8-spezifische Kontrolle der **vier epochalen Verlustbudgets**, nicht
notwendigerweise eine kleine uniforme All-i-Basisbarriere.

### O.6 Grenzen des Nachtrags

1. `R²_cand = 0,014016590` ist ein **Fensterkandidat** (Tiefe 34, k ≤ 17);
   die `T_k(∞)` sind Fenstermaxima, keine Suprema; `u_max ≈ 0,00125·log N`
   ist ein Fit, keine Schranke.
2. Die V22-Aussage über das 88/144-Zellen-Fenster (i ≤ 15) bleibt mit
   `R²_alt` korrekt; widerlegt ist nur der globale Anspruch. Der Refit ist
   keine Aussage über alle i oder alle k.
3. Epoch-Loss-Tabelle und 1,5-4 %-Nutzung sind Messungen (k ≤ 16);
   Epoch-(P) mit 500 ist für Start 8 nicht bewiesen; „epoch-only" schließt
   einen späteren All-i-Beweis nicht aus.
4. Der C-Kernel ist ein Rechenwerkzeug; Profiling und Optimierungen stammen
   aus der Parallel-Session (Learnings #99378/#99380) und sind hier nur
   referenziert, nicht nachgerechnet.
5. Kein Lösungsergebnis: Antihydra bleibt offen.

### O.7 Artefakte und Kommandos des Nachtrags

| Artefakt | Inhalt | Kommando / Quelle |
|---|---|---|
| `data/astra-antihydra-rounds/astra-antihydra-r{29..33}.json` | fünf neue Rohantworten (Empfang 09:25-12:09) | Beweismaterial; Anker unten |
| `bemyself/experiments/antihydra_c.c` | C-Kernel (Leaf, GMP, Grid, Top-Cache) | Repo-Eigentum (`dcb66b4` + `4ca5534`/`33785e7`); hier nur referenziert |
| `.yesmem/tmp/antihydra-2026-09-14/` (gitignored) | Wide-/αK-Logs, E/D-JSONs, R29-R33-Archiv | Rohdaten der Tabellen §O.2/§O.5 |

#### Nachrechnung des Nachtrags (Stichproben)

- **Seeds:** `r_{j,6}`, `r_{j,7}`, `r_{j,8}`, `r_{j,9}` frisch aus einem
  Tiefe-22-Lauf der Engine (25 Ziele, 0,1 s): `r_{j,7}` und `r_{j,8}` exakt
  wie angegeben, inklusive `min u`; K = 6: 0,4848938, K = 9: 0,4970531.
- **Epoch-Loss-Tabelle:** Zeilen k = 4..7 frisch aus demselben Lauf
  (identisch zur Tabelle), Zeilen k = 8..16 aus `alphaK-D-values-C.json`
  (exakt); kumulierte Budgets K = 7/8 nachgerechnet.
- **Rekordzellen:** `t(7000,4) = 304766525/21743271936`,
  `t(23922,5) = 9282357875/782757789696`,
  `t(12043,6) = 269897525/27518828544`, ferner k = 7..9 — aus den
  E-Zählern des Wide-Logs exakt nachgerechnet; `t(64,9) =
  12592924675/2229025112064` aus dem D-Dump.
- **Energie-Identität:** `z_P² = (8/9)(a²+b²) − (4/9)(a−b)²` für fünf
  zufällige rationale Paare exakt (0 Differenz).
- **Kreuzverifikation:** die beiden D-Dumps (Python/C) sind byte-identisch
  (`cmp` ohne Ausgabe).

### Anker des V23-Nachtrags

Die folgenden Marker binden die neuen Rohrunden; der Prüfbefehl steht in
`data/attack-02-check.txt`.

[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r29.json -> b3911166e33efca8b46d788ea0eb320b45dfa327c283c82c6a8284de6529804e]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r30.json -> bd6f6bbddc2c2264b8922a63d5b8b37daec73da10d834a3d455761bbb24f10e7]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r31.json -> 8083fdcc90b11e976a87ab90b6584b2d0b74ef40daf2dee747a9b479caca5357]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r32.json -> 1bc1fc59c3df075bc119a62415329010028357638bf7b9343ad476ab88a82670]
[ARTIFACT: yesdocs/formal-conjectures/data/astra-antihydra-rounds/astra-antihydra-r33.json -> b191f302a6df3dec939e31451044128d4406dbd51c4bfcfa893cea89e8e04537]

# Schur-Zahlen: belegte Faerbungen (P13)

Diese Auswertung sammelt fuer die Schur-Zahlen, wie weit sich die Zahlen
`1..N` mit `k` Farben so faerben lassen, dass keine Farbklasse eine Loesung
von `x + y = z` enthaelt. Sie ist der Pruefbericht des Claim-Typs
`[COLORING]` (README, Abschnitt "Schur-Faerbungen"; Modul
`bemyself/claimtypes/coloring.py`).

**Konvention.** `S(k)` ist hier die groesste Zahl `N`, fuer die eine
solche k-Faerbung von `1..N` existiert (OEIS A045652, "Schur's numbers
(version 2)": 1, 4, 13, 44, 160). Die verwandte OEIS-Folge A030126
zaehlt die um eins groessere Zahl (2, 5, 14, 45, 161 -- das kleinste `N`,
bei dem JEDE k-Faerbung von `1..N` eine monochromatische Loesung hat).
Zitate unten nennen die jeweilige Version ausdruecklich.

Nachrechnen dieser Datei:

```
python3 -m bemyself check --report yesdocs/schur/README.md --strict
```

Erwartet: Exit 0, alle sechs `[COLORING]`-Marker `CONFIRMED` (der Test
`tests/test_coloring.py` fixiert das: jede in dieser Datei stehende
Behauptung muss verifizieren).

## 1. Pruefbericht: die Zertifikate dieser Datei

Die vier kleinen Faelle sind **eigene Zertifikate**: gefunden mit dem
deterministischen Suchlauf dieses Repos, `python3 -m
bemyself.experiments.schur <k> <n>` (MRV-Backtracking, kein Zufall, kein
Seed; gleiche Eingaben ergeben dasselbe Zertifikat). Die Knotenzahl steht
im Befehlsergebnis. Die beiden grossen Faelle sind
**Literatur-Zertifikate**: aus der in Abschnitt 3 genannten Quelle
abgelesen, in die Farbfolge uebersetzt und mit demselben Pruefer
nachgerechnet -- die Uebersetzung ist die eigene Zutat, die Quelle nennt
nur die Zerlegung.

- **k = 1, N = 1.** Ein einziges Element, kein Tripel `x + y <= 1`:
  jede Faerbung ist gueltig. Eigene Suche, 0 Knoten. Die Schranke ist
  exakt: `S(1) = 1` (mit zwei Zahlen erzeugt `1 + 1 = 2` zwingend eine
  monochromatische Loesung).

  [COLORING: k=1 ; 1]

- **k = 2, N = 4.** Zerlegung `{1, 4} / {2, 3}` als Farbfolge 1,2,2,1:
  die Tripel 1+1=2, 1+2=3, 1+3=4, 2+2=4 sind samtlich nicht
  monochromatisch. Eigene Suche, 3 Knoten. Die Schranke ist exakt:
  `S(2) = 4` (klassisch; `1..5` ist nicht mehr 2-faerbbar).

  [COLORING: k=2 ; 1221]

- **k = 3, N = 13.** Eigene Suche, 15 Knoten. Die Schranke ist exakt:
  `S(3) = 13` (klassisch; per Hand nachvollziehbar).

  [COLORING: k=3 ; 1221331331221]

- **k = 4, N = 44 (eigene Suche).** Eigene Suche, 18.870 Knoten (rund
  eine Sekunde). Die Schranke ist exakt: `S(4) = 44` (Golomb & Baumert
  1965; OEIS A030126 fuehrt `a(4) = 45`).

  [COLORING: k=4 ; 12213343122141223431444413432314122131331221]

- **k = 4, N = 44 (Literatur, nachgerechnet).** Die Zerlegung von
  Golomb & Baumert, wie sie als Beispiel in OEIS A045652 steht
  (Mengen A, B, C, D; hier in die Farbfolge uebersetzt, A=1, B=2, C=3,
  D=4). Nachgerechnet mit demselben Pruefer.

  [COLORING: k=4 ; 12131322444434141213233231214343444422313121]

- **k = 5, N = 160 (Literatur, nachgerechnet).** Das Zertifikat von
  Exoo, wie es (von Marijn Heule eingetragen) als Beispiel in OEIS
  A030126 und A045652 steht (Mengen A..E; hier als Farbfolge, A=1..E=5).
  Nachgerechnet mit demselben Pruefer. Die Schranke ist exakt:
  `S(5) = 160` (Heule 2018: keine 5-Faerbung von `1..161`; SAT-Beweis
  ueber 2 Petabytes). **Nicht** selbst gefunden: der eigene Suchlauf
  findet 160 im getesteten Budget nicht (ehrlich: 90 Sekunden, kein
  Fund); deshalb steht hier das Literatur-Zertifikat.

  [COLORING: k=5 ; 1223314241444233412213122143314441424133331512233125415445354255155555552155554554555512555555515524535445145213322151333314241444133412213122143324441424133221]

## 2. Landkarte

Stand der recherchierten Quellen: 12.09.2026. "Exakt" heisst: beide
Seiten sind bekannt (obere und untere Schranke fallen zusammen);
"offen" heisst: die obere Seite ist unbekannt, es gibt nur die genannte
untere Schranke.

| k | untere Schranke (belegt) | Zertifikat | oberer Rand | Quelle des Stands |
|---|---|---|---|---|
| 1 | 1 | eigene Suche | exakt: `S(1) = 1` | klassisch (trivial) |
| 2 | 4 | eigene Suche | exakt: `S(2) = 4` | klassisch |
| 3 | 13 | eigene Suche | exakt: `S(3) = 13` | klassisch |
| 4 | 44 | eigene Suche + Golomb & Baumert | exakt: `S(4) = 44` | Golomb & Baumert 1965 (OEIS A030126) |
| 5 | 160 | Exoo (OEIS), nachgerechnet | exakt: `S(5) = 160` | Heule 2018 (SAT; 2 Petabytes Beweis) |
| 6 | 536 | nur Quelle, kein Zertifikat nachgerechnet | offen (unbekannt; kein kompaktes Zertifikat) | Fredricksen & Sweet 2000; Erdős Problems #483 |
| 7 | 1696 | nur Quelle, kein Zertifikat nachgerechnet | offen (unbekannt; kein kompaktes Zertifikat) | Rowley 2021 (verbessert 1680) |

Was dieses Werkzeug kann: jedes eingereichte Faerbungs-Zertifikat bis zur
Laenge 4096 vollstaendig nachrechnen (alle Tripel `x <= y` mit
`x + y <= N`) -- das umfasst alle hier gezeigten Faelle -- und die
kleinen Faelle `S(1..4)` deterministisch selbst finden (Sekunden, s.
Befehle unten).

Was dieses Werkzeug nicht kann -- und die Datei deshalb ehrlich offen
laesst:

- Die **obere Seite** pruefen: "keine k-Faerbung von `1..N+1`" hat kein
  kompaktes Zertifikat (das ist gerade die Pointe des Typs). Fuer
  `k = 5` ist sie per SAT bewiesen (Heule 2018, 2 Petabytes Beweis --
  ein Referenzartefakt, kein nachpruefbares Kurzzertifikat); fuer
  `k >= 6` ist sie offen.
- Die Zertifikate fuer `k = 6` (`N = 536`) und `k = 7` (`N = 1696`)
  nachrechnen: uns ist keine maschinenlesbare Fassung zugaenglich.
  Fredricksen & Sweet (2000) geben die untere Schranke `S(6) >= 536`
  in einem Paper (EJC #R32, nur PDF); Rowleys 1696-Partition liegt im
  Ancillary-XLS zu arXiv:2107.03560 (Tabellenkalkulationsdatei). Beide
  Zahlen sind hier **Quellenangabe, kein Haekchen** -- dieselbe
  Unterscheidung wie im Erdős-Straus-Report fuer nicht-affine
  Identitaeten.
- `160` selbst finden: der eigene Suchlauf (der die Faelle bis `N = 44`
  in Sekunden loest) findet `N = 160` nicht in zumutbarer Zeit; die
  Zertifikats-Quelle ist dort die Literatur (Exoo).

Ein weiterer belegter Punkt aus der Quelle: Rowleys Template-Zerlegung
impliziert `S(k+5) >= 376 * S(k) + 160` fuer alle `k > 0` (mit `S(1) = 1`
also `S(6) >= 536` -- dieselbe Schranke, die Fredricksen & Sweet 2000
zuerst zeigten). Auch das ist Quellenstand, nicht nachgerechnet.

## 3. Quellen

- OEIS, [A045652 "Schur's numbers (version 2)"](https://oeis.org/A045652)
  (Werte 1, 4, 13, 44, 160; Golomb-Baumert- und Exoo-Zertifikate;
  Lower-Bound-Kommentare zu 536/1680 und Rowleys 1696). Abgerufen am
  12.09.2026.
- OEIS, [A030126 "Schur's numbers (version 1)"](https://oeis.org/A030126)
  (Werte 2, 5, 14, 45, 161; `a(6) >= 537`, `a(7) >= 1681` nach Ahmed,
  Boza, Revuelta, Sanz 2023). Abgerufen am 12.09.2026.
- M. J. H. Heule, "Schur Number Five", AAAI 2018,
  [arXiv:1711.08076](https://arxiv.org/abs/1711.08076) und die
  Projektseite <https://www.cs.utexas.edu/~marijn/Schur/> (SAT-Beweis
  fuer `S(5) = 160`, 2 Petabytes Proof; Zaehlung: 2.447.113.088
  Faerbungen von `1..160`). Abgerufen am 12.09.2026.
- H. Fredricksen, M. M. Sweet, "Symmetric Sum-Free Partitions and Lower
  Bounds for Schur Numbers", Electron. J. Combin. 7 (2000), #R32,
  [doi:10.37236/1510](https://doi.org/10.37236/1510) (untere Schranken
  `S(6) >= 536`, `S(7) >= 1680`). Abgerufen (Metadaten/Abstract) am
  12.09.2026.
- F. Rowley, "An Improved Lower Bound for S(7) and Some Interesting
  Templates", [arXiv:2107.03560](https://arxiv.org/abs/2107.03560)
  (`S(7) >= 1696`; Template `[1,376]`; `S(k+5) >= 376 * S(k) + 160`;
  Partitionsdaten im Ancillary-XLS). Abgerufen am 12.09.2026.
- T. F. Bloom, "Erdős Problem #483", <https://www.erdosproblems.com/483>
  (Schur-Zahlen; Schranken `(380)^{k/5} - O(1) <= f(k) <= (e - 1/6) * k!`
  nach Ageron et al. 2021 bzw. Xu, Xie, Chen 2002; `f(k) <= R(3;k) - 1`).
  Abgerufen am 12.09.2026.
- Wikipedia, "Schur's theorem",
  <https://en.wikipedia.org/wiki/Schur%27s_theorem> (Definition;
  Referenz auf Heule). Abgerufen am 12.09.2026.

Alle Werte dieses Abschnitts sind aus den genannten Quellen abgelesen
(Abrufdatum 12.09.2026) und, wo nachgerechnet, mit den Zertifikaten oben
belegt. Kein Wert ist aus dem Gedaechtnis behauptet.

## 4. Nachrechnen und eigene Suche

```
python3 -m bemyself check --report yesdocs/schur/README.md --strict
python3 -m bemyself.experiments.schur 1 1
python3 -m bemyself.experiments.schur 2 4
python3 -m bemyself.experiments.schur 3 13
python3 -m bemyself.experiments.schur 4 44
```

Erwartet: `check` endet mit Exit 0 und sechs `CONFIRMED`; die Suchlaeufe
geben jeweils eine Zeile `coloring k=<k> n=<n> nodes=<knoten> <farbfolge>`
aus und enden mit Exit 0, z. B. `coloring k=4 n=44 nodes=18870
12213343122141223431444413432314122131331221`. Alle Ausgaben sind
deterministisch (kein Zufall): zweimal ausgefuehrt, identisches Ergebnis
-- `tests/test_schur.py` fixiert das. Ein Budget, das nicht reicht, endet
mit Ausgabe `none ...` und Exit 1 -- ein abgebrochener Lauf behauptet
nichts; das Budget zaehlt expandierte Entscheidungsknoten exakt, ein
gestoppter Lauf meldet nie mehr Knoten als das Budget erlaubt.

## 5. Grenzen dieser Auswertung

- Ein `CONFIRMED` der Marker belegt die untere Schranke `S(k) >= N` und
  sonst nichts: es beweist keine Gleichheit und sagt nichts ueber die
  obere Schranke. Die Werte in Spalte "oberer Rand" der Landkarte sind
  Quellenstand (SAT-Beweis fuer `k = 5`, Sonstiges klassisch), nicht von
  diesem Werkzeug geprueft.
- Die eigene Suche ist ein ehrlicher Best-Effort-Lauf mit dokumentiertem
  Knotenbudget, kein Vollstaendigkeitsbeweis; die Knotenzahlen (0, 3, 15,
  18870) sind empirisch auf der Entwicklungsmaschine gemessen.
- Die Uebersetzung der OEIS-Mengenlisten in Farbfolgen ist die eigene
  Zutat; Fehler waeren hier moeglich -- deshalb prueft `check --report`
  jedes uebersetzte Zertifikat unabhaengig nach (die Marker oben sind
  genau dieser Nachweis).

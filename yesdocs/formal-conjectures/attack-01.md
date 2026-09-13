# Angriff 01 — BMO#1 (Collatz-artig) und Antihydra (BB(6)-Holdouts)

Datum: 2026-09-13. Ausgangsbasis: `master` @ `d2662e9` (E2: Katalog-Scan + Shortlist +
erster umgrenzter Angriff, `yesdocs/formal-conjectures/README.md`). Dieser Bericht ist
der vertiefte Angriff auf die zwei BB(6)-Holdouts der Shortlist, mit vier Teilen:

1. **Reduktionen lokal beidseitig verifizieren** — schließt die in E2 §4.4 deklarierte
   Lücke (Maschine↔Reformulierungs-Äquivalenzen nur aus externer Doku).
2. **Verifizierte Läufe** — Antihydra über die öffentlich dokumentierte Tiefe hinaus,
   BMO#1 mit gemessener Grenze und Begründung.
3. **Strukturjagd** — exakte Teilstruktur der dokumentierten Ersatzmodelle.
4. **Was hat V1.1 geleistet** — Evaluierung der Notation in diesem Angriff (§5).

**Kein Lösungsergebnis.** Beide Maschinen bleiben offen. Alles hier sind endliche,
exakt beschriftete Beobachtungen, maschinell verifiziert (Blätter + Runner-Verdikte;
`[ARTIFACT]`/`[COMPUTE]`/`[SEARCHED]`-Anker im Anker-Bericht `data/attack-01-check.txt`).

Maschinen (bbchallenge-Notation, Zustände A..F, `_` = keine Regel):

- `MB` = BMO#1 = `1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE`
- `MA` = Antihydra = `1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA`

## 1. Quellen (Zugriff 2026-09-13, Revisionsstände per MediaWiki-API geprüft)

| Quelle | Inhalt | Stand |
|---|---|---|
| [BusyBeaverWiki — BMO#1](https://wiki.bbchallenge.org/wiki/1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE) (rev 8053) | Standard-Config `0^inf (10)^a D> 1^b 0^inf`; @-d-Regeln (b<a+2 → `(a-b+1, 4b-1)`, b>a+2 → `(2a+2, b-a-1)`, b=a+2 → Halt); besuchte Liste f(0,3) f(2,2) f(1,7) f(4,5) f(0,19) f(2,18) f(6,15) f(14,8); A-Modell (a>c → `(a-c, 4c+2)`, a<c → `(2a+1, c-a)`, a=c → Halt, Start A(1,2)); Rückwärtsbaum `(m/(m+4), (b-2)/(m+4))` und `(2m+1, b+m)`; Halte-Bedingung 2 = m+b; Fraktaldaten (Ziffern von φ); Tiefe 10^8 Map-Iterationen | 2026-07-20 |
| [BusyBeaverWiki — Antihydra](https://wiki.bbchallenge.org/wiki/Antihydra) (rev 7477) | Standard-Config `0^inf 1^a 0 1^b E> 0^inf`; Regeln (b gerade → b' = 3b/2+2, a' = a+2; b ungerade → a' = a-1; Halt gdw. a=0 und b ungerade); Schritt-Deltas 47, 111, 250, 500, 1209, 2713, ⋯; Random-Walk-Frage P(n) = 1/2·P(n-1) + 1/2·P(n+2), P(-1)=1, Lösung P(n) = φ^(n+1); Kuperberg-Beschleunigung | 2026-05-09 |
| [Sligocki — BB(6,2) is hard](https://www.sligocki.com/2024/07/06/bb-6-2-is-hard.html) | Antihydra als Cryptid; Herleitung der Regeln; äquivalentes Hydra-Modell h₀=8, h → h + h//2 | 2024-07-06 |
| [bbchallenge-Forum — Antihydra simulation status](https://discuss.bbchallenge.org/t/antihydra-simulation-status/242) | amling, Post #2 (2024-07-04): 11,8M Schritte → b = 5890334 (mit der Wiki abgeglichen), Simulator 23M Schritte in <10 min; C7X, Post #6 (2024-07-23): „I ran mxdys's program for a couple days, and its final line of output was 2147483648 1073720884 -20940" — der öffentliche Tiefenstand; mxdys' D&C-Programm, Post #1 (2024-07-07) | Thread-Ende 2024-07-23 |
| [OEIS A385902](https://oeis.org/A385902) | Antihydra-Zähler (b-Werte der Iteration, Start f(8,0)); b-File n=0..10000 im Volltext geprüft | b-File abgerufen 2026-09-13 |
| OEIS A386792 | BMO#1-b-File (Startkonfiguration), abgerufen | 2026-09-13 |

Öffentliche Tiefen (Quellenvergleich, kein eigener Rekordanspruch): Antihydra 2^31
Schritte (C7X 2024-07-23, mit mxdys' Programm; der Thread endet dort; die Wiki-Seite
nennt — Stand 2026-05-09 — keinen tieferen Wert). BMO#1: 10^8 Map-Iterationen (Wiki
rev 8053).

## 2. Reduktionen lokal beidseitig verifiziert (E2-§4.4-Lücke geschlossen)

Werkzeug: `tools/reductions.py` (+ `tools/test_reductions.py`), Artefakt
`data/reductions.txt` (`[ARTIFACT]`), Blatt `data/bmo-phase2.msheet` (Runner-Verdikte).
Orakel ist der Roh-TM-Simulator `bemyself.turing`; der eigene Tape-Stepper für
Arbiträr-Konfigurationen wird vor Gebrauch gegen `run_checkpoints` auf der
Leerband-Trajektorie zeilengenau abgeglichen (Zustand, Kopf, jede Zelle; Schritte
0, 1, 5, 23, 45, 113, 249, 1000, 100000 — 0 Abweichungen für beide Maschinen).

**Richtung A — Maschine → Map** (Leerbandlauf, kanonische Konfigurationen):

- BMO#1: 12 Konfigurationen, erste f(0,3), letzte f(29,23), Zwischenschritte
  `[18, 22, 68, 136, 82, 238, 522, 358, 1124, 2146, 198]`; die ersten 8 sind exakt die
  von der Wiki gelistete Besuchsliste, die weiteren 4 sind unsere Fortsetzung
  derselben Kette. Abweichungen: keine.
- Antihydra: 12 Konfigurationen, A(0,4) → A(13,677), Deltas
  `[47, 111, 250, 500, 1209, 2713, 6092, 13460, 30622, 68396, 154608]`; die Wiki-Deltas
  47…2713 stimmen exakt, 6092 ff. ist unsere Fortsetzung (Wiki endet dort mit „⋯").
  Abweichungen: keine.

**Richtung B — Map → Maschine** (konstruierte kanonische Konfiguration je (a,b),
Roh-Simulator bis zur nächsten kanonischen Konfiguration bzw. zum Halt):

- BMO#1, Fenster a ∈ 0..24, b ∈ 2..60 (ohne die Randbedingung b = a+2):
  1450 Nachfolger geprüft, 0 Abweichungen.
- Antihydra, Fenster a ∈ 0..20, b ∈ 2..40: 800 Nachfolger, 0 Abweichungen; die 19
  Haltefälle stimmen exakt mit der dokumentierten Bedingung überein (a=0, b ungerade).
- Hydra-Form: h = b+4, h → h + h//2, Zähler +2/−1 läuft 3000 Schritte deckungsgleich
  mit der A-Regel-Kette; Min-Zähler bei 2000 Schritten 0, Bit-Länge von h 1173.

**Zwei Domänen-Befunde (Korrekturen an der Doku):**

1. **Antihydra, b = 1 liegt außerhalb der Regeln.** Die dokumentierten Bedingungen
   (b ≥ 2 gerade, b ≥ 3 ungerade) sind nötig: für konstruierte Konfigurationen mit
   b = 1 folgt die Maschine den Regeln nicht (21/21 Fälle im Fenster a ∈ 0..20
   weichen ab). Auf der Leerband-Trajektorie wird b = 1 nie erreicht.
2. **BMO#1, b = a+2 ist eine Renormierungsstufe vor dem Halt.** Die @-d-Regel sagt
   „Halt"; der Roh-Simulator läuft in allen 25 geprüften Fällen (a ∈ 0..24) noch
   eine kanonische Kopie weiter: Nachfolger von f(a, a+2) ist f(2a+2, 1), und von
   dort hält die Maschine in allen 25 Fällen. Für die Haltefrage sind beide Lesarten
   äquivalent, die exakte Regel-Aussage ist aber um eine Stufe versetzt.

Beide Befunde sind genau die Klasse von Fehlern, die die beidseitige Prüfung finden
soll: eine einseitige (nur Trajektorie) Prüfung sieht sie nicht.

## 3. Verifizierte Läufe

**Antihydra — 2^32 Schritte (Block-Divide-and-Conquer).** Methode: mxdys' D&C
(Forum 2024-07-07): die Paritätsfolge der ersten n Schritte hängt nur von h modulo
2^n ab; jedes Blatt rechnet 2^8 Schritte, die Korrektur `3^(2^k)·x − c` wird von den
Halbblöcken zum Elternblock komponiert (Patch-up). Implementierung
`bemyself/experiments/antihydra_deep.py` mit libgmp über `ctypes` (order=1,
Big-Endian-Bytes; Backend-Selbsttest gegen CPython bei jedem Start) und
CPython-Fallback. Kommando (Artefakt `data/antihydra-deep-2p32.txt`):

```
python3 -m bemyself.experiments.antihydra_deep --depth 32 --also 11800000 --verify-brute 20
```

Ergebnis (Laufzeit bis 2^32: 1566,9 s bzw. 1788,7 s in zwei Durchläufen,
≈26–30 min auf 1 Kern eines 16-Kern-Hosts):

- **2^32 = 4 294 967 296 Schritte: Zähler = 2 147 493 851, Abweichung +10 203**
  (Abweichung = Zähler − ⌊Schritte/2⌋), Minimum des Zählers 0 (nie −1 → kein Halt
  auf diesem endlichen Lauf).
- Externe Anker auf dem Weg: **2^31: Zähler = 1 073 720 884, Abweichung −20 940** —
  identisch mit der dokumentierten C7X-Zeile `2147483648 1073720884 -20940`
  (Forum Post #6, 2024-07-23, mit mxdys' Programm); **11 800 000 Schritte: Zähler =
  5 890 334** — exakt der von amling im Forum verifizierte Wert (Post #2, 2024-07-04).
  Zwei unabhängige Fremdpunkte, beide auf den exakten Wert getroffen.
- Interne Verifikation: D&C == einfache Rekurrenz für alle Zweierpotenzen bis 2^20
  (Teil des Laufs: `check.brute.depth=20 checkpoints_compared=21 mismatches=none`),
  zusätzlich Tests bis 2^12 über Blockbasen 0..8 und alle Zweierpotenzen;
  OEIS-A385902-b-File n = 0..10000 (10001 Werte) exakt reproduziert
  (`--check-prefix`).
- **Unabhängiges Orakel:** der Roh-TM-Simulator selbst, 2^32 Schritte:
  `halts=False steps=4294967296 score=86040` in 6 min 57 s (Artefakt
  `data/raw-antihydra-2p32.txt`). Die Haltefrage des Roh-Simulators und der Zähler der
  Map sind dieselbe Frage — der Rohlauf belegt „kein Halt innerhalb 2^32" ohne die
  Map-Kette.

Einordnung (ehrlich): unsere verifizierte Tiefe 2^32 liegt über dem öffentlich
dokumentierten 2^31, aber die Methode ist öffentlich und der Vorsprung ist Faktor 2;
wir behaupten **keinen Weltrekord**, sondern eine mit unserer Kette reproduzierte und
extern verankerte Tiefe. Ein `[COMPUTE]`-Anker für den 2^32-Lauf ist nicht möglich:
`COMPUTE_TIMEOUT` (300 s) liegt weit unter der Laufzeit — die Verankerung läuft über
`[ARTIFACT]` (Datei-Digest) + `[COMPUTE]` auf 2^22 (Werkzeug-/Backend-Reproduktion)
+ `[SEARCHED]` auf 2^32 (Roh-TM, ≈7 min).

**BMO#1 — 10^7 Map-Iterationen, und warum nicht 10^8.** Kommando (Artefakt
`data/bmo1-run.txt`):

```
python3 yesdocs/formal-conjectures/tools/reductions.py --bmo1-run 10000000
```

Ergebnis: 10^7 Iterationen ohne a = b (kein Halt-Hinweis auf dem endlichen Lauf);
Endpaar a/b mit 2 178 111 / 2 178 113 Bit (≈656 000 Dezimalziffern), Digest
`sha256(hex(a):hex(b)) = 1aa72b0b90…` (im Artefakt vollständig); Laufzeit ≈13 min
(780 s bzw. 822 s in zwei Läufen, byte-identische Ausgabezeile).

Grenze, gemessen: 10^6 Iterationen 6,5 s, 10^7 Iterationen ≈800 s (Faktor ≈120 für
Faktor 10 → quadratisch in den Bit-Kosten, wie erwartet: die Werte wachsen linear in
n Bits). Hochgerechnet auf die öffentliche Tiefe 10^8: ≈22 h auf dieser Maschine
für einen einzigen Lauf — außerhalb dieses Budgets. Eine D&C-Beschleunigung wie bei
Antihydra ist hier **nicht** verfügbar: die Fallunterscheidung `a > b` ist eine
globale Eigenschaft der vollen Werte, es gibt keine Low-Bit-Selbstähnlichkeit, die
man maskieren könnte. Deshalb bleibt es bei „verifizierte Tiefe 10^7 mit unserer
Kette, 10× über dem E2-Probe, 10× unter dem öffentlichen Bestwert" — ehrlich
beschriftet statt hochgerechnet.

## 4. Strukturjagd (exakte Teilstruktur, keine Lösung)

**(a) Random-Walk-Lösung der Antihydra-Frage ist exakt.** Die Wiki-Frage
P(n) = 1/2·P(n-1) + 1/2·P(n+2) mit P(-1) = 1 hat nach eigenen Tabellen die Lösung
P(n) = φ^(n+1). Wir prüfen die Identität exakt in Z[φ] (φ² = 1 − φ, ganzzahlige
Paare, kein Fließkomma): 1 + φ³ = 2φ und P(n-1) + P(n+2) = 2·P(n) für n = 0..200 —
0 Abweichungen (`data/structure.txt`, `[ARTIFACT]`). Das ist eine finite exakte
Verifikation der Rekurrenz-Äquivalenz, kein Beweis der offenen Frage (P(n) → 0 bleibt
offen).

**(b) BMO#1-Rückwärtsbaum: exakt bis Level 18, ein Wiki-Fund.** Der Baum aus
(m,b) = (1,0) mit den Urbildern `(m/(m+4), (b-2)/(m+4))` und `(2m+1, b+m)` in exakter
Bruchrechnung bis Level 18 (262 144 Knoten):

- **kein** Knoten erfüllt 2 = m + b (bis Level 18) — konsistent mit „offen";
- die Invariante m > b verletzt kein Knoten;
- die Wiki-Rekordliste der nächsten Punkte zur Halte-Linie wird für Level 5, 6, 7, 9,
  10 exakt reproduziert; die Ausnahme: Wiki nennt für Level 8 („below") den Anstieg
  669/401 — dieser Punkt existiert im Baum bis Level 18 überhaupt nicht. Der nächste
  Punkt unterhalb der Linie ist **699/401** (Abstand 0.0549), erzeugt auf Level 8.
  Wir halten 669/401 für eine Zifferntransposition (6**6**9 → 6**9**9) in der
  Wiki-Tabelle; Level 19/20 lagen außerhalb des geprüften Fensters. (Die Wiki-Liste ist
  ein laufender Rekord über alle Level, nicht ein Level-Minimum — die Prüfung
  vergleicht dieselbe Semantik.)

Grenzen: die fraktale Struktur (Ziffern von φ) ist in der Doku unpräzise beschrieben;
ein exakter Brückenbeweis Baum ↔ φ-Ziffern wäre ein eigenes Projekt. Der Baum gibt
keine neue Schranke für die Haltefrage her (er ist exakt äquivalent).

## 5. Was hat V1.1 geleistet? (Pflichtabschnitt, nüchtern)

**Geleistet:**

- **Blätter + Runner-Verdikte statt Prosa:** `data/bmo-phase2.msheet` liefert 8
  Roh-TM-Zeugen (feste kanonische Checkpoints für beide Maschinen) + 8 CLAIM-Zeilen
  = 16 maschinell entschiedene Verdikte, alle `#ok`
  (`python3 -m bemyself.msheet run data/bmo-phase2.msheet`). Zusammen mit E2s
  `bmo-attack.msheet` (8 Verdikte) trägt die Angriffs-Kette 24 Runner-Verdikte.
- **Die Verdikte haben Zähne (Negativkontrolle, zweifach):** (i) Blätter ohne
  `+`-Marker werden frisch ausgeführt (`#ok: v1 … v8`); (ii) ein mutierter Checkpoint
  (Kopf 43 → 44 bei t=4917) wird als `REFUTED` gemeldet („sim: at step 4917 the head
  is at 43, not 44"), der abhängige Claim `c1` als UNVERIFIABLE.
- **Anker-Kette:** `data/attack-01-check.txt` bindet alle zentralen Aussagen an
  ausführbare Prüfungen: `[SEARCHED]` (Roh-TM 10^8 bzw. 2^32 Schritte),
  `[COMPUTE]` (Deep-Tool, bwrap-Sandkasten, Digest-Vergleich) und `[ARTIFACT]`
  (Blätter, Reduktions-/Struktur-/Lauf-Artefakte). Jede Erfolgsaussage hängt an einer
  Prüfung, nicht an Formulierungsdisziplin.
- **Fehlerfang durch die Prüfschicht:** die Format-/Semantikfalle „`Int`/`//`" aus E2
  §3.1 blieb hier ohne Treffer, aber die beidseitige Fensterprüfung fand zwei
  echte Doku-Korrekturen (b=1, b=a+2) — genau die Fehlerklasse, die eine einseitige
  Prüfung übersieht.

**Nicht geleistet / Grenzen:**

- Das Witness-Vokabular (`sim` läuft vom Leerband) trägt nur die *Trajektorie*; die
  eigentliche Reduktions-Verifikation (beidseitig, konstruierte Tape-Konfigurationen,
  Lese-/Schreibrichter) war in Python zu bauen. Der Sheet-Runner hat die
  Trajektorien-Checkpoints zertifiziert, nicht die Reduktion.
- Die Domänen-Befunde (b=1, b=a+2) kamen aus dem beidseitigen Fensterlauf, nicht aus
  dem Blatt. Blätter halten fest, was man vorher verstanden hat; sie *entdecken* eine
  falsch verstandene Domäne nicht.
- Die Rekordläufe selbst (Block-D&C, GMP, 2^32) liegen außerhalb der Blätter — als
  `[ARTIFACT]`/`[COMPUTE]`/`[SEARCHED]` ankerbar, aber nicht als Sheet-Verdikt
  (COMPUTE-Timeout 300 s).
- **Zeitaufwand (Eigenmessung, grob):** Blatt-Generierung + Runner ≈ 10 min; die
  beiden Python-Werkzeuge mit Tests ≈ 2 h; Doku/Anker ≈ 40 min; die Deep-Läufe ≈ 45
  min Wartezeit (parallel zur Arbeit). Netto hat die Notation die Werkzeugzeit nicht
  verkürzt — sie hat die Nachprüfbarkeit erhöht (24 Verdikte + Anker statt Prosa).
- Wo die Notation *nicht* half: beim Entwurf der D&C-Maskierungsregel und der
  Domänen-Grenzen. Dort war der Fehlerfang ein Python-Fensterlauf, kein Blatt.

**Befund:** V1.1 funktioniert als *Prüfschicht* (Verdikte statt Behauptungen, Anker
statt Vertrauen, Fehlerfang belegt) und stößt dort an eine Grenze, wo die Arbeit in
neuem ausführbarem Code liegt. Ohne die Notation wären die Aussagen dieses Berichts
nicht schlechter, aber weniger überprüfbar.

## 6. Grenzen, keine Überclaims

- Kein Halt-Beweis und kein Positivitäts-Beweis für BMO#1 oder Antihydra. Beide
  Maschinen bleiben offen.
- Endliche Beobachtungen mit Budget; „kein Halt innerhalb N Schritten" ist keine
  Aussage über alle Schritte.
- Tiefenvergleich nur mit Quellen: Antihydra 2^32 > öffentlich 2^31 (Faktor 2, Methode
  öffentlich) → „verifizierte Tiefe", kein Rekordanspruch. BMO#1 10^7 < öffentlich
  10^8 → ehrlich als Unterbietung ausgewiesen, mit gemessener Begründung.
- Der 2^32-Lauf ist nicht per `[COMPUTE]` verifizierbar (300-s-Timeout); die Kette
  ist `[ARTIFACT]` + `[COMPUTE]`(2^22) + `[SEARCHED]`(2^32, Roh-TM).
- Future Work: (i) die b=1/b=a+2-Befunde und den 669/401-Typo in die Wiki-Diskussion
  tragen (externer Schritt); (ii) exakter Brückenbeweis Baum ↔ φ-Ziffern
  (Lean-Territorium, E1-Muster); (iii) D&C-Verallgemeinerung auf weitere Cryptids mit
  Low-Bit-Struktur (Hydra-Familie).

## 7. Artefakte und Kommandos

| Artefakt | Inhalt | Kommando |
|---|---|---|
| `data/reductions.txt` | Reduktions-Verifikation, beide Richtungen, Domänen | `python3 yesdocs/formal-conjectures/tools/reductions.py` |
| `data/structure.txt` | φ-Identität (Z[φ]) + BMO#1-Rückwärtsbaum | `… tools/reductions.py --structure` |
| `data/bmo-phase2.msheet` | 8 Roh-TM-Zeugen + 8 Claims (Runner-verifiziert) | `python3 -m bemyself.msheet run … --json` |
| `data/antihydra-deep-2p32.txt` | Antihydra-Zähler bei 2^32 Schritten (D&C, GMP) | `python3 -m bemyself.experiments.antihydra_deep --depth 32 --also 11800000 --verify-brute 20` |
| `data/raw-antihydra-2p32.txt` | Roh-TM-Kreuzlauf 2^32 Schritte (unabhängiges Orakel) | `python3 -m bemyself.turing 1RB1RA_…---0RA 4294967296` |
| `data/bmo1-run.txt` | BMO#1-Map 10^7 Iterationen + Digest des Endpaars | `… tools/reductions.py --bmo1-run 10000000` |
| `data/attack-01-check.txt` | Anker-Bericht (`bemyself check --strict`) | `python3 -m bemyself check --report data/attack-01-check.txt --strict` |

Verifikationskette (alle Kommandos reproduzierbar): Repo-Suite (`make test`),
`tools/test_reductions.py`, `tests/test_antihydra_deep.py`, 16 Runner-Verdikte im
Blatt `bmo-phase2.msheet` (+ 8 aus E2), Determinismus der Artefakte (byte-identische
Wiederholung), Quellen-Anker (OEIS-b-File, zwei Forumswerte, Wiki-Listen).

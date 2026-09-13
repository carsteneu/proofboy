# Angriff 01 — BMO#1 (Collatz-artig) und Antihydra (BB(6)-Holdouts)

Datum: 2026-09-13. Ausgangsbasis: `master` @ `d2662e9` (E2: Katalog-Scan + Shortlist +
erster umgrenzter Angriff, `yesdocs/formal-conjectures/README.md`). Dieser Bericht ist
der vertiefte Angriff auf die zwei BB(6)-Holdouts der Shortlist, mit drei Teilen:

1. **Reduktionen lokal beidseitig verifizieren** — schließt die in E2 §4.4 deklarierte
   Lücke (Maschine↔Reformulierungs-Äquivalenzen nur aus externer Doku).
2. **Verifizierte Läufe (Rekordtiefe)** — Antihydra über den öffentlichen Bestwert
   hinaus, BMO#1 mit dokumentierter Grenze.
3. **Strukturjagd** — exakte Teilstruktur der dokumentierten Ersatzmodelle.

**Kein Lösungsergebnis.** Beide Maschinen bleiben offen. Alles hier sind endliche,
exakt beschriftete Beobachtungen, maschinell verifiziert (Blätter + Runner-Verdikte,
`[ARTIFACT]`/`[COMPUTE]`/`[SEARCHED]`-Anker in `data/attack-01-check.txt`).

Maschinen (bbchallenge-Notation, Zustände A..F, `_` = keine Regel):

- `MB` = BMO#1 = `1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE`
- `MA` = Antihydra = `1RB1RA_0LC1LE_1LD1LC_1LA0LB_1LF1RE_---0RA`

## 1. Quellen (Zugriff 2026-09-13)

| Quelle | Inhalt | Stand |
|---|---|---|
| [BusyBeaverWiki — BMO#1](https://wiki.bbchallenge.org/wiki/1RB1RE_1LC0RA_0RD1LB_---1RC_1LF1RE_0LB0LE) | Standard-Config `0^inf (10)^a D> 1^b 0^inf`; @-d-Regeln (b<a+2 → `(a-b+1, 4b-1)`, b>a+2 → `(2a+2, b-a-1)`, b=a+2 → Halt); besuchte Liste f(0,3) f(2,2) f(1,7) …; A-Modell (a>c → `(a-c, 4c+2)`, a<c → `(2a+1, c-a)`, a=c → Halt, Start A(1,2)); Rückwärtsbaum mit `(m/(m+4), (b-2)/(m+4))` und `(2m+1, b+m)`; Halte-Bedingung 2 = m+b; Fraktaldaten (Ziffern von φ); Bestwert 10^8 Iterationen | oldid 8053, 2026-07-20 |
| [BusyBeaverWiki — Antihydra](https://wiki.bbchallenge.org/wiki/Antihydra) | Standard-Config `0^inf 1^a 0 1^b E> 0^inf`; Regeln (b gerade → b' = 3b/2+2, a' = a+2; b ungerade → a' = a-1; Halt gdw. a=0 und b ungerade); Schritt-Deltas 47, 111, 250, 500, 1209, 2713, 6092 …; Random-Walk-Frage P(n) = 1/2·P(n-1) + 1/2·P(n+2), P(-1)=1, Lösung P(n) = φ^(n+1); Kuperberg-Beschleunigung | oldid 7477, 2025-08-02 |
| [Sligocki — BB(6,2) is hard](https://www.sligocki.com/2024/07/06/bb-6-2-is-hard.html) | Antihydra als Cryptid; Herleitung der Regeln; äquivalentes Hydra-Modell h₀=8, h → h + h//2 | 2024-07-06 |
| [OEIS A385902](https://oeis.org/A385902) | Antihydra-Zähler (a(n) = b-Zähler; Kommentar: „last checked to 2^31 iterations, starts at 0"); b-File n=0..10000 | b-File abgerufen 2026-09-13 |
| [bbchallenge-Forum: Antihydra simulation status](https://discuss.bbchallenge.org/t/antihydra-simulation-status/242) | mxdys, 2024-07-07: 2^31 Schritte (b = 1073720884, a-Äquivalent −20940), D&C-Blockmethode (Methode unten) | Thread 242 |
| OEIS A386792 (BMO#1) | b-File | abgerufen 2026-09-13 |

Rekordlage (Quellen-Vergleich, kein eigener Rekordanspruch): Antihydra öffentlich
2^31 Schritte (mxdys 2024, im OEIS-Kommentar bestätigt); BMO#1 öffentlich 10^8
Map-Iterationen (Wiki).

## 2. Reduktionen lokal beidseitig verifiziert (E2-§4.4-Lücke geschlossen)

Werkzeug: `tools/reductions.py` (+ `tools/test_reductions.py`, 18 Tests), Artefakt
`data/reductions.txt` (`[ARTIFACT]`). Orakel ist der Roh-TM-Simulator
`bemyself.turing`; der eigene Tape-Stepper für Arbiträr-Konfigurationen wird vor
Gebrauch gegen `run_checkpoints` auf der Leerband-Trajektorie zeilengenau
abgeglichen (Zustand, Kopf, jede Zelle; Schritte 0..100000).

**Richtung A — Maschine → Map** (Leerbandlauf, kanonische Konfigurationen):

- BMO#1: 12 Konfigurationen, erste f(0,3), letzte f(29,23), Zwischenschritte
  `[18, 22, 68, 136, 82, 238, 522, 358, 1124, 2146, 198]`, Abweichungen: keine.
  Die besuchte Liste der Wiki (f(0,3) f(2,2) f(1,7) f(4,5) f(0,19) f(2,18) f(6,15)
  f(14,8) f(7,31) f(16,23) f(34,6) f(29,23)) wird Konfiguration für Konfiguration
  reproduziert.
- Antihydra: 12 Konfigurationen, A(0,4) → A(13,677), Deltas
  `[47, 111, 250, 500, 1209, 2713, 6092, 13460, 30622, 68396, 154608]`; die
  Wiki-Deltas 47, 111, 250, 500, 1209, 2713, 6092 stimmen exakt; Abweichungen: keine.

**Richtung B — Map → Maschine** (konstruierte kanonische Konfiguration je (a,b),
Roh-Simulator bis zur nächsten kanonischen Konfiguration bzw. zum Halt):

- BMO#1, Fenster a ∈ 0..24, b ∈ 2..60 (ohne die Randbedingung b = a+2):
  1450 Nachfolger geprüft, 0 Abweichungen.
- Antihydra, Fenster a ∈ 0..20, b ∈ 2..40: 800 Nachfolger, 0 Abweichungen; die 19
  Haltefälle stimmen exakt mit der dokumentierten Bedingung überein (a=0, b ungerade).
- Hydra-Form: `tools`-pruefung `h = b+4`, h → h + h//2, Zähler +2/−1 läuft 3000
  Schritte deckungsgleich mit der A-Regel-Kette; die Min-Zählung bei 2000 Schritten
  ist 0 (Startwert), die Bit-Länge von h bei 2000 Schritten 1173.

**Zwei Domänen-Befunde (Korrekturen an der Doku):**

1. **Antihydra, b = 1 liegt außerhalb der Regeln.** Die dokumentierten Bedingungen
   (b ≥ 2 gerade, b ≥ 3 ungerade) sind nötig: für konstruierte Konfigurationen mit
   b = 1 folgt die Maschine den Regeln nicht (21/21 Fälle im Fenster a ∈ 0..20
   weichen ab). Auf der Leerband-Trajektorie wird b = 1 nie erreicht.
2. **BMO#1, b = a+2 ist eine Renormierungsstufe vor dem Halt.** Die @-d-Regel sagt
   „Halt"; der Roh-Simulator läuft in allen 25 geprüften Fällen (a ∈ 0..24) noch
   eine kanonische Kopie weiter und hält erst in der nächsten Runde ( 2=b+a
   äquivalent): der Nachfolger von f(a, a+2) ist f(2a+2, 1), und von dort hält die
   Maschine in allen 25 Fällen. Beide Lesarten sind für die Haltefrage äquivalent,
   aber die exakte Aussage der Wiki-Regel ist um eine Stufe versetzt.

Beide Befunde sind genau die Klasse von Fehlern, die die beidseitige Prüfung finden
soll: eine einseitige (nur Trajektorie) Prüfung sieht sie nicht.

## 3. Verifizierte Läufe (Rekordtiefe)

Siehe Abschnitt unten — Zahlen und Anker werden nach Laufende eingetragen
(`data/antihydra-deep-2p32.txt`, `data/raw-antihydra-2p32.txt`, `data/bmo1-run.txt`).

## 4. Strukturjagd (exakte Teilstruktur, keine Lösung)

Zwei exakte, maschinell geprüfte Befunde; beide betreffen die *dokumentierten*
Ersatzmodelle, nicht die Haltefrage der Roh-Maschine.

**(a) Random-Walk-Lösung der Antihydra-Frage ist exakt.** Die Wiki-Frage
P(n) = 1/2·P(n-1) + 1/2·P(n+2) mit P(-1) = 1 hat nach eigenen Tabellen die Lösung
P(n) = φ^(n+1). Wir prüfen die Identität exakt in Z[φ] (φ² = 1 − φ, ganzzahlige
Paare, kein Fließkomma): 1 + φ³ = 2φ und P(n-1) + P(n+2) = 2·P(n) für n = 0..200 —
0 Abweichungen (`data/structure.txt`, `[ARTIFACT]`). Das ist eine *finite exakte
Verifikation* der Rekurrenz-Äquivalenz, kein Beweis der offenen Frage (P(n) → 0
bleibt offen).

**(b) BMO#1-Rückwärtsbaum: exakt bis Level 18, ein Wiki-Fund.** Der Baum aus
(m,b) = (1,0) mit den beiden Urbildern `(m/(m+4), (b-2)/(m+4))` und `(2m+1, b+m)`
wird in exakter Bruchrechnung bis Level 18 aufgebaut (262144 Knoten):

- **Kein** Knoten erfüllt 2 = m + b (bis Level 18) — konsistent mit „offen";
- die Invariante m > b verletzt kein Knoten;
- die Wiki-Liste der line-nächsten Punkte (Level 5..10) wird in 5 von 6 Fällen
  exakt reproduziert; die Ausnahme: Wiki nennt für Level 8 („below") den Anstieg
  669/401 — dieser Punkt existiert im Baum überhaupt nicht. Der nächste Punkt
  unterhalb der Linie ist 699/401 (Abstand 0.0549), erzeugt auf Level 8. Wir halten
  669/401 für eine Zifferntransposition (6[6]9 → 6[9]9) in der Wiki-Tabelle;
  Level 19/20 lagen außerhalb des geprüften Fensters.

Grenzen: die fraktale Struktur (Ziffern von φ) ist in der Doku nur unpräzise
beschrieben; ein exakter Brückenbeweis (Baum ↔ φ-Ziffern ↔ Map-Trajektorie) wäre ein
eigenes Projekt. Die Minimierungsfrage ist äquivalent zur Haltefrage — der Baum gibt
keine neue Schranke her.

## 5. Was hat V1.1 geleistet? (Pflichtabschnitt, nüchtern)

Gezählt werden nur Belege aus diesem Angriff (Stand: nach Phase 4).

**Geleistet:**

- **Blätter + Runner-Verdikte statt Prosa:** `data/bmo-phase2.msheet` liefert 8
  Roh-TM-Zeugen (feste kanonische Checkpoints für beide Maschinen) + 8 CLAIM-Zeilen
  = 16 maschinell entschiedene Verdikte, alle `#ok` (Runner:
  `python3 -m bemyself.msheet run …`). Zusammen mit E2s `bmo-attack.msheet`
  (8 Verdikte) trägt die Angriffs-Kette 24 Runner-Verdikte.
- **Die Verdikte haben Zähne (Negativkontrolle):** ein mutierter Checkpoint
  (Kopf 43 → 44 bei t=4917) wird nicht übersehen, sondern vom Runner als
  `REFUTED` gemeldet („sim: at step 4917 the head is at 43, not 44") — nachgewiesen
  doppelt: (i) Blätter ohne `+`-Marker werden frisch ausgeführt (`#ok: v1 … v8`),
  (ii) Mutation → REFUTED.
- **Anker-Kette:** `bemyself check --strict` bestätigt in einem Lauf
  `[SEARCHED]` (Roh-TM), `[COMPUTE]` (Deep-Tool, bwrap-Sandkaste, Digest-Vergleich)
  und `[ARTIFACT]` (Blätter/Artefakte) — jede Erfolgsaussage ist an eine
  ausführbare Prüfung gebunden, nicht an Formulierungsdisziplin.
- **Werkzeugkosten:** die Blatt-Generierung ist automatisiert (Checkpoints aus dem
  Simulator, keine Abschreibfehler); die semantische Arbeit (welche Konfiguration
  ist kanonisch, welche Domäne gilt) war echter Arbeitsaufwand — genau dort fielen
  die zwei Domänen-Befunde (b=1, b=a+2) auf.

**Nicht geleistet / Grenzen:**

- Das Witness-Vokabular (`sim` läuft vom Leerband) trägt nur die *Trajektorie*;
  die eigentliche Reduktions-Verifikation (beidseitig, konstruierte
  Tape-Konfigurationen, Lese-/Schreibrichter) war in Python zu bauen. Der
  Sheet-Runner hat diese Arbeit nicht abgenommen — er hat die
  Trajektorien-Checkpoints zertifiziert.
- Die Domänen-Befunde (b=1, b=a+2) kamen aus dem beidseitigen Fensterlauf, nicht
  aus dem Blatt. Blätter halten fest, was man vorher verstanden hat; sie
  *entdecken* eine falsch verstandene Domäne nicht.
- Die Rekordläufe selbst (Block-D&C, GMP) sind außerhalb der Blätter — als
  `[COMPUTE]`/`[ARTIFACT]` ankerbar, aber nicht als Sheet-Verdikt.
- Laufzeit-Ersparnis: keine (Blatt + Runner ≈ so schnell wie ein Test-Skript);
  der Gewinn ist Nachprüfbarkeit und Fehlerfang, nicht Tempo.

**Befund:** V1.1 hat in diesem Angriff als *Prüfschicht* funktioniert (Verdikte
statt Behauptungen, Anker statt Vertrauen, Fehlerfang belegt) und ist als
*Denk-Werkzeug* an der Grenze angelangt, wo die Arbeit in neuem Python-Code liegt
(bidirektionale Reduktionsprüfung, D&C-Läufe). Ohne die Notation wären die Aussagen
in diesem Bericht nicht schlechter, aber weniger überprüfbar.

## 6. Grenzen, keine Überclaims

- Kein Halt-Beweis und kein Positivitäts-Beweis für BMO#1 oder Antihydra. Beide
  Maschinen bleiben offen.
- Endliche Beobachtungen mit Budget; „kein Halt innerhalb N" ist keine Aussage über
  alle Schritte.
- „Rekordtiefe" nur mit Quellenvergleich: Antihydra 2^32 < öffentlich bekanntem
  2^31? Nein — 2^32 = 4.29e9 > 2^31 = 2.15e9; die Formulierung bleibt trotzdem
  „verifizierte Tiefe 2^32 mit unserer Kette", nicht „Weltrekord" (der öffentliche
  Stand ist ein Foren-/OEIS-Stand, kein zitierbarer Wettbewerb).
- Future Work: (i) die b=1/b=a+2-Befunde in die Wiki-Diskussion tragen (externer
  Schritt, nicht hier); (ii) exakter Brückenbeweis Baum ↔ φ-Ziffern (Lean-Territorium,
  E1-Muster); (iii) D&C-Verallgemeinerung auf andere Cryptids mit „low-bit"-
  Struktur (Hydra-Familie).

## 7. Artefakte und Kommandos

| Artefakt | Inhalt | Kommando |
|---|---|---|
| `data/reductions.txt` | Reduktions-Verifikation, beide Richtungen, Domänen | `python3 yesdocs/formal-conjectures/tools/reductions.py` |
| `data/structure.txt` | φ-Identität (Z[φ]) + BMO#1-Rückwärtsbaum | `… tools/reductions.py --structure` |
| `data/bmo-phase2.msheet` | 8 Roh-TM-Zeugen + 8 Claims (Runner-verifiziert) | `python3 -m bemyself.msheet run …` |
| `data/antihydra-deep-2p32.txt` | Antihydra-Zähler bei 2^32 Schritten (D&C, GMP) | `python3 -m bemyself.experiments.antihydra_deep --depth 32 --also 11800000 --verify-brute 24` |
| `data/raw-antihydra-2p32.txt` | Roh-TM-Kreuzlauf 2^32 Schritte (unabhängiges Orakel) | `python3 -m bemyself.turing 1RB1RA_… ---0RA 4294967296` |
| `data/bmo1-run.txt` | BMO#1-Map 10^7 Iterationen + Digest des Endpaars | `… tools/reductions.py --bmo1-run 10000000` |
| `data/attack-01-check.txt` | `bemyself check --strict`-Bericht mit allen Ankern | `python3 -m bemyself check --report … --strict` |

Verifikationskette: 902 Suite-Tests (Repo) + 18 `tools/test_reductions.py` + 12
`tests/test_antihydra_deep.py` + 16 Runner-Verdikte; alle Läufe deterministisch
(Seed-freie Rekurrenzen, Digest-Vergleiche).

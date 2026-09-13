# Erdős–Straus: parametrisch abgedeckte Progressionsklassen (P12)

Diese Auswertung ordnet fuer die Vermutung von Erdős–Straus (jedes `n >= 2`
hat `a, b, c >= 1` mit `4/n = 1/a + 1/b + 1/c`) jeder betrachteten Klasse
von `n` einen von drei Zustaenden zu:

1. **Fuer alle `n` der Progression** gilt eine verifizierte Identitaet --
   exakt und maschinell geprueft. Die IDENT-Marker weiter unten sind der
   Pruefbericht dieser Datei.
2. Nur **endlich** belegt: das P11-Artefakt deckt alle `n <= 1.000.000` mit
   expliziten Zeugen ab.
3. **Keine Parametrisierung bekannt** in den konsultierten Quellen.

Kein Zustand davon ist ein Beweis der Vermutung. Eine verifizierte
Identitaet deckt eine Progression fuer alle Parameter ab; die Vermutung
braucht alle `n`, und die abgedeckten Progressionen lassen Klassen offen
(Abschnitt 4).

Werkzeug: der Claim-Typ IDENT (README, Abschnitt "Parameterisierte
Identitaeten"; Modul `bemyself/claimtypes/ident.py`). Nachrechnen dieser
Datei:

```
python3 -m bemyself check --report yesdocs/erdos-straus/README.md --strict
```

Erwartet: Exit 0, alle sechs Marker `CONFIRMED` (der Test
`tests/test_ident.py` fixiert das: jede in dieser Datei stehende
Behauptung muss verifizieren).

## 1. Verifizierte Identitaeten (fuer alle Parameter)

Alle Zeilen unten sind Skalierungen eines kleinen Zeugen: Ist
`4/d = 1/x + 1/y + 1/z`, so ist `4/(d*t) = 1/(xt) + 1/(yt) + 1/(zt)` fuer
jedes `t >= 1`. Die Skalierung ist das Standard-Argument der Literatur
(Wikipedia: "whenever `4/n` has a three-term expansion, so does `4/mn` for
all positive integers `m`"); die konkreten Zeugen sind elementar und hier
maschinell geprueft.

- **n = 2t -- alle geraden n.** Zeuge `(t, 2t, 2t)`:
  `1/t + 1/(2t) + 1/(2t) = 2/t = 4/(2t)`.

  [IDENT: n=2t ; a=t, b=2t, c=2t]

- **n = 3t -- alle Vielfachen von 3.** Zeuge `(t, 4t, 12t)`:
  `(12 + 3 + 1)/(12t) = 16/(12t) = 4/(3t)`.

  [IDENT: n=3t ; a=t, b=4t, c=12t]

- **n = 5t -- alle Vielfachen von 5.** Zeuge `(2t, 4t, 20t)`:
  `(10 + 5 + 1)/(20t) = 16/(20t) = 4/(5t)`.

  [IDENT: n=5t ; a=2t, b=4t, c=20t]

- **n = 7t -- alle Vielfachen von 7.** Zeuge `(3t, 6t, 14t)`:
  `(14 + 7 + 3)/(42t) = 24/(42t) = 4/(7t)`.

  [IDENT: n=7t ; a=3t, b=6t, c=14t]

- **n = 11t -- alle Vielfachen von 11.** Zeuge `(3t, 66t, 66t)`:
  `(22 + 1 + 1)/(66t) = 24/(66t) = 4/(11t)`.

  [IDENT: n=11t ; a=3t, b=66t, c=66t]

- **n = 13t -- alle Vielfachen von 13.** Zeuge `(4t, 26t, 52t)`:
  `(13 + 2 + 1)/(52t) = 16/(52t) = 4/(13t)`.

  [IDENT: n=13t ; a=4t, b=26t, c=52t]

Allgemeiner: fuer jedes `d >= 2`, fuer das ein Zeuge `(x, y, z)` von `4/d`
bekannt ist, deckt `(xt, yt, zt)` die ganze Progression `n = d*t` ab, also
alle positiven Vielfachen von `d`. Maschinell verifiziert sind hier die
kleinen Faelle oben (`d = 2, 3, 5, 7, 11, 13`); fuer ein groesseres `d` ist
die jeweilige Identitaet **nicht** einzeln nachgerechnet -- die Existenz
eines Zeugen folgt dann aus der Rechenverifikation der Vermutung bis
`N = 10^17` (Salez 2014, s. Quellen) plus der Skalierung. In diesem Sinne ist
jedes `n`, das einen Teiler `d` mit `2 <= d <= 10^17` besitzt, durch eine
skalierte Identitaet abgedeckt (aber nicht durch dieses Werkzeug
nachgerechnet); offen bleiben nur `n`, deren saemtliche Primfaktoren groesser
als `10^17` sind (darunter alle Primzahlen groesser als `10^17`). Das ist
eine Folgerung aus Skalierung plus Rechenstand, kein eigenes Theorem, und
ebenfalls kein Beweis.

## 2. Parametrisch abgedeckt in der Literatur, aber nicht affin

Diese Identitaeten sind aus den Quellen belegt, aber **nicht** in diesem
Report maschinell geprueft: der IDENT-Typ prueft nur affine Funktionen in
`t`; die folgenden Formeln haben quadratische Nenner und lassen sich in
dieser Form nicht ausdruecken. Ehrlich heisst hier: Quelle ja, Haekchen
nein.

- **n ≡ 2 (mod 3)** (Wikipedia):
  `4/n = 1/n + 1/((n+1)/3) + 1/(n(n+1)/3)` -- eine Polynomidentitaet; der
  dritte Nenner ist quadratisch in `n`.
- **Mordell (1967)**, zitiert nach Wikipedia: Polynomidentitaeten liefern
  Loesungen fuer `n ≡ 3 (mod 4)`, `n ≡ 2 oder 3 (mod 5)`,
  `n ≡ 3, 5 oder 6 (mod 7)` und `n ≡ 5 (mod 8)`. Kombiniert decken sie alle
  `n` ab ausser moeglicherweise denen mit `n ≡ 1, 121, 169, 289, 361` oder
  `529 (mod 840)`; die kleinste nicht abgedeckte Primzahl ist `1009`. Fuer
  Primzahlen formuliert Ionascu & Wilson (2010) dasselbe als Theorem 1.6
  (Ausnahmen `840k + r` mit `r` aus den Quadraten `1^2, 11^2, 13^2, 17^2,
  19^2, 23^2`).

Ein Hinweis zur Lesart: Diese Klassen-Aussagen sind Aussagen ueber
Primzahlen (Mordell/Ionascu-Wilson) beziehungsweise ueber alle `n` je Klasse;
wer eine Zahl `n` pruefen will, deren Primfaktoren alle in den
Ausnahmeklassen liegen (kleinstes Beispiel: `1009`), findet auch dort keine
der bekannten Identitaeten.

## 3. Endliches Fenster: alle n <= 1.000.000 (P11)

Modul `bemyself/experiments/erdos_straus.py`; Kommando
`python3 -m bemyself.experiments.erdos_straus 1000000`; sha256 des stdout
`e5b68dd1818d89f2c66d0e7b5a68bf906dbe7adc77c64dba015bf27058a4f89d`;
46.906.788 Bytes; Artefakt-Commit `07c166f` (auf master gemergt, README
"Erdős–Straus bis N"). Aussage: fuer jedes `n` von 2 bis 1.000.000 steht ein
expliziter Zeuge `(a, b, c)` in der deterministischen Ausgabe. Endlich
verifiziert, kein Beweis; ueber `N` hinaus sagt der Lauf nichts. (Am
12.09.2026 nachgerechnet: Hash, Bytezahl und Schlusszeile `ok 1000000 999999`
stimmen mit dem gepinnten Artefakt ueberein.)

## 4. Keine Parametrisierung bekannt

- Die `840`-Ausnahmen (`1, 121, 169, 289, 361, 529 mod 840`) sind der Stand
  nach Mordell (1967): fuer diese Klassen liefern die bekannten
  Polynomidentitaeten nichts; die kleinste nicht abgedeckte Primzahl ist
  `1009`.
- Eine eigene, beschraenkte affine Suche (Progressionsschritt `p <= 12`,
  Versatzfenster `+-40`, Steigungen bis 80) fand ausserhalb der
  Teilerklassen (Skalierungen von Zeugen kleiner Teiler `d`) keine affine
  Identitaet -- insbesondere keine fuer `n ≡ 1 (mod 3)` oder fuer
  `n ≡ 1 (mod 24)`. Das ist eine beschraenkte Suche mit deklarierten
  Grenzen, kein Nichtexistenz-Beweis.
- Mordell (1967, nach Wikipedia) begrenzt die Form solcher Identitaeten: eine
  Polynomidentitaet fuer `n ≡ r (mod p)` kann nur existieren, wenn `r` kein
  quadratischer Rest modulo `p` ist. Ein vollstaendiges Ueberdeckungssystem
  aus Identitaeten dieses Typs gibt es daher nicht -- "1 bleibt immer
  unbedeckt" (Wikipedia). Die Frage, ob es ueberhaupt eine endliche Menge
  affiner Identitaeten gibt, die alle Restklassen abdeckt, ist damit nicht
  beantwortet; diese Auswertung behauptet es nicht.

## 5. Grenzen dieser Auswertung

- Ein `CONFIRMED` im IDENT-Typ deckt eine Progression fuer alle Parameter ab;
  es ist kein Beweis der Vermutung, solange nicht alle Restklassen abgedeckt
  sind.
- Die nicht-affinen Literatur-Identitaeten (Abschnitt 2) sind hier **nicht**
  maschinell geprueft; der IDENT-Typ kann sie nicht ausdruecken. Diese Zeilen
  tragen Quelle, aber kein Haekchen.
- Die P11-Zeile ist endlich: Fenster bis `10^6`, kein Beweis.
- Quellenstand: 12.09.2026 (Wikipedia-Fassung vom Abruf; Ionascu & Wilson
  2010; Salez 2014; Mordell 1967). Rechnerischer Weltstand laut Wikipedia:
  bis `10^17` verifiziert.
- **Lean-Zwilling (E1, 13.09.2026).** Die sechs Identitaeten aus Abschnitt 1
  und ein endliches Fenster (n <= 1000) sind zusaetzlich im Lean-4-Kernel
  bewiesen: `lean/erdos-straus/` (README dort) enthaelt die sechs Klassen als
  Theoreme ueber Q fuer alle `t >= 1` plus eine generierte Zeugentabelle mit
  Kernel-Beweis fuer `2 <= n <= 1000`; `lake build` gruen, Axiom-Audit nur
  `propext`/`Classical.choice`/`Quot.sound`, kein `sorry`, kein
  `native_decide`. Das verschiebt keine Grenze dieser Auswertung: der Kernel
  deckt dasselbe Fenster und dieselben sechs Klassen -- die Vermutung bleibt
  offen (Abschnitt 5, erster Punkt).

## Nachrechnen

```
python3 -m bemyself check --report yesdocs/erdos-straus/README.md --strict
python3 -m bemyself.experiments.erdos_straus 1000000 | sha256sum
```

Erwartet: alle sechs Marker `CONFIRMED` (Exit 0); Hash
`e5b68dd1818d89f2c66d0e7b5a68bf906dbe7adc77c64dba015bf27058a4f89d`.

## Quellen

- Wikipedia (en), "Erdős–Straus conjecture", Abschnitte "Modular identities",
  "Nonexistence of identities" und "Computational results",
  <https://en.wikipedia.org/wiki/Erd%C5%91s%E2%80%93Straus_conjecture>,
  abgerufen am 12.09.2026.
- L. J. Mordell, *Diophantine Equations*, Academic Press, 1967, S. 287–290
  (zitiert nach Wikipedia).
- E. J. Ionascu, A. Wilson, "On the Erdős-Straus conjecture",
  arXiv:1001.1100 (2010) -- Theorem 1.6 (Mordell, Ausnahmen fuer Primzahlen),
  Proposition 1.3 (`n ≡ 1 (mod 24)`).
- S. E. Salez, "The Erdős-Straus conjecture: New modular equations and
  checking up to N = 10^17", arXiv:1406.6307 (2014) -- zitiert nach
  Wikipedia.
- P11-Artefakt: `bemyself/experiments/erdos_straus.py`, Commit `07c166f`;
  README, Abschnitt "Erdős–Straus bis N".

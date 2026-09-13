# erdos-straus — Lean-4-Kernel-Brücke der Erdős–Straus-Assets

Lean-4-Formalisierung der Rücküberführung aus `yesdocs/erdos-straus/README.md`
(P12: sechs parametrische Klassen-Identitäten) und
`bemyself/experiments/erdos_straus.py` (P11: Zeugen für alle n ≤ N): die
maschinell geprüften Fragmente bekommen Zwillinge im Lean-Kernel. Werkzeuge:
Lean 4.33.1 (via elan), Lake 5.0.0-src, **mathlib** (Tag `v4.33.1`, gepinnt in
`lake-manifest.json`).

## Was hier bewiesen wird

- **Semantik** (`ErdosStraus/Basic.lean`): `ok n a b c` ist die
  kreuzmultiplizierte Zeugenbedingung `4*a*b*c = n*(a*b+a*c+b*c)` mit positiven
  `a, b, c` — entscheidbar, also per `by decide` im Kernel prüfbar. `ok_sound`
  hebt ein bestandenes `decide` auf die exakte rationale Identität
  `4/n = 1/a + 1/b + 1/c` in `ℚ`. `Conjecture` hält die volle Vermutung fest —
  sie wird hier **nicht** bewiesen.
- **Parametrische Klassen** (`ErdosStraus/Scaling.lean`): das generische
  Skalierungs-Muster `scaling` (ein Zeuge für `m` skaliert zu einem Zeugen für
  jedes `m * t`) und daraus die sechs `[IDENT]`-Klassen
  (m = 2, 3, 5, 7, 11, 13) für alle `t ≥ 1` — exakt der Gültigkeitsbereich des
  IDENT-Checkers (`bemyself/claimtypes/ident.py`: n ≥ 2, positive Nenner für
  alle `t ≥ 1`). Die Zeugen sind die Spalten der Tabelle in
  `yesdocs/erdos-straus/README.md` §1.
- **Finite Brücke** (`ErdosStraus/Finite.lean`, generiert): die Zeugentabelle
  n ≤ 1000 (Quelle: P11-Modul), `witnesses_all_ok` — ein Kernel-`decide` über
  die ganze Tabelle, **axiomenfrei** — und `finite_bridge`: für jedes n mit
  `2 ≤ n ≤ 1000` existiert ein Zeugentripel mit der rationalen Identität,
  999 Fälle per `interval_cases` und `ok_sound`.
- **Generator** (`tools/gen_witnesses.py`): erzeugt `Finite.lean`
  deterministisch aus `bemyself.experiments.erdos_straus`; jede Zeile wird bei
  der Erzeugung mit exakter `fractions.Fraction`-Arithmetik nachgerechnet, und
  der sha256 des P11-stdout für dasselbe N steht im Dateikopf.

## Bauen und prüfen

```sh
export PATH="$HOME/.elan/bin:$PATH"
cd lean/erdos-straus
lake update && lake exe cache get   # einmalig: ~7,5 GB mathlib-Oleans
lake build
grep -rn 'sorry\|admit' ErdosStraus # muss leer sein
```

Axiom-Audit (Konservativität, vgl. `03-05-roundtrip-anforderungen.md` §2.1):
Datei mit `import ErdosStraus` und `#print axioms <Theorem>`-Zeilen anlegen und
mit `lake env lean <datei>` ausführen. Erwartet: `[propext, Classical.choice,
Quot.sound]` (Standard-Fundament von mathlib), kein `sorryAx`, kein
`Lean.ofReduceBool`.

Regenerieren der Tabelle (deterministisch, vom Repository-Root aus):

```sh
python3 lean/erdos-straus/tools/gen_witnesses.py 1000
```

## Evidenz (2026-09-13)

- `lake build` → `Build completed successfully (8710 jobs)` (~20 s mit
  mathlib-Cache; Kaltbau der eigenen drei Module: 10 s + 4 s + 16 s).
- Kein `sorry`/`admit` im Quelltext; kein `native_decide`.
- `#print axioms` über alle Haupt-Theoreme: `[propext, Classical.choice,
  Quot.sound]`; `witnesses_all_ok` hängt von **keinem** Axiom ab.
- Tabelle: 999 Zeilen, P11-stdout-sha256
  `1eef700ba906bf1d7b2e7cf9469cea566239816adc014948e79a1e60b92aa9f2`
  (reproduzierbar: `python3 -m bemyself.experiments.erdos_straus 1000 | sha256sum`).
- Python-Suite unverändert: 818 Tests OK.

## Ehrliche Grenzen

- Die Vermutung ist **nicht** bewiesen. Die finite Brücke deckt ein Fenster
  (n ≤ 1000), die Klassentheoreme sechs Progressionen (Vielfache von
  2, 3, 5, 7, 11, 13). Unbedeckt bleiben alle n ohne Teiler in
  {2, 3, 5, 7, 11, 13} oberhalb 1000 — zum Beispiel 1009, die kleinste nicht
  abgedeckte Primzahl der 840-Ausnahmeklassen aus
  `yesdocs/erdos-straus/README.md` §2/§4. Der rechnerische Weltstand ist 10^17
  (Salez 2014) bzw. 10^18 (Preprint 2025) — rechnerisch, nicht kernel-geprüft.
- **Kernel-Grenze der finiten Brücke (gemessen 2026-09-13):** N = 1000 baut in
  ~16 s; N = 2000 überschreitet die Default-Heartbeats der Elaboration bei der
  Tabellen-Elaboration, N = 10^4 zusätzlich in `interval_cases`. Größere N
  bräuchten eine andere Kodierung (z. B. String-Tabelle mit geprüftem Parser,
  oder `native_decide` mit Compiler-Vertrauen) oder eine feinere Aufteilung —
  bewusst nicht Teil dieser Runde.
- `native_decide` wird nicht benutzt: es verlässt sich auf den Compiler statt
  auf den Kernel (`Lean.ofReduceBool`). Die Tabelle prüft der Kernel selbst.
- Die Übersetzung „P11-Zeuge → Lean-Tabelle“ macht ein Python-Programm
  (Generator); der Kernel prüft das Ergebnis, nicht die Treue der Übersetzung
  (dieselbe Spezifikationslücke wie in `03-05` §2.3). Gegenmaßnahmen: exakte
  Fraction-Nachprüfung je Zeile, sha256-Bindung an den P11-stdout,
  deterministische Regeneration.
- Die nicht-affinen Klassen aus `yesdocs/erdos-straus/README.md` §2
  (quadratische Nenner) sind hier nicht formalisiert — sie entsprechen keinem
  `[IDENT]`-Marker und sind im IDENT-Checker bewusst ungeprüft.

## Struktur

```
ErdosStraus/Basic.lean     Semantik: ok, ok_sound, Conjecture
ErdosStraus/Scaling.lean   Skalierungs-Muster scaling + class_2/3/5/7/11/13
ErdosStraus/Finite.lean    GENERIERT: Zeugentabelle, witnesses_all_ok, finite_bridge
tools/gen_witnesses.py     Generator (P11 → Finite.lean, mit Fraction-Selbstprüfung)
```

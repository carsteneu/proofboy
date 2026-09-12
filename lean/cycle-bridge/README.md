# cycle-bridge — erster Lean-4-Beweis der Zyklus-Brücke

Lean-4-Formalisierung der ersten Zelle der Rücküberführbarkeit aus
`yesdocs/deepseek-math-notation/wiki/03-formale-bruecke/03-05-roundtrip-anforderungen.md`:
Der maschinell verifizierte `[CYCLE]`-Zeuge (Python, `bemyself/claimtypes/cycle.py`)
bekommt einen formalen Zwilling im Lean-Kernel. Bewusst minimal: nur Core/Std,
kein mathlib. Werkzeuge: Lean 4.33.1 (via elan), Lake 5.0.0-src.

## Was hier bewiesen wird

- **Sprache** (`CycleBridge/Basic.lean`): Konfiguration `Config σ`
  (`state`, `head : ℤ`, `band : ℤ → Bool`), Translation `shift c d`
  (`head + d`, `band i ↦ c.band (i − d)` — dieselbe Vorzeichenkonvention wie
  `cycle.py`: `head₂ = head₁ + d`), deterministischer Schritt `TM.step`
  (stuttert im Haltezustand), Halte-Prädikat `TM.Halts`.
- **Translations-Äquivarianz** (`TM.step_shift`):
  `step (shift c d) = shift (step c) d`.
- **Satz** (`CycleBridge/Cycle.lean`): Zyklus ⇒ Nicht-Halten.
  - `cycle_never_halts`: Gilt `step^[k] c = shift c d` mit `k > 0` und hält der
    Lauf in den ersten `k` Schritten nicht, dann hält er nie. Beweisidee: per
    Induktion `step^[n·k + r] c = shiftN n (step^[r] c)`; eine Haltezeit `t`
    zerlegt sich als `t = (t/k)·k + t mod k`, Halten ist shift-invariant, also
    gäbe es einen Halt bei `r < k` — Widerspruch.
  - `never_halts_of_certificate`: nimmt exakt die `[CYCLE]`-Zertifikatsform
    `(t1, t2, d)` mit `step^[t2] c = shift (step^[t1] c) d` und „kein Halt in
    den ersten `t2` Schritten".
- **Konkrete Theoreme**:
  - `machine_0LA0LA_never_halts` — Maschine `0LA0LA` (Aufgabe B3-0005,
    `DEMO-v11-showcase.md`), Zertifikat `cyc(0, 1, −1)`: exakt der in der
    Live-Demo maschinenverifizierte Fall.
  - `machine_0RB1RB_0RA0LZ_never_halts` — Maschine `0RB1RB_0RA0LZ`
    (Aufgabe B3-0006), Zertifikat `cyc(1, 3, 2)`; der Fall `t1 = 1 > 0`
    trainiert die volle Wrapper-Form.

## Bauen und prüfen

```sh
export PATH="$HOME/.elan/bin:$PATH"
cd lean/cycle-bridge
lake build
```

Axiom-Audit (Konservativität, vgl. 03-05 §2.1): Datei mit `import CycleBridge`
und `#print axioms <Theorem>`-Zeilen anlegen und mit `lake env lean <datei>`
ausführen. Erwartet: nur die Standardaxiome `propext` und `Quot.sound`, kein
`sorryAx`. `grep -rn 'sorry\|admit' CycleBridge` muss leer sein.

## Evidenz (2026-09-12)

- `lake build` → `Build completed successfully (7 jobs)`, keine Warnungen.
- Kein `sorry`/`admit` im Quelltext.
- `#print axioms` über alle sieben Theoreme: ausschließlich
  `[propext, Quot.sound]` — keine Zusatzaxiome, kein `sorryAx`.

## Schnittstelle: [CYCLE]-Check ↔ Theorem-Hypothesen (offene Punkte)

- Der `[CYCLE]`-Check in `bemyself/claimtypes/cycle.py` vergleicht nur die
  **erreichbaren Zellen** (Lin-Fenster); der Satz hier nimmt die **volle**
  Translations-Gleichheit der Konfigurationen an. Für Läufe auf dem leeren Band
  (beide Demo-Maschinen) fallen beide Bedingungen zusammen — dort ist die Kette
  Blatt → Verdikt → formaler Beweis geschlossen.
- Offen: eine Fenster-Variante des Satzes (Abweichungen hinter der maximalen
  Kopf-Auslenkung erlaubt); dafür bräuchte das TM-Modul einen Begriff des
  erreichbaren Fensters samt Kompositionslemma.
- Offen: die Autoformalisierung Blatt → Lean-Lemma bleibt manuell; der Kernel
  prüft das Ergebnis, nicht die Treue der Übersetzung (03-05 §2.3).
- Hinweis: `cycle.py` verlangt `d ≠ 0` für Zertifikate; der formale Satz gilt
  auch für `d = 0` (reine Periodizität) und ist damit konservativ gegenüber dem
  Check.

## Struktur

```
CycleBridge/Basic.lean            Sprache: Config, shift, TM, step, Halts, Äquivarianz
CycleBridge/Cycle.lean            Satz: Iterationslemmas, cycle_never_halts, Wrapper
CycleBridge/ZeroLA0LA.lean        B3-0005: Zertifikat (0, 1, −1)
CycleBridge/ZeroRB1RB0RA0LZ.lean  B3-0006: Zertifikat (1, 3, 2)
```

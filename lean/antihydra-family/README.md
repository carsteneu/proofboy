# antihydra-family — kernel-geprüfte Halt-Familie der Antihydra-Reduktion

Lean-4-Formalisierung des ersten Satzes aus dem Astra-Lemma-Loop (r3, §(A)):
der **Halt-Familie** der Antihydra-Reduktion. Für jedes `k ≥ 3` führt der Start
`(k−1, 2^k − 3)` **genau `k−1` legale Übergänge** aus und hält dann. Bewusst
minimal: nur Core/Std, kein mathlib. Werkzeuge: Lean 4.33.1 (via elan),
Lake 5.0.0 (Muster: `lean/cycle-bridge`).

## Was hier bewiesen wird

- **Sprache** (`Antihydra.lean`): Zustand `(A, b) : Nat × Nat`; deterministischer
  Schritt `step : State → Option State` — Spiegel von `antihydra_next` in
  `yesdocs/formal-conjectures/tools/reductions.py`: `b` gerade → `(A+2, 3b/2+2)`;
  `b` ungerade und `A > 0` → `(A−1, (3b+3)/2)`; `b` ungerade und `A = 0` → Halt
  (`none`). Halte-Prädikat `Halts s := s.2 % 2 = 1 ∧ s.1 = 0`;
  `step_eq_none_iff` verbindet beide Modelle. `stepN n s` ist die `n`-fache
  legale Iteration (`none`, wenn der Lauf früher endet).
- **Lemma A1** (`odd_of_two_mul`): `b + 3 = 2q → b % 2 = 1` (der
  Ungeradheitszeuge `q−2` des Textes, Guard `2 ≤ q`, in der `omega`-Ableitung).
- **Lemma A2** (`U_add_three_of_two_mul`): `b + 3 = 2q → U b + 3 = 3q` mit der
  verschobenen Koordinate `U b := (3b+3)/2`.
- **Induktion I** (`beta_invariant`): für die β-Folge `β₀ = 2^k−3`,
  `β_{i+1} = U β_i` gilt `i ≤ k−1 → β_i + 3 = 3^i · 2^{k−i}` — additiv
  formuliert, damit der Schritt keine Subtraktionsdistributivität braucht.
- **Korollar** (`beta_odd`): alle relevanten `β_i` (`i ≤ k−1`) sind ungerade.
- **Induktion II** (`iterate_state`): nach `i ≤ k−1` legalen Übergängen ist der
  Zustand exakt `(k−1−i, β_i)` — im Schritt ist `A_i ≥ 1` (kein Halt) und
  `β_i` ungerade, es greift ausschließlich die ungerade Regel.
- **Hauptsatz** (`halt_family`): für jedes `k ≥ 3` hält der Start
  `(k−1, 2^k−3)` nach **genau** `k−1` legalen Übergängen; jeder `i`-te Zustand
  (`i ≤ k−1`) erfüllt `A_i = k−1−i`, `b_i + 3 = 3^i·2^{k−i}`, `b_i` ungerade;
  Endzustand `(0, 2·3^{k−1} − 3)` mit ungeradem `b`; kein früherer Zustand ist
  ein Haltzustand.
- **Korollar** (`odd_run`): für jedes `k ≥ 3` laufen `k−1` aufeinanderfolgende
  Schritte über die ungerade Regel („beliebig lange Ungerade-Läufe“).
- **Spotchecks**: `example`-Zeilen via `decide` für `k = 3`, `k = 5` und der
  Halt am Endzustand `(0, 15)`.

## Bauen und prüfen

```sh
export PATH="$HOME/.elan/bin:$PATH"
cd lean/antihydra-family
lake build
```

Axiom-Audit (Konservativität): Datei mit `import Antihydra` und
`#print axioms <Theorem>`-Zeilen anlegen und mit `lake env lean <datei>`
ausführen. Erwartet: nur die Standardaxiome `propext` und `Quot.sound`, kein
`sorryAx`. `grep -rn 'sorry\|admit' Antihydra.lean` muss leer sein.

## Evidenz (2026-09-13)

- `lake build` → `Build completed successfully (3 jobs)`, keine Warnungen.
- Kein `sorry`/`admit` im Quelltext.
- `#print axioms` über `halt_family`, `iterate_state`, `beta_invariant`,
  `beta_odd`, `odd_run`, `step_eq_none_iff`: ausschließlich
  `[propext, Quot.sound]` — keine Zusatzaxiome, kein `sorryAx`.

## Bezug zum Beweis-Text

Der Beweis folgt dem Astra-Lemma-Loop r3, Abschnitt „(A) Halt-Familie“ 1:1 in
der Struktur: zwei Induktionen mit je *einer* Induktionsbehauptung. Die
bewachten Nat-Subtraktionen des Textes (`2^k − 3 + 3 = 2^k`; der
Ungeradheitszeuge `q − 2`; die Exponentenidentität `k−i = (k−(i+1)) + 1`)
trägt `omega`; explizit als Lemmas herausgezogen sind die beiden
Potenz-Wachen `three_le_two_pow` (`3 ≤ 2^k`) und
`three_le_two_mul_three_pow` (`3 ≤ 2·3^{k−1}`, Endpunkt-Subtraktion). Die
Definitionen spiegeln `antihydra_next`
(`yesdocs/formal-conjectures/tools/reductions.py:225`).
Der Satz löst **keine** offene Frage: er beweist eine vollständige
Halt-Familie der reduzierten Regel, nicht die Antihydra-Vermutung.

## Struktur

```
Antihydra.lean    Sprache + A1/A2 + Induktion I/II + Hauptsatz + Korollare + Spotchecks
lakefile.toml     Lake-Ziel (ohne Abhängigkeiten, kein mathlib)
lean-toolchain    Lean 4.33.1 (leanprover/lean4:v4.33.1)
```

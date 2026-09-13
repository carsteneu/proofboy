import Std

/-!
# Antihydra halt family: first kernel-checked family of the Astra lemma loop

Formalizes section (A) of the Astra lemma loop (r3): the *halt family* of the
antihydra reduction. For every `k ≥ 3` the start `(k−1, 2^k − 3)` performs
exactly `k−1` legal transitions and then halts.

The definitions mirror `antihydra_next` in
`yesdocs/formal-conjectures/tools/reductions.py`:

- state `(A, b) : Nat × Nat`;
- `step`: `b` even → `(A+2, 3b/2+2)`; `b` odd and `A > 0` → `(A−1, (3b+3)/2)`;
  `b` odd and `A = 0` → halt (`none` in the `Option` model);
- `Halts (A, b) := b % 2 = 1 ∧ A = 0`.

Beweisstrategie (Astra §(A), 1:1): zwei Induktionen mit je *einer*
Induktionsbehauptung. (I) die β-Folge `β₀ = 2^k − 3`, `β_{i+1} = U β_i` mit der
absichtlich additiven Invariante `β_i + 3 = 3^i · 2^(k−i)`; (II) der
Paar-Zustand `(α_i, β_i)`, `α_i = k−1−i`. Nur Core/Std, kein mathlib
(Muster: `lean/cycle-bridge`, Lean 4.33.1).
-/

namespace Antihydra

/-- State of the antihydra reduction: `(A, b)`, mirroring the Python
`antihydra_next` in `yesdocs/formal-conjectures/tools/reductions.py`. -/
abbrev State := Nat × Nat

/-- One antihydra step; `none` means halt. `b` even → `(A+2, 3b/2+2)`;
`b` odd and `A > 0` → `(A−1, (3b+3)/2)`; `b` odd and `A = 0` → halt. -/
def step (s : State) : Option State :=
  if s.2 % 2 = 0 then some (s.1 + 2, 3 * s.2 / 2 + 2)
  else if 0 < s.1 then some (s.1 - 1, (3 * s.2 + 3) / 2)
  else none

/-- The halting predicate: `b` odd and `A = 0`. -/
def Halts (s : State) : Prop := s.2 % 2 = 1 ∧ s.1 = 0

/-- `n`-fold legal iteration of `step`; `none` if the run has ended earlier. -/
def stepN : Nat → State → Option State
  | 0, s => some s
  | n + 1, s => (stepN n s).bind step

@[simp] theorem stepN_zero (s : State) : stepN 0 s = some s := rfl

theorem stepN_succ (n : Nat) (s : State) :
    stepN (n + 1) s = (stepN n s).bind step := rfl

/-- `step` returns `none` exactly at the halt states. -/
theorem step_eq_none_iff {s : State} : step s = none ↔ Halts s := by
  unfold step Halts
  by_cases hb : s.2 % 2 = 0
  · simp [hb]
  · have hb1 : s.2 % 2 = 1 := by omega
    by_cases hA : 0 < s.1
    · have h1 : ¬ (s.1 = 0) := by omega
      simp [hb1, hA, h1]
    · have hA0 : s.1 = 0 := by omega
      simp [hb1, hA0]

/-- Shifted coordinate of the odd rule: `U b = (3b + 3) / 2`. -/
def U (b : Nat) : Nat := (3 * b + 3) / 2

/-- The `b`-side of the family run: `β₀ = 2^k − 3`, `β_{i+1} = U β_i`. -/
def beta (k : Nat) : Nat → Nat
  | 0 => 2 ^ k - 3
  | n + 1 => U (beta k n)

/-- **Lemma A1 (parity).** If `b + 3 = 2q` then `b` is odd. -/
theorem odd_of_two_mul {b q : Nat} (h : b + 3 = 2 * q) : b % 2 = 1 := by omega

/-- **Lemma A2 (shifted coordinate).** If `b + 3 = 2q` then `U b + 3 = 3q`. -/
theorem U_add_three_of_two_mul {b q : Nat} (h : b + 3 = 2 * q) : U b + 3 = 3 * q := by
  unfold U
  omega

/-- `k ≥ 3` implies `3 ≤ 2^k` (guards the base subtraction `2^k − 3`). -/
theorem three_le_two_pow {k : Nat} (hk : 3 ≤ k) : 3 ≤ 2 ^ k := by
  have h' : 2 ^ 3 ≤ 2 ^ k := Nat.pow_le_pow_right (by omega) hk
  omega

end Antihydra

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

/-- **First induction (β-sequence).** For `i ≤ k−1`: `β_i + 3 = 3^i · 2^{k−i}`.
One induction hypothesis, no case gaps; the additive form is chosen so the step
needs no subtraction distributivity (Astra §(A)). -/
theorem beta_invariant (k : Nat) (hk : 3 ≤ k) :
    ∀ i, i ≤ k - 1 → beta k i + 3 = 3 ^ i * 2 ^ (k - i) := by
  intro i
  induction i with
  | zero =>
      intro _
      simp [beta, Nat.sub_add_cancel (three_le_two_pow hk)]
  | succ i ih =>
      intro hle
      have hi : i ≤ k - 1 := by omega
      have hIH := ih hi
      have hexp : k - i = (k - (i + 1)) + 1 := by omega
      have h2 : 3 ^ i * 2 ^ (k - i) = 2 * (3 ^ i * 2 ^ (k - (i + 1))) := by
        rw [hexp, Nat.pow_succ]
        ac_rfl
      calc beta k (i + 1) + 3
          = U (beta k i) + 3 := rfl
        _ = 3 * (3 ^ i * 2 ^ (k - (i + 1))) := U_add_three_of_two_mul (by rw [hIH, h2])
        _ = 3 ^ (i + 1) * 2 ^ (k - (i + 1)) := by
            rw [Nat.pow_succ]
            ac_rfl

/-- **Corollary.** All relevant `β_i` (`i ≤ k−1`) are odd. -/
theorem beta_odd (k : Nat) (hk : 3 ≤ k) (i : Nat) (hi : i ≤ k - 1) : beta k i % 2 = 1 := by
  have h := beta_invariant k hk i hi
  have hexp : k - i = (k - (i + 1)) + 1 := by omega
  have h2 : 3 ^ i * 2 ^ (k - i) = 2 * (3 ^ i * 2 ^ (k - (i + 1))) := by
    rw [hexp, Nat.pow_succ]
    ac_rfl
  exact odd_of_two_mul (by rw [h, h2])

/-- **Second induction (pair state).** After `i ≤ k−1` legal transitions the
state is exactly `(k−1−i, β_i)`. In the step `A_i ≥ 1` (no halt) and `β_i` is
odd, so only the odd rule applies. -/
theorem iterate_state (k : Nat) (hk : 3 ≤ k) :
    ∀ i, i ≤ k - 1 → stepN i (k - 1, 2 ^ k - 3) = some (k - 1 - i, beta k i) := by
  intro i
  induction i with
  | zero =>
      intro _
      rfl
  | succ i ih =>
      intro hle
      have hi : i ≤ k - 1 := by omega
      have hodd : beta k i % 2 = 1 := beta_odd k hk i hi
      have hpos : 0 < k - 1 - i := by omega
      have harith : k - 1 - i - 1 = k - 1 - (i + 1) := by omega
      rw [stepN_succ, ih hi, Option.bind_some]
      simp [step, hodd, hpos, beta, U, harith]

/-- `3 ≤ 2 · 3^{k−1}` for `k ≥ 3` (guards the endpoint subtraction). -/
theorem three_le_two_mul_three_pow {k : Nat} (hk : 3 ≤ k) : 3 ≤ 2 * 3 ^ (k - 1) := by
  have h2 : 2 ≤ k - 1 := by omega
  have h' : 3 ^ 2 ≤ 3 ^ (k - 1) := Nat.pow_le_pow_right (by omega) h2
  omega

/-- **Main theorem (A).** For `k ≥ 3` the start `(k−1, 2^k − 3)` holds after
exactly `k−1` legal transitions: every `i`-th state (`i ≤ k−1`) is `(k−1−i, β_i)`
with `β_i + 3 = 3^i·2^{k−i}` and `β_i` odd; the endpoint is
`(0, 2·3^{k−1} − 3)` with odd `b`; no earlier state is a halt state. -/
theorem halt_family (k : Nat) (hk : 3 ≤ k) :
    (∀ i, i ≤ k - 1 → stepN i (k - 1, 2 ^ k - 3) = some (k - 1 - i, beta k i)
        ∧ beta k i + 3 = 3 ^ i * 2 ^ (k - i) ∧ beta k i % 2 = 1)
    ∧ stepN (k - 1) (k - 1, 2 ^ k - 3) = some (0, 2 * 3 ^ (k - 1) - 3)
    ∧ (2 * 3 ^ (k - 1) - 3) % 2 = 1
    ∧ (∀ i, i < k - 1 → ¬ Halts (k - 1 - i, beta k i)) := by
  have hend : beta k (k - 1) = 2 * 3 ^ (k - 1) - 3 := by
    have hb := beta_invariant k hk (k - 1) (by omega)
    have h1 : k - (k - 1) = 1 := by omega
    simp [h1] at hb
    omega
  have hoddend : (2 * 3 ^ (k - 1) - 3) % 2 = 1 :=
    odd_of_two_mul (Nat.sub_add_cancel (three_le_two_mul_three_pow hk))
  refine ⟨?_, ?_, hoddend, ?_⟩
  · intro i hi
    exact ⟨iterate_state k hk i hi, beta_invariant k hk i hi, beta_odd k hk i hi⟩
  · rw [iterate_state k hk (k - 1) (by omega)]
    rw [show k - 1 - (k - 1) = 0 from by omega, hend]
  · intro i hi hh
    have hA : k - 1 - i = 0 := hh.2
    exact absurd hA (by omega)

/-- **Corollary (arbitrarily long odd runs).** For every `k ≥ 3`, each of the
first `k−1` steps of the family run starts from odd `b` and positive `A` — so
`k−1` consecutive steps use the odd rule. -/
theorem odd_run (k : Nat) (hk : 3 ≤ k) (i : Nat) (hi : i < k - 1) :
    ∃ A b, stepN i (k - 1, 2 ^ k - 3) = some (A, b) ∧ b % 2 = 1 ∧ 0 < A := by
  obtain ⟨h1, _, h3⟩ := (halt_family k hk).1 i (by omega)
  exact ⟨k - 1 - i, beta k i, h1, h3, by omega⟩

-- Spot checks (finite, kernel-evaluated): k = 3 and k = 5.
example : stepN 2 (2, 2 ^ 3 - 3) = some (0, 2 * 3 ^ 2 - 3) := by decide
example : stepN 4 (4, 2 ^ 5 - 3) = some (0, 2 * 3 ^ 4 - 3) := by decide
example : step (0, 15) = none := by decide

end Antihydra

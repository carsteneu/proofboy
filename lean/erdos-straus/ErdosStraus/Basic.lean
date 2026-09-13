/-
  Erdős–Straus: kernel semantics of the witness check.

  `ok` is the witness condition `4 / n = 1 / a + 1 / b + 1 / c` (positive
  `a, b, c`) cross-multiplied into the naturals, so a kernel `decide` can
  check it; `ok_sound` lifts a passing check back to the exact identity over
  `ℚ`. This mirrors the exact rational arithmetic of the IDENT checker
  (`bemyself/claimtypes/ident.py`) and the cross-multiplication used there.

  The finite window lives in the generated certificate
  `ErdosStraus/Finite.lean` (see `tools/gen_witnesses.py`); the parametric
  classes live in `ErdosStraus/Scaling.lean`.
-/
import Mathlib

namespace ErdosStraus

/-- The Erdős–Straus statement, for orientation only: this project does
**not** prove it. `Conjecture` is the full statement; `finite_bridge`
(`ErdosStraus/Finite.lean`) proves it for a finite window and the `class_*`
theorems (`ErdosStraus/Scaling.lean`) for one progression each. -/
def Conjecture : Prop :=
  ∀ n : ℕ, 2 ≤ n → ∃ a b c : ℕ, 0 < a ∧ 0 < b ∧ 0 < c ∧ (4 : ℚ) / n = 1 / a + 1 / b + 1 / c

/-- Witness condition for `4 / n = 1 / a + 1 / b + 1 / c`, cross-multiplied
into `ℕ`: `4 * a * b * c = n * (a * b + a * c + b * c)` with positive
`a, b, c`. Decidable, so `by decide` evaluates a concrete instance in the
kernel. -/
def ok (n a b c : ℕ) : Bool :=
  decide (0 < a) && decide (0 < b) && decide (0 < c) &&
    (4 * a * b * c == n * (a * b + a * c + b * c))

/-- Soundness of `ok`: a passing kernel check yields the exact rational
identity. Positivity of `n, a, b, c` supplies the non-vanishing denominators;
the cross-multiplied natural equation is cast to `ℚ` and the denominators are
cleared. -/
theorem ok_sound {n a b c : ℕ} (hn : 0 < n) (h : ok n a b c = true) :
    0 < a ∧ 0 < b ∧ 0 < c ∧ (4 : ℚ) / n = 1 / a + 1 / b + 1 / c := by
  simp only [ok, Bool.and_eq_true, decide_eq_true_eq, beq_iff_eq] at h
  obtain ⟨⟨⟨ha, hb⟩, hc⟩, hcross⟩ := h
  refine ⟨ha, hb, hc, ?_⟩
  have hcast : (4 : ℚ) * a * b * c = n * (a * b + a * c + b * c) := by
    exact_mod_cast hcross
  have hn' : (n : ℚ) ≠ 0 := by exact_mod_cast Nat.pos_iff_ne_zero.mp hn
  have ha' : (a : ℚ) ≠ 0 := by exact_mod_cast Nat.pos_iff_ne_zero.mp ha
  have hb' : (b : ℚ) ≠ 0 := by exact_mod_cast Nat.pos_iff_ne_zero.mp hb
  have hc' : (c : ℚ) ≠ 0 := by exact_mod_cast Nat.pos_iff_ne_zero.mp hc
  field_simp
  linear_combination hcast

end ErdosStraus

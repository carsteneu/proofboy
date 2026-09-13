/-
  The parametric bridge: a witness for one fixed value scales to a whole
  progression.

  `scaling` is the reusable pattern (the formal counterpart of the scaling
  argument in `yesdocs/erdos-straus/README.md` §1); the `class_*` theorems are
  its instances for the six progressions verified by the IDENT checker
  (`[IDENT: n = m*t ; a = x*t, b = y*t, c = z*t]`, `yesdocs/erdos-straus/README.md`
  §1).

  Statement shape (same for every class): for every parameter `t ≥ 1`
  — exactly the soundness range of the IDENT checker, which requires `n ≥ 2`
  and positive denominators for every `t ≥ 1` — the identity holds over `ℚ`.
-/
import Mathlib
import ErdosStraus.Basic

namespace ErdosStraus

/-- Scaling lemma: if `x, y, z` are a witness for `m` (all positive, and
`4 * x * y * z = m * (x * y + x * z + y * z)`), then `x * t, y * t, z * t` is a
witness for every positive multiple `m * t` of `m`. -/
theorem scaling (m x y z t : ℕ)
    (hw : 4 * x * y * z = m * (x * y + x * z + y * z))
    (hm : 0 < m) (hx : 0 < x) (hy : 0 < y) (hz : 0 < z) (ht : 0 < t) :
    (4 : ℚ) / (m * t) = 1 / (x * t) + 1 / (y * t) + 1 / (z * t) := by
  have hcast : (4 : ℚ) * x * y * z = m * (x * y + x * z + y * z) := by
    exact_mod_cast hw
  have hm' : (0 : ℚ) < m := by exact_mod_cast hm
  have hx' : (0 : ℚ) < x := by exact_mod_cast hx
  have hy' : (0 : ℚ) < y := by exact_mod_cast hy
  have hz' : (0 : ℚ) < z := by exact_mod_cast hz
  have ht' : (0 : ℚ) < t := by exact_mod_cast ht
  field_simp
  linear_combination hcast

/-- `n = 2t`: the classical even case, witness `(t, 2t, 2t)`. -/
theorem class_2 (t : ℕ) (ht : 1 ≤ t) :
    (4 : ℚ) / (2 * t) = 1 / t + 1 / (2 * t) + 1 / (2 * t) := by
  simpa using scaling 2 1 2 2 t (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num) (by omega)

/-- `n = 3t`: witness `(t, 4t, 12t)`. -/
theorem class_3 (t : ℕ) (ht : 1 ≤ t) :
    (4 : ℚ) / (3 * t) = 1 / t + 1 / (4 * t) + 1 / (12 * t) := by
  simpa using scaling 3 1 4 12 t (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num) (by omega)

/-- `n = 5t`: witness `(2t, 4t, 20t)`. -/
theorem class_5 (t : ℕ) (ht : 1 ≤ t) :
    (4 : ℚ) / (5 * t) = 1 / (2 * t) + 1 / (4 * t) + 1 / (20 * t) := by
  simpa using scaling 5 2 4 20 t (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num) (by omega)

/-- `n = 7t`: witness `(3t, 6t, 14t)`. -/
theorem class_7 (t : ℕ) (ht : 1 ≤ t) :
    (4 : ℚ) / (7 * t) = 1 / (3 * t) + 1 / (6 * t) + 1 / (14 * t) := by
  simpa using scaling 7 3 6 14 t (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num) (by omega)

/-- `n = 11t`: witness `(3t, 66t, 66t)`. -/
theorem class_11 (t : ℕ) (ht : 1 ≤ t) :
    (4 : ℚ) / (11 * t) = 1 / (3 * t) + 1 / (66 * t) + 1 / (66 * t) := by
  simpa using scaling 11 3 66 66 t (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num) (by omega)

/-- `n = 13t`: witness `(4t, 26t, 52t)`. -/
theorem class_13 (t : ℕ) (ht : 1 ≤ t) :
    (4 : ℚ) / (13 * t) = 1 / (4 * t) + 1 / (26 * t) + 1 / (52 * t) := by
  simpa using scaling 13 4 26 52 t (by norm_num) (by norm_num) (by norm_num)
    (by norm_num) (by norm_num) (by omega)

end ErdosStraus

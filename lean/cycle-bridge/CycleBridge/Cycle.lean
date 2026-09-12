import CycleBridge.Basic

/-!
# Translated cycles never halt

If a deterministic two-symbol machine repeats its configuration up to a
translation after `k > 0` steps, and it does not halt within the first `k`
steps of the run, then it never halts: by determinism the machine re-runs the
same segment, shifted, forever — a *translated cycler*, the Lin recurrence of
the bbchallenge decider.

`cycle_never_halts` is the general engine; `never_halts_of_certificate` consumes
the `(t1, t2, d)` certificate form of `bemyself`'s `[CYCLE]` claim type
directly.
-/

@[simp] theorem Nat.repeat_zero {α : Type} (f : α → α) (a : α) : Nat.repeat f 0 a = a := rfl

@[simp] theorem Nat.repeat_one {α : Type} (f : α → α) (a : α) : Nat.repeat f 1 a = f a := rfl

@[simp] theorem Nat.repeat_succ {α : Type} (f : α → α) (n : Nat) (a : α) :
    Nat.repeat f (n + 1) a = f (Nat.repeat f n a) := rfl

/-- `Nat.repeat` composes: repeating `f` `m` times after `n` times is repeating
it `m + n` times. -/
theorem Nat.repeat_add {α : Type} (f : α → α) (m n : Nat) (a : α) :
    Nat.repeat f (m + n) a = Nat.repeat f m (Nat.repeat f n a) := by
  induction m with
  | zero => rw [Nat.zero_add]; rfl
  | succ m ih => rw [Nat.succ_add]; exact congrArg f ih

namespace CycleBridge

/-- The `n`-fold translation by `d`. -/
def shiftN {σ : Type} : Nat → Int → Config σ → Config σ
  | 0, _, c => c
  | n + 1, d, c => shiftN n d (shift c d)

@[simp] theorem shiftN_zero {σ : Type} (d : Int) (c : Config σ) : shiftN 0 d c = c := rfl

theorem shiftN_succ {σ : Type} (n : Nat) (d : Int) (c : Config σ) :
    shiftN (n + 1) d c = shiftN n d (shift c d) := rfl

/-- Iterated steps commute with a single translation. -/
theorem TM.iterate_shift {σ : Type} [DecidableEq σ] (M : TM σ) (d : Int) (r : Nat) :
    ∀ c : Config σ, Nat.repeat M.step r (shift c d) = shift (Nat.repeat M.step r c) d := by
  induction r with
  | zero => intro c; rfl
  | succ r ih =>
      intro c
      show M.step (Nat.repeat M.step r (shift c d)) = shift (M.step (Nat.repeat M.step r c)) d
      rw [ih c, TM.step_shift]

/-- The period block: from a translation cycle of length `k`, the run after
`k + r` steps is the translated copy of the run after `r` steps. -/
theorem TM.iterate_block {σ : Type} [DecidableEq σ] (M : TM σ) (d : Int) {k : Nat}
    {c : Config σ} (hper : Nat.repeat M.step k c = shift c d) (r : Nat) :
    Nat.repeat M.step (k + r) c = shift (Nat.repeat M.step r c) d := by
  rw [Nat.add_comm k r, Nat.repeat_add, hper, TM.iterate_shift]

/-- Decomposition of the run into blocks: after `n` periods plus `r` steps the
configuration is the `n`-fold translated copy of the configuration after `r`
steps. -/
theorem TM.iterate_decomp {σ : Type} [DecidableEq σ] (M : TM σ) (d : Int) {k : Nat}
    {c : Config σ} (hper : Nat.repeat M.step k c = shift c d) :
    ∀ n r : Nat, Nat.repeat M.step (n * k + r) c = shiftN n d (Nat.repeat M.step r c) := by
  intro n
  induction n with
  | zero =>
      intro r
      rw [Nat.zero_mul, Nat.zero_add]
      rfl
  | succ n ih =>
      intro r
      have harith : (n + 1) * k + r = n * k + (k + r) := by rw [Nat.succ_mul, Nat.add_assoc]
      rw [harith, ih (k + r), TM.iterate_block M d hper r]
      rfl

/-- Halting is invariant under an `n`-fold translation. -/
theorem TM.halts_shiftN {σ : Type} (M : TM σ) (d : Int) (n : Nat) :
    ∀ c : Config σ, M.Halts (shiftN n d c) ↔ M.Halts c := by
  induction n with
  | zero => intro c; rfl
  | succ n ih =>
      intro c
      rw [shiftN_succ, ih (shift c d), TM.halts_shift]

/-- **Translation cycle ⇒ never halts.** If the configuration after `k > 0`
steps is the initial configuration translated by `d`, and the run does not halt
within the first `k` steps, then the run never halts. -/
theorem cycle_never_halts {σ : Type} [DecidableEq σ] (M : TM σ) {k : Nat} (hk : 0 < k)
    (c : Config σ) (d : Int) (hper : Nat.repeat M.step k c = shift c d)
    (hno : ∀ j, j < k → ¬ M.Halts (Nat.repeat M.step j c)) :
    ∀ t, ¬ M.Halts (Nat.repeat M.step t c) := by
  intro t hhalt
  have hdec : t = (t / k) * k + t % k := by
    have h := Nat.div_add_mod t k
    rw [Nat.mul_comm] at h
    exact h.symm
  rw [hdec, TM.iterate_decomp M d hper (t / k) (t % k)] at hhalt
  exact hno (t % k) (Nat.mod_lt t hk) ((TM.halts_shiftN M d (t / k) _).mp hhalt)

/-- The `[CYCLE]` certificate form `(t1, t2, d)`: the configuration at step
`t2 > t1` is the configuration at step `t1` translated by `d`; if the run does
not halt within the first `t2` steps, it never halts. -/
theorem never_halts_of_certificate {σ : Type} [DecidableEq σ] (M : TM σ) (c : Config σ)
    (d : Int) {t1 t2 : Nat} (hlt : t1 < t2)
    (hper : Nat.repeat M.step t2 c = shift (Nat.repeat M.step t1 c) d)
    (hno : ∀ j, j < t2 → ¬ M.Halts (Nat.repeat M.step j c)) :
    ∀ t, ¬ M.Halts (Nat.repeat M.step t c) := by
  generalize hc' : Nat.repeat M.step t1 c = c'
  have hk : 0 < t2 - t1 := by omega
  have hper' : Nat.repeat M.step (t2 - t1) c' = shift c' d := by
    rw [← hc', ← Nat.repeat_add, Nat.sub_add_cancel (Nat.le_of_lt hlt), hper]
  have hno' : ∀ j, j < t2 - t1 → ¬ M.Halts (Nat.repeat M.step j c') := by
    intro j hj ht
    have h2 : Nat.repeat M.step j (Nat.repeat M.step t1 c) = Nat.repeat M.step (t1 + j) c := by
      rw [← Nat.repeat_add, Nat.add_comm]
    rw [← hc'] at ht
    rw [h2] at ht
    exact hno (t1 + j) (by omega) ht
  have hnever := cycle_never_halts M hk c' d hper' hno'
  intro t ht
  by_cases hle : t < t1
  · exact hno t (by omega) ht
  · have h3 : Nat.repeat M.step (t - t1) c' = Nat.repeat M.step t c := by
      rw [← hc', ← Nat.repeat_add, Nat.sub_add_cancel (Nat.le_of_not_lt hle)]
    rw [← h3] at ht
    exact hnever (t - t1) ht

end CycleBridge

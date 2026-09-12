import Std

/-!
# A generic two-symbol Turing machine and translation equivariance

This module fixes the language of the Lean bridge for `bemyself`'s `[CYCLE]`
claim type: configurations of a two-symbol machine, translation of a
configuration, the deterministic step, and the halting predicate.
-/

namespace CycleBridge

/-- Direction of the head movement. -/
inductive Dir where
  | left
  | right
  deriving DecidableEq, Repr

/-- The integer offset a head moves by. -/
def Dir.toInt : Dir → Int
  | .left => -1
  | .right => 1

/-- A configuration: control state, head position and tape (cell ↦ bit). -/
structure Config (σ : Type) where
  state : σ
  head : Int
  band : Int → Bool

/-- Translation of a configuration by `d` cells: the head moves by `d`, the
tape moves with it. `d` is signed and matches the `[CYCLE]` certificate
convention (`head₂ = head₁ + d`). -/
def shift {σ : Type} (c : Config σ) (d : Int) : Config σ where
  state := c.state
  head := c.head + d
  band := fun i => c.band (i - d)

@[simp] theorem shift_state {σ : Type} (c : Config σ) (d : Int) :
    (shift c d).state = c.state := rfl

@[simp] theorem shift_head {σ : Type} (c : Config σ) (d : Int) :
    (shift c d).head = c.head + d := rfl

@[simp] theorem shift_band {σ : Type} (c : Config σ) (d : Int) :
    (shift c d).band = fun i => c.band (i - d) := rfl

/-- Overwrite cell `i` of a tape with the bit `b`. -/
def write (band : Int → Bool) (i : Int) (b : Bool) : Int → Bool :=
  fun j => if j = i then b else band j

@[simp] theorem write_apply (band : Int → Bool) (i j : Int) (b : Bool) :
    write band i b j = if j = i then b else band j := rfl

@[simp] theorem write_self (band : Int → Bool) (i : Int) (b : Bool) :
    write band i b i = b := by
  rw [write_apply, if_pos rfl]

@[simp] theorem write_of_ne {band : Int → Bool} {i j : Int} (b : Bool) (h : j ≠ i) :
    write band i b j = band j := by
  rw [write_apply, if_neg h]

/-- Writing `false` over an all-`false` tape changes nothing. -/
theorem write_false (h : Int) :
    write (fun _ : Int => false) h false = (fun _ : Int => false) := by
  funext i
  by_cases hi : i = h <;> simp [write_apply, hi]

/-- A deterministic two-symbol Turing machine over states `σ`. `trans` is
consulted only outside the halting state. -/
structure TM (σ : Type) where
  halt : σ
  trans : σ → Bool → σ × Bool × Dir

/-- One step of the machine. A halted configuration stutters; the transition
table of the halting state is never consulted. -/
def TM.step {σ : Type} [DecidableEq σ] (M : TM σ) (c : Config σ) : Config σ :=
  if c.state = M.halt then c
  else
    let (s', b', dir) := M.trans c.state (c.band c.head)
    { state := s', head := c.head + dir.toInt, band := write c.band c.head b' }

/-- The halting predicate: the control state is the halting state. -/
def TM.Halts {σ : Type} (M : TM σ) (c : Config σ) : Prop :=
  c.state = M.halt

@[simp] theorem TM.halts_shift {σ : Type} (M : TM σ) (c : Config σ) (d : Int) :
    M.Halts (shift c d) ↔ M.Halts c := Iff.rfl

/-- Translation equivariance: translating a configuration commutes with one
step of the machine. -/
theorem TM.step_shift {σ : Type} [DecidableEq σ] (M : TM σ) (c : Config σ) (d : Int) :
    M.step (shift c d) = shift (M.step c) d := by
  unfold TM.step
  by_cases h : c.state = M.halt
  · simp [h]
  · have h' : ¬ ((shift c d).state = M.halt) := by simpa using h
    rw [if_neg h', if_neg h]
    have hT : M.trans (shift c d).state ((shift c d).band (shift c d).head)
        = M.trans c.state (c.band c.head) := by
      simp only [shift_state, shift_band, shift_head]
      rw [Int.add_sub_cancel]
    rw [hT]
    generalize htr : M.trans c.state (c.band c.head) = tr
    obtain ⟨s', b', dir⟩ := tr
    show ({ state := s', head := c.head + d + dir.toInt,
            band := write (fun i => c.band (i - d)) (c.head + d) b' } : Config σ)
        = { state := s', head := c.head + dir.toInt + d,
            band := fun i => write c.band c.head b' (i - d) }
    rw [Config.mk.injEq]
    refine ⟨rfl, ?_, ?_⟩
    · omega
    · funext i
      rw [write_apply, write_apply]
      by_cases hc : i = c.head + d
      · rw [if_pos hc, if_pos (by omega)]
      · rw [if_neg hc, if_neg (by omega)]

end CycleBridge

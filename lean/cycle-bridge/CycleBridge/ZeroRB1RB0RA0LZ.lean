import CycleBridge.Cycle

/-!
# The machine `0RB1RB_0RA0LZ` never halts (task B3-0006)

`0RB1RB_0RA0LZ`: in state `A` the head moves right and hands over to `B`; in
`B` it moves right and hands back to `A`, except that reading a `1` in `B`
overwrites it with `0`, moves left and halts. The machine of task B3-0006 in
`yesdocs/deepseek-math-notation/sets/tier_b_v11-b-0.3.json`; started in state
`A` on the empty tape, the head walks right over zeros forever, so the run
never reads a `1`.

Its `[CYCLE]` certificate is `cyc(1, 3, 2)`: the configuration after three
steps is the configuration after one step translated by two. The `t1 = 1 > 0`
is exactly the `(t1, t2, d)` shape `never_halts_of_certificate` consumes — this
machine exercises the wrapper where the showcase machine `0LA0LA` only needs
`t1 = 0`.
-/

namespace CycleBridge

namespace Machine0RB1RB0RA0LZ

/-- States of `0RB1RB_0RA0LZ`: `A` and `B` run, `Z` halts. -/
inductive State where
  | A
  | B
  | Z
  deriving DecidableEq, Repr

/-- `0RB1RB_0RA0LZ` in bbchallenge notation: `A` hands over to `B` (writing
the symbol back), `B` hands back to `A`, and halts on a `1`. -/
def machine : TM State where
  halt := .Z
  trans := fun s b => match s with
    | .A => (.B, b, .right)
    | .B => if b then (.Z, false, .left) else (.A, false, .right)
    | .Z => (.Z, b, .left)

/-- Start: state `A`, head at `0`, empty tape (as in the task). -/
def start : Config State where
  state := .A
  head := 0
  band := fun _ => false

/-- The `[CYCLE]` certificate `cyc(1, 3, 2)` on the empty tape: after three
steps the configuration is the configuration after one step translated by
two. -/
theorem step_three :
    Nat.repeat machine.step 3 start = shift (Nat.repeat machine.step 1 start) 2 := by
  show ({ state := State.B, head := ((0 + 1) + 1) + 1,
          band := write (write (write (fun _ => false) 0 false) 1 false) 2 false } : Config State)
      = { state := State.B, head := (0 + 1) + 2,
          band := fun i => write (fun _ => false) 0 false (i - 2) }
  rw [Config.mk.injEq]
  refine ⟨rfl, ?_, ?_⟩
  · omega
  · funext i
    simp only [write_false]

end Machine0RB1RB0RA0LZ

open Machine0RB1RB0RA0LZ

/-- **The machine `0RB1RB_0RA0LZ` never halts** — kernel-checked from the
`[CYCLE]` certificate `cyc(1, 3, 2)`. -/
theorem machine_0RB1RB_0RA0LZ_never_halts :
    ∀ t : Nat, ¬ machine.Halts (Nat.repeat machine.step t start) :=
  never_halts_of_certificate machine start 2 (t1 := 1) (t2 := 3)
    (by omega) step_three
    (by
      intro j hj
      have h : j = 0 ∨ j = 1 ∨ j = 2 := by omega
      rcases h with rfl | rfl | rfl
      · change ¬ (State.A = State.Z); decide
      · change ¬ (State.B = State.Z); decide
      · change ¬ (State.A = State.Z); decide)

end CycleBridge

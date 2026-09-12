import CycleBridge.Cycle

/-!
# The showcase machine `0LA0LA` never halts

`0LA0LA` in bbchallenge notation is the machine of task B3-0005 in
`yesdocs/deepseek-math-notation/sets/tier_b_v11-b-0.3.json` and of the live
demo in `DEMO-v11-showcase.md`: a single running state `A` that, on both
symbols, overwrites the cell with `0` and moves the head left. Started in state
`A` with the head at `0` on the empty tape, one step is exactly a translation
by `-1` — the `[CYCLE]` certificate `cyc(0, 1, -1)` — so the run never halts.
-/

namespace CycleBridge

namespace Machine0LA0LA

/-- States of `0LA0LA`: `A` runs, `Z` halts (no transition enters `Z`). -/
inductive State where
  | A
  | Z
  deriving DecidableEq, Repr

/-- `0LA0LA`: in state `A`, both symbols are overwritten with `0` and the head
moves left. -/
def machine : TM State where
  halt := .Z
  trans := fun s _ => match s with
    | .A => (.A, false, .left)
    | .Z => (.Z, false, .left)

/-- The demo start: state `A`, head at `0`, empty tape. -/
def start : Config State where
  state := .A
  head := 0
  band := fun _ => false

/-- The `[CYCLE]` certificate `cyc(0, 1, -1)`: one step translates the start
configuration by `-1`. -/
theorem step_start : machine.step start = shift start (-1) := by
  show ({ state := State.A, head := 0 + (-1),
          band := write (fun _ => false) 0 false } : Config State)
      = { state := State.A, head := 0 + (-1),
          band := fun i => (fun _ => false) (i - (-1)) }
  rw [Config.mk.injEq]
  refine ⟨rfl, ?_, ?_⟩
  · rfl
  · funext i
    rw [write_apply]
    by_cases hi : i = 0
    · rw [if_pos hi]
    · rw [if_neg hi]

end Machine0LA0LA

open Machine0LA0LA

/-- **The showcase machine `0LA0LA` never halts** — kernel-checked from the
`[CYCLE]` certificate `cyc(0, 1, -1)`. -/
theorem machine_0LA0LA_never_halts :
    ∀ t : Nat, ¬ machine.Halts (Nat.repeat machine.step t start) :=
  never_halts_of_certificate machine start (-1) (t1 := 0) (t2 := 1)
    (by omega) (by simpa using step_start)
    (by
      intro j hj
      have h0 : j = 0 := by omega
      subst h0
      simp [TM.Halts, machine, start])

end CycleBridge

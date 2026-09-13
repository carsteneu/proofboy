import Lean

open Lean

/-- Read the axiom list of a declaration straight from a compiled artifact.

Usage: `lean --run lean_axioms.lean <Module> <Declaration>`

The module is loaded as data at runtime (`importModules`); it is never
imported at elaboration time.  Nothing from the inspected project runs in
this process -- no tactic, no macro, no `initialize` block, no `#eval` --
so the answer on stdout cannot be produced or suppressed by repository code:
the only writer is this program.  The axiom data comes from the olean the
build produced; `leanchecker` (run separately) re-checks that artifact with
the kernel.

Exit codes: 0 answer printed, 1 declaration unknown, 2 module could not be
loaded, 3 usage. -/
def main (args : List String) : IO UInt32 := do
  match args with
  | [moduleName, constName] =>
    let imports : Array Import := #[{ module := moduleName.toName }]
    let constName := constName.toName
    try
      let env ← importModules imports {} (leakEnv := true)
      if env.find? constName |>.isNone then
        IO.println s!"BEMYSELF-LEAN-UNKNOWN {constName}"
        return 1
      let ctx : Core.Context := { fileName := "<bemyself-lean-axioms>", fileMap := default }
      let axioms ← (collectAxioms constName : CoreM (Array Name)).toIO' ctx { env := env }
      let names := axioms.toList.map (·.toString)
      IO.println s!"BEMYSELF-LEAN-AXIOMS {constName} [{String.intercalate ", " names}]"
      return 0
    catch e =>
      IO.println s!"BEMYSELF-LEAN-ERROR {e.toString}"
      return 2
  | _ =>
    IO.eprintln "usage: lean --run lean_axioms.lean <Module> <Declaration>"
    return 3

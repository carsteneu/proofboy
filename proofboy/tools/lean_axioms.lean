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

The declaration must be defined in `<Module>` itself: a name that only lives
in an imported module is reported as foreign, so a claim cannot be confirmed
with a proof that does not come from the checked file.

Exit codes: 0 answer printed, 1 declaration unknown or foreign, 2 module
could not be loaded, 3 usage. -/
def main (args : List String) : IO UInt32 := do
  match args with
  | [moduleName, constName] =>
    let imports : Array Import := #[{ module := moduleName.toName }]
    let moduleName := moduleName.toName
    let constName := constName.toName
    try
      let env ← importModules imports {} (leakEnv := true)
      match env.find? constName with
      | none =>
        IO.println s!"PROOFBOY-LEAN-UNKNOWN {constName}"
        return 1
      | some _ =>
        let foreign? : Option Name :=
          match env.header.moduleNames.findIdx? (· == moduleName),
              env.getModuleIdxFor? constName with
          | some home, some defining =>
            if home == defining.toNat then none
            else (env.header.moduleNames[defining.toNat]?).getD .anonymous
          | _, _ => none
        match foreign? with
        | some origin =>
          IO.println s!"PROOFBOY-LEAN-FOREIGN {constName} {origin}"
          return 1
        | none =>
          let ctx : Core.Context :=
            { fileName := "<proofboy-lean-axioms>", fileMap := default }
          let axioms ← (collectAxioms constName : CoreM (Array Name)).toIO' ctx { env := env }
          let names := axioms.toList.map (·.toString)
          IO.println s!"PROOFBOY-LEAN-AXIOMS {constName} [{String.intercalate ", " names}]"
          return 0
    catch e =>
      IO.println s!"PROOFBOY-LEAN-ERROR {e.toString}"
      return 2
  | _ =>
    IO.eprintln "usage: lean --run lean_axioms.lean <Module> <Declaration>"
    return 3

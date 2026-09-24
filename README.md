# proofboy

A verifier that does not believe agent reports — it re-derives every claim.

An agent reports `DONE: tests green, commit abc123, branch pushed, deploy done`. I can write that
same message myself. `proofboy` takes such a report and checks it against reality: does the commit
exist, was the branch really pushed, is the diff really the claimed one, do the tests really pass on
a clean checkout of that commit, do the cited evidence IDs exist. Each claim gets a verdict —
`confirmed`, `refuted` or `unverifiable` — with the executed command and its raw output attached.

The guiding rule: **a false confirmation is the worst possible error.** When in doubt the verdict is
`unverifiable`, never `confirmed`.

## Doctrine

- The report is hostile. The repository is hostile. Only executed checks count.
- A passing exit code is not evidence. `tests_green` requires a positive test summary in the output
  (`Ran 1364 tests`, `OK (N tests, M assertions)`); skipped/pending counters are shown in the verdict.
  A no-op `make check:` target is `unverifiable`, not `confirmed`.
- Every check runs against the pinned commit in a throwaway checkout — never against the working tree.
- Claimed commands run allowlisted, with a minimal environment (no operator secrets), and inside a
  `bwrap` sandbox when available.
- The tool only reads. YesMem scratchpad sections are opened read-only.
- A placeholder (`<hash>`, `TODO`, `…`) is a template slot: it asserts nothing.

## Requirements

- Python 3.12 — standard library only, no third-party packages
- `git`
- Optional: `bwrap` (recommended; `--sandbox require` makes it mandatory)
- For `[LEAN]` claims: a Lean toolchain, pinned via a `--tools` manifest (authority + version)

## Quick start

```bash
# check a report file against a repository
python3 -m proofboy check --report tests/data/beispiel-report.md --repo . --base <rev>

# check a YesMem scratchpad section instead of a file (read-only)
python3 -m proofboy check --section <name> --project /path/to/project

# gate: no exit code 0 while anything is unverified
python3 -m proofboy check --report done.md --repo . --strict
```

Useful flags: `--json` (machine-readable), `--profile yesloop-done` (required claim classes for a
completion report), `--detect` (stack suggestion for the repository), `--allow <prefix>`,
`--project-config <file>`, `--list-types`. The Makefile wraps the common paths: `make test`,
`make check`, `make eval`.

## Example

A real run of `make check` (this repository, trimmed):

```
deploy         UNVERIFIABLE  no checker registered for claim kind 'deploy'
commit_exists  CONFIRMED     commit 88b57aec4e581b05de015c232c159adec93f80ba resolves to 88b57aec4e581b05de015c232c159adec93f80ba
    cmd: git ... rev-parse --verify --quiet '88b57aec4e581b05de015c232c159adec93f80ba^{commit}'
    out: 88b57aec4e581b05de015c232c159adec93f80ba
branch_pushed  UNVERIFIABLE  no git remote configured; cannot verify the branch was pushed
tests_green    CONFIRMED     'python3 -m unittest discover -s tests' exited 0 as claimed; evidence: Ran 162 tests in 12.675s (sandboxed with bwrap)
    cmd: git clone --no-hardlinks <repo> <checkout> && git checkout 88b57aec... && bwrap ... -- python3 -m unittest discover -s tests

summary: CONFIRMED: 3, REFUTED: 0, UNVERIFIABLE: 3 (defect: 0, environment: 1, limit: 0, unverifiable: 2); executed: 6, not executed: 0
```

## What it checks

Structural claims, derived from the report itself:

| Trigger in the report | Claim | What is verified |
|---|---|---|
| `[COMMIT: <hash>]` | `commit_exists` | The hash resolves in the repository. Exactly one hash-shaped commit binds the dependent claims. |
| `[BRANCH: <name>]` | `branch_pushed` | The branch is really on a remote. No remote configured → `unverifiable` (environment). |
| `[MERGE: <status>]` | `merge` | The merge statement against the repository (a status token naming no branch is unverifiable). |
| `[DEPLOY: …]` | `deploy` | Nothing — deliberately no checker. Deployment stays `unverifiable`. |
| `Tests run: <cmd> → exit 0` | `tests_green` | The command in a throwaway checkout of the pinned commit, sandboxed, plus the evidence rule above. |
| `Tests run: <cmd> → exit N` | `tests_exit` | An honest failure report is checked against its own exit code (never read as "green"). |
| `Files in scope: a, b` | `diff_scope` | `git diff --name-only <base>..<commit>` against the claimed list. |
| any unknown `[MARKER: …]` | `unknown_marker` | A **defect** (exit 5) — never silently ignored. |

Marker claims, one module per kind in `proofboy/claimtypes/`:

| Trigger | Kind | What is verified |
|---|---|---|
| `[HALT: <machine> -> <steps>]`, `[SCORE: …]` | `halt` | Turing-machine simulation in-process; halting and the exact step count/score (`--halt-limit`). |
| `[SEARCHED: …]` | `search` | A bounded search against the claim (`--search-limit`). |
| `[COMPUTE: <cmd> -> <sha256>]` | `compute` | An allowlisted command runs in the checkout + sandbox; the SHA-256 of its output is compared. |
| `[CYCLE: …]` | `cycle` | Translated nondeterministic cycles (finite non-halting certificate). |
| `[IDENT: …]` | `ident` | Parameterized identities. |
| `[COLORING: …]` | `coloring` | Schur-type colorings (`--coloring-limit`). |
| `[ARTIFACT: …]` | `artifact` | Artifact/build claims; paths against `--artifact-root`. |
| `[LEAN: <file.lean> -> <theorem>]` | `lean` | Lean toolchain pinned by `--tools` manifest; compile + kernel recheck + axiom query. |
| `[LINT: <cmd>]` | `lint` | Linters bound to the commit: `php -l`, `bin/console lint:twig\|yaml\|container`, `composer validate`. Own allowlist. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | at least one `confirmed`, none `refuted` |
| 1 | at least one `refuted` (dominates) |
| 2 | error (report/repo/section/config) |
| 3 | nothing confirmed |
| 4 | `--strict`: `confirmed` plus `unverifiable` |
| 5 | defect (form violation — also without `--strict`) |
| 6 | `--strict`: a budget (`limit`) was exhausted |

## How a command claim is checked

1. **Allowlist** — only commands with an allowed prefix run (test runners vs. linters are separate
   lists; `--allow` extends them). Wrapper commands (`make`, `npm`, `composer`, …) must show the
   inner runner in their output.
2. **Throwaway checkout** — `git clone --no-hardlinks` + `git checkout <commit>` under `.yesmem/tmp`;
   verification never touches the working tree.
3. **Gatekeeper** — a runner module shadowed by the checkout → environment gap; an argument escaping
   the checkout via symlink → defect.
4. **Sandbox** — `bwrap` (`--sandbox auto|require|off`), minimal environment; network is not available
   inside the sandbox.
5. **Run** — with a time limit, process-group kill on timeout, capped output; logs under
   `.yesmem/tmp/check/`.
6. **Evidence & verdict** — exit-code comparison *plus* the required positive test summary; skip
   counters stay visible. Missing dependencies (`vendor/`, `node_modules/`) are an environment gap
   (`unverifiable`), never a defect and never a confirmation.

## Verifying YesMem scratchpad sections

`--section <name> --project <path>` reads a YesMem agent scratchpad section directly from the SQLite
database (read-only, `mode=ro`) — the natural source when agent reports are written as scratchpad
sections. `--repo` defaults to the project path. `--json` emits machine-readable output including
claim classes and the negative-space line.

## Extending

- **New claim type** — one module in `proofboy/claimtypes/` plus one registry entry. The report parser
  and the dispatcher need no change. Worked recipe: `SPEC.md` and the German manual (`README.de.md`).
- **New stack / project** — two axes:
  - *Operator flags* — `--allow <prefix>` for additional runners; `--project-config <file>` bundles
    allow/profile/sandbox/tools/tmp as JSON (CLI > config > defaults; unknown keys are an error;
    repository-side configuration is never loaded).
  - *Suggestion* — `--detect` reads manifest files (`composer.json`, `package.json`, `go.mod`, …) and
    suggests stacks, runners and linters. Detection never extends permissions and never changes a
    verdict.

## Limits (honest)

- `[DEPLOY: …]` can never be confirmed — the verifier cannot prove the outside world.
- Evidence text is repo-controlled display: a repository can print lines that downgrade a `refuted`
  to `unverifiable` — never the reverse.
- Template rule: a value containing an angle token, or literally named `TODO`, is indistinguishable
  from a placeholder and is skipped as one.
- Results depend on the host toolchain (e.g. which Node/PHP version is installed); gaps are reported
  as `environment`.
- `[HALT]`/`[SEARCHED]`/`[CYCLE]` are bounded by their budgets; an exhausted budget is a `limit`, not
  a refutation.

## Status

- Test suite: **1364 tests, green** (2026-09-24).
- Eval harness (`make eval`, 31 adversarially wrong reports): detection **31/31**, false-confirmation
  rate **0 %**.
- Python reference implementation (stdlib only). Roadmap: Go port and native YesMem integration; the
  Python version remains the reference.
- German-language project history and research wiki: `yesdocs/pruefer/`.

## Documentation

- `SPEC.md` — normative specification (German)
- `README.de.md` — full manual incl. per-claim-type details and extension recipes (German)
- `tests/data/` — example report, eval corpus, honest shims for PHP/Go runners

## License

MIT — see [LICENSE](LICENSE).

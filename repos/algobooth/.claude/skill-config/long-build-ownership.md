# Long-build ownership (harness-tracked, orchestrator-owned)

Any build or test expected to exceed a single subagent turn is **orchestrator-owned** and MUST be run
as a **harness-tracked background task** (`Bash` `run_in_background: true`) from the orchestrator
session — never backgrounded from inside a dispatched cycle subagent.

## Why
A process backgrounded from inside a subagent **dies when that subagent's turn ends** — its process
tree is torn down with the turn. A `tauri build` started this way once silently vanished, leaving no
artifact and no error. Only a process the orchestrator owns (started in the main session via
`run_in_background`) survives across subagent turn boundaries — the same property Step 1d.0 relies on
to keep `tauri dev` alive for an `/mcp-test` cycle.

## Rules
1. **Orchestrator owns long builds.** Start any build/test that may exceed a subagent turn with `Bash`
   `run_in_background: true` from the orchestrator session and drive it via the harness's task
   tracking — NOT from inside a cycle subagent.
2. **`cargo check --release` before a packaged build.** A full packaged `tauri build` takes ~20–40 min.
   Before committing to one, run `cargo check --release` first — it surfaces compile errors in a couple
   of minutes, so a 20–40 min build is never spent only to fail on a type error `cargo check` would
   have caught.
3. This is `Bash`-only process ownership; it does NOT expand the orchestrator's `Write`/`Edit` sentinel
   scope (HARD CONSTRAINT 1 still holds), exactly as Step 1d.0's `run_in_background` `tauri dev` does not.

---
name: tauri-build
description: Queue-routed AlgoBooth Tauri build (serialized through the machine-global build queue with hygiene + authoritative outcome banner). Workstation only.
argument-hint: "[pass-through args for the exec script]"
model: haiku
allowed-tools: ["Bash"]
---

# Tauri Build — Queue-Routed AlgoBooth Build

Run the AlgoBooth `tauri build` through the machine-global build queue, so it is serialized
against every other heavy build on the machine (Cognito solution builds included), gets the
`rust-tauri` hygiene profile (Job-Object process reap + cargo log-failure/no-output fidelity
checks; no .NET compiler recycle, no DLL sweep), and reports through the authoritative
last-line outcome banner.

**Windows workstation only.** Cloud sessions have no build queue (`powershell.exe` absent —
the invocation fails fast) and the cloud pipeline variants defer build work by design. This is
the v1 platform scope locked in `build-queue-generalization` (D7).

**This skill IS the queue route for the takeover contract (locked D5).** A subagent's raw
`tauri build` is denied by `long-build-ownership-guard.sh` with the
`LONG-BUILD-OWNERSHIP-TAKEOVER` signature; the orchestrator's takeover re-launch then routes
through this skill's wrapper invocation — the enforce hook's wrapper exemption allows it, so
there is no ping-pong between the two hooks. The queue contributes serialization + hygiene +
banner; the Transient Build contract (`run_transient_build` + `promote_artifact_atomically`)
still owns detachment and atomic artifact promotion.

Note: `/production-build` (the test-box installer workflow wrapping `test-production.ps1`)
remains the operator-facing "give me something to test" path; this skill is the sanctioned
queue op for pipeline/agent-driven builds.

## Instructions

1. Construct the command:
   ```
   cd <algobooth repo root> && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op tauri-build
   ```
   `-Exec` is omitted deliberately: the wrapper resolves it from this repo's ops manifest
   (`.claude/skill-config/build-queue-ops.json`, op `tauri-build`). An explicit `-Exec` would
   override the manifest entry — don't pass one unless deliberately testing an alternate script.

2. If `$ARGUMENTS` is provided, append it verbatim to the command (pass-through args reach the
   exec script unchanged).

3. A Tauri release build (Rust release + Vite + sidecar) routinely exceeds 10 minutes, so
   **default to the background + await pattern**: run the command with `run_in_background: true`.
   The `build-queue: enqueued as seq=N` line it returns is NOT an outcome — never end your turn
   or report a result on it. Follow the run to its authoritative result with the await helper
   (foreground Bash, `timeout: 600000`):
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>
   ```
   It blocks until `results/<seq>.json` exists, re-emits the authoritative
   `build-queue: seq=<N> op=tauri-build RESULT=<PASS|FAIL> (result_fidelity=...)` banner as its
   LAST stdout line, and exits with the build's exit code. On its distinct await-timeout exit
   (`124`, `result not yet present for seq=N`) the build is still running — re-run the helper or
   check `/build-queue-status`; NEVER treat a timeout as success, and do not hand-read
   `results/<seq>.json` instead. Trust the banner; do NOT `cat`/`grep` the runner script
   (`build-queue-runner.ps1`) to disambiguate an `exit_code=0`.

ETA note: the enqueue echo and waiting-position lines may carry advisory predictions (`eta-start≈` / `eta-done≈`, `?` when history is cold) computed from recent run durations. They are predictions, never outcomes — the authoritative outcome remains the final `build-queue: ... RESULT=` banner line.

4. For a build confidently under 10 minutes (warm incremental), a foreground run with
   `timeout: 600000` is fine — same banner contract. **Foreground-timeout recovery:** if a
   foreground run is killed by the Bash timeout before the banner prints, recover the seq from
   the `build-queue: enqueued as seq=N` line already in the output and run the await helper —
   do NOT re-enqueue the build.

## Recognizing a no-output false-green (`build_fidelity: no-output`)

A build can exit 0 while compiling nothing. The queue positively classifies it: an exit-0 build
op whose captured log is missing / empty / whitespace-only / near-empty is forced to
`RESULT=FAIL` with `build_fidelity: no-output` (visible via `/build-queue-status`). Trust the
banner — the corrective action is exactly what it names (clean the build output and rebuild).
The `rust-tauri` hygiene profile also scans the log for cargo failure signatures (`error[E…]`,
`error:`) so an exited-0-but-failed cargo run is overridden to FAIL
(`build_fidelity: log-failure-override`).

---
name: qg-sidecar
description: Queue-routed AlgoBooth heavy sidecar quality gate (npm run qg -- sidecar, serialized through the machine-global build queue with an authoritative outcome banner). Workstation only.
argument-hint: "[pass-through args for the exec script]"
model: haiku
allowed-tools: ["Bash"]
---

# qg-sidecar — Queue-Routed AlgoBooth Sidecar Quality Gate

Run the AlgoBooth **heavy sidecar quality gate** (`npm run qg -- sidecar` →
`bash scripts/quality-gate.sh sidecar`: sidecar type-check + test + build) through the
machine-global build queue, so it is serialized against every other heavy build on the machine
(Cognito solution builds and AlgoBooth `tauri build` included) and reports through the
authoritative last-line outcome banner.

`hygiene: none` — the sidecar gate runs npm scripts (`sidecar:type-check`/`:test`/`:build`), no
`cargo --release` and no shared Tauri release artifacts, so it needs neither the `rust-tauri`
Job-Object reap nor a compiler recycle. The queue contributes serialization + lane accounting +
the banner only.

**Windows workstation only.** Cloud sessions have no build queue (`powershell.exe` absent — the
invocation fails fast) and the cloud pipeline variants defer heavy work by design. This is the
v1 platform scope locked in `build-queue-generalization` (D7).

**Governing contract:** `~/.claude/skills/_components/runner-outcome-contract.md` — the SSOT for
the banner grammar, the followable-await 124/125 semantics, and the never-pipe-through-tail rule
this skill obeys.

## Instructions

1. Construct the command:
   ```
   cd <algobooth repo root> && powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" -Op qg-sidecar
   ```
   `-Exec` is omitted deliberately: the wrapper resolves it from this repo's ops manifest
   (`.claude/skill-config/build-queue-ops.json`, op `qg-sidecar` → `.claude/scripts/qg-sidecar-filtered.ps1`).
   An explicit `-Exec` would override the manifest entry — don't pass one unless deliberately
   testing an alternate script.

2. If `$ARGUMENTS` is provided, append it verbatim to the command (pass-through args reach the
   exec script — and thus `quality-gate.sh` — unchanged).

3. The sidecar gate can exceed 10 minutes, so **default to the background + await pattern**: run
   the command with `run_in_background: true`. The `build-queue: enqueued as seq=N` line it
   returns is NOT an outcome — never end your turn or report a result on it. Follow the run to its
   authoritative result with the await helper (foreground Bash, `timeout: 600000`):
   ```
   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>
   ```
   It blocks until `results/<seq>.json` exists, re-emits the authoritative
   `build-queue: seq=<N> op=qg-sidecar RESULT=<PASS|FAIL> ...` banner as its LAST stdout line, and
   exits with the gate's exit code. On its distinct await-timeout exit (`124`, `result not yet
   present for seq=N`) the gate is still running — re-run the helper or check
   `/build-queue-status`; NEVER treat a timeout as success. Trust the banner; do NOT `cat`/`grep`
   the runner script (`build-queue-runner.ps1`) or `results/<seq>.json` to disambiguate an
   `exit_code=0`.

4. For a run confidently under 10 minutes (fully warm), a foreground run with `timeout: 600000`
   is fine — same banner contract. **Foreground-timeout recovery:** if a foreground run is killed
   by the Bash timeout before the banner prints, recover the seq from the `build-queue: enqueued
   as seq=N` line already in the output and run the await helper — do NOT re-enqueue.

## Light siblings stay DIRECT — only rust/sidecar are queue-routed

Only the two HEAVY gates (`qg-rust`, `qg-sidecar`) are queue-routed. The LIGHT gates
(`npm run qg -- ts`, `npm run qg -- docs`) stay ORDINARY direct invocations that end in their own
authoritative `QG_VERDICT: PASS|FAIL (exit N)` line — run them directly, never pipe them through
`tail` (a pipeline masks the gate's exit under `tail`'s 0), and never queue-route them
(SPEC L2/L3). Bare `npm run qg` (all gates) is likewise NOT queue-denied — only the exact heavy
`-- rust` / `-- sidecar` forms are.

!`cat ~/.claude/skills/_components/turn-end-gate.md`

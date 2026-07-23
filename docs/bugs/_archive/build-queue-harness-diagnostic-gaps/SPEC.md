# Build-queue harness diagnostic gaps (bad exec, wrong log guidance, no status/enqueue path, phantom dead-holder lock)

**Status:** Fixed
**Fixed:** 2026-07-23
**Fix commit:** 1a5b62ed

Investigation spec for build-queue harness defects surfaced during a live `/execute-plan`
autonomous run in the Cognito Forms repo. All live in `claude-config` (the canonical config
source; `build-queue.ps1`, the runner, the await/status readers, and the build/test skills are
symlinked into repos from `user/scripts/` and `repos/cognito-forms/.claude/`). Five defects are
covered: Defects 1-3 from the original investigation, plus Defects 4-5 batched from a follow-up
report in the same session (same subsystem, one consolidated pass).

## Reconstructed route

An `/execute-plan` run hand-composed build-queue invocations rather than routing through the
`/msbuild` `/nxbuild` skills verbatim, exercising three distinct failure surfaces:

1. `build-queue.ps1 -Op msbuild -Exec "<path>/msbuild-filtered.ps1"` — a NON-EXISTENT exec
   (the real script is `build-filtered.ps1`).
2. A genuine `CS1705` GemBox assembly-version compile failure (seq 1405).
3. A foreground `nxbuild` invocation under the default 2-minute Bash timeout, plus an attempted
   `build-queue.ps1 -Status`.

## Defects and root cause

### Defect 1 (PRIMARY) — a bad `-Exec` path FAILs indistinguishably, with empty diagnostics
`Resolve-BuildQueueOp` (build-queue-hygiene.ps1) accepts an explicit `-Exec` (or a manifest
`exec`) and returns `ok=$true` WITHOUT checking the path exists. The wrapper then allocates a
seq, wins the slot, and spawns the runner with the bad exec. `powershell.exe -File <bad>` errors
("The argument … to the -File parameter does not exist") to a surface no operator inspects, the
`logs/<seq>.build.err.log` / `logs/<seq>.log` are empty, and the banner reports a generic
`RESULT=FAIL` shape-identical to a real compile failure.

**Root cause:** `script-defect` — the op-resolution seam greenlights a non-runnable exec. The
manifest already carries the authoritative `exec`, so requiring callers to re-pass `-Exec` is
also an error-prone redundancy that created the wrong-path opportunity.

**Fix scope:** validate the resolved exec exists in `Resolve-BuildQueueOp` (covers both the
manifest entry and an explicit `-Exec`); on a miss return `ok=$false` with a distinct
`exec script not found` error. Because Step 0 of the wrapper runs op resolution BEFORE any state
write, this fails fast with exit 1 and a clear message — no seq, no misleading FAIL banner.
Additionally, make the build/test skills present the `-Exec`-free invocation (manifest is
authoritative) so hand-composition cannot supply a wrong path.

### Defect 2 — FAIL guidance points at the WRONG log file for build ops
`build-queue-runner.ps1` redirects a BUILD op's grandchild stdout to `logs/<seq>.build.log` and
stderr to `logs/<seq>.build.err.log`. MSBuild writes compile errors (CS1705, "Build FAILED") to
STDOUT, so the actionable text lands in `.build.log` while `.build.err.log` is empty. Yet
`Format-BuildQueueBanner` and the skill prose direct operators to `.build.err.log` on
`RESULT=FAIL`. The symmetric error exists for TEST ops: their transcript is inherited into
`logs/<seq>.log` (the banner/skills pointed at the empty `.err.log`).

**Root cause:** `script-defect` + `ambiguous-prose` — the next-action hint keys off the stderr
sidecar rather than the stdout transcript where these tools emit diagnostics.

**Fix scope:** banner build-op hint → `logs/<seq>.build.log`; test-op hint → `logs/<seq>.log`.
Mirror the same correction in the msbuild/nxbuild (`.build.log`) and nxtest (`.log`) skill prose.

### Defect 3 — no lightweight status/enqueue-only affordance on the wrapper
A foreground `build-queue.ps1` call blocks until the build COMPLETES; a caller under the default
2-minute Bash timeout (not the skills' `timeout: 600000`) times out merely waiting in queue.
`build-queue.ps1 -Status` errors cryptically ("missing mandatory parameters: Op") because `-Op`
is mandatory and there is no status affordance on the wrapper — status lives only in the separate
`build-queue-status.ps1` / `/build-queue-status`.

**Root cause:** `script-defect` (entrypoint mishandles a natural `-Status` guess) plus a docs
gap. The enqueue-and-return story (`run_in_background:true` + `build-queue-await.ps1`) is already
documented in all four skills.

**Fix scope:** make `-Op` non-mandatory and add a `-Status` switch that delegates to
`build-queue-status.ps1`; when neither `-Op` nor `-Status` is supplied, emit an actionable error
naming both. Cross-reference the `build-queue.ps1 -Status` shortcut from the status skill.

**Implementation footgun found + fixed:** the first cut named the switch parameter `$Status`,
which — because PowerShell variable names are case-insensitive — is the SAME variable as the
pervasively-used poll-loop local `$status` (the string lock-status 'dead'/'absent'/'alive').
A `[switch]`-typed parameter applies a type constraint to that variable, so the poll loop's
`$status = Get-ActiveLockStatus` (a string assignment) threw `Cannot convert "System.String" to
"System.Management.Automation.SwitchParameter"` on EVERY non-status invocation — i.e. the switch
silently broke normal builds. Fix: keep the operator-facing `-Status` flag and rename the local
loop variable to `$lockStatus`. The pre-existing happy-path wrapper test (which exercises the
poll loop) is the regression guard: it went red on the collision and green on the rename.

### Defect 4 (HIGH) — a dead build holder wedges the read-only diagnostic tools (await hangs, status lies)
A foreground build whose wrapper is killed by the caller's short Bash timeout (SIGTERM / exit
143) can take its detached runner down with it (Windows process-tree kill), leaving
`active.lock` naming a now-DEAD `build_pid` with NO `results/<seq>.json` ever written. The
*next* build dispatch self-heals — `Test-ShouldReclaimLock` reclaims the lock on the lowest-seq
waiter after `StaleThreshold` (3) consecutive `dead` observations, regardless of lock age — so
the queue is NOT permanently wedged for new builds. But the two read-only diagnostic tools an
operator reaches for both fail on the dead holder:

- `build-queue-await.ps1 -Seq <deadSeq>` hangs to its 540s timeout (exit 124). It has stale-lock
  detection, but line ~107 EXPLICITLY excludes the awaited seq itself (`$lockSeq -eq $Seq` →
  return `$false`) — so the exact Defect-4 case (await the dead holder's OWN seq) is never
  detected, and the OTHER-seq path additionally gates on a 30-minute age.
- `build-queue-status.ps1` renders the dead holder as a normal Active Build with an
  ever-climbing `elapsed` — it never checks `build_pid` liveness.

**Root cause:** `script-defect` — the readers have no dead-holder-without-result liveness check
for the awaited/active seq. Prevention (spawning the runner truly detached so a killed waiter
cannot reap it) is a real but platform-fragile Windows problem (CREATE_BREAKAWAY_FROM_JOB /
process-group semantics vs. the Bash-tool tree-kill); a liveness self-diagnose in the readers is
the universal fix — it handles a killed waiter, a crashed runner, OOM, or a reboot identically.

**Fix scope:**
- `build-queue-await.ps1`: detect the awaited-seq-IS-the-dead-holder case. When `active.lock.seq
  == $Seq`, `build_pid` is dead, and no result exists, after a few consecutive dead observations
  (guards against a transient just-spawned pid read) break and report a DISTINCT non-124 failure
  (exit 1) that names the dead pid and the recovery (dispatch a new build to self-heal, or clear
  `active.lock`) — instead of silently polling to 124. Leave the existing OTHER-seq stale path
  intact.
- `build-queue-status.ps1`: check `build_pid` liveness on the active lock. When the holder is
  dead (and, when relevant, no result exists), render a distinct `[STALE - holder pid N dead …]`
  line instead of a climbing phantom Active Build, so the operator sees the truth at a glance.
- Both readers stay READ-ONLY (their documented contract): they DETECT and REPORT; they do not
  mutate locks/results. The actual lock reclaim remains owned by the next build's poll loop
  (already correct). A reclaim-writes-synthetic-result enhancement (so a pending await returns
  via the result file after reclaim) is noted as possible future work, not done here.

### Defect 5 — `build-queue.ps1 -Status` documented but not implemented (resolved by Defect 3)
The `build-queue-status` skill advertised `build-queue.ps1 -Status` as an equivalent shortcut,
but the live wrapper rejected it (`missing mandatory parameters: Op`). This is the same
skill/script drift Defect 3 addresses. **Resolved by the Defect-3 fix** — the real `-Status`
switch now delegates to `build-queue-status.ps1` and returns without enqueuing; skill prose and
script are back in lockstep. No additional change needed beyond Defect 3.

## Verification

- Runner stdout/stderr routing confirmed by reading `build-queue-runner.ps1` (build ops set
  `RedirectStandardOutput=<seq>.build.log` / `RedirectStandardError=<seq>.build.err.log`; test
  ops inherit the wrapper's `<seq>.log` / `<seq>.err.log`).
- `Resolve-BuildQueueOp` runs BEFORE any state write (build-queue.ps1 Step 0 comment), so
  validating there is side-effect-free.
- Existing Pester coverage (`build-queue-hygiene.Tests.ps1`) exercises both seams and is updated
  to reflect the corrected log filenames and to add exec-existence coverage.

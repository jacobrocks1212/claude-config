# Build-queue harness diagnostic gaps (bad exec, wrong log guidance, no status/enqueue path)

**Status:** Concluded

Investigation spec for three concrete build-queue harness defects surfaced during a live
`/execute-plan` autonomous run in the Cognito Forms repo. All three live in `claude-config`
(the canonical config source; `build-queue.ps1`, the runner, and the build/test skills are
symlinked into repos from `user/scripts/` and `repos/cognito-forms/.claude/`).

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

## Verification

- Runner stdout/stderr routing confirmed by reading `build-queue-runner.ps1` (build ops set
  `RedirectStandardOutput=<seq>.build.log` / `RedirectStandardError=<seq>.build.err.log`; test
  ops inherit the wrapper's `<seq>.log` / `<seq>.err.log`).
- `Resolve-BuildQueueOp` runs BEFORE any state write (build-queue.ps1 Step 0 comment), so
  validating there is side-effect-free.
- Existing Pester coverage (`build-queue-hygiene.Tests.ps1`) exercises both seams and is updated
  to reflect the corrected log filenames and to add exec-existence coverage.

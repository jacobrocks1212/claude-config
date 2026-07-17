---
title: "Build-queue wrapper spawns builds with a color-enabled env, leaking ANSI into a captured webpack artifact"
status: Concluded
priority: High
date: 2026-07-17
---

## Verified Symptom

A full-solution Cognito build routed through the machine-global build queue
(`/msbuild` → `build-queue.ps1 -Op msbuild -Exec …/build-filtered.ps1` →
`dotnet build Cognito.sln`) regenerates the frontend prod webpack artifact
`Cognito.Services/Infrastructure/Vue/serve/supported-browser-regex.txt` with raw
ANSI color escape codes embedded (`ESC[31m … ESC[39m` — red around the RegExp).
The artifact is a committed source-of-truth file, so the corruption shows up as a
spurious diff and a runtime-parse hazard (a prior Cognito commit,
`80fda06349f`, had to strip ANSI codes that were corrupting the supported-browser
regex at parse time).

## Root Cause

**Root cause class:** script-defect (the harness build wrapper).

The Cognito repo's `Cognito.Web.Client/apps/client/webpack.prod.js` runs
`pnpm exec browserslist-useragent-regexp --allowHigherVersions` via `exec` and
captures stdout into the artifact. The CLI does `console.log(<RegExp>)`; Node's
`util.inspect` colorizes RegExp values in red **when color is enabled**. Color is
enabled because the build child environment carries a truthy color signal
(`FORCE_COLOR` / TTY / pnpm-nx color propagation), and `FORCE_COLOR` is checked
**before** `NO_COLOR`, so `NO_COLOR` alone does not suppress it.

The harness is what spawns the build with that color-enabled environment. The
build process tree is:

```
build-queue.ps1  (sets no build env)
  └─ Start-Process → build-queue-runner.ps1        (detached; inherits parent env)
       └─ Start-Process → build-filtered.ps1        (inherits env)
            └─ & dotnet build Cognito.sln           (inherits env)
                 └─ MSBuild target → nx/pnpm client prod build
                      └─ webpack.prod.js → pnpm exec browserslist-useragent-regexp
                           (util.inspect colorizes RegExp → ANSI into stdout → artifact)
```

`Start-Process` inherits the spawning process's current environment block, so an
env var set anywhere at or above the wrapper propagates through the whole detached
tree to the leaf `browserslist` CLI.

**Direct repro (pre-verified):**
- `FORCE_COLOR=1` parent env → ANSI leaks into captured stdout.
- `NO_COLOR=1` alone → STILL leaks (Node checks `FORCE_COLOR` first).
- `FORCE_COLOR=0` → clean.

So the operative fix is `FORCE_COLOR=0` (with `NO_COLOR=1` as belt-and-suspenders).

## Why the harness owns this (Option B)

Two candidate fix sites:

- **Option A — Cognito repo:** pass `{ env: { …process.env, FORCE_COLOR:'0' } }` to
  the `exec` in `webpack.prod.js`. Rejected: it lands in the shared Cognito team
  repo, and the non-determinism is introduced by *the build environment the harness
  provides*, not by the product code.
- **Option B — claude-config harness (CHOSEN):** the build queue is what spawns the
  build tree with a color-enabled env; forcing a no-color env at the wrapper makes
  every build tool (including the browserslist leaf) deterministic. This also
  hardens the class generally: build output captured by the filtered exec scripts
  is re-emitted by `Write-Host -ForegroundColor`, so ANSI in captured tool output
  is never surfaced to the user — it is at best noise and at worst regex-parser
  corruption (cf. Round 8 this month, and the length-threshold ANSI bug in
  `Test-BuildProducedNoOutput`).

At the time this bug was authored the Cognito worktree carried an uncommitted
Option-A edit to `webpack.prod.js`; landing Option B supersedes it, and the Cognito
worktree is returned to a pristine (HEAD) state so the fix lives entirely in
claude-config.

## Proposed Fix Scope

Set `FORCE_COLOR=0` and `NO_COLOR=1` in the process environment of
`user/scripts/build-queue.ps1` immediately before it spawns the detached build tree
(Step 4 `Start-Process`). Scoped to the wrapper process (and its inherited children)
— **not** a machine-wide/global env var, and never touching the interactive
terminal.

Placing it at the single build-queue choke point (rather than in the Cognito-scoped
`build-filtered.ps1`) subsumes both regen paths — `/msbuild` (server build →
client prod build) and `/nxbuild -Project cognito-client` (direct client prod
build) — with one writer and no near-neighbor gap.

## Related

- `docs/specs/turn-routing-enforcement/` — hardening stage / this round.
- Round 8 (2026-07) — ANSI-in-captured-log length-threshold false-fail in
  `Test-BuildProducedNoOutput`; same family (ANSI in build output the queue
  captures).
- Cognito commit `80fda06349f` — "remove ANSI color codes corrupting
  supported-browser regex" (the downstream parse-time symptom).

---
kind: fixed
feature_id: build-queue-harness-diagnostic-gaps
date: 2026-07-23
provenance: backfilled-unverified
fix_commits: [4a7ecddd, 01dbc777, 37396be0, f77945d4]
validated_via: deferred-non-cloud
---

# Completion Receipt

Five build-queue harness diagnostic defects fixed out-of-pipeline via a manual
`/harden-harness` pass (no cycle marker). Receipt is `backfilled-unverified`:
the fix shipped through `harden(...)` commits, not the bug pipeline's gated
`__mark_fixed__` path.

## What shipped

- **Defect 1** — `Resolve-BuildQueueOp` (build-queue-hygiene.ps1) now validates
  the resolved exec exists and returns `ok=$false` with a distinct
  `exec script not found` error before any state write, so a bad `-Exec`/manifest
  path fails fast instead of allocating a seq and emitting an empty-log
  `RESULT=FAIL`.
- **Defect 2** — `Format-BuildQueueBanner` FAIL hint points at
  `logs/<seq>.build.log` for build ops and `logs/<seq>.log` for test ops, where
  MSBuild/nx actually write diagnostics.
- **Defect 3 / 5** — `build-queue.ps1` `-Op` is no longer mandatory and a
  `-Status` switch delegates to `build-queue-status.ps1` without enqueuing; the
  documented-but-unimplemented shortcut is now real. Poll-loop local renamed
  `$status` -> `$lockStatus` to avoid the case-insensitive collision with the
  `[switch]$Status` parameter.
- **Defect 4** — `build-queue-await.ps1` detects the awaited seq being the dead
  active-lock holder (dead `build_pid`, no result) after a few consecutive dead
  observations and returns a distinct exit 1 instead of polling to the 540s
  timeout; `build-queue-status.ps1` unmasks a dead-holder lock as
  `Active Build (STALE)`. Both stay read-only.

## Verification (green regression evidence)

- `build-queue.Tests.ps1` 4/4, `build-queue-hygiene.Tests.ps1` 195/195,
  `build-queue-await.Tests.ps1` 10/10 (2 new Defect-4 cases),
  `build-queue-status.Tests.ps1` 8/8 (3 new Defect-4 cases).
- Gates: `lint-skills.py --check-projected --check-capabilities` PASS,
  `pytest tests/test_lazy_core/` 1354/1354 (one Windows `os.replace` temp-file
  flake confirmed transient on isolated re-run), `lazy-state.py --test` PASS,
  `bug-state.py --test` PASS, `test_hooks.py` 295/295, `bug-state.py --fsck` clean.

`validated_via: deferred-non-cloud` — the fix is PowerShell/skill-prose/docs only
(no MCP-testable product surface); verified via the Pester suites and the harness
gate battery above.

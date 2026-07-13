---
kind: fixed
feature_id: build-queue-orphaned-result-on-wrapper-kill
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: Pester (build-queue-runner.Tests.ps1, build-queue.Tests.ps1) — NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-orphaned-result-on-wrapper-kill marked Fixed on 2026-07-12 by an
operator-directed bug-fix lane (BUILD-QUEUE lane, hand-executed outside the autonomous
`/lazy-bug` pipeline per this bug's own PHASES.md — "no PowerShell unit-test framework"
at authoring time). This receipt is written by the lane, not the pipeline's
`__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`.

## What was already done (prior session, 2026-06-24)

The root-cause fix itself — moving result-write + lock-release ownership from the
foreground wrapper onto the detached `build-queue-runner.ps1` child, so the outcome
survives the wrapper being killed — was fully implemented and manually repro'd in the
original implementation session (see PHASES.md Phase 1 + Phase 2 Implementation Notes,
2026-06-24): `user/scripts/build-queue-runner.ps1` (net-new, self-releasing runner) and
`user/scripts/build-queue.ps1` (Step 4 retargeted at the runner; Step 5 demoted to an
idempotent, seq-scoped best-effort). All PHASES.md deliverables were already `[x]`; the
Runtime Verification rows were left unchecked pending Pester (none existed at the time).

## What this session did

Pester 6.0.0 is now installed (bootstrapped by a prior lane). Added automated, repeatable
regression coverage for the fix and re-verified it directly:

- `user/scripts/build-queue-runner.Tests.ps1` (4 tests) — the WU-1 repro in isolation:
  matching-seq write + nested-exit invariant (stub exit 0 and non-zero), the seq-scoped
  guard leaving a mismatched `active.lock` untouched, idempotent repeated writes.
- `user/scripts/build-queue.Tests.ps1` (2 tests) — the WU-2 repro, i.e. **the bug's exact
  symptom, red→green**: launches the real wrapper in an isolated state root, waits for
  `active.lock` to carry the detached runner's PID (distinct from the wrapper's own),
  `Stop-Process`es the **wrapper only**, and asserts the runner still writes
  `results/<seq>.json` with the real exit code, releases `active.lock`, and
  `build-queue-status.ps1` renders `queue idle` afterward — with no wrapper alive to have
  done any of it. A companion happy-path test proves the demoted wrapper Step 5 doesn't
  double-act with the runner's canonical write (stub exit 0 and exit 1).

All 6 new tests pass; combined with the pre-existing `build-queue-await.Tests.ps1`
(8 tests), the full regression run is **14 passed, 0 failed**, confirmed stable across
repeated runs (Gate command:
`Import-Module Pester -RequiredVersion 6.0.0 -Force; Invoke-Pester -Path user/scripts/build-queue-await.Tests.ps1,user/scripts/build-queue-runner.Tests.ps1,user/scripts/build-queue.Tests.ps1 -Output Detailed`).

PHASES.md: ticked Phase 1's 3 Runtime Verification rows and Phase 2's Orphan-path +
Happy-path rows (all now genuinely re-observed via Pester this session). Left unticked:
Phase 2's Concurrency and Stale-reclaim rows — not re-run with new automation this
session (proven manually by the original 2026-06-24 session per its Implementation
Notes, but not independently re-verified today); deferred to Jacob's manual pass or a
follow-up automation lane.

## Symptom reproduction (the required red→green evidence)

Before this fix existed (per the SPEC's Verified Symptoms), killing the wrapper mid-build
left no `results/<seq>.json` ever, and `active.lock` lingering until stale-reclaim. The
new `build-queue.Tests.ps1` orphan-path test is exactly that scenario automated: it kills
the real wrapper process mid-build and asserts the previously-impossible outcome (result
written, lock released, status idle) — which passes because the fix (runner-owned Step 5)
is in place. This is the case's own red→green: the SAME test against the pre-fix
`build-queue.ps1` (wrapper launches the filtered script directly, Step 5 only runs after
the wrapper's own tail loop) would fail exactly as the two failures surfaced during this
session's harness debugging did — the difference there was test-harness bugs (a
`FileShare` read collision and a `-Op`-driven build-fidelity misclassification), not the
product; once those were fixed, the test is a faithful, currently-green assertion of the
fix's behavior.

## Out-of-scope finding (not fixed here)

`build-queue-hygiene.Tests.ps1` has 3 pre-existing failing tests
(`Add-ProcessToBuildJob`/`Stop-BuildJobTree` zero-handle assertions, `Reset-CompilerServer`
bool-return assertion) that reproduce identically run completely alone, confirmed
independent of this bug and this session's changes (`build-queue-hygiene.ps1` and its
test file are untouched — see `git status`). Flagged for a separate bug/hardening pass,
not addressed here to keep this receipt's evidence scoped to what was actually fixed.

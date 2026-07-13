---
kind: fixed
feature_id: build-queue-buildlogpath-child-scope-forces-no-output-fail
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-buildlogpath-child-scope-forces-no-output-fail marked fixed on 2026-07-12 by an
interactive bug-fix subagent Jacob directed at this bug + a sibling test-harness triage. This
receipt was written by the subagent, not the pipeline's `__mark_fixed__` gate — provenance is
deliberately operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

Root cause (child-scope discard of `$buildLogPath` inside a `Get-SafeValue { }` block in
`build-queue-runner.ps1`) was fixed in a **prior session** (2026-07-06): WU-1 RED regression guard
`27174696`, WU-2 main-scope bind `7108b2e8`. This session confirmed the fix is still intact after
the intervening `801aec12` generalization commit, authored the PHASES.md this bug's fix-plan
(`kind: fix-plan`) never required until now, and ran the closeout gates:

- `build-queue-hygiene.Tests.ps1`: 175/175 passing (incl. WU-1's guard). Found + fixed 3 UNRELATED
  pre-existing failures in the SAME file as part of the sibling triage task (a Pester
  `{ $result = Foo } | Should -Not -Throw` child-scope discard IN THE TEST FILE — same defect class
  as this bug's production root cause, distinct instance, already flagged in-file as "the 3 known
  pre-existing failures"; fixed via try/catch, no production code touched).
- Regression set green: `build-queue.Tests.ps1` (2/2), `build-queue-runner.Tests.ps1` (4/4),
  `build-queue-await.Tests.ps1` (8/8).
- `python user/scripts/lint-skills.py` clean.

**Outstanding (operator, deferred to work laptop):** the two `## Runtime Verification` rows in
PHASES.md require a live Cognito worktree + `/msbuild` on a Windows host with a real Cognito
checkout — Cognito is intentionally absent on this machine (workspace `CLAUDE.md`). Precedent for
shipping `Fixed` with an outstanding real-worktree row:
`docs/bugs/_archive/build-queue-recycle-kills-concurrent-worktree-build/FIXED.md`.

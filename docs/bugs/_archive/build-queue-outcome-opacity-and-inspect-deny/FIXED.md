---
kind: fixed
feature_id: build-queue-outcome-opacity-and-inspect-deny
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests + Pester (not pipeline-gated); 3 Runtime Verification rows deferred-to-work-laptop
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-outcome-opacity-and-inspect-deny marked fixed on 2026-07-12 during an interactive
HOOKS-lane close-out pass (Jacob directed a sweep of three named bugs; this receipt was written
by that session, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`).

## Notes

**Pre-landed (confirmed, not re-implemented this pass):** Phases 1–4 of `PHASES.md` (the
`build-queue-enforce.sh` invoke-vs-reference anchoring — item 2(b) inspect-deny — plus the
zero-match fidelity detection, inline outcome banner, and skill-doc updates — item 2(a) outcome
opacity) were found fully implemented, tested, and deliverable-ticked at HEAD. Spot-verified this
pass:
- `user/hooks/build-queue-enforce.sh` carries the anchored `_FILTERED_SCRIPT_DIRECT_RE` /
  `_FILTERED_SCRIPT_POWERSHELL_RE` / `_CMD_START`-anchored dotnet/nx denies; all 12
  `test_bqe_*`/`test_longbuild_guard_*` cases from Phase 1 are present and GREEN.
- `repos/cognito-forms/.claude/scripts/test-filtered.ps1` carries `Get-TestOutcomeExitCode`
  (exit 5 for zero-match); `user/scripts/build-queue-runner.ps1` maps exit 5 to
  `result_fidelity: "no-tests-matched"`.
- `user/scripts/build-queue-hygiene.ps1` carries `Format-BuildQueueBanner`; `build-queue.ps1`
  composes and prints it.
- All four `{msbuild,mstest,nxbuild,nxtest}/SKILL.md` files carry `RESULT=` banner-trust guidance.

**New this pass (Phase 5, follow-up):** `user/scripts/build-queue-status.ps1` never surfaced the
test-op Passed/Failed/Total counts the runner already records at `hygiene.counts` — an agent
still had to `cat results/<seq>.json` to see them, the exact inspection this bug's fix exists to
make unnecessary. Added a `counts(passed/failed/total)=` segment to the hygiene status line +
a new `user/scripts/build-queue-status.Tests.ps1` (5 cases, none existed before).

**Gates run this pass:**
- `python -m pytest user/scripts/test_hooks.py -q` → 217 passed (206 baseline + 11 new from the
  sibling `long-build-and-build-queue-matcher-bypasses` bug fixed in the same session; none of
  the 217 relate to a regression here).
- `Invoke-Pester user/scripts/build-queue-status.Tests.ps1` → 5 passed (new).
- `Invoke-Pester user/scripts/build-queue-hygiene.Tests.ps1` → 178 passed.
- `Invoke-Pester user/scripts/build-queue-runner.Tests.ps1` → 9 passed.
- `Invoke-Pester user/scripts/build-queue-await.Tests.ps1` → 8 passed.
- `Invoke-Pester user/scripts/build-queue.Tests.ps1` → 2 passed.
- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0.

**Residual (honest, not silenced):** 4 Runtime Verification checkboxes across Phases 2, 3, and 5
require a live Cognito Forms worktree + real dotnet/MSTest toolchain and are left **unticked,
marked deferred-to-work-laptop** in `PHASES.md` — they are not fabricated as passing. All
Minimum-Verifiable-Behavior gates (Pester unit coverage) for those same phases are GREEN.

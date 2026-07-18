---
kind: blocked
feature_id: build-queue-no-artifact-or-process-hygiene-on-crash
phase: "Step 7a write-plan — Phase 4 runtime spike (deliverable 1) + conditional root-cause fix (deliverable 3)"
blocked_at: 2026-07-06T04:48:14Z
retry_count: 0
blocker_kind: requires-host
recovery_suggestion: "Re-run /lazy-bug on a Windows host with a PowerShell build runtime + a real Cognito worktree to observe the ≥3-way-OR /mstest spike, then plan/land the conditional root-cause fix."
---

## Details

`/write-plan` has nothing code-authorable left to plan. All three plan parts
(`plans/fix-hygiene-part-1.md`, `-part-2.md`, `-part-3.md`) are `status: Complete`
and cover Phases 1–5. Every code-authorable deliverable in `PHASES.md` is already
`[x]` (both defensive layers of Phase 4 — the `test-filtered.ps1` zero-output guard
and the runner's `result_fidelity` classifier — landed via the sibling
`build-queue-false-green` work, verified in the 2026-07-06 execute-plan part-3
cycle; see PHASES.md Implementation Notes).

The ONLY two remaining unchecked non-verification-only deliverables (both Phase 4)
are runtime-observation-gated and cannot be satisfied on this host:

1. **Phase 4 deliverable 1 — runtime spike.** *"(Runtime spike — must be satisfied
   by observing a real run, not a static read) Run a real ≥3-way-OR `/mstest` filter
   with unfiltered `dotnet test` output captured; record whether zero tests matched
   (filter-construction bug) or tests ran but the summary format was unparsed (regex
   miss)."* By its own text this is satisfied only by OBSERVING a real run — a static
   code read is explicitly rejected.
2. **Phase 4 deliverable 3 — conditional root-cause fix.** *"(Conditional on spike
   outcome) If the spike proves a filter-construction bug, apply the minimal
   root-cause fix …; if it proves an unparsed-summary regex miss, widen the `:56`
   summary regex."* Which branch (if any) applies is decided by the spike's observed
   outcome; the fix cannot be scoped — let alone traced to a cause per the
   root-cause-trace-gate — without that observation. The defensive guard the plan
   notes "lands either way" is already `[x]`.

**Missing host capability:** a **Windows PowerShell build runtime** (`pwsh` /
`powershell.exe` + `dotnet`) and a **real Cognito worktree** to run `/mstest`
against. This repo runs in a Linux cloud container:
`command -v pwsh powershell dotnet` returns nothing, and there is no
`cognitoforms/cognito` checkout here. The spike targets the machine-global Cognito
build queue whose scripts are Windows PowerShell (`user/scripts/build-queue*.ps1`,
`repos/cognito-forms/.claude/scripts/test-filtered.ps1`).

## What was tried

- Read `PHASES.md` in full and all three `plans/*.md` parts — confirmed parts 1–3
  are `status: Complete` (phases 1–5) and every code deliverable is `[x]`.
- Enumerated remaining unchecked non-`<!-- verification-only -->` deliverables:
  exactly the two Phase 4 items above.
- Probed host capability: `command -v pwsh powershell dotnet` → empty (no Windows
  PowerShell build runtime); no Cognito worktree present.
- Concluded there is no code-authorable work for `/write-plan` to decompose — the
  remainder is Windows-runtime-observation-gated. Per the orchestrator's standing
  guidance, did NOT fabricate a plan for un-runnable work.

## Recovery Suggestion

Defer this bug to a capability-bearing host. On a **Windows machine with a
PowerShell build runtime and a real Cognito worktree**, run a real ≥3-way-OR
`/mstest` with unfiltered `dotnet test` output captured to satisfy the Phase 4
spike, record the OBSERVED mechanism in the plan notes, then plan + land the
conditional root-cause fix (deliverable 3) if the spike warrants one. The two
defensive layers are already shipped and correct regardless of the spike outcome,
so the remaining scope is narrow. The `<!-- verification-only -->` rows across
Phases 1–5 are likewise operator/runtime-owned and closed by the `__mark_fixed__`
gate on a Windows host — this BLOCKED.md defers that same host-gated tail honestly
rather than false-greening it here.

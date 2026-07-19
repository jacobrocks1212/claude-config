# Concurrent Multi-Agent Worktree Coordination — Feature Specification

> Make concurrent multi-session agent work on a SHARED worktree/branch safe and non-panicking: awareness, safe git, a FIFO file-lock, and consistent conflict handling across claude-config + AlgoBooth.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-07-18
**Friction-reduction feature:** yes

**Depends on:**

- parallel-worktree-batch-execution — hard — reuses `lazy_coord.py`'s `os.mkdir` global lock, fencing-token leases, and `owner.json` stale-holder reclamation as the FIFO file-lock substrate.
- park-provisional-acceptance — hard — the semantic-conflict halt must be added to `lazy_core.provisional_eligibility`'s fail-closed carve-out, whose concrete predicate shape this feature extends.
- generalized-build-test-runner-skills — composes — the cross-platform lock/coordination surface mirrors its runner-outcome-contract two-implementation pattern (PowerShell workstation plane + stdlib-Python cloud plane).
- build-queue-generalization — soft — borrows/shares FIFO-serializer patterns from `build-queue.ps1` (`active.lock`, seq numbers, confirmed-dead stale reclaim).
- multi-repo-concurrent-runs — soft — builds on the per-repo keyed state dir and the concurrent-run marker arbitration (`refuse_run_start_clobber`, single-slot ownership).
- long-build-and-runtime-ownership — soft — the temp-worktree merge-back path reuses the orchestrator transient-worktree/takeover contract (`run_transient_build`).

---

## Executive Summary

Multiple Claude agent sessions can operate on the SAME git worktree/branch concurrently — a live interactive `/lazy-batch` run while the operator (or a scheduled run, or a second session) commits to the same `main`. Today the harness assumes a single writer per worktree: its process-friction detector, breach/telemetry alarms, and `git add -A` cycle commits all treat a concurrent writer's activity as anomalous. On 2026-07-18 an operator's concurrent session committed 28 archive files to `main` mid-cycle, tripping a false process-friction signal and nearly firing a false breach alarm — the motivating incident.

This feature makes concurrent shared-worktree work **safe and non-panicking** in both claude-config (the harness, primary home) and AlgoBooth (consumer of the same contracts), along four axes: (1) **awareness** — every agent is told other agents may be working the same worktree/branch; (2) **git safety** — fetch+ff-before-push everywhere, bounded non-ff push retry, never force, append-only / pathspec-scoped commits instead of blanket `git add -A`; (3) a **FIFO file-lock** — agents detect write contention and coordinate through a cross-platform queue lock built on the existing `lazy_coord.py` / `build-queue.ps1` machinery, each proceeding in turn; and (4) **consistent conflict handling** — a non-halting path for write conflicts (rare-but-expected in the long run: retry/queue, log, continue), a HALT path for genuine semantic conflicts (write `NEEDS_INPUT.md`, class `product`, never provisional-auto-accepted), and a temp-worktree merge-back path for large/complex but non-semantic conflicts (orchestrator completes the work in a transient worktree, merges back, resolves, and communicates to the conflicting agent — without halting the run).

The design deliberately REUSES the concurrency plane that already exists (`lazy_coord.py` global lock + fencing leases + stale-holder reclamation; `build-queue.ps1` FIFO serializer; `lazy_core.provisional_eligibility` fail-closed carve-out; the runner-outcome two-implementation contract) rather than inventing a new locking substrate. Four design forks — lock granularity, the semantic/non-semantic discriminator, the temp-worktree merge-back lifecycle, and the cross-agent communication channel — were surfaced to the operator and are now RESOLVED to the recommended options (see `## Locked Decisions`): **per-queue-item lock grain**, a **git-mergeability + coupled-surface conflict discriminator**, **reuse of the `lazy_coord.py` lane machinery** for merge-back, and a **commit-message-trailer communication channel**.

## User Experience

The "user" here is an agent (cycle subagent, orchestrator, or a dispatched sub-subagent) and the operator watching a run. Observable behaviors:

- **Awareness in every dispatch/context.** Cycle subagents, orchestrators, and sub-subagents are told, in their prompt/context, that OTHER agents may be committing to this same worktree/branch concurrently from parallel sessions — so an unexpected commit or a moved HEAD is *expected*, not a defect to panic on.
- **Safe git by default.** Pushes fetch-and-fast-forward first and retry on a non-ff race (bounded); commits stage a scoped pathspec (the agent's own changed files), never absorbing a concurrent writer's staged work via `git add -A`.
- **Write conflict → no panic, no halt.** When two agents contend for the same artifact, the FIFO lock makes them proceed in turn (wait-for-unlock). A genuine write conflict that slips past the lock is handled consistently — retry/queue, log, continue — and never halts a `/lazy-batch` run.
- **Semantic conflict → honest halt.** When the two agents' work is logically incompatible (a true semantic conflict), the run writes `NEEDS_INPUT.md` (class `product`) and HALTS for the operator. No provisional auto-accept, even under `--park-provisional`.
- **Large non-semantic conflict → transparent merge-back.** When a conflict is large/complex but NOT semantic, the orchestrator completes the work in a temporary worktree (spun as a `lazy_coord.py` coordinator lane) and merges it back in queue order, resolving conflicts as needed. If this agent beats the conflicting agent to the merge, it COMMUNICATES to the other agent via a structured commit-message trailer (`Concurrent-Merge-Back:`) that the conflicting agent reads on the fetch/rebase it must perform to push — naming affected paths and resolution guidance. This path does not halt the run.

## Technical Design

### Reuse map (existing systems this feature builds on)

| Existing system | Location | What it provides here |
|-----------------|----------|-----------------------|
| `lazy_coord.py` concurrency plane | `user/scripts/lazy_coord.py` | `os.mkdir` global lock (atomic on NTFS), fencing-token leases (`leases.json` + `lease-token-watermarks.json` monotonic watermarks), `owner.json` stale-holder reclamation (`_confirmed_dead_owner`: pid gone OR kernel-start-time mismatch), heartbeat/expiry, `lanes.json` ledger, worktree-pool provisioning + scrub-to-clean. The FIFO file-lock's substrate. |
| `build-queue.ps1` FIFO serializer | `user/scripts/build-queue*.ps1` | Machine-global single-slot FIFO with `active.lock` + seq numbers, confirmed-dead stale reclaim (`Get-ActiveLockStatusFromText` / `Test-ShouldReclaimLock`), authoritative one-line outcome banner. The workstation-plane FIFO precedent to borrow/share. |
| `lazy_core.provisional_eligibility` | `user/scripts/lazy_core/docmodel.py:2551` | The fail-closed provisional-acceptance predicate. The semantic-conflict halt is added as a new carve-out (mirroring the existing Spike-FAIL / `stub_origin` exclusions) so it is NEVER auto-accepted under `--park-provisional`. |
| Runner-outcome two-implementation contract | `user/skills/_components/runner-outcome-contract.md` + `user/scripts/gate-battery.py` | The documented (not shared-code) grammar pattern: a PowerShell workstation implementation and a stdlib-Python cloud implementation conform independently. The cross-platform lock mirrors this (PowerShell for workstation, stdlib-Python for cloud/AlgoBooth). |
| Per-repo keyed state + run-marker arbitration | `lazy_core.claude_state_dir` / `refuse_run_start_clobber` / `marker_owner_status` | Concurrent-run detection already distinguishes same-repo/same-branch/same-pipeline walkers; this feature composes with it rather than re-deriving concurrency detection. |
| Transient-worktree takeover | `lazy_core.run_transient_build` / `long-build-ownership-guard.sh` | The orchestrator-owned transient worktree precedent the temp-worktree merge-back path reuses. |

### Requirement 1 — Awareness (injection points)

Bake a concise "other agents may be working this same worktree/branch concurrently — an unexpected commit / moved HEAD is expected, not a defect" note into: the cycle-base prompt (`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`); the orchestrator HARD CONSTRAINTS of `user/skills/lazy-batch/SKILL.md` and `user/skills/lazy-batch-parallel/SKILL.md`; the sub-subagent dispatch policy prose; the root `CLAUDE.md` / `user/CLAUDE.md` `<orchestration>` "One writer per file" block (which currently assumes single-writer and must be reconciled with sanctioned concurrent writers); and the AlgoBooth mirrors (`repos/algobooth/.claude/skills/lazy-batch-cloud`, `lazy-cloud`). Mechanical text injection — no product decision.

### Requirement 2 — Git safety

Make every git operation safe under an open shared worktree: fetch + fast-forward before every push; bounded push-retry on a non-ff rejection (never `--force`); prefer append-only / pathspec-scoped commits over blanket `git add -A` (the flush-commit-artifacts precedent) so a concurrent writer's staged files are never absorbed into this agent's commit. Wired into the cycle commit path and the runner-outcome commit chains.

### Requirement 3 — FIFO file-lock (cross-platform)

Agents DETECT write contention and coordinate via a FIFO/queue lock so each proceeds in turn, waiting on a file to unlock before proceeding. Built on the `lazy_coord.py` global-lock + fencing-lease machinery, sharing code/patterns with `build-queue.ps1`. Two conforming implementations per the runner-outcome pattern: PowerShell (workstation) and stdlib-Python (cloud/AlgoBooth). **Lock granularity is LOCKED to per-queue-item** (Locked Decision 1): one lock per feature/bug item, reusing the `lazy_coord.py` lease keying verbatim — two agents on the SAME item serialize, two agents on DIFFERENT items never block. Per-file granularity is a documented vN refinement if same-item throughput becomes a real constraint.

### Requirements 4–6 — Conflict handling (three routes)

- **Write conflict (non-halting).** Rare-but-expected in the long run; handled consistently without panic: retry/queue via the FIFO lock, log, continue. NEVER halts a `/lazy-batch` run.
- **Semantic conflict (HALT).** The two agents' work is logically incompatible → write `NEEDS_INPUT.md` (class `product`), add semantic-conflict to `provisional_eligibility`'s fail-closed carve-out (no auto-accept even under `--park-provisional`), HALT. **The semantic/non-semantic discriminator is LOCKED to the git-mergeability + coupled-surface heuristic** (Locked Decision 2): a conflict is NON-semantic when git auto-merges it (no conflict markers) OR the conflicting hunks touch disjoint logical surfaces (different files/decision-doc sections with no shared symbol); it is SEMANTIC when git reports an un-auto-resolvable conflict on the SAME logical artifact (same function, same Locked-Decision row, same sentinel). Deterministic and conservative — an ambiguous case falls to SEMANTIC/halt (the fail-safe direction).
- **Large/complex non-semantic conflict (temp-worktree merge-back).** Orchestrator completes the work in a temporary worktree, merges back, resolves conflicts. If this agent beats the conflicting agent to the merge, it COMMUNICATES to the other agent that conflicts are expected + how to resolve. Does NOT halt the run. **The merge-back lifecycle is LOCKED to reusing the `lazy_coord.py` lane machinery** (Locked Decision 3): spin the temp worktree as a coordinator lane (`lane/<item-id>` + lane marker + fencing lease), do the work there, and merge back in queue order via the existing `merge_lane_branch` (abort-and-demote on conflict, lane branch preserved, `lanes.json` audit ledger). Workstation-only for v1; the cloud/bug path is a documented follow-up. **The communication channel is LOCKED to a commit-message trailer** (Locked Decision 4): the merging agent writes a structured `Concurrent-Merge-Back:` trailer (affected paths + resolution guidance) into its commit message, which the conflicting agent reads in the incoming history it must fetch/rebase to push — zero new contended state, scoped to exactly the conflicting commits.

### Cross-repo scope

claude-config is the primary home (the harness owns the contracts); AlgoBooth consumes the same contracts. Workstation + cloud both supported via the two-implementation lock. `/spec-phases` will decompose per-repo wiring.

## Implementation Phases

(Phased breakdown drafted at `/spec-phases`; high-level: awareness injection → git-safety wiring → cross-platform FIFO lock → conflict-routing + provisional carve-out → temp-worktree merge-back + cross-agent channel → AlgoBooth mirror.)

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Concurrent commit does not trip false process-friction | Second session commits to `main` mid-cycle | `--cycle-end` friction detector does not append a `process-friction` deny-ledger entry for a sanctioned concurrent commit | `lazy_core` friction detector test |
| Push retries on non-ff instead of failing/forcing | Push races a concurrent push | Fetch+ff+retry succeeds; no `--force`; bounded attempts | git-safety unit test |
| FIFO lock serializes contending writers | Two agents claim the same lock target | Second waits for unlock, then proceeds in turn | `lazy_coord` / FIFO-lock test |
| Semantic conflict halts, never auto-accepted | Semantic conflict detected under `--park-provisional` | `NEEDS_INPUT.md` (class `product`) written; `provisional_eligibility` returns ineligible | `test` fixture on the new carve-out |
| Large non-semantic conflict merges back without halting | Large non-semantic conflict | Temp worktree created, merged back, run continues; conflicting agent notified | merge-back integration test |

## Locked Decisions

The four design forks below were surfaced to the operator via `NEEDS_INPUT.md` (a stub/pre-baseline `/spec` Phase-1 halt) and are now RESOLVED to the recommended options (operator resolution 2026-07-18):

1. **Lock granularity → per-queue-item lock.** One lock per feature/bug item, reusing the `lazy_coord.py` lease keying verbatim. Two agents on the same item serialize; two agents on different items never block. Per-file granularity is a documented vN refinement if same-item throughput becomes a real constraint.
2. **Semantic-vs-non-semantic conflict discriminator → git-mergeability + coupled-surface heuristic.** NON-semantic when git auto-merges (no conflict markers) OR the conflicting hunks touch disjoint logical surfaces; SEMANTIC when git reports an un-auto-resolvable conflict on the same logical artifact (same function / Locked-Decision row / sentinel). Deterministic; ambiguous cases fall to SEMANTIC/halt (fail-safe direction).
3. **Temp-worktree merge-back lifecycle → reuse the `lazy_coord.py` lane machinery.** Spin the temp worktree as a coordinator lane (`lane/<item-id>` + lane marker + fencing lease); merge back in queue order via `merge_lane_branch` (abort-and-demote on conflict, `lanes.json` audit ledger). Workstation-only v1; cloud/bug path documented as a follow-up.
4. **Cross-agent communication channel → commit-message trailer.** The merging agent writes a structured `Concurrent-Merge-Back:` trailer (affected paths + resolution guidance) into its commit message; the conflicting agent reads it in the incoming history it must fetch/rebase to push. Zero new contended state; scoped to exactly the conflicting commits. A documented trailer grammar is authored at `/spec-phases`.

## KPI Declaration

This is a friction-reduction feature (it eliminates false process-friction/breach alarms and prevents write-conflict-induced run halts). Baselines are `pending` at the stub stage and will be captured at `/spec` Phase 3 finalization / post-ship.

```json
{
  "id": "concurrent-worktree-false-friction",
  "system": "concurrent-worktree-agent-coordination",
  "title": "False process-friction / breach signals from sanctioned concurrent commits",
  "friction": "A concurrent session's commit to the shared branch trips a false process-friction or breach alarm mid-run.",
  "signal": {"source": "deny-ledger", "selector": "kind=process-friction reason=unexpected-commits attributable-to-concurrent-writer"},
  "unit": "events-per-run",
  "direction": "decrease",
  "baseline": {"value": null, "captured_at": null, "window": "20-runs", "provenance": "pending"},
  "band": null,
  "review_by": "2026-09-30"
}
```

```json
{
  "id": "concurrent-worktree-conflict-halts",
  "system": "concurrent-worktree-agent-coordination",
  "title": "lazy-batch run halts caused by write conflicts",
  "friction": "A write conflict panics the pipeline into an unnecessary halt instead of retry/queue/continue.",
  "signal": {"source": "halt-dwell", "selector": "terminal=blocked blocker=write-conflict"},
  "unit": "halts-per-20-runs",
  "direction": "decrease",
  "baseline": {"value": null, "captured_at": null, "window": "20-runs", "provenance": "pending"},
  "band": null,
  "review_by": "2026-09-30"
}
```

## Research References

Pre-research stub. `RESEARCH_PROMPT.md` will be authored at `/spec` Phase 2; prior art (distributed FIFO locks, git non-ff race handling, worktree merge-back protocols, cross-agent signaling) informs the four design forks.

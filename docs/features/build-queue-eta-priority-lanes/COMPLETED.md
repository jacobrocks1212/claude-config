---
kind: completed
feature_id: build-queue-eta-priority-lanes
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-eta-priority-lanes marked complete on 2026-07-09 by the interactive subagent orchestration Jacob directed
(decision round answered same day; all 4 locked decisions implemented as confirmed). This receipt
was written by the orchestrator, not the pipeline gate -- provenance is deliberately
operator-directed-interactive.

## Notes

Implemented per the locked decisions (D3 echo+waiters+status never-the-banner, D4 explicit manifest lane class, D5 two lanes over one slot with K=3 fast-pass cap, D6 no preemption): runner records op/started_at/duration_seconds on results (also fixes the awaited-banner empty-op limit from bug subagent-backgrounds-verification) + ring-capped stats/<op>.json (20, fail-open); Get-BuildQueueEta median-of-last-10-successes (<3 -> ?); enqueue echo / position lines / status view carry lane + eta-start/eta-done approximations; Test-LaneClaimEligible admission predicate with anti-livelock carve-out (fast head at cap claims when no heavy waiter exists); single-writer fast-passes.count; reclaim/lock/hygiene/occupancy/results-merge/banner byte-identical (D7). Lane assignment shipped: mstest/nxtest fast; msbuild/nxbuild/tauri-build/cargo-release heavy. VERIFIED offline: Pester 172/175 passing (same 3 pre-existing environmental fails; all 41 new tests + all wave-G tests pass); banner-carries-no-ETA pinned at output AND source level; regression suites at baseline; sandboxed end-to-end 4-cycle smoke (cold eta-done=? warming to a numeric median; real state dir proven untouched). OUTSTANDING (operator observation): live multi-waiter lane behavior (a real fast /mstest overtaking a real /msbuild), real-duration ETA quality on genuine Cognito builds, and the Phase-4 manual fault-injection row (delete stats/counter mid-queue -- self-heals by design). FOLLOW-UP (cosmetic, pre-existing at HEAD): two stray True lines in wrapper/runner stdout from unassigned Stop-BuildJobTree / Reset-CompilerServer calls.

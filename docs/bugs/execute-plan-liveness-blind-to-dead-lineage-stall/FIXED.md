---
kind: fixed
feature_id: execute-plan-liveness-blind-to-dead-lineage-stall
date: 2026-07-20
provenance: backfilled-unverified
validated_via: pytest user/scripts/ -q (full script suite green, 2684/2684 — incl. test_execute_plan_liveness with 4 new wedge-candidate/env-override/fresh-marker regression tests); test_hooks.py 286/286; generate-coupled-skills.py --check byte-identical; skill-size-ratchet.py --check OK; harness-gate.py overfit+gate_weakening pass; NOT pipeline-gated (fixed OUT-OF-PIPELINE via a harden commit)
auto_ticked_rows: 0
---

# Completion Receipt

`execute-plan-liveness-blind-to-dead-lineage-stall` fixed OUT-OF-PIPELINE by
`/harden-harness` Round 129 (2026-07-20). Fix commit: `3f2294a5`
(`harden(script): add marker-staleness wedge-candidate to execute-plan-liveness`).
Bug spec commit: `fa75b72e`. This receipt was written by the dispatched harden
subagent, not the bug pipeline's `__mark_fixed__` gate — provenance is
`backfilled-unverified`.

## Notes

The Step 1e.4a pause-vs-terminal discriminator (`lazy_core.execute_plan_liveness`)
returned `verdict: paused` whenever the execute-plan marker was present and the plan
was not `Complete`, with no liveness/staleness dimension — so a live backgrounded
pause and a DEAD-lineage wedge were indistinguishable, and a wedged/dead lineage
(marker ~3.6h stale, plan `In-progress`) was mis-verdicted `paused`, suppressing
recovery forever until the operator intervened (inspector-track-dashboard part-2).

Fix: added a marker-mtime staleness bound (`_EXECUTE_PLAN_MARKER_WEDGE_SECONDS`,
default 1800s, env-overridable via `LAZY_EXECUTE_PLAN_MARKER_WEDGE_SECS`). A present
marker + non-Complete plan + stale mtime now returns the reserved `wedge-candidate`
verdict; the orchestrator (SKILL Step 1e.4a, canonical + coupled `lazy-bug-batch`)
routes it to the genuine-wedge fallback (a `TaskList` lineage probe) — DEAD ⇒ route
recovery, LIVE ⇒ keep waiting. Additive + fail-safe (any mtime-read error preserves
legacy `paused`); `wedge-candidate` never tears down the marker (decision #12 stays
parked), so a false-positive on a legit long run is safe.

## Verification

`pytest user/scripts/ -q` green (2684/2684). New regression tests in
`test_execute_plan_liveness.py`: a 3h-stale marker + non-Complete plan →
`wedge-candidate`; a stale-but-Complete marker → `terminal`; the
`LAZY_EXECUTE_PLAN_MARKER_WEDGE_SECS` env override drives a moments-old marker to
`wedge-candidate`; a fresh marker + non-Complete plan stays `paused` (additive
contract). `generate-coupled-skills.py --check` byte-identical; `harness-gate.py`
`overfit: pass`, `gate_weakening: pass`.

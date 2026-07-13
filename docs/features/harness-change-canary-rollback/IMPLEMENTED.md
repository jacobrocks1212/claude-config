---
kind: implemented
feature_id: harness-change-canary-rollback
date: 2026-07-12
provenance: operator-directed-interactive
derivation: message-grep
commits: [2a4117f5, 35ffa592, fbfe0ddd, 0196c976, 0dc0ba5c, 9ce919c5, 3335ea39, 9818a16f,
  dfaf1e5c, c5afe1a2, a250322d, 68cd2040, 9126dad1, 305a3404, b5015cf8, b3bc2410, acf2a45c,
  fa301f87, 1b41be54]
decisions: [D1, D2, D3, D4, D5, D6, D7]
---

# Implementation Ledger

**What shipped:** A canary observation window for shipped control-surface changes, built almost
entirely on `intervention-efficacy-tracking`'s existing machinery. At capture time
(`lazy_core.record_intervention`), a `canary:` sub-map is written onto the intervention record
whenever the shipped change's touched-file set (derived from the `code-doc-provenance-linkage`
commit-bracket mapping) intersects a control-surface manifest (`_canary_control_surfaces` — a
fallback glob constant, since `anti-overfit-design-gate`'s `docs/gate/control-surfaces.json` has
not shipped); the sub-map carries the window config, matched surfaces, commit set, a computed
coupled-pair scope (`_compute_pair_scope` over `lazy-parity-manifest.json` + the CLAUDE.md pairs
table), and a degraded-revert note. A `--canary` mode in `user/scripts/efficacy-eval.py` runs at
every end-of-run flush while any record has `canary.status: open`: it accrues the run-denominated
window (10 runs / 30-day ceiling), applies the D2 tripwire (KPI band regression, else 25%
relative with 3+ post-ship occurrences, OR 2+ attributable fresh incidents), and applies D3
surface-based attribution (unknown-surface incidents never attribute; a shared surface trips all
matching open canaries). On a trip it flags-and-enqueues (never auto-reverts, D4) an
evidence-bearing `canary-revert-<id>` bug stub via the existing `bug-state.py --enqueue-adhoc`
path, with a watcher-written `EVIDENCE.md` carrying the trip reason, commit set, pair scope, and
degraded-revert note — once ever per canary. On window maturity with no trip, the record stamps
`closed-clean` (or `closed-clean (no-data)`) and gains a `## Canary <date>` section; the efficacy
review proceeds unaffected (a clean canary never pre-judges it, a tripped one never skips it).
The system's own KPI (`canary-trip-precision`) is registered in `docs/kpi/registry.json` and
`kpi-scorecard.py`, honestly `provenance: pending` until the canary has tripped. All four phases
(registration + revertibility metadata; watcher windows/attribution/tripwire; flag-and-enqueue
consequences + end-of-run flush wiring across the coupled orchestrator skills; steady-state
handoff + retro citation + KPI) landed across prior cloud `/execute-plan` sessions per HANDOFF.md
and the PHASES.md Implementation Notes; this session verified every phase's fixture suite and
gate green on the workstation, confirmed the KPI Declaration lints clean, granted the structural
`SKIP_MCP_TEST.md` deferred by the cloud run, and flipped Status to Complete.

**Decisions that drove it:** D1 (canary state is a sub-map on the existing intervention record,
armed by the shared control-surface manifest — not a second registry file) · D2 (run-denominated
window: 10 runs / 30-day ceiling; tripwire = KPI band regression else 25% relative with ≥3
post-ship occurrences, OR ≥2 attributable fresh incidents — operator-approved 2026-07-04) · D3
(surface-based incident attribution; unknown surfaces never attribute; shared surfaces trip all
matching canaries — operator-approved 2026-07-04) · D4 (no change class ever earns true
auto-revert in v1 — flag-and-enqueue always, a standing operator-owned policy, operator-approved
2026-07-04) · D5 (the revert item is an evidence-bearing bug stub via the existing enqueue path,
carrying commit set + coupled-pair scope so a revert is mechanical, not archaeology) · D6 (the
watcher is a `--canary` mode of the efficacy evaluator, invoked at every end-of-run flush while
any window is open — not a standalone script) · D7 (window close is a status stamp + record
section, not a second artifact; the efficacy review's own cadence is untouched).

**Receipt: COMPLETED.md (provenance: operator-directed-interactive).**

---
kind: needs-input
feature_id: canary-revert-harden-2026-07-r54
written_by: spec-bug
decisions:
  - Disposition of the harden-2026-07-r54 canary trip — revert, redesign, or close-as-noise
class: product
divergence: structural
stub_origin: true
next_skill: plan-bug
date: 2026-07-19
---

## Decision Context

### 1. Disposition of the harden-2026-07-r54 canary trip — revert, redesign, or close-as-noise

**Problem:** The harness-change **canary** (a per-run automatic watcher over shipped
control-surface changes; part of `harness-change-canary-rollback`) tripped for intervention
`harden-2026-07-r54`. That intervention is commit `1af48e1d` — *"route dispatch-bound probe +
inject hook by merged head, not sticky pipeline"* — which fixed a real bug where two P0 bugs were
skipped for a lower-priority feature. The canary flags-and-enqueues only; **nothing was reverted
automatically** (design decision D4). This bug is the human triage the design intends: pick
**revert**, **redesign**, or **close-as-noise**.

The trip reason is a **band-only** movement: the targeted friction signal `event:gate-refusal`
(the count of pipeline gate refusals per run) rose **+59.6%** vs a frozen baseline of 4.7
events/run (band is ±25%), with **zero** freshly-attributed incidents. Critically, the
investigation **traced** that commit `1af48e1d` is **not on the serving path of
`event:gate-refusal`**: its added code only sets a route-override telemetry field
(`route_overridden_by=merged-head-diverged`) and never emits a `gate-refusal` event (the actual
emit sites are the completion/coverage gate seams the commit does not touch —
`lazy-state.py:13176.. / bug-state.py:9026..`). So the band moved for reasons unattributable to
this change (co-shipped hardening rounds firing gate-refusal sub-signals against the same undivided
target, which the intervention machinery confounds by design). See `SPEC.md` §"Proven Findings".
This is a stub-origin baseline the operator has never reviewed, and the options diverge in shipped
behavior (a revert removes a correct fix), so it parks for you rather than auto-accepting.

**Options:**
- **Close-as-noise (Recommended)** — Keep commit `1af48e1d` as-is; record the trip as a false
  positive and let it feed canary-band / sub-signal tuning. Rationale: the change is a correct fix
  and is provably off the tripped signal's serving path, so a revert would remove working behavior
  to chase a signal the change does not produce. Cost: near-zero (no code revert); a small
  follow-up may split the `event:gate-refusal` target into a sub-signal to stop the confound
  (out of this bug's scope — a canary-tuning spin-off). Reversibility: full — the commit stays and
  can still be revisited if the efficacy verdict (~20-run window) later shows it ineffective (a
  distinct, non-canary question). Downside: leaves the canary bands slightly loose until tuned;
  the trip counts against the `canary-trip-precision` KPI as an imprecise trip (which is the honest
  record).
- **Revert** — `git revert 1af48e1d` (plain, revert-safe; `pair_scope` empty, no coupled sibling,
  a green `lazy_parity_audit.py` is not needed since no parity pair is touched). Cost: low
  mechanically, but **removes a correctness fix** — the merged-head route override that stopped two
  P0 bugs from being skipped mid-feature-run. Risk: reintroduces that P0-skip regression. Only
  choose this if you judge the merged-head change independently undesirable — the canary evidence
  does **not** support it (the change is off the tripped signal's path).
- **Redesign** — Re-architect the merged-head route override. Cost: high; forks the approach.
  **No design defect was found** — the change works correctly and is off the tripped signal — so
  there is nothing the evidence points at to redesign. Listed only for completeness of the canary
  triage menu.

**Recommendation:** Close-as-noise — the traced finding shows the change is correct and not on the
`event:gate-refusal` serving path, so the trip is a band-only confound; keep the fix and tune the
canary signal rather than revert working behavior.

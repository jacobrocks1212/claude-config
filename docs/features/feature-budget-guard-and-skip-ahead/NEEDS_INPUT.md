---
kind: needs-input
feature_id: feature-budget-guard-and-skip-ahead
written_by: spec
class: product
decisions:
  - Per-feature budget trip signal — what metric trips the guard
  - On-trip action — what happens to a feature that exceeds its per-feature budget
  - Skip-ahead default — make dependency-aware skip-ahead default-on or keep it opt-in
date: 2026-06-19
next_skill: spec
---

# /spec --batch — Needs Input

## Decision Context

The baseline SPEC.md for Feature Budget Guard + Skip-Ahead is drafted. The mechanical design (per-feature counter on the run marker, run-scoped defer-to-tail mechanism, dependency-aware readiness predicate reusing the `**Depends on:**` block) is locked in from the existing state-machine infrastructure. Three decisions remain that change what the operator actually sees the run do — they are product-behavior calls, deferred to the operator rather than auto-accepted.

### 1. Per-feature budget trip signal — what metric trips the guard

**Problem:** The guard needs a per-feature signal to decide a feature is monopolizing the budget. The friction incidents show three distinct failure shapes: pure cycle burn (`d8-live-looping` consumed the entire 20→32 budget), repeated validation failures (~5 MCP-validation blocks in the same incident), and corrective-phase churn (`d7-wavetable` looped ~20 cycles producing 6 contradictory corrective phases). The signal chosen determines *when and why* the guard fires, which the operator sees in the run log and notifications.

**Options:**
- **Forward-cycles consumed (single signal)** — trip when one feature's per-feature forward-cycle count crosses a ceiling (e.g. N forward cycles). Simplest, fully deterministic, reuses the existing forward-advance plumbing directly, and is the most legible signal for an operator ("feature X took 8 cycles, deferred"). Cons: a feature making slow-but-real progress could trip on raw cycle count even when it's not actually stuck.
- **MCP-validation-block count** — trip on the number of validation-escalation / MCP-validation blocks a feature accrues. Targets the specific "keeps failing validation" shape. Cons: narrower — misses the pure-cycle-burn and corrective-phase-churn shapes; requires counting a sentinel signal that's less uniformly present than cycle count.
- **Composite (cycles + validation-blocks + corrective-phase-count, any-crosses-threshold)** — trip when any of the three signals crosses its own sub-threshold. Catches all three observed failure shapes. Cons: most complex to tune and explain; three thresholds to pick defaults for; harder to make the operator-facing notification crisp ("which signal tripped?").

**Recommendation:** Forward-cycles consumed (single signal) — it is the most deterministic and legible signal, reuses existing counter plumbing with zero new oracle, and directly addresses the canonical monopoly incident (`d8-live-looping` was pure cycle burn). The composite can be layered on later if a single signal proves insufficient; starting single-signal keeps the default behavior predictable and the notification crisp.

### 2. On-trip action — what happens to a feature that exceeds its per-feature budget

**Problem:** When the guard trips on a feature, the orchestrator must do something with that feature. The choice changes what the operator observes happen to a stubborn feature and how much of the run's remaining budget the rest of the queue gets.

**Options:**
- **Defer to back of queue (run-scoped reorder)** — move the tripped feature to the tail of the live queue; its on-disk progress is untouched and it resumes when re-reached. The run advances to the next ready item. A second trip on the same feature in the same run escalates (force-stop or surface). Lets the rest of the queue make progress while preserving the hard feature's partial work; the operator sees "deferred to tail, advancing to <next>". Cons: a genuinely-broken feature gets a second bite before it's force-stopped, costing a few extra cycles.
- **Force-stop the feature** — mark the feature blocked/skipped for the rest of the run (write a sentinel), notify, and advance. Most aggressive budget protection — a stubborn feature gets exactly one budget's worth and no more. Cons: a feature that was *close* to done loses its remaining shot this run; less forgiving of slow-but-real progress.
- **Escalate to `/investigate`** — on trip, dispatch the existing `/investigate` gate to root-cause why the feature is churning before deciding. Aligns with the existing investigation-first machinery for `validation_escalation`. Cons: investigation itself costs cycles (counts against the run); if the feature is just *large* rather than *broken*, investigation is wasted effort.
- **AskUserQuestion** — surface the trip to the operator and let them choose per-incident (defer / force-stop / investigate / extend budget). Maximum operator control. Cons: blocks an unattended run; adds an interactive halt to a pipeline whose value is autonomy.

**Recommendation:** Defer to back of queue (run-scoped reorder) with bounded re-trip escalation — it directly solves the monopoly problem (the rest of the queue advances) while preserving the hard feature's partial progress, keeps the run autonomous (no interactive halt), and bounds the cost (one deferral, then escalation on a second trip). This composes cleanly with the existing `--park-*` skip-list pattern.

### 3. Skip-ahead default — make dependency-aware skip-ahead default-on or keep it opt-in

**Problem:** When the queue head is research-gated (or BLOCKED), the current strict default halts the whole run, stranding independent downstream-safe work behind it (session `18e1d3d7`: 59 independent front-loaded features + poly-mod stranded behind one research-gated head). The new dependency-aware skip-ahead advances only onto items with no `hard` dependency on the gated head. The question is whether this becomes the default run behavior or stays an opt-in flag generalizing the existing `--allow-research-skip`.

**Options:**
- **Default-on (dependency-aware skip-ahead is the new default)** — when the head is gated, the run automatically advances to independent ready items; it only halts/surfaces when every remaining item is gated or genuinely downstream of a gated item. The dependency-awareness is the safety rail that makes default-on safe (unlike the current all-or-nothing `--allow-research-skip`, which is opt-in *because* it's unsafe on an ordered queue). Matches the desired outcome in the stub ("the orchestrator can skip ahead instead of stranding the whole queue"). Cons: a run no longer halts on the first gated head by default — an operator who *wanted* the strict halt must now opt out; a mis-declared dep block could let work leak onto an item that's actually downstream.
- **Opt-in (keep it a flag, generalizing `--allow-research-skip`)** — strict halt-on-first-gated-head stays the default; the dependency-aware skip is enabled via a flag. Most conservative — preserves today's default behavior exactly; the operator explicitly opts into skip-ahead when they've judged it safe. Cons: the stranding friction (the motivating incident) persists by default; the operator has to remember the flag to get the benefit.

**Recommendation:** Default-on — the dependency-aware `hard`-dep predicate is precisely the safety rail that the current opt-in-only `--allow-research-skip` lacks, so default-on is safe in a way the legacy flag never was, and it directly resolves the motivating stranding incident without requiring the operator to remember a flag. A `--strict-research-halt` opt-out can preserve the legacy behavior for operators who want it. (This is the one decision most likely to warrant operator override, since it changes the default run behavior on every gated queue — hence surfacing it rather than auto-accepting.)

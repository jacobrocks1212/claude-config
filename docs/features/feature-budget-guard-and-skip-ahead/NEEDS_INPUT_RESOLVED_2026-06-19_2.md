---
kind: needs-input
feature_id: feature-budget-guard-and-skip-ahead
written_by: spec
class: product
decisions:
  - Default per-feature ceiling — static integer vs. dynamic fair-share formula
  - Skip-ahead readiness predicate — hard-dep-absence alone vs. add a shared-state isolation rail
date: 2026-06-19
next_skill: spec
---

# /spec --batch — Needs Input (Phase 3 research integration)

## Decision Context

The Gemini deep research (`RESEARCH.md`, summarized in `RESEARCH_SUMMARY.md`) **confirms the three operator-locked decisions** (trip on forward-cycles, defer-to-tail, default-on skip-ahead) as directionally correct, but raises two refinements that change observable run behavior and that the operator should confirm before SPEC.md is finalized. One of them (Decision 2) directly challenges a claim in the existing `## Locked Decisions` block, so it cannot be auto-accepted.

(A third research finding — the exact bounded re-trip escalation ladder — was taken in-cycle under the completeness-first policy because the locked on-trip decision already constrained it to an autonomous, non-interactive shape. See the cycle's `⚖ policy` disclosure. It is NOT surfaced here.)

### 1. Default per-feature ceiling — static integer vs. dynamic fair-share formula

**Problem:** The guard trips when one feature's per-feature forward-cycle count crosses a *ceiling*. The trip *signal* is already locked (forward-cycles). What is still open — an explicit Open Question in the SPEC ("Default per-feature ceiling value") — is **how the default ceiling is computed**, and this default is something the operator sees the run act on (it determines *when* a feature gets deferred). Research flags a hard tradeoff: a **static** ceiling cannot adapt to run size or queue depth. With a 20–32 cycle global budget and a 5–15 feature queue, a static ceiling of e.g. 10 lets two heavy features eat the whole budget while 13 one-cycle features starve; a static ceiling of e.g. 4 prematurely trips a legitimately-large feature on every run. Mature fair-share schedulers (Slurm, CrewAI) compute the per-task cap dynamically from the remaining global budget and queue depth instead.

**Options:**
- **Dynamic fair-share formula (Recommended)** — compute the ceiling at run start (or when the feature reaches the queue head) as `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`, where `C_global` is the run's `max_cycles` and `Q_depth` is the count of ready queue features. This mathematically guarantees no single feature consumes >40% of the run budget while preserving a 6-cycle minimum execution floor (so small runs/queues still let a feature finish). Reuses counters the state machine already has (`max_cycles`, queue length). Cost: slightly more logic than a constant; the operator-facing notification must report the *computed* ceiling, not a fixed number. A flag can still override the result. This is the research-recommended default and directly mitigates the single-signal false-trip risk the research flagged.
- **Static integer default (e.g. 8) with flag override** — ship a fixed default ceiling (e.g. `--per-feature-cycle-cap 8`, default 8) that applies regardless of run/queue size. Simplest to implement and explain; the operator sees one number. Cost: research-documented false trips on large features in deep queues and under-protection in shallow ones; the operator must hand-tune the flag per run to get good behavior — exactly the manual intervention the dynamic formula removes.

**Recommendation:** Dynamic fair-share formula — it adapts to both run size and queue depth with zero new oracle (reusing `max_cycles` + queue length), bounds any single feature to ≤40% of the run, and removes the per-run hand-tuning a static default forces. The `--strict`/override flag is preserved either way for operators who want a fixed cap.

### 2. Skip-ahead readiness predicate — hard-dep-absence alone vs. add a shared-state isolation rail

**Problem:** The existing `## Locked Decisions` block states that dependency-aware skip-ahead is default-on and that *"the `hard`-dep readiness predicate is the safety rail that makes default-on safe."* Research **directly challenges that claim** (`RESEARCH.md` §4, FLAG: The Readiness Predicate). Bazel/Buck2 evidence shows that human-*declared* dependencies are routinely incomplete, and that out-of-order execution on a **shared, unsandboxed filesystem** — which is exactly our case (the state machine operates on one Git working tree with no Linux-namespace hermeticity) — risks an **undeclared-dependency collision**: a skipped-ahead feature mutates shared repo state that the gated head implicitly relied on, producing merge conflicts or silent logic regressions when the head later runs. Research's verdict: hard-dep absence alone is *"fundamentally insufficient for autonomous safety on a shared filesystem."* Because this contradicts a locked decision, the operator must decide whether to keep the predicate as-is or harden it.

**Options:**
- **Add a lightweight shared-state isolation rail (Recommended)** — keep default-on skip-ahead, but make a candidate "skip-ahead-ready" only when it passes hard-dep-absence **AND** one additional cheap guard. The lightest defensible form: require the skipped item to carry an explicit `independent: true` (a.k.a. `no_shared_state`) marker in its SPEC/queue entry (default absent ⇒ NOT skip-ahead-eligible), so skip-ahead advances only onto items a human (or a prior planning step) has affirmatively declared isolated. This keeps the run autonomous and deterministic (an on-disk flag, not an LLM judgment), closes the undeclared-dependency hole research flagged, and degrades safely (absent flag ⇒ behaves like today's strict halt for that item). Cost: items must be annotated to benefit from skip-ahead, so the feature's reach is gated on annotation coverage; a separate Phase can backfill the flag across the queue. Heavier variants (file-touch-target validation, per-skip Git-branch isolation) are noted as Phase-N hardening but are out of scope for v1.
- **Keep hard-dep-absence as the sole predicate (as currently locked)** — ship exactly what the `## Locked Decisions` block says: skip-ahead-ready iff no `hard` dep resolves to a gated item, with no extra rail. Simplest and matches the operator's prior choice; relies on dep blocks being authored correctly. Cost: accepts the research-documented risk that a *mis-declared or under-declared* dep block lets skip-ahead advance onto an item that actually shares state with the gated head, causing a hard-to-debug regression in an unattended run — the precise footgun research says shared-filesystem pipelines must guard against.

**Recommendation:** Add a lightweight shared-state isolation rail (explicit `independent: true` marker as the second key) — it preserves the autonomous, deterministic, default-on behavior the operator already chose while closing the undeclared-dependency hole that research identifies as the central skip-ahead risk on an unsandboxed working tree. The marker is on-disk state (no new oracle, no LLM judgment), and absent-flag items simply behave as they do today, so it is a strict safety addition rather than a behavior reversal.

## Resolution

Resolved by operator via `/lazy-batch` Step 1g `AskUserQuestion` on 2026-06-19 (both choices matched the research-backed recommendations).

1. **Default per-feature ceiling** → **Dynamic fair-share formula**. Compute the ceiling at run start (or when the feature reaches the queue head) as `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`, where `C_global` is the run's `max_cycles` and `Q_depth` is the count of ready queue features. Guarantees no single feature consumes >40% of the run budget with a 6-cycle minimum floor; reuses `max_cycles` + queue length (no new oracle). The operator-facing notification must report the *computed* ceiling. A `--per-feature-cycle-cap` override flag is preserved.
2. **Skip-ahead readiness predicate** → **Add the shared-state isolation rail**. A candidate is "skip-ahead-ready" only when it passes hard-dep-absence **AND** carries an explicit `independent: true` (a.k.a. `no_shared_state`) marker in its SPEC/queue entry (default absent ⇒ NOT skip-ahead-eligible). On-disk, deterministic (no LLM judgment); absent-flag items behave as today's strict halt. **This REVISES the existing `## Locked Decisions` skip-ahead entry** — update that block so the readiness predicate is "no `hard` dep on a gated item AND `independent: true`", not hard-dep-absence alone. Heavier hardening (file-touch-target validation, per-skip Git-branch isolation) is noted as Phase-N, out of scope for v1.

Propagate both into SPEC.md, REVISING the `## Locked Decisions` skip-ahead entry per Decision 2, then neutralize this sentinel.

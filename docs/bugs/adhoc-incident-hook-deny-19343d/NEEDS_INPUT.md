---
kind: needs-input
feature_id: adhoc-incident-hook-deny-19343d
written_by: root-cause-trace-gate
next_skill: spec-bug
class: product
stub_origin: true
decisions:
  - Disposition of the working-as-designed loop-formation-flag deny cluster
date: 2026-07-12
---

## Decision Context

### 1. Disposition of the working-as-designed loop-formation-flag deny cluster

**Problem:** incident-scan auto-captured 3 `lazy-cycle-containment` `loop-formation-flag` denies in claude-config on 2026-07-12 (14:24→15:59Z) and enqueued this bug stub. Investigation established two things with high confidence: (a) the containment hook is **correct-by-design** — a `loop-formation-flag` deny fires only when a dispatched cycle subagent (PreToolUse `agent_id` present) invokes an orchestrator-only state-script flag (`--probe` / `--emit-prompt` / `--run-start|end` / `--apply-pseudo` / `--enqueue-adhoc` / `--emit-dispatch` / `--cycle-begin|end` / `--repeat-count[-peek]`), and **no sanctioned subagent path reaches those flags** (the only subagent state-script call, the turn-end `--verify-ledger`, is allow-listed); and (b) the deny ledger correlates all three to the `live-settings-split-brain-disarms-enforcement-plane` remediation run — the very run that re-registered this hook after the 2026-06-11→2026-07-12 split-brain blind window. So the cluster is the containment hook coming back online and correctly stopping in-flight subagent overreach during that remediation.

The **root-cause-trace gate blocks concluding** because the fix-site *driver* is `asserted`, not `traced`: the deny event stores only the fixed corrective string (not the offending command), and no 2026-07-12 workstation transcript survives locally, so the exact op each subagent ran — and its authoring instruction — cannot be pinned surface→source. Because the hook is provably correct, there is no code cause to fix, and the remaining question is a disposition the operator must own: how should the harness treat a recurring, provably-working-as-designed containment-deny cluster? The options diverge in harness behavior (a durable traceability change vs. a collector-tuning change vs. no change) and depend on operator intent about how much to invest — a product-class decision, not effort-only. This sentinel carries `stub_origin: true` because the investigation did not reach a proven, lockable code cause (pre-conclusion halt).

**Options:**
- **Close as working-as-designed — no code change (Recommended)** — Accept that the hook is correct (relaxing it would re-open the runaway-loop hole its C2/C3 lockstep closes) and that the cluster is a one-off transient of the split-brain re-arm, with no standing skill/component driver found (grep surfaced only orchestrator-path loop-formation sites). Resolve the queue item toward `Won't-fix`. Cost: near-zero. Risk: if the same signature recurs in a *future* run outside a re-arm event, it remains un-root-causable (the traceability gap persists) — accepted as low given severity Low and no product impact.
- **Durable traceability fix — capture the offending command in loop-formation deny events** — Enrich `lazy-cycle-containment.sh` `_deny` / `lazy_core.append_hook_event` (and the `INCIDENT.md` capsule) to record the denied Bash command (truncated/sanitized) alongside the signature, so any future `loop-formation-flag` recurrence IS root-causable to the driving op and its skill. Additive only — the deny verdict is unchanged. Cost: a small bounded change across the hook + shared appender + incident capsule + tests. Risk: minor (log-content sizing; command may contain paths). This is the highest-value durable improvement and the natural spin-off if recurrence continues.
- **Tune incident-scan to not re-capture never-false-positive containment denies** — Down-weight or exclude `lazy-cycle-containment|loop-formation-flag` (a provably-never-false-positive class) from incident-scan's `hook-deny` capture so it no longer generates un-actionable bug stubs. Cost: a small config/predicate change in `incident-scan.py` + tests. Risk: suppresses a genuine prompt-adherence / subagent-overreach signal — a recurring cluster could indicate a real mis-scoped skill and would no longer surface; weakest option on its own.

**Recommendation:** Close as working-as-designed — no code change. The hook is provably correct, the cluster is contained to the split-brain re-arm run, and no standing driver exists; resolve the queue item toward `Won't-fix`. If the operator prefers durable value, the second option (capture the offending command in loop-formation deny events) is the recommended spin-off — implement it as a follow-up rather than relaxing the correct hook or blinding the collector.

## Resolution

*Recorded on 2026-07-12 UTC.*

### 1. Disposition of the working-as-designed loop-formation-flag deny cluster

**Choice:** Close as working-as-designed — no code change
**Notes:** Operator selected the recommended disposition. The containment hook is provably correct; resolve this queue item toward `Won't-fix`. No code change; no spin-off enqueued this cycle (the command-capture traceability option remains the recommended follow-up should the signature recur outside a re-arm event).

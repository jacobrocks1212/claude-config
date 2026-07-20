---
kind: gate-verdict
feature_id: subagent-wedge-backstop-hook
gate_version: 1
date: 2026-07-18
scope_hit: [user/hooks/subagent-wedge-backstop.sh, user/settings.json, user/hooks/CLAUDE.md]
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: hit-signed
  complexity: declared
retires: net-new — a SubagentStop enforcement hook that mechanically backstops a genuinely-wedged dispatched subagent (blocks-once via exit 2, keyed on the documented agent_id). It is net-new enforcement surface, not a replacement; it pays for itself by closing the strand-on-dead-stop class that the sender-side turn-end-gate prose cannot self-enforce.
override: operator-approved 2026-07-18 — false-positive gate_weakening flag on a plane-STRENGTHENING change (adds a new enforcement hook); the sole evidence is LAZY_QUEUE.md generated queue-count renumbering. Signed via /lazy-batch Step 1g.
---

## Adversarial answers

### overfit
The checker flagged "alternation literal appended" (`_HOOK_NOPY_TS="$(date +%s ...)"` — the new
hook's fail-open breadcrumb) and "incident-shaped literal add" (in an UNRELATED bug SPEC,
`run-end-efficacy-breadcrumb-misattributed-...`, swept into the commit range, not this feature's
work) plus a plan-doc literal. The new hook keys on **structural signals** — run-marker presence,
active-plan `status != Complete`, and (git-dirty OR unchecked plan WUs) — not on any incident
literal; its predicate is deliberately generic (and its known over-broadness is already spun off as
`adhoc-subagent-wedge-hook-overfires-globs-all-plans`). Nearest recurrence the hook must catch: ANY
dispatched subagent that stops with uncommitted work under a live run marker — caught by the
git-dirty structural half, independent of which plan or feature. The breadcrumb literal is the whole
class (a single per-agent_id staleness key), not a fit to one incident.

### tautology
N/A — no self-emitted-signal metric concern; the feature declares a measurable KPI
(`subagent-wedge-strand-recurrence` over the deny-ledger `process-friction-count`), an independent
signal the hook does not itself emit.

### gate_weakening
The checker's SOLE gate_weakening evidence is **LAZY_QUEUE.md numeric-literal changes** — the
auto-generated queue-status doc's counts renumbering (`## Bugs (17) → ## Bugs (16)`, queue index
shifts) as items complete. LAZY_QUEUE.md is a GENERATED doc regenerated on every cycle commit, NOT
a gate; its counts are not a "gate line." The actual feature diff ADDS a new SubagentStop
enforcement hook + registers it — the OPPOSITE of a weakening. No `def test_*` deleted, no
`permissionDecision: deny`/`refuse_*`/`exit 3` removed, no `*_BYPASS=` added. Underlying-defect
alternative: none — the change strengthens the plane. Routed to operator sign-off per the
never-judgment-passable rule; `override` above records the approval. Per-change, non-standing.

### complexity
Net-new enforcement surface (see `retires:`). One hook script (~fail-open, blocks-once,
agent_id-keyed staleness GC) + a SubagentStop/SessionEnd registration + a Hooks-table row. It
generalizes: the loop-guard keys on the documented agent_id so it bounds ANY wedged dispatched
subagent, not the one observed instance.

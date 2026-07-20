---
kind: gate-verdict
feature_id: spike-pipeline-role
gate_version: 1
date: 2026-07-18
scope_hit: [user/scripts/lazy-state.py, user/scripts/bug-state.py, user/scripts/lazy_core/docmodel.py, user/scripts/lazy_core/gates.py, user/scripts/lazy_core/__init__.py, user/scripts/lazy-parity-manifest.json, user/skills/lazy-batch/SKILL.md, user/skills/lazy-bug-batch/SKILL.md]
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: hit-signed
  complexity: declared
retires: net-new — the Spike role is a deliberately added pipeline stage (runtime-proof gate before mark-complete); its loop-guard caps (spike_tooling_rounds ≤ 3) bound the added surface, and the role replaces ad-hoc "trust the narrative" completions for runtime-coupled claims
override: operator-approved 2026-07-18 — gate-weakening evidence is entirely LAZY_QUEUE.md dashboard-regen churn (queue counts/positions shifting as other items were fixed in the same range); no code gate line, test, exemption set, or deny branch was touched — spike's diff ADDS 45+ tests and routing
---

## Adversarial answers

Checker run: `harness-gate.py --range 1268aa65~1..fcb6a6d6 --feature-dir docs/features/spike-pipeline-role`
(the range interleaves same-night run machinery — LAZY_QUEUE regens, adhoc queue enqueues —
which dominates the evidence lines; the spike code diff itself is commits 1268aa65, 4cee96e3,
5f8ab040, fcb6a6d6).

### overfit

Evidence is queue.json enqueue rows from OTHER items sharing the range plus spike's own new
step-name strings and test-fixture literals — the documented fixture-literal false-positive
class (Rounds 91–93 precedent). Nearest-recurrence test: the production routing keys on
structural predicates (`**Spike:** required` header parse via `phases_spike_required`,
`blocker_kind: runtime-spike-verdict-pending`, `spike_tooling_cap_exceeded` counter), not on
any observed slug/date literal; a future spike on any feature is caught by the same parsers.

### tautology

Flag = no `## Intervention Hypothesis` block in the pre-existing SPEC (authored before that
convention). Independent signal declared: the role's success metric is future runs'
spike-routing outcomes — SPIKE_VERDICT PASS/FAIL artifacts and cap-bounded needs-input halts
produced by the runtime/tooling under test, not by the routing change itself — plus the
`__mark_complete__`-recorded intervention row (repo has `interventions: true`), which the
efficacy evaluator grades independently. If the routing were broken, spikes would simply
never fire (observable as zero SPIKE_VERDICT artifacts on `**Spike:** required` phases),
which is distinguishable from working.

### gate_weakening

All 19 evidence lines are `LAZY_QUEUE.md` regenerated-dashboard numeric churn (e.g.
`## Bugs (8) → (9)`, queue-position renumbering) from the interleaved run commits. No
`def test_*` deleted (spike ADDED test_spike_state_routing.py 14 cases,
test_spike_tooling_loop.py 31 cases, +7 units), no gate-line numeric changed, no
exemption/sanction set grown, no deny/refusal removed. Operator sign-off recorded in the
`override:` line above (AskUserQuestion, 2026-07-18).

### complexity

`net-new` declared honestly: the Spike role is an added pipeline stage by design (SPEC'd,
phased, operator-initiated). The added surface pays for itself by replacing narrative-trust
completions on runtime-coupled claims with a bounded, evidence-bearing proof step; the
tooling loop is hard-capped (3 rounds → needs-input), so the surface cannot grow unbounded.

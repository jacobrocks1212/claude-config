---
kind: fixed
bug_id: orchestrator-misroutes-on-grandchild-subagent-notifications
provenance: backfilled-unverified
fixed_by: harden-harness
fix_commits: [ca7f2c8b]
date: 2026-07-18
---

# Fixed — orchestrator misroutes on grandchild sub-sub-agent notifications

Resolved OUT-OF-PIPELINE by harden-harness Round 98 (inline manual invocation).
See `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 98.

**BUG 1 (fixed).** New `§1d-await` subsection in `lazy-batch`, `lazy-bug-batch`, and
`lazy-batch-cloud` SKILL.md: the `Agent` cycle dispatch is async; the orchestrator acts ONLY on
its DIRECT cycle child's notification (task-id == the dispatched `agentId`, positive signal; WAIT
default otherwise), and never `--cycle-end`/routes/`TaskStop`s on a grandchild (sub-sub-agent)
notification. Never kills a cycle on a grandchild BLOCKED/failure.

**BUG 2 (pinned + standing rule).** The `No tools needed for summary` tool wedge is a
platform-runtime transient — not a claude-config surface (`grep` finds it nowhere in the repo; it
fires uniformly before every tool type, which no per-tool `PreToolUse` hook could produce), so it
is not fixable here. Standing rule shipped (§1d.1 Trigger 5 ×3 + `user/CLAUDE.md` auto-invoke
pointer): a sub-sub-agent tool-wedge auto-triggers a harden ONLY when non-transient (reproducible
/ ≥2×-recurring / not a platform blip).

**Fix commit:** `ca7f2c8b` (`harden(skill-prose)`).

**Evidence.** lazy_core pytest 1254/1254 · test_hooks 266/266 · lazy-state/bug-state `--test` PASS
· `--fsck` clean · lint clean · harness-gate clean (gate_weakening/overfit pass, complexity
net-new). No automated regression test is applicable — the fix is orchestrator-judgment prose with
no script/hook seam that observes task-notifications (documented in `SPEC.md` → "Why no mechanical
enforcement"), hence `provenance: backfilled-unverified`.

---
kind: needs-input
feature_id: byref-updatedinput-unapplied-on-background-agent-dispatch
written_by: harden-harness
class: process
divergence: structural
decisions:
  - "By-reference `updatedInput` rewrite unapplied on a background Agent dispatch — carve background dispatches to verbatim, add a subagent-side bare-token fallback, or confirm the platform behavior first? (feeds turn-routing-enforcement NEEDS_INPUT decision #1)"
date: 2026-07-17
---

## Decision Context

### 1. By-reference `updatedInput` rewrite unapplied on a background Agent dispatch — how to make it robust?

**Problem:** On a `run_in_background: true` Agent dispatch, the `lazy-dispatch-guard.sh` F2a path
ALLOWED the dispatch and CONSUMED the `@@lazy-ref` nonce (proving F2a ran and returned
`hookSpecificOutput.updatedInput` with the resolved prompt bytes) — yet the spawned subagent
received the **bare** `@@lazy-ref nonce=884c53da…` token, not the resolved bytes. The
`updatedInput` rewrite did not take effect on the background dispatch. The subagent recovered only
by manually resolving the nonce from the prompt registry (an improvisation, not a designed path;
the near-neighbor failure is a subagent that takes zero tool-uses and returns "no task attached").

This is a **sanctioned combination**: `lazy-batch/SKILL.md` §1d prefers `dispatch_prompt_ref`
(by-reference) at ALL dispatch sites, and line 849 dispatches non-blocking work BACKGROUNDED —
so background + by-reference is a path the harness actively produces.

**This is NEW, concrete evidence for the operator-owned park already open at**
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` **decision #1** ("keep `dispatch_prompt_ref`
PREFERRED, or flip to verbatim `dispatch_prompt`?"). It should be decided together with that
question, not in isolation.

**Why this is hard-parked (implemented nothing):**
- The root cause hinges on **unconfirmed Claude Code platform behavior** — whether
  `hookSpecificOutput.updatedInput` on a PreToolUse `allow` reliably REPLACES the Agent/Task
  tool's `prompt`, and specifically whether it does so for a **background** dispatch. This is only
  ASSERTED in code comments + skill prose (citing "lazy-validation-readiness Phase 3"), never
  confirmed against platform docs. Per the Step-2 platform-confirmation mandate (harden Round 83),
  load-bearing logic must not ship on an unconfirmed platform assumption; confirming it needs the
  `claude-code-guide` agent, which this marked hardening run's subagent policy forbids.
- Every candidate fix either **preempts the parked operator decision** or **band-aids over the
  unconfirmed behavior** (see Options).

**Options:**
- **(a) Confirm the platform behavior first (Recommended FIRST step).** Dispatch `claude-code-guide`
  (from an unmarked session, or by the operator) to confirm whether `hookSpecificOutput.updatedInput`
  is honored for the Agent/Task tool and for a background dispatch. If it is NOT reliably honored
  for background dispatches, option (b) becomes the durable fix; if it is never honored for the
  Agent tool at all, the by-reference edifice itself must be reconsidered (decision #1). Cost: one
  guide dispatch. Risk: none (read-only confirmation). No harness change until confirmed.
- **(b) Carve background dispatches out of the by-reference preference.** Prose contract across the
  coupled dispatch skills (`lazy-batch` ↔ `lazy-bug-batch` ↔ `lazy-batch-cloud`): dispatch the
  verbatim `cycle_prompt`/`dispatch_prompt` for any `run_in_background: true` Agent dispatch;
  by-reference stays a foreground-only convenience. Weakens no gate (verbatim is still fully
  hash-validated by the guard's normal `lookup_emission` ALLOW+consume). Platform-independent.
  BUT it is a **partial flip** of parked decision #1 — do not implement unilaterally.
- **(c) Subagent-side bare-token fallback.** A dispatch-template contract: a subagent that receives
  a bare `@@lazy-ref` token resolves it (never zero tool-uses). Orthogonal to the preference, but
  needs a sanctioned read path for a subagent to resolve a nonce the guard **already consumed**
  (`resolve_emission_by_nonce` filters consumed entries) — a new registry-read surface — and it
  band-aids over the unconfirmed platform behavior rather than confirming it.

**Recommendation:** (a) confirm the platform behavior via `claude-code-guide` FIRST, then decide
(b)/(c) together with the parked dispatch-preference decision #1. `divergence: structural` — the
choice reconfigures a shipped dispatch-preference control surface and/or the registry read model,
and it is already an operator-owned fork; do not provisional-implement over it. No gate weakened,
no registry/marker edited by this round.

## Resolution

- **Decision 1 (byref updatedInput on background dispatches):** **Option (a) — confirm the platform behavior first** — the recommended option, chosen by the operator via AskUserQuestion on 2026-07-18.
- **Propagation:** the orchestrator runs a read-only `claude-code-guide` confirmation immediately after this run's `--run-end` (unmarked session state; the guide dispatch is then guard-exempt) and records the finding in this bug dir. The (b)/(c) fix choice is then decided by the operator TOGETHER with the parked dispatch-preference decision #1 at `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md`, with facts in hand. This sentinel stays live (bug remains open) until that joint decision.
- resolved_by: operator (AskUserQuestion, Step 1g decision-resume; partial resolution — confirmation step authorized, fix fork intentionally still open)
- date: 2026-07-18

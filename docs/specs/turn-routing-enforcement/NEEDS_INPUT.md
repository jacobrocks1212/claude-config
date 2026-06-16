---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
decisions:
  - "Dispatch-preference contract for Agent dispatches: keep `dispatch_prompt_ref` (@@lazy-ref) PREFERRED, or flip to verbatim `dispatch_prompt`?"
date: 2026-06-16
class: product
next_skill: harden-harness
---

## Decision Context

### 1. Dispatch-preference contract for Agent dispatches: keep `dispatch_prompt_ref` (@@lazy-ref) PREFERRED, or flip to verbatim `dispatch_prompt`?

**Problem:** Hardening defect D-C exposed that a bare `@@lazy-ref nonce=<hex>` token reached a subagent unresolved, and the subagent silently improvised an off-task `/lazy` run (which then caused the D-B run-marker clobber). The *mechanical* hole is now closed — `lazy_guard.py` denies a bare `@@lazy-ref` token whenever it cannot resolve+consume it (including the previously-silent marker-absent fast-path), with a corrective reason that prescribes the verbatim `dispatch_prompt` (Round 19 mechanical fix, this dispatch). So a bare ref token can never again reach a subagent.

What remains is a **contract-preference fork** that is NOT mechanical to decide. Today the skill prose actively makes the by-reference token the PREFERRED dispatch form:
- `lazy-batch/SKILL.md:619` — "F2a dispatch-by-reference (PREFERRED when available) … use it as the `prompt:` field instead of the full `cycle_prompt` text."
- `lazy-batch/SKILL.md:621` — "Meta-dispatch by-reference — PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites … PREFER `dispatch_prompt_ref` over the verbatim `dispatch_prompt`."
- Mirrored in `lazy-bug-batch/SKILL.md` (coupled pair).

This preference was introduced deliberately in Phase 7 / lazy-validation-readiness to eliminate the **transcription-slip** failure class (a verbatim prompt hand-copied with a drifted byte gets denied). D-C is the opposite failure class: by-ref is *fragile to context loss* — it resolves ONLY inside the PreToolUse guard while the owning run marker is live, so any condition that hides/breaks the marker (a clobber, a session-id mismatch, a stale/consumed nonce) degrades the by-ref token to a bare unresolvable string. The two failure classes pull in opposite directions, so which form to PREFER is a genuine design tradeoff an operator should own — not something to flip silently in a hardening cycle.

**Options:**
- **Keep `dispatch_prompt_ref` PREFERRED (Recommended)** — Leave the contract as-is. Rationale: the by-ref token's only failure modes (unresolvable nonce, no live marker) are now HARD-DENIED at the guard with an actionable corrective, so the silent-improvisation hole is closed regardless of which form is preferred. By-ref still buys the transcription-slip immunity it was added for, and D-C's trigger condition (a clobbered marker) is itself independently fixed by D-B (`refuse_run_start_clobber`). Cost: by-ref remains the recommended form, so a future context-loss bug would surface as a deny (noisy but safe) rather than transparently working. Low risk, fully reversible (it is prose).
- **Flip to verbatim `dispatch_prompt` PREFERRED for Agent dispatches** — Change `lazy-batch` + `lazy-bug-batch` (+ `lazy-batch-cloud`) prose so the orchestrator dispatches the verbatim `dispatch_prompt` text and uses `dispatch_prompt_ref` only as a fallback / never. Rationale: a verbatim prompt is self-contained and portable — it cannot degrade to a meaningless token under marker loss. Cost: re-opens the transcription-slip class the by-ref preference was specifically introduced to close (the 2026-06-14 incident's 2 guard denials were transcription drift on a verbatim meta-dispatch); the F2c transcription-slip detector + F2b hash-fold remain as the backstop, but the preference would now lean on a weaker guarantee. This is a reversal of a prior locked design choice and touches three coupled SKILL files.
- **Make `@@lazy-ref` resolvable in more contexts** — Extend resolution so a by-ref token survives marker loss (e.g. resolve from the registry by nonce even without a live marker, gated by TTL only). Rejected as the recommended path: it would weaken the run-start gate (an entry must be dispatchable only within the owning run), which is load-bearing for the validate-deny model — exactly the kind of gate-softening the hardening prohibitions forbid. Listed for completeness.

**Recommendation:** Keep `dispatch_prompt_ref` PREFERRED — the mechanical guard deny (Round 19) already closes the silent-improvisation hole, D-B independently removes the clobber that triggered D-C, and the by-ref preference retains its transcription-slip immunity. Only flip to verbatim if the operator judges context-loss fragility a worse risk than transcription drift for the AlgoBooth fleet.

## Why this is surfaced and not auto-applied

Per the hardening prohibitions and decision-class tiering: D-A and D-B were applied mechanically under full gates (Round 19). D-C's mechanical half (guard deny) was ALSO applied mechanically — a bare unresolved ref token now hard-denies. The ONLY thing escalated here is the dispatch-preference contract flip, which reverses a deliberate Phase 7 design decision and trades one real failure class for another. That is a `product`-class fork, so it is surfaced via this file rather than baked silently.

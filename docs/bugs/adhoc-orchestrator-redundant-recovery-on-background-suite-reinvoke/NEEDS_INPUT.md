---
kind: needs-input
feature_id: adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke
written_by: spec-bug
next_skill: spec-bug
class: product
divergence: contained
stub_origin: true
decisions:
  - Fix approach — mechanical foreground enforcement, deterministic orchestrator pause signal, or both
date: 2026-07-19
---

## Decision Context

### 1. Fix approach — mechanical foreground enforcement, deterministic orchestrator pause signal, or both

**Problem:** The investigation traced two coupled defects (see SPEC Proven Findings). **Gap 1:** a cycle `/execute-plan` subagent backgrounded an over-cap (>~10 min) aggregate verification suite and returned "holding, will re-invoke" instead of foreground-awaiting it — violating a **prose-only** mandate (`cycle-base-prompt.md` turn-end §1) that has no mechanical enforcement. **Gap 2:** the orchestrator's post-cycle path (`lazy-batch/SKILL.md` Step 1e / guardrail D) has no way to tell that "holding" return apart from a genuine resultless return, so it dispatched a redundant `--emit-dispatch recovery` cycle that collided (two writers on the same files) with the harness-re-invoked agent and had to be `TaskStop`-ped. The root cause is proven and the fix site is on the traced path for both gaps; what remains is a genuine design choice about *which seam(s) to fix*. It shapes the entire fix (which files change, whether a new enforcement hook is introduced, and the observable run behavior), and this is a stub baseline the operator has never reviewed — so it is parked rather than auto-decided. Complicating factor: `turn-end-gate.md` L13–18 asserts dispatched agents CANNOT get background re-invocation, yet the run observed re-invocation happening — so a prose-only fix (Gap 1 alone) is unreliable, and the actual re-invocation behavior bears on how strong Gap 1's prevention must be.

**Options:**
- **Both — deterministic orchestrator signal (Gap 2, load-bearing) + mechanical foreground enforcement (Gap 1, prevention) (Recommended)** — Wire the receiver-side authoritative signal that already exists in `dispatched-agent-liveness.md` (execute-plan run marker present + plan `status:` not Complete ⇒ agent is PAUSED, not terminal) into `lazy-batch`/`lazy-bug-batch` Step 1e so guardrail D skips recovery dispatch on a paused/will-re-invoke cycle; AND add a mechanical guard (a `user/hooks/` PreToolUse deny on a `run_in_background` long gate launched inside an armed cycle subagent) so the "holding" precondition rarely arises. Defense-in-depth: Gap 2 is the correctness fix (stops the dual-writer even if a hold slips through); Gap 1 removes the trigger. Cost: two coupled changes (orchestrator prose + coupled bug-batch mirror + a new hook with its false-positive surface). Highest completeness; the hook is the extra scope.
- **Deterministic orchestrator signal only (Gap 2)** — Fix only the orchestrator: consult the run marker + plan status before dispatching recovery; on a paused agent, WAIT for re-invocation instead of recovering. Cheapest, lowest-risk, reuses existing machinery, no new hook/false-positive surface. Leaves cycle subagents free to keep backgrounding (still contract-violating, still noisy in logs), and relies on the harness's re-invocation actually firing — if re-invocation is unreliable, a backgrounded suite could genuinely stall (no recovery would fire because the orchestrator now treats the marker as "paused").
- **Mechanical foreground enforcement only (Gap 1)** — Add a hook that denies backgrounding a long gate inside a cycle subagent, forcing under-cap foreground sub-components; the "holding" return never happens, so the orchestrator never faces the ambiguity. Prevents the trigger at the source. Risk: a new control surface with false-positive potential (distinguishing a "long gate" from any backgrounded command), and it does NOT protect against any OTHER paused-return shape reaching guardrail D — the orchestrator's blind spot persists for non-gate pauses.

**Recommendation:** Both — deterministic orchestrator signal (Gap 2) + mechanical foreground enforcement (Gap 1). Gap 2 is the load-bearing correctness fix (it stops the dual-writer collision directly and reuses the already-designed `dispatched-agent-liveness.md` signal), and Gap 1 removes the trigger so the ambiguous return is rare; together they are robust to the observed re-invocation contradiction. If the operator prefers minimal scope, "Gap 2 only" captures most of the safety at lowest cost, deferring the enforcement hook.

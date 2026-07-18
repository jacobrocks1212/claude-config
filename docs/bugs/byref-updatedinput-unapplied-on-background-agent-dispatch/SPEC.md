# By-reference dispatch `updatedInput` rewrite unapplied on a background Agent dispatch

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-17
**Related:** `docs/specs/turn-routing-enforcement/` (the hardening stage + the operator-owned
dispatch-preference park — this SPEC is NEW evidence for its `NEEDS_INPUT.md` **decision #1**:
"keep `dispatch_prompt_ref` (@@lazy-ref) PREFERRED, or flip to verbatim `dispatch_prompt`?");
`docs/specs/lazy-validation-readiness/` (Phase 3 — where F2a by-reference + `updatedInput` shipped);
`docs/bugs/_archive/bug-pipeline-cycle-dispatch-omits-cycle-prompt-ref/` (the ref emission origin).

## Trigger

Harness-hardening dispatch (`trigger_kind: harness-gap`) during a live `/lazy-batch` run with
`dispatch-probe-and-inject-bypass-merged-head` in flight. On **cycle 1**, a **`plan-bug`
background Agent dispatch** used the by-reference token `@@lazy-ref nonce=884c53da3dc841b1b7f85fb1c89546bc`.

- The `lazy-dispatch-guard.sh` PreToolUse guard **ALLOWED** the dispatch (NOT a deny).
- The guard's F2a branch resolved + **consumed** the nonce (registry state at dispatch time:
  nonce `884c53da…` **registered + consumed**), which proves F2a ran and returned
  `_allow_with_updated_input(...)` with `updatedInput.prompt = <resolved bytes>`.
- **Yet the subagent received the BARE `@@lazy-ref` token** — the `updatedInput` rewrite did not
  take effect. The subagent had to resolve the nonce **manually** from the prompt registry to
  recover its actual task.

## Reconstructed route (divergence point)

The by-reference contract (`lazy-batch/SKILL.md` §1d "F2a dispatch-by-reference"; `lazy_guard.py`
`_allow_with_updated_input`; `lazy_core/dispatch.py:1703`) asserts:

> The PreToolUse guard resolves the token → registered bytes and **rewrites the tool input**
> (via `hookSpecificOutput.updatedInput`) before the subagent runs — the subagent receives the
> full prompt unchanged.

Two independently-sanctioned harness rules collide here:

1. **"Prefer by-reference at ALL dispatch sites."** `lazy-batch/SKILL.md` §1d ("Meta-dispatch
   by-reference — PREFER `dispatch_prompt_ref` at ALL `--emit-dispatch` sites") and the cycle
   dispatch (`prompt: <cycle_prompt_ref if present, else cycle_prompt verbatim>`).
2. **"Dispatch non-blocking work BACKGROUNDED."** `lazy-batch/SKILL.md` line 849
   (observed-friction / non-blocking harden policy D1): "pass `blocking=false` and dispatch
   **backgrounded** (`Agent` with `run_in_background: true`)."

Their intersection — **a `run_in_background: true` Agent dispatch carrying a `@@lazy-ref`
token** — is the exact combination that failed. F2a produced the correct `updatedInput`, but it
was not applied to the background dispatch, so the subagent booted with the literal reference
token as its prompt.

**Divergence point:** the F2a guard ALLOW+`updatedInput` rewrite of a `@@lazy-ref` token does not
reach a **background** Agent dispatch's subagent — a sanctioned background+by-reference dispatch
lands the bare token instead of the resolved bytes.

## Root cause

**`root_cause_class: missing-contract`**, with an unconfirmed-platform-behavior dependency at its
core:

- The whole F2a by-reference mechanism rests on the ASSERTED (never-repo-confirmed) Claude Code
  platform behavior that `hookSpecificOutput.updatedInput` on a PreToolUse `allow` REPLACES the
  Agent tool's `prompt` before execution. This is stated only in code comments and skill prose,
  citing "lazy-validation-readiness Phase 3" — no platform-doc confirmation exists in-repo.
- Field evidence now shows the rewrite did **not** apply to a background Agent dispatch, while the
  by-reference path is heavily used and works for the foreground synchronous cycle dispatch —
  consistent with prior rounds where **background** Agent dispatches have repeatedly been a
  distinct, problematic class (hardening Round ~28: the containment hook needed a dedicated
  background-dispatch deny branch because "a backgrounded child reaches only the main thread").
- There is **no contract** carving background dispatches out of the by-reference preference, and
  **no subagent-side fallback** telling a subagent that receives a bare `@@lazy-ref` token to
  resolve it (rather than taking zero tool-uses and returning "no task attached", the exact
  failure the SKILL prose warns about for stale banners).

"The rewrite didn't fire" is not a terminal diagnosis; the harness question is which change makes
the failure impossible or self-announcing — and that answer is entangled with (a) an operator-owned
design fork and (b) an unconfirmed platform behavior (below).

## Verified symptom

- Guard ALLOWED (no deny ledger entry); nonce `884c53da…` observed **consumed** in the registry
  (F2a fired).
- Subagent's received prompt was the literal `@@lazy-ref nonce=884c53da…` line, not the resolved
  bytes → subagent improvised recovery by reading the prompt registry.

## Fix scope — DEFERRED to the operator-owned park (nothing implemented this round)

The candidate fixes all either (a) preempt the **already-hard-parked** operator decision, or
(b) depend on / band-aid over the unconfirmed platform behavior:

1. **Carve background dispatches out of the by-reference preference** (dispatch verbatim for any
   `run_in_background: true` Agent dispatch; by-reference stays a foreground-only convenience).
   This is a **partial flip** of the very "keep by-ref preferred vs. flip to verbatim" question
   the operator has parked (`turn-routing-enforcement/NEEDS_INPUT.md` decision #1) — implementing
   it unilaterally preempts that decision. Weakens no gate (a verbatim prompt is still fully
   hash-validated by the guard's normal `lookup_emission` ALLOW+consume path).
2. **Subagent-side bare-token fallback** ("if your prompt is a bare `@@lazy-ref` token, resolve it
   before proceeding; never take zero tool-uses"). Orthogonal to the preference, but needs a
   sanctioned read path for a subagent to resolve a nonce the guard **already consumed**
   (`resolve_emission_by_nonce` filters consumed entries) — a new registry-read surface — and it
   band-aids over the unconfirmed platform behavior rather than confirming it.
3. **Confirm the platform behavior first** (does `hookSpecificOutput.updatedInput` reliably apply
   to the Agent/Task tool, and specifically to a background dispatch?) via the `claude-code-guide`
   agent, then decide whether by-reference is safe as the preferred path at all. This is the
   correct FIRST step but requires an Agent-tool dispatch that this marked hardening run is
   forbidden from making (subagent policy).

**Blocker (why nothing shipped):** the root cause hinges on unconfirmed Claude Code platform
behavior (Step-2 platform-confirmation mandate; harden Round 83). Confirming it requires
`claude-code-guide`, which the marked-run subagent policy forbids this session. Per Step-2
guidance ("if an undocumented dependency is unavoidable, hard-park it for the operator rather than
shipping on the assumption") AND because the disposition is an **already operator-owned** design
fork, this is a hard-park carve-out: the new evidence is fed into the existing park
(`turn-routing-enforcement/NEEDS_INPUT.md` decision #1) and a bug-local `NEEDS_INPUT.md` halts this
item pending the operator decision. **No gate weakened; no registry/marker edited.**

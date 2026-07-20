---
kind: needs-input
feature_id: byref-updatedinput-unapplied-on-background-agent-dispatch
written_by: execute-plan
class: product
divergence: structural
decisions:
  - "WU-3 self-resolving @@lazy-ref wrapper cannot deliver end-to-end without a PreToolUse dispatch-guard change — where does the by-reference resolve-first contract live, and does the guard change?"
date: 2026-07-19
next_skill: execute-plan
---

# /execute-plan — Needs Input (Phase 2 / WU-3 design fork)

Phase 1 (WU-1 `resolve_consumed_emission_by_nonce` + WU-2 `--resolve-ref` CLI on both
state scripts) is **complete, committed, and pushed** — the sanctioned consumed-nonce
read surface exists and is parity-audited. Phase 2 (WU-3 self-resolving dispatch
template; WU-4 coupled prose) hit a load-bearing integration fork that was not visible at
plan time and conflicts with a SPEC Locked framing. Halting for one decision.

## Decision Context

### 1. WU-3 self-resolving `@@lazy-ref` wrapper requires a dispatch-guard change to work end-to-end — reconcile the delivery mechanism

**The gap (empirically verified this cycle).** WU-3 says: wrap the emitted
`@@lazy-ref nonce=<hex>` token with a first-step resolve instruction and make that
**wrapper** the surfaced `cycle_prompt_ref` / `dispatch_prompt_ref`. But the fix only
works if the subagent can run `--resolve-ref N` and get its real bytes — and WU-1's
consumed-reader **requires nonce N to already be CONSUMED**. The guard consumes N **only**
when it sees a **bare** token: `lazy_guard.py::_REF_RE = ^@@lazy-ref nonce=<hex>$` is a
**full-match** on the stripped prompt.

I invoked the real guard against a wrapped ref (`"…FIRST run --resolve-ref N\n\n@@lazy-ref
nonce=N"`):

- guard `permissionDecision: deny` (F2a full-match fails → hash-lookup of the wrapper
  fails → deny),
- nonce N **NOT consumed**,
- therefore `resolve_consumed_emission_by_nonce(N)` → `None` (the subagent's
  `--resolve-ref N` would fail).

So a wrapped surfaced-ref (a) is **denied** by the guard (the orchestrator falls to the
verbatim path, i.e. by-reference is effectively dead), and (b) even if allowed, leaves N
unconsumed so the WU-1 reader can't resolve it. The two requirements —
*guard consumes N* (needs a bare token) and *subagent sees the resolve instruction*
(needs the wrapper in the prompt) — **conflict** unless the guard is taught to
extract+resolve+consume a token embedded in a larger prompt.

**Why this is a fork, not a mechanical fix.** Teaching the guard to consume a token inside
a wrapper is a change to `lazy_guard.py` (+ `test_hooks.py`) — a **PreToolUse control
surface** that (i) is NOT in WU-3's plan file list (`dispatch.py` + the two state scripts +
SKILL prose + tests), and (ii) is in tension with the SPEC's Locked framing that "the
guard's `lookup_emission` ALLOW+consume hash-validation is **unaffected** by the bug and
stays the integrity mechanism" (PHASES: "Do NOT weaken the existing guard"). It is also
security-relevant (widens what the guard ALLOWs+consumes). This is exactly the class of
control-surface decision a `--batch` park-mode cycle must not resolve unilaterally.

**Context the operator should weigh:** `PLATFORM_CONFIRMATION.md` already found option (c)
"dead on arrival **as designed**" (no hook path can rewrite an Agent prompt; upstream
#39814 closed not-planned) and that the evidence "supports flipping the preference to
verbatim". The operator nonetheless locked option (c) (subagent-side resolve) on
2026-07-18. This sub-fork — *how* the resolve-first contract reaches a by-reference
subagent — is the concrete mechanism that lock did not pin.

**Options:**

- **(a) [RECOMMENDED] Keep the guard UNCHANGED; deliver the resolve-first contract via
  PROSE, not the emitted token.** The surfaced ref stays a **bare** `@@lazy-ref nonce=N`
  token (guard F2a consumes N exactly as today → `--resolve-ref N` resolves). WU-3's
  Python wrapper-helper is dropped (the emit sites are byte-unchanged); the "your
  instructions are registered under nonce X; FIRST run
  `<state-script> --repo-root <root> --resolve-ref X`" contract is authored in WU-4's
  coupled dispatch-skill prose (`lazy-batch` ↔ `lazy-bug-batch` ↔ `lazy-batch-cloud`) and
  the subagent dispatch briefing (`cycle-base-prompt.md` / CLAUDE.md, which a dispatched
  subagent inherits). Satisfies SPEC items 1-4 (the `--resolve-ref` read shipped in
  Phase 1 is exactly what the prose points at) **without touching the guard** — preserving
  the "guard's ALLOW+consume unaffected" Locked Decision verbatim.
  - *Divergence from the plan:* WU-3's emitted-surface wrapper + its zero-tool-use
    emission unit test are removed; the "contractual first step" moves from the emitted
    token to prose (the WU-4 layer) + a subagent-briefing rule. Reframes WU-3 as a
    prose/briefing deliverable rather than a `dispatch.py` helper.
  - *Risk:* relies on the subagent's standing context (dispatch briefing / CLAUDE.md)
    reaching a by-reference subagent whose literal prompt is only the token. If that
    standing context does not reliably reach such a subagent, (b) or (c) is the durable
    fix.

- **(b) Extend the guard's F2a to resolve+consume a `@@lazy-ref nonce=N` token that
  appears on its OWN LINE within a larger prompt** (relax the full-match to a
  dedicated-line match; still gate ALLOW on a valid, unforgeable, unconsumed nonce). Makes
  WU-3's wrapper work exactly as written — the wrapper is both ALLOW+consumed AND delivered
  to the subagent.
  - *Cost:* a change to `lazy_guard.py` + `test_hooks.py` (a PreToolUse control surface
    outside WU-3's scope), and a `GATE_VERDICT.md` / harden-review pass under
    `harness-change-gate.md` (gate-behavior change). Arguably non-weakening (the nonce
    stays the sole credential) but it contradicts the SPEC's "guard unaffected" framing, so
    it needs an explicit operator ok.

- **(c) Abandon by-reference for Agent dispatches and flip to verbatim** — the direction
  `PLATFORM_CONFIRMATION.md`'s evidence supports and the still-open parked decision
  `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` #1 asks. WU-1/WU-2's `--resolve-ref`
  stays as an operator/diagnostic read; WU-3/WU-4 are re-scoped to "verbatim is the
  dispatch, `@@lazy-ref` demoted until upstream #39814 is fixed".
  - *Cost:* the largest divergence — reconfigures the dispatch-preference control surface
    and overlaps the joint decision #1 (should be decided together with it).

**Recommendation:** **(a)** — it delivers the operator-locked "designed subagent-side
resolve" mechanism (the shipped `--resolve-ref` read is the command the prose names; the
bare token still consumes N so the read resolves) **without** touching the
security-relevant dispatch guard, keeping the SPEC's "guard's ALLOW+consume unaffected"
Locked Decision intact. If the operator wants the wrapper delivered by the emitted token
itself (WU-3 as literally written), that is option (b) and requires an explicit
guard-change sign-off. `divergence: structural` — the options fork where the delivery
contract lives, whether the guard's matching changes, and (for (c)) whether by-reference
survives at all.

---
kind: needs-input
bug_id: meta-dispatch-not-by-reference-and-ack-overpriced
written_by: fix
decisions:
  - "D1: locked-decision-4 conflict — relax one-hardening-dispatch-per-deny for the cheap-ack classes"
  - "D2: ack selector shape — FIFO-oldest vs denied_sha12-addressed"
date: 2026-07-12
class: product
divergence: isolated
audit_divergence: isolated
next_skill: fix
---

# NEEDS_INPUT — Provisionally Accepted (park-provisional protocol)

This bug's SPEC marks **D1 as `NEEDS OPERATOR`** explicitly: Fix Scope §1/§2 (a cheap per-entry
ack CLI + same-cause dedup) deliberately relax `turn-routing-enforcement`'s **locked decision 4**
("one hardening dispatch per deny — inline, unbounded, no dedup"). That is a change to a
previously-locked decision elsewhere in the harness, which the SPEC says needs explicit operator
sign-off before `/plan-bug`. Per the park-provisional protocol, this session implemented the SPEC's
own recommended Fix Scope in full (Half 1 was already fixed in current code; Half 2's cheap-ack +
dedup + regression guard are now implemented and TDD-covered) rather than halting, and records the
locked-decision relaxation here for ratify-or-redirect review. **This bug's Status is NOT flipped
to Fixed and the directory is NOT archived** pending that review, even though the code is
implemented, tested, and landed.

## Decision Context

### 1. D1: locked-decision-4 conflict (NEEDS OPERATOR per the SPEC)

**Problem:** `turn-routing-enforcement` locked "one hardening dispatch per deny — inline,
unbounded, no dedup" as a deliberate anti-abuse design (every denial costs a full Opus
`/harden-harness` round, so there is no cheap way to wave away debt). This bug's Fix Scope
explicitly asks for the opposite for two named classes: (a) a denial whose root cause was already
fixed by an earlier round this run (the observed turns ~125–182 redundant-second-dispatch case),
(b) an explicit no-fix classification (Rounds 1/4/6/7/9/13 in the evidence session dispatched a
full hardening round solely to FIFO-ack ledger debt with nothing to fix).

**What was implemented:** `lazy_core.ack_deny_by_selector(selector, resolution)` — a new function
in `user/scripts/lazy_core.py`, wired as `--ack-deny <selector> --resolution <text>` on both
`lazy-state.py` and `bug-state.py` (coupled-pair mirror). It:
- Retires ONE unacked entry (`selector="oldest"` FIFO, or a `denied_sha12` value/prefix), gated by
  `refuse_if_cycle_active("--ack-deny")` at the CLI layer — **never reachable from a cycle
  subagent**, exactly like `--backfill-receipts`/`--link-provenance`.
- REQUIRES a non-empty `resolution` audit note, recorded on the acked entry with
  `ack_method: "manual-ack"` (distinct from the hardening-round `ack_oldest_deny()` path's implicit
  ack, so a retro can tell the two apart and grade abuse).
- Same-cause dedup (Fix Scope §2): every OTHER unacked entry sharing the same cause key
  (`_deny_entry_same_cause_key` — identical `denied_sha12`, or identical `kind`+`reason_head` as a
  fallback for entries with no sha, e.g. `process-friction`) is acked in the SAME call with
  `ack_method: "manual-ack-dedup"`, so one oscillating cause never costs more than one unit of
  retirement effort.

This is a real, load-bearing relaxation of locked decision 4 for exactly the two named classes —
it does NOT touch the hardening-dispatch ack path (`ack_oldest_deny`, still called only from
`lazy_guard.py`'s `_ack_if_hardening` on a hardening-class guard-allow) or the operator-blanket
override (`ack_all_unacked_denies`, still reachable only via `--run-end --ack-unhardened`).

**This session's choice:** implement per the SPEC's own recommended Fix Scope (there is no
competing option offered — the SPEC states the mechanism to build, only flagging that it conflicts
with a locked decision elsewhere). **Rationale:** the SPEC is `Concluded` (root cause proven, Fix
Scope fully specified) and the conflict is explicitly framed as "needs sign-off before
`/plan-bug`", not "pick between two designs" — there is one design to ratify, not a fork to
resolve. Building it and parking the ratification (rather than skipping the whole bug) preserves
the evidence (a real, tested implementation) for the operator to accept or reject, instead of
leaving the friction unaddressed pending a scheduling slot.

**Abuse guard-rail already in place (per the SPEC's own requirement):** the op is orchestrator-only
(cycle subagents refused exit 3, zero side effects) and every ack — cheap or dedup — carries an
audited `resolution` string plus `ack_method` discriminator, so `/lazy-batch-retro` can grade
whether `--ack-deny` was used honestly (cheap/no-fix/dedup) vs. as a blanket escape hatch.

### 2. D2: ack selector shape (fix-planning, mechanical — resolved without operator input)

The SPEC flagged this as "mechanical-internal; resolve at `/plan-bug`" (FIFO-oldest vs
`denied_sha12`-addressed vs interactive listing). Implemented **both** `"oldest"` (FIFO, mirroring
`ack_oldest_deny`'s existing default ordering) and a `denied_sha12` value/prefix (addressed ack) —
the two lowest-friction forms from the SPEC's own list, no interactive listing (out of scope for a
non-interactive CLI). This is a mechanical choice with no locked-decision conflict; recorded here
for completeness, not for ratification.

## Resolution

Not yet ratified. This file documents the provisional choice (D1); the bug's `SPEC.md` **Status**
stays `Concluded` (not `Fixed`) and the directory is **not archived** until an operator reviews and
either ratifies the relaxation as implemented or redirects (e.g. narrower eligibility, a stricter
audit requirement, or rejecting the relaxation and reverting to inline-unbounded-only). The
implementation (`lazy_core.ack_deny_by_selector`, the `--ack-deny`/`--resolution` CLI on both state
scripts, the `_deny_entry_same_cause_key` dedup, and the `DISPATCH_CLASSES` round-trip regression
guard for Half 1) is complete, TDD-covered in `test_lazy_core.py`, and does not depend on this
ratification to be correct code — only the bug's own completion bookkeeping (Status/archive) is
gated on it.

# __mark_complete__ partial-apply crash window with an unrecoverable receipt-only noop — Investigation Spec

> `apply_pseudo`'s `__mark_complete__`/`__mark_fixed__` branch performs a multi-file write
> sequence (receipt → SPEC flip → PHASES flip → sentinel cleanup → queue trim → ROADMAP strike)
> where each write is individually atomic but the SEQUENCE is not — and the branch-entry
> idempotency check noops on RECEIPT-EXISTS ALONE. A kill between the receipt write and the
> status flip leaves receipt-present + `Status: In-progress`; every re-invocation noops with
> zero writes, the walk re-routes to mark-complete forever, and no code path can ever repair it.

**Status:** Concluded
**Priority:** P1
**Last updated:** 2026-07-11
**Related:** `docs/features/completion-coherence-gate-reconciliation/` (Complete — reconciled the completion gate's REFUSAL rule and made each individual write atomic; it deliberately did not address sequence-level crash-consistency, which is this bug — no fix-scope overlap, see Root Cause); `docs/bugs/production-sentinel-writes-bypass-atomic-write/` + `docs/bugs/coord-lock-no-stale-reclaim/` (siblings — shared theme: crash-consistency of script-owned state); `docs/features/CLAUDE.md` (the receipt-gate contract this bug is the blind inverse of); `user/scripts/CLAUDE.md` (atomic-write contract).

## Verified Defect

**Code-proven, not field-observed** — no run has yet been caught in this state; the causal
trace below is a line-level read of the live tree (2026-07-11, uncommitted working copy — line
numbers cited are what the current file actually shows).

The `__mark_complete__` / `__mark_fixed__` branch of `apply_pseudo`
(`user/scripts/lazy_core.py:4696`) executes this write sequence:

| Order | Write | Line | Individually atomic? |
|-------|-------|------|----------------------|
| 1 | Evidence-gated auto-tick of verification rows | `autotick_verification_rows` call @ ~4822 | yes (`_atomic_write` per its contract) |
| 2 | Auto-flip all-ticked phase `**Status:**` lines in PHASES.md | `_atomic_write` @ 4927 | yes |
| 3 | **COMPLETED.md / FIXED.md receipt** | `write_completed_receipt` @ 4956–4968 | yes |
| 4 | Intervention capture (fail-open) | `record_intervention` @ ~4990 | yes |
| 5 | SPEC.md top `**Status:**` → Complete/Fixed | `_atomic_write` @ 5017 | yes |
| 6 | PHASES.md top `**Status:**` → Complete/Fixed | `_atomic_write` @ 5027 | yes |
| 7 | Delete VALIDATED.md / RETRO_DONE.md / DEFERRED_NON_CLOUD.md | `unlink` @ 5034–5038 | n/a |
| 8 | Trim entry from docs/features/queue.json (feature path) | `_atomic_write` @ 5105 | yes |
| 9 | Strike ROADMAP row (feature path) | `_strike_roadmap_row` @ 5136 | yes |
| 10 | Provenance ledger (fail-open) | `write_provenance` @ ~5174 | yes |

The idempotency check at branch entry (`lazy_core.py:4746–4753`) is:

```python
receipt_path = spec_path / receipt_filename
existing_receipt = parse_sentinel(receipt_path)
if existing_receipt is not None and existing_receipt.get("kind") == receipt_kind:
    return _noop()
```

It verifies the receipt ALONE — none of the post-conditions of steps 5–9 — and it returns
before any of them could be re-applied.

**The crash window.** A `KeyboardInterrupt` / `SIGKILL` / power loss between step 3 (receipt
written) and step 5 (SPEC flip) leaves on disk: `COMPLETED.md` present, `**Status:**
In-progress`, `VALIDATED.md` still present (deleted only at step 7), queue entry present,
ROADMAP unstruck. Nothing in the branch catches this — the only try/except in the sequence
(intervention capture, 4982–4998) catches `Exception`, which `KeyboardInterrupt`/`SystemExit`
are not, and `SIGKILL`/power-loss need no exception path at all.

**The unrecoverable loop.** On the next probe, `lazy-state.py`'s queue walk:

1. The receipt gate at `lazy-state.py:1861–1886` fires only when completion is CLAIMED
   (`completion_claimed(...)` — ROADMAP struck / SPEC Complete). Here the Status is still
   In-progress and the ROADMAP is unstruck → not claimed → the walk continues normally.
2. Phases are complete and `VALIDATED.md` is present → Step 10 routes
   `sub_skill: __mark_complete__` (`lazy-state.py:3650–3657`).
3. `apply_pseudo` hits the receipt-only noop at `lazy_core.py:4752` → `_noop()`, ZERO writes.
4. Disk state is byte-identical to before → the next probe computes the identical route.

No path repairs the state. At best the WU-4 repeat-streak detector eventually surfaces a
loop halt for the operator; the pipeline itself is dead on this item until a human hand-edits
the files.

**The contract blind spot.** `docs/features/CLAUDE.md` (~line 29–31, mirrored in AlgoBooth's
`docs/features/CLAUDE.md` §"Completion is receipt-gated") states: "**A `Complete` status with
no receipt is a hard error**" — and `lazy-state.py` enforces exactly that direction
(`terminal_reason="completion-unverified"`, lines 1868–1886). The INVERSE — receipt with no
Complete status, which is precisely what the crash window produces — is handled nowhere.

**Same pattern in the bug pipeline.** `__mark_fixed__` shares the identical branch (same
idempotency check at 4752, on `FIXED.md`), so the same window exists between the FIXED.md
receipt and the SPEC flip. Notably, the FOLLOW-ON step `archive_fixed`
(`lazy_core.py:6126`) already demonstrates the correct posture: its step-1 gate detects a
prior partial run (`spec_path` gone + archive dest exists → `resume = True`, lines
6210–6215) and resumes from where the previous run died — the in-file precedent for
resume-not-noop that the receipt branch lacks.

## Root Cause

**Classification: `incomplete-idempotency-key` (partial-apply crash window).** The branch
treats "receipt exists" as equivalent to "completion fully applied", but the receipt is
written FIRST among the externally-observable post-conditions the state machine routes on.
The noop check therefore keys on the one artifact guaranteed to exist in every partial
state, and returns before the remaining post-conditions (SPEC/PHASES status, sentinel
cleanup, queue trim, ROADMAP strike) are verified or re-applied. Each write being
individually `_atomic_write`-safe is irrelevant: the failure mode is sequence-level, and
the repo has no transactional/journal mechanism for multi-file completions.

Why `completion-coherence-gate-reconciliation` does not cover this: that feature (SPEC
Status: Complete, 2026-06-19) reconciled the gate's refusal RULE (verification-row
carve-out, evidence-gated auto-tick) and mandated per-write atomicity for the tick rewrite.
Its scope ends at "the gate stops wrongly refusing"; it never touched what happens when the
already-authorized sequence dies midway. This bug is the complementary gap — cross-linked,
zero fix-scope overlap.

## Fix Scope (Concluded)

Resume-not-noop: the idempotency check verifies ALL post-conditions and re-applies the
missing tail.

1. **Replace the receipt-only noop (`lazy_core.py:4746–4753`)** with a post-condition audit:
   receipt present + correct kind AND SPEC `**Status:**` == terminal value AND PHASES top
   `**Status:**` == terminal value AND cleanup sentinels absent AND (feature path) queue
   entry absent + ROADMAP row struck. All hold → `_noop()` (today's behavior, preserved for
   genuinely-done dirs, including the documented "re-completing must never re-refuse" rule —
   the audit runs BEFORE the retro-staleness/provisional/coherence gates exactly where the
   noop sits today).
2. **Partial state → RESUME:** receipt present but any post-condition missing → skip the
   receipt write (and intervention capture, which is guarded by its own record-exists noop)
   and re-execute only steps 5–10, which are already individually idempotent (regex `count=1`
   status sub, exists-checks, no-op trims/strikes). Surface `resumed: true` +
   the re-applied artifacts in the result dict so the orchestrator can see the recovery.
3. **Both pipelines:** the shared branch fixes `__mark_fixed__` for free; add a
   `__mark_fixed__` resume case mirroring `archive_fixed`'s existing resume posture.
4. **Kill-between-writes test in `user/scripts/test_lazy_core.py`:** fixture that
   materializes the exact crash state (receipt written, Status In-progress, VALIDATED.md
   present, queue entry present), asserts (a) pre-fix behavior would noop (regression
   documentation), (b) post-fix `apply_pseudo` resumes and converges to the fully-applied
   state, (c) a second invocation is then a clean noop. Plus a walk-level assertion that
   `lazy-state.py` no longer computes the same Step-10 route twice against the repaired dir.
5. **Doc sync:** `docs/features/CLAUDE.md` receipt-gate paragraph gains the inverse rule
   ("a receipt with a non-terminal Status is a resumable partial completion, repaired by
   re-running `__mark_complete__`"), and `user/scripts/CLAUDE.md`'s high-signal invariants
   note the sequence-resume contract.

## Decisions

- **D1 — Resume vs refuse-loudly:** RESUME (auto-repair). The partial state is
  unambiguous (the gate already authorized the completion once; all evidence was verified
  pre-receipt), and every tail step is idempotent — refusing would trade a silent loop for
  a halt that still needs the same mechanical repair. Matches the `archive_fixed` precedent
  and the completeness-first operator policy.
- **D2 — No journal/transaction layer:** rejected as over-engineering. The post-condition
  audit + idempotent tail re-apply achieves convergence without a new persistence format;
  a journal would itself need crash-consistency.
- **D3 — Ordering unchanged:** receipt-first write order is kept (the receipt is the
  integrity gate's proof-of-authorization; flipping status first would recreate the
  `completion-unverified` hard-error state on crash, which halts the pipeline loudly but
  wrongly). The fix makes the existing order safe instead of reshuffling it.

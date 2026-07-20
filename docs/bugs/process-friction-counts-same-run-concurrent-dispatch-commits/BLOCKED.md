---
kind: blocked
blocker_kind: operator-design-decision-pending
blocked_by: operator
written_by: lazy-bug-batch
---

# BLOCKED — process-friction-counts-same-run-concurrent-dispatch-commits

The fix for this bug requires an operator **design decision** that is currently parked, so it
cannot be planned/implemented autonomously.

**The design fork (from `/harden-harness` Round 111, hard-park):** the `--cycle-end`
process-friction `unexpected-commits` detector charges a cycle's commit budget with commits made
by **same-run concurrent dispatches** (background hardens, reconcile/archive/provenance ops)
because `_count_concurrent_writer_commits` (`user/scripts/lazy_core/markers.py`) attributes
concurrent commits only by a **distinct committer-email** OR a **distinct-run-identity** ledger
sha — same-run concurrent writers share this box's single git identity AND the live run marker's
`started_at`, so both attribution arms return 0 and the concurrent commits are charged to the
cycle (observed live this run: cycle 14 charged 11 window commits vs a budget of 7; 8 were
sanctioned same-run concurrent writers). Fixing it **forks the detector's core integrity
measurement with false-NEGATIVE stakes** — a wrong choice could mask a genuine runaway — which is
why the harden hard-parked rather than self-implementing.

**Full operator surfacing (canonical):**
`docs/specs/turn-routing-enforcement/NEEDS_INPUT_2026-07-19-process-friction-same-run-concurrent-dispatch-attribution.md`

**Options:**
- **Option A (harden-recommended):** per-commit **cycle-nonce attribution** feeding a
  purely-additive third arm — measures the cycle's OWN commits vs the pollutable
  `begin_head_sha..HEAD` window proxy; never masks a runaway.
- **Option B:** cap by `commit_tally` — rejected by the harden as coverage-reducing (removes the
  window's unique hook-bypassed-runaway catch).
- Widening the budget — rejected as gate-weakening (Prohibition #2).

**Resolution:** operator picks the attribution approach; this bug then routes to `/plan-bug` with
the chosen design. Parked (`--park`) pending that decision; surfaced at the run-end flush.

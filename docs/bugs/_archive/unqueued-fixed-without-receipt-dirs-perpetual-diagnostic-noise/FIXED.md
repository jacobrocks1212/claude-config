---
kind: fixed
feature_id: unqueued-fixed-without-receipt-dirs-perpetual-diagnostic-noise
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

unqueued-fixed-without-receipt-dirs-perpetual-diagnostic-noise marked fixed on 2026-07-12, closed
as **fixed-by-sweep**: this bug's entire prescribed Fix Scope (run `--backfill-receipts`, commit
the receipts, no code change, no signal suppression) was already carried out by the
`fixed-bugs-unarchived-fsck` reconciliation sweep (commit `efaf93b3`) before this bug's own pickup
in this session. This receipt was written by the session directly, not the pipeline's
`__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`.

## Notes

Re-verified 2026-07-12: all 7 dirs the SPEC names are archived + receipted (`FIXED.md` present,
sitting under `docs/bugs/_archive/`); `python3 user/scripts/bug-state.py --backfill-receipts
--repo-root .` reports `{"backfilled": [], "count": 0}` — no remaining debt of this class. No code
change was needed or made in this pass; the diagnostic itself (`_find_open_bug_dirs`'s honest
completion-integrity signal) is fully intact and unsuppressed for any future Fixed-without-receipt
dir, exactly as the SPEC's own reasoning requires.

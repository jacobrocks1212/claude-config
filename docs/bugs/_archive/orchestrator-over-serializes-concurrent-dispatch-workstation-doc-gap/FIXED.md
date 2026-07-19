---
kind: fixed
feature_id: orchestrator-over-serializes-concurrent-dispatch-workstation-doc-gap
date: 2026-07-19
provenance: backfilled-unverified
validated_via: doc-only change (workspace CLAUDE.md subsection) — grep-confirmed the subsection lands and cross-references the global policy; NOT pipeline-gated
auto_ticked_rows: 0
---

# Fixed

`orchestrator-over-serializes-concurrent-dispatch-workstation-doc-gap` marked Fixed on
2026-07-19 by a dispatched `/harden-harness` round (observed-friction trigger, Round 106).
Fixed OUT-OF-PIPELINE via a `harden(...)` commit, not the bug pipeline's gated `__mark_fixed__`
path — provenance is deliberately `backfilled-unverified`.

## What shipped

A tight `### Concurrent-writer coordination` subsection was added to
`workspace/CLAUDE.DESKTOP-GHTC5K6.md` (the DESKTOP-GHTC5K6 machine-keyed workspace doc,
projected to `~/source/repos/CLAUDE.md` on this box), recording durably that:

1. This shared claude-config worktree is multi-writer-safe via the shipped
   `concurrent-worktree-agent-coordination` feature (FIFO per-item file-lock `lazy_coord.py` /
   `concurrent-lock-contract.md` + git-safety + conflict-routing `lazy_core.py`); it serializes
   genuine contention and halts only on a true SEMANTIC conflict.
2. The orchestrator must NOT pre-serialize / delay a dispatch on the mere possibility of write
   contention — dispatch concurrently, a moved HEAD / incoming commit is EXPECTED. Cross-references
   the user-global `<orchestration>` "Concurrent-writer awareness" block + `/lazy-batch` HARD
   CONSTRAINT 11 rather than duplicating them.
3. The one real caveat: no competing `--cycle-begin` bracket against the single-slot
   `~/.claude/state/lazy-cycle-active.json` marker — dispatch the concurrent worker via the
   registered emit-dispatch path instead.

## Verification

- Fix commit `2e841b17` (pushed to origin/main `11188076..2e841b17`); investigation-spec commit
  `08bcfbdf` (committed FIRST, `harden(docs):`).
- Full gate battery green over the merged (concurrent-writer) tree: pytest `tests/test_lazy_core/`
  1300/1300; `test_hooks.py` 289/289; `lazy-state.py --test` / `bug-state.py --test` all smoke
  passing; `lint-skills.py --check-projected --check-capabilities` OK; `bug-state.py --fsck` clean.
- `harness-gate.py`: `gate_weakening: false`; my own two-commit diff (`workspace/…` + this
  `SPEC.md`) touches ZERO control surfaces (`in_scope: false` scoped to my paths) — the earlier
  `overfit: flag` was pollution from a concurrent lane's control-surface files in the interleaved
  range.

## Reconciliation handback

A cycle marker for the concurrent execute-plan run is active, so `--archive-fixed` /
`--link-provenance` are orchestrator-only (refused for a subagent). This receipt + the
`**Status:** → Fixed` flip are cycle-safe; the two orchestrator-only ops are handed back to the
harden-return seam:

```
python3 user/scripts/bug-state.py --repo-root . --archive-fixed docs/bugs/orchestrator-over-serializes-concurrent-dispatch-workstation-doc-gap
python3 user/scripts/lazy-state.py --link-provenance --id orchestrator-over-serializes-concurrent-dispatch-workstation-doc-gap --commits 2e841b17
```

---
kind: fixed
feature_id: lazy-batch-parallel-run-harness-gaps-round-2
date: 2026-07-18
provenance: backfilled-unverified
fixed_commit: 719ec339
validated_via: lazy_coord.py --test (Fixture 22 has-live-lease-predicate) + test_dispatch.py subprocess serial-tail lease-held/negative-control (4/4 isolated) + lazy-state.py/bug-state.py --test + lazy_parity_audit.py exit 0; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`lazy-batch-parallel-run-harness-gaps-round-2` marked Fixed on 2026-07-18 by a dispatched
`/harden-harness` round (hardening-log Round 94). This receipt was written by the harden subagent,
not the bug pipeline's `__mark_fixed__` gate — provenance is `backfilled-unverified`.

## Notes

Both gaps fixed in commit `719ec339` (bug spec `33e301e4`):

- **Gap 8 (script-defect, RUN-BLOCKING).** Added `lazy_coord.has_live_lease()` (factors out
  `claim_shardable`'s liveness predicate) and exempted the `--emit-prompt` merged-head divergence
  guard when the probed `feature_id` itself holds a live coordinator lease — the analog of the
  round-85 lane exemption, for the post-merge serial-tail case at the main root (parent marker,
  `parent_run: null`). Mirrored into `bug-state.py` (coupled pair). Fail-safe and byte-identical
  for every serial run without a `leases.json`.

- **Gap 9 (missing-contract).** Documented the FOREGROUND-ONLY contract for `--ensure-runtime`
  (`user/scripts/CLAUDE.md` + `lazy-batch-parallel/SKILL.md` serial-tail step) — the
  evidence-sanctioned resolution, since the root cause hinges on target-repo `kill-dev.js`
  (out of claude-config scope) and undocumented Claude Code `run_in_background` lifecycle.

Regression coverage: `lazy_coord` Fixture 22; `test_dispatch.py` serial-tail lease-held
no-withhold + negative control (no lease → still withholds). `--archive-fixed` +
`--link-provenance` are handed back to the orchestrator (Round 94 Reconciliation) — this receipt
satisfies the `--archive-fixed` precondition.

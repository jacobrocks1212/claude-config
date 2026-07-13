---
kind: fixed
feature_id: fixed-bugs-unarchived-fsck
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: bug-state.py --test smoke harness + live --fsck run against this repo
auto_ticked_rows: 0
---

# Completion Receipt

fixed-bugs-unarchived-fsck marked fixed on 2026-07-12 by an operator-directed interactive subagent
session. This receipt was written by the session directly, not the pipeline's `__mark_fixed__`
gate — provenance is deliberately `operator-directed-interactive`.

## Notes

Both halves of the SPEC's Fix Scope are done:

1. **Reconciliation sweep (Fix Scope §1–§2):** landed in a PRIOR session (commit `efaf93b3`,
   "archive 20 Fixed+receipted bug dirs, drop 3 stale queue rows"), re-verified this pass — all 13
   receipted dirs + all 5 `subagent-baseline-*` dirs (backfilled per D1) are archived, and the 3
   stale `queue.json` rows are gone.
2. **`bug-state.py --fsck` (Fix Scope §3):** new read-only lint mode asserting the three archive-
   on-fix invariants (`unarchived-fixed`, `fixed-without-receipt`, `stale-queue-entry`), wired as
   `--fsck` on `bug-state.py`, TDD-covered in the in-file smoke harness (`fsck-violations` +
   `fsck-clean-tree` fixtures). `docs/bugs/CLAUDE.md` gained a "Fixing a bug OUT-OF-PIPELINE"
   contract section (the STATE-lane half of Fix Scope §4).

Live confirmation: `python user/scripts/bug-state.py --repo-root . --fsck` on the real claude-config
tree returns `{"ok": true, "violations": []}` — the reconciliation sweep left the tree clean, and
the new checker certifies it.

**Deferred (out of the STATE lane, explicitly):** the `user/skills/harden-harness/SKILL.md` prose
half of Fix Scope §4 (telling a harden-harness session to run `--archive-fixed` or leave `Status`
untouched) is `user/skills/**` — this session's assignment excludes it. The mechanical enforcement
(`--fsck` itself, callable standalone/at `--run-end`/from a future CI lane) does not depend on that
prose update to be effective.

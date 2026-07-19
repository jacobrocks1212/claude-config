---
kind: fixed
feature_id: subagent-wedge-backstop-dirty-tree-predicate-repo-wide
date: 2026-07-19
provenance: backfilled-unverified
---

# Completion Receipt

Fixed OUT-OF-PIPELINE via harden Round 107 (a `harden(hook):` commit, not the bug
pipeline's gated `__mark_fixed__` path), so this receipt is `backfilled-unverified`
(hook fix, no MCP surface).

**Fix commit:** `4a12e218` — `subagent-wedge-backstop.sh` replaces the whole-tree
`_git_dirty(repo_root)` read with `_own_work_dirty(repo_root, own_item_dir)`: a dirty
path under `docs/` that is NOT under the active cycle's own pipeline-item dir (derived
from the cycle marker's execute-plan plan path) is treated as concurrent-lane residue
and ignored; non-`docs/` (source) dirt and the cycle's own item dir still count. Fail-OPEN
posture and block-at-most-once loop-guard preserved.

**Regression evidence (green):** `test_hooks.py` 280/280 (3 new `test_wedge_*`:
foreign-residue-only → allow; own-source dirt → block; own-item-dir dirt → block).
Full gates: `test_lazy_core` 1300 passed, `lazy-state.py --test` / `bug-state.py --test`
OK, `lint-skills.py` OK.

Spec: this dir's `SPEC.md` (Status → Fixed). Origin: harden Round 107,
`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`.

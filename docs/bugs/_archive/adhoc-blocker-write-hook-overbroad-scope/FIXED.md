---
kind: fixed
feature_id: adhoc-blocker-write-hook-overbroad-scope
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (user/scripts/test_hooks.py)
auto_ticked_rows: 0
---

# Completion Receipt

adhoc-blocker-write-hook-overbroad-scope marked fixed on 2026-07-12 via direct HOOKS-lane
operator-directed session work — a same-session investigation + fix (SPEC authored and Concluded,
then immediately fixed, in one pass) for a small defect observed by another lane. This receipt was
written directly, not by the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`, matching `docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

## Notes

**Symptom-reproduction (red→green):** `test_noncanonical_allows_blocker_shaped_name_outside_docs_scope`
reproduces the observed real-world false positive
(`user/skills/_components/blocked-resolution.md` denied purely on basename shape) plus two more
out-of-scope blocker-shaped paths, confirmed RED against the pre-fix hook (no directory scoping
anywhere in `main()`) before landing the `_SENTINEL_SCOPE_RE` path-scope check. The load-bearing
in-scope case is pinned by `test_noncanonical_denies_misnamed_blocker_under_docs_features`
(`docs/features/x/BLOCKED_foo.md` still denies) — no regression.

**Gates:** `python -m pytest user/scripts/test_hooks.py -q` → 206 passed (baseline 204 after the
prior bug's phase + 2 from this bug).

**Files touched:** `user/hooks/block-noncanonical-blocker-write.sh`, `user/scripts/test_hooks.py`,
`docs/bugs/adhoc-blocker-write-hook-overbroad-scope/SPEC.md` (authored this session).

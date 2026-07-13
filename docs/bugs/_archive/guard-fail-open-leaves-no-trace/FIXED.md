---
kind: fixed
feature_id: guard-fail-open-leaves-no-trace
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (user/scripts/test_hooks.py)
auto_ticked_rows: 0
---

# Completion Receipt

guard-fail-open-leaves-no-trace marked fixed on 2026-07-12 via direct HOOKS-lane operator-directed
session work (a bug-fix subagent scoped to `user/hooks/*.sh` + `user/scripts/test_hooks.py`). This
receipt was written by the subagent, not the pipeline's `__mark_fixed__` gate — provenance is
deliberately `operator-directed-interactive`, matching
`docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

## Notes

**Symptom-reproduction (red→green):** every fix in this bug is proven by a subprocess pipe test
against the live hook, not narrative claim:
- No-python fail-open path (symptoms a/b): confirmed RED via ad-hoc manual subprocess pipes
  (`PATH=""` through the properly-resolved Git Bash exe) BEFORE landing
  `test_all_python_bearing_hooks_breadcrumb_on_no_python` and
  `test_containment_no_python_breadcrumb_lands_in_override_dir_not_root` — both GREEN after the
  fix, across all 7 python-bearing hooks.
- Sentinel-pair catch-all (symptom c): confirmed RED via the malformed-JSON pipe leg before landing
  `test_noncanonical_catch_all_writes_breadcrumb_and_event` /
  `test_straybranch_catch_all_writes_breadcrumb_and_event` — GREEN after the fix.

**Fix Scope items 1, 2, 3, 6 (SPEC) — implemented, GREEN.** Items 4 (fail-open heartbeat /
dead-plane alarm) and 5 (hook-timeout-kill tracing) are **descoped residuals**, documented in
`PHASES.md` Phase 1's Decision note and in `user/hooks/CLAUDE.md`'s Fail-OPEN section:
- Item 4 needs a STATE-lane script change (`lazy-state.py --probe` or `lazy_inject.py`) outside
  this fix's HOOKS-lane scope; after this fix, `incident-scan.py` is no longer blind to a dead
  guard plane (both `hook-error.json` and `hook-events.jsonl` are now written on every no-python
  path), so the heartbeat is an additional real-time alarm, not required to close the SPEC's
  verified symptoms.
- Item 5 is gated on the SPEC's own "UNVERIFIED — flagged" symptom (e), which would require staging
  a deliberately slow hook against the live 5s harness timeout — outside what a pipe-test
  subprocess can exercise. Documented as a known limitation per the SPEC's own D3 fallback.

**Gates:** `python -m pytest user/scripts/test_hooks.py -q` → 203 passed (baseline 199 + 4 from
this bug). `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0 (root `CLAUDE.md`
Hooks-table rows reconciled where materially changed).

**Files touched:** `user/hooks/lazy-cycle-containment.sh`,
`user/hooks/block-noncanonical-blocker-write.sh`,
`user/hooks/block-sentinel-write-on-stray-branch.sh`, `user/hooks/long-build-ownership-guard.sh`,
`user/hooks/build-queue-enforce.sh`, `user/hooks/lazy-dispatch-guard.sh`,
`user/hooks/lazy-route-inject.sh`, `user/scripts/test_hooks.py`, `user/hooks/CLAUDE.md`.

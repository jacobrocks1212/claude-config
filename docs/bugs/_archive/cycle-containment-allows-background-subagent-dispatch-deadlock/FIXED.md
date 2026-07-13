---
kind: fixed
feature_id: cycle-containment-allows-background-subagent-dispatch-deadlock
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (user/scripts/test_hooks.py)
auto_ticked_rows: 0
---

# Completion Receipt

cycle-containment-allows-background-subagent-dispatch-deadlock marked fixed on 2026-07-12/13 by a
direct HOOKS-lane operator-directed session (a bug-fix subagent scoped to `user/hooks/*.sh` +
`user/scripts/test_hooks.py`). This receipt was written by the subagent, not the pipeline's
`__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`, matching
`docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

## Notes

**Fully implemented in a prior session this same evening (commit `a43808ee`,
"harden(hook): deny background sub-subagent dispatch from cycle subagents").** The fix landed
during the same live `/lazy-bug-batch` run whose deadlock the SPEC's "Verified Symptom" describes
first-hand — the containment hook's own operator dispatched the mechanical fix in-run rather than
waiting for a separate bug-pipeline cycle. This receipt records the terminal state confirmed on
disk this session; no code changed in this pass.

**Symptom-reproduction (red→green), reconfirmed this session:**
- `python -m pytest user/scripts/test_hooks.py -k "background_subagent or foreground_subagent or main_thread_background" -q`
  → **3 passed** (`test_containment_denies_background_subagent_dispatch`,
  `test_containment_allows_foreground_subagent_dispatch`,
  `test_containment_allows_main_thread_background_dispatch`).
- Full suite: `python -m pytest user/scripts/test_hooks.py -q` → **217 passed**.
- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0 (5 checks, 0 drift findings, 2
  pre-existing exempted divergences unrelated to this bug).

**Fix Scope items, all verified present on disk:**
- `_is_truthy_background()` helper and the subagent+background deny branch in
  `user/hooks/lazy-cycle-containment.sh` (`:443`, `:571-572`), with the corrective reason text at
  `:187-199` directing re-dispatch without `run_in_background`.
- Foreground subagent dispatch stays allowed (2026-07-09 Explore-fan-out carve-out preserved,
  regression-guarded by its own test).
- Main-thread background dispatch stays allowed (deny keys on `agent_id`, not the background flag
  alone).

No residuals. The deadlock class (background sub-subagent dispatch from a contained cycle
subagent) is mechanically unreachable; the prose-only synchronous-await contract is now
hook-enforced.

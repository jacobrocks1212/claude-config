---
kind: fixed
feature_id: dispatch-guard-denies-workstation-subsubagent-split
date: 2026-07-10
provenance: operator-directed-interactive
validated_via: pipe-tests (user/scripts/test_hooks.py); unit tests (user/scripts/test_lazy_core.py, not re-run this pass — STATE lane)
auto_ticked_rows: 0
---

# Completion Receipt

dispatch-guard-denies-workstation-subsubagent-split marked fixed on 2026-07-10 (fix landed same
day as discovery, commit `821896b2`) via direct operator resolution of `turn-routing-enforcement`
decision 4, confirmed and receipted retroactively in this HOOKS-lane session
(2026-07-12/13, `user/hooks/*.sh` + `user/scripts/test_hooks.py` scope). This receipt was written
by the subagent, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`, matching `docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

## Notes

**Fully implemented at discovery time** — the SPEC's own "Resolution (2026-07-10 — operator
decision + fix shipped)" section documents the shipped predicate (`lazy_guard.py` `guard()` branch
2b: workstation-only, bound marker, skill-declared `subagent_model` capability, consumed fence) in
full, citing "Full suites green: test_lazy_core 939/939, test_hooks 149/149" at landing time. The
gap this pass closes is purely a **missing receipt** — `Status` was left at `Concluded` (not
`Fixed`) with no `PHASES.md`/`FIXED.md`, even though the Resolution reads as a completed fix. No
code changed in this pass.

**Symptom-reproduction (red→green), reconfirmed this session:**
- `python -m pytest user/scripts/test_hooks.py -k "worker_subdispatch" -q` → **6 passed**
  (`test_guard_worker_subdispatch_exemption_allows`,
  `test_guard_worker_subdispatch_denied_before_consume`,
  `test_guard_worker_subdispatch_denied_without_capability`,
  `test_guard_worker_subdispatch_denied_on_cloud`,
  `test_guard_worker_subdispatch_denied_unbound_marker`,
  `test_guard_worker_subdispatch_exemption_allows_fresh_cycle_nonce`).
- Full HOOKS-lane suite: `python -m pytest user/scripts/test_hooks.py -q` → **217 passed**.
- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0.
- `test_lazy_core.py` (STATE lane, active elsewhere this session) **not independently re-run** —
  relying on the SPEC's own landing-time citation (939/939) rather than touching files another
  lane owns mid-session.

**Fix Scope items, verified present on disk this pass:**
- `lazy_guard.py` branch 2b (workstation + bound-marker + `subagent_model` + consumed-fence
  predicate), `subagent_model`/`skill_declares_subagent_model`/`worker_subdispatch` markers present
  at the cited region.
- Cloud path (`lazy-batch-cloud`) unaffected — the fix is workstation-scoped by construction
  (branch 2b's first predicate).

No residuals in the HOOKS-lane slice of this fix. Decision 4 in
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` is resolved; the FIFO no-op hardening drain
(Rounds 9-13) this bug diagnosed is eliminated at the source.

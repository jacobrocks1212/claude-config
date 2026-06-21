# Stale TestStateScriptParity fixtures fail after newer coupled-pair parity assertions added — Investigation Spec

> `test_lazy_parity.py::TestStateScriptParity`'s synthetic `tmp_path` stubs predate the `--reassert-owner` and `requires_host` fail-fast parity assertions added to `audit_state_script_parity`, so the audit returns extra findings the fixtures don't expect. Test-fixture-only; no production drift.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-20
**Fixed:** 2026-06-20
**Fix commit:** 7667072
**Placement:** docs/bugs/adhoc-stale-state-script-parity-test-fixtures
**Related:** `docs/bugs/single-slot-marker-ownership-race-disarms-owning-run` (added `--reassert-owner`); `host-capability-declaration-for-gated-features` (added the `requires_host:` fail-fast parity check); `docs/bugs/no-sanctioned-queue-reorder-command` (added `--reorder-queue`); `user/scripts/lazy_parity_audit.py::audit_state_script_parity`

---

## Verified Symptoms

1. **[VERIFIED]** `test_lazy_parity.py::TestStateScriptParity` has exactly 3 failing tests — `test_audit_state_script_parity_fires_when_binding_missing`, `_fires_when_reorder_queue_missing`, `_clean_when_both_bind` — reproduced via `pytest` (3 failed, 1 passed). The 4th test (`test_live_state_scripts_bind_active_repo`, real-repo) passes.
2. **[VERIFIED]** The load-bearing real-repo audit passes: `python user/scripts/lazy_parity_audit.py --repo-root .` exits 0 with no findings. The real `lazy-state.py`/`bug-state.py` carry all four parity surfaces. Only the unit-test fixtures are stale.
3. **[VERIFIED]** `git diff --stat HEAD~5` shows no production-code drift in the state scripts relevant to the failure; the failures are a consequence of new *audit assertions* landing without their fixtures being updated.

## Reproduction Steps

1. `cd C:\Users\Jacob\source\repos\claude-config`
2. `python -m pytest user/scripts/test_lazy_parity.py::TestStateScriptParity -q`
3. Observe: `3 failed, 1 passed`.

**Expected:** All 4 `TestStateScriptParity` tests pass (the real-repo gate already does).
**Actual:** The 3 synthetic-fixture tests fail — the clean-fixture test gets 4 extra findings; the fires-when-missing tests assert a stale expected set (`len == 1`) while the audit now emits more.
**Consistency:** Always (deterministic, hermetic `tmp_path` fixtures).

## Evidence Collected

### Source Code

`audit_state_script_parity(repo_root)` (`user/scripts/lazy_parity_audit.py:334`) now checks **four** coupled-pair surfaces per state script (`_STATE_SCRIPTS = ("lazy-state.py", "bug-state.py")`):

| # | Surface | Regex constant | Required token in a stub |
|---|---------|----------------|--------------------------|
| 1 | active-repo binding | `_ACTIVE_REPO_BINDING_RE` (`:299`) | `set_active_repo_root(args.repo_root)` (optionally `lazy_core.`-prefixed) |
| 2 | operator-only reorder | `_REORDER_QUEUE_RE` (`:305`) | `"--reorder-queue"` |
| 3 | orchestrator-only re-arm | `_REASSERT_OWNER_RE` (`:310`) | `"--reassert-owner"` |
| 4 | host-capability fail-fast | `_HOST_CAPABILITY_FAILFAST_RE` (`:328`) **AND** `_HOST_CAPABILITY_BLOCKER_KIND_RE` (`:331`) | `format_unknown_host_capability_blocker` AND `unknown-host-capability` |

Surfaces 3 and 4 were added by `single-slot-marker-ownership-race-disarms-owning-run` (Phase 2) and `host-capability-declaration-for-gated-features` (Phase 6) respectively, **after** the `TestStateScriptParity` fixtures were last written. The fixtures (`test_lazy_parity.py:638`–`702`) write minimal stubs that carry only surfaces 1+2.

### Git History

Recent commits (`git log --oneline -8`) show `host-capability-declaration-for-gated-features` landing immediately before this bug was enqueued (`48d5d30`, `e90960b` add the `requires_host` parity mirror + audit check). The ad-hoc brief (`4fbc3a8`) named only `--reassert-owner` as the new assertion because it was written before the host-capability surface landed — the actual staleness now spans surfaces 3 **and** 4.

### Related Documentation

`user/scripts/CLAUDE.md` documents both new surfaces and states `lazy_parity_audit.py::audit_state_script_parity` is the coupled-pair guard for each. No production change is warranted — the guard is correct; the fixtures lag it.

## Theories

### Theory 1: Stale fixtures — extra audit assertions, un-updated stubs
- **Hypothesis:** When surfaces 3 (`--reassert-owner`) and 4 (`requires_host` fail-fast) were added to `audit_state_script_parity`, the `TestStateScriptParity` `tmp_path` stubs were not updated to include the new tokens, so the clean-fixture stub now trips both new assertions and the fires-when-missing stubs assert a stale `len == 1`.
- **Supporting evidence:** Real-repo audit passes (exit 0). Failing assertion messages name exactly `--reassert-owner` and the `requires_host` fail-fast finding as the "extra" items. `_clean_when_both_bind` reports "4 more items" (= 2 scripts × 2 new surfaces).
- **Contradicting evidence:** None.
- **Status:** Confirmed.

## Proven Findings

- **Root cause CONFIRMED:** test-fixture staleness only. The audit logic and the real state scripts are correct; the three failing tests are synthetic-fixture tests whose stubs/expectations predate surfaces 3 and 4.
- **No production code change.** The fix is confined to `user/scripts/test_lazy_parity.py`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| parity-audit unit tests | `user/scripts/test_lazy_parity.py` (`TestStateScriptParity`, lines ~638–702) | 3 failing fixtures need updating |
| (reference, NOT changed) | `user/scripts/lazy_parity_audit.py::audit_state_script_parity` | Authoritative four-surface contract the fixtures must match |

## Fix Scope (for /plan-bug)

Update the three `TestStateScriptParity` `tmp_path` fixtures so their stub state scripts carry the full four-surface token set that `audit_state_script_parity` now requires:

- **`_clean_when_both_bind`** — both stub scripts (`lazy-state.py`, `bug-state.py`) must include all four surface tokens (binding + `"--reorder-queue"` + `"--reassert-owner"` + `format_unknown_host_capability_blocker` + `unknown-host-capability`) so the audit returns `[]`.
- **`_fires_when_binding_missing`** — both stubs carry surfaces 2+3+4; only `bug-state.py` drops the binding → assert exactly one finding naming the binding gap.
- **`_fires_when_reorder_queue_missing`** — both stubs carry surfaces 1+3+4; only `bug-state.py` drops `"--reorder-queue"` → assert exactly one finding naming `--reorder-queue`.
- Keep each fixture isolating exactly ONE missing surface (the others fully present) so each "fires-when-missing" test asserts `len == 1`.
- **Future-proofing note:** any subsequent coupled-pair surface added to `audit_state_script_parity` must update these stubs in lockstep. Consider noting this lockstep in the test class docstring (a one-time cross-reference to the audit's `_STATE_SCRIPTS` surface list).

## Open Questions

- None. Root cause proven; fix is mechanically determined by the audit's required-token set.

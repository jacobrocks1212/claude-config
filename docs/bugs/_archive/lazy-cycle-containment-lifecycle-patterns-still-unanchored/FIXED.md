---
kind: fixed
feature_id: lazy-cycle-containment-lifecycle-patterns-still-unanchored
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pipe-tests (user/scripts/test_hooks.py)
auto_ticked_rows: 0
---

# Completion Receipt

lazy-cycle-containment-lifecycle-patterns-still-unanchored marked fixed on 2026-07-12 via direct
HOOKS-lane operator-directed session work. This receipt was written directly, not by the
pipeline's `__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`,
matching `docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

## Notes

**Symptom-reproduction (red→green):** the SPEC's own Mechanical Reproduction table already proved
the false-positive at HEAD (both `git commit -m "...npm run dev:kill..."` and
`git commit -m "...kill-port 3333..."` denied). `test_containment_allows_lifecycle_reference_only_mention`
reproduces that exact finding as a pipe test and is GREEN after the anchoring fix
(`_LIFECYCLE_INVOKE_RE`, mirroring `_STATE_PY_INVOKE_RE`'s `_CMD_START` anchor). The two pre-existing
pinned deny tests (`test_containment_denies_lifecycle_commands`,
`test_containment_agentid_present_denies_lifecycle_no_marker`) stayed green UNMODIFIED — every real
lifecycle invocation (`npm run dev:kill`/`npm run dev:restart`/bare `dev:kill`/bare `dev:restart`/bare
`kill-port 3333`/bare `kill-port 1420`) still denies.

**Concurrent-edit reconciliation confirmed clean at fix time:** the sibling
`powershell-tool-bypasses-bash-matched-guards` round's `COMMAND_TOOL_NAMES`/`_normalize_ps_syntax`
additions (commit `302258cb`) do not touch `LIFECYCLE_PATTERNS` or its deny loop, exactly as the
SPEC predicted — no semantic conflict, straightforward textual coexistence.

**Gates:** `python -m pytest user/scripts/test_hooks.py -q` → 204 passed (baseline 203 after the
prior bug's phase + 1 from this bug).

**Files touched:** `user/hooks/lazy-cycle-containment.sh`, `user/scripts/test_hooks.py`.

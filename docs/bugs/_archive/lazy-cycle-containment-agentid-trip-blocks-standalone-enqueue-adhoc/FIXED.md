---
kind: fixed
feature_id: lazy-cycle-containment-agentid-trip-blocks-standalone-enqueue-adhoc
date: 2026-07-20
provenance: backfilled-unverified
validated_via: full regression suite green (0 failures, no new failures); 2 new pinned regression tests
auto_ticked_rows: 0
---

# Completion Receipt

Fix shipped in commit(s):
- 0bcc34c8 — harden(hook): scope --enqueue-adhoc's agent_id deny to a live run marker

Verification evidence:
- `python3 user/scripts/test_hooks.py` → 288/288 passed (was 286; +2 new pinned tests:
  `test_containment_agentid_present_allows_enqueue_adhoc_no_run_marker` RED-then-GREEN against
  the reported gap, `test_containment_agentid_present_denies_enqueue_adhoc_with_run_marker`
  proving the relaxation stays scoped to "no live run").
- `python3 -m pytest user/scripts/tests/test_lazy_core/ -q` → 1341/1341 passed, 0 failed.
- `python3 user/scripts/lazy-state.py --test` → all smoke tests passed.
- `python3 user/scripts/bug-state.py --test` → all smoke tests passed.
- `python3 user/scripts/bug-state.py --repo-root . --fsck` → `{"ok": true, "violations": []}`.
- `python3 user/scripts/lazy_parity_audit.py --repo-root .` → exit 0, clean.
- `python3 user/scripts/doc-drift-lint.py --repo-root .` → clean, 0 drift findings.
- `python3 user/scripts/lint-skill-config.py --repo-root .` → clean (pre-existing suppressed
  warnings only, unrelated to this change).
- `python3 ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` → OK.
- `python3 user/scripts/harness-gate.py --repo-root . --staged --json` → `gate_weakening: pass`;
  `overfit` flagged and justified in `GATE_VERDICT.md`; `complexity` declared net-new.

Manual live reproduction of the ORIGINAL symptom (pre-fix, 2026-07-20) confirmed the deny;
the two new pinned tests are the regression-test equivalent of re-running that reproduction
against the fixed hook (a live-session re-repro was not re-run post-fix — the pinned hermetic
tests exercise the exact PreToolUse payload shape the reproduction used).

Receipt + archive performed OUT-OF-PIPELINE per `docs/bugs/CLAUDE.md`'s "Fixing a bug
OUT-OF-PIPELINE" contract: this was a manual, direct `/harden-harness` invocation (no cycle
marker present — `lazy-state.py --marker-present --repo-root .` exits 1; inline reconciliation
path), not a `/lazy-bug-batch` cycle.

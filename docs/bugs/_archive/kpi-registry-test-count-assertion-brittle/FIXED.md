---
kind: fixed
feature_id: kpi-registry-test-count-assertion-brittle
date: 2026-07-20
provenance: backfilled-unverified
validated_via: full regression suite green (0 failures, no new failures)
auto_ticked_rows: 0
---

# Completion Receipt

Fix shipped in commit(s):
- 0b85cf3e — harden(test): stop hardcoding the KPI registry row count

Verification evidence:
- `python3 -m pytest user/scripts/test_kpi_scorecard.py -q` → 145/145 passed (was 1 failed,
  144 passed: `assert 26 == 25`).
- `python3 -m pytest user/scripts/ -q` → 2705/2705 passed, 0 failed (full suite, no
  regressions).
- `python3 user/scripts/test_hooks.py` → 286/286 passed.
- `python3 user/scripts/lazy-state.py --test` → all smoke tests passed.
- `python3 user/scripts/bug-state.py --test` → all smoke tests passed.
- `python3 user/scripts/bug-state.py --repo-root . --fsck` → `{"ok": true, "violations": []}`.
- `python3 ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` → OK.

Receipt + archive performed OUT-OF-PIPELINE per `docs/bugs/CLAUDE.md`'s "Fixing a bug
OUT-OF-PIPELINE" contract: this was a manual, direct `/harden-harness` invocation (no cycle
marker; inline reconciliation path), not a `/lazy-bug-batch` cycle.

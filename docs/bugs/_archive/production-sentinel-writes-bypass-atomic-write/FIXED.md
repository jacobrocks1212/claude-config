---
kind: fixed
feature_id: production-sentinel-writes-bypass-atomic-write
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py) + lazy-state.py --test + bug-state.py --test; NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`production-sentinel-writes-bypass-atomic-write` marked fixed on 2026-07-12 by a direct
operator-directed STATE-lane bug-fix pass (PHASES then implement; this bug skips the pipeline's
`__mark_fixed__` gate). Root cause: the atomic-write invariant in `user/scripts/CLAUDE.md`
("All queue/marker/sentinel writes go through `lazy_core._atomic_write`") existed only as prose,
with zero mechanical enforcement — seven production write sites across both state scripts used
bare `path.write_text()`, and a duplicate `_current_head` definition in `lazy_core.py` had gone
undetected for the same reason (no lint gate of any kind over `user/scripts/`).

## What shipped

- **All seven inventory rows routed through `lazy_core._atomic_write`:** `lazy-state.py`'s
  `_write_yaml_sentinel` / `_write_yaml_blocked_sentinel`, `_write_step10_needs_input`, the
  `enqueue_adhoc` ROADMAP append + brief write, `enqueue_adhoc_bug`'s brief write, and
  `materialize_wi`'s feature/bug brief + stub SPEC.md writes; `bug-state.py`'s mirrored
  `_write_yaml_sentinel` / `_write_yaml_blocked_sentinel`. Byte-identical output — mechanical
  substitution only.
- **Layout reconciliation:** both state scripts' two sentinel writers re-bannered as production
  helpers, ABOVE their respective (now-correctly-scoped) fixture-region banners.
- **PyYAML-fallback reconciliation (D3):** `bug-state.py`'s dead per-call `except ImportError`
  fallback deleted; `bug-state.py` now hard-exits at import time on missing PyYAML (matching
  `lazy-state.py`'s posture) via an explicit top-level import guard.
- **F811 bonus-finding fixed:** the duplicate `_current_head` definition in `lazy_core.py` (two
  module-level defs, identical bodies, the second silently shadowing the first) resolved to one
  definition.
- **Mechanical lint gates added** (`user/scripts/test_lazy_core.py`): a pure-AST bare-write
  collector (self-checking meta-test + two negative-fixture proofs) and a pure-AST duplicate-
  top-level-def collector (self-checking meta-test + a negative-fixture proof) — the F811-class
  gate substitute (stdlib-only, no new `ruff` dependency; see PHASES.md's Deferred Follow-Up).

## Evidence ladder

- **Mechanical regression gates, not just a one-time fix:** `test_no_bare_production_sentinel_writes`
  and `test_no_duplicate_top_level_defs_in_state_scripts` are self-checking meta-tests that FAIL
  (naming file + line) on any future bare write or shadowed definition — proven non-vacuous by
  three accompanying negative-fixture tests that plant synthetic violations and confirm the
  collectors catch them (and do not false-positive on fixture-region-scoped writes or clean
  modules).
- **Full gates:** `python -m pytest user/scripts/test_lazy_core.py -q` → 1030 passed, 0 failed.
  `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` both
  exit 0 (every sentinel-write path the smoke harnesses exercise still produces parseable
  sentinels via the now-atomic path). `python user/scripts/lazy_parity_audit.py --repo-root .` and
  `python user/scripts/doc-drift-lint.py --repo-root .` both exit 0.
- **Grep-confirmed inventory closure:** every remaining `.write_text(` call in `lazy-state.py` and
  `bug-state.py` sits at/after each file's fixture-region banner; `lazy_core.py` has zero.

## Deferred (documented, not blocking this Fixed status)

The SPEC's alternate lint vehicle (`ruff check --select F`) was not adopted — the stdlib AST
duplicate-def guard fully covers this bug's concrete defect class without adding a new dependency
to a repo with zero existing external lint tooling. A future harden-harness round wanting broader
pyflakes-class coverage can still add `ruff --select F` as an additional gate; see PHASES.md.

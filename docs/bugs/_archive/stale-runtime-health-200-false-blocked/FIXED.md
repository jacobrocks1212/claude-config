---
kind: fixed
feature_id: stale-runtime-health-200-false-blocked
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py) + lazy-state.py --test + bug-state.py --test; NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`stale-runtime-health-200-false-blocked` marked fixed on 2026-07-12 by a direct operator-directed
STATE-lane bug-fix pass (PHASES then implement; this bug skips the pipeline's `__mark_fixed__`
gate). Root cause: `ensure_runtime`'s STALE verdict state existed and was already routed to a
rebuild at every classification site, but its `stale_check` parameter defaulted to `lambda: False`
in production — the F7 freshness predicate (`stale_binary.native_source_newer_than`) that could
have supplied a real signal was built and fully tested (`test_stale_binary.py`) but had ZERO
production callers anywhere under `user/`, orphaned since its introduction.

## What shipped

- `user/scripts/lazy_core.py`: `_default_stale_check(repo_root, cfg)` — derives a real staleness
  signal from the boot-spawn stamp (`read_boot_stamp`, falling back to `.runtime.lock.json`'s
  recorded kernel `start_time` when absent) compared via `stale_binary.native_source_newer_than`
  against the newest commit touching the repo's configured `native_globs`. Fail-safe throughout:
  any missing signal or predicate error reports NOT stale (never raises), preserving
  `stale_binary.py`'s own documented fail-safe direction.
  - `ensure_runtime`'s `stale_check` default changed from the unconditional `lambda: False` to this
    real binding — the ONLY change needed to make the already-built STALE→rebuild routing (legacy
    mode's `elif stale_check(): restart(); ...`; M4 mode's `_route_non_serving("STALE", ...)` →
    `_recover_runtime`) reachable in production. No new state machine.
  - `ensure_runtime`'s docstring corrected (an unrelated pre-existing inaccuracy — a
    `stale_check(artifact_hash)` signature that never matched the real zero-arg callable).
- `user/scripts/test_lazy_core.py`: 6 unit tests of `_default_stale_check` (native-commit-after-boot
  stale, native-commit-before-boot fresh, no-boot-stamp lock fallback, no signal at all fails safe,
  configured `native_globs` respected, bogus repo root never raises) + 2 tests calling
  `ensure_runtime` with NO `stale_check=` injected, proving the real production default derives
  from a genuine git repo + boot stamp and routes STALE→`restart()`/stays fresh with no restart.

## Evidence ladder

- **Serving-path regression test:** the 8 new tests are RED-for-the-right-reason against the prior
  `lambda: False` default (a stale-and-derived-True scenario could never have reached `restart()`
  under that default — verified by reading the prior code path, which never referenced
  `stale_binary` at all) and GREEN against the fix.
- **Full gates:** `python -m pytest user/scripts/test_lazy_core.py -q` → 1030 passed, 0 failed.
  `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` both
  exit 0 (unaffected — STALE routing was already exercised there via injected `stale_check`
  fixtures; this fix only changes what the UNINJECTED default derives).
  `python user/scripts/lazy_parity_audit.py --repo-root .` and
  `python user/scripts/doc-drift-lint.py --repo-root .` both exit 0.
- **Not re-testable inside claude-config:** the fix's live-runtime effect (fewer stale-confound
  false BLOCKED mints on a real AlgoBooth checkout) requires a real Tauri dev runtime + a genuinely
  stale binary — the "Manual live cold-boot smoke" convention documented in
  `user/scripts/CLAUDE.md` is the sanctioned operator-side confirmation, deferred to that repo's own
  observation on its next live `/lazy-batch` run.

## Deferred (SKILLS-lane, not blocking this Fixed status)

Fix Scope items 3 (a BLOCKED.md freshness-fingerprint guard — defense-in-depth against the residual
race window between a READY-and-fresh `--ensure-runtime` verdict and a native commit landing before
`/mcp-test` runs) and 4 (a `lazy-batch/SKILL.md` prose line, now accidentally TRUE as of this fix —
no correction needed, only a cross-check at the next SKILLS-lane touch) require edits under
`user/skills/**`, outside this STATE-lane pass's file-ownership grant. See PHASES.md's "Deferred
Follow-Up" section. Neither blocks the field-observed defect this bug fixes — see PHASES.md's
"Validated Assumptions" for why Phase 1 alone already satisfies Fix Scope item 2's outward behavior.

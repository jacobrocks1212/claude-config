# Plan-structure authoring gate silently disarms repo-wide on infrastructure failure — Investigation Spec

> `lazy_core.plan_structural_backstop` wraps its load of validate-plan.py's
> `run_structural_checks` in a broad `except Exception` that returns `{"ok": True, "findings": []}`
> — so a LOADER/IMPORT crash (gate machinery broken) is indistinguishable from a clean plan
> (plan validated fine). When the lazy-core-package-decomposition Phase 1 deleted the flat
> `user/scripts/lazy_core.py`, validate-plan.py's `_load_lazy_core` (which loaded that flat file
> by literal path) raised `FileNotFoundError` on every invocation, and the plan-structure
> authoring gate no-oped REPO-WIDE with zero signal — caught only by an independent reviewer
> re-run, never by the harness itself.

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** 5e0f4d7a
**Priority:** P1
**Last updated:** 2026-07-13
**Related:** `docs/features/lazy-core-package-decomposition/` (the module move that triggered the disarm; Phase 1 commits `10f187b5` + `23109934`); `docs/bugs/planning-audit-blind-to-inbound-module-path-loads/` (the sibling PLANNING-time gap — why no WU covered the inbound loaders in the first place); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 37 (the hardening round that fixes this).

## Verified Symptom

During the lazy-core-package-decomposition Phase 1 execution (2026-07-13), after
`user/scripts/lazy_core.py` was decomposed into the `user/scripts/lazy_core/` package:

- `validate-plan.py::_load_lazy_core` (pre-fix form) loaded the now-deleted flat
  `lazy_core.py` via `spec_from_file_location` → `FileNotFoundError` on every call.
- `plan_structural_backstop` (`user/scripts/lazy_core/_monolith.py:4121-4125`) caught it in
  `except Exception: return {"ok": True, "findings": [], "mid_execution": mid_execution}` —
  a SILENT PASS. Every plan probed during that window was reported structurally clean without
  a single rule executing.
- Zero diagnostics, zero findings, zero breadcrumbs. The disarm was discovered only by an
  independent reviewer re-running the battery — the exact "review that catches late" the
  mission statement says gates exist to replace.

## Root Cause

**Classification: `script-defect`** (two sites, one failure class).

1. **`_monolith.py::plan_structural_backstop` (~L4121-4125):** the `except Exception` branch
   conflates two distinct conditions its own docstring separates elsewhere: "the plan is
   imperfect" (the deliberate mid-execution warns-not-refuses fail-open — CORRECT, preserved)
   vs. "the gate machinery is broken" (loader crash, import error — a harness infrastructure
   failure). The latter must be LOUD (an ERROR finding + `_diag` breadcrumb), never a silent
   `ok: True` — a silently-disarmed gate is strictly worse than no gate, because downstream
   consumers believe validation ran.
2. **`validate-plan.py::run_structural_checks` (~L803):** its docstring promises "Never
   raises: an unreadable/unparseable file is reported as an ERROR finding, never a silent
   pass" — but it calls `_load_lazy_core()` UNGUARDED, so a lazy_core import failure violates
   the contract by raising (which is what fed the silent `except` above).

## Fix Scope

- `run_structural_checks`: guard `_load_lazy_core()`; on failure return
  `([f"[ERROR] (infrastructure) …"], 1)` — honoring its own never-raises contract and making
  the machinery failure a first-class ERROR finding that flows through the existing
  fresh-refuses / mid-execution-warns semantics.
- `plan_structural_backstop`: the residual `except Exception` (now covering only
  `_load_validate_plan_module` failures) returns a loud
  `[ERROR] (infrastructure) …` finding + a `_diag` breadcrumb + `infrastructure_error: True`,
  with `ok` honoring the EXISTING exemption discriminator (`exempt` — mid-execution/legacy
  plans warn, fresh plans refuse). The deliberate fail-opens that stay: unreadable PLAN file
  (plan-side, pinned by `test_plan_structural_backstop_missing_file_fails_open`) and the
  checkbox-count fallback.
- Fold in the stale-prose cleanup from the same decomposition (cosmetic, same files):
  `_monolith.py:7726` flat-file path comment, the `skill_declares_subagent_model` /
  `skill_declares_multi_commit` "this module's parent.parent" docstrings (now wrong for a
  module living in `lazy_core/`; the CODE correctly uses `_SCRIPTS_DIR.parent`), and
  `migrate_legacy_state_dir`'s docstring reference to the retired `_legacy_state_migrated`
  guard name (now `_ctx.legacy_state_migrated()`).
- Regression tests: infrastructure failure on a fresh plan → loud refuse; on a mid-execution
  plan → loud warn (ok True, findings non-empty); `run_structural_checks` with a broken
  lazy_core loader → returns the ERROR finding, never raises.

Fix lands in hardening Round 37 (this session); remaining pipeline work is receipt-gated
`__mark_fixed__` verification.

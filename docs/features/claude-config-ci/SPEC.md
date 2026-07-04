# CI for claude-config Itself — Feature Specification

> The repo has ~10 pytest suites, `lint-skills.py`, the parity audit, and a bash hook harness — and no `.github/workflows/`, so the harness's own integrity gates only run when someone remembers. Add a push-triggered GitHub Actions workflow (plus Pester/PSScriptAnalyzer for the PowerShell side) so every commit to the harness is gate-checked mechanically.

**Status:** Draft (pre-Gemini)
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The mission statement says integrity gates are load-bearing, but the gates guarding the harness
itself are opt-in local runs. A regression in `lazy_core.py`, a broken component injection, or a
coupled-pair drift can land on `main` unnoticed until a live run trips it.

## Direction (deliberately not locked)

- **Python lane:** pytest across `user/scripts/` suites (`test_lazy_core`, `test_hooks`,
  `test_pipeline_visualizer`, `test_lazy_parity`, ...), `lint-skills.py --check-projected
  --check-capabilities`, `project-skills.py` projection check.
- **Bash lane:** the hook harness (`test_hooks.py` bash-side fixtures) on a Linux runner.
- **PowerShell lane:** `build-queue-hygiene.Tests.ps1` via Pester + PSScriptAnalyzer on the
  `*.ps1` family (Windows or `pwsh` on Linux — needs a portability assessment).
- Keep it fast and non-flaky; the suites are hermetic by design (`--test` injection points).

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: runner OS matrix (bash hooks are
> POSIX, build-queue is Windows-shaped); required-check vs. informational; whether the parity
> audit and doc-drift linter (sibling proposal) join the same workflow. Solutions above are
> directional, not locked.

# Cross-Platform Setup (Python Port of setup.ps1/manifest.psd1) — Feature Specification

> Bootstrap/check/repair is PowerShell-only, so Linux/cloud containers can't materialize the symlink layout, and the windows-portability bug class keeps recurring. A stdlib-Python `setup.py check|repair` reading a portable manifest makes the harness self-hosting in cloud sessions too.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The symlink system is the repo's core mechanism, and it is unreachable from non-Windows hosts:
`manifest.psd1` is a PowerShell data file and `setup.ps1` assumes Windows paths/link semantics.
Cloud sessions (including the ones running `/lazy-batch-cloud` against this very repo) operate on
a bare clone without the write-through layout, and portability fixes get rediscovered per-bug
(`windows-portability-in-probe-glue-and-field-validators`).

## Direction (deliberately not locked)

- **Manifest:** either parse `.psd1` from Python (keep single source of truth) or migrate to
  JSON/TOML with a psd1 shim during transition — drift between two manifests is the failure mode
  to avoid.
- **Script:** stdlib-only Python `setup.py bootstrap|check|repair` with the same scopes/targets;
  Windows keeps working (junction/symlink selection per-platform, matching current behavior).
- **Cloud story:** decide what "live locations" mean in an ephemeral container (`~/.claude/`
  exists there too) and which scopes make sense to link.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: manifest format decision;
> Windows symlink-privilege handling parity; whether `setup.ps1` is retired or kept as a thin
> caller. Solutions above are directional, not locked.

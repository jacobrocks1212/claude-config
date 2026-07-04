---
kind: implemented
feature_id: cross-platform-setup
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [a10e3f0, 0a60ec3, c1b358a, 9eb42d5, 0b80d31, db3e3b7, c20f619, 2b2c5f4]
decisions: []
---

# Implementation Ledger

**What shipped:** Bootstrap/check/repair is PowerShell-only, so Linux/cloud containers can't materialize the symlink layout, and the windows-portability bug class keeps recurring. A stdlib-only Python `setup.py bootstrap|check|repair` at the repo root — reading the EXISTING `manifest.psd1` through a minimal tolerant psd1 parser — makes the harness self-hosting in cloud sessions while keeping one manifest as the single source of truth and keeping `setup.ps1` working unchanged on Windows.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**

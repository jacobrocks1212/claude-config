# Doc-Drift Linter (CLAUDE.md vs. Reality) — Feature Specification

> The CLAUDE.md hooks/scripts tables are hand-maintained claims about `settings.json` and the filesystem, and drift has already happened once (`worktree-claude-doc-drift`). A lint script cross-checks documented hooks against registered hooks, documented scripts against files on disk, and coupled-pair tables against `lazy-parity-manifest.json`, catching drift mechanically instead of in retros.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

Nested CLAUDE.md files are the orientation layer agents read first; when their tables lie (a hook
documented as registered but unwired, a script renamed, a coupled pair missing from the sync
table), agents act on stale claims. Today the only detector is a human retro.

## Direction (deliberately not locked)

- **Checks:** hooks table ↔ `user/settings.json` registration (including the deliberate
  NOT-registered rows, which must stay documented as such); scripts table ↔ `user/scripts/`
  contents; coupled-pair table ↔ `lazy-parity-manifest.json`; manifest.psd1 mappings ↔ repo dirs.
- **Shape:** stdlib-Python sibling of `lint-skills.py`; runnable locally and in the CI proposal
  (`claude-config-ci`).
- **Tolerance:** structured-claim extraction from markdown tables only — no NLP over prose.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: which claims are machine-checkable
> vs. prose-only; annotation convention for deliberate divergences; scope (this repo only vs.
> per-repo `.claude/` CLAUDE.md files too). Solutions above are directional, not locked.

---
kind: implemented
feature_id: doc-drift-linter
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [8e9c1f6, e05444f, 14d0d0f, 728e61b, aea2b59, 9a831c3, aa12aa1]
decisions: [K1, K2, K3, K4]
---

# Implementation Ledger

**What shipped:** The CLAUDE.md hooks/scripts tables are hand-maintained claims about `settings.json` and the filesystem, and drift has already happened once (`worktree-claude-doc-drift`). A stdlib-only lint script (`user/scripts/doc-drift-lint.py`, sibling of `lint-skills.py`) cross-checks four structured-claim surfaces mechanically — the root `CLAUDE.md` hooks table against `user/settings.json` hook registrations (including asserting the deliberately NOT-registered rows stay documented as such), the root + `user/scripts/CLAUDE.md` script tables against `user/scripts/` files on disk, the root Coupled Skill Pairs table against `user/scripts/lazy-parity-manifest.json`, and `manifest.psd1` Repos entries against `repos/<name>/` dirs — catching drift at lint time instead of in retros. Deliberate divergences are annotated in place with a single SSOT marker constant (the `<!-- verification-only -->` precedent).

**Decisions that drove it:**
- K1 — **hooks:** root `CLAUDE.md` `## Hooks` table ↔ `user/settings.json` hook registrations.
- K2 — **scripts:** root `CLAUDE.md` `## Scripts` table + `user/scripts/CLAUDE.md`
- K3 — **coupled pairs:** root `CLAUDE.md` `### Coupled Skill Pairs` table ↔
- K4 — **manifest:** `manifest.psd1` `Repos` entries ↔ `repos/<name>/` dirs. Forward: every

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**

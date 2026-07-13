---
kind: fixed
feature_id: skills-plane-hygiene-debris
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: lint-skills.py --check-projected --check-capabilities + project-skills.py + lazy_parity_audit.py; NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`skills-plane-hygiene-debris` marked fixed on 2026-07-12. Root cause: hygiene debt via a missing
gate (`hygiene-debt` / `missing-gate`, plus one `incomplete-sweep`) — bulk "sync skills" commits
stage the whole tree with no `*.stackdump` gitignore backstop; component archival is a manual
convention with no automated "referenced by nothing" detector; the 2026-06-14 retro-unwire sweep
(`ea738f4`) removed dispatch prose but missed three sub_skill mapping tables; and the prevention
tool (`skill-usage-miner.py`) exists but has no mechanical trigger (that trigger is
`docs/features/claude-config-ci/`'s scope, cross-linked, not built by this bug).

## What shipped

Three independent hygiene phases, executed per the SPEC's Fix Scope + adopted Decisions
(D1 archive, D2 delete, D3 defer to claude-config-ci — no design fork, so no
`NEEDS_INPUT_PROVISIONAL.md` was warranted):

1. **Crash dumps (Phase 1).** Removed the two tracked `sh.exe.stackdump` files (repo root +
   `user/skills/`) from the working tree and added a `*.stackdump` entry to `.gitignore` so a
   future Git-Bash crash during a bulk sync cannot re-commit one.
2. **Orphan components (Phase 2).** Re-confirmed all three `_components/` files (`interview-relevance.md`,
   `parallel-implementation.md`, `post-compact-reread.md`) have zero live `!cat` references
   anywhere in `user/`, `docs/`, `repos/*/.claude/` (mechanical re-grep, not trust-the-SPEC), then
   moved them to `archived/user-skills/_components/` (mirrors the existing `archived/user-skills/`
   naming convention) with one `archived/CLAUDE.md` trail row each, per D1's "archive, never
   delete" rule.
3. **Retro mapping rows (Phase 3).** Deleted the never-emitted `retro` / `retro-feature`
   sub_skill rows from `lazy-status/SKILL.md`, `lazy-bug-status/SKILL.md`, and `lazy-bug/SKILL.md`
   (per D2 — delete, not annotate); fixed the stale "fall through to retro on next cycle" prose in
   the still-LIVE `__write_deferred_non_cloud__` row (both status skills — that row is retained,
   only its description was stale) to describe the actual route (direct to the Step 9 MCP gate,
   since retro was unwired 2026-06-14). Left the DORMANT banners and all other retro prose
   mentions untouched — the SPEC's Verified Symptom (c) found those already internally
   consistent; only the five enumerated mapping-table lines were debris.
4. **Standing prevention (Fix Scope item 4)** is explicitly NOT built here — it is cross-linked
   to `docs/features/claude-config-ci/` (Draft), which owns the commit-time gate mechanism. This
   bug only records the requirement (already true of the SPEC; no PHASES.md action needed).

No design fork was hit — every decision point in the SPEC (D1/D2/D3) already carried a clear
recommendation that this pass adopted verbatim, so this is pure hygiene per the OPERATOR PROTOCOL
and closes normally (no `NEEDS_INPUT_PROVISIONAL.md`).

## Symptom reproduction — before/after inventory

**(a) Crash dumps — before:** `git ls-files | grep -i stackdump` → `sh.exe.stackdump` AND
`user/skills/sh.exe.stackdump`; `.gitignore` had no `*.stackdump` entry.
**After:** both files deleted from the working tree (`git status --short` shows `D
sh.exe.stackdump`, `D user/skills/sh.exe.stackdump`); `.gitignore:13` reads `*.stackdump`.

**(b) Orphan components — before:** `user/skills/_components/interview-relevance.md`,
`parallel-implementation.md`, `post-compact-reread.md` present in `user/skills/_components/`
with zero live `!cat` consumers.
**After:** none of the three exist under `user/skills/_components/`; all three exist under
`archived/user-skills/_components/`, each with a trail row in `archived/CLAUDE.md`.
`project-skills.py` and `lint-skills.py --check-projected --check-capabilities` both stayed clean
post-move (no missing-component regressions — they were orphans by construction).

**(c) Retro mapping rows — before:** `lazy-status/SKILL.md:70/72`, `lazy-bug-status/SKILL.md:91/92`,
`lazy-bug/SKILL.md:~252` presented `retro`/`retro-feature` as live pipeline emissions and stale
"fall through to retro" prose, contradicting the scripts' `RETRO UNWIRED` comments.
**After:** grep for `retro --auto` / `retro-feature.*retrospective` / `retrospective pass` /
`fall through to retro` across all three files returns nothing. The `__write_deferred_non_cloud__`
row (retained, still live) now reads "phases complete routes directly to the Step 9 MCP gate on
the next cycle (retro is unwired)" in both status skills.

## Gates run

- `python3 user/scripts/lazy_parity_audit.py --repo-root .` → exit 0 (all pairs).
- `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-bug-status` → exit 0.
- `python user/scripts/project-skills.py` → "Skills projected (_default): 88, Components
  resolved (_default): 97, Errors (_default): none" across all 3 repo projections.
- `python user/scripts/lint-skills.py --check-projected --check-capabilities` → all four checks
  OK, exit 0.

## Files touched

- `sh.exe.stackdump` — deleted (working tree).
- `user/skills/sh.exe.stackdump` — deleted (working tree).
- `.gitignore` — added `*.stackdump` (+2 lines incl. comment).
- `user/skills/_components/interview-relevance.md` → `archived/user-skills/_components/interview-relevance.md` (moved).
- `user/skills/_components/parallel-implementation.md` → `archived/user-skills/_components/parallel-implementation.md` (moved).
- `user/skills/_components/post-compact-reread.md` → `archived/user-skills/_components/post-compact-reread.md` (moved).
- `archived/CLAUDE.md` — three new trail rows.
- `user/skills/lazy-status/SKILL.md` — deleted `retro` row, fixed `__write_deferred_non_cloud__` prose.
- `user/skills/lazy-bug-status/SKILL.md` — deleted `retro-feature` row, fixed `__write_deferred_non_cloud__` prose.
- `user/skills/lazy-bug/SKILL.md` — deleted `retro-feature` row.
- `docs/bugs/skills-plane-hygiene-debris/PHASES.md` — authored this pass; all three phases
  ticked Complete with evidence.
- `docs/bugs/skills-plane-hygiene-debris/SPEC.md` — `**Status:**` flipped to `Fixed`.
- `docs/bugs/skills-plane-hygiene-debris/FIXED.md` — this receipt (new).

No hook, state-script, `settings.json`, or build-queue file was touched — those lanes were owned
by concurrent agents this wave (out of scope for this subagent).

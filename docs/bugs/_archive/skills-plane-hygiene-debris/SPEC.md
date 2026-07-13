# Skills-plane hygiene debris — tracked crash dumps, orphan components, stale retro mapping rows — Investigation Spec

> The skills plane has accumulated hygiene debris that nothing gates: two git-tracked
> `sh.exe.stackdump` crash dumps (no `*.stackdump` gitignore), three `_components/` files referenced
> by nothing, and emit-mapping rows in the lazy status/wrapper skills that still present the
> retro step as a live pipeline emission eight-plus weeks after the operator unwired it. The
> `skill-usage-miner.py` hygiene sweep exists but is on-demand only — it never gates a commit,
> so debris persists until a human happens to run it.

**Status:** Fixed
**Priority:** P3
**Last updated:** 2026-07-11
**Related:** `user/skills/CLAUDE.md` ("Usage audit / pruning" — the on-demand miner + the deliberate-`archived/`-move rule); `archived/CLAUDE.md` (the audit-trail table convention for deprecated config); `docs/features/skill-usage-miner/` (Complete — the sweep tool); `docs/features/claude-config-ci/` (Draft — the standing commit-time prevention vehicle, cross-linked in Fix Scope); commit `ea738f4` (2026-06-14, "docs(retro-unwire): remove stale /retro prose from lazy-pipeline skills and components" — the sweep that missed the mapping tables); commit `f8719a8` ("chore: sync skills, components, hooks, and repo configs" — the sync that committed the crash dumps).

## Verified Symptom

All items re-verified live 2026-07-11.

**(a) Git-tracked crash dumps, no gitignore guard.** `git ls-files | grep -i stackdump` →
`sh.exe.stackdump` (repo root) AND `user/skills/sh.exe.stackdump`. Both were introduced by the
bulk sync commit `f8719a8` ("chore: sync skills, components, hooks, and repo configs"). `.gitignore`
has no `*.stackdump` entry, so the next Git-Bash crash during a sync re-commits a new one.

**(b) Orphan components (referenced by nothing).** Grep across `user/`, `docs/`, `plugins/`:

- `user/skills/_components/interview-relevance.md` — zero references anywhere.
- `user/skills/_components/parallel-implementation.md` — zero references anywhere.
- `user/skills/_components/post-compact-reread.md` — zero live references: no skill `!cat`s it.
  The only mentions are historical documents — `docs/features/plan-skills-redesign/IMPLEMENTATION_NOTES.md`
  (lines 47/70/101: a past sweep that updated it as a notes-mining *consumer*) and
  `docs/specs/spec-buddy/SPEC.md` line 37 (a planned-reuse table row; the shipped
  `user/skills/spec-buddy/SKILL.md` does not reference it).

**(c) Retro dormancy story is inconsistent across planes — with one correction to the original report.**
The originally-reported contradiction ("retro is DORMANT but retro-feature is a live skill") is
**partially refuted**: BOTH `user/skills/retro/SKILL.md` (line 8) and `user/skills/retro-feature/SKILL.md`
(line 14) carry the identical banner
`> **DORMANT — unwired from the lazy autonomous pipeline 2026-06; retained for manual use and restore. The pipeline no longer dispatches this step.**`
(added in `ea738f4`, 2026-06-14). The pair is internally consistent. The verified debris is the
**emit-mapping rows that survived the `ea738f4` sweep** and still present retro as a live pipeline
emission:

- `user/skills/lazy-status/SKILL.md:70` — `| `retro` | /retro --auto — run retrospective |`
- `user/skills/lazy-status/SKILL.md:72` — `__write_deferred_non_cloud__` row: "… fall through to retro on next cycle"
- `user/skills/lazy-bug-status/SKILL.md:91` — `| `retro-feature` | /retro-feature — run retrospective |`
- `user/skills/lazy-bug-status/SKILL.md:92` — same stale "fall through to retro" prose
- `user/skills/lazy-bug/SKILL.md` (~line 252) — `| `retro-feature` | `/retro-feature` — retrospective pass |`

The scripts are unambiguous the other way: `lazy-state.py` ~3349 ("RETRO UNWIRED (operator decision,
2026-06): the Step 8 /retro phase has been removed from the pipeline") and `bug-state.py:171`
(`SKILL_RETRO = "retro-feature"  # DORMANT (retro unwired 2026-06) — kept for restore path  # noqa: F841` —
never emitted). So the status skills document `sub_skill` values the state machines can no longer
produce; a reader of the mapping tables concludes the Step 8/9 retro exists, a reader of the scripts
concludes it doesn't.

**(d) The hygiene sweep never gates.** `user/scripts/skill-usage-miner.py` (feature Complete —
`docs/features/skill-usage-miner/COMPLETED.md`) includes exactly the needed sweep: stray non-skill
artifacts, dangling symlinks, case-variant `skill.md`, frontmatter defects. But
`user/skills/CLAUDE.md` documents it as "read-only, on-demand", and nothing invokes it at commit
time — grep for invokers finds only docs and its own tests. Items (a)–(c) all postdate the miner's
completion: existence of the tool without a trigger did not prevent the debris.

## Root Cause

**Classification: `hygiene-debt` via `missing-gate`, plus one `incomplete-sweep`.**

1. Bulk "sync skills" commits stage the whole tree (`f8719a8`), so any crash artifact present at
   sync time gets committed; with no `*.stackdump` gitignore there is no backstop.
2. Component archival is a manual convention (`archived/` move + trail row, per `user/skills/CLAUDE.md`
   and `archived/CLAUDE.md`) with no detector for "referenced by nothing" between on-demand miner runs.
3. The `ea738f4` retro-unwire sweep removed dispatch prose but missed the three skills' sub_skill
   mapping tables (and the "fall through to retro" annotations) — an incomplete sweep with no
   drift-lint to catch the miss.
4. The prevention tool exists (miner hygiene sweep) but has no mechanical trigger — the same class of
   gap `docs/features/claude-config-ci/` (Draft) exists to close.

## Fix Scope (Concluded)

1. **Crash dumps:** `git rm sh.exe.stackdump user/skills/sh.exe.stackdump`; add `*.stackdump` to
   `.gitignore`.
2. **Orphan components:** move all three to `archived/` (the deliberate move, never delete — house
   rule) and add one trail row each to `archived/CLAUDE.md` naming the replacement/disposition
   ("orphaned — no consumer since <evidence>"). Then re-run `project-skills.py` + `lint-skills.py`
   to confirm no projection references break (expected no-op — they are orphans by construction).
3. **Retro mapping rows:** delete the stale rows/prose in `lazy-status/SKILL.md` (:70, :72),
   `lazy-bug-status/SKILL.md` (:91, :92), and `lazy-bug/SKILL.md` (~:252) — or annotate them
   `(DORMANT — restore path only)` per D2. Honor the coupled-pair discipline: run
   `python3 user/scripts/lazy_parity_audit.py` per the parity note in the lazy-* skill frontmatter,
   then re-project + `lint-skills.py`.
4. **Standing prevention (cross-link, not built here):** `docs/features/claude-config-ci/` is the
   commit-time gate vehicle — a hygiene lane there (running the miner's non-session-log hygiene
   sweep and/or a stray-artifact check) is what keeps this class of debris from recurring. This bug
   only records the requirement; the CI feature owns the mechanism.

## Decisions

- **D1 — Archive vs delete the orphan components:** archive (recommended — `archived/CLAUDE.md`'s
  "move it here (don't delete)" rule is explicit; deletion loses the audit trail for a component that
  a future skill redesign might revive).
- **D2 — Delete vs annotate the stale mapping rows:** delete (recommended). The DORMANT banners on
  both retro skills plus the state scripts' `RETRO UNWIRED` comments are sufficient restore
  breadcrumbs; keeping dormant rows in a table titled as the live sub_skill map is exactly the
  confusion being fixed.
- **D3 — Gating cadence for the miner's hygiene sweep:** defer to `claude-config-ci` (recommended) —
  the miner stays read-only/on-demand for usage mining (session-log-dependent, workstation-bound),
  while its hermetic hygiene checks are the CI-eligible subset. No new trigger machinery in this bug.

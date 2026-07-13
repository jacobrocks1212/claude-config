# Implementation Phases — Skills-plane hygiene debris

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a pure
hygiene sweep (file moves, a `.gitignore` entry, and stale-prose deletion) verified via
deterministic gates (`lint-skills.py`, `project-skills.py`, `lazy_parity_audit.py`) and a
grep-based before/after inventory, the repo's established "build-tooling / repo-config, no app
integration" untestable class (no `mcp-tool-catalog.md` in this repo, so the planning-time MCP
tool-existence audit no-ops).

## Validated Assumptions

- **All four debris classes (a)-(d) are still live on disk** — re-verified 2026-07-12 before
  authoring this plan: both `sh.exe.stackdump` files present, no `*.stackdump` gitignore entry,
  all three orphan components present with zero live `!cat` references (grep across
  `user/`, `repos/*/.claude/`), and all five stale retro mapping-row line numbers match the SPEC
  exactly. Nothing pre-landed; git log shows no prior commit touching this bug's slug.
- **D1/D2/D3 (SPEC "Decisions") are adopted as recommended** — archive (not delete) the orphan
  components; delete (not annotate) the stale mapping rows; defer the standing-prevention CI gate
  to `docs/features/claude-config-ci/` (cross-link only, no new trigger machinery here). No design
  fork — this is pure hygiene executed exactly as the SPEC concluded, so no
  `NEEDS_INPUT_PROVISIONAL.md` is warranted.
- **The `__write_deferred_non_cloud__` row's "fall through to retro" prose is inaccurate, not
  merely dormant** — `lazy-state.py`'s live routing (confirmed in `user/scripts/CLAUDE.md`'s "Per-item
  lifecycle" section) sends a phases-complete feature DIRECTLY to Step 9 (MCP gate) since the
  2026-06-14 retro-unwire; there is no "next cycle" retro to fall through to. The row itself (the
  pseudo-skill mapping) is NOT stale — it is a live, still-emitted pseudo-skill — only its
  trailing prose needs correcting, so this row is EDITED in place, not deleted (distinct from the
  `retro` / `retro-feature` rows, which are deleted outright because those sub_skill values are
  never emitted at all).

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. `docs/features/claude-config-ci/` (Draft) is
cross-linked as the standing-prevention vehicle for fix-scope item 4 — this bug does not build
it, only records the requirement (already done in the SPEC's Fix Scope + Related line; no
PHASES.md action needed for item 4).

---

### Phase 1: Crash dumps — `git rm`-equivalent + gitignore guard

**Scope:** Remove the two tracked `sh.exe.stackdump` crash dumps from the working tree (plain
`mv` out of the tree per orchestrator-owns-git constraint — the orchestrator stages the deletion)
and add a `*.stackdump` entry to `.gitignore` so a future Git-Bash crash during a sync commit
cannot re-introduce one.

**TDD:** no (file deletion + a `.gitignore` line; no unit under test).

**Status:** Complete

**Deliverables:**
- [x] Delete `sh.exe.stackdump` (repo root) from the working tree.
- [x] Delete `user/skills/sh.exe.stackdump` from the working tree.
- [x] Add `*.stackdump` to `.gitignore`.

**Minimum Verifiable Behavior:** `git status --short` shows both files as pending deletions (`D`);
`git ls-files | grep -i stackdump` returns nothing once staged; a fresh `touch sh.exe.stackdump &&
git status --short` (manual local probe, not committed) shows the file as untracked/ignored, not
a candidate for `git add`.

**Runtime Verification** *(no app runtime — repo-hygiene only)*:
- [x] <!-- verification-only --> Both stackdump files absent from the working tree post-move;
  `.gitignore` contains `*.stackdump`. **Verified 2026-07-12:** `git status --short` shows
  `D sh.exe.stackdump` and `D user/skills/sh.exe.stackdump`; `.gitignore:13` reads `*.stackdump`.

**Implementation Notes (2026-07-12):** Both crash dumps removed via plain `rm` (working-tree
delete; orchestrator stages it as `D`, not `git rm`, per the subagent's no-git-mutation
constraint). `.gitignore` gained a `# Git-Bash (MSYS) crash dumps` / `*.stackdump` block after the
existing OS-artifacts section. Files: `sh.exe.stackdump` (deleted), `user/skills/sh.exe.stackdump`
(deleted), `.gitignore` (+2 lines).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `sh.exe.stackdump` — deleted (verified exists, 539 bytes, repo root).
- `user/skills/sh.exe.stackdump` — deleted (verified exists, 539 bytes).
- `.gitignore` — add one line.

**Testing Strategy:** `git ls-files | grep -i stackdump` (expect empty) + manual `.gitignore`
pattern spot-check.

**Integration Notes for Next Phase:** None — independent of Phase 2/3.

---

### Phase 2: Orphan components — archive to `archived/user-skills/_components/`

**Scope:** Move the three zero-consumer `_components/` files to `archived/user-skills/_components/`
(mirrors the existing `archived/user-skills/` bucket's source-tree-relative naming, per D1 —
archive, never delete) and add one trail row each to `archived/CLAUDE.md`. Re-run
`project-skills.py` + `lint-skills.py` to confirm the move is a true no-op (they are orphans by
construction — no skill should reference them, so projection output must be unaffected).

**TDD:** no (a file move + a docs table row; the gate is the existing lint/projection tooling).

**Status:** Complete

**Deliverables:**
- [x] Confirm orphanhood mechanically (re-grep, do not trust the SPEC alone): zero `!cat` /
  filename hits for each of the three across `user/skills/**/SKILL.md`, `user/skills/_components/**`,
  and `repos/*/.claude/**`.
- [x] Move `user/skills/_components/interview-relevance.md` →
  `archived/user-skills/_components/interview-relevance.md`.
- [x] Move `user/skills/_components/parallel-implementation.md` →
  `archived/user-skills/_components/parallel-implementation.md`.
- [x] Move `user/skills/_components/post-compact-reread.md` →
  `archived/user-skills/_components/post-compact-reread.md`.
- [x] Add three rows to `archived/CLAUDE.md`'s trail table (one per file), each naming "orphaned —
  no consumer since <evidence>" per the SPEC's Fix Scope item 2 wording.
- [x] Re-run `python user/scripts/project-skills.py` — expect clean (no missing-component errors;
  the three files were referenced by nothing, so no projected SKILL.md should regress).
- [x] Re-run `python user/scripts/lint-skills.py --check-projected --check-capabilities` — expect
  exit 0.

**Minimum Verifiable Behavior:** the three files exist under `archived/user-skills/_components/`
and no longer under `user/skills/_components/`; `project-skills.py` and `lint-skills.py` both
exit 0 post-move with no new findings attributable to the move.

**Runtime Verification** *(no app runtime — repo-hygiene only)*:
- [x] <!-- verification-only --> `python user/scripts/project-skills.py` clean +
  `python user/scripts/lint-skills.py --check-projected --check-capabilities` exit 0 after the
  move. **Verified 2026-07-12:** `project-skills.py` → "Skills projected (_default): 88,
  Components resolved (_default): 97, Errors (_default): none" (all 3 repo projections clean);
  `lint-skills.py --check-projected --check-capabilities` → all four checks OK, exit 0.

**Implementation Notes (2026-07-12):** Pre-move grep across `user/`, `repos/*/.claude/`, `docs/`
confirmed zero live `!cat` references to all three files (only historical mentions of
`post-compact-reread.md` survive in `docs/features/plan-skills-redesign/IMPLEMENTATION_NOTES.md`
and `docs/specs/spec-buddy/SPEC.md` — planning-doc mentions, not a shipped consumer). Moved via
plain `mv` to `archived/user-skills/_components/` (mirrors the existing `archived/user-skills/`
bucket's naming, which already holds retired `user/skills/*` content). Post-move re-grep
confirmed still zero references (nothing regressed). `archived/CLAUDE.md` gained three trail rows.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (independent of Phase 1).

**Files likely modified:**
- `user/skills/_components/interview-relevance.md` → `archived/user-skills/_components/interview-relevance.md`.
- `user/skills/_components/parallel-implementation.md` → `archived/user-skills/_components/parallel-implementation.md`.
- `user/skills/_components/post-compact-reread.md` → `archived/user-skills/_components/post-compact-reread.md`.
- `archived/CLAUDE.md` — three new trail rows.

**Testing Strategy:** grep-before (zero live-reference confirmation) → move → grep-after (still
zero, from the new path — proves nothing broke) → `project-skills.py` + `lint-skills.py`.

**Integration Notes for Next Phase:** None — independent of Phase 3.

---

### Phase 3: Retro mapping rows — delete stale rows, fix stale prose, parity audit

**Scope:** Delete the `retro` / `retro-feature` sub_skill mapping rows (never emitted since the
2026-06-14 unwire) from `lazy-status/SKILL.md`, `lazy-bug-status/SKILL.md`, and
`lazy-bug/SKILL.md`; fix the stale "fall through to retro on next cycle" prose in the
`__write_deferred_non_cloud__` rows (both status skills) to describe the actual live route
(direct to the MCP gate). Per D2, delete rather than annotate. Honor the coupled-pair discipline
(`lazy-status` ↔ `lazy-bug-status` is a parity-audited pair) — run the parity audit before and
after, then re-project + lint.

**TDD:** no (prose edits in skill dispatchers; gate is the parity audit + lint/projection).

**Status:** Complete

**Deliverables:**
- [x] `user/skills/lazy-status/SKILL.md:70` — delete the `| `retro` | /retro --auto — run
  retrospective |` row.
- [x] `user/skills/lazy-status/SKILL.md:72` — edit the `__write_deferred_non_cloud__` row's prose
  from "fall through to retro on next cycle" to describe the direct-to-MCP-gate route (row
  retained — it is a live pseudo-skill, only the description text is stale).
- [x] `user/skills/lazy-bug-status/SKILL.md:91` — delete the `| `retro-feature` | /retro-feature —
  run retrospective |` row.
- [x] `user/skills/lazy-bug-status/SKILL.md:92` — same prose fix as above, bug-pipeline wording.
- [x] `user/skills/lazy-bug/SKILL.md` (~:252) — delete the `| `retro-feature` | `/retro-feature` —
  retrospective pass |` row from its sub-skill routing table.
- [x] Leave the DORMANT banners (`retro/SKILL.md:8`, `retro-feature/SKILL.md:14`) and the other
  prose mentions of retro (e.g. `lazy-bug/SKILL.md` lines ~159/177/291/297/326/328) UNTOUCHED —
  the SPEC's Verified Symptom (c) found those internally consistent; only the five enumerated
  mapping-table lines are debris.
- [x] Run `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-bug-status` AFTER
  editing — expect exit 0 (both tables lost their retro row identically, so parity is preserved,
  not broken).
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root .` (all pairs) — expect exit 0.
- [x] Re-run `python user/scripts/project-skills.py` + `python user/scripts/lint-skills.py
  --check-projected --check-capabilities` — expect clean / exit 0.

**Minimum Verifiable Behavior:** grep for `retro --auto` / `retro-feature.*retrospective` /
`retrospective pass` across the three files returns nothing; the `__write_deferred_non_cloud__`
row prose no longer mentions retro in either status skill; `lazy_parity_audit.py --repo-root .`
exits 0.

**Runtime Verification** *(no app runtime — repo-hygiene only)*:
- [x] <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py --repo-root .` exit 0
  post-edit (all pairs, not just lazy-bug-status). **Verified 2026-07-12:**
  `python3 user/scripts/lazy_parity_audit.py --repo-root .` → exit 0, no output (clean).
- [x] <!-- verification-only --> `python user/scripts/lint-skills.py --check-projected
  --check-capabilities` exit 0 post-edit. **Verified 2026-07-12:** all four checks OK, exit 0
  (same run cited in Phase 2 — it covers all skills, not just this phase's three files).

**Implementation Notes (2026-07-12):** Deleted the `retro` row (`lazy-status`:70) and
`retro-feature` row (`lazy-bug-status`:91, `lazy-bug`:~252) outright — these sub_skill values are
never emitted (`lazy-state.py` "RETRO UNWIRED" comment, `bug-state.py:171`
`SKILL_RETRO = "retro-feature"  # DORMANT`). Edited (not deleted) the `__write_deferred_non_cloud__`
row's trailing prose in both status skills — that row IS still live/emitted every cloud cycle;
only its "fall through to retro" description was stale, now reads "phases complete routes
directly to the Step 9 MCP gate on the next cycle (retro is unwired)". Left the DORMANT banners
and all other prose mentions of retro untouched per the SPEC's item-(c) finding that those are
already internally consistent. Post-edit: grep for the stale phrasings across all three files
returns nothing; the coupled-pair `lazy-status`↔`lazy-bug-status` audit and the full
`lazy_parity_audit.py --repo-root .` (all pairs) both stayed exit 0 — the retro row's removal was
symmetric across the pair, so parity was preserved, not broken. Files: `user/skills/lazy-status/SKILL.md`,
`user/skills/lazy-bug-status/SKILL.md`, `user/skills/lazy-bug/SKILL.md`.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None (independent of Phase 1/2, but run last since it is the highest-touch
phase — easiest to verify in isolation after the simpler moves are confirmed clean).

**Files likely modified:**
- `user/skills/lazy-status/SKILL.md` — delete 1 row, edit 1 row's prose (verified: rows at :70/:72).
- `user/skills/lazy-bug-status/SKILL.md` — delete 1 row, edit 1 row's prose (verified: rows at :91/:92).
- `user/skills/lazy-bug/SKILL.md` — delete 1 row (verified: row at ~:252).

**Testing Strategy:** grep-before (confirm exact stale lines match SPEC line numbers) → edit →
grep-after (confirm zero stale-prose hits) → parity audit → project + lint.

**Integration Notes for Next Phase:** None — final phase. The bug's `**Status:**` flip to
`Fixed` + `FIXED.md` receipt is authored directly per this bug's OPERATOR PROTOCOL (bugs-pipeline
subagent, not the gated `__mark_fixed__` pseudo-skill) — not a checkbox in any phase.

**Completion:** `**Status:**` flipped to `Fixed` in SPEC.md + PHASES.md, and `FIXED.md` authored,
directly by this pass (per the assigned OPERATOR PROTOCOL for this bug — park-provisional,
non-gated) once all three phases' gates are green and the before/after inventory is captured.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

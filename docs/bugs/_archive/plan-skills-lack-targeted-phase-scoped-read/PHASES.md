# Implementation Phases — Plan skills lack targeted-phase scoped reads

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure skill-prose fix, verified via `lint-skills.py` +
`project-skills.py` (the skills project and resolve cleanly). No `mcp-tool-catalog.md` in this
repo; the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The three plan skills had no phase-selector and read PHASES.md in full** (confirmed in
  SPEC.md Evidence — `write-plan`/`write-plan-cloud`/`write-plan-cognito` Step 1a parsed only
  `.md` tokens; Step 1b read full). An OPTIONAL, interactive-only selector is byte-identical to
  today when absent, so it cannot regress the operator-confirmed by-design full-read authoring
  path.

## Cross-feature Integration Notes

No `**Depends on:**` block. Composes with the completed `phases-slice-scoped-reads` feature
(reuses its `phases-slice.py` + the `source-reread.md` canonical command; extends its scoped-read
reach to the authoring path, which that feature deliberately left uncovered). Self-contained
skill-prose fix.

---

### Phase 1: Add an optional interactive-only phase selector to the three plan skills

**Scope:** Add a repeatable `--phase <id>` flag AND bare `phase <id>` token to Step 1a argument
resolution of `write-plan`, `write-plan-cloud`, `write-plan-cognito`; when present (and NOT
`--batch`), replace the Step 1b full read with `phases-slice.py … --phase <id> --notes all` and
narrow the Step 2/1c phase scan to `TARGET_PHASES`. When absent (or under `--batch`), behavior is
byte-identical to before. Mirror argument-hint/description.

**TDD:** verification-by-gate — the fix is skill prose; correctness is that the skills lint,
project, and resolve cleanly and the selector is documented in each argument-hint.

**Status:** Fixed

**Deliverables:**
- [x] `user/skills/write-plan/SKILL.md` — argument-hint `[--phase <id> ...]`; Batch Mode
      ignore-clause; Step 1a `TARGET_PHASES` parse+strip; Step 1b conditional scoped read; Step 1c
      scan narrowed to `TARGET_PHASES`.
- [x] `user/skills/write-plan-cloud/SKILL.md` — same selector parse/strip + phase-targeted scoped
      read (replaced the prior mechanism-less "unless the user scoped a subset" gesture).
- [x] `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` — argument-hint; Batch
      Mode ignore-clause; Step 1a parse/strip; Step 1b conditional scoped read; Step 1c/Step 2
      scan narrowed to `TARGET_PHASES`.
- [x] Execution-side Cognito lane contract (`execution-contract-cognito-lanes.md`) intentionally
      untouched — it already reads scoped via `source-reread.md`; only the authoring path changed.

**Minimum Verifiable Behavior:** `python3 user/scripts/lint-skills.py` is clean and
`python3 user/scripts/project-skills.py` resolves all three skills (no broken `!cat`, planner
resolution OK); each skill's argument-hint documents the `[--phase <id> ...]` mode.

**MCP Integration Test Assertions:** N/A — skill-prose fix, no MCP-observable surface.

**Prerequisites:** None (only phase).

**Files likely modified:**
- `user/skills/write-plan/SKILL.md`
- `user/skills/write-plan-cloud/SKILL.md`
- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md`

**Testing Strategy:** `lint-skills.py` + `project-skills.py` over the three edited skills.

**Runtime Verification** *(checked by the lint/projection gates — the skills' "runtime" is
projection + resolution)*:
- [x] <!-- verification-only --> The three plan skills lint, project, and resolve cleanly with
  the selector added. **Verified 2026-07-14:** `lint-skills.py` → "OK — no broken or embedded
  !cat patterns" + "planner resolution: write-plan-cognito resolves"; `project-skills.py` →
  claude-config / algobooth / cognito-forms all project (91 skills, 102 components), exit 0.

**Integration Notes for Next Phase:** None — only phase. Fix landed on `main` directly from the
Concluded SPEC's "Fix shape"; receipt written via the gated `__mark_fixed__` chain (correcting the
original bare `Status: Fixed` flip the fsck flagged).

---

## Review Notes

_(Fix landed on main from the Concluded SPEC; receipt-gated through the structural no-MCP skip —
correcting the original receiptless flip.)_

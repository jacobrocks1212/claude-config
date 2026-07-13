# Implementation Phases — Derive multi-commit cycle-commit budget from dispatch sites

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; verified via
`test_lazy_core.py` (pytest) + `lint-skills.py --check-projected --check-capabilities` +
`project-skills.py` / `generate-coupled-skills.py` projection.

---

### Phase 1: `skill_declares_multi_commit` helper + `detect_cycle_bracket_friction` consumption-site swap

**Status:** Complete

**Scope:** Replace `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset-membership consultation
(`detect_cycle_bracket_friction` branch 3) with a new `skill_declares_multi_commit(sub_skill, *,
repo_root=None)` helper modeled directly on `skill_declares_subagent_model` — same repo-scoped-
then-user-level SKILL.md resolution order, same leading-frontmatter-only extraction, same
fail-closed posture (missing file/flag → not multi-commit → conservative single-commit default,
never a crash, never a false negative on the safe side). Retain a small explicit
`_MULTI_COMMIT_PSEUDO_SKILLS` dict for the 2 pseudo-skill identities (`__mark_complete__`,
`__mark_fixed__`) that have no SKILL.md. Retire `_MULTI_COMMIT_DISPATCH_SKILLS` entirely.

**TDD:** yes — new fixtures for `skill_declares_multi_commit` (flagged/unflagged/missing/malformed)
plus an end-to-end `detect_cycle_bracket_friction` case, per the SPEC's own "Regression coverage"
section.

**Deliverables:**
- [x] `_COMMIT_CADENCE_MULTI_FLAG_RE` + `_MULTI_COMMIT_PSEUDO_SKILLS` + `skill_declares_multi_commit()` added to `lazy_core.py`, co-located after `skill_declares_subagent_model`.
- [x] `detect_cycle_bracket_friction` branch (3) rewired to call `skill_declares_multi_commit(ss, repo_root=repo_root)`; `repo_root` threaded as a new optional keyword arg on `detect_cycle_bracket_friction`, supplied by `cycle_end_friction_check` (which already resolves `root`).
- [x] `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset REMOVED from `lazy_core.py` (retirement comment left in its place, naming the replacement mechanism and the stale `retro-feature` history).
- [x] `commit-cadence: multi` frontmatter added to the 7 real skills: `user/skills/execute-plan/SKILL.md`, `user/skills/write-plan/SKILL.md`, `user/skills/spec/SKILL.md`, `user/skills/spec-bug/SKILL.md`, `user/skills/plan-feature/SKILL.md`, `user/skills/plan-bug/SKILL.md`, `repos/algobooth/.claude/skills/mcp-test/SKILL.md`. `retro-feature`'s own SKILL.md deliberately left UNFLAGGED (it is dead/unwired — the missing-row class in reverse: it now correctly reverts to the single-commit default instead of keeping stale membership forever).
- [x] Regression tests: `test_skill_declares_multi_commit_user_level_and_pseudo` (flagged skills → True, unflagged spec-phases/retro-feature → False, pseudo-skill dict, fail-closed shapes, `_MULTI_COMMIT_DISPATCH_SKILLS` genuinely gone) + `test_skill_declares_multi_commit_repo_scoped` (repo-scoped fixture with/without `repo_root`, prose-only-flag miss) + rewritten `test_detect_friction_registry_known_skill_budgeted_without_literal_row` (class-closure via a FRESH fixture SKILL.md never mentioned in `lazy_core.py`, proving the mechanism is general — not a name check — plus a repo-scoped override fixture proving `_MULTI_COMMIT_CEILING_OVERRIDE` composes with the new derivation).
- [x] `test_detect_friction_mcp_test_cycle_multi_commit_within_budget` updated to build a hermetic `repo_root` fixture (mirroring the real AlgoBooth `mcp-test` SKILL.md) and thread it through every `detect_cycle_bracket_friction` call; added a no-`repo_root` control proving the repo-scoped flag genuinely cannot resolve without it (fail-closed, not a crash).
- [x] Post-edit gates run per Fix Scope: `python user/scripts/project-skills.py` (88 skills, 0 errors, 3 repos), `python user/scripts/generate-coupled-skills.py --extract` then `--check` ("all pairs byte-identical"), `python user/scripts/lint-skills.py --check-projected --check-capabilities` (all OK).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "multi_commit" -q` is green; the full suite is green; `lint-skills.py --check-projected --check-capabilities` and `generate-coupled-skills.py --check` both pass after the frontmatter edits.

**Runtime Verification:**
- [x] <!-- verification-only --> A flagged user-level skill (`execute-plan`) is budgeted multi-commit via the derivation with zero hand-maintained registry backing it. **Verified:** `test_skill_declares_multi_commit_user_level_and_pseudo`, `test_detect_friction_registry_known_skill_budgeted_without_literal_row` — GREEN.
- [x] <!-- verification-only --> `retro-feature` (dead, unflagged) now correctly defaults to the single-commit budget instead of keeping stale multi-commit membership. **Verified:** `test_skill_declares_multi_commit_user_level_and_pseudo` asserts `skill_declares_multi_commit("retro-feature") is False`.
- [x] <!-- verification-only --> A repo-scoped skill (`mcp-test`) resolves its flag only when `repo_root` is supplied, and its `_MULTI_COMMIT_CEILING_OVERRIDE` magnitude composes correctly with the new membership derivation. **Verified:** `test_skill_declares_multi_commit_repo_scoped`, `test_detect_friction_mcp_test_cycle_multi_commit_within_budget`, `test_detect_friction_registry_known_skill_budgeted_without_literal_row` (part 3) — GREEN.
- [x] <!-- verification-only --> A brand-new fixture skill flagged ONLY via frontmatter (never mentioned in `lazy_core.py`) gets the multi-commit ceiling with zero core-module edits. **Verified:** `test_detect_friction_registry_known_skill_budgeted_without_literal_row` part 3 — GREEN.

**MCP Integration Test Assertions:** N/A — no app runtime surface; pytest + the skills-projection/lint gates are the verification tier for this repo.

**Prerequisites:** None (first phase). Coordinated with the sibling bug `adhoc-align-cycle-commit-count-with-budget-population` (same code region — this phase landed first, the sibling's noise-allowance cushion on top).

**Files likely modified:**
- `user/scripts/lazy_core.py` — new helper + retired frozenset + `detect_cycle_bracket_friction`/`cycle_end_friction_check` repo_root threading.
- `user/scripts/test_lazy_core.py` — new/rewritten regression tests + `_TESTS` registry update.
- `user/skills/execute-plan/SKILL.md`, `user/skills/write-plan/SKILL.md`, `user/skills/spec/SKILL.md`, `user/skills/spec-bug/SKILL.md`, `user/skills/plan-feature/SKILL.md`, `user/skills/plan-bug/SKILL.md` — frontmatter-only edits.
- `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — frontmatter-only edit.
- `user/scripts/CLAUDE.md` — reconciled the stale `_MULTI_COMMIT_DISPATCH_SKILLS` prose reference (also documents the sibling bug's noise allowance in the same block).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug. Not a checkbox — done out-of-pipeline
this round per `docs/bugs/CLAUDE.md` ("Fixing a bug OUT-OF-PIPELINE").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

Implemented + closed out 2026-07-12 in the same STATE-lane pass as the sibling
`adhoc-align-cycle-commit-count-with-budget-population` (same code region, sequenced this-then-
sibling per operator instruction). Full suite: `python -m pytest user/scripts/test_lazy_core.py -q`
→ 1064 passed; `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py
--test` both green; `python user/scripts/lazy_parity_audit.py --repo-root .` exit 0; `python
user/scripts/doc-drift-lint.py --repo-root .` exit 0 (pre-existing exemptions unrelated to this
change).

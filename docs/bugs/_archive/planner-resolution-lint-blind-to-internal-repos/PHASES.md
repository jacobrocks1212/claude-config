# Implementation Phases — planner-resolution lint is blind to the canonical internal `repos/`

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config lint/script tooling; no app runtime or MCP server
in this repo. Verification is a deterministic script run (`lint-skills.py`) plus the pytest
suite covering `lint_planner_resolution`.

**Coherence-recovery note:** this PHASES.md is authored AFTER the fix already landed. The Fix
Scope's own `**Related:**` line flagged that a prior manual `/harden-harness` pass (Round 25,
commit `8ffd1d0f`, 2026-07-11 23:02) had already resolved `lint_planner_resolution` against the
canonical internal `repos/`, and a follow-on Round-26 consolidation (commit `011aa7d6`,
2026-07-11 23:30) refactored it onto the shared `skill_repos.py` helper. This phase is the
verification record for that pre-landed fix — no production code changed in this session.

---

### Phase 1: Verify `lint_planner_resolution` resolves against the canonical internal `repos/` (pre-landed fix)

**Scope:** Confirm `user/scripts/lint-skills.py::lint_planner_resolution` unions the passed
`--repos-dir` with the canonical, git-tracked `<claude-config>/repos/` (via
`skill_repos.iter_config_repos` + `skill_repos.resolve_internal_repos_root()`), deduplicated by
resolved skills-root path, so the D1 planner-resolution gate no longer depends on the
machine-variable `~/source/repos` symlink layout. Confirm regression coverage exists and is
green, and confirm the gate is clean on this machine.

**TDD:** N/A this session — the fix + its regression tests were authored in commits `8ffd1d0f`
and `011aa7d6`. This phase re-runs and re-reads that existing coverage rather than writing new
tests (no new code path was introduced by this pass).

**Status:** Complete (verified against current `main`, no code changed this session)

**Deliverables:**
- [x] Read `lint_planner_resolution` (`user/scripts/lint-skills.py:219-313`): confirmed it takes
  an explicit `internal_repos_dir: Path | None = None` parameter, resolves
  `repo_skill_roots` via `skill_repos.iter_config_repos(repos_dir, internal_repos_dir,
  ".claude/skills")`, and that `main()` (`:406-411`) always passes
  `resolve_internal_repos_root()` in production — so the real invocation unions the internal
  repos regardless of `~/source/repos` layout, matching the Fix Scope exactly.
- [x] Confirmed the shared helper `user/scripts/skill_repos.py` exists
  (`resolve_internal_repos_root()` + `iter_config_repos()`), landed in `011aa7d6` as the
  structural consolidation the SIBLING bug's Fix Scope called for (this bug's own Fix Scope only
  required the union, not the shared module — the consolidation is a superset, not a deviation).
- [x] Confirmed regression coverage in `user/scripts/test_project_skills.py`: the six
  `test_planner_resolution_*` tests (`:932-1021`, incl. `test_planner_resolution_real_tree_is_clean`
  pinning the live claude-config tree) call `lint.lint_planner_resolution(repos, user_skills)`
  with NO `internal_repos_dir` argument — i.e. it defaults to `None`, so the synthetic fixtures
  stay hermetic (the sibling bug's "secondary defect: stale non-hermetic lint test" is resolved —
  `internal_repos_dir` being an explicit opt-in parameter is exactly what restores hermeticity).
- [x] `python -m pytest user/scripts/test_project_skills.py user/scripts/test_lint_skills.py -q`
  → **44 passed** (includes all six planner-resolution fixtures).
- [x] `python user/scripts/lint-skills.py --check-projected --check-capabilities` on this
  machine → exit 0, `OK — planner resolution: write-plan-cognito resolves; no
  execute-plan-cognito fork.` (the exact RED-turned-GREEN gate from the SPEC's reconstructed
  route).

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py --check-projected
--check-capabilities` exits 0 with the planner-resolution line reading `OK`, on a machine where
`~/source/repos` does not contain sibling checkouts of the repo-scoped-skill repos (the exact
symptom machine described in the SPEC).

**Runtime Verification** *(no app runtime in this repo — verified via the lint script + pytest,
the established harness for this class of check)*:
- [x] <!-- verification-only --> `python user/scripts/lint-skills.py --check-projected
  --check-capabilities` exits 0 (RC=0), planner-resolution line reads `OK — planner resolution:
  write-plan-cognito resolves; no execute-plan-cognito fork.` **Verified 2026-07-12** (this
  session): ran via a temp-file-captured invocation to read `RC` cleanly; output matched
  verbatim.
- [x] <!-- verification-only --> `python -m pytest user/scripts/test_project_skills.py
  user/scripts/test_lint_skills.py -q` is green. **Verified 2026-07-12:** `44 passed in 1.11s`.

**MCP Integration Test Assertions:** N/A — no MCP/app runtime surface in this repo; the lint
script run above IS the runtime-observable behavior for this gate.

**Prerequisites:** None (first and only phase — verification of a pre-landed fix).

**Files likely modified:** None this session (verification only). Files inspected:
`user/scripts/lint-skills.py`, `user/scripts/skill_repos.py`,
`user/scripts/test_project_skills.py`.

**Testing Strategy:** Re-run the existing pytest suite + the exact gate command named in the
SPEC's reconstructed route; confirm both are green with no code changes.

**Integration Notes for Next Phase:** None — final phase. The sibling bug
(`project-skills-under-projects-machine-variable-repos-dir`) shares the same `skill_repos.py`
consolidation and is closed alongside this one.

**Completion (gate-owned):** this bug is closed via operator-directed-interactive provenance in
this session (not the autonomous `__mark_fixed__` pipeline gate) — see `FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

**Coherence-recovery close-out (2026-07-12):** Verified the fix landed in prior commits
(`8ffd1d0f`, `011aa7d6`), re-ran the gate + pytest suite green, authored this PHASES.md and
`FIXED.md` as the verification record. No production code touched.

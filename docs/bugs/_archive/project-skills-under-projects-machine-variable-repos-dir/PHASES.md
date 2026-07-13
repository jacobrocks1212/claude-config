# Implementation Phases — `project-skills.py` silently under-projects (machine-variable `--repos-dir` default)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config lint/projection tooling; no app runtime or MCP
server in this repo. Verification is a deterministic script run (`project-skills.py`) plus the
pytest suite covering `project_all` / `skill_repos`.

**Coherence-recovery note:** this PHASES.md is authored AFTER the fix already landed. The
`**Related:**` line names this as "the FIRST fix of this same root-cause class... Round 25 /
commit `8ffd1d0`" for the SIBLING bug, and this bug's own Proposed Fix Scope (Step 3) is the
structural consolidation carried out in commit `011aa7d6` (2026-07-11 23:30) — new shared
`user/scripts/skill_repos.py`, `project_all` gaining an injectable `internal_repos_dir`, and
`lint_planner_resolution` refactored onto the same helper. This phase is the verification record
for that pre-landed fix — no production code changed in this session.

---

### Phase 1: Verify `project_all` unions the canonical internal `repos/` via the shared `skill_repos` helper (pre-landed fix)

**Scope:** Confirm `user/scripts/project-skills.py::project_all` no longer scans ONLY the
machine-variable `--repos-dir`, but unions it with the canonical, git-tracked
`<claude-config>/repos/` via the new shared module `user/scripts/skill_repos.py`
(`resolve_internal_repos_root()` + `iter_config_repos()`), exactly as the Fix Scope's three-step
plan specifies (shared helper → `project-skills.py` consumer → `lint-skills.py` consumer sharing
the same helper). Confirm the secondary defect (`test_project_skills.py`'s stale non-hermetic
lint test) is resolved, and confirm the default invocation now discovers `algobooth` and
`cognito-forms` on this machine instead of silently omitting them.

**TDD:** N/A this session — the fix + its regression tests were authored in commit `011aa7d6`
(the same commit that closed the sibling bug's structural-consolidation half). This phase
re-runs and re-reads that existing coverage rather than writing new tests (no new code path was
introduced by this pass).

**Status:** Complete (verified against current `main`, no code changed this session)

**Deliverables:**
- [x] Read `user/scripts/skill_repos.py` in full: `resolve_internal_repos_root()` derives
  `<claude-config>/repos/` from the module's own location (`Path(__file__).resolve().parents[2] /
  "repos"`) — machine-independent, matching Fix Scope item 1. `iter_config_repos(repos_dir,
  internal_repos_dir, marker)` yields the union of both bases, deduplicated by the RESOLVED
  `repo/<marker>` path (a symlinked sibling is not double-counted; the passed `repos_dir` wins on
  collision) — matching Fix Scope item 1 exactly, including the dedup requirement.
- [x] Read `user/scripts/project-skills.py`: `project_all` (`:251-303`) now takes an injectable
  `internal_repos_dir: Optional[Path] = None` param and iterates
  `iter_config_repos(repos_dir, internal_repos_dir, ".claude/skill-config")` — matching Fix Scope
  item 2. `main()` (`:343-350`) resolves `internal_repos_dir = resolve_internal_repos_root()` and
  passes it through, and the repo-discovery gate at `:345` is `if repos_dir.exists() or
  internal_repos_dir.exists():` — so a real invocation unions the internal repos regardless of
  the host's `~/source/repos` layout, matching the symptom fix exactly.
- [x] Confirmed `lint-skills.py::lint_planner_resolution` consumes the SAME `skill_repos` module
  (Fix Scope item 3 — `from skill_repos import iter_config_repos, resolve_internal_repos_root` at
  `user/scripts/lint-skills.py:24`), retiring the duplicated inline union logic Round-25's
  `8ffd1d0` had added — a single source of truth for both callers, as specified.
- [x] Confirmed the secondary defect is resolved: `internal_repos_dir` is an explicit opt-in
  parameter (default `None`) rather than a hidden `__file__`-derived reach, so
  `test_project_skills.py::test_planner_resolution_flags_missing_cognito_planner` (which calls
  `lint_planner_resolution(repos, user_skills)` with no third argument) is hermetic again — the
  synthetic fixture with no `write-plan-cognito` anywhere correctly raises the finding.
- [x] Confirmed regression coverage for the union itself: `test_project_all_unions_internal_repos_dir`,
  `test_project_all_internal_repos_default_none_is_hermetic`, plus `skill_repos`-level dedup and
  `resolve_internal_repos_root` tests (`user/scripts/test_project_skills.py:514-628`).
- [x] `python -m pytest user/scripts/test_project_skills.py user/scripts/test_lint_skills.py -q`
  → **44 passed**.
- [x] `python user/scripts/project-skills.py` (no `--repos-dir`, default machine-variable
  `~/source/repos`) on this machine → `Repos discovered: 3` — `claude-config`, `algobooth`
  (`caps=[mcp]`), `cognito-forms` — confirming `algobooth` and `cognito-forms` are no longer
  silently omitted from the default run.

**Minimum Verifiable Behavior:** `python user/scripts/project-skills.py` (default, no
`--repos-dir` override) discovers and projects `algobooth` and `cognito-forms` alongside
`_default`, on a machine where the host's `~/source/repos` layout would otherwise have omitted
them — matching the SPEC's exact reconstructed-route symptom, now fixed.

**Runtime Verification** *(no app runtime in this repo — verified via the projection script +
pytest, the established harness for this class of check)*:
- [x] <!-- verification-only --> `python user/scripts/project-skills.py` (default) exits 0 and
  reports `Repos discovered   : 3` including `algobooth: ... caps=[mcp]` and `cognito-forms: ...`.
  **Verified 2026-07-12** (this session): ran via a temp-file-captured invocation to read `RC`
  cleanly (`RC=0`); full output matched.
- [x] <!-- verification-only --> `python -m pytest user/scripts/test_project_skills.py
  user/scripts/test_lint_skills.py -q` is green. **Verified 2026-07-12:** `44 passed in 1.11s`.

**MCP Integration Test Assertions:** N/A — no MCP/app runtime surface in this repo; the
projection script run above IS the runtime-observable behavior for this gate.

**Prerequisites:** None (first and only phase — verification of a pre-landed fix).

**Files likely modified:** None this session (verification only). Files inspected:
`user/scripts/project-skills.py`, `user/scripts/skill_repos.py`,
`user/scripts/test_project_skills.py`, `user/scripts/lint-skills.py`.

**Testing Strategy:** Re-run the existing pytest suite + the exact default-invocation command
named in the SPEC's reconstructed route; confirm both are green with no code changes and that
the previously-omitted repos now appear.

**Integration Notes for Next Phase:** None — final phase. The sibling bug
(`planner-resolution-lint-blind-to-internal-repos`) shares the same `skill_repos.py`
consolidation and is closed alongside this one.

**Completion (gate-owned):** this bug is closed via operator-directed-interactive provenance in
this session (not the autonomous `__mark_fixed__` pipeline gate) — see `FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

**Coherence-recovery close-out (2026-07-12):** Verified the fix landed in prior commit
`011aa7d6` (which also structurally consolidated the sibling bug's fix onto the same
`skill_repos.py` helper), re-ran the gate + pytest suite green, authored this PHASES.md and
`FIXED.md` as the verification record. No production code touched.

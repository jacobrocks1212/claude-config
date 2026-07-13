---
kind: implementation-plan
feature_id: skill-config-schema-and-reference-lint
status: Complete
created: 2026-07-12
complexity: complex
phases: [0, 1, 2, 3]
---

> **Plan** — single self-contained part covering all 4 phases (0-3).
> Executed inline by this lane (spec-implementation batch, 2026-07-12).

# Implementation Plan — skill-config-schema-and-reference-lint (Phases 0-3)

**PHASES.md:** `docs/features/skill-config-schema-and-reference-lint/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/skill-config-schema-and-reference-lint/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), test-first for the new script. Never invoke `/lazy` or `/lazy-batch`
> recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest user/scripts/test_lint_skill_config.py -q
python3 user/scripts/lint-skill-config.py --repo-root .
python3 user/scripts/lint-skills.py --check-skill-config
python3 user/scripts/lint-skills.py --check-projected --check-capabilities
python3 user/scripts/project-skills.py
python3 user/scripts/kpi-scorecard.py --lint --repo-root .
```

## Key design contract (read before WU-0.1)

- **New sibling script, not a deep lint-skills.py rewrite:** `lint-skill-config.py` owns the
  manifest/JSON-schema/reference-sweep logic; `lint-skills.py` gets one small additive
  `--check-skill-config` flag (default off, byte-identical without it) per the ownership rule
  that concurrent lanes may be touching `lint-skills.py` for other reasons.
- **DRY via `importlib`, not duplication:** `lint-skill-config.py` loads `lint-skills.py` as a
  module (mirroring `test_doc_drift_lint.py`'s own `_load_module` pattern) to reuse
  `_FALLBACK_CAT` / `_FALLBACK_ECHO` verbatim rather than re-deriving the regex forms.
  file-ownership: only `lint-skills.py`'s CLI section gets a small additive edit; the reference
  regex forms themselves are read, never modified.
- **`SUPPRESSIONS` is script-owned, not an inline skill-file comment** — the two real
  fallback-less-pointer findings this run discovered live in files outside this feature's
  ownership (`user/skills/lazy-batch/SKILL.md`, `lazy-bug-batch/SKILL.md`,
  `_components/lazy-dispatch-template.md` — SKILLS lane). Reason-required, printed as a
  WARNING (visible, never silent).
- **Manifests are hand-authored, not lint-generated:** the lint's job is to VALIDATE a
  manifest, not author one. Both real manifests were built by running the lint iteratively
  (bootstrap-then-fix loop) against the real tree until 0 errors.
- **No runtime strictness added anywhere:** every check here is authoring-time
  (`lint-skill-config.py` exit code); no hook, no skill dispatch, no fallback behavior changes.

---

## Phase 0 — Quick win: commit-policy.md

- [x] WU-0.1 — Grep `repos/algobooth/*.md` for any AlgoBooth-specific commit convention
  (none found) — confirms the pointer-adoption file needs zero deltas from the generic
  default.
- [x] WU-0.2 — `repos/algobooth/.claude/skill-config/commit-policy.md` — pointer-adoption
  content citing `_components/commit-and-push.md` verbatim + the personal-repo push note.

## Phase 1 — Manifest schema + authored manifests + JSON-schema checkers

- [x] WU-1.1 — `user/scripts/test_lint_skill_config.py` written first (schema fixtures,
  bidirectional-check fixtures, `build-queue-ops.json` fixtures) against the not-yet-existing
  module — failing on import, as expected.
- [x] WU-1.2 — `user/scripts/lint-skill-config.py`: `validate_manifest`,
  `bidirectional_provides_check`, `check_build_queue_ops`, `JSON_SCHEMA_CHECKERS`,
  `discover_repo_names`, `run()` orchestration wiring for the manifest + JSON-schema halves
  only (reference sweep stubbed as a later WU). Fixtures green.
- [x] WU-1.3 — Real repo census: enumerated every on-disk skill-config file per repo (21
  algobooth, 16 cognito-forms, pre-Phase-0) via `ls`; enumerated every
  `.claude/skill-config/<file>` mention across `user/skills/` + `repos/*/.claude/skills/` via
  `grep -rn`.
- [x] WU-1.4 — `repos/algobooth/.claude/skill-config/MANIFEST.json` +
  `repos/cognito-forms/.claude/skill-config/MANIFEST.json` authored from the WU-1.3 census;
  iterated against a first `lint-skill-config.py --repo-root .` run until manifest-schema +
  bidirectional-provides errors were zero.

## Phase 2 — Reference sweep

- [x] WU-2.1 — `scan_source_for_refs` + `_SKILL_CONFIG_REF` prose regex + `_PROSE_FALLBACK_
  HINTS` heuristic + `_check_refs_against_repo`; wired into `run()`.
- [x] WU-2.2 — First live run surfaced 3 false-positive classes (fixed, not suppressed): a
  stray trailing-period capture (regex anchored on real extensions), 4 self-referential
  `_components/<name>.md` mentions of their own override path (self-reference exclusion
  added), and confirmed 2 genuine dead-pointer findings + 1 aspirational mention.
- [x] WU-2.3 — `SUPPRESSIONS` allowlist authored for the 2 dead-pointer + 1 aspirational
  finding (each reasoned); re-ran to 0 errors, 6 documented warnings.
- [x] WU-2.4 — Small additive `--check-skill-config` hook-in on `lint-skills.py` (flag +
  ~15-line dispatch block); confirmed the flag-less invocation is byte-identical.
- [x] WU-2.5 — `test_lint_skill_config.py` extended: dangling-reference, fallback-less-pointer
  (declared+no-fallback), intended-absent-with-fallback OK, suppression downgrade,
  missing/malformed manifest, unregistered-JSON warning, `build-queue-ops.json` schema error
  surfacing through `run()`, repo-scoped isolation, self-reference exclusion, and the real-tree
  self-check (`test_this_repo_is_clean`). 29 tests total, all green.
- [x] WU-2.6 — Full gate suite run: `pytest test_lint_skill_config.py` (29 passed),
  `lint-skill-config.py --repo-root .` (0 errors, 6 warnings), `lint-skills.py
  --check-skill-config` (folds cleanly), `lint-skills.py --check-projected
  --check-capabilities` (clean), `project-skills.py` (clean, 88 skills / 97 components / 3
  repos), `lazy_parity_audit.py --repo-root .` (clean), `pytest test_lint_skills.py` (3
  passed, unaffected by the additive flag).

## Phase 3 — KPI registry follow-up

- [x] WU-3.1 — `docs/kpi/registry.json`: appended the SPEC-drafted
  `skill-config-broken-reference-reads` row verbatim (source: `deny-ledger`, selector:
  `process-friction-count`, both already-registered enum values — no new selector code
  needed for the coarse-proxy channel).
- [x] WU-3.2 — `kpi-scorecard.py --lint --repo-root .` green; `kpi-scorecard.py --repo-root .`
  regenerated `docs/kpi/SCORECARD.md`.

## Final integration checklist

- [x] All four phases' checkboxes ticked in `PHASES.md`.
- [x] `NEEDS_INPUT_PROVISIONAL.md` recorded for D1/D4 (park-provisional protocol — both
  isolated-divergence, recommendation-first, auto-provisional-accepted; ratification
  outstanding).
- [x] `SPEC.md` Design Decisions annotated RESOLVED (D1/D4 → provisional; D2/D3 →
  auto-accepted) and Open Questions resolved in place.
- [x] `SKIP_MCP_TEST.md` (this feature has no MCP-reachable surface).
- [x] `**Friction-reduction feature:** yes` + `## KPI Declaration` already present in
  `SPEC.md` (drafted at SPEC-authoring time) — re-verified against the now-registered row.

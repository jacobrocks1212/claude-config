# Stub-Origin Provisional Exclusion — Implementation Phases

**Status:** Complete
**Spec:** [SPEC.md](SPEC.md)
**Last updated:** 2026-07-09
**MCP runtime:** not-required — one `lazy_core` predicate clause + component/skill prose + `--test` fixtures; no app surface. Validation is the state scripts' `--test` harnesses, regenerated baselines, `pytest test_lazy_core.py`, `lazy_parity_audit.py` — the Step-9 gate grants the structural MCP-skip.

Single-session implementation (autonomous).

---

### Phase 1: Predicate + fixtures

**Status:** Complete
**Phase kind:** design

- [x] `lazy_core.provisional_eligibility`: `stub_origin` present-and-not-explicitly-false → excluded (fail-closed on malformed values)
- [x] `lazy-state.py --test` fixture: otherwise-eligible sentinel + `stub_origin: true` → parked, not routed
- [x] `bug-state.py --test` mirror fixture
- [x] Baselines regenerated via `_normalize_smoke_output`; baseline pytest green

### Phase 2: Schema + prompt + skill addenda

**Status:** Complete
**Phase kind:** design

- [x] `sentinel-frontmatter.md`: `stub_origin` key + provisional-rule condition (6) + tier-summary update
- [x] `cycle-base-prompt.md` D13 park-spec section: mandatory `stub_origin: true` on stub-spec sentinels
- [x] `input-audit-prompt.md` step 7c: stub-origin verify/backstop duty
- [x] `spec/SKILL.md` Phase-1-under-batch step 4: sentinel carries `stub_origin: true`
- [x] `spec-bug/SKILL.md` batch path: pre-conclusion sentinel carries `stub_origin: true`
- [x] `lazy-batch/SKILL.md` `--park-provisional` bullet: never-provisional list names stub-origin

### Phase 3: Verification

**Status:** Complete
**Phase kind:** design

#### Runtime Verification / MCP Integration Test

- [x] `python3 user/scripts/lazy-state.py --test` + `bug-state.py --test` green (new fixtures)
- [x] baseline pytest tests green; `python3 -m pytest user/scripts/test_lazy_core.py -k emit_cycle_prompt` green
- [x] `lazy_parity_audit.py --repo-root .` exit 0; `project-skills.py` + `lint-skills.py` clean

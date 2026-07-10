# Park-Provisional Acceptance — Implementation Phases

**Status:** In-progress
**Spec:** [SPEC.md](SPEC.md)
**Last updated:** 2026-07-09

Single-session implementation (autonomous). Phases ordered by load-bearing-ness: shared core → feature state machine → bug parity → schema/prompt components → orchestrator skills → verification.

---

### Phase 1: Shared core (`lazy_core.py`)

**Status:** Complete
**Phase kind:** design

- [x] `PROVISIONAL_SENTINEL` filename constant + `build_parked_entry` gains `sentinel_kind: "provisional"` for `NEEDS_INPUT_PROVISIONAL.md`
- [x] `provisional_eligibility(sentinel_path)` — deterministic fail-closed predicate (SPEC D3/D4/D8): kind/decisions checks, two-key-mechanical precedence, `written_by: completion-integrity-gate` exclusion, divergence two-key (`divergence` + `audit_divergence` ∈ {isolated, contained}), rich-body structural check (`## Decision Context` + ≥len(decisions) `**Recommendation:**`)
- [x] `provisionalize_sentinel(path, repo_root)` — re-validate, extract recommended labels per H3, append `## Resolution` (`resolved_by: auto-provisional`, `decision_commit`), git-mv-aware rename to `NEEDS_INPUT_PROVISIONAL.md`; zero writes on refusal
- [x] `apply_pseudo` `__mark_complete__` / `__mark_fixed__` refusal while `NEEDS_INPUT_PROVISIONAL.md` exists (SPEC D6 layer c)
- [x] `emit_cycle_prompt` `park_mode` param + `@section` `park=` filter attribute (SPEC D13; default `both`, byte-identical when absent)

### Phase 2: Feature state machine (`lazy-state.py`)

**Status:** Complete
**Phase kind:** design

- [x] `--park-provisional` CLI flag (hard error without `--park-needs-input`) threaded into `compute_state(park_provisional=)`
- [x] Walk-loop routing: eligible sentinel + both flags → `__provisional_accept__` route (`Step 3.5: needs-input (provisional accept)`); ineligible → park as today with `_diag` reason
- [x] Step 3.6: non-park `needs-ratification` halt on `NEEDS_INPUT_PROVISIONAL.md` (NEEDS_INPUT.md precedence when both exist)
- [x] Park-mode Step 10: park (`sentinel_kind: provisional`) instead of emitting `__mark_complete__`
- [x] `provisional[]` probe key (park mode only, mirrors `parked[]` gating)
- [x] `--provisionalize-sentinel <path>` CLI action
- [x] `--emit-prompt` threads park flags into `emit_cycle_prompt(park_mode=)`
- [x] `--test` fixtures: eligible route, structural park, single-key park, two-key-mechanical precedence, workable-under-park, needs-ratification, both-sentinels precedence, Step-10 park, provisionalize action happy/refuse, apply-pseudo refusal, non-park byte-identity, flag validation

### Phase 3: Bug-pipeline parity (`bug-state.py`)

**Status:** Complete
**Phase kind:** design

- [x] Mirror flag, predicate call, `__provisional_accept__` route, `needs-ratification`, mark-fixed-emission park, `provisional[]` key, `--provisionalize-sentinel`, `--emit-prompt` threading
- [x] `--test` fixtures mirroring Phase 2's
- [x] `lazy_parity_audit.py --repo-root .` exit 0

### Phase 4: Schema + prompt components

**Status:** Complete
**Phase kind:** design

- [x] `sentinel-frontmatter.md`: `divergence` / `audit_divergence` fields, grade vocabulary, `NEEDS_INPUT_PROVISIONAL.md` lifecycle row, `resolved_by: auto-provisional` + `## Ratification` markers, three-tier decision table
- [x] `input-audit-prompt.md`: independent `audit_divergence` grading duty (Key 2)
- [x] `cycle-base-prompt.md`: `park=park` `skills=spec` sentinel-mediation section (SPEC D13) + producer `divergence:` self-grade guidance
- [x] New `provisional-ratification.md` shared component (ratify / redirect / defer affordance)
- [x] `parked-flush.md`: Step 2.7 provisional branch (partition `sentinel_kind: provisional`; run the ratification affordance)
- [x] `completion-integrity-gate.md`: precondition 2c (unratified provisional refuses)
- [x] `dispatch-apply-resolution.md`: `resolution_kind: provisional` (propagate, never neutralize) + `resolution_kind: ratify-redirect` (propagate + corrective phase scoped by `decision_commit` + neutralize) sections

### Phase 5: Orchestrator skills

**Status:** Complete
**Phase kind:** design

- [x] `lazy-batch/SKILL.md`: argument-hint + Step 0 parsing, Step 1a probe flag, Step 1c.5 `__provisional_accept__` pseudo-skill, `needs-ratification` terminal routing (Step 1g-ratify), §1c.6 provisional-accept notification, batch-report digest table, stub-spec disambiguation park-mode row
- [x] `lazy-bug-batch/SKILL.md` + `lazy-batch-cloud/SKILL.md`: parity mirrors (argument surface + terminal tables)
- [x] `lazy-batch-parallel/SKILL.md`: `--park-provisional` pass-through + lane-local acceptance note (SPEC D10)

### Phase 6: Verification

**Status:** Complete
**Phase kind:** design

#### Runtime Verification / MCP Integration Test

- [x] `python3 user/scripts/lazy-state.py --test` green (incl. new fixtures)
- [x] `python3 user/scripts/bug-state.py --test` green (incl. new fixtures)
- [x] `python3 -m pytest user/scripts/test_lazy_core.py` green
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root .` exit 0
- [x] `python3 user/scripts/kpi-scorecard.py --lint --spec docs/features/park-provisional-acceptance/SPEC.md` OK
- [x] `python ~/.claude/scripts/project-skills.py` + `lint-skills.py` clean; projected output spot-checked

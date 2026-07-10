# Workstation Recursive Sub-Subagent Dispatch — Implementation Phases

**Status:** Complete
**Spec:** [SPEC.md](SPEC.md)
**Last updated:** 2026-07-09
**MCP runtime:** not-required — claude-config harness prose (cycle-prompt template + SKILL.md contracts) plus one pytest anchor swap; no app surface. Validation is `pytest test_lazy_core.py`, the state scripts' `--test` harnesses, `lazy_parity_audit.py`, projection + skill lint — the Step-9 gate grants the structural MCP-skip.

Single-session implementation (autonomous).

---

### Phase 1: Prompt template + pinned test

**Status:** Complete
**Phase kind:** design

- [x] `cycle-base-prompt.md`: replace the workstation `inline-override` section with the `workstation-dispatch` section (marker `WORKSTATION DISPATCH — LOAD-BEARING`; guardrails per SPEC D3); cloud-override byte-untouched; header rule-inventory R3 row updated
- [x] `test_lazy_core.py` binding-matrix workstation anchor → new marker (cloud anchor unchanged); tests green

### Phase 2: Skill prose (lazy-batch + parallel + retro)

**Status:** Complete
**Phase kind:** design

- [x] `lazy-batch/SKILL.md`: rewrite the "Cycle-subagent execution model" paragraph + the TDD-tradeoff note for the lift (cloud/pre-lift scoping)
- [x] `lazy-batch-parallel/SKILL.md`: lanes follow the workstation dispatch-permitted model
- [x] `lazy-batch-retro/SKILL.md`: branch 2 re-scoped historical (old-marker-gated); R-O-4 named-clause list + R-O-9 parenthetical updated

### Phase 3: Verification

**Status:** Complete
**Phase kind:** design

#### Runtime Verification / MCP Integration Test

- [x] `python3 -m pytest user/scripts/test_lazy_core.py -k emit_cycle_prompt` green; full baseline tests green (template change alters no fixture output)
- [x] `python3 user/scripts/lazy-state.py --test` + `bug-state.py --test` green
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root .` exit 0; `project-skills.py` + `lint-skills.py` clean; projected lazy-batch spot-checked

### Phase 4 (post-completion follow-up, 2026-07-10): dispatch-guard allow branch

**Status:** Complete
**Phase kind:** corrective

The original rollout lifted the ban in prose and fixed the *containment* hook but
overlooked the *dispatch* guard (`lazy_guard.py`), which kept denying every
workstation sub-subagent dispatch under a live run marker and booking a no-op
hardening debt per denial. Root-caused and fixed via
`docs/bugs/dispatch-guard-denies-workstation-subsubagent-split/` after the
operator resolved `turn-routing-enforcement` decision 4 (active-cycle-marker
exemption keyed on a general `subagent-model: true` SKILL-frontmatter capability
+ consumed-emission fence; cloud keeps the unconditional deny).

- [x] `lazy_guard.py` branch 2b (workstation sub-subagent exemption, fail-closed)
- [x] `lazy_core.py` capability predicate + consumed fence + `worker_subdispatch` audit + cycle-marker stamping
- [x] `subagent-model: true` frontmatter on the ten sub-subagent-model skills
- [x] 4 unit + 5 guard pipe-tests; all four suites green

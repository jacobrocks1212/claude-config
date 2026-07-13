---
kind: fixed
feature_id: adhoc-derive-multi-commit-budget-from-dispatch-sites
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py) + both state scripts' --test smoke harnesses + skills-projection/lint gates; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

adhoc-derive-multi-commit-budget-from-dispatch-sites marked Fixed on 2026-07-12 during an
operator-directed multi-item STATE-lane close-out pass. This receipt was written by the
orchestrating subagent, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`.

## Notes

Implemented per the SPEC's own recommended fix (Theory 2 / the working `skill_declares_subagent_model`
precedent): `lazy_core.skill_declares_multi_commit(sub_skill, *, repo_root=None)` replaces the
hand-maintained `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset (now removed) as the input to
`detect_cycle_bracket_friction`'s commit-budget derivation, reading a `commit-cadence: multi`
SKILL.md frontmatter flag with the same repo-scoped-then-user-level resolution order and
fail-closed posture as its model. `commit-cadence: multi` was added to the 7 real skills
(`execute-plan`, `write-plan`, `spec`, `spec-bug`, `plan-feature`, `plan-bug`,
`repos/algobooth/.claude/skills/mcp-test`); the 2 pseudo-skills (`__mark_complete__`,
`__mark_fixed__`) keep a small explicit dict. `retro-feature` — confirmed dead/unwired — is
deliberately left unflagged and correctly reverts to the single-commit default.

Coordinated with the sibling bug `adhoc-align-cycle-commit-count-with-budget-population` (same
code region, same session): this bug's fix landed first, the sibling's `_CYCLE_COMMIT_NOISE_ALLOWANCE`
cushion landed on top of it.

Verification: `python -m pytest user/scripts/test_lazy_core.py -q` → 1064 passed (net +1 vs. the
pre-change 1063 — one old registry-membership test replaced by two new
`skill_declares_multi_commit` tests). `python user/scripts/lazy-state.py --test` and `python
user/scripts/bug-state.py --test` — all smoke tests passed. `python
user/scripts/lazy_parity_audit.py --repo-root .` → exit 0. `python user/scripts/doc-drift-lint.py
--repo-root .` → exit 0 (2 pre-existing, unrelated exemptions). Skills gates:
`python user/scripts/project-skills.py` (88 skills / 0 errors / 3 repos),
`python user/scripts/generate-coupled-skills.py --extract` then `--check` ("all pairs
byte-identical"), `python user/scripts/lint-skills.py --check-projected --check-capabilities`
(all OK).

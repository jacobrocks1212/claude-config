---
kind: fixed
feature_id: project-skills-under-projects-machine-variable-repos-dir
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: script-run (project-skills.py) + pytest (NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

project-skills-under-projects-machine-variable-repos-dir marked fixed on 2026-07-12 by an
operator-directed lint-lane bug-fix pass. This receipt is written by the operator's subagent, not
the pipeline's `__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`.

## Notes

The fix was already implemented in a prior session: commit `011aa7d6` (2026-07-11 23:30,
"harden(script): consolidate internal-repos union into skill_repos; fix project-skills
under-projection") added the shared `user/scripts/skill_repos.py` helper
(`resolve_internal_repos_root()` + `iter_config_repos()`) and refactored both
`project-skills.py::project_all` (gained an injectable `internal_repos_dir`, defaulted in `main()`
to `resolve_internal_repos_root()`) and `lint-skills.py::lint_planner_resolution` onto it — exactly
the "structural consolidation" the SPEC's Fix Scope called for as the class's second instance. This
session verified the fix on disk, re-ran the gate + test suite, and authored `PHASES.md` + this
receipt as the paperwork close-out — no production code changed.

## Symptom Reproduction (before/after gate output)

**Root cause (one sentence):** `project-skills.py::project_all` scanned only the machine-variable
`--repos-dir` (default `~/source/repos`) for repos with `.claude/skill-config/`, so on a machine
without the sibling-checkout symlink layout it silently omitted the canonical internal
`<claude-config>/repos/<name>/.claude/skill-config/` projections (`algobooth`, `cognito-forms`)
with exit 0 — an invisible under-projection.

**Gate (this session, verbatim):**
```
python user/scripts/project-skills.py
Skills projected (_default): 88
Components resolved (_default): 97
Errors (_default)  : none
Repos discovered   : 3
  claude-config: 88 skills, 97 components, 1 skipped caps=[]
  algobooth: 88 skills, 97 components caps=[mcp]
  cognito-forms: 88 skills, 97 components, 1 skipped caps=[]
RC=0
```
`algobooth` and `cognito-forms` are now discovered by the DEFAULT invocation (no `--repos-dir`
override needed) — the exact under-projection the SPEC's reconstructed route documents is fixed.

**Tests (this session, verbatim):**
```
python -m pytest user/scripts/test_project_skills.py user/scripts/test_lint_skills.py -q
44 passed in 1.11s
```

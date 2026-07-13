---
kind: fixed
feature_id: planner-resolution-lint-blind-to-internal-repos
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: script-run (lint-skills.py --check-projected --check-capabilities) + pytest (NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

planner-resolution-lint-blind-to-internal-repos marked fixed on 2026-07-12 by an operator-directed
lint-lane bug-fix pass. This receipt is written by the operator's subagent, not the pipeline's
`__mark_fixed__` gate — provenance is deliberately `operator-directed-interactive`.

## Notes

The fix was already implemented in a prior session: commit `8ffd1d0f` (2026-07-11 23:02, "harden(script):
resolve D1 planner check against canonical internal repos/") made `lint_planner_resolution`
(`user/scripts/lint-skills.py`) union the passed `--repos-dir` with the canonical, git-tracked
`<claude-config>/repos/`, and commit `011aa7d6` (2026-07-11 23:30) refactored it onto the shared
`user/scripts/skill_repos.py` helper (`resolve_internal_repos_root()` + `iter_config_repos()`) as
part of closing the sibling bug. This session verified the fix on disk, re-ran the gate + test
suite, and authored `PHASES.md` + this receipt as the paperwork close-out — no production code
changed.

## Symptom Reproduction (before/after gate output)

**Root cause (one sentence):** `lint_planner_resolution` defaulted repo-skill-root discovery to
the machine-variable `~/source/repos` instead of the canonical, always-present, git-tracked
`<claude-config>/repos/`, so on a machine without the sibling-checkout symlink layout it found
zero repo skill roots and falsely reported `write-plan-cognito` as missing.

**Gate (this session, verbatim):**
```
python user/scripts/lint-skills.py --check-projected --check-capabilities
OK — no broken or embedded !cat patterns found.
OK — planner resolution: write-plan-cognito resolves; no execute-plan-cognito fork.
OK — no unexpanded !cat patterns in projected output (C:\Users\Jacob\.claude\skills-projected).
Known capability namespaces: lazy-batch-prompts, mcp
OK — no capability namespace pollution detected.
RC=0
```

**Tests (this session, verbatim):**
```
python -m pytest user/scripts/test_project_skills.py user/scripts/test_lint_skills.py -q
44 passed in 1.11s
```

Both confirm the gate is GREEN and the regression coverage (incl.
`test_planner_resolution_real_tree_is_clean`, which pins the live claude-config tree) passes on
this machine.

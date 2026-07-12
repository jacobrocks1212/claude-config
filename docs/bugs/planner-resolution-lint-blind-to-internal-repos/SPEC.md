# planner-resolution lint is blind to the canonical internal `repos/` — RED on clean `main` — Investigation Spec

> On a clean `main`, `python user/scripts/lint-skills.py --check-projected --check-capabilities`
> exits 1 with a single finding: *"Cognito planner not found: no `write-plan-cognito` skill
> resolves under any repos/\*/.claude/skills/ (D1 rename must be present)"* — even though the
> `write-plan-cognito` skill IS present and git-tracked at
> `repos/cognito-forms/.claude/skills/write-plan-cognito/`. The D1 planner-resolution gate is a
> standing false failure on this machine.

**Status:** Concluded
**Severity:** P2 (a mandatory harness quality gate is RED on clean `main`, on at least one of the operator's machines)
**Discovered:** 2026-07-11 (manual `/harden-harness`, trigger 5)
**Root-cause class:** script-defect
**Related:** `docs/features/plan-skills-redesign/SPEC.md` (D1 — Deterministic planner resolution); `docs/bugs/_archive/adhoc-write-plan-cognito-planner-contract-read/SPEC.md` (same skill, prior verification showed the gate GREEN)

---

## Reconstructed route (Step 1)

- **Gate invoked:** `lint-skills.py --check-projected --check-capabilities` (the canonical
  skill-plane gate — `.claude/skill-config/quality-gates.md:11`), no `--repos-dir` → default
  `~/source/repos`.
- **Divergence:** `lint_planner_resolution(repos_dir, user_skills_dir)`
  (`user/scripts/lint-skills.py:213`) scans `repos_dir/*/.claude/skills/` for a `write-plan-cognito`
  directory. It defaults `repos_dir` to `~/source/repos` (`user/scripts/lint-skills.py:369-373`).
- **Symptom (verbatim):**
  ```
  Cognito planner not found: no `write-plan-cognito` skill resolves under any
  repos/*/.claude/skills/ (D1 rename must be present)
  1 planner-resolution issue(s) found.
  EXIT=1
  ```

## Root cause (Step 2) — script-defect

The repo-scoped skills are **git-tracked inside claude-config** at
`<claude-config>/repos/<name>/.claude/skills/`. On the operator's primary dev machines and in
WSL, `~/source/repos/<name>/.claude/skills` is a **symlink** to that internal path, so a scan of
`~/source/repos/*` happens to resolve the skills. That machine-specific symlink layout is the
*only* reason the default `--repos-dir ~/source/repos` ever worked.

On **this** machine (laptop `DESKTOP-GHTC5K6`, user `Jacob`), only `claude-config` itself is
checked out under `~/source/repos` — the sibling working copies (`cognito-forms`, `algobooth`,
`cognito-docs`) are not present as siblings; they exist only as the canonical internal copies
under `<claude-config>/repos/`. So `repos_dir.iterdir()` yields just `claude-config`, whose
top-level `.claude/` has no `skills/` subdir → `repo_skill_roots` is empty → `write-plan-cognito`
"not found" → false RED.

**Proof:**
- `ls repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` → present (git-tracked).
- `python user/scripts/lint-skills.py --check-projected --check-capabilities` → EXIT 1 (the finding).
- `python user/scripts/lint-skills.py --check-projected --check-capabilities --repos-dir "$(pwd)/repos"` → EXIT 0
  (`OK — planner resolution: write-plan-cognito resolves; no execute-plan-cognito fork.`).
- `ls ~/source/repos` → only `claude-config/`.

The check anchors D1 resolution to a **machine-variable, non-guaranteed** location
(`~/source/repos`) instead of the **canonical, always-present, git-tracked** location
(`<claude-config>/repos/`). D1 (`plan-skills-redesign/SPEC.md:66-76`) requires that
`write-plan-cognito` resolve repo-scoped and that no `execute-plan-cognito` fork exist — both
invariants apply to the canonical internal source of truth, which the gate must scan regardless
of whether sibling working copies happen to be checked out.

## Fix scope (Step 3)

Make `lint_planner_resolution` resolve repo skill roots from the **union** of:
1. the passed `repos_dir` (sibling working copies / symlinks — preserved for dev machines), and
2. the claude-config-internal `<claude-config>/repos/` derived from the script's own location
   (`Path(__file__).resolve().parents[2] / "repos"`) — always present, machine-independent.

Deduplicate roots by resolved path so a symlinked sibling is not double-counted. This is strictly
*stronger*: the negative `execute-plan-cognito` invariant now also covers the internal repos. No
gate is weakened, no threshold softened — the fix corrects WHERE the invariant looks, not WHAT it
requires. Regression coverage: a `test_lazy_core.py` unit test that invokes the planner-resolution
check against a synthetic repos layout where the skill exists ONLY in the internal location and
the passed `repos_dir` is empty, asserting no finding.

## Out of scope (deliberate class boundary)

`project-skills.py` shares the same `~/source/repos` default and correspondingly under-projects on
this machine (produces `_default` + `claude-config` only, omitting per-repo projections) — but it
exits 0 (a missing projection is silent, not a gate failure), so it is not the RED finding under
investigation. Not fixed here to avoid gold-plating; noted for a possible follow-up if it later
surfaces as friction.

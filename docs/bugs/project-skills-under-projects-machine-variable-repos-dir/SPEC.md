# `project-skills.py` silently under-projects — machine-variable `--repos-dir` default — Investigation Spec

> On a clean `main`, `python user/scripts/project-skills.py` (no `--repos-dir`) defaults
> `--repos-dir` to the machine-variable `~/source/repos` and discovers only whatever repos
> happen to be checked out there. On a machine where only `claude-config` is checked out under
> `~/source/repos`, it produces `_default` + a spurious `claude-config` projection and SILENTLY
> OMITS the real per-repo projections (`algobooth`, `cognito-forms`) that are git-tracked inside
> `<claude-config>/repos/`. Exit 0, no RED gate — an invisible under-projection.

**Status:** Concluded
**Severity:** P2 (skill projection is machine-dependent and silently incomplete; no gate catches it)
**Discovered:** 2026-07-11 (manual `/harden-harness`, trigger 5 — Gap A)
**Root-cause class:** script-defect
**Related:** `docs/bugs/planner-resolution-lint-blind-to-internal-repos/SPEC.md` (the FIRST fix of this same root-cause class — Round 25 / commit `8ffd1d0`, `lint-skills.py:lint_planner_resolution`); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` (Round 26)

---

## Reconstructed route (Step 1)

- **Entry point:** `project-skills.py::main()` → `project_all(skills_dir, output_dir, repos_dir)`
  (`user/scripts/project-skills.py:245`, `:289`).
- **Divergence:** `main()` resolves `repos_dir` from `args.repos_dir` whose default is
  `Path.home() / "source" / "repos"` (`user/scripts/project-skills.py:311-315`, resolved at
  `:321`). `project_all` then scans ONLY `repos_dir.iterdir()` for `repo/.claude/skill-config/`
  (`:265-280`). No fallback to the canonical internal `repos/`.
- **Symptom (verbatim, this machine):**
  ```
  # python user/scripts/project-skills.py            (default --repos-dir ~/source/repos)
  Repos discovered   : 1
    claude-config: 88 skills, 97 components, 1 skipped caps=[]

  # python user/scripts/project-skills.py --repos-dir "$(pwd)/repos"
  Repos discovered   : 2
    algobooth: 88 skills, 97 components caps=[mcp]
    cognito-forms: 88 skills, 97 components, 1 skipped caps=[]
  ```
  The default run omits `algobooth` (with its `mcp` capability filter) and `cognito-forms`
  entirely, and instead projects a spurious `claude-config` repo (the repo root that happens
  to sit under `~/source/repos`, whose top-level `.claude/skill-config` has empty capabilities).
  Exit 0 either way — the under-projection is silent.

## Root cause (Step 2) — script-defect

Identical root-cause CLASS to the Round-25 finding
(`docs/bugs/planner-resolution-lint-blind-to-internal-repos/`): a harness script anchors
repo discovery to the **machine-variable, non-guaranteed** `~/source/repos` instead of the
**canonical, always-present, git-tracked** `<claude-config>/repos/`.

The repo-scoped skills/config are git-tracked inside claude-config at
`<claude-config>/repos/<name>/.claude/skill-config/`. On the operator's primary dev machines /
WSL, `~/source/repos/<name>` is a symlink to that internal path, so scanning `~/source/repos/*`
happens to resolve them. That machine-specific symlink layout is the *only* reason the default
`--repos-dir ~/source/repos` ever produced the per-repo projections.

On **this** machine, only `claude-config` is checked out under `~/source/repos`; the sibling
working copies do not exist there. So `repos_dir.iterdir()` yields just `claude-config`, and the
real per-repo projections silently disappear from `~/.claude/skills-projected/`.

**Proof:**
- `ls repos/` → `algobooth  cognito-docs  cognito-forms` (git-tracked); `algobooth` and
  `cognito-forms` have `.claude/skill-config/`.
- `ls ~/source/repos` → only `claude-config/`.
- Default run vs. `--repos-dir ./repos` run diverge exactly as the verbatim symptom above shows.

## Proposed fix scope (Step 3) — structural consolidation (this class's SECOND fix)

Per the over-fit detector, this is the **second** instance of the class "harness script defaults
repo discovery to machine-variable `~/source/repos` instead of the canonical internal `repos/`"
(first: Round 25 / `8ffd1d0`). A generalization is now warranted, and a shared import is
practical (both scripts are stdlib-only and live in `user/scripts/`), so the fix is a
**structural consolidation** rather than a copy-paste:

1. **New shared helper** `user/scripts/skill_repos.py` (stdlib-only):
   - `resolve_internal_repos_root()` → `<claude-config>/repos/` derived from the module's own
     location (`parents[2]`), machine-independent.
   - `iter_config_repos(repos_dir, internal_repos_dir, marker)` → yields repo dirs from the
     UNION of the passed `repos_dir` and `internal_repos_dir` where `repo/<marker>` exists,
     deduplicated by resolved marker path (order: passed dir first, then internal).
2. **`project-skills.py`**: `project_all` gains an injectable `internal_repos_dir` param and
   iterates `iter_config_repos(...)`; `main()` passes `resolve_internal_repos_root()` so the
   real invocation unions the internal repos regardless of `~/source/repos` layout.
3. **`lint-skills.py`**: `lint_planner_resolution` is refactored onto the same helper (retiring
   the duplicated inline union logic added by `8ffd1d0`), with `internal_repos_dir` made an
   **injectable parameter** (production `main()` passes the canonical root). This also restores
   test hermeticity — see below.

### Secondary defect uncovered: stale non-hermetic lint test (RED)

`test_project_skills.py::test_planner_resolution_flags_missing_cognito_planner` is currently
**FAILING** on `main`: it passes a synthetic tmp `repos_dir` with no `write-plan-cognito` and
asserts a `planner-resolution` finding, but `8ffd1d0` made `lint_planner_resolution` reach into
the REAL internal `repos/` (which HAS `write-plan-cognito`) via a hard `__file__`-derived path,
so the finding never fires. The test was left non-hermetic by that round. Making
`internal_repos_dir` an injectable parameter lets the synthetic lint tests pass an empty
internal dir and become hermetic again — restoring the RED→GREEN and the test's intent.

Regression coverage: `test_project_skills.py` gains tests asserting `project_all` unions an
injected `internal_repos_dir`, plus hermeticity fixes to the synthetic lint tests. No gate is
weakened; production behavior is strictly more complete (per-repo projections now appear
regardless of the host's `~/source/repos` layout).

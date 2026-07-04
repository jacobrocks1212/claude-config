# CI for claude-config Itself — Feature Specification

> The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a
> skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no
> `.github/workflows/`, so those integrity gates only run when someone remembers to run them
> locally. Add a push- and PR-triggered GitHub Actions workflow that runs every hermetic gate
> mechanically on each commit, so a regression in `lazy_core.py`, a broken component injection, or
> a coupled-pair drift is caught on the commit that introduces it rather than on a later live run.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Friction-reduction feature:** no

<!-- Classification rationale (measurability gate): this is a regression-prevention / integrity
     gate — the same class as the Complete `doc-drift-linter` (which carries no KPI declaration).
     It does not *measure* a harness signal, so no `## KPI Declaration` section is required. The
     KPI registry's members all measure a signal (false-green rate, halt dwell,
     cycles-per-completion); this feature enforces existing gates. -->

**Depends on:**

- doc-drift-linter — soft — CI wires the completed `doc-drift-lint.py` script into a workflow lane; the script must exist, but this feature does not hinge on its internals.

<!-- Downstream dependee (informational, not authored in this block): doc-drift-linter/SPEC.md D4
     explicitly defers its own "CI wiring" to this feature. -->

---

## Executive Summary

The repo is the canonical source for Jacob's autonomous agentic development harness, and its own
`CLAUDE.md` mission statement declares that "integrity gates are load-bearing." Yet the gates that
guard the harness itself — the pytest suites under `user/scripts/`, `lint-skills.py`,
`project-skills.py` projection validation, `lazy_parity_audit.py`, `doc-drift-lint.py`, and the
PowerShell test family — are opt-in local runs. Nothing mechanically re-checks them on a commit, so
a regression can land on `main` and stay latent until a live pipeline run trips it.

This feature adds a GitHub Actions workflow (`.github/workflows/ci.yml`) that runs on every push and
pull request. The workflow is organized into parallel lanes: a **Python lane** (pytest + the lint
scripts + the projection check, all stdlib/pytest and hermetic by design), a **Bash-hook lane**
(the `test_hooks.py` fixtures on a POSIX runner), and a **PowerShell lane** (Pester +
PSScriptAnalyzer over the `*.ps1` family and `*.Tests.ps1` suites). The Python and Bash lanes are
POSIX-native and run on `ubuntu-latest`; the PowerShell lane's runner (Windows vs. `pwsh`-on-Linux)
is the one open question deferred to research, because the build-queue code it exercises is
Windows-shaped (Job Objects, VBCSCompiler recycling).

The design goal is a fast, non-flaky signal that turns "someone remembers to run the suite" into
"every commit is gate-checked." The suites are already hermetic (they use `--test` injection points
and stdlib-only fakes), so no external services, secrets, or network access are required.

## User Experience

The consumer is the harness maintainer (Jacob) and any autonomous cloud/worktree session that
pushes a branch.

- **On push / PR:** GitHub runs the workflow and reports a status check per lane. A green check
  means every hermetic gate passed on that commit; a red check names the failing lane and the
  maintainer opens the job log to the failing test/lint line.
- **Local parity:** the workflow runs the *same* commands the maintainer runs locally
  (`pytest user/scripts/`, `python user/scripts/lint-skills.py --check-projected
  --check-capabilities`, `python user/scripts/doc-drift-lint.py`, etc.), so a green local run and a
  green CI run mean the same thing — no CI-only incantations.
- **Cloud durability tie-in:** because cloud/worktree sessions push work branches, CI gives those
  sessions an automatic post-push integrity signal they otherwise never get (they cannot run the
  Windows PowerShell suites at all).
- **Empty/edge states:** a lane with zero matching tests must fail loudly (the `pass==total==0`
  anti-pattern is a known false-green — mirror the completion-coherence-gate rule), not report a
  spurious green.

## Technical Design

- **Workflow file:** `.github/workflows/ci.yml`, triggered on `push` (all branches) and
  `pull_request`.
- **Python lane** (`ubuntu-latest`): `actions/checkout` + `actions/setup-python`; install nothing
  beyond stdlib + pytest (a minimal `requirements-ci.txt` or inline `pip install pytest`); run
  `pytest user/scripts/`, then `python user/scripts/lint-skills.py --check-projected
  --check-capabilities`, `python user/scripts/project-skills.py` (projection check), `python
  user/scripts/doc-drift-lint.py --repo-root .`, and `python user/scripts/lazy_parity_audit.py
  --repo-root .`.
- **Bash-hook lane:** the hook fixtures (`test_hooks.py` exercises the `user/hooks/*.sh` chain on a
  POSIX shell); runs on `ubuntu-latest`.
- **PowerShell lane:** `Invoke-Pester` over `*.Tests.ps1` + `Invoke-ScriptAnalyzer` over the `*.ps1`
  family. **Runner OS is the open research question** — Windows runner (native, but slower/costlier)
  vs. `pwsh`-on-Linux (fast, but the build-queue code is Windows-shaped and may not exercise
  faithfully). See Open Questions.
- **Concurrency + speed:** lanes run as parallel jobs; add a `concurrency` group keyed on ref to
  cancel superseded runs on rapid re-pushes. Cache pip where it helps.
- **Required vs. informational:** whether a red check *blocks* merge is a GitHub branch-protection
  setting, not a workflow concern; v1 ships the workflow reporting status on all branches, and
  branch-protection wiring is a follow-up repo-settings decision (see Open Questions).
- **Symlink note:** the repo uses symlinks (`manifest.psd1`); CI checks out with symlinks intact on
  Linux runners — verify no lane depends on a live `~/.claude/` target that only exists on the
  workstation (the suites are designed `--repo-root`-relative, so this should hold; confirm during
  implementation).

## Implementation Phases

1. **Python + Bash lanes (core).** Author `ci.yml` with the `ubuntu-latest` Python lane (pytest +
   all four lint/projection/parity checks) and the Bash-hook lane. Prove green on a test push.
2. **Zero-test / false-green guard.** Ensure each lane fails on `pass==total==0` and on a missing
   suite, not just on assertion failures.
3. **PowerShell lane.** Add the Pester + PSScriptAnalyzer lane on the runner OS chosen by research;
   scope which `*.ps1`/`*.Tests.ps1` are portable to that runner.
4. **Polish.** Concurrency-cancel, caching, status-badge in `CLAUDE.md`/README, and (optionally)
   branch-protection required-check wiring per the Open Questions resolution.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Workflow runs on every commit | push a commit to any branch | a CI run appears for that commit | GitHub Actions tab / `gh run list` |
| Python lane catches a broken test | push a commit with a failing `test_*.py` | Python lane job goes red, names the failing test | Actions job log |
| Lint lane catches a broken injection | push a skill with a broken `!cat` component ref | lint-skills lane goes red | Actions job log |
| Doc-drift lane catches doc drift | push a `CLAUDE.md` claim that diverges from disk | doc-drift lane goes red (exit 1) | Actions job log |
| Parity lane catches coupled-pair drift | edit one half of a coupled skill pair only | parity-audit lane goes red | Actions job log |
| No false-green on empty suite | run a lane whose test filter matches zero tests | lane FAILS (not a spurious green) | Actions job log / lane exit code |
| PowerShell lane runs the PS suites | push a change under `user/scripts/*.ps1` | Pester + PSScriptAnalyzer report on the chosen runner | Actions job log |

## Open Questions

Research-answerable (harvested into `RESEARCH_PROMPT.md` at Phase 2):

1. **PowerShell lane runner OS** — Windows runner vs. `pwsh`-on-Linux. Do the existing
   `build-queue-hygiene.Tests.ps1` / `*.Tests.ps1` suites run faithfully under `pwsh` on Linux, or
   do their Windows-shaped dependencies (Job Objects, VBCSCompiler recycling, `powershell.exe`
   invocations) require a `windows-latest` runner? What do comparable cross-platform PowerShell
   projects do in CI?
2. **Required-check vs. informational** — for a single-maintainer config repo with direct pushes,
   is a blocking required status check worth the branch-protection setup, or is an informational
   status check sufficient? Convention among similar personal-tooling repos.
3. **Action pinning / supply-chain** — pin actions by commit SHA vs. major-version tag; caching
   strategy that helps without staleness risk.
4. **Matrix breadth** — single Python version vs. a small version matrix; is any suite
   version-sensitive?

Scope/config decisions taken in-cycle (completeness-first): v1 wires **every** hermetic gate that
runs on a Linux runner (pytest, lint-skills, project-skills projection, doc-drift-lint, parity
audit, bash hooks) plus a PowerShell lane whose runner OS is the deferred research question; triggers
on push (all branches) + PR; ships status-reporting (branch-protection is a follow-up).

## Research References

Baseline shaped from the repo-exploration proposal session 2026-07-04 (the prior stub) and an
internal codebase survey of the existing suites and lint scripts. `RESEARCH.md` pending — the four
Open Questions above drive the Phase 2 research prompt (or an operator-directed research skip, as
sibling infra features `doc-drift-linter` and `cross-platform-setup` took).

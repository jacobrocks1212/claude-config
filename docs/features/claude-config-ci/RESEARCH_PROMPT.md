# GitHub Actions CI for a symlink-based, multi-language personal tooling monorepo (Python + Bash hooks + Windows-shaped PowerShell)

## Research Question

I maintain a single git repository (`claude-config`) that is the canonical source for an autonomous
agentic development harness. It ships a large body of integrity gates — roughly 18 `pytest` suites,
several stdlib linters (`lint-skills.py`, `doc-drift-lint.py`, `lazy_parity_audit.py`), a
skill-projection validator (`project-skills.py`), a POSIX shell-hook test suite, and a Windows-shaped
PowerShell family (Pester `*.Tests.ps1` suites + `PSScriptAnalyzer` over `*.ps1` scripts). None of it
runs on commit today — there is no `.github/workflows/`, so the gates only fire when someone remembers
to run them locally.

I want to add a push- and PR-triggered GitHub Actions workflow (`.github/workflows/ci.yml`) that runs
every hermetic gate mechanically on each commit. The suites are already hermetic (stdlib-only, no
network, no secrets, `--repo-root`-relative). **What is the best-practice design for this workflow, and
specifically how should I handle the Windows-shaped PowerShell lane, false-green prevention, action
supply-chain pinning, and Python version matrixing?**

## Context

- **Repo shape:** a personal-tooling monorepo. It uses symlinks heavily (a `manifest.psd1` maps repo
  files to live `~/.claude/` locations); on Linux CI runners the repo is checked out with symlinks
  intact and the suites are written `--repo-root`-relative, so they should not depend on a live
  `~/.claude/` target — but I want to confirm the symlink-checkout behavior on GitHub-hosted runners.
- **Languages/gates in play:**
  - **Python (stdlib + pytest):** `pytest user/scripts/`, `python user/scripts/lint-skills.py
    --check-projected --check-capabilities`, `python user/scripts/project-skills.py` (projection
    validation), `python user/scripts/doc-drift-lint.py --repo-root .`, `python
    user/scripts/lazy_parity_audit.py --repo-root .`. All stdlib-only except the `pytest` dependency.
  - **Bash hooks:** a `test_hooks.py` suite exercises a chain of `user/hooks/*.sh` PreToolUse/PostToolUse
    hooks on a POSIX shell.
  - **PowerShell:** `Invoke-Pester` over `*.Tests.ps1` plus `Invoke-ScriptAnalyzer` over the `*.ps1`
    family. The scripts under test are **Windows-shaped** — they use Windows Job Objects, VBCSCompiler
    process recycling, `powershell.exe` invocations, and Windows path semantics (a build-queue
    serializer for a separate C#/.NET monorepo).
- **Constraints:** single maintainer, direct pushes to `main` common, cloud/worktree agent sessions
  also push work branches (they cannot run the Windows PowerShell suites at all). Signal must be fast
  and non-flaky. No external services, secrets, or network access required by any suite.

## Baseline Spec Summary (decisions already made)

- One workflow file, `.github/workflows/ci.yml`, triggered on `push` (all branches) + `pull_request`.
- Organized into parallel jobs ("lanes"): a **Python lane** and a **Bash-hook lane** on
  `ubuntu-latest`, plus a **PowerShell lane** whose runner OS is the open question below.
- Install nothing beyond stdlib + pytest (minimal `requirements-ci.txt` or inline `pip install pytest`).
- Add a `concurrency` group keyed on ref to cancel superseded runs on rapid re-pushes.
- v1 ships status-reporting on all branches; whether a red check *blocks* merge (branch protection) is
  treated as a follow-up repo-settings decision, not a workflow concern.
- A lane with **zero matching tests must fail loudly** — the `pass == total == 0` false-green is a known
  anti-pattern in this harness and must not report a spurious green.

## Research Areas

1. **PowerShell in CI — Windows runner vs. `pwsh`-on-Linux for Windows-shaped code.** How do
   comparable cross-platform (or Windows-targeting) PowerShell projects run Pester + PSScriptAnalyzer in
   GitHub Actions? When code under test depends on Windows-only primitives (Job Objects, process
   recycling, `powershell.exe` / Windows PowerShell 5.1 vs. PowerShell 7 `pwsh`), what breaks under
   `pwsh` on `ubuntu-latest`, and what is the accepted practice — a `windows-latest` runner, a
   platform-gated test subset, `[Platform]` / `-Skip` Pester filters, or splitting analyzer-only
   (portable) from behavior tests (Windows-only)? Cost/speed tradeoffs of `windows-latest` minutes.
2. **False-green / zero-test prevention in GitHub Actions.** Best practice for making a job fail when a
   test filter matches zero tests or a suite file is missing (not just on assertion failures). Cover
   `pytest` (e.g. `--strict-markers`, exit-code 5 "no tests collected" handling, `-p no:cacheprovider`)
   and Pester (`Should -Not -Be 0` on discovered count, `-CI` mode, `Run.Exit`/`Run.Throw`
   configuration). How do teams assert "N tests actually ran"?
3. **Action supply-chain / pinning.** Pin `actions/checkout`, `actions/setup-python`, etc. by full
   commit SHA vs. major-version tag — current best practice, tradeoffs, and tooling (Dependabot for
   actions, `pin-github-action`, StepSecurity Harden-Runner). Caching strategy (`actions/cache` /
   `setup-python` built-in pip cache) that helps a stdlib+pytest install without staleness/poisoning
   risk.
4. **Python version matrix.** Single pinned Python version vs. a small matrix (e.g. 3.11/3.12/3.13) for
   a stdlib-only + pytest codebase. Is the marginal flakiness/time cost worth it? Which stdlib surfaces
   are most version-sensitive (e.g. `tomllib`, `argparse`, `pathlib`, `zoneinfo`, dataclass/typing
   changes) such that a matrix would actually catch regressions here?
5. **Symlink-heavy checkout on hosted runners.** Confirm `actions/checkout` preserves symlinks on
   `ubuntu-latest` (it does by default — but note any `core.symlinks` / autocrlf gotchas), and any
   Windows-runner symlink caveats relevant to the PowerShell lane.
6. **Concurrency & required-vs-informational checks for a single-maintainer repo.** Convention among
   similar personal-tooling / dotfiles-style repos: is a blocking required status check worth the
   branch-protection setup for a solo maintainer with direct pushes, or is an informational check
   sufficient? `concurrency` `cancel-in-progress` patterns and their interaction with PR vs. push
   triggers (avoiding double-runs on PR branches).

## Specific Questions

1. For Windows-shaped PowerShell code (Job Objects, VBCSCompiler recycling, `powershell.exe`), should
   the CI lane use `windows-latest` or `pwsh` on `ubuntu-latest`? If the answer is "it depends,"
   what is the decision rule, and how do I split portable analyzer/lint checks from Windows-only
   behavior tests so the fast portable subset can run on Linux?
2. What is the most reliable way to make a GitHub Actions job **fail on zero collected tests** for both
   `pytest` and Pester? Give the exact config/flags.
3. Should GitHub Actions be pinned by commit SHA or version tag in 2026? What is the lowest-friction way
   to keep SHA pins current (Dependabot config snippet)?
4. Is a Python version matrix justified for a stdlib-only + pytest codebase, or does a single pinned
   interpreter give the same regression coverage at lower cost? If a matrix, which versions?
5. What `concurrency` configuration cancels superseded runs on rapid re-pushes **without** cancelling an
   in-flight run I care about, and without double-running the same commit on both `push` and
   `pull_request`?
6. For a solo-maintainer config repo with direct pushes, is branch-protection with a required status
   check the right call, or does an informational status check deliver most of the value at less
   friction? What do comparable repos do?
7. Are there `actions/checkout` symlink or line-ending (`core.autocrlf`) gotchas that would break a
   symlink-based repo whose suites are `--repo-root`-relative?
8. Any known Pester + PSScriptAnalyzer GitHub Actions integration pitfalls (module version pinning,
   `Invoke-Pester` vs. the newer configuration object, PSScriptAnalyzer settings-file discovery)?

## Output Format Request

Provide structured findings with clear sections mirroring the Research Areas above. For each open
question, give an actionable recommendation with a one-line rationale and, where relevant, a concrete
YAML snippet (job block, `concurrency` block, matrix, cache, or pinning example) I can adapt directly
into `.github/workflows/ci.yml`. Call out any recommendation that is contested in the community and
explain the tradeoff so I can make the final call. Prioritize the PowerShell-runner decision (Research
Area 1 / Question 1) and the false-green prevention (Research Area 2 / Question 2) — those two most
shape the workflow's structure.

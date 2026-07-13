@{
    User = @(
        # Directory symlinks
        @{ Live = '~\.claude\skills';            Repo = 'user\skills';            Type = 'Directory' }
        @{ Live = '~\.claude\hooks';             Repo = 'user\hooks';             Type = 'Directory' }
        @{ Live = '~\.claude\scripts';           Repo = 'user\scripts';           Type = 'Directory' }
        @{ Live = '~\.claude\templates';         Repo = 'user\templates';         Type = 'Directory' }
        # Local-tools plugins — source tracked here, symlinked into the local-tools marketplace
        @{ Live = '~\.claude\plugins\local-tools\plugins\cognito-pr-review';   Repo = 'user\plugins\local-tools\plugins\cognito-pr-review';   Type = 'Directory' }
        @{ Live = '~\.claude\plugins\local-tools\plugins\work-logging-plugin'; Repo = 'user\plugins\local-tools\plugins\work-logging-plugin'; Type = 'Directory' }
        # File symlinks
        @{ Live = '~\.claude\CLAUDE.md';           Repo = 'user\CLAUDE.md';           Type = 'File' }
        @{ Live = '~\.claude\CLAUDE.local.md';     Repo = 'user\CLAUDE.local.md';     Type = 'File' }
        @{ Live = '~\.claude\settings.json';       Repo = 'user\settings.json';       Type = 'File' }
        @{ Live = '~\.claude\settings.local.json'; Repo = 'user\settings.local.json'; Type = 'File' }
        @{ Live = '~\.claude\keybindings.json';    Repo = 'user\keybindings.json';    Type = 'File' }
    )
    Personal = @(
        @{ Live = '~\.claude-personal\CLAUDE.md'; Repo = 'personal\CLAUDE.md'; Type = 'File' }
    )
    Workspace = @(
        @{ Live = '~\source\repos\CLAUDE.md'; Repo = 'workspace\CLAUDE.md'; Type = 'File' }
    )
    Repos = @{
        # doc-drift:deliberate-divergence: algobooth — repos/algobooth/ has no Repos entry on
        # purpose. This manifest is shared across machines: on the WORK laptop the repo does not
        # exist locally, and a Repos entry made setup.ps1 recreate an empty personal-repo husk
        # dir there — 47b4fa4 dropped the entry to stop that. On the PERSONAL machine the repo IS
        # live and actively developed; its .claude symlinks already exist, so it needs no entry
        # to (re)create them — it only needs its symlink targets present in-repo. So the tracked
        # content under repos/algobooth/.claude/ stays tracked (resolves the personal machine's
        # symlinks; inert on the work laptop, since no entry ⇒ setup.ps1 skips it): skills/
        # (algobooth-ui, production-build + the cloud /lazy halves lazy-cloud, lazy-batch-cloud,
        # mcp-test), skill-config/ (quality-gates, catalogs, runtime guidance — the mcp-test
        # commit/quality rules), AND settings.local.json (env.BASH_ENV + allow-list). NOTE:
        # 47b4fa4 over-deleted all three; all restored from 47b4fa4^ — settings.local.json cleaned
        # of 33 dead JacobMadsen/strudel-dj one-shot commit allows (kept env + 42 generic entries).
        # Do NOT re-add a Repos entry while the work laptop lacks the live repo.
        # build-queue-generalization (2026-07-09) follows the same pattern: the new tracked
        # content under repos/algobooth/.claude/ — skill-config/build-queue-ops.json (the ops
        # manifest) + skills/{tauri-build,cargo-release} (queue-routed build ops) — ships with
        # NO Repos entry. It resolves via the existing symlinks where the repo is live, or via
        # setup.py bootstrap --target Repos --repos-root on a fresh checkout; inert elsewhere.
        'cognito-forms' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\Cognito Forms'
            RootFiles      = @(
                'CLAUDE.local.md', 'worktree-wizard.ps1',
                # Personal subdir CLAUDE.local.md docs — claude-config-owned, symlinked into every
                # worktree (main + aliased B/C/D). Nested subpaths resolve via the Join-Path mapping
                # loop + parent-dir creation in setup.ps1; no setup.ps1 change needed.
                'Cognito.Core\CLAUDE.local.md',
                'Cognito\CLAUDE.local.md',
                'Cognito.Services\CLAUDE.local.md',
                'Cognito.QueueJob\CLAUDE.local.md',
                'Cognito.UnitTests\CLAUDE.local.md',
                'Cognito.Web.Client\CLAUDE.local.md',
                'Cognito.Web.Client\apps\spa\CLAUDE.local.md',
                'Cognito.Web.Client\apps\client\CLAUDE.local.md',
                'Cognito.Web.Client\libs\model.js\CLAUDE.local.md',
                'Cognito.Web.Client\libs\types\CLAUDE.local.md',
                'Cognito.Web.Client\libs\vuemodel\CLAUDE.local.md'
            )
            # .claude/CLAUDE.md and commands/{msbuild,review-pr,work-item}.md are team-owned
            # (git-tracked by the Cognito Forms repo) — do NOT whole-dir/whole-file symlink them.
            # Only personal, git-ignored command files are symlinked individually.
            # scripts\*.ps1 below are personal, git-ignored tooling scripts — sourced here so all
            # worktrees share one copy. create-branch-worktree.ps1 and review-pr.ps1 are team-owned
            # (git-tracked) and intentionally NOT symlinked.
            # hooks\normalize-crlf.ps1 is likewise personal + git-ignored (.claude/ is gitignored by
            # the Cognito repo) — versioned here so the EOL hook is reviewable and shared across worktrees.
            DotClaudeFiles = @(
                'settings.json', 'settings.local.json',
                'hooks\normalize-crlf.ps1',
                'commands\spec.md', 'commands\format-csharp.md', 'commands\process-build-session.md',
                'scripts\build-filtered.ps1', 'scripts\test-filtered.ps1',
                'scripts\client-build-filtered.ps1', 'scripts\client-test-filtered.ps1',
                'scripts\find-dll.ps1', 'scripts\find-large-folders.ps1',
                'scripts\list-downloads.ps1', 'scripts\quick-scan.ps1', 'scripts\system-stats.ps1'
            )
            DotClaudeDirs  = @('skill-config', 'skills', 'knowledge')
        }
        'cognito-forms-B' = @{
            Path  = 'C:\Users\JacobMadsen\source\repos\Cognito Forms-B'
            Alias = 'cognito-forms'
        }
        'cognito-forms-C' = @{
            Path  = 'C:\Users\JacobMadsen\source\repos\Cognito Forms-C'
            Alias = 'cognito-forms'
        }
        'cognito-forms-D' = @{
            Path  = 'C:\Users\JacobMadsen\source\repos\Cognito Forms-D'
            Alias = 'cognito-forms'
        }
        'cognito-docs' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\cognito-docs'
            DotClaudeFiles = @('settings.local.json')
        }
        # Overwatch (cognitoforms/overwatch) — work repo, .NET Core (net10.0). Personal,
        # claude-config-owned root CLAUDE.md symlinked in; not committed to the team repo
        # (kept out via Overwatch's .git/info/exclude). Shares the user-level skill tree like
        # every repo (write-pr-description / write-pr-comments live there now).
        'overwatch' = @{
            Path      = 'C:\Users\JacobMadsen\source\repos\Overwatch'
            RootFiles = @('CLAUDE.md')
        }
    }
}

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
        'cognito-forms' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\Cognito Forms'
            RootFiles      = @('CLAUDE.local.md', 'worktree-wizard.ps1', 'Cognito.Core\CLAUDE.local.md')
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
    }
}

@{
    User = @(
        # Directory symlinks
        @{ Live = '~\.claude\skills';            Repo = 'user\skills';            Type = 'Directory' }
        @{ Live = '~\.claude\hooks';             Repo = 'user\hooks';             Type = 'Directory' }
        @{ Live = '~\.claude\scripts';           Repo = 'user\scripts';           Type = 'Directory' }
        @{ Live = '~\.claude\templates';         Repo = 'user\templates';         Type = 'Directory' }
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
            RootFiles      = @('CLAUDE.local.md')
            # .claude/CLAUDE.md and commands/{msbuild,review-pr,work-item}.md are team-owned
            # (git-tracked by the Cognito Forms repo) — do NOT whole-dir/whole-file symlink them.
            # Only personal, git-ignored command files are symlinked individually.
            DotClaudeFiles = @('settings.json', 'settings.local.json', 'commands\spec.md', 'commands\format-csharp.md', 'commands\process-build-session.md')
            DotClaudeDirs  = @('skill-config', 'skills', 'knowledge')
        }
        'cognito-forms-side-repo' = @{
            Path  = 'C:\Users\JacobMadsen\source\repos\Cognito Forms-side-repo'
            Alias = 'cognito-forms'
        }
        'algobooth' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\algobooth'
            DotClaudeFiles = @('settings.local.json')
            DotClaudeDirs  = @('skill-config', 'skills')
        }
        'strudel' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\strudel'
            DotClaudeFiles = @('settings.local.json')
            DotClaudeDirs  = @('skills')
        }
        'finances' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\finances'
            DotClaudeFiles = @('CLAUDE.md', 'settings.local.json')
            DotClaudeDirs  = @('commands')
        }
        'zen-mcp-server' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\zen-mcp-server'
            DotClaudeFiles = @('settings.json')
            DotClaudeDirs  = @('commands')
        }
        'housing-locator' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\housing-locator'
            DotClaudeDirs  = @('skill-config', 'skills')
        }
        'memory' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\memory'
            DotClaudeFiles = @('settings.local.json')
        }
        'cognito-docs' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\cognito-docs'
            DotClaudeFiles = @('settings.local.json')
        }
        'meeting-documenter' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\meeting-documenter'
            DotClaudeFiles = @('settings.local.json')
        }
        'scene-remixer' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\scene-remixer'
            DotClaudeFiles = @('settings.local.json')
        }
        'system-design' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\system-design'
            DotClaudeFiles = @('settings.local.json')
        }
        'wiki' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\wiki'
            DotClaudeFiles = @('settings.local.json')
        }
        'meridian-setup' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\meridian-setup'
            DotClaudeFiles = @('settings.json')
        }
        'story' = @{
            Path           = 'C:\Users\JacobMadsen\source\repos\story'
            DotClaudeFiles = @('settings.local.json')
            DotClaudeDirs  = @('commands', 'skills')
        }
    }
}

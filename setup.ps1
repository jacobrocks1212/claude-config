param(
    [Parameter(Position = 0)]
    [ValidateSet('bootstrap', 'check', 'repair', 'add-repo')]
    [string]$Command = 'check',

    [ValidateSet('All', 'User', 'Personal', 'Workspace', 'Repos')]
    [string]$Target = 'All',

    [string]$RepoName,
    [string]$RepoPath
)

$ErrorActionPreference = 'Stop'
$script:RepoRoot = $PSScriptRoot

function Expand-LivePath([string]$Path) {
    $Path -replace '^~', $env:USERPROFILE
}

function Expand-RepoPath([string]$Path) {
    Join-Path $script:RepoRoot $Path
}

function Test-Symlink([string]$Path) {
    $item = Get-Item $Path -Force -ErrorAction SilentlyContinue
    $item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Get-SymlinkTarget([string]$Path) {
    (Get-Item $Path -Force).Target
}

function Resolve-Absolute([string]$Path, [string]$Base) {
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    [IO.Path]::GetFullPath((Join-Path $Base $Path))
}

function Get-AllMappings([string]$TargetFilter) {
    $manifest = Import-PowerShellDataFile (Join-Path $script:RepoRoot 'manifest.psd1')
    $mappings = [System.Collections.ArrayList]::new()

    $sections = [ordered]@{
        User      = $manifest.User
        Personal  = $manifest.Personal
        Workspace = $manifest.Workspace
    }

    foreach ($section in $sections.Keys) {
        if ($TargetFilter -notin 'All', $section) { continue }
        foreach ($e in $sections[$section]) {
            [void]$mappings.Add(@{
                Live    = Expand-LivePath $e.Live
                Repo    = Expand-RepoPath $e.Repo
                Type    = $e.Type
                Section = $section
            })
        }
    }

    if ($TargetFilter -in 'All', 'Repos') {
        foreach ($name in ($manifest.Repos.Keys | Sort-Object)) {
            $cfg = $manifest.Repos[$name]
            $livePath = $cfg.Path
            $configName = if ($cfg.Alias) { $cfg.Alias } else { $name }
            $srcCfg = if ($cfg.Alias) { $manifest.Repos[$cfg.Alias] } else { $cfg }

            if ($srcCfg.RootFiles) {
                foreach ($f in $srcCfg.RootFiles) {
                    [void]$mappings.Add(@{
                        Live    = Join-Path $livePath $f
                        Repo    = Expand-RepoPath "repos\$configName\$f"
                        Type    = 'File'
                        Section = "Repo:$name"
                    })
                }
            }
            if ($srcCfg.DotClaudeFiles) {
                foreach ($f in $srcCfg.DotClaudeFiles) {
                    [void]$mappings.Add(@{
                        Live    = Join-Path $livePath ".claude\$f"
                        Repo    = Expand-RepoPath "repos\$configName\.claude\$f"
                        Type    = 'File'
                        Section = "Repo:$name"
                    })
                }
            }
            if ($srcCfg.DotClaudeDirs) {
                foreach ($d in $srcCfg.DotClaudeDirs) {
                    [void]$mappings.Add(@{
                        Live    = Join-Path $livePath ".claude\$d"
                        Repo    = Expand-RepoPath "repos\$configName\.claude\$d"
                        Type    = 'Directory'
                        Section = "Repo:$name"
                    })
                }
            }
        }
    }

    $mappings
}

function Invoke-Bootstrap([array]$Mappings) {
    $moved = 0; $linked = 0; $skipped = 0; $warned = 0

    foreach ($m in $Mappings) {
        $live = $m.Live
        $repo = $m.Repo
        $label = "$($m.Section) | $(Split-Path $live -Leaf)"

        # Already correctly linked
        if (Test-Symlink $live) {
            $target = Get-SymlinkTarget $live
            $resolvedTarget = Resolve-Absolute $target (Split-Path $live)
            $resolvedRepo   = [IO.Path]::GetFullPath($repo)
            if ($resolvedTarget -eq $resolvedRepo) {
                Write-Host "  SKIP     $label" -ForegroundColor DarkGray
                $skipped++; continue
            }
        }

        # Ensure repo parent dir exists
        $repoParent = Split-Path $repo
        if ($repoParent -and -not (Test-Path $repoParent)) {
            New-Item -ItemType Directory -Path $repoParent -Force | Out-Null
        }

        if (Test-Path $live) {
            if (Test-Symlink $live) {
                # Symlink pointing to wrong target
                if (Test-Path $repo) {
                    Remove-Item $live -Force
                    New-Item -ItemType SymbolicLink -Path $live -Target $repo | Out-Null
                    Write-Host "  RELINK   $label" -ForegroundColor Cyan
                    $linked++
                } else {
                    if ($m.Type -eq 'Directory') {
                        Copy-Item $live -Destination $repo -Recurse -Force
                    } else {
                        Copy-Item $live -Destination $repo -Force
                    }
                    Remove-Item $live -Force
                    New-Item -ItemType SymbolicLink -Path $live -Target $repo | Out-Null
                    Write-Host "  COPYLINK $label" -ForegroundColor Cyan
                    $linked++
                }
            } else {
                # Real file/directory
                if (Test-Path $repo) {
                    Write-Host "  WARN     $label (both live and repo exist)" -ForegroundColor Yellow
                    $warned++; continue
                }
                Move-Item $live -Destination $repo -Force
                New-Item -ItemType SymbolicLink -Path $live -Target $repo | Out-Null
                Write-Host "  MOVE     $label" -ForegroundColor Green
                $moved++
            }
        } elseif (Test-Path $repo) {
            $liveParent = Split-Path $live
            if ($liveParent -and -not (Test-Path $liveParent)) {
                New-Item -ItemType Directory -Path $liveParent -Force | Out-Null
            }
            New-Item -ItemType SymbolicLink -Path $live -Target $repo | Out-Null
            Write-Host "  LINK     $label (recovery)" -ForegroundColor Cyan
            $linked++
        } else {
            Write-Host "  NONE     $label" -ForegroundColor DarkGray
            $skipped++
        }
    }

    Write-Host "`nBootstrap: $moved moved, $linked linked, $skipped skipped, $warned warnings"
}

function Invoke-Check([array]$Mappings) {
    $ok = 0; $broken = 0; $absent = 0

    foreach ($m in $Mappings) {
        $live = $m.Live
        $repo = $m.Repo
        $label = "$($m.Section) | $(Split-Path $live -Leaf)"

        $item = Get-Item $live -Force -ErrorAction SilentlyContinue
        if (-not $item) {
            if (Test-Path $repo) {
                Write-Host "  MISSING  $label" -ForegroundColor Red
                $broken++
            } else {
                Write-Host "  ABSENT   $label" -ForegroundColor DarkGray
                $absent++
            }
            continue
        }

        if (-not (Test-Symlink $live)) {
            Write-Host "  REAL     $label (not symlinked)" -ForegroundColor Yellow
            $broken++; continue
        }

        $target = Get-SymlinkTarget $live
        $resolvedTarget = Resolve-Absolute $target (Split-Path $live)
        $resolvedRepo   = [IO.Path]::GetFullPath($repo)

        if ($resolvedTarget -eq $resolvedRepo) {
            Write-Host "  OK       $label" -ForegroundColor Green
            $ok++
        } else {
            Write-Host "  WRONG    $label -> $target" -ForegroundColor Yellow
            $broken++
        }
    }

    Write-Host "`nCheck: $ok OK, $broken broken, $absent absent"

    # Warn-only pass: verify the FULL tracked hook set (all 12 hooks, not just the two
    # turn-routing ones) is live in ~/.claude/settings.json. Delegates to
    # doc-drift-lint.py --live rather than re-listing hook names here, so this check
    # has exactly ONE source of truth for "what hooks are tracked" (doc-drift-lint's own
    # hook-table cross-check). This is a configuration advisory — it does NOT affect the
    # exit code (broken count unchanged) because the live file is per-machine and may
    # legitimately be un-synced on a machine that has not run `repair` yet.
    #
    # Registration now ships TRACKED in user/settings.json (this bug's Phase 1) instead of
    # the old per-machine manual paste-fragment. docs/specs/turn-routing-enforcement/
    # REGISTRATION.md's paste-fragment workflow is retired by
    # docs/bugs/live-settings-split-brain-disarms-enforcement-plane's part 3 (Phase 4) —
    # see that doc for the full retirement; this pass only stops re-deriving hook names
    # from it.
    $liveCfgPath = Expand-LivePath '~\.claude\settings.json'
    if (-not (Test-Path $liveCfgPath)) {
        Write-Host '  WARN     live settings.json: absent - cannot verify the tracked hook set is live (run repair)' -ForegroundColor Yellow
    } else {
        $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
        if (-not $pythonCmd) { $pythonCmd = Get-Command python -ErrorAction SilentlyContinue }
        if (-not $pythonCmd) {
            Write-Host '  WARN     live settings.json hook-set check skipped - no python3/python on PATH' -ForegroundColor Yellow
        } else {
            $driftScript = Join-Path $script:RepoRoot 'user\scripts\doc-drift-lint.py'
            $liveOutput = & $pythonCmd.Source $driftScript '--live' '--repo-root' $script:RepoRoot 2>&1
            $liveExit = $LASTEXITCODE
            if ($liveExit -eq 0) {
                Write-Host '  OK       live settings.json reflects the tracked SSOT (doc-drift-lint --live)' -ForegroundColor Green
            } else {
                Write-Host '  WARN     doc-drift-lint --live reports drift between the live and tracked settings.json:' -ForegroundColor Yellow
                foreach ($line in $liveOutput) { Write-Host "           $line" -ForegroundColor Yellow }
            }
        }
    }

    # Warn-only passes for the Cognito Forms worktrees: team-owned-doc drift
    # detection + unregistered-subdir backfill guard. Both are advisories only —
    # they NEVER mutate anything and NEVER touch $broken, so the exit code stays
    # purely symlink-state driven. Every worktree path is Test-Path-guarded so an
    # absent worktree (e.g. -A) or a read error no-ops instead of throwing.
    try {
        $dcManifest = Import-PowerShellDataFile (Join-Path $script:RepoRoot 'manifest.psd1')
        $cfMain = $dcManifest.Repos['cognito-forms']
        if ($cfMain -and $cfMain.Path) {
            $mainWt = $cfMain.Path

            # Non-main worktrees = every Repos entry aliased to cognito-forms (-B/-C/-D).
            $otherWts = [System.Collections.ArrayList]::new()
            foreach ($rn in $dcManifest.Repos.Keys) {
                $r = $dcManifest.Repos[$rn]
                if ($r.Alias -eq 'cognito-forms' -and $r.Path) { [void]$otherWts.Add($r.Path) }
            }

            # --- Pass 1: team-owned-doc drift detector (DRIFT / BEHIND) ---
            # Canonical reference = the MAIN worktree working copy. A doc absent on
            # a stale branch reads as BEHIND (branch predates the file), never DRIFT.
            # Warn-only: git-tracked content is never copied/symlinked/mutated.
            if (Test-Path $mainWt) {
                $teamDocs = @('AGENTS.md', 'CLAUDE.md', 'Cognito.Web.Client\AGENTS.md')
                foreach ($doc in $teamDocs) {
                    $mainDoc = Join-Path $mainWt $doc
                    if (-not (Test-Path $mainDoc)) { continue }   # no reference copy -> nothing to compare
                    $mainContent = Get-Content $mainDoc -Raw -ErrorAction SilentlyContinue
                    foreach ($wt in $otherWts) {
                        if (-not (Test-Path $wt)) { continue }     # absent worktree (e.g. -A) -> no-op
                        $wtName = Split-Path $wt -Leaf
                        $wtDoc  = Join-Path $wt $doc
                        if (-not (Test-Path $wtDoc)) {
                            Write-Host "  BEHIND   $wtName | $doc (branch predates this file)" -ForegroundColor Yellow
                        } else {
                            $wtContent = Get-Content $wtDoc -Raw -ErrorAction SilentlyContinue
                            if ($wtContent -ne $mainContent) {
                                Write-Host "  DRIFT    $wtName | $doc" -ForegroundColor Yellow
                            }
                        }
                    }
                }
            }

            # --- Pass 2: unregistered-subdir backfill guard (UNREGISTERED) ---
            # Any personal */CLAUDE.local.md in main that is NOT in the manifest
            # RootFiles is re-introduced drift (authored directly in a worktree,
            # never registered). node_modules/.git/.claude are pruned during the
            # walk (perf + they are never personal subdir docs).
            if (Test-Path $mainWt) {
                $registered = @($cfMain.RootFiles)
                $stack = [System.Collections.Generic.Stack[string]]::new()
                $stack.Push($mainWt)
                while ($stack.Count -gt 0) {
                    $dir  = $stack.Pop()
                    $leaf = Split-Path $dir -Leaf
                    if ($leaf -eq 'node_modules' -or $leaf -eq '.git' -or $leaf -eq '.claude') { continue }
                    try {
                        foreach ($sub in [IO.Directory]::GetDirectories($dir)) { $stack.Push($sub) }
                        foreach ($file in [IO.Directory]::GetFiles($dir, 'CLAUDE.local.md')) {
                            $rel = $file.Substring($mainWt.Length).TrimStart('\')
                            if ($rel -eq 'CLAUDE.local.md') { continue }   # root doc, registered separately
                            if ($registered -notcontains $rel) {
                                Write-Host "  UNREGISTERED $rel (author it in manifest RootFiles)" -ForegroundColor Yellow
                            }
                        }
                    } catch { }
                }
            }
        }
    } catch {
        $dErr = $_.Exception.Message
        Write-Host "  WARN     worktree doc-drift check skipped ($dErr)" -ForegroundColor Yellow
    }

    return ($broken -eq 0)
}

function Invoke-Repair([array]$Mappings) {
    $repaired = 0; $skipped = 0

    foreach ($m in $Mappings) {
        $live = $m.Live
        $repo = $m.Repo
        $label = "$($m.Section) | $(Split-Path $live -Leaf)"

        if (-not (Test-Path $repo)) {
            $skipped++; continue
        }

        if (Test-Symlink $live) {
            $target = Get-SymlinkTarget $live
            $resolvedTarget = Resolve-Absolute $target (Split-Path $live)
            $resolvedRepo   = [IO.Path]::GetFullPath($repo)
            if ($resolvedTarget -eq $resolvedRepo) { $skipped++; continue }
            Remove-Item $live -Force
        } elseif (Test-Path $live) {
            $bakPath = "$live.bak"
            Move-Item $live $bakPath -Force
            Write-Host "  BACKUP   $label" -ForegroundColor Yellow
        }

        $liveParent = Split-Path $live
        if ($liveParent -and -not (Test-Path $liveParent)) {
            New-Item -ItemType Directory -Path $liveParent -Force | Out-Null
        }

        New-Item -ItemType SymbolicLink -Path $live -Target $repo | Out-Null
        Write-Host "  REPAIR   $label" -ForegroundColor Green
        $repaired++
    }

    Write-Host "`nRepair: $repaired fixed, $skipped OK"
}

# --- Main ---

Write-Host "`n=== Claude Config Setup ===" -ForegroundColor White
Write-Host "Command: $Command | Target: $Target | Root: $script:RepoRoot`n"

$mappings = Get-AllMappings $Target
Write-Host "Mappings: $($mappings.Count)`n"

switch ($Command) {
    'bootstrap' { Invoke-Bootstrap $mappings }
    'check'     { Invoke-Check $mappings }
    'repair'    { Invoke-Repair $mappings }
    'add-repo'  {
        if (-not $RepoName -or -not $RepoPath) {
            Write-Error "Usage: setup.ps1 add-repo -RepoName <name> -RepoPath <path>"
            return
        }
        Write-Host "Add entry to manifest.psd1, then run: .\setup.ps1 bootstrap -Target Repos"
    }
}

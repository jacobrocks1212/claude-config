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

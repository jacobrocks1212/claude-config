[CmdletBinding()]
param (
    [string]$Branch,
    [string]$Name,
    [switch]$InstallDeps,
    [switch]$Cleanup,
    [switch]$RunDev,
    [switch]$DualSite,
    [switch]$Force,
    [switch]$ShowDetails  # Show detailed output (hidden by default for cleaner UX)
)

$ErrorActionPreference = "Stop"

# --- ADMIN CHECK (Soft) ---
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Warning "Running in Non-Admin Mode."
    Write-Host "The following features will be disabled/skipped:" -ForegroundColor Yellow
    Write-Host "  - Automatic IIS Permissions (May cause 500.19 errors)" -ForegroundColor Gray
    Write-Host "  - Dual Site Mode (Parallel Backend infrastructure)" -ForegroundColor Gray
    Write-Host "  - Hosts file editing" -ForegroundColor Gray
    Write-Host "You can continue, but you may need to run 'icacls' manually if you encounter permission errors.`n" -ForegroundColor White
}

# --- PRE-CALCULATE ROOT & PATHS ---
$gitRoot = git rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Current directory is not inside a git repository."
    return
}

# Get the main worktree path (first entry in worktree list)
# This ensures we copy config from main repo even when running from a worktree
$mainWorktree = (git worktree list --porcelain | Select-String "^worktree " | Select-Object -First 1).ToString().Substring(9)
if ([string]::IsNullOrWhiteSpace($mainWorktree)) {
    $mainWorktree = $gitRoot  # Fallback if worktree list fails
}

$projectName = Split-Path $mainWorktree -Leaf
$parentDir = Split-Path $mainWorktree -Parent

# --- CONFIGURATION ---
$filesToCopy = @(
    ".claude",
    ".claude.local"
)

# --- HELPER FUNCTIONS ---

function Remove-ItemRobust {
    param($Path)
    if (-not (Test-Path $Path)) { return }

    # Try standard remove first
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
    }
    catch {
        # Robocopy Mirror Trick for Long Paths
        # Mirrors an empty folder into the target to bypass Windows API path limits
        $emptyDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
        New-Item -Type Directory -Path $emptyDir -Force | Out-Null

        # Run Robocopy silently
        $pInfo = New-Object System.Diagnostics.ProcessStartInfo
        $pInfo.FileName = "robocopy.exe"
        $pInfo.Arguments = "`"$emptyDir`" `"$Path`" /MIR /NFL /NDL /NJH /NJS /NP /R:0 /W:0"
        $pInfo.UseShellExecute = $false
        $pInfo.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($pInfo)
        $p.WaitForExit()

        # Cleanup temp
        Remove-Item -LiteralPath $emptyDir -Force -ErrorAction SilentlyContinue

        # Final kill of target (CMD is often more robust than PS for the final empty dir)
        cmd /c "rmdir /s /q `"$Path`"" 2>$null
    }

    if (Test-Path $Path) {
        Write-Error "Failed to delete directory: $Path. Please delete manually (some files may be locked)."
    }
}

function Write-VerboseHost {
    param(
        [string]$Message,
        [string]$ForegroundColor = "DarkGray"
    )
    if ($script:ShowDetails) {
        Write-Host $Message -ForegroundColor $ForegroundColor
    }
}

function New-DevSymlink {
    # Create a symlink that succeeds NON-ELEVATED when Windows Developer Mode is enabled.
    # Windows PowerShell 5.1's New-Item -ItemType SymbolicLink does not pass the unprivileged-
    # create flag, so it demands elevation even under Dev Mode. cmd's mklink honors Dev Mode's
    # unprivileged create, and also works when elevated — so we shell out to it for both paths.
    # Picks /D for a directory target. Throws on failure so callers can fall back to a copy.
    param([string]$Link, [string]$Target)

    $flag = if (Test-Path -LiteralPath $Target -PathType Container) { '/D ' } else { '' }
    $out = cmd /c "mklink $flag`"$Link`" `"$Target`"" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "mklink failed: $out" }
}

function Sync-ClaudeConfigSymlinks {
    # The config copy above uses Copy-Item, which DEREFERENCES symlinks into frozen real
    # copies. The main worktree's .claude links several entries into the personal
    # claude-config repo (skills, skill-config, knowledge, settings, personal command files).
    # Re-creating those as symlinks here makes the new worktree track claude-config live,
    # matching main. Team-owned real files (e.g. commands\msbuild.md) are left as copies.
    # Degrades gracefully (keeps the copy) if claude-config is absent or symlink creation
    # is unavailable (non-admin without Developer Mode) — so this stays portable for anyone
    # who runs the wizard without a claude-config setup.
    param($MainClaude, $TargetClaude)

    if (-not (Test-Path $MainClaude) -or -not (Test-Path $TargetClaude)) { return }

    # Default Get-ChildItem -Recurse does NOT descend into reparse points, so this lists the
    # symlink entries themselves without walking into their claude-config targets.
    $links = Get-ChildItem -LiteralPath $MainClaude -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }

    $relinked = 0
    foreach ($link in $links) {
        $target = $link.Target
        if ($target -is [array]) { $target = $target | Select-Object -First 1 }
        if ([string]::IsNullOrWhiteSpace($target)) { continue }

        $rel = $link.FullName.Substring($MainClaude.Length).TrimStart('\', '/')
        $dest = Join-Path $TargetClaude $rel

        try {
            # Remove the dereferenced copy Copy-Item placed here (a real file/dir, not yet a
            # link, so this is safe), then recreate the link to the same claude-config target.
            if (Test-Path $dest) {
                if ((Get-Item -LiteralPath $dest -Force).PSIsContainer) {
                    Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction Stop
                } else {
                    Remove-Item -LiteralPath $dest -Force -ErrorAction Stop
                }
            }
            $parent = Split-Path $dest -Parent
            if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            New-DevSymlink -Link $dest -Target $target
            $relinked++
            Write-VerboseHost "  Linked: .claude\$rel -> $target"
        } catch {
            Write-VerboseHost "  Could not link .claude\$rel (kept copy): $_" -ForegroundColor Yellow
        }
    }
    if ($relinked -gt 0) {
        Write-Host "  Linked $relinked claude-config item(s) for live updates." -ForegroundColor Green
    }
}

function Sync-RootConfigSymlinks {
    # Repo-ROOT counterpart to Sync-ClaudeConfigSymlinks. The main worktree links a few
    # root-level files into claude-config (e.g. CLAUDE.local.md). Those live OUTSIDE .claude,
    # so the .claude sync never sees them, and they are not in $filesToCopy — so without this
    # the new worktree has no CLAUDE.local.md at all, dropping the work-logging trigger plus the
    # build/test/branch-doc guidance it carries. We recreate each top-level symlink so the
    # worktree tracks claude-config live, matching main. Falls back to a frozen copy, then skips,
    # if claude-config is absent or symlink creation is unavailable (non-admin without Dev Mode).
    param($MainWorktree, $TargetWorktree)

    if (-not (Test-Path $MainWorktree) -or -not (Test-Path $TargetWorktree)) { return }

    # Top-level only (NO -Recurse): root config files are never nested, and we must not descend
    # into a reparse point and walk its claude-config target.
    $links = Get-ChildItem -LiteralPath $MainWorktree -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }

    $relinked = 0
    foreach ($link in $links) {
        $target = $link.Target
        if ($target -is [array]) { $target = $target | Select-Object -First 1 }
        if ([string]::IsNullOrWhiteSpace($target)) { continue }

        $dest = Join-Path $TargetWorktree $link.Name

        try {
            # Remove any dereferenced copy a prior copy step placed here (a real file/dir, not yet
            # a link), then recreate the link to the same claude-config target.
            if (Test-Path $dest) {
                if ((Get-Item -LiteralPath $dest -Force).PSIsContainer) {
                    Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction Stop
                } else {
                    Remove-Item -LiteralPath $dest -Force -ErrorAction Stop
                }
            }
            New-DevSymlink -Link $dest -Target $target
            $relinked++
            Write-VerboseHost "  Linked: $($link.Name) -> $target"
        } catch {
            # Symlink creation unavailable (non-admin / no Developer Mode). Fall back to a frozen
            # copy so the worktree at least HAS the file, matching how the .claude copy degrades.
            try {
                Copy-Item -LiteralPath $target -Destination $dest -Recurse -Force -ErrorAction Stop
                Write-VerboseHost "  Copied (no symlink): $($link.Name)" -ForegroundColor Yellow
            } catch {
                Write-VerboseHost "  Could not link or copy $($link.Name): $_" -ForegroundColor Yellow
            }
        }
    }
    if ($relinked -gt 0) {
        Write-Host "  Linked $relinked root config item(s) for live updates." -ForegroundColor Green
    }
}

function Remove-RootConfigSymlinks {
    # Root counterpart to Remove-ClaudeConfigSymlinks. Unlink top-level symlinks (e.g.
    # CLAUDE.local.md) before any recursive removal, so a directory link can never be traversed
    # into its shared claude-config target. Deleting the reparse point removes the link only.
    param($TargetWorktree)
    if (-not (Test-Path $TargetWorktree)) { return }

    $links = Get-ChildItem -LiteralPath $TargetWorktree -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }

    foreach ($link in $links) {
        try {
            if ($link.PSIsContainer) {
                [System.IO.Directory]::Delete($link.FullName, $false)
            } else {
                [System.IO.File]::Delete($link.FullName)
            }
            Write-VerboseHost "  Unlinked: $($link.FullName)"
        } catch {
            Write-VerboseHost "  Could not unlink $($link.FullName): $_" -ForegroundColor Yellow
        }
    }
}

function Remove-ClaudeConfigSymlinks {
    # Delete ONLY the symlink entries under the worktree's .claude before any recursive file
    # removal. The fallback removal path (Remove-Item -Recurse / robocopy /MIR / rmdir /s) can
    # otherwise traverse a directory symlink and delete the SHARED claude-config target.
    # Deleting the reparse point itself removes the link only, never the target's contents.
    param($TargetClaude)
    if (-not (Test-Path $TargetClaude)) { return }

    # Default -Recurse does not follow reparse points, so enumeration cannot wander into
    # claude-config. We only ever delete the link nodes themselves.
    $links = Get-ChildItem -LiteralPath $TargetClaude -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }

    foreach ($link in $links) {
        try {
            if ($link.PSIsContainer) {
                # Non-recursive delete unlinks a directory symlink without touching its target.
                [System.IO.Directory]::Delete($link.FullName, $false)
            } else {
                [System.IO.File]::Delete($link.FullName)
            }
            Write-VerboseHost "  Unlinked: $($link.FullName)"
        } catch {
            Write-VerboseHost "  Could not unlink $($link.FullName): $_" -ForegroundColor Yellow
        }
    }
}

function Invoke-WithSpinner {
    param(
        [string]$Label,
        [string]$Command,
        [string]$WorkingDirectory = $PWD,
        [switch]$ShowOutput
    )

    # Determine if we should show detailed output
    $verbose = $ShowOutput -or $script:ShowDetails

    $spinner = @('|', '/', '-', '\')

    # Start the job with the command as a string
    $job = Start-Job -ScriptBlock {
        param($cmd, $wd)
        Set-Location $wd
        $ErrorActionPreference = 'Continue'
        Invoke-Expression $cmd 2>&1
    } -ArgumentList $Command, $WorkingDirectory

    $i = 0
    while ($job.State -eq 'Running') {
        Write-Host "`r  $Label $($spinner[$i % 4])" -NoNewline
        $i++
        Start-Sleep -Milliseconds 200
    }

    $output = Receive-Job -Job $job -Wait
    $jobFailed = $job.State -eq 'Failed'
    Remove-Job -Job $job

    if ($jobFailed) {
        Write-Host "`r  $Label " -NoNewline
        Write-Host "Failed!" -ForegroundColor Red
        if ($output) { $output | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray } }
    } else {
        Write-Host "`r  $Label " -NoNewline
        Write-Host "Done   " -ForegroundColor Green
        # Show output when verbose mode is enabled (even on success)
        if ($verbose -and $output) {
            $output | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        }
    }
}

function Invoke-RemovalWithSpinner {
    param(
        [string]$Label,
        [string]$Path
    )

    if (-not (Test-Path $Path)) { return }

    $spinner = @('|', '/', '-', '\')

    # Start a background job that just outputs spinner frames
    $spinnerJob = Start-Job -ScriptBlock {
        param($label, $spinChars)
        $i = 0
        while ($true) {
            Write-Output "$label $($spinChars[$i % 4])"
            $i++
            Start-Sleep -Milliseconds 200
        }
    } -ArgumentList $Label, $spinner

    # Track the last displayed frame to avoid flicker
    $lastFrame = ""

    try {
        # Run removal in main thread (has access to Remove-ItemRobust)
        $removalJob = Start-Job -ScriptBlock {
            param($p)
            # Inline the removal logic since functions aren't available in jobs
            if (-not (Test-Path $p)) { return $true }
            try {
                Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction Stop
                return $true
            }
            catch {
                # Robocopy Mirror Trick for Long Paths
                $emptyDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
                New-Item -Type Directory -Path $emptyDir -Force | Out-Null
                $pInfo = New-Object System.Diagnostics.ProcessStartInfo
                $pInfo.FileName = "robocopy.exe"
                $pInfo.Arguments = "`"$emptyDir`" `"$p`" /MIR /NFL /NDL /NJH /NJS /NP /R:0 /W:0"
                $pInfo.UseShellExecute = $false
                $pInfo.CreateNoWindow = $true
                $proc = [System.Diagnostics.Process]::Start($pInfo)
                $proc.WaitForExit()
                Remove-Item -LiteralPath $emptyDir -Force -ErrorAction SilentlyContinue
                # Remove the now-empty directory
                if (Test-Path $p) {
                    Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
                }
                return -not (Test-Path $p)
            }
        } -ArgumentList $Path

        # Update spinner while removal runs
        while ($removalJob.State -eq 'Running') {
            $frames = Receive-Job -Job $spinnerJob -ErrorAction SilentlyContinue
            if ($frames) {
                $lastFrame = $frames | Select-Object -Last 1
                Write-Host "`r  $lastFrame" -NoNewline
            }
            Start-Sleep -Milliseconds 100
        }

        $success = Receive-Job -Job $removalJob -Wait
        $jobFailed = $removalJob.State -eq 'Failed' -or $success -eq $false
    }
    finally {
        Stop-Job -Job $spinnerJob -ErrorAction SilentlyContinue
        Remove-Job -Job $spinnerJob -Force -ErrorAction SilentlyContinue
        Remove-Job -Job $removalJob -Force -ErrorAction SilentlyContinue
    }

    if ($jobFailed -or (Test-Path $Path)) {
        Write-Host "`r  $Label " -NoNewline
        Write-Host "Failed!" -ForegroundColor Red
    } else {
        Write-Host "`r  $Label " -NoNewline
        Write-Host "Done   " -ForegroundColor Green
    }
}

function Setup-IIS-DualSite {
    param($Name, $Path, $SpaPort)

    # --- CRITICAL: Early validation to prevent main site corruption ---
    # Ensure $Path is NOT pointing to the main repository
    $mainSitePath = Join-Path $gitRoot "Cognito.Services"
    $pathResolved = $null
    $mainResolved = $null

    if (Test-Path $Path) {
        $pathResolved = (Get-Item $Path).FullName
    }
    if (Test-Path $mainSitePath) {
        $mainResolved = (Get-Item $mainSitePath).FullName
    }

    if ($pathResolved -and $mainResolved -and ($pathResolved -ieq $mainResolved)) {
        Write-Error "CRITICAL: Path parameter '$Path' resolves to main repository!"
        Write-Error "  Resolved path: $pathResolved"
        Write-Error "  Main site path: $mainResolved"
        Write-Error "This would corrupt the main site's configuration. Aborting."
        return
    }

    $iisName = "$projectName-$Name"
    $hostName = "$Name.cognito.dev"
    $appPoolUser = "IIS AppPool\$iisName"

    Write-Host "`nConfiguring Dual Site Mode..." -ForegroundColor Cyan

    # 1. Hosts File
    $hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
    $entry = "127.0.0.1 $hostName"
    if (-not (Select-String -Path $hostsPath -Pattern $hostName)) {
        Add-Content -Path $hostsPath -Value "`r`n$entry"
        Write-VerboseHost "  Hosts file updated: $entry"
    }

    # 2. Find Cert (filter expired, pick newest)
    $cert = Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Subject -like "*cognito.dev*" -and $_.NotAfter -gt (Get-Date) } | Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) { Write-Error "Could not find valid (non-expired) wildcard certificate for *.cognito.dev. Run: .\process\create-local-cert.ps1 -TLD cognito.dev"; return }

    # 3. IIS Setup (Requires WebAdministration module)
    Import-Module WebAdministration -WarningAction SilentlyContinue

    # --- CRITICAL: Find main site BEFORE creating worktree site ---
    # This avoids a race condition in WebAdministration module where Get-Website
    # called immediately after New-WebSite can return corrupted path data.
    $foundMainSiteName = $null
    $foundMainSitePath = $null

    Write-VerboseHost "  Searching for main site (local.cognito.dev)..."

    # First try: Look up by binding (most reliable)
    $allSites = Get-Website
    foreach ($s in $allSites) {
        $bindings = $s.Bindings
        if ($bindings.GetType().Name -eq "ConfigurationElementCollection") {
            $bindings = $bindings.Collection
        }

        foreach ($b in $bindings) {
            # Exact match for local.cognito.dev binding (not subdomains)
            if ($b.bindingInformation -match ":80:local\.cognito\.dev$" -or
                $b.bindingInformation -match ":443:local\.cognito\.dev$") {
                $foundMainSiteName = $s.Name
                $foundMainSitePath = $s.PhysicalPath
                break
            }
            # Robust Check: Host Property (exact match only)
            if ($b.PSObject.Properties["Host"] -and $b.Host -eq "local.cognito.dev") {
                $foundMainSiteName = $s.Name
                $foundMainSitePath = $s.PhysicalPath
                break
            }
        }
        if ($foundMainSiteName) { break }
    }

    # Fallback: Look for standard site name if binding lookup failed
    if ([string]::IsNullOrWhiteSpace($foundMainSiteName)) {
        $mainSite = Get-Website -Name "cognito-services" -ErrorAction SilentlyContinue
        if ($mainSite) {
            $foundMainSiteName = "cognito-services"
            $foundMainSitePath = $mainSite.PhysicalPath
            Write-VerboseHost "  Binding lookup failed. Using fallback site name: 'cognito-services'" -ForegroundColor Yellow
        }
    }

    # Validate main site was found
    if ([string]::IsNullOrWhiteSpace($foundMainSiteName)) {
        Write-Error "Could not locate main site (local.cognito.dev). Dual Site mode requires a main site to clone from."
        return
    }

    # Validate main site path matches git repository root
    $expectedMainPath = Join-Path $gitRoot "Cognito.Services"

    # CRITICAL: Check if main site is pointing to a worktree (corrupted state)
    if ($foundMainSitePath -like "*$projectName-*") {
        Write-Error "CRITICAL: Main site '$foundMainSiteName' is corrupted!"
        Write-Error "  Current path: $foundMainSitePath"
        Write-Error "  Expected path: $expectedMainPath"
        Write-Error ""
        Write-Error "The main site is pointing to a worktree directory instead of the main repository."
        Write-Error "Please fix the main site in IIS Manager or run: process\setup-sites.ps1 -recreate"
        return
    }

    if ($foundMainSitePath -ne $expectedMainPath) {
        Write-Warning "Main site path validation:"
        Write-Warning "  Found: $foundMainSitePath"
        Write-Warning "  Expected: $expectedMainPath"
        Write-Warning "  The main site may not be the correct repository. Proceeding with caution..."
    } else {
        Write-VerboseHost "  Main site validated: $foundMainSiteName" -ForegroundColor Green
        Write-VerboseHost "    Path: $foundMainSitePath"
    }

    # Snapshot main site info BEFORE creating worktree site
    $mainSitePathSnapshot = $foundMainSitePath

    # Also capture vdirs and apps from main site BEFORE creating worktree site
    $mainSiteVdirs = Get-WebVirtualDirectory -Site $foundMainSiteName -ErrorAction SilentlyContinue
    $mainSiteApps = Get-WebApplication -Site $foundMainSiteName -ErrorAction SilentlyContinue

    # --- Now create the worktree site ---
    if (Test-Path "IIS:\AppPools\$iisName") {
        Remove-WebAppPool $iisName | Out-Null
        Write-Host "  Removed existing App Pool: $iisName" -ForegroundColor DarkGray
    }
    New-WebAppPool -Name $iisName | Out-Null
    Write-VerboseHost "  Created App Pool: $iisName"

    if (Test-Path "IIS:\Sites\$iisName") {
        Remove-WebSite $iisName | Out-Null
        Write-Host "  Removed existing Site: $iisName" -ForegroundColor DarkGray
    }

    # Create Site - use pre-captured site count to avoid race condition
    $id = ($allSites | Measure-Object Id -Maximum).Maximum + 1
    New-WebSite -Name $iisName -Id $id -Port 80 -PhysicalPath $Path -ApplicationPool $iisName -HostHeader $hostName | Out-Null

    # Add HTTPS Binding
    New-WebBinding -Name $iisName -Protocol https -Port 443 -HostHeader $hostName -IpAddress "*" | Out-Null

    # Use netsh for SSL binding (works in both PowerShell 5.1 and PowerShell 7)
    # The AddSslCertificate() method doesn't work in PS7 due to object deserialization
    $appId = [Guid]::NewGuid().ToString("B")
    netsh http add sslcert hostnameport="${hostName}:443" certhash=$($cert.Thumbprint) appid="$appId" certstorename=My 2>&1 | Out-Null

    # --- Explicit Permissions for Worktree Root ---
    # Defense in depth: Grant the specific AppPool user Modify rights to the worktree
    Write-VerboseHost "  Granting AppPool permissions on worktree root..."
    icacls "$Path" /grant "${appPoolUser}:(OI)(CI)M" | Out-Null

    if (-not [string]::IsNullOrWhiteSpace($foundMainSiteName)) {
        Write-VerboseHost "  Creating Virtual Directories for worktree (isolated paths)..."

        # Calculate worktree root from $Path (remove \Cognito.Services suffix)
        $worktreeRoot = Split-Path $Path -Parent

        # Calculate main site's solution root from $foundMainSitePath
        $mainSiteRoot = Split-Path $foundMainSitePath -Parent

        Write-VerboseHost "    Worktree root: $worktreeRoot"
        Write-VerboseHost "    Main site root: $mainSiteRoot"

        # Helper function to convert main site path to worktree-local path
        function Get-WorktreeLocalPath {
            param($MainSitePath, $MainRoot, $WorktreeRoot)

            # Get relative path from main site root
            if ($MainSitePath.StartsWith($MainRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                $relativePath = $MainSitePath.Substring($MainRoot.Length).TrimStart('\', '/')
                $localPath = Join-Path $WorktreeRoot $relativePath
                return $localPath
            }

            # Path is external to main site root - skip it for isolation
            return $null
        }

        # Copy Virtual Directories using worktree-local paths (use pre-captured data)
        foreach ($vdir in $mainSiteVdirs) {
            try {
                $localPath = Get-WorktreeLocalPath -MainSitePath $vdir.physicalPath -MainRoot $mainSiteRoot -WorktreeRoot $worktreeRoot

                if ($localPath) {
                    if (Test-Path $localPath) {
                        New-WebVirtualDirectory -Site $iisName -Name $vdir.path.Trim("/") -PhysicalPath $localPath -Force | Out-Null

                        # Grant permissions only on worktree-local path (safe - within our worktree)
                        icacls $localPath /grant "${appPoolUser}:(OI)(CI)R" | Out-Null

                        Write-VerboseHost "   + VDir: $($vdir.path) -> $localPath"
                    } else {
                        Write-VerboseHost "   - VDir: $($vdir.path) skipped (path not found in worktree: $localPath)" -ForegroundColor Yellow
                    }
                } else {
                    Write-VerboseHost "   - VDir: $($vdir.path) skipped (external path, not cloning for isolation)" -ForegroundColor Yellow
                }
            } catch {
                Write-Warning "   ! Failed to create VDir '$($vdir.path)': $_"
            }
        }

        # Copy Web Applications using worktree-local paths (use pre-captured data)
        foreach ($app in $mainSiteApps) {
            if ($app.path -ne "/") {
                try {
                    $localPath = Get-WorktreeLocalPath -MainSitePath $app.physicalPath -MainRoot $mainSiteRoot -WorktreeRoot $worktreeRoot

                    if ($localPath) {
                        if (Test-Path $localPath) {
                            New-WebApplication -Site $iisName -Name $app.path.Trim("/") -PhysicalPath $localPath -Force | Out-Null

                            # Grant permissions only on worktree-local path (safe - within our worktree)
                            icacls $localPath /grant "${appPoolUser}:(OI)(CI)R" | Out-Null

                            Write-VerboseHost "   + App: $($app.path) -> $localPath"
                        } else {
                            Write-Host "   - App: $($app.path) skipped (path not found in worktree: $localPath)" -ForegroundColor Yellow
                        }
                    } else {
                        Write-Host "   - App: $($app.path) skipped (external path, not cloning for isolation)" -ForegroundColor Yellow
                    }
                } catch {
                    Write-Warning "   ! Failed to create App '$($app.path)': $_"
                }
            }
        }
    } else {
        Write-Warning "  Could not locate main site binding (local.cognito.dev). Virtual Directories were not created."
    }

    # --- Grant permissions for static content folders ---
    # The IIS anonymous user (IUSR) needs read access to serve static files.
    # Without this, requests fall through to ASP.NET and get 302 redirects to login.
    # The location block with runAllManagedModulesForAllRequests="false" in Web.config
    # handles disabling managed modules - we just need file permissions.
    $contentPath = Join-Path $Path "Content"
    if (Test-Path $contentPath) {
        Write-VerboseHost "  Granting IUSR permissions on Content folder (for static file serving)..."
        icacls $contentPath /grant "IUSR:(OI)(CI)R" 2>&1 | Out-Null
        Write-VerboseHost "   + Content folder permissions set" -ForegroundColor Green
    } else {
        Write-Warning "  Content folder not found at: $contentPath"
    }

    Write-Host "  IIS Site Created: https://$hostName" -ForegroundColor Green

    # --- POST-CREATION VALIDATION ---
    # Verify the worktree site was created correctly and main site wasn't corrupted
    Write-VerboseHost "  Validating site creation..."

    # Check worktree site exists and has correct path
    $worktreeSite = Get-Website -Name $iisName -ErrorAction SilentlyContinue
    if (-not $worktreeSite) {
        Write-Error "CRITICAL: Worktree site '$iisName' was not created!"
        return
    }
    if ($worktreeSite.PhysicalPath -ne $Path) {
        Write-Error "CRITICAL: Worktree site has wrong physical path!"
        Write-Error "  Expected: $Path"
        Write-Error "  Actual: $($worktreeSite.PhysicalPath)"
        return
    }

    # Check main site wasn't corrupted
    if (-not [string]::IsNullOrWhiteSpace($foundMainSiteName)) {
        $mainSiteAfter = Get-Website -Name $foundMainSiteName -ErrorAction SilentlyContinue
        if ($mainSiteAfter) {
            $mainSitePathAfter = $mainSiteAfter.PhysicalPath
            if ($mainSitePathAfter -ne $mainSitePathSnapshot) {
                Write-Error "CRITICAL: Main site '$foundMainSiteName' was corrupted during worktree creation!"
                Write-Error "  Before: $mainSitePathSnapshot"
                Write-Error "  After: $mainSitePathAfter"
                Write-Host "  Attempting to restore main site..." -ForegroundColor Yellow
                try {
                    Set-ItemProperty "IIS:\Sites\$foundMainSiteName" -Name physicalPath -Value $mainSitePathSnapshot
                    Write-Host "  Main site restored successfully." -ForegroundColor Green
                } catch {
                    Write-Error "  Failed to restore main site: $_"
                    Write-Error "  Please manually fix the main site in IIS Manager."
                    return
                }
            }
        } else {
            Write-Warning "  Main site '$foundMainSiteName' no longer exists after worktree creation!"
        }
    }

    Write-VerboseHost "  Validation passed." -ForegroundColor Green

    # 4. Web.Config Transformation
    $webConfigPath = Join-Path $Path "web.config"

    # SAFETY CHECK: Ensure we are NOT writing to the main repo's config (check BEFORE reading)
    $mainRepoConfig = Join-Path $gitRoot "Cognito.Services\web.config"
    $webConfigResolved = if (Test-Path $webConfigPath) { (Get-Item $webConfigPath).FullName } else { $null }
    $mainConfigResolved = if (Test-Path $mainRepoConfig) { (Get-Item $mainRepoConfig).FullName } else { $null }

    if ($webConfigResolved -and $mainConfigResolved -and ($webConfigResolved -ieq $mainConfigResolved)) {
        Write-Error "CRITICAL ERROR: Web.config path resolves to main repository!"
        Write-Error "  Worktree config: $webConfigResolved"
        Write-Error "  Main config: $mainConfigResolved"
        Write-Error "Aborting to prevent main site corruption."
        return
    }

    if (Test-Path $webConfigPath) {
        Write-VerboseHost "  Updating Web.Config..."
        $rawContent = Get-Content $webConfigPath -Raw
        if (-not [string]::IsNullOrWhiteSpace($rawContent)) {
            $rawContent = $rawContent.Replace("local.cognito.dev", $hostName)

            [xml]$xml = $rawContent

            # Domain & SPA Port
            $domainNode = $xml.SelectSingleNode("//domain")
            if ($domainNode) { $domainNode.InnerText = $hostName }

            $spaNode = $xml.SelectSingleNode("//spaAssetsUrl")
            if ($spaNode) { $spaNode.InnerText = "https://localhost:$SpaPort" }

            # NOTE: Web.config already has correct location blocks with runAllManagedModulesForAllRequests="false"
            # inherited from git. IIS has built-in font MIME types. The IUSR permission grant (above) is
            # what actually enables static file serving - no Web.config XML manipulation needed.

            # Save
            $settings = New-Object System.Xml.XmlWriterSettings
            $settings.Indent = $true
            $settings.IndentChars = "`t"
            $settings.NewLineOnAttributes = $false

            $writer = [System.Xml.XmlWriter]::Create($webConfigPath, $settings)
            $xml.Save($writer)
            $writer.Flush()
            $writer.Dispose()

            Write-VerboseHost "  Web.config updated (Domain, SPA Port)"
        }
    }

    # 5. SPA .Env Transformation
    $envPath = Join-Path $Path "..\Cognito.Web.Client\apps\spa\.env"

    # SAFETY CHECK: Ensure we're not modifying main repo's .env
    $mainSpaEnv = Join-Path $gitRoot "Cognito.Web.Client\apps\spa\.env"
    $envResolved = if (Test-Path $envPath) { (Get-Item $envPath).FullName } else { $null }
    $mainSpaEnvResolved = if (Test-Path $mainSpaEnv) { (Get-Item $mainSpaEnv).FullName } else { $null }

    if ($envResolved -and $mainSpaEnvResolved -and ($envResolved -ieq $mainSpaEnvResolved)) {
        Write-Error "CRITICAL ERROR: SPA .env path resolves to main repository! Aborting."
        return
    }

    if (Test-Path $envPath) {
        $content = Get-Content $envPath

        # 1. Update DEV_SERVER_PORT
        $content = $content -replace "DEV_SERVER_PORT=\d+", "DEV_SERVER_PORT=$SpaPort"

        # 2. Update COMPONENT_LIB_PORT (Default offset +4, preventing conflicts)
        $compLibPort = [int]$SpaPort + 4
        $content = $content -replace "COMPONENT_LIB_PORT=\d+", "COMPONENT_LIB_PORT=$compLibPort"

        # 3. Update Domain Globally (This handles SERVER_URL, SITE_URL, and SPA_ASSET_URL while preserving paths)
        $content = $content -replace [regex]::Escape("local.cognito.dev"), $hostName

        $content | Set-Content $envPath
        Write-VerboseHost "  SPA .env updated (Ports: $SpaPort, $compLibPort)"
    }

    # 6. Client .Env Transformation (Form-client dev server ports)
    $clientEnvPath = Join-Path $Path "..\Cognito.Web.Client\apps\client\.env"

    # SAFETY CHECK: Ensure we're not modifying main repo's client .env
    $mainClientEnv = Join-Path $gitRoot "Cognito.Web.Client\apps\client\.env"
    $clientEnvResolved = if (Test-Path $clientEnvPath) { (Get-Item $clientEnvPath).FullName } else { $null }
    $mainClientEnvResolved = if (Test-Path $mainClientEnv) { (Get-Item $mainClientEnv).FullName } else { $null }

    if ($clientEnvResolved -and $mainClientEnvResolved -and ($clientEnvResolved -ieq $mainClientEnvResolved)) {
        Write-Error "CRITICAL ERROR: Client .env path resolves to main repository! Aborting."
        return
    }

    if (Test-Path $clientEnvPath) {
        $content = Get-Content $clientEnvPath

        # Calculate client ports with offset from SPA port to avoid conflicts
        # SpaPort+2 for modern, SpaPort+3 for legacy (leaving +4 for COMPONENT_LIB_PORT)
        $clientModernPort = [int]$SpaPort + 2
        $clientLegacyPort = [int]$SpaPort + 3

        # Update DEV_SERVER_MODERN_PORT and DEV_SERVER_LEGACY_PORT
        $content = $content -replace "DEV_SERVER_MODERN_PORT=\d+", "DEV_SERVER_MODERN_PORT=$clientModernPort"
        $content = $content -replace "DEV_SERVER_LEGACY_PORT=\d+", "DEV_SERVER_LEGACY_PORT=$clientLegacyPort"

        # Update domain references
        $content = $content -replace [regex]::Escape("local.cognito.dev"), $hostName

        $content | Set-Content $clientEnvPath
        Write-VerboseHost "  Client .env updated (Ports: $clientModernPort, $clientLegacyPort)"
    }

    # 7. .csproj IISUrl Transformation (CRITICAL: prevents VS from corrupting main site)
    # When VS opens the worktree solution, it reads <IISUrl> and syncs with IIS.
    # If left as "local.cognito.dev", VS will find and corrupt the main site's physical path.
    # By changing it to the worktree's domain, VS syncs with the worktree's IIS site instead.
    $csprojPath = Join-Path $Path "Cognito.Services.csproj"

    # SAFETY CHECK: Ensure we're not modifying main repo's .csproj
    $mainCsproj = Join-Path $gitRoot "Cognito.Services\Cognito.Services.csproj"
    $csprojResolved = if (Test-Path $csprojPath) { (Get-Item $csprojPath).FullName } else { $null }
    $mainCsprojResolved = if (Test-Path $mainCsproj) { (Get-Item $mainCsproj).FullName } else { $null }

    if ($csprojResolved -and $mainCsprojResolved -and ($csprojResolved -ieq $mainCsprojResolved)) {
        Write-Error "CRITICAL ERROR: .csproj path resolves to main repository! Aborting."
        return
    }

    if (Test-Path $csprojPath) {
        $content = Get-Content $csprojPath -Raw
        $originalContent = $content

        # Update IISUrl to use worktree's domain
        $content = $content -replace '<IISUrl>https://local\.cognito\.dev</IISUrl>', "<IISUrl>https://$hostName</IISUrl>"

        if ($content -ne $originalContent) {
            $content | Set-Content $csprojPath -NoNewline
            Write-VerboseHost "  .csproj IISUrl updated to: https://$hostName"
        }
    }
}

function Teardown-IIS-DualSite {
    param($Name)
    $iisName = "$projectName-$Name"
    $hostName = "$Name.cognito.dev"

    Write-Host "Cleaning up Dual Site infrastructure..." -ForegroundColor Cyan

    # 1. Remove IIS (comprehensive cleanup)
    Import-Module WebAdministration -WarningAction SilentlyContinue

    if (Test-Path "IIS:\Sites\$iisName") {
        Write-VerboseHost "  Removing IIS site components..."

        # Remove virtual directories first (suppress IIS cmdlet output)
        try {
            $vdirs = Get-WebVirtualDirectory -Site $iisName -ErrorAction SilentlyContinue
            foreach ($vdir in $vdirs) {
                $vdirName = $vdir.path.Trim("/")
                Write-VerboseHost "    Removing virtual directory: $vdirName"
                Remove-Item "IIS:\Sites\$iisName\$vdirName" -Recurse -Force -ErrorAction SilentlyContinue 2>&1 | Out-Null
            }
        } catch {
            # Silently continue - vdirs may not exist
        }

        # Remove web applications (except root "/") - suppress IIS cmdlet output
        try {
            $apps = Get-WebApplication -Site $iisName -ErrorAction SilentlyContinue
            foreach ($app in $apps | Where-Object { $_.path -ne "/" }) {
                $appName = $app.path.Trim("/")
                Write-VerboseHost "    Removing web application: $appName"
                Remove-Item "IIS:\Sites\$iisName\$appName" -Recurse -Force -ErrorAction SilentlyContinue 2>&1 | Out-Null
            }
        } catch {
            # Silently continue - apps may not exist
        }

        # Now remove the site itself
        Remove-WebSite $iisName -Confirm:$false 2>&1 | Out-Null
        Write-VerboseHost "  IIS Site removed."
    }

    if (Test-Path "IIS:\AppPools\$iisName") {
        Remove-WebAppPool $iisName -Confirm:$false 2>&1 | Out-Null
        Write-VerboseHost "  App Pool removed."
    }

    # Remove the user profile Windows auto-created when the app pool first ran.
    # IIS app pools with loadUserProfile=true (the default) materialize
    # C:\Users\<AppPoolName>\. Removing the pool does NOT clean up the profile,
    # so without this step every teardown leaves an orphan profile behind.
    $userProfile = Get-CimInstance Win32_UserProfile -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPath -eq "C:\Users\$iisName" }
    if ($userProfile -and -not $userProfile.Loaded -and -not $userProfile.Special) {
        try {
            Remove-CimInstance -InputObject $userProfile -ErrorAction Stop
            Write-VerboseHost "  User profile removed: C:\Users\$iisName"
        } catch {
            Write-VerboseHost "  Could not remove user profile at C:\Users\$iisName : $_"
        }
    }

    # Verify main site wasn't contaminated
    $mainSiteName = $null
    try {
        $allSites = Get-Website
        foreach ($s in $allSites) {
            $bindings = $s.Bindings
            if ($bindings.GetType().Name -eq "ConfigurationElementCollection") {
                $bindings = $bindings.Collection
            }

            foreach ($b in $bindings) {
                if ($b.bindingInformation -match ":80:local\.cognito\.dev$" -or
                    $b.bindingInformation -match ":443:local\.cognito\.dev$") {
                    $mainSiteName = $s.Name
                    break
                }
            }
            if ($mainSiteName) { break }
        }

        if ($mainSiteName) {
            Write-VerboseHost "  Verifying main site integrity..."
            $contaminated = $false

            # Get expected main repo path for validation
            $expectedMainRepoPath = $gitRoot
            $expectedMainSitePath = Join-Path $gitRoot "Cognito.Services"

            # CRITICAL: Check main site's ROOT physical path first
            $mainSite = Get-Website -Name $mainSiteName -ErrorAction SilentlyContinue
            if ($mainSite) {
                $mainSitePhysicalPath = $mainSite.PhysicalPath
                if ($mainSitePhysicalPath -like "*$projectName-$Name*") {
                    Write-Warning "    CONTAMINATION: Main site root path points to deleted worktree: $mainSitePhysicalPath"
                    $contaminated = $true

                    # Attempt to restore the main site path
                    if (Test-Path $expectedMainSitePath) {
                        Write-Host "      Restoring main site path to: $expectedMainSitePath" -ForegroundColor Yellow
                        try {
                            Set-ItemProperty "IIS:\Sites\$mainSiteName" -Name physicalPath -Value $expectedMainSitePath
                            Write-Host "      Main site path restored successfully." -ForegroundColor Green
                        } catch {
                            Write-Error "      Failed to restore main site path: $_"
                        }
                    } else {
                        Write-Warning "      Cannot auto-restore: expected path doesn't exist: $expectedMainSitePath"
                    }
                }
            }

            # Check virtual directories
            $mainVdirs = Get-WebVirtualDirectory -Site $mainSiteName -ErrorAction SilentlyContinue
            foreach ($vdir in $mainVdirs) {
                if ($vdir.physicalPath -like "*$projectName-$Name*") {
                    Write-Warning "    CONTAMINATION: Main site vdir '$($vdir.path)' points to deleted worktree: $($vdir.physicalPath)"
                    $contaminated = $true

                    # Attempt to restore to main repo path - with safety checks
                    $originalPath = $vdir.physicalPath -replace [regex]::Escape("$projectName-$Name"), $projectName

                    # SAFETY: Only restore if the target path is within the main repo
                    if ((Test-Path $originalPath) -and $originalPath.StartsWith($expectedMainRepoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                        Write-Host "      Restoring to: $originalPath" -ForegroundColor Yellow
                        try {
                            Set-ItemProperty "IIS:\Sites\$mainSiteName\$($vdir.path)" -Name physicalPath -Value $originalPath
                            Write-Host "      Restored successfully." -ForegroundColor Green
                        } catch {
                            Write-Error "      Failed to restore: $_"
                        }
                    } else {
                        Write-Warning "      Cannot auto-restore: target path doesn't exist or is outside main repo"
                        Write-Warning "      Expected: $originalPath"
                    }
                }
            }

            # Check web applications
            $mainApps = Get-WebApplication -Site $mainSiteName -ErrorAction SilentlyContinue
            foreach ($app in $mainApps | Where-Object { $_.path -ne "/" }) {
                if ($app.physicalPath -like "*$projectName-$Name*") {
                    Write-Warning "    CONTAMINATION: Main site app '$($app.path)' points to deleted worktree: $($app.physicalPath)"
                    $contaminated = $true

                    # Attempt to restore - with safety checks
                    $originalPath = $app.physicalPath -replace [regex]::Escape("$projectName-$Name"), $projectName

                    # SAFETY: Only restore if the target path is within the main repo
                    if ((Test-Path $originalPath) -and $originalPath.StartsWith($expectedMainRepoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                        Write-Host "      Restoring to: $originalPath" -ForegroundColor Yellow
                        try {
                            Set-ItemProperty "IIS:\Sites\$mainSiteName\$($app.path)" -Name physicalPath -Value $originalPath
                            Write-Host "      Restored successfully." -ForegroundColor Green
                        } catch {
                            Write-Error "      Failed to restore: $_"
                        }
                    } else {
                        Write-Warning "      Cannot auto-restore: target path doesn't exist or is outside main repo"
                        Write-Warning "      Expected: $originalPath"
                    }
                }
            }

            if ($contaminated) {
                Write-Host "  Restarting IIS to clear cached configuration..." -ForegroundColor Yellow
                iisreset /restart | Out-Null
                Write-Host "  IIS restarted." -ForegroundColor Green
            } else {
                Write-Host "  Main site integrity verified." -ForegroundColor Green
            }
        }
    } catch {
        Write-Warning "  Could not verify main site integrity: $_"
    }

    # 2. Clean Hosts
    $hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
    $content = Get-Content $hostsPath
    $newContent = $content | Where-Object { $_ -notmatch [regex]::Escape($hostName) }
    if ($content.Count -ne $newContent.Count) {
        $newContent | Set-Content $hostsPath
        Write-VerboseHost "  Hosts file entry removed."
    }
}

# --- INTERACTIVE WIZARD ---
if ([string]::IsNullOrWhiteSpace($Name)) {
    Write-Host "------------------------------------------------"

    # 1. Mode
    $mode = Read-Host "Do you want to (c)reate or (r)emove a worktree? [c/r]"
    if ($mode -match "^r") {
        $Cleanup = $true
    }

    # 2. Name Selection
    if ($Cleanup) {
        $candidates = Get-ChildItem -Path $parentDir -Directory -Filter "$projectName-*"
        if ($candidates) {
             Write-Host "`nFound existing worktrees:"
             for ($i = 0; $i -lt $candidates.Count; $i++) {
                 $suffix = $candidates[$i].Name.Substring($projectName.Length + 1)
                 Write-Host " [$($i+1)] $suffix"
             }
             $sel = Read-Host "Choice"
             if ($sel -match "^\d+$" -and $sel -le $candidates.Count) {
                 $Name = $candidates[$sel-1].Name.Substring($projectName.Length + 1)
             } else {
                 Write-Error "Invalid selection."; return
             }
        } else {
             Write-Host "No existing worktrees found." -ForegroundColor Yellow
             return
        }
    }

    if (-not $Cleanup -and [string]::IsNullOrWhiteSpace($Name)) {
        $Name = Read-Host "Enter a name for this worktree"
    }
    if ([string]::IsNullOrWhiteSpace($Name)) { Write-Error "Name is required."; return }

    # 3. Creation Config
    if (-not $Cleanup) {
        $Branch = Read-Host "`nEnter a branch name (new or existing)"

        # Ask DualSite FIRST - determines whether to ask for port/deps/dev
        if ($isAdmin) {
            $dualChoice = Read-Host "Configure Dual Site Mode (Parallel IIS Backend)? [y/n]"
            if ($dualChoice -match "^y") { $DualSite = $true }
        }

        # Auto-assign port and enable deps/dev for DualSite mode
        if ($DualSite) {
            # Auto-calculate port based on existing worktrees (base 7785 + count * 10)
            # Increment by 10 to leave room for related ports (modern +2, legacy +3, component lib +4)
            $existingWorktrees = Get-ChildItem -Path $parentDir -Directory -Filter "$projectName-*"
            $spaPort = 7785 + ($existingWorktrees.Count * 10)
            Write-Host "SPA Port: $spaPort" -ForegroundColor Cyan

            # DualSite implies full local dev environment
            $InstallDeps = $true
            $RunDev = $true
        }
    }
    Write-Host "------------------------------------------------`n"
}

# --- VALIDATION & PATHS ---
if (-not $Cleanup -and [string]::IsNullOrWhiteSpace($Branch)) { Write-Error "Branch required."; return }
if ([string]::IsNullOrWhiteSpace($Name)) { Write-Error "Name required."; return }

# Check for collisions (Creation Only)
if (-not $Cleanup) {
    while ($true) {
        $targetDirName = "$projectName-$Name"
        $targetPath = Join-Path $parentDir $targetDirName

        if (Test-Path $targetPath) {
            Write-Warning "The worktree name '$Name' is already in use."
            Write-Host "Location: $targetPath" -ForegroundColor Red

            Write-Host "`nCurrent Worktrees:" -ForegroundColor Cyan
            $candidates = Get-ChildItem -Path $parentDir -Directory -Filter "$projectName-*"
            foreach ($c in $candidates) {
                $suffix = $c.Name.Substring($projectName.Length + 1)
                if ($suffix -eq $Name) { Write-Host " - $suffix (CONFLICT)" -ForegroundColor Red }
                else { Write-Host " - $suffix" -ForegroundColor Gray }
            }

            $newName = Read-Host "`nPlease enter a different name/suffix"
            if ([string]::IsNullOrWhiteSpace($newName)) {
                Write-Error "Name cannot be empty."
                return
            }
            $Name = $newName
        }
        else {
            # Name is unique, break loop
            break
        }
    }
}

# Re-calculate final path (Create or Cleanup)
$targetDirName = "$projectName-$Name"
$targetPath = Join-Path $parentDir $targetDirName

# --- CLEANUP LOGIC ---
if ($Cleanup) {
    Write-Host "Attempting to remove worktree at: $targetPath"
    if (-not (Test-Path $targetPath)) { Write-Warning "Directory not found."; return }
    if ($gitRoot -eq $targetPath) { Write-Error "Cannot delete current directory."; return }

    # --- NEW WARNING ---
    Write-Host "`n[ATTENTION] To prevent file locking errors:" -ForegroundColor Yellow
    Write-Host "  1. Close any Visual Studio instances opened for this worktree."
    Write-Host "  2. Close any terminal windows (Dev Server, etc) currently inside this directory."
    Read-Host "Press Enter once you have closed these applications..."
    # -------------------

    # Unlink any claude-config symlinks FIRST so the recursive removal below can never
    # traverse a directory link and delete the shared claude-config source.
    Remove-ClaudeConfigSymlinks -TargetClaude (Join-Path $targetPath ".claude")
    Remove-RootConfigSymlinks -TargetWorktree $targetPath

    # Clean up IIS resources (Only if Admin)
    if ($isAdmin) {
        Import-Module WebAdministration -WarningAction SilentlyContinue
        if (Test-Path "IIS:\Sites\$projectName-$Name") {
            Teardown-IIS-DualSite -Name $Name
        }
    }

    # Attempt to kill the dev server window spawned by this script
    $devTitle = "Worktree Dev ($Name)"
    $processes = Get-Process | Where-Object { $_.MainWindowTitle -eq $devTitle }
    if ($processes) {
        Write-Host "Stopping Dev Server ($devTitle)..." -ForegroundColor Yellow
        $processes | Stop-Process -Force
        Start-Sleep -Seconds 1 # Give handles time to release
    }

    # --- PRE-CLEANUP LOCKS (.vs) ---
    $vsPath = Join-Path $targetPath ".vs"
    Invoke-RemovalWithSpinner -Label "Visual Studio temp files" -Path $vsPath

    # --- PRE-CLEANUP HEAVY FOLDERS (Fixes Git "Filename too long" & Locking) ---
    # Git chokes on deep paths or locked hidden folders. We remove them robustly first.
    Write-VerboseHost "Removing large folders..."
    $heavyPaths = @(
        @{ Path = Join-Path $targetPath "node_modules"; Name = "node_modules (root)" }
        @{ Path = Join-Path $targetPath "Cognito.Web.Client\node_modules"; Name = "node_modules (web client)" }
        @{ Path = Join-Path $targetPath ".nx"; Name = ".nx cache (root)" }
        @{ Path = Join-Path $targetPath "Cognito.Web.Client\.nx"; Name = ".nx cache (web client)" }
        @{ Path = Join-Path $targetPath "Cognito.Services\bin"; Name = "bin" }
        @{ Path = Join-Path $targetPath "Cognito.Services\obj"; Name = "obj" }
    )
    foreach ($item in $heavyPaths) {
        Invoke-RemovalWithSpinner -Label $item.Name -Path $item.Path
    }

    # --- WORKTREE STATE CHECK ---
    # If .git file is missing, the worktree is already partially removed or was never fully created
    if (-not (Test-Path "$targetPath\.git")) {
        Write-Host "Worktree partially removed. Completing cleanup..." -ForegroundColor Yellow
        Write-VerboseHost "  Pruning git worktree metadata..."
        git worktree prune 2>&1 | Out-Null
        Invoke-RemovalWithSpinner -Label "Remaining files" -Path $targetPath
        if (-not (Test-Path $targetPath)) {
            Write-Host "Successfully removed worktree: $targetDirName" -ForegroundColor Green
        } else {
            Write-Error "Could not delete directory. Please close all apps and delete manually."
        }
        return
    }

    # --- SMART FORCE CHECK ---
    # If the only changes are Web.config or .env (which we modified), we auto-force.
    $useForce = $Force
    if (-not $useForce) {
        try {
            # Check git status in the worktree
            $status = git -C "$targetPath" status --porcelain 2>&1
            if ($LASTEXITCODE -eq 0) {
                $changes = $status | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

                # Filter out known acceptable changes (Web.config, .env, .csproj)
                $dangerousChanges = @()
                foreach ($line in $changes) {
                    if ($line -match "web\.config$") { continue }
                    if ($line -match "\.env$") { continue }
                    if ($line -match "\.csproj$") { continue }
                    $dangerousChanges += $line
                }

                if ($changes.Count -gt 0 -and $dangerousChanges.Count -eq 0) {
                    Write-Host "Auto-enabling force remove (only wizard-generated changes detected)." -ForegroundColor Green
                    $useForce = $true
                }
            }
        } catch {
            # Silently continue - git status failed, will try normal removal
        }
    }

    # --- REMOVAL ATTEMPT ---
    Write-VerboseHost "Removing worktree..."
    $ErrorActionPreference = 'SilentlyContinue'
    if ($useForce) {
        $null = git worktree remove $targetPath --force 2>&1
    } else {
        $null = git worktree remove $targetPath 2>&1
    }
    $ErrorActionPreference = 'Continue'

    if ($LASTEXITCODE -ne 0) {
        # If auto-force was already enabled but still failed, go straight to fallback
        if ($useForce) {
            Write-Host "  Git removal incomplete. Completing cleanup manually..." -ForegroundColor Yellow
        } else {
            # Only prompt if we weren't already using force
            Write-Warning "Git refused to remove (likely due to modified/untracked files)."
            $forceInput = Read-Host "Force remove? (All uncommitted changes will be lost) [y/n]"
            if ($forceInput -notmatch "^y") {
                Write-Warning "Worktree was NOT removed. Please check directory manually."
                return
            }
            # Try force removal
            $ErrorActionPreference = 'SilentlyContinue'
            $null = git worktree remove $targetPath --force 2>&1
            $ErrorActionPreference = 'Continue'
            if ($LASTEXITCODE -eq 0) {
                $null = git worktree prune 2>&1
                Write-Host "Successfully removed worktree: $targetDirName" -ForegroundColor Green
                return
            }
        }

        # Fallback: manual cleanup
        Write-VerboseHost "  Pruning git worktree metadata..."
        $null = git worktree prune 2>&1
        Invoke-RemovalWithSpinner -Label "Remaining files" -Path $targetPath

        if (-not (Test-Path $targetPath)) {
            Write-Host "Successfully removed worktree: $targetDirName" -ForegroundColor Green
        } else {
            Write-Error "Could not delete directory. Please close all apps and delete manually."
        }
    } else {
        git worktree prune 2>&1 | Out-Null
        Write-Host "Successfully removed worktree: $targetDirName" -ForegroundColor Green
    }
}
# --- CREATION LOGIC ---
else {
    if (Test-Path $targetPath) { Write-Error "Target directory exists."; return }

    # --- FIX: DETECT EXISTING BRANCH CORRECTLY ---
    git show-ref --verify --quiet "refs/heads/$Branch"
    $localExists = $LASTEXITCODE -eq 0

    $remoteExists = $false
    if (-not $localExists) {
        $remoteOutput = git ls-remote --heads origin $Branch
        $remoteExists = -not [string]::IsNullOrWhiteSpace($remoteOutput)
    }

    if ($localExists -or $remoteExists) {
        Write-Host "Branch '$Branch' found. Checking out..."
        git worktree add $targetPath $Branch
    }
    else {
        # New branch - ensure main is up to date first
        Write-Host "Creating new branch '$Branch' from latest main..."
        Write-VerboseHost "  Fetching latest from remote..."
        $ErrorActionPreference = 'SilentlyContinue'
        git fetch origin main 2>&1 | Out-Null
        $fetchExitCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($fetchExitCode -ne 0) {
            Write-Warning "Failed to fetch from remote. Proceeding with local main."
        }

        # Pull main if we're currently on main branch
        $currentBranch = git branch --show-current
        if ($currentBranch -eq "main") {
            Write-VerboseHost "  Updating main branch..."
            $ErrorActionPreference = 'SilentlyContinue'
            git pull origin main 2>&1 | Out-Null
            $pullExitCode = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($pullExitCode -ne 0) {
                Write-Warning "Failed to pull main. Proceeding with current state."
            }
        }

        git worktree add -b $Branch $targetPath main
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create worktree. See git error message above."
        return
    }

    # IIS Permissions (Only if Admin AND setting up a local site)
    if ($isAdmin -and $DualSite) {
        Write-VerboseHost "Granting IIS_IUSRS Modify permissions..."
        icacls "$targetPath" /grant "IIS_IUSRS:(OI)(CI)M" | Out-Null
    }

    # Config Copy (always copy from main worktree to ensure all local files are included)
    Write-VerboseHost "Copying configuration files from main worktree..."
    foreach ($item in $filesToCopy) {
        $sourcePath = Join-Path $mainWorktree $item
        if (Test-Path $sourcePath) { Copy-Item -Path $sourcePath -Destination $targetPath -Recurse -Force }
    }

    # Re-link the personal claude-config entries the copy above dereferenced into frozen
    # copies, so repo-scoped skills/skill-config/knowledge (etc.) track claude-config live.
    Sync-ClaudeConfigSymlinks -MainClaude (Join-Path $mainWorktree ".claude") -TargetClaude (Join-Path $targetPath ".claude")

    # Re-link repo-root claude-config entries (e.g. CLAUDE.local.md) the same way, so the
    # work-logging trigger and other root guidance track claude-config live instead of going missing.
    Sync-RootConfigSymlinks -MainWorktree $mainWorktree -TargetWorktree $targetPath

    # Replicate skip-worktree flags from main worktree to new worktree
    # This prevents copied config files from showing as modified in the worktree
    Write-VerboseHost "Replicating skip-worktree flags..."
    $skipWorktreeFiles = git -C $mainWorktree ls-files -v | Where-Object { $_ -match "^S " } | ForEach-Object { $_.Substring(2) }
    if ($skipWorktreeFiles) {
        Push-Location $targetPath
        try {
            foreach ($file in $skipWorktreeFiles) {
                if (Test-Path (Join-Path $targetPath $file)) {
                    git update-index --skip-worktree $file 2>$null
                    Write-VerboseHost "  Set skip-worktree: $file"
                }
            }
        }
        finally {
            Pop-Location
        }
    }

    # Copy .Local.config files from main worktree
    Write-VerboseHost "Copying .Local.config files..."
    $localConfigFiles = @(
        "Cognito.Services\Web.Local.config"
    )

    foreach ($configFile in $localConfigFiles) {
        $sourceConfigPath = Join-Path $gitRoot $configFile
        $destConfigPath = Join-Path $targetPath $configFile

        if (Test-Path $sourceConfigPath) {
            $destDir = Split-Path $destConfigPath -Parent
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Copy-Item -Path $sourceConfigPath -Destination $destConfigPath -Force
            Write-VerboseHost "  Copied: $configFile"
        }
        else {
            Write-VerboseHost "  Skipped: $configFile (not found in main worktree)"
        }
    }

    # Dual Site Setup
    if ($DualSite) {
        # Auto-calculate port if not already set (non-interactive -DualSite flag)
        if ([string]::IsNullOrWhiteSpace($spaPort)) {
            $existingWorktrees = Get-ChildItem -Path $parentDir -Directory -Filter "$projectName-*"
            $spaPort = 7785 + ($existingWorktrees.Count * 10)
        }
        if ($isAdmin) {
            $iisPath = Join-Path $targetPath "Cognito.Services"
            if (Test-Path $iisPath) {
                Setup-IIS-DualSite -Name $Name -Path $iisPath -SpaPort $spaPort
            } else {
                Write-Warning "Could not find 'Cognito.Services' in worktree. Skipping IIS setup."
            }
        } else {
            Write-Warning "Dual Site Mode skipped (Requires Administrator privileges)."
        }
    }

    # Deps
    if ($InstallDeps) {
        Write-Host "Initializing dependencies..."

        # Root Install
        if (Test-Path (Join-Path $targetPath "package.json")) {
            Invoke-WithSpinner "pnpm install (Root)..." "pnpm install" -WorkingDirectory $targetPath
        }

        # Sub-project Install (Fix for missing node_modules in client)
        $clientPath = Join-Path $targetPath "Cognito.Web.Client"
        if (Test-Path "$clientPath\package.json") {
            Invoke-WithSpinner "pnpm install (Client)..." "pnpm install" -WorkingDirectory $clientPath
        }

        $slnPath = Join-Path $targetPath "Cognito.sln"
        if (Test-Path $slnPath) {
            Invoke-WithSpinner "dotnet restore..." "dotnet restore" -WorkingDirectory $targetPath
        }
    }

    # Pre-create obj directories for projects with early build targets (Verify.props race condition)
    # Without this, first VS build fails because Verify targets run before MSBuild creates obj\Debug
    # This runs outside InstallDeps block to ensure it always happens for DualSite mode
    $objPaths = @(
        "Cognito.UnitTests\obj\Debug",
        "Cognito.Forms.UnitTests\obj\Debug"
    )
    foreach ($p in $objPaths) {
        $fullPath = Join-Path $targetPath $p
        if (-not (Test-Path $fullPath)) {
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        }
    }

    # Dev Server (start early so it's ready while build runs)
    if ($RunDev) {
        $devPath = Join-Path $targetPath "Cognito.Web.Client"
        if (Test-Path $devPath) {
            Write-Host "Starting dev server..."
            # Using CMD /k to keep window open
            Start-Process cmd -ArgumentList "/k title Worktree Dev ($Name) && cd /d ""$devPath"" && pnpm serve:spa"
        }
    }

    # Build solution (DualSite mode only)
    # NOTE: MSBuild must run synchronously (not in background job) to preserve VS environment
    if ($DualSite) {
        $msbuildPath = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\2022\*\MSBuild\Current\Bin\MSBuild.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
        $slnPath = Join-Path $targetPath "Cognito.sln"
        if ($msbuildPath -and (Test-Path $slnPath)) {
            # NuGet restore for legacy packages.config projects (populates packages/ folder)
            # Try: VS installation -> PATH -> download from nuget.org
            $nugetPath = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\2022\*\Common7\IDE\CommonExtensions\Microsoft\NuGet\nuget.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
            if (-not $nugetPath) {
                $nugetCmd = Get-Command nuget -ErrorAction SilentlyContinue
                $nugetPath = if ($nugetCmd) { $nugetCmd.Source } else { $null }
            }
            if (-not $nugetPath) {
                # Download nuget.exe to temp if not found
                $nugetPath = Join-Path $env:TEMP "nuget.exe"
                if (-not (Test-Path $nugetPath)) {
                    Write-Host "  Downloading NuGet... " -NoNewline
                    try {
                        Invoke-WebRequest -Uri "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe" -OutFile $nugetPath -UseBasicParsing
                        Write-Host "Done" -ForegroundColor Green
                    } catch {
                        Write-Host "Failed" -ForegroundColor Red
                        $nugetPath = $null
                    }
                }
            }

            if ($nugetPath) {
                Write-Host "  Restoring NuGet packages... " -NoNewline
                $nugetLogFile = Join-Path $env:TEMP "nuget-$(Get-Random).log"
                $nugetProcess = Start-Process -FilePath $nugetPath -ArgumentList "restore", "`"$slnPath`"", "-NonInteractive" -WorkingDirectory $targetPath -NoNewWindow -Wait -PassThru -RedirectStandardOutput $nugetLogFile -RedirectStandardError "$nugetLogFile.err"

                $nugetOutput = @()
                if (Test-Path $nugetLogFile) { $nugetOutput += Get-Content $nugetLogFile; Remove-Item $nugetLogFile -Force }
                if (Test-Path "$nugetLogFile.err") { $nugetOutput += Get-Content "$nugetLogFile.err"; Remove-Item "$nugetLogFile.err" -Force }

                if ($nugetProcess.ExitCode -eq 0) {
                    Write-Host "Done" -ForegroundColor Green
                    if ($script:ShowDetails -and $nugetOutput) {
                        $nugetOutput | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                    }
                } else {
                    Write-Host "Failed! (exit code: $($nugetProcess.ExitCode))" -ForegroundColor Red
                    if ($nugetOutput) {
                        $nugetOutput | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                    }
                }
            } else {
                Write-Host "  Skipping NuGet restore (nuget.exe not found)" -ForegroundColor Yellow
            }

            # Run MSBuild with spinner animation
            $logFile = Join-Path $env:TEMP "msbuild-$(Get-Random).log"
            $process = Start-Process -FilePath $msbuildPath -ArgumentList "`"$slnPath`"", "-restore", "-p:WarningLevel=0", "-verbosity:minimal", "-nologo" -WorkingDirectory $targetPath -NoNewWindow -PassThru -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"

            # Animate spinner while build runs
            $spinner = @('|', '/', '-', '\')
            $i = 0
            while (-not $process.HasExited) {
                Write-Host "`r  Building solution... $($spinner[$i % 4])" -NoNewline
                $i++
                Start-Sleep -Milliseconds 200
            }
            $process.WaitForExit()

            $buildOutput = @()
            if (Test-Path $logFile) { $buildOutput += Get-Content $logFile; Remove-Item $logFile -Force }
            if (Test-Path "$logFile.err") { $buildOutput += Get-Content "$logFile.err"; Remove-Item "$logFile.err" -Force }

            # Check if main project was built (more reliable than exit code which can be non-zero due to warnings)
            $servicesPath = Join-Path $targetPath "Cognito.Services\bin\Cognito.Services.dll"
            $buildSuccess = (Test-Path $servicesPath) -and ((Get-Item $servicesPath).LastWriteTime -gt (Get-Date).AddMinutes(-5))

            if ($buildSuccess) {
                Write-Host "`r  Building solution... Done   " -ForegroundColor Green
                if ($script:ShowDetails -and $buildOutput) {
                    $buildOutput | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                }
            } else {
                Write-Host "`r  Building solution... Failed!" -ForegroundColor Red
                if ($buildOutput) {
                    $buildOutput | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
                }
                Write-Warning "Build failed. The site may not work until you rebuild in Visual Studio."
            }
        }
    }

    Write-Host "`nWorktree created at: $targetPath"
    if ($DualSite -and $isAdmin) {
        Write-Host "Local Site Url: https://$Name.cognito.dev" -ForegroundColor Green
    }
    Write-Host "------------------------------------------------"
}

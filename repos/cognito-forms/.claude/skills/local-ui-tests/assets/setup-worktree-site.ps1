# Provision a dedicated local IIS "DualSite" for the ALREADY-EXISTING worktree
# "Cognito Forms-C" (branch p/ps-ff-tests), so it can run the site locally without
# touching the canonical tree's local.cognito.dev binding.
#
# This reuses the wizard's own Setup-IIS-DualSite function verbatim (imported by
# dot-sourcing worktree-wizard.ps1) and drives it against this worktree. The wizard's
# normal create path refuses to run on an existing directory, which is why this
# standalone driver exists.
#
# REQUIRES: elevated (Administrator) PowerShell. IIS site/app-pool creation,
# netsh sslcert, and hosts-file edits are all elevation-gated.
#
# Result: https://c.cognito.dev  ->  this worktree's Cognito.Services
#         SPA dev server expected on https://localhost:<SpaPort>

[CmdletBinding()]
param(
    [string]$Name       = 'C',
    [int]   $SpaPort    = 7795,
    [string]$Canonical  = 'C:\Users\JacobMadsen\source\repos\Cognito Forms',
    [string]$Worktree   = 'C:\Users\JacobMadsen\source\repos\Cognito Forms-C'
)

$ErrorActionPreference = 'Stop'

# --- Elevation guard ---
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "This script MUST be run from an ELEVATED (Administrator) PowerShell. IIS/netsh/hosts changes require elevation."
}

$Wizard  = Join-Path $Worktree 'worktree-wizard.ps1'
$iisPath = Join-Path $Worktree 'Cognito.Services'

if (-not (Test-Path $Wizard))  { throw "Wizard not found at: $Wizard" }
if (-not (Test-Path $iisPath)) { throw "Worktree Cognito.Services not found at: $iisPath" }
if (-not (Test-Path (Join-Path $Canonical 'Cognito.Services'))) { throw "Canonical tree not found at: $Canonical" }

Write-Host "Importing Setup-IIS-DualSite from wizard..." -ForegroundColor Cyan

# Dot-source the wizard FROM the canonical tree so its $gitRoot/$projectName resolve to
# the main tree (exactly the context Setup-IIS-DualSite expects: main site = canonical,
# target = this worktree). Passing -Name skips the interactive prompts; the wizard then
# throws "Branch required." AFTER all functions are defined -- we swallow only that error.
Push-Location $Canonical
try {
    . $Wizard -Name $Name
}
catch {
    if ($_.ToString() -notmatch 'Branch required') { throw }
}
finally {
    Pop-Location
}

if (-not (Get-Command Setup-IIS-DualSite -ErrorAction SilentlyContinue)) {
    throw "Failed to import Setup-IIS-DualSite from the wizard (its structure may have changed)."
}

# Ensure the wizard's context variables point at the canonical (main) tree.
$script:gitRoot     = $Canonical
$script:projectName = Split-Path $Canonical -Leaf
$script:ShowDetails = $true

Write-Host "Provisioning IIS site '$($script:projectName)-$Name' -> $iisPath" -ForegroundColor Cyan
Write-Host "  Host: https://$($Name.ToLower()).cognito.dev   SPA dev port: $SpaPort" -ForegroundColor Cyan

Setup-IIS-DualSite -Name $Name -Path $iisPath -SpaPort $SpaPort

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Done. Worktree site provisioned." -ForegroundColor Green
Write-Host "   URL:        https://$($Name.ToLower()).cognito.dev" -ForegroundColor Green
Write-Host "   Backend:    $iisPath (build with /msbuild in the worktree)" -ForegroundColor Green
Write-Host "   SPA server: https://localhost:$SpaPort (run 'pnpm serve:spa' in the worktree)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "NOTE: this rewrote the worktree's web.config/.env/.csproj to the new"
Write-Host "domain+port. Those are LOCAL-ONLY churn -- do not commit them; revert at finalize."

# Remove-CognitoFormsProfiles.ps1
# Audits "Cognito Forms-*" IIS app pools and Windows user profiles, then
# removes profiles whose app pool no longer exists. Also writes a report
# to C:\temp\cognito-forms-profiles.txt so the audit can be reviewed after.
#
# Usage (run elevated):
#   Dry-run (default, no changes):
#     powershell -ExecutionPolicy Bypass -File .\Remove-CognitoFormsProfiles.ps1
#   Actually remove orphan profiles:
#     powershell -ExecutionPolicy Bypass -File .\Remove-CognitoFormsProfiles.ps1 -Apply
#   Also remove matching app pools (and then their profiles):
#     powershell -ExecutionPolicy Bypass -File .\Remove-CognitoFormsProfiles.ps1 -Apply -RemoveAppPools

[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$RemoveAppPools,
    [string]$ReportPath = 'C:\temp\cognito-forms-profiles.txt'
)

$ErrorActionPreference = 'Continue'

if (-not (Test-Path 'C:\temp')) { New-Item -ItemType Directory -Path 'C:\temp' | Out-Null }

$log = New-Object System.Text.StringBuilder
function Log {
    param([string]$Msg, [string]$Color = 'Gray')
    Write-Host $Msg -ForegroundColor $Color
    [void]$log.AppendLine($Msg)
}

# --- Admin check ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(`
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Log "ERROR: This script must be run from an elevated shell." 'Red'
    $log.ToString() | Out-File -LiteralPath $ReportPath -Encoding UTF8
    return
}

Log "=== Cognito Forms profile audit ($(Get-Date)) ===" 'Cyan'
Log ("Apply          : {0}" -f $Apply)
Log ("RemoveAppPools : {0}" -f $RemoveAppPools)
Log ''

# --- Step 1: enumerate IIS app pools matching Cognito Forms-* ---
Log '=== IIS app pools matching Cognito Forms-* ===' 'Cyan'
$appPools = @()
try {
    Import-Module WebAdministration -ErrorAction Stop
    $appPools = Get-ChildItem 'IIS:\AppPools' | Where-Object { $_.Name -like 'Cognito Forms-*' }
    if ($appPools) {
        foreach ($p in $appPools) {
            Log ("  {0,-45} State={1}" -f $p.Name, $p.State)
        }
    } else {
        Log '  (none found)'
    }
} catch {
    Log ("WARNING: Could not query IIS: {0}" -f $_) 'Yellow'
    Log '  (Continuing - will treat all profiles as orphans.)'
}

# --- Step 2: enumerate user profiles matching C:\Users\Cognito Forms-* ---
Log ''
Log '=== User profiles matching C:\Users\Cognito Forms-* ===' 'Cyan'
$profiles = Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like 'C:\Users\Cognito Forms-*' }

if (-not $profiles) {
    Log '  (none found)'
    $log.ToString() | Out-File -LiteralPath $ReportPath -Encoding UTF8
    Log "Report written to $ReportPath" 'Green'
    return
}

# Build the pool lookup so we can classify each profile
$poolNames = @($appPools | ForEach-Object { $_.Name })
$classified = foreach ($pr in $profiles) {
    $profileName = Split-Path -Leaf $pr.LocalPath
    $hasPool = $poolNames -contains $profileName
    [pscustomobject]@{
        ProfileName = $profileName
        LocalPath   = $pr.LocalPath
        SID         = $pr.SID
        Loaded      = $pr.Loaded
        Special     = $pr.Special
        HasAppPool  = $hasPool
        Cim         = $pr
    }
}

foreach ($c in $classified) {
    $tag = if ($c.HasAppPool) { '[has pool]' } else { '[orphan]  ' }
    Log ("  {0} {1,-45} Loaded={2} Special={3}" -f $tag, $c.ProfileName, $c.Loaded, $c.Special)
}

$orphans     = $classified | Where-Object { -not $_.HasAppPool -and -not $_.Loaded -and -not $_.Special }
$withPools   = $classified | Where-Object { $_.HasAppPool }
$skipLoaded  = $classified | Where-Object { $_.Loaded -or $_.Special }

Log ''
Log ("Orphan profiles (safe to remove): {0}" -f @($orphans).Count) 'Cyan'
Log ("Profiles still linked to app pool: {0}" -f @($withPools).Count)
Log ("Loaded/Special (skipped):         {0}" -f @($skipLoaded).Count)

# --- Step 3: optionally remove matching app pools first ---
if ($RemoveAppPools -and $appPools) {
    Log ''
    Log '=== Removing matching app pools ===' 'Cyan'
    foreach ($p in $appPools) {
        if ($Apply) {
            try {
                Remove-WebAppPool -Name $p.Name -ErrorAction Stop
                Log ("  REMOVED app pool: {0}" -f $p.Name) 'Yellow'
            } catch {
                Log ("  FAILED: {0} - {1}" -f $p.Name, $_) 'Red'
            }
        } else {
            Log ("  [dry-run] would remove app pool: {0}" -f $p.Name) 'DarkCyan'
        }
    }
    if ($Apply) {
        # Re-classify: with pools gone, the former "has pool" entries become orphans
        $orphans = $classified | Where-Object { -not $_.Loaded -and -not $_.Special }
    }
}

# --- Step 4: remove orphan profiles ---
Log ''
Log '=== Removing orphan profiles ===' 'Cyan'
if (-not $orphans) {
    Log '  (nothing to remove)'
} else {
    foreach ($o in $orphans) {
        if ($Apply) {
            try {
                Remove-CimInstance -InputObject $o.Cim -ErrorAction Stop
                Log ("  REMOVED: {0}" -f $o.LocalPath) 'Yellow'
            } catch {
                Log ("  FAILED: {0} - {1}" -f $o.LocalPath, $_) 'Red'
            }
        } else {
            Log ("  [dry-run] would remove: {0}" -f $o.LocalPath) 'DarkCyan'
        }
    }
}

# --- Step 5: report any leftover folders on disk ---
Log ''
Log '=== Leftover directories on disk ===' 'Cyan'
$leftover = Get-ChildItem 'C:\Users' -Directory -Filter 'Cognito Forms-*' -ErrorAction SilentlyContinue
foreach ($d in $leftover) {
    $matched = $profiles | Where-Object { $_.LocalPath -eq $d.FullName }
    $tag = if ($matched) { '[profile still registered]' } else { '[orphan dir]             ' }
    Log ("  {0} {1}" -f $tag, $d.FullName)
}

Log ''
Log 'Done.' 'Green'
$log.ToString() | Out-File -LiteralPath $ReportPath -Encoding UTF8
Write-Host "Report written to $ReportPath" -ForegroundColor Green

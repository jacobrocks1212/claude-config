# Set-Pagefile.ps1
# Sets the C: pagefile to a fixed size (initial = max).
# Must be run from an elevated PowerShell. Reboot afterward for the file to physically shrink.
#
# Usage:
#   .\Set-Pagefile.ps1                  # defaults to 16 GB
#   .\Set-Pagefile.ps1 -SizeMB 8192     # 8 GB
#   .\Set-Pagefile.ps1 -SizeMB 16384    # 16 GB
#
# Decision guide: check commit charge first. If peak commit << RAM, shrinking is safe.
# Get-CimInstance Win32_OperatingSystem and Win32_PageFileUsage give you the numbers.
# Never set to 0 - that breaks crash dumps and confuses the memory manager.

#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [int]$SizeMB = 16384
)

if ($SizeMB -lt 1024) {
    Write-Error "Refusing to set pagefile below 1024 MB. Specify -SizeMB explicitly to override this guard."
    return
}

Write-Host 'Current pagefile configuration:' -ForegroundColor Cyan
Get-WmiObject Win32_PageFileSetting | Format-Table Name, InitialSize, MaximumSize
Get-WmiObject Win32_ComputerSystem | Format-List AutomaticManagedPagefile

Write-Host 'Disabling automatic pagefile management...' -ForegroundColor Cyan
$cs = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges
if ($cs.AutomaticManagedPagefile) {
    $cs.AutomaticManagedPagefile = $false
    [void]$cs.Put()
    Write-Host '  Automatic management disabled.' -ForegroundColor Green
} else {
    Write-Host '  Already disabled.' -ForegroundColor DarkGray
}

Write-Host ("Setting C: pagefile to fixed {0} MB..." -f $SizeMB) -ForegroundColor Cyan
$pf = Get-WmiObject Win32_PageFileSetting | Where-Object { $_.Name -like 'C:*' }
if (-not $pf) {
    Set-WmiInstance -Class Win32_PageFileSetting -Arguments @{
        Name        = 'C:\pagefile.sys'
        InitialSize = $SizeMB
        MaximumSize = $SizeMB
    } | Out-Null
    Write-Host '  Created new pagefile setting.' -ForegroundColor Green
} else {
    $pf.InitialSize = $SizeMB
    $pf.MaximumSize = $SizeMB
    [void]$pf.Put()
    Write-Host '  Updated existing pagefile setting.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'New pagefile configuration:' -ForegroundColor Cyan
Get-WmiObject Win32_PageFileSetting | Format-Table Name, InitialSize, MaximumSize

Write-Host ''
Write-Host 'Done. REBOOT required for pagefile.sys to physically shrink on disk.' -ForegroundColor Yellow

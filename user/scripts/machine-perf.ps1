<#
.SYNOPSIS
  Snapshot of this Windows machine's performance and uptime.

.DESCRIPTION
  Read-only diagnostics. Collects uptime, CPU, memory, disk, network, and the
  top resource-consuming processes, then prints a human-readable report.
  Pass -Json to emit a single JSON object instead (for programmatic relay).

  No state is mutated; safe to run anytime.
#>
[CmdletBinding()]
param(
    [switch]$Json,
    [int]$TopN = 5,
    # Seconds to sample CPU load over. 0 = instantaneous WMI LoadPercentage only.
    [int]$SampleSeconds = 2
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-SafeValue {
    param([scriptblock]$Block, $Fallback = $null)
    try { & $Block } catch { $Fallback }
}

# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------
$report = [ordered]@{}

# --- Identity ---------------------------------------------------------------
$os  = Get-SafeValue { Get-CimInstance Win32_OperatingSystem }
$cs  = Get-SafeValue { Get-CimInstance Win32_ComputerSystem }
$cpu = Get-SafeValue { Get-CimInstance Win32_Processor | Select-Object -First 1 }

$report.host = [ordered]@{
    name          = $env:COMPUTERNAME
    os            = if ($os) { $os.Caption } else { 'unknown' }
    version       = if ($os) { $os.Version } else { 'unknown' }
    architecture  = if ($os) { $os.OSArchitecture } else { 'unknown' }
    manufacturer  = if ($cs) { $cs.Manufacturer } else { 'unknown' }
    model         = if ($cs) { $cs.Model } else { 'unknown' }
}

# --- Uptime -----------------------------------------------------------------
$uptime = $null
if ($os -and $os.LastBootUpTime) {
    $boot = $os.LastBootUpTime
    $span = (Get-Date) - $boot
    $uptime = [ordered]@{
        last_boot       = $boot.ToString('yyyy-MM-dd HH:mm:ss')
        uptime_days     = [math]::Floor($span.TotalDays)
        uptime_readable = ('{0}d {1}h {2}m' -f [math]::Floor($span.TotalDays), $span.Hours, $span.Minutes)
        total_hours     = [math]::Round($span.TotalHours, 1)
    }
}
$report.uptime = $uptime

# --- CPU --------------------------------------------------------------------
# WMI LoadPercentage is an instantaneous snapshot; if a sample window is
# requested, average two reads over the window for a more stable number.
$cpuLoad = Get-SafeValue {
    if ($SampleSeconds -gt 0) {
        $a = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
        Start-Sleep -Seconds $SampleSeconds
        $b = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
        [math]::Round((($a + $b) / 2), 1)
    } else {
        [math]::Round((Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average, 1)
    }
}

$report.cpu = [ordered]@{
    name             = if ($cpu) { ($cpu.Name).Trim() } else { 'unknown' }
    physical_cores   = if ($cpu) { $cpu.NumberOfCores } else { $null }
    logical_cores    = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $null }
    load_percent     = $cpuLoad
    max_clock_mhz    = if ($cpu) { $cpu.MaxClockSpeed } else { $null }
}

# --- Memory -----------------------------------------------------------------
if ($os) {
    $totalKb = [double]$os.TotalVisibleMemorySize
    $freeKb  = [double]$os.FreePhysicalMemory
    $usedKb  = $totalKb - $freeKb
    $report.memory = [ordered]@{
        total_gb     = [math]::Round($totalKb / 1MB, 2)
        used_gb      = [math]::Round($usedKb / 1MB, 2)
        free_gb      = [math]::Round($freeKb / 1MB, 2)
        used_percent = if ($totalKb -gt 0) { [math]::Round(($usedKb / $totalKb) * 100, 1) } else { $null }
    }
} else {
    $report.memory = $null
}

# --- Disks ------------------------------------------------------------------
$report.disks = Get-SafeValue {
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        $total = [double]$_.Size
        $free  = [double]$_.FreeSpace
        [ordered]@{
            drive        = $_.DeviceID
            total_gb     = [math]::Round($total / 1GB, 1)
            free_gb      = [math]::Round($free / 1GB, 1)
            used_percent = if ($total -gt 0) { [math]::Round((($total - $free) / $total) * 100, 1) } else { $null }
        }
    }
} @()

# --- Top processes ----------------------------------------------------------
# Snapshot once, then immediately project each process to plain numbers with a
# per-process guard. A process can exit between the snapshot and a later sort,
# at which point its CPU/WorkingSet getters throw; reading them once here (and
# swallowing per-process failures) keeps one dead process from killing the list.
$procSnap = @(
    foreach ($p in (Get-SafeValue { Get-Process -ErrorAction SilentlyContinue } @())) {
        try {
            [pscustomobject]@{
                name      = $p.ProcessName
                cpu_sec   = if ($null -ne $p.CPU) { [math]::Round($p.CPU, 1) } else { $null }
                memory_mb = [math]::Round($p.WorkingSet64 / 1MB, 1)
            }
        } catch { }
    }
)

$report.top_cpu = @(
    $procSnap |
        Where-Object { $null -ne $_.cpu_sec } |
        Sort-Object cpu_sec -Descending |
        Select-Object -First $TopN |
        ForEach-Object { [ordered]@{ name = $_.name; cpu_sec = $_.cpu_sec; memory_mb = $_.memory_mb } }
)

$report.top_memory = @(
    $procSnap |
        Sort-Object memory_mb -Descending |
        Select-Object -First $TopN |
        ForEach-Object { [ordered]@{ name = $_.name; memory_mb = $_.memory_mb } }
)

# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------
if ($Json) {
    $report | ConvertTo-Json -Depth 6
    return
}

function Write-Section($title) { Write-Output ''; Write-Output "== $title ==" }

Write-Output "MACHINE PERFORMANCE REPORT  ($($report.host.name))"
Write-Output ("Captured: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))

Write-Section 'Host'
Write-Output ("  OS:    {0} (v{1}, {2})" -f $report.host.os, $report.host.version, $report.host.architecture)
Write-Output ("  Model: {0} {1}" -f $report.host.manufacturer, $report.host.model)

Write-Section 'Uptime'
if ($uptime) {
    Write-Output ("  Up for:    {0}  ({1} hours)" -f $uptime.uptime_readable, $uptime.total_hours)
    Write-Output ("  Last boot: {0}" -f $uptime.last_boot)
} else {
    Write-Output '  (unavailable)'
}

Write-Section 'CPU'
Write-Output ("  {0}" -f $report.cpu.name)
Write-Output ("  Cores: {0} physical / {1} logical   Max clock: {2} MHz" -f $report.cpu.physical_cores, $report.cpu.logical_cores, $report.cpu.max_clock_mhz)
Write-Output ("  Load:  {0}%" -f $report.cpu.load_percent)

Write-Section 'Memory'
if ($report.memory) {
    Write-Output ("  {0} GB used / {1} GB total  ({2}% used, {3} GB free)" -f `
        $report.memory.used_gb, $report.memory.total_gb, $report.memory.used_percent, $report.memory.free_gb)
} else {
    Write-Output '  (unavailable)'
}

Write-Section 'Disks'
foreach ($d in $report.disks) {
    Write-Output ("  {0}  {1} GB free / {2} GB total  ({3}% used)" -f $d.drive, $d.free_gb, $d.total_gb, $d.used_percent)
}

Write-Section "Top $TopN processes by CPU time"
foreach ($p in $report.top_cpu) {
    Write-Output ("  {0,-28} {1,8} CPU-sec  {2,8} MB" -f $p.name, $p.cpu_sec, $p.memory_mb)
}

Write-Section "Top $TopN processes by memory"
foreach ($p in $report.top_memory) {
    Write-Output ("  {0,-28} {1,8} MB" -f $p.name, $p.memory_mb)
}

Write-Output ''

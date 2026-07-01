<#
.SYNOPSIS
  Read-only status view of the machine-global Cognito build queue.

.DESCRIPTION
  Reads state written by build-queue.ps1 from $StateRoot and prints:
    - The active build (op, worktree, PID, elapsed, log path, start-time perf snapshot).
    - Ordered waiter list (position, seq, op, worktree, wait duration).
    - A fresh one-line machine-load summary from machine-perf.ps1.
  If the queue is idle, prints "queue idle" followed by the live load line.
  Mutates nothing; safe to run anytime.
#>
[CmdletBinding()]
param(
	[string]$StateRoot = (Join-Path $HOME '.claude\state\build-queue')
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

function Get-SafeValue {
	param([scriptblock]$Block, $Fallback = $null)
	try { & $Block } catch { $Fallback }
}

function Format-Elapsed {
	param([string]$IsoTimestamp)
	$start = Get-SafeValue { [datetime]::Parse($IsoTimestamp, $null, [System.Globalization.DateTimeStyles]::RoundtripKind) }
	if ($null -eq $start) { return '?' }
	$span = (Get-Date) - $start
	if ($span.TotalHours -ge 1) {
		return ('{0}h {1}m {2}s' -f [math]::Floor($span.TotalHours), $span.Minutes, $span.Seconds)
	}
	if ($span.TotalMinutes -ge 1) {
		return ('{0}m {1}s' -f [math]::Floor($span.TotalMinutes), $span.Seconds)
	}
	return ('{0}s' -f [math]::Floor($span.TotalSeconds))
}

function Get-LiveLoadLine {
	$perfScript = Join-Path $HOME '.claude\scripts\machine-perf.ps1'
	$perfJson = Get-SafeValue {
		if (Test-Path $perfScript) {
			& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $perfScript -Json -SampleSeconds 0 2>$null
		}
	}
	if ($null -eq $perfJson -or $perfJson -eq '') { return 'Load: (unavailable)' }
	$perf = Get-SafeValue { $perfJson | ConvertFrom-Json }
	if ($null -eq $perf) { return 'Load: (unavailable)' }
	$cpu = Get-SafeValue { $perf.cpu.load_percent }
	$usedGb = Get-SafeValue { $perf.memory.used_gb }
	$totalGb = Get-SafeValue { $perf.memory.total_gb }
	$usedPct = Get-SafeValue { $perf.memory.used_percent }
	$freeGb = Get-SafeValue { $perf.memory.free_gb }
	$cpuStr = if ($null -ne $cpu) { "$cpu%" } else { '?' }
	$memStr = if ($null -ne $usedGb -and $null -ne $totalGb) { "$usedGb/$totalGb GB used ($usedPct%), $freeGb GB free" } else { '?' }
	return "Load: CPU $cpuStr | Mem $memStr"
}

function Get-PerfSnapshotLine {
	param($MachinePerfRaw)
	if ($null -eq $MachinePerfRaw) { return $null }
	$perfObj = $null
	if ($MachinePerfRaw -is [string]) {
		$perfObj = Get-SafeValue { $MachinePerfRaw | ConvertFrom-Json }
	} else {
		$perfObj = $MachinePerfRaw
	}
	if ($null -eq $perfObj) { return $null }
	$cpu = Get-SafeValue { $perfObj.cpu.load_percent }
	$usedGb = Get-SafeValue { $perfObj.memory.used_gb }
	$totalGb = Get-SafeValue { $perfObj.memory.total_gb }
	$usedPct = Get-SafeValue { $perfObj.memory.used_percent }
	$freeGb = Get-SafeValue { $perfObj.memory.free_gb }
	$cpuStr = if ($null -ne $cpu) { "$cpu%" } else { '?' }
	$memStr = if ($null -ne $usedGb -and $null -ne $totalGb) { "$usedGb/$totalGb GB used ($usedPct%), $freeGb GB free" } else { '?' }
	return "At build start - CPU $cpuStr | Mem $memStr"
}

$activeLock = Join-Path $StateRoot 'active.lock'
$ticketsDir = Join-Path $StateRoot 'tickets'

$hasActive = $false
$hasWaiters = $false

if (Test-Path $activeLock) {
	$lockData = Get-SafeValue {
		$raw = [System.IO.File]::ReadAllText($activeLock)
		$raw | ConvertFrom-Json
	}
	if ($null -ne $lockData) {
		$hasActive = $true
		$elapsed = Format-Elapsed $lockData.started_at
		Write-Output '=== Active Build ==='
		Write-Output ("  op:      {0}" -f $lockData.op)
		Write-Output ("  worktree:{0}" -f $lockData.worktree)
		Write-Output ("  pid:     {0}" -f $lockData.build_pid)
		Write-Output ("  elapsed: {0}" -f $elapsed)
		Write-Output ("  log:     {0}" -f $lockData.log_path)
		$snapLine = Get-SafeValue { Get-PerfSnapshotLine $lockData.machine_perf }
		if ($null -ne $snapLine -and $snapLine -ne '') {
			Write-Output ("  perf:    {0}" -f $snapLine)
		}
	}
}

$tickets = @()
if (Test-Path $ticketsDir) {
	$ticketFiles = @(Get-ChildItem -Path $ticketsDir -Filter '*.json' -ErrorAction SilentlyContinue)
	foreach ($tf in $ticketFiles) {
		$td = Get-SafeValue {
			$raw = [System.IO.File]::ReadAllText($tf.FullName)
			$raw | ConvertFrom-Json
		}
		if ($null -ne $td) {
			$tickets += $td
		}
	}
	$tickets = @($tickets | Sort-Object { [int]$_.seq })
}

if (@($tickets).Count -gt 0) {
	$hasWaiters = $true
	Write-Output ''
	Write-Output '=== Waiters ==='
	$pos = 1
	foreach ($t in $tickets) {
		$waited = Format-Elapsed $t.started_wait_at
		Write-Output ("  [{0}] seq={1} op={2} worktree={3} waiting={4}" -f $pos, $t.seq, $t.op, $t.worktree, $waited)
		$pos++
	}
}

if (-not $hasActive -and -not $hasWaiters) {
	Write-Output 'queue idle'
}

$hygieneSeq = $null
if ($hasActive -and $null -ne $lockData) {
	$hygieneSeq = Get-SafeValue { $lockData.seq }
}
if ($null -eq $hygieneSeq) {
	$resultsDir = Join-Path $StateRoot 'results'
	if (Test-Path $resultsDir) {
		$resultFiles = @(Get-ChildItem -Path $resultsDir -Filter '*.json' -ErrorAction SilentlyContinue)
		$bestSeq = $null
		foreach ($rf in $resultFiles) {
			$seqVal = Get-SafeValue { [int]([System.IO.Path]::GetFileNameWithoutExtension($rf.Name)) }
			if ($null -ne $seqVal -and ($null -eq $bestSeq -or $seqVal -gt $bestSeq)) {
				$bestSeq = $seqVal
			}
		}
		$hygieneSeq = $bestSeq
	}
}

if ($null -ne $hygieneSeq) {
	$resultPath = Join-Path $StateRoot ("results\{0}.json" -f $hygieneSeq)
	$resultData = Get-SafeValue {
		if (Test-Path $resultPath) {
			$raw = [System.IO.File]::ReadAllText($resultPath)
			$raw | ConvertFrom-Json
		}
	}
	$hygiene = Get-SafeValue { $resultData.hygiene }
	if ($null -eq $hygiene) {
		Write-Output 'hygiene: (not recorded)'
	} else {
		$recycled = Get-SafeValue { $hygiene.vbcscompiler_recycled }
		$quarantinedCount = @(Get-SafeValue { $hygiene.quarantined_artifacts } $null).Count
		$fidelity = Get-SafeValue { $hygiene.result_fidelity }
		$fidelityStr = if ($null -ne $fidelity -and $fidelity -ne '') { $fidelity } else { 'n/a' }
		$buildFidelity = Get-SafeValue { $hygiene.build_fidelity }
		$buildFidelityStr = if ($null -ne $buildFidelity -and $buildFidelity -ne '') { $buildFidelity } else { 'n/a' }
		$lockersReapedRaw = Get-SafeValue { $hygiene.lockers_reaped } $null
		$lockersReaped = @(if ($null -ne $lockersReapedRaw) { $lockersReapedRaw })
		$lockersReapedCount = $lockersReaped.Count
		$lockersReapedStr = if ($lockersReapedCount -gt 0) { "{0} ({1})" -f $lockersReapedCount, ($lockersReaped -join ',') } else { '0' }
		$line = "hygiene (seq {0}): recycled={1} | quarantined={2} | fidelity={3} | build_fidelity={4} | lockers_reaped={5}" -f $hygieneSeq, $recycled, $quarantinedCount, $fidelityStr, $buildFidelityStr, $lockersReapedStr
		if ($buildFidelityStr -eq 'log-failure-override') {
			Write-Host ($line + '  [BUILD LIED - copy-lock override fired]') -ForegroundColor Red
		} elseif ($fidelityStr -eq 'no-output') {
			Write-Host ($line + '  [UNVERIFIED - no test output captured]') -ForegroundColor Yellow
		} else {
			Write-Output $line
		}
	}
}

Write-Output ''
Write-Output (Get-LiveLoadLine)

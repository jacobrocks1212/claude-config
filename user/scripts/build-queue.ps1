<#
.SYNOPSIS
  Machine-global FIFO serializer for expensive Cognito Forms builds across git worktrees.

.DESCRIPTION
  Ensures only ONE build runs at a time across all worktrees on this machine.
  Clients are served in strict arrival (FIFO) order via a monotonic sequence counter.
  State lives under $HOME/.claude/state/build-queue/ (machine-global by construction).

  Usage:
	build-queue.ps1 -Op msbuild -Exec <path-to-filtered-script> [<pass-through-args>...]

  -Op     One of: msbuild, mstest, nxbuild, nxtest
  -Exec   Absolute path to the underlying filtered script (e.g. build-filtered.ps1)
		  That script is invoked UNCHANGED inside a detached PowerShell process.
  Remaining arguments are forwarded verbatim to the filtered script.

  Queue state layout ($HOME/.claude/state/build-queue/):
	seq.counter           - monotonic sequence allocator (integer text)
	seq.counter.lock      - transient exclusive-open lock guarding seq allocation
	tickets/<seq>.json    - one per waiter: {seq, pid, worktree, op, started_wait_at}
	active.lock           - current holder: {seq, build_pid, op, worktree, started_at, log_path, machine_perf}
	logs/<seq>.log        - build stdout/stderr
	results/<seq>.json    - {seq, exit_code, ended_at} written on completion
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory=$true)]
	[ValidateSet('msbuild','mstest','nxbuild','nxtest')]
	[string]$Op,

	[Parameter(Mandatory=$true)]
	[string]$Exec,

	[Parameter(ValueFromRemainingArguments=$true)]
	$ExecArgs
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-SafeValue {
	param([scriptblock]$Block, $Fallback = $null)
	try { & $Block } catch { $Fallback }
}

Get-SafeValue {
	. (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1')
}

function Test-PidAlive {
	param([int]$ProcId)
	if ($ProcId -le 0) { return $false }
	try {
		$null = [System.Diagnostics.Process]::GetProcessById($ProcId)
		return $true
	} catch [System.ArgumentException] {
		return $false
	} catch {
		return $true
	}
}

$stateRoot  = Join-Path $HOME '.claude\state\build-queue'
$ticketsDir = Join-Path $stateRoot 'tickets'
$logsDir    = Join-Path $stateRoot 'logs'
$resultsDir = Join-Path $stateRoot 'results'
$counterFile = Join-Path $stateRoot 'seq.counter'
$counterLock = Join-Path $stateRoot 'seq.counter.lock'
$activeLock  = Join-Path $stateRoot 'active.lock'

foreach ($dir in @($stateRoot, $ticketsDir, $logsDir, $resultsDir)) {
	if (-not (Test-Path $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
}

$worktree = Get-SafeValue {
	$wt = git rev-parse --show-toplevel 2>$null
	if ($LASTEXITCODE -eq 0 -and $wt) { $wt.Trim() } else { $PWD.Path }
} $PWD.Path

# ---------------------------------------------------------------------------
# Step 1: Allocate seq - bounded retry around exclusive-open lock
# ---------------------------------------------------------------------------
$seq = $null
$lockRetries = 200
$lockStream  = $null

for ($i = 0; $i -lt $lockRetries; $i++) {
	try {
		$lockStream = [System.IO.File]::Open(
			$counterLock,
			[System.IO.FileMode]::CreateNew,
			[System.IO.FileAccess]::ReadWrite,
			[System.IO.FileShare]::None
		)
		break
	} catch {
		Start-Sleep -Milliseconds 20
	}
}

if ($null -eq $lockStream) {
	Write-Error "build-queue: could not acquire seq.counter.lock after $lockRetries retries"
	exit 1
}

try {
	$currentSeq = 0
	if (Test-Path $counterFile) {
		$raw = Get-SafeValue { [System.IO.File]::ReadAllText($counterFile).Trim() }
		if ($raw -match '^\d+$') { $currentSeq = [int]$raw }
	}
	$seq = $currentSeq + 1
	[System.IO.File]::WriteAllText($counterFile, "$seq")
} finally {
	$lockStream.Dispose()
	Get-SafeValue { Remove-Item $counterLock -Force -ErrorAction SilentlyContinue }
}

# ---------------------------------------------------------------------------
# Step 2: Enqueue - write ticket
# ---------------------------------------------------------------------------
$ticketPath = Join-Path $ticketsDir "$seq.json"
$ticketBody = [ordered]@{
	seq            = $seq
	pid            = $PID
	worktree       = $worktree
	op             = $Op
	started_wait_at = (Get-Date).ToString('o')
} | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($ticketPath, $ticketBody)

Write-Output "build-queue: enqueued as seq=$seq (op=$Op)"

# ---------------------------------------------------------------------------
# Step 3: Poll loop - reclaim stale, check head, heartbeat
# ---------------------------------------------------------------------------
$lastEmittedPosition = -1

function Get-LiveTicketSeqs {
	$seqs = @()
	$files = Get-SafeValue { Get-ChildItem -Path $ticketsDir -Filter '*.json' -ErrorAction SilentlyContinue } @()
	foreach ($f in $files) {
		$data = Get-SafeValue {
			$txt = [System.IO.File]::ReadAllText($f.FullName)
			$txt | ConvertFrom-Json
		}
		if ($null -eq $data) { continue }
		$ticketSeq = Get-SafeValue { [int]$data.seq } $null
		$ticketPid = Get-SafeValue { [int]$data.pid } $null
		if ($null -eq $ticketSeq -or $null -eq $ticketPid) { continue }
		$alive = Test-PidAlive $ticketPid
		if (-not $alive) {
			Get-SafeValue { Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue }
			continue
		}
		$seqs += $ticketSeq
	}
	return $seqs
}

function Get-ActiveLockStatus {
	if (-not (Test-Path $activeLock)) { return 'absent' }
	$data = Get-SafeValue {
		$txt = [System.IO.File]::ReadAllText($activeLock)
		$txt | ConvertFrom-Json
	}
	if ($null -eq $data) { return 'unknown' }
	$buildPid = Get-SafeValue {
		$v = $data | Select-Object -ExpandProperty build_pid -ErrorAction SilentlyContinue
		if ($null -ne $v) { [int]$v } else { $null }
	} $null
	if ($null -eq $buildPid) { return 'unknown' }
	if (Test-PidAlive $buildPid) { return 'alive' }
	return 'dead'
}

$logPath = Join-Path $logsDir "$seq.log"
$errPath = Join-Path $logsDir "$seq.err.log"

$won = $false
$staleTicks = 0
$staleThreshold = 3
while (-not $won) {
	$liveSeqs    = @(Get-LiveTicketSeqs)
	$lowestSeq   = if ($liveSeqs.Count -gt 0) { (@($liveSeqs | Sort-Object))[0] } else { $seq }
	$status      = Get-ActiveLockStatus

	if ($status -eq 'alive' -or $status -eq 'absent') {
		$staleTicks = 0
	} else {
		$staleTicks++
		if ($staleTicks -ge $staleThreshold -and $lowestSeq -eq $seq) {
			Get-SafeValue { Remove-Item $activeLock -Force -ErrorAction SilentlyContinue }
			$status = 'absent'
			$staleTicks = 0
		}
	}

	if ($status -eq 'absent' -and $lowestSeq -eq $seq) {
		$lockFileStream = $null
		try {
			$lockFileStream = [System.IO.File]::Open(
				$activeLock,
				[System.IO.FileMode]::CreateNew,
				[System.IO.FileAccess]::ReadWrite,
				[System.IO.FileShare]::None
			)
			$won = $true
			$provisionalBody = [ordered]@{
				seq          = $seq
				build_pid    = $PID
				op           = $Op
				worktree     = $worktree
				started_at   = (Get-Date).ToString('o')
				log_path     = $logPath
				machine_perf = $null
			} | ConvertTo-Json -Compress
			$provisionalBytes = [System.Text.Encoding]::UTF8.GetBytes($provisionalBody)
			$lockFileStream.Write($provisionalBytes, 0, $provisionalBytes.Length)
			$lockFileStream.Flush()
			$lockFileStream.Dispose()
			$lockFileStream = $null
			Get-SafeValue { Remove-Item $ticketPath -Force -ErrorAction SilentlyContinue }
		} catch {
			if ($null -ne $lockFileStream) {
				try { $lockFileStream.Dispose() } catch {}
				$lockFileStream = $null
			}
		}
	}

	if (-not $won) {
		$liveSeqsSorted = @($liveSeqs | Sort-Object)
		$myIndex        = [Array]::IndexOf($liveSeqsSorted, $seq)
		$aheadCount = if ($status -eq 'alive') { $myIndex + 1 } else { $myIndex }
		$position   = $aheadCount + 1

		if ($position -ne $lastEmittedPosition) {
			$lastEmittedPosition = $position
			if ($aheadCount -eq 0) {
				Write-Output "build-queue: waiting to claim slot..."
			} else {
				Write-Output "build-queue: queued at position $position ($aheadCount build(s) ahead). Waiting..."
			}
		}

		Start-Sleep -Milliseconds 1000
	}
}

# ---------------------------------------------------------------------------
# Step 4: Run detached build
# ---------------------------------------------------------------------------
$machinePerf = Get-SafeValue {
	$perfScript = Join-Path $HOME '.claude\scripts\machine-perf.ps1'
	if (-not (Test-Path $perfScript)) { return $null }
	$raw = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $perfScript -Json -SampleSeconds 0 2>$null) -join "`n"
	if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
	$parsed = $raw | ConvertFrom-Json
	if ($null -eq $parsed -or $null -eq $parsed.cpu) { return $null }
	[ordered]@{
		cpu    = [ordered]@{ load_percent = $parsed.cpu.load_percent }
		memory = [ordered]@{
			used_gb      = $parsed.memory.used_gb
			total_gb     = $parsed.memory.total_gb
			used_percent = $parsed.memory.used_percent
			free_gb      = $parsed.memory.free_gb
		}
	}
} $null

$execArgsArr = @($ExecArgs | Where-Object { $_ -ne $null })

function Format-ProcArg {
	param([string]$Value)
	if ($Value -eq '' -or $Value -match '[\s"]') {
		return '"' + ($Value -replace '"', '\"') + '"'
	}
	return $Value
}

$runnerScript = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
$procArgList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Format-ProcArg $runnerScript),
	'-Exec', (Format-ProcArg $Exec),
	'-Seq', "$seq",
	'-StateRoot', (Format-ProcArg $stateRoot))
foreach ($a in $execArgsArr) { $procArgList += (Format-ProcArg ([string]$a)) }
$procArgString = $procArgList -join ' '

$proc     = Start-Process -FilePath 'powershell.exe' `
	-ArgumentList $procArgString `
	-RedirectStandardOutput $logPath `
	-RedirectStandardError  $errPath `
	-WindowStyle Hidden `
	-PassThru
$buildPid = $proc.Id
$null = $proc.Handle

$activeLockBody = [ordered]@{
	seq          = $seq
	build_pid    = $buildPid
	op           = $Op
	worktree     = $worktree
	started_at   = (Get-Date).ToString('o')
	log_path     = $logPath
	machine_perf = $machinePerf
} | ConvertTo-Json -Compress -Depth 5
$activeLockTmp = Join-Path $stateRoot "active.$seq.tmp"
[System.IO.File]::WriteAllText($activeLockTmp, $activeLockBody)
try {
	[System.IO.File]::Replace($activeLockTmp, $activeLock, [NullString]::Value)
} catch {
	Get-SafeValue { [System.IO.File]::WriteAllText($activeLock, $activeLockBody) }
	Get-SafeValue { Remove-Item $activeLockTmp -Force -ErrorAction SilentlyContinue }
}

Write-Output "build-queue: build started (pid=$buildPid, seq=$seq, log=$logPath)"

# ---------------------------------------------------------------------------
# Tail log file to wrapper stdout while the detached build runs
# ---------------------------------------------------------------------------
$logFilePos = 0L

while (-not $proc.HasExited) {
	if (Test-Path $logPath) {
		try {
			$fs = [System.IO.File]::Open($logPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
			try {
				$null = $fs.Seek($logFilePos, [System.IO.SeekOrigin]::Begin)
				$buf = New-Object byte[] 4096
				$read = $fs.Read($buf, 0, $buf.Length)
				while ($read -gt 0) {
					$chunk = [System.Text.Encoding]::UTF8.GetString($buf, 0, $read)
					Write-Host $chunk -NoNewline
					$logFilePos += $read
					$read = $fs.Read($buf, 0, $buf.Length)
				}
			} finally {
				$fs.Dispose()
			}
		} catch {}
	}
	Start-Sleep -Milliseconds 500
}

foreach ($tailFile in @($logPath, $errPath)) {
	if (Test-Path $tailFile) {
		try {
			$fs = [System.IO.File]::Open($tailFile, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
			try {
				$seekPos = if ($tailFile -eq $logPath) { $logFilePos } else { 0L }
				$null = $fs.Seek($seekPos, [System.IO.SeekOrigin]::Begin)
				$buf = New-Object byte[] 4096
				$read = $fs.Read($buf, 0, $buf.Length)
				while ($read -gt 0) {
					$chunk = [System.Text.Encoding]::UTF8.GetString($buf, 0, $read)
					Write-Host $chunk -NoNewline
					$read = $fs.Read($buf, 0, $buf.Length)
				}
			} finally {
				$fs.Dispose()
			}
		} catch {}
	}
}

$exitCode = $proc.ExitCode

# ---------------------------------------------------------------------------
# Step 5: Release - write results, delete active.lock
# ---------------------------------------------------------------------------
$resultBody = [ordered]@{
	seq       = $seq
	exit_code = $exitCode
	ended_at  = (Get-Date).ToString('o')
} | ConvertTo-Json -Compress
$resultPath = Join-Path $resultsDir "$seq.json"
$resultTmp  = Join-Path $resultsDir "$seq.tmp"
Get-SafeValue { [System.IO.File]::WriteAllText($resultTmp, $resultBody) }
try {
	[System.IO.File]::Replace($resultTmp, $resultPath, [NullString]::Value)
} catch {
	Get-SafeValue { [System.IO.File]::WriteAllText($resultPath, $resultBody) }
	Get-SafeValue { Remove-Item $resultTmp -Force -ErrorAction SilentlyContinue }
}

Get-SafeValue {
	if (Test-Path $activeLock) {
		$d       = [System.IO.File]::ReadAllText($activeLock) | ConvertFrom-Json
		$lockSeq = Get-SafeValue { [int]$d.seq } $null
		if ($lockSeq -eq $seq) {
			Remove-Item $activeLock -Force
		}
	}
}

Get-SafeValue { Reset-CompilerServer }

Write-Output "build-queue: build complete (seq=$seq, exit_code=$exitCode)"

exit $exitCode


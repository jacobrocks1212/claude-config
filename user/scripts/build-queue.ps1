<#
.SYNOPSIS
  Machine-global FIFO serializer for expensive Cognito Forms builds across git worktrees.

.DESCRIPTION
  Ensures only ONE build runs at a time across all worktrees on this machine.
  Clients are served in strict arrival (FIFO) order via a monotonic sequence counter.
  State lives under $HOME/.claude/state/build-queue/ (machine-global by construction).

  Usage:
	build-queue.ps1 -Op msbuild [-Exec <path-to-filtered-script>] [<pass-through-args>...]

  -Op     An op registered in the current repo's ops manifest
		  (.claude/skill-config/build-queue-ops.json — feature
		  build-queue-generalization). With no manifest, the legacy four
		  (msbuild, mstest, nxbuild, nxtest) are accepted for back-compat
		  and -Exec is required.
  -Exec   Path to the underlying filtered script (e.g. build-filtered.ps1).
		  Optional when the manifest registers the op (resolved from the
		  entry's repo-root-relative 'exec'); an explicit -Exec overrides.
		  That script is invoked UNCHANGED inside a detached PowerShell process.
  Remaining arguments are forwarded verbatim to the filtered script.

  The manifest entry's kind/hygiene are threaded to the runner as
  -OpKind/-Hygiene so hygiene dispatches on a profile record
  (Get-HygieneProfile), never on repo identity or exec filename.

  Queue state layout ($HOME/.claude/state/build-queue/):
	seq.counter           - monotonic sequence allocator (integer text)
	seq.counter.lock      - transient exclusive-open lock guarding seq allocation
	tickets/<seq>.json    - one per waiter: {seq, pid, worktree, op, lane, started_wait_at}
	active.lock           - current holder: {seq, build_pid, op, worktree, started_at, log_path, machine_perf}
	logs/<seq>.log        - build stdout/stderr
	results/<seq>.json    - {seq, exit_code, ended_at, +op/started_at/duration_seconds} written on completion
	stats/<op>.json       - rolling per-op duration ring (20 entries; ETA input; advisory)
	fast-passes.count     - consecutive fast-lane claims counter (lane starvation bound K=3; advisory)
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory=$true)]
	[string]$Op,

	[string]$Exec = '',

	[Parameter(ValueFromRemainingArguments=$true)]
	$ExecArgs
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-SafeValue {
	param([scriptblock]$Block, $Fallback = $null)
	try { & $Block } catch { $Fallback }
}

try {
	. (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1')
} catch { }

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

$worktree = Get-SafeValue {
	$wt = git rev-parse --show-toplevel 2>$null
	if ($LASTEXITCODE -eq 0 -and $wt) { $wt.Trim() } else { $PWD.Path }
} $PWD.Path

# ---------------------------------------------------------------------------
# Step 0: Resolve -Op against the repo's ops manifest (build-queue-generalization)
# BEFORE any state write, so an unknown op / missing exec exits side-effect-free.
# ---------------------------------------------------------------------------
$opKind = ''
$opHygiene = ''
$opLane = 'heavy'
if (Get-Command Resolve-BuildQueueOp -ErrorAction SilentlyContinue) {
	$opResolution = Resolve-BuildQueueOp -RepoRoot $worktree -Op $Op -Exec $Exec
	if (-not $opResolution.ok) {
		Write-Error $opResolution.error
		exit 1
	}
	$Exec      = [string]$opResolution.exec
	$opKind    = [string]$opResolution.kind
	$opHygiene = [string]$opResolution.hygiene
	$opLane    = Get-SafeValue { if (@('fast','heavy') -contains [string]$opResolution.lane) { [string]$opResolution.lane } else { 'heavy' } } 'heavy'
} else {
	# Hygiene module absent: legacy inline fallback (pre-manifest behavior —
	# the four legacy ops with an explicit -Exec).
	if (@('msbuild','mstest','nxbuild','nxtest') -notcontains $Op) {
		Write-Error "build-queue: unknown op '$Op' (hygiene module unavailable; legacy ops: msbuild, mstest, nxbuild, nxtest)"
		exit 1
	}
	if ([string]::IsNullOrWhiteSpace($Exec)) {
		Write-Error "build-queue: -Exec is required for op '$Op' (hygiene module unavailable; manifest resolution not possible)"
		exit 1
	}
}

foreach ($dir in @($stateRoot, $ticketsDir, $logsDir, $resultsDir)) {
	if (-not (Test-Path $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
}

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
	lane           = $opLane
	started_wait_at = (Get-Date).ToString('o')
} | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText($ticketPath, $ticketBody)

# eta-priority-lanes D3: predictions ride the PRE-outcome surfaces only (this
# echo + the position lines + the status view) with the approx/? markers —
# NEVER the authoritative Format-BuildQueueBanner last line.
$script:etaApprox = [char]0x2248
function Format-EtaSuffix {
	param([int]$SelfSeq, [string]$SelfOp, [string]$SelfLane, [switch]$IncludeDone)
	return Get-SafeValue {
		if (-not (Get-Command Get-BuildQueueWaitEta -ErrorAction SilentlyContinue)) { return '' }
		$eta = Get-BuildQueueWaitEta -StateRoot $stateRoot -SelfSeq $SelfSeq -SelfOp $SelfOp -SelfLane $SelfLane
		$startStr = Format-EtaDuration $eta.eta_start_seconds
		$suffix = " eta-start$($script:etaApprox)$startStr"
		if ($IncludeDone) {
			$doneStr = Format-EtaDuration $eta.eta_done_seconds
			$suffix += " eta-done$($script:etaApprox)$doneStr"
		}
		return $suffix
	} ''
}

$enqueueEcho = "build-queue: enqueued as seq=$seq (op=$Op, lane=$opLane)"
$enqueueEcho += Get-SafeValue {
	$queuedTickets = @(Get-ChildItem -Path $ticketsDir -Filter '*.json' -ErrorAction SilentlyContinue)
	$activePresent = Test-Path $activeLock
	$aheadGuess = [math]::Max(0, $queuedTickets.Count - 1) + $(if ($activePresent) { 1 } else { 0 })
	" position=$($aheadGuess + 1)"
} ''
$enqueueEcho += Format-EtaSuffix -SelfSeq $seq -SelfOp $Op -SelfLane $opLane -IncludeDone
Write-Output $enqueueEcho

# ---------------------------------------------------------------------------
# Step 3: Poll loop - reclaim stale, check head, heartbeat
# ---------------------------------------------------------------------------
$lastEmittedPosition = -1

function Get-LiveTickets {
	# Live tickets as @{seq; lane} records (lane absent/invalid -> 'heavy' —
	# legacy tickets ride the heavy lane, eta-priority-lanes D5). Dead-pid
	# tickets are pruned exactly as before.
	$live = @()
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
		$ticketLaneRaw = Get-SafeValue { [string]$data.lane } ''
		$ticketLane = if ($ticketLaneRaw -eq 'fast') { 'fast' } else { 'heavy' }
		$live += [pscustomobject]@{ seq = $ticketSeq; lane = $ticketLane }
	}
	return $live
}

function Get-LiveTicketSeqs {
	return @(Get-LiveTickets | ForEach-Object { $_.seq })
}

function Get-ActiveLockStatusOnce {
	if (-not (Test-Path $activeLock)) { return 'absent' }
	$txt = Get-SafeValue { [System.IO.File]::ReadAllText($activeLock) } $null
	if ($null -eq $txt) { return 'unknown' }

	if (Get-Command Get-ActiveLockStatusFromText -ErrorAction SilentlyContinue) {
		return Get-ActiveLockStatusFromText -Text $txt -IsPidAlive { param($p) Test-PidAlive $p }
	}

	# Fallback (hygiene module absent): inline classification, current behavior.
	$data = Get-SafeValue { $txt | ConvertFrom-Json } $null
	if ($null -eq $data) { return 'unknown' }
	$buildPid = Get-SafeValue {
		$v = $data | Select-Object -ExpandProperty build_pid -ErrorAction SilentlyContinue
		if ($null -ne $v) { [int]$v } else { $null }
	} $null
	if ($null -eq $buildPid) { return 'unknown' }
	if (Test-PidAlive $buildPid) { return 'alive' }
	return 'dead'
}

function Get-ActiveLockStatus {
	# Bounded re-read: a mid-write/transient partial read can classify 'unknown'
	# even though the lock is genuinely alive/dead — retry up to 3 total attempts
	# so a transient read resolves to the real status before falling back to
	# 'unknown' for good.
	$maxAttempts = 3
	$lastStatus = 'unknown'
	for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
		$lastStatus = Get-ActiveLockStatusOnce
		if ($lastStatus -ne 'unknown') { return $lastStatus }
		if ($attempt -lt $maxAttempts) { Start-Sleep -Milliseconds 50 }
	}
	return $lastStatus
}

$logPath = Join-Path $logsDir "$seq.log"
$errPath = Join-Path $logsDir "$seq.err.log"

$won = $false
$staleThreshold = 3
# eta-priority-lanes D5: starvation bound — after K consecutive fast-lane
# claims the oldest heavy waiter is admitted (counter in fast-passes.count).
$maxFastPasses = 3
$recentStatuses = New-Object System.Collections.Generic.List[string]
# Legacy fallback counter (used only when Test-ShouldReclaimLock is unavailable):
# increments ONLY on a confirmed 'dead' observation, resets on anything else.
$consecutiveDeadFallback = 0
while (-not $won) {
	$liveTickets = @(Get-LiveTickets)
	if (-not (@($liveTickets | ForEach-Object { $_.seq }) -contains $seq)) {
		# Self ticket unreadable/pruned mid-poll: keep self in the admission
		# set (synthetic record) so the lane predicate can still elect us.
		$liveTickets += [pscustomobject]@{ seq = $seq; lane = $opLane }
	}
	$liveSeqs    = @($liveTickets | ForEach-Object { $_.seq })
	$lowestSeq   = if ($liveSeqs.Count -gt 0) { (@($liveSeqs | Sort-Object))[0] } else { $seq }
	$status      = Get-ActiveLockStatus

	$recentStatuses.Add($status)
	while ($recentStatuses.Count -gt $staleThreshold) {
		$recentStatuses.RemoveAt(0)
	}

	$isLowestSeq = ($lowestSeq -eq $seq)
	$shouldReclaim = $false
	if (Get-Command Test-ShouldReclaimLock -ErrorAction SilentlyContinue) {
		$shouldReclaim = Test-ShouldReclaimLock -Observations @($recentStatuses.ToArray()) -StaleThreshold $staleThreshold -IsLowestSeq $isLowestSeq
	} else {
		if ($status -eq 'dead') {
			$consecutiveDeadFallback++
		} else {
			$consecutiveDeadFallback = 0
		}
		$shouldReclaim = ($consecutiveDeadFallback -ge $staleThreshold -and $isLowestSeq)
	}

	if ($shouldReclaim) {
		Get-SafeValue { Remove-Item $activeLock -Force -ErrorAction SilentlyContinue }
		$status = 'absent'
		$recentStatuses.Clear()
		$consecutiveDeadFallback = 0
	}

	# eta-priority-lanes D5: lane-aware claim eligibility (admission-order only —
	# the slot-free check, the CreateNew race arbiter, reclaim, and everything
	# below the claim are byte-identical; D7 structural containment). Fallback
	# to the legacy global-lowest-seq rule when the hygiene module is absent.
	$claimEligible = $false
	if ($status -eq 'absent') {
		if (Get-Command Test-LaneClaimEligible -ErrorAction SilentlyContinue) {
			$fastPasses = Get-SafeValue { Get-FastPassCount -StateRoot $stateRoot -MaxFastPasses $maxFastPasses } $maxFastPasses
			$claimEligible = Test-LaneClaimEligible -SelfSeq $seq -Tickets $liveTickets -FastPasses $fastPasses -MaxFastPasses $maxFastPasses
		} else {
			$claimEligible = ($lowestSeq -eq $seq)
		}
	}

	if ($claimEligible) {
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

			if (Get-Command Set-LockFileAtomic -ErrorAction SilentlyContinue) {
				# The exclusive CreateNew open above is the race arbiter (only
				# one waiter can win it) - dispose it BEFORE writing the body
				# so the body write itself can go through the atomic
				# temp-then-move path.
				$lockFileStream.Dispose()
				$lockFileStream = $null
				$null = Set-LockFileAtomic -Path $activeLock -Body $provisionalBody
			} else {
				# Fallback (hygiene module absent): current raw write behavior,
				# writing directly into the still-open claim handle.
				$provisionalBytes = [System.Text.Encoding]::UTF8.GetBytes($provisionalBody)
				$lockFileStream.Write($provisionalBytes, 0, $provisionalBytes.Length)
				$lockFileStream.Flush()
				$lockFileStream.Dispose()
				$lockFileStream = $null
			}

			Get-SafeValue { Remove-Item $ticketPath -Force -ErrorAction SilentlyContinue }

			# eta-priority-lanes D5: ONLY the claim winner writes the counter
			# (single-writer by construction — the CreateNew open above already
			# arbitrated exactly one winner). Increment on a fast claim, reset
			# on a heavy claim. Advisory scheduling state: fail-open.
			Get-SafeValue {
				if (Get-Command Set-FastPassCount -ErrorAction SilentlyContinue) {
					if ($opLane -eq 'fast') {
						$prior = Get-SafeValue { Get-FastPassCount -StateRoot $stateRoot -MaxFastPasses $maxFastPasses } $maxFastPasses
						$null = Set-FastPassCount -StateRoot $stateRoot -Count ([math]::Min($prior + 1, $maxFastPasses))
					} else {
						$null = Set-FastPassCount -StateRoot $stateRoot -Count 0
					}
				}
			}
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
				# eta-priority-lanes D3: eta-start rides the position line (a
				# pre-outcome surface); '?' whenever any term lacks history.
				$etaSuffix = Get-SafeValue {
					$s = Format-EtaSuffix -SelfSeq $seq -SelfOp $Op -SelfLane $opLane
					if ($s) { ($s -replace '^ ', ', ') } else { '' }
				} ''
				Write-Output "build-queue: queued at position $position ($aheadCount build(s) ahead$etaSuffix). Waiting..."
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
	'-StateRoot', (Format-ProcArg $stateRoot),
	'-Worktree', (Format-ProcArg $worktree),
	'-Op', (Format-ProcArg $Op))
if (-not [string]::IsNullOrWhiteSpace($opKind)) {
	$procArgList += @('-OpKind', (Format-ProcArg $opKind))
}
if (-not [string]::IsNullOrWhiteSpace($opHygiene)) {
	$procArgList += @('-Hygiene', (Format-ProcArg $opHygiene))
}
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
$resultPath = Join-Path $resultsDir "$seq.json"
$resultTmp  = Join-Path $resultsDir "$seq.tmp"
$endedAt = (Get-Date).ToString('o')

$mergedResult = Get-SafeValue {
	$existingText = [System.IO.File]::ReadAllText($resultPath)
	$parsed = $existingText | ConvertFrom-Json
	$parsed.exit_code = $exitCode
	$parsed.ended_at  = $endedAt
	$parsed
} $null

$resultBody = if ($null -ne $mergedResult) {
	$mergedResult | ConvertTo-Json -Compress -Depth 5
} else {
	[ordered]@{
		seq       = $seq
		exit_code = $exitCode
		ended_at  = $endedAt
	} | ConvertTo-Json -Compress
}

Get-SafeValue { [System.IO.File]::WriteAllText($resultTmp, $resultBody) }
try {
	[System.IO.File]::Replace($resultTmp, $resultPath, [NullString]::Value)
} catch {
	Get-SafeValue { [System.IO.File]::WriteAllText($resultPath, $resultBody) }
	Get-SafeValue { Remove-Item $resultTmp -Force -ErrorAction SilentlyContinue }
}

Get-SafeValue {
	if (Test-Path $activeLock) {
		# Bounded re-read via the shared Read-WithRetry helper (3x/50ms, no sleep
		# after the last attempt): a transient partial/locked read of active.lock
		# resolves to the real .seq before giving up, so a transient read never
		# leaves a stale lock behind. Converged onto Read-WithRetry for dedupe/
		# parity with the runner's active.lock loop (WU-3, optional).
		$lockSeq = Read-WithRetry -Parse {
			Get-SafeValue {
				$d = [System.IO.File]::ReadAllText($activeLock) | ConvertFrom-Json
				[int]$d.seq
			} $null
		} -MaxAttempts 3 -DelayMs 50 -Fallback $null
		if ($lockSeq -eq $seq) {
			Remove-Item $activeLock -Force
		}
	}
}

Get-SafeValue {
	# Profile-gated release recycle (build-queue-generalization): only a
	# profile that recycles the compiler server (dotnet — today's behavior,
	# also the default when no profile is threaded) reaches Reset-CompilerServer.
	# A rust-tauri/none op must never name-kill VBCSCompiler from the wrapper.
	$wrapperProfile = Get-SafeValue { Get-HygieneProfile -Name $opHygiene } $null
	$wrapperRecycles = if ($null -ne $wrapperProfile) { [bool]$wrapperProfile.recycle_compiler_server } else { $true }
	if ($wrapperRecycles) {
		$occupancy = Get-SafeValue { Get-BuildQueueOccupancy -StateRoot $stateRoot -SelfSeq $seq } 0
		Reset-CompilerServer -OtherBuildActive ($occupancy -gt 0)
	}
}

Get-SafeValue {
	$finalResultText = [System.IO.File]::ReadAllText($resultPath)
	$finalResult = $finalResultText | ConvertFrom-Json

	$resultFidelity = Get-SafeValue { $finalResult.hygiene.result_fidelity } $null
	$buildFidelity  = Get-SafeValue { $finalResult.hygiene.build_fidelity } $null

	$bannerCounts = $null
	$parsedCounts = Get-SafeValue { $finalResult.counts } $null
	if ($null -ne $parsedCounts) {
		$bannerCounts = @{
			passed = $parsedCounts.passed
			failed = $parsedCounts.failed
			total  = $parsedCounts.total
		}
	}

	$banner = Format-BuildQueueBanner -Seq $seq -Op $Op -ExitCode $exitCode -ResultFidelity $resultFidelity -BuildFidelity $buildFidelity -Counts $bannerCounts
	Write-Output $banner
}

exit $exitCode


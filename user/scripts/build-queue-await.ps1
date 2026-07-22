<#
.SYNOPSIS
  Followable-wait primitive for the build queue: block until a build's
  results/<seq>.json exists, then re-emit the authoritative outcome banner.

.DESCRIPTION
  A backgrounded queue-routed build (or a foreground one whose wrapper was
  killed by a shell timeout) returns only "build-queue: enqueued as seq=N" —
  which is NOT an outcome. This helper turns that enqueue into a followable,
  completed result: it polls <StateRoot>/results/<Seq>.json until present,
  reads the outcome fields defensively (any field may be missing/$null — the
  current runner does not record `op`, for example), composes the SAME
  authoritative banner the wrapper prints (via the real Format-BuildQueueBanner
  from build-queue-hygiene.ps1), writes it as the LAST stdout line, and exits
  with the build's own exit_code.

  Exit codes:
    <build exit_code>  result present and readable — mirrors the build.
    124                await-timeout: result not yet present. The build may
                       still be running — re-run this helper or check
                       /build-queue-status. NEVER treat 124 as success.
    125                internal/malformed: hygiene module unavailable, or the
                       result file is present but unreadable / carries no
                       exit_code after bounded retries.

.PARAMETER Seq
  The build-queue sequence number to await (from the
  "build-queue: enqueued as seq=N" line).

.PARAMETER TimeoutSeconds
  Maximum seconds to wait for the results file (default 540 — just under the
  10-minute Bash tool ceiling so the caller sees exit 124, not a tool kill).

.PARAMETER PollIntervalMs
  Poll interval while waiting (default 2000).

.PARAMETER StateRoot
  Build-queue state root (default ~\.claude\state\build-queue).

.NOTES
  Read-only over the queue state: this helper never writes tickets, locks,
  results, or logs.
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory = $true)][int]$Seq,
	[int]$TimeoutSeconds = 540,
	[int]$PollIntervalMs = 2000,
	[string]$StateRoot = (Join-Path $HOME '.claude\state\build-queue')
)

Set-StrictMode -Version Latest

# Fail-open helper idiom (copied verbatim from build-queue-runner.ps1:34-37).
function Get-SafeValue {
	param([scriptblock]$Block, $Fallback = $null)
	try { & $Block } catch { $Fallback }
}

# Dot-source at SCRIPT scope — never inside a function/child scope (see
# docs/bugs/build-queue-hygiene-dot-source-discarded-in-child-scope); same
# Join-Path $PSScriptRoot pattern as build-queue.ps1.
try {
	. (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1')
} catch { }

if ($null -eq (Get-Command Format-BuildQueueBanner -ErrorAction SilentlyContinue)) {
	Write-Output "build-queue-await: build-queue-hygiene.ps1 failed to load (Format-BuildQueueBanner unavailable) - cannot compose the authoritative banner."
	exit 125
}

$resultPath = Join-Path (Join-Path $StateRoot 'results') "$Seq.json"
$activeLock = Join-Path $StateRoot 'active.lock'

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$result = $null
$staleActiveLockDetected = $false
while ($true) {
	if (Test-Path -LiteralPath $resultPath) {
		# Bounded parse-with-retry: the runner writes the file atomically, but a
		# transient partial/locked read resolves within the shared 3x/50ms window.
		$result = Read-WithRetry -Parse {
			Get-SafeValue {
				$text = Get-Content -LiteralPath $resultPath -Raw -ErrorAction Stop
				if ([string]::IsNullOrWhiteSpace($text)) { return $null }
				$text | ConvertFrom-Json
			} $null
		} -MaxAttempts 3 -DelayMs 50 -Fallback $null
		if ($null -ne $result) { break }
	}

	# Detect stale active lock: if the lock exists but the build_pid is dead and
	# the lock is old (30+ minutes), report it as a failure rather than polling
	# forever. (Gap fix: docs/bugs/build-queue-await-hangs-on-stale-lock)
	if (-not $staleActiveLockDetected -and (Test-Path -LiteralPath $activeLock)) {
		$staleActiveLockDetected = Get-SafeValue {
			$lockText = Get-Content -LiteralPath $activeLock -Raw -ErrorAction SilentlyContinue
			if ([string]::IsNullOrWhiteSpace($lockText)) { return $false }
			$lockData = $lockText | ConvertFrom-Json -ErrorAction SilentlyContinue
			if ($null -eq $lockData) { return $false }

			$lockSeq = Get-SafeValue { [int]$lockData.seq } $null
			$buildPid = Get-SafeValue { [int]$lockData.build_pid } $null
			$startedAtRaw = Get-SafeValue { [string]$lockData.started_at } $null

			# Only worry about locks from OTHER builds (not our seq)
			if ($null -eq $lockSeq -or $lockSeq -eq $Seq) { return $false }

			# Check if the PID is dead
			$pidDead = $false
			if ($null -ne $buildPid -and $buildPid -gt 0) {
				try {
					$null = [System.Diagnostics.Process]::GetProcessById($buildPid)
				} catch [System.ArgumentException] {
					$pidDead = $true
				}
			}
			if (-not $pidDead) { return $false }

			# Check lock age
			if ($null -ne $startedAtRaw) {
				try {
					$startedAt = [DateTime]::Parse($startedAtRaw, [System.Globalization.CultureInfo]::InvariantCulture)
					$elapsed = [DateTime]::UtcNow - $startedAt
					# 30-minute staleness threshold
					return ($elapsed.TotalMinutes -ge 30)
				} catch { }
			}

			return $false
		} $false

		if ($staleActiveLockDetected) { break }
	}

	if ([DateTime]::UtcNow -ge $deadline) { break }
	Start-Sleep -Milliseconds $PollIntervalMs
}

if ($null -eq $result) {
	if ($staleActiveLockDetected) {
		Write-Output "build-queue-await: detected stale active lock (dead PID, lock age 30+ minutes) blocking seq=$Seq. Another build may have crashed. Run /build-queue-status to assess or manually remove the lock ($activeLock) if safe."
		exit 1
	}
	if (Test-Path -LiteralPath $resultPath) {
		Write-Output "build-queue-await: result file for seq=$Seq is present but unreadable/malformed after retries ($resultPath)."
		exit 125
	}
	Write-Output "build-queue-await: result not yet present for seq=$Seq after ${TimeoutSeconds}s ($resultPath). The build may still be running - re-run build-queue-await.ps1 -Seq $Seq or check /build-queue-status. Do NOT treat this as success."
	exit 124
}

# Defensive field reads — any field may be missing/$null (the current runner
# records no `op`; counts/hygiene are absent for some ops and legacy results).
$exitCode       = Get-SafeValue { [int]$result.exit_code } $null
$op             = Get-SafeValue { [string]$result.op } ''
if ($null -eq $op) { $op = '' }
$resultFidelity = Get-SafeValue { [string]$result.hygiene.result_fidelity } $null
$buildFidelity  = Get-SafeValue { [string]$result.hygiene.build_fidelity } $null

$bannerCounts = $null
$parsedCounts = Get-SafeValue { $result.counts } $null
if ($null -ne $parsedCounts) {
	$bannerCounts = @{
		passed = Get-SafeValue { $parsedCounts.passed } $null
		failed = Get-SafeValue { $parsedCounts.failed } $null
		total  = Get-SafeValue { $parsedCounts.total } $null
	}
}

if ($null -eq $exitCode) {
	Write-Output "build-queue-await: result for seq=$Seq carries no readable exit_code ($resultPath)."
	exit 125
}

$banner = Format-BuildQueueBanner -Seq $Seq -Op $op -ExitCode $exitCode `
	-ResultFidelity $resultFidelity -BuildFidelity $buildFidelity -Counts $bannerCounts

# The authoritative banner is the LAST stdout line; exit mirrors the build.
Write-Output $banner
exit $exitCode

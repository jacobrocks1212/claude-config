<#
.SYNOPSIS
  Self-releasing detached build runner for the machine-global Cognito build queue.

.DESCRIPTION
  Invoked as a detached child by build-queue.ps1.  Runs the filtered build/test
  script as a nested powershell.exe grandchild, then writes results/<seq>.json
  and releases active.lock (seq-scoped, idempotent) before exiting with the
  build exit code.  The result survives the foreground wrapper being killed.

  Parameters
    -Exec       Absolute path to the filtered script to run.
    -Seq        Queue sequence number allocated by the wrapper.
    -StateRoot  State directory (defaults to the same root as build-queue.ps1).
    Remaining   Verbatim args forwarded to the filtered script.

  results/<seq>.json schema
    {
      seq: <int>, exit_code: <int>, ended_at: "<ISO-8601>",
      counts: { passed: <int>, failed: <int>, total: <int> } | null,
        # Parsed from the LAST "Results: Passed=<P> Failed=<F> Total=<T>" line found
        # in logs/<seq>.log (the test grandchild's inherited stdout, which the
        # wrapper already tails live — no separate redirect is added for this).
        # null for a non-test op, a missing log, or an unparseable/absent line.
      hygiene: {
        vbcscompiler_recycled: <bool>,   # whether VBCSCompiler was recycled after the build
        recycle_skipped_reason: "concurrent-build-active" | null, # non-null iff the recycle was skipped because another queue build was live (occupancy > 0); null when the recycle ran (sole build) or otherwise
        quarantined_artifacts: [<path>], # absolute paths of 0-byte/truncated-PE *.dll swept from bin/+obj/ (empty on a clean build)
        result_fidelity: "verified" | "no-output" | "no-tests-matched" | "n/a"  # "no-output" = test op produced zero results; "no-tests-matched" = test op whose filter matched zero tests (summary reported Total=0); "verified" = test op had real output; "n/a" = build op
        build_fidelity: "log-failure-override" | "no-output" | "verified" | "n/a"  # "log-failure-override" = a build op exited 0 but its captured log matched a known MSBuild failure signature (Test-BuildLogFailure), so the exit code/buildFailed were overridden to failure BEFORE the quarantine gate; "no-output" = a build op exited 0 but produced no captured output (missing/empty/whitespace/near-empty log — Test-BuildProducedNoOutput), overridden to failure the same way; "verified" = build op needed no override; "n/a" = non-build op (e.g. test)
        lockers_reaped: [<pid>]          # PIDs of in-worktree processes reaped (Stop-DllLockers) BEFORE a build op started, to clear a leftover DLL lock ahead of the copy step (empty on a clean run / test op / no worktree / fail-open)
      }
    }
    Job-Object reap of build descendants happens unconditionally but records no PID list
    (fire-and-forget) — there is no reaped-PID field.

    Build-op stdout/stderr are redirected to logs/<seq>.build.log / <seq>.build.err.log
    (sibling of results/) so Test-BuildLogFailure has a log to scan for a bogus-exit-0
    failure signature (e.g. copy-lock retries that MSBuild reports as errors but the
    outer process still exits success).
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory=$true)]
	[string]$Exec,

	[Parameter(Mandatory=$true)]
	[int]$Seq,

	[string]$StateRoot = (Join-Path $HOME '.claude\state\build-queue'),

	[string]$Worktree,

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

function Format-ProcArg {
	param([string]$Value)
	if ($Value -eq '' -or $Value -match '[\s"]') {
		return '"' + ($Value -replace '"', '\"') + '"'
	}
	return $Value
}

$job = [IntPtr]::Zero
$vbcscompilerRecycled = $false
$recycleSkippedReason = $null
$quarantinedArtifacts = @()
$lockersReaped = @()
$execLeaf = Get-SafeValue { Split-Path -Leaf $Exec } ''
$isBuildOp = $execLeaf -match 'build-filtered\.ps1$'
$isTestOp = $execLeaf -match 'test-filtered\.ps1$'
$buildLogPath = $null
$buildFidelity = 'n/a'
trap {
	Get-SafeValue { Stop-BuildJobTree -JobHandle $job }
	continue
}

try {
	$procArgList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Format-ProcArg $Exec))
	foreach ($a in $ExecArgs) {
		$procArgList += (Format-ProcArg ([string]$a))
	}
	$procArgString = $procArgList -join ' '

	$startProcParams = @{
		FilePath     = 'powershell.exe'
		ArgumentList = $procArgString
		NoNewWindow  = $true
		PassThru     = $true
	}
	if ($isBuildOp) {
		Get-SafeValue {
			$logsDir = Join-Path $StateRoot 'logs'
			if (-not (Test-Path $logsDir)) {
				$null = New-Item -ItemType Directory -Path $logsDir -Force
			}
			$buildLogPath = Join-Path $logsDir "$Seq.build.log"
			$startProcParams['RedirectStandardOutput'] = $buildLogPath
			$startProcParams['RedirectStandardError']  = (Join-Path $logsDir "$Seq.build.err.log")
		}
	}

	# Reap any lingering in-worktree DLL lockers BEFORE the build starts, so a leftover
	# locker from a prior run is gone by the time MSBuild reaches the copy step. Build
	# ops only (never test ops); no-op when there is no worktree to scope the reap to.
	if ($isBuildOp -and -not [string]::IsNullOrWhiteSpace($Worktree)) {
		$lockersReaped = Get-SafeValue { @(Stop-DllLockers -WorktreeRoot $Worktree) } @()
	}

	$proc = Start-Process @startProcParams
	$null = $proc.Handle

	$job = New-BuildJobObject
	if ($job -ne [IntPtr]::Zero) {
		$null = Add-ProcessToBuildJob -JobHandle $job -ProcessHandle $proc.Handle
	}

	$proc.WaitForExit()
	$exitCode = $proc.ExitCode
	if ($null -eq $exitCode) { $exitCode = 0 }

	if ($isBuildOp) {
		# Flush-safe build-log read (Root Cause C): the build log is flushed/closed
		# by the wrapper's live-tail redirect; a single-shot ReadAllText here can
		# race that flush and see an empty/truncated log. Route through
		# Read-WithRetry so a not-yet-flushed log settles (3x/50ms) before we
		# classify. A genuinely-absent path returns immediately (not a race); an
		# empty read returns $null → retry; exhaustion falls back to the same
		# fail-open no-failure verdict the single-shot read used.
		# Capture the SAME flush-safe read for the no-output classifier below —
		# the Phase-3 build-output gate classifies on this text, it does NOT
		# re-read the log (Phase-3 Integration Note: "classifier called AFTER the
		# Phase 2 read, not a re-read"). Left $null when the log was genuinely
		# absent or never settled (both => no output produced).
		$script:buildLogTextForClassify = $null
		$logFailure = Read-WithRetry -Parse {
			if ([string]::IsNullOrWhiteSpace($buildLogPath) -or -not (Test-Path $buildLogPath)) {
				return @{ failed = $false; signature = $null }
			}
			$logText = Get-SafeValue { [System.IO.File]::ReadAllText($buildLogPath) } $null
			if ([string]::IsNullOrEmpty($logText)) {
				return $null
			}
			$script:buildLogTextForClassify = $logText
			Get-SafeValue { Test-BuildLogFailure -Log $logText } @{ failed = $false; signature = $null }
		} -Fallback @{ failed = $false; signature = $null }

		if ($logFailure.failed -and $exitCode -eq 0) {
			# Log-failure-override wins first: a real MSBuild failure signature is
			# the strongest signal, so it takes precedence over the no-output
			# residual case below.
			$exitCode = 1
			$buildFailed = $true
			$buildFidelity = 'log-failure-override'
		} elseif ($exitCode -eq 0 -and (Test-BuildProducedNoOutput -LogText $script:buildLogTextForClassify)) {
			# Root Cause B: exit 0 but the build produced no captured output
			# (missing / empty / whitespace-only / near-empty log) — a silently
			# broken build that Test-BuildLogFailure fails OPEN on. Force failure,
			# mirroring the log-failure-override mechanism above. Forcing
			# $buildFailed = $true here ALSO makes Phase 1's per-project quarantine
			# sweep (the finally block's `$buildFailed -and $Worktree` gate) fire on
			# a no-output build, so its poisoned artifacts are swept too.
			$exitCode = 1
			$buildFailed = $true
			$buildFidelity = 'no-output'
		} else {
			$buildFidelity = 'verified'
		}
	}
} finally {
	Get-SafeValue { Stop-BuildJobTree -JobHandle $job }
	$occupancy = Get-SafeValue { Get-BuildQueueOccupancy -StateRoot $StateRoot -SelfSeq $Seq } 0
	$otherBuildActive = ($occupancy -gt 0)
	$vbcscompilerRecycled = Get-SafeValue { Reset-CompilerServer -OtherBuildActive $otherBuildActive } $false
	$recycleSkippedReason = if ($otherBuildActive) { 'concurrent-build-active' } else { $null }

	$buildFailed = Get-SafeValue { ($null -eq $exitCode) -or ($exitCode -ne 0) } $true
	if ($buildFailed -and -not [string]::IsNullOrWhiteSpace($Worktree)) {
		$quarantinedArtifacts = Get-SafeValue { @(Remove-PoisonedArtifacts -WorktreeRoot $Worktree) } @()
	}
}

$resultFidelity = Get-SafeValue {
	if (-not $isTestOp) { 'n/a' }
	elseif ($exitCode -eq 3) { 'no-output' }
	elseif ($exitCode -eq 5) { 'no-tests-matched' }
	else { 'verified' }
} 'n/a'

# Test-op Passed/Failed/Total counts, parsed from the grandchild's inherited stdout
# (already captured in logs/<seq>.log by the wrapper's live-tail redirect — no
# additional RedirectStandardOutput is added here for test ops, which would break
# that live tail). Fail-open: any read/parse error, a non-test op, a missing log,
# or an absent "Results:" line all yield $null (never throws).
# Flush-safe counts read (Root Cause C): the "Results:" summary line is the LAST
# thing written to the test log, so a single-shot read here most acutely races the
# wrapper-owned flush/close — a dropped trailing line reads as counts=$null and the
# agent bypasses the capture. Route through Read-WithRetry so a not-yet-flushed
# Results line settles (3x/50ms) before we commit an empty parse. The $isTestOp
# guard stays OUTSIDE the retry (a non-test op is $null immediately, not a race);
# a genuinely-absent Results line still falls back to $null after exhaustion.
$counts = $null
if ($isTestOp) {
	$counts = Read-WithRetry -Parse {
		$testLogPath = Join-Path (Join-Path $StateRoot 'logs') "$Seq.log"
		if (-not (Test-Path $testLogPath)) { return $null }
		$logText = Get-SafeValue { [System.IO.File]::ReadAllText($testLogPath) } $null
		if ([string]::IsNullOrEmpty($logText)) { return $null }
		$resultMatches = [regex]::Matches($logText, '^Results:\s*Passed=(\d+)\s+Failed=(\d+)\s+Total=(\d+)', [System.Text.RegularExpressions.RegexOptions]::Multiline)
		if ($resultMatches.Count -eq 0) { return $null }
		$m = $resultMatches[$resultMatches.Count - 1]
		[ordered]@{
			passed = [int]$m.Groups[1].Value
			failed = [int]$m.Groups[2].Value
			total  = [int]$m.Groups[3].Value
		}
	} -Fallback $null
}

$resultsDir = Join-Path $StateRoot 'results'
Get-SafeValue {
	if (-not (Test-Path $resultsDir)) {
		$null = New-Item -ItemType Directory -Path $resultsDir -Force
	}
}

$resultPath = Join-Path $resultsDir "$Seq.json"
$resultTmp  = Join-Path $resultsDir "$Seq.tmp"
$resultBody = [ordered]@{
	seq       = $Seq
	exit_code = $exitCode
	ended_at  = (Get-Date).ToString('o')
	counts    = $counts
	hygiene   = [ordered]@{
		vbcscompiler_recycled  = $vbcscompilerRecycled
		recycle_skipped_reason = $recycleSkippedReason
		quarantined_artifacts  = $quarantinedArtifacts
		result_fidelity        = $resultFidelity
		build_fidelity         = $buildFidelity
		lockers_reaped         = $lockersReaped
	}
} | ConvertTo-Json -Compress -Depth 5

[System.IO.File]::WriteAllText($resultTmp, $resultBody)
try {
	[System.IO.File]::Replace($resultTmp, $resultPath, [NullString]::Value)
} catch {
	Get-SafeValue { [System.IO.File]::WriteAllText($resultPath, $resultBody) }
	Get-SafeValue { Remove-Item $resultTmp -Force -ErrorAction SilentlyContinue }
}

$activeLock = Join-Path $StateRoot 'active.lock'
Get-SafeValue {
	if (Test-Path $activeLock) {
		# Bounded re-read via the shared Read-WithRetry helper (3x/50ms, no sleep
		# after the last attempt): a transient partial/locked read of active.lock
		# resolves to the real .seq before giving up, so a transient read never
		# leaves a stale lock behind. Converged onto Read-WithRetry for dedupe/
		# parity with the runner's other fidelity-bearing reads (WU-3, optional).
		$lockSeq = Read-WithRetry -Parse {
			Get-SafeValue {
				$data = [System.IO.File]::ReadAllText($activeLock) | ConvertFrom-Json
				[int]$data.seq
			} $null
		} -MaxAttempts 3 -DelayMs 50 -Fallback $null
		if ($lockSeq -eq $Seq) {
			Remove-Item $activeLock -Force
		}
	}
}

exit $exitCode

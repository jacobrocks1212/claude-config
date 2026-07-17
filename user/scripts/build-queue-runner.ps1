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
    -Op         Queue op name (build-queue-eta-priority-lanes D1). When
                present, the result gains op/started_at/duration_seconds and
                a stats/<op>.json ring entry is appended (fail-open). Absent
                (legacy invocation) -> those fields are omitted, everything
                else byte-identical.
    -OpKind     'build' | 'test' from the repo's ops manifest
                (build-queue-generalization). Empty/absent falls back to the
                legacy exec-leaf-name inference — byte-identical for legacy
                invocations.
    -Hygiene    Hygiene profile id ('dotnet' | 'rust-tauri' | 'none') from
                the manifest. Empty/absent resolves to the 'dotnet' profile
                (today's behavior). Dispatch happens on the profile record
                from Get-HygieneProfile, never on repo identity or filename.
    Remaining   Verbatim args forwarded to the filtered script.

  results/<seq>.json schema
    {
      seq: <int>, exit_code: <int>, ended_at: "<ISO-8601>",
      op: "<op>", started_at: "<ISO-8601>", duration_seconds: <double>,
        # Present only when the wrapper threaded -Op (eta-priority-lanes D1).
        # duration_seconds = exec-run time (runner start -> exit), not queue wait.
      counts: { passed: <int>, failed: <int>, total: <int> } | null,
        # Parsed from the LAST "Results: Passed=<P> Failed=<F> Total=<T>" line found
        # in logs/<seq>.log (the test grandchild's inherited stdout, which the
        # wrapper already tails live — no separate redirect is added for this).
        # null for a non-test op, a missing log, or an unparseable/absent line.
      hygiene: {
        status: "pending" | "complete",  # two-phase crash-safe write (docs/bugs/
        # build-queue-timeout-kill-reaps-detached-runner): the result is written
        # EARLY — immediately after the exit code + fidelity classification are
        # known, BEFORE any hygiene work — with status "pending" and the hygiene
        # fields below defaulted, then written a SECOND time after hygiene with
        # the real hygiene fields and status "complete". An untrappable kill
        # mid-hygiene (Bash-tool timeout tree-kill) leaves the truthful pending
        # result instead of nothing, so build-queue-await returns the build's
        # real outcome instead of a misleading 124.
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

	[string]$Op = '',

	[string]$OpKind = '',

	[string]$Hygiene = '',

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
# Manifest-threaded -OpKind wins; empty falls back to the legacy leaf-name
# inference so a pre-manifest invocation is byte-identical.
if (-not [string]::IsNullOrWhiteSpace($OpKind)) {
	$isBuildOp = ($OpKind -eq 'build')
	$isTestOp  = ($OpKind -eq 'test')
} else {
	$isBuildOp = $execLeaf -match 'build-filtered\.ps1$'
	$isTestOp = $execLeaf -match 'test-filtered\.ps1$'
}
# Hygiene profile record (build-queue-generalization D3): empty -Hygiene
# resolves to 'dotnet' inside Get-HygieneProfile (today's behavior); a
# missing hygiene module (dot-source failed) leaves $null and the dotnet
# defaults below — where every dotnet-only call site is already fail-open.
$hygieneProfile = Get-SafeValue { Get-HygieneProfile -Name $Hygiene } $null
$profileReapsLockers  = if ($null -ne $hygieneProfile) { [bool]$hygieneProfile.reap_dll_lockers } else { $true }
$profileRecycles      = if ($null -ne $hygieneProfile) { [bool]$hygieneProfile.recycle_compiler_server } else { $true }
$profilePoisonSweep   = if ($null -ne $hygieneProfile) { $hygieneProfile.poison_sweep } else { 'dotnet-dll' }
$profileLogSignatures = if ($null -ne $hygieneProfile) { $hygieneProfile.log_failure_signatures } else { 'msbuild' }
$buildLogPath = $null
$buildFidelity = 'n/a'
# Pre-initialized so the finally block's early-write guard can distinguish a
# known exit code from a build-spawn exception (where it stays $null) without
# tripping Set-StrictMode.
$exitCode = $null
trap {
	# $null = : the unassigned Stop-BuildJobTree return leaked a bare 'True'
	# into the runner's stdout (logs/<seq>.log, which the test-counts regex
	# parses) — assign it away.
	$null = Get-SafeValue { Stop-BuildJobTree -JobHandle $job }
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
		$logsDir = Join-Path $StateRoot 'logs'
		Get-SafeValue {
			if (-not (Test-Path $logsDir)) {
				$null = New-Item -ItemType Directory -Path $logsDir -Force
			}
		}
		$buildLogPath = Join-Path $logsDir "$Seq.build.log"
		$startProcParams['RedirectStandardOutput'] = $buildLogPath
		$startProcParams['RedirectStandardError']  = (Join-Path $logsDir "$Seq.build.err.log")
	}

	# Reap any lingering in-worktree DLL lockers BEFORE the build starts, so a leftover
	# locker from a prior run is gone by the time MSBuild reaches the copy step. Build
	# ops only (never test ops); no-op when there is no worktree to scope the reap to.
	# Profile-gated (dotnet only): a rust-tauri/none op never reaps by DLL lock.
	if ($isBuildOp -and $profileReapsLockers -and -not [string]::IsNullOrWhiteSpace($Worktree)) {
		$lockersReaped = Get-SafeValue { @(Stop-DllLockers -WorktreeRoot $Worktree) } @()
	}

	# eta-priority-lanes D1: capture the run start instant immediately before
	# the exec spawn — duration_seconds measures exec-run time, not queue wait.
	$script:runStartedAt = Get-Date

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
		# Read-WithRetry so a not-yet-flushed log settles before we
		# classify. A genuinely-absent path returns immediately (not a race); an
		# empty read returns $null -> retry; exhaustion falls back to the same
		# fail-open no-failure verdict the single-shot read used.
		# WIDENED WINDOW (build-queue-nxbuild-false-no-output-fail): the original
		# 3x/50ms (~100ms ceiling) settle budget was tuned for dotnet's fast,
		# near-immediate flush and was too tight for an npx/node/rspack process
		# tree (Nx daemon/per-task worker fan-out), whose redirected stdout can
		# settle to disk noticeably later -- the classifier then sees an empty
		# read, feeds $null to Test-BuildProducedNoOutput, and force-fails a
		# genuinely-successful build as `no-output`. 10x/100ms (~1s ceiling) is
		# cheap relative to a multi-second-to-multi-minute build op and applies to
		# EVERY build op (not just nx) -- a fast dotnet build still settles on
		# attempt 1, so this is a pure widening, never a regression for msbuild.
		# Capture the SAME flush-safe read for the no-output classifier below —
		# the Phase-3 build-output gate classifies on this text, it does NOT
		# re-read the log (Phase-3 Integration Note: "classifier called AFTER the
		# Phase 2 read, not a re-read"). Left $null when the log was genuinely
		# absent or never settled (both => no output produced).
		$script:buildLogTextForClassify = $null
		$logFailure = Read-WithRetry -MaxAttempts 10 -DelayMs 100 -Parse {
			if ([string]::IsNullOrWhiteSpace($buildLogPath) -or -not (Test-Path $buildLogPath)) {
				return @{ failed = $false; signature = $null }
			}
			$logText = Get-SafeValue { [System.IO.File]::ReadAllText($buildLogPath) } $null
			if ([string]::IsNullOrEmpty($logText)) {
				return $null
			}
			$script:buildLogTextForClassify = $logText
			if ($null -eq $profileLogSignatures) {
				# Profile has no log-failure signature set ('none') — the log
				# is still captured above for the no-output classifier, but no
				# signature scan runs.
				return @{ failed = $false; signature = $null }
			}
			Get-SafeValue { Test-BuildLogFailure -Log $logText -SignatureSet $profileLogSignatures } @{ failed = $false; signature = $null }
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
	# ------------------------------------------------------------------
	# CRASH-SAFE EARLY RESULT WRITE
	# (docs/bugs/build-queue-timeout-kill-reaps-detached-runner)
	#
	# A foreground wrapper call that hits its Bash-tool timeout is
	# tree-killed (exit 143), and that TerminateProcess reaps this
	# "detached" runner with it — untrappable, so no exit handler can save
	# the result. On RED builds the runner used to spend minutes in the
	# failed-build quarantine sweep BEFORE the single result write, losing
	# the build's true outcome forever and stranding active.lock on a dead
	# pid. The fix shrinks the unprotected window: persist the truthful
	# result (exit code + fidelity + counts, hygiene marked status=pending)
	# the moment the outcome is known — BEFORE any hygiene work — then
	# merge the real hygiene fields in the second (final) write below,
	# after hygiene. Lock release stays AFTER hygiene (the lock serializes
	# hygiene against the next build); a kill after this write still
	# strands the lock, but the next enqueue's 3-dead-tick reclaim
	# self-heals that — and build-queue-await now returns the build's real
	# outcome instead of a misleading 124.
	# ------------------------------------------------------------------

	# Result fidelity + test counts depend only on the exit code and the
	# already-complete logs, so they are computed here (before hygiene) and
	# carried by the early write; the final write reuses the same values.
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
			# Share-tolerant read (NOT ReadAllText): logs/<seq>.log IS this
			# runner's own redirected stdout, so its write handle stays open for
			# the runner's whole lifetime — ReadAllText (FileShare.Read) hits a
			# deterministic sharing violation against that live write handle and
			# silently nulled the counts. Open FileShare.ReadWrite instead, the
			# same pattern as the wrapper's live tail.
			$logText = Get-SafeValue {
				$fs = [System.IO.File]::Open($testLogPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
				try {
					$sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
					try { $sr.ReadToEnd() } finally { $sr.Dispose() }
				} finally {
					$fs.Dispose()
				}
			} $null
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

	# eta-priority-lanes D1: duration fields, present only when -Op was threaded
	# (legacy invocations omit all three — byte-identical result schema).
	# Captured HERE, at build exit — duration_seconds is exec-run time per the
	# documented schema (hygiene time excluded); the final write and the stats
	# ring reuse these exact values so both writes agree.
	$durationSeconds = $null
	$startedAtStamp  = $null
	if (-not [string]::IsNullOrWhiteSpace($Op)) {
		$startedAtStamp = Get-SafeValue { $script:runStartedAt.ToString('o') } $null
		$durationSeconds = Get-SafeValue {
			[math]::Round(((Get-Date) - $script:runStartedAt).TotalSeconds, 1)
		} $null
	}

	# EARLY WRITE — only when the exit code is actually known (a build-spawn
	# exception leaves $exitCode $null: hygiene still runs below and the final
	# write handles the degraded case, preserving the legacy exception path).
	# Fail-open: a failed/unavailable Write-BuildQueueResult (e.g. the hygiene
	# module never dot-sourced) degrades to today's single post-hygiene write.
	if ($null -ne $exitCode) {
		$null = Get-SafeValue {
			Write-BuildQueueResult -StateRoot $StateRoot -Seq $Seq -ExitCode $exitCode `
				-Counts $counts -Op $Op -StartedAt $startedAtStamp -DurationSeconds $durationSeconds `
				-Hygiene ([ordered]@{
					status                 = 'pending'
					vbcscompiler_recycled  = $false
					recycle_skipped_reason = $null
					quarantined_artifacts  = @()
					result_fidelity        = $resultFidelity
					build_fidelity         = $buildFidelity
					lockers_reaped         = $lockersReaped
				})
		}
	}

	# Hygiene — behavior, gating, and internal order UNCHANGED; only its
	# position relative to the (now-early) result write moved. A kill
	# anywhere from here down leaves the truthful early result above.
	# ($null = : the unassigned Stop-BuildJobTree return used to leak a bare
	# 'True' into logs/<seq>.log, which the test-counts regex parses.)
	$null = Get-SafeValue { Stop-BuildJobTree -JobHandle $job }
	if ($profileRecycles) {
		# dotnet profile only: the occupancy-gated VBCSCompiler recycle (the
		# ONE sanctioned name-targeted kill). Other profiles never reach it.
		$occupancy = Get-SafeValue { Get-BuildQueueOccupancy -StateRoot $StateRoot -SelfSeq $Seq } 0
		$otherBuildActive = ($occupancy -gt 0)
		$vbcscompilerRecycled = Get-SafeValue { Reset-CompilerServer -OtherBuildActive $otherBuildActive } $false
		$recycleSkippedReason = if ($otherBuildActive) { 'concurrent-build-active' } else { $null }
	}

	$buildFailed = Get-SafeValue { ($null -eq $exitCode) -or ($exitCode -ne 0) } $true
	# Poison-DLL sweep is a BUILD-op concern only — gate on $isBuildOp so a
	# zero-result TEST op (exit 3 no-output / exit 5 zero-match, both non-zero
	# → buildFailed) no longer walks the whole worktree for artifacts a
	# --no-build test op never produced (docs/bugs/build-queue-foreground-
	# wait-blocks-past-terminal-outcome Theory 2). Delegated to the pure
	# Test-ShouldSweepPoisonedArtifacts gate for coverage; fail-open to the
	# same isBuildOp-gated inline predicate if the hygiene module is absent.
	$shouldSweep = if (Get-Command Test-ShouldSweepPoisonedArtifacts -ErrorAction SilentlyContinue) {
		Get-SafeValue { Test-ShouldSweepPoisonedArtifacts -IsBuildOp $isBuildOp -ExitCode $exitCode -PoisonSweep $profilePoisonSweep -Worktree $Worktree } $false
	} else {
		$isBuildOp -and $buildFailed -and $profilePoisonSweep -eq 'dotnet-dll' -and -not [string]::IsNullOrWhiteSpace($Worktree)
	}
	if ($shouldSweep) {
		$quarantinedArtifacts = Get-SafeValue { @(Remove-PoisonedArtifacts -WorktreeRoot $Worktree) } @()
	}
}

# FINAL WRITE — merge the real hygiene fields over the early write (status
# flips pending -> complete). Kept INLINE (not via Write-BuildQueueResult) so
# the result contract survives a failed hygiene-module dot-source, exactly as
# the single write always has.
$resultsDir = Join-Path $StateRoot 'results'
Get-SafeValue {
	if (-not (Test-Path $resultsDir)) {
		$null = New-Item -ItemType Directory -Path $resultsDir -Force
	}
}

$resultPath = Join-Path $resultsDir "$Seq.json"
$resultTmp  = Join-Path $resultsDir "$Seq.tmp"
$endedAtStamp = (Get-Date).ToString('o')

$resultBody = [ordered]@{
	seq       = $Seq
	exit_code = $exitCode
	ended_at  = $endedAtStamp
	counts    = $counts
	hygiene   = [ordered]@{
		status                 = 'complete'
		vbcscompiler_recycled  = $vbcscompilerRecycled
		recycle_skipped_reason = $recycleSkippedReason
		quarantined_artifacts  = $quarantinedArtifacts
		result_fidelity        = $resultFidelity
		build_fidelity         = $buildFidelity
		lockers_reaped         = $lockersReaped
	}
}
if (-not [string]::IsNullOrWhiteSpace($Op)) {
	$resultBody['op']               = $Op
	$resultBody['started_at']       = $startedAtStamp
	$resultBody['duration_seconds'] = $durationSeconds
}
$resultBody = $resultBody | ConvertTo-Json -Compress -Depth 5

[System.IO.File]::WriteAllText($resultTmp, $resultBody)
try {
	[System.IO.File]::Replace($resultTmp, $resultPath, [NullString]::Value)
} catch {
	Get-SafeValue { [System.IO.File]::WriteAllText($resultPath, $resultBody) }
	Get-SafeValue { Remove-Item $resultTmp -Force -ErrorAction SilentlyContinue }
}

# eta-priority-lanes D2: append this run to the per-op duration ring
# (stats/<op>.json, cap 20, atomic, fail-open — never affects the result).
if (-not [string]::IsNullOrWhiteSpace($Op) -and $null -ne $durationSeconds) {
	$null = Get-SafeValue {
		Add-BuildQueueStatsEntry -StateRoot $StateRoot -Op $Op -Seq $Seq `
			-DurationSeconds $durationSeconds -ExitCode $exitCode -EndedAt $endedAtStamp
	} $false
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

# $exitCode is $null only on the degraded build-spawn-exception path (never
# after a real WaitForExit, which coerces null to 0) — exit 1 there instead of
# letting `exit $null` report a false green.
if ($null -eq $exitCode) { exit 1 }
exit $exitCode

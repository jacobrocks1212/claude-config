<#
.SYNOPSIS
  Pester v5 tests for build-queue.ps1 — the machine-global FIFO build wrapper
  (docs/bugs/build-queue-orphaned-result-on-wrapper-kill, WU-2).

.DESCRIPTION
  The regression test for the bug itself: with the fix, the wrapper's Step 4
  launches build-queue-runner.ps1 as a distinct detached process (not the
  filtered script directly), so stopping the WRAPPER mid-build no longer
  strands the result — the runner survives and completes Step 5 on its own.

  Each test runs against an ISOLATED state root: $env:USERPROFILE is
  overridden (build-queue.ps1 derives $stateRoot from $HOME, which PowerShell
  populates from USERPROFILE at process start) to a fresh $TestDrive
  subdirectory for the duration of the child process launch only, so the real
  ~/.claude/state/build-queue/ is never read or written. This mirrors the
  orchestrator's original WU-2 repro ("isolated temp $HOME so the real queue
  was never touched").

  No repo in this tree registers a build-queue-ops.json manifest, so -Op
  msbuild + an explicit -Exec resolves via the legacy (pre-manifest) branch —
  byte-compatible op resolution, no manifest dependency.
#>

BeforeAll {
	$script:WrapperPath = Join-Path $PSScriptRoot 'build-queue.ps1'
	$script:StatusPath  = Join-Path $PSScriptRoot 'build-queue-status.ps1'

	function Get-SafeValue {
		param([scriptblock]$Block, $Fallback = $null)
		try { & $Block } catch { $Fallback }
	}

	function New-IsolatedRoot {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $root -Force
		return $root
	}

	function Get-QueueStateRoot {
		param([string]$IsolatedRoot)
		return Join-Path $IsolatedRoot '.claude\state\build-queue'
	}

	function New-StubExec {
		param([string]$Path, [int]$SleepSeconds = 2, [int]$ExitCode = 0)
		# -Op msbuild resolves to OpKind 'build' (build-queue-generalization's
		# legacy-fallback kind inference), so the runner captures this exec's
		# stdout as a "build log" and forces a failure when that log is empty
		# (Test-BuildProducedNoOutput — a separate, legitimate fidelity check,
		# not something this bug's regression coverage should trip). Emit a
		# real output line (>40 chars, the near-empty threshold) so a
		# genuine exit-0 stub is never reclassified to failed.
		$lines = @(
			"Write-Output 'stub build: simulated output for Pester regression coverage.'",
			"Start-Sleep -Seconds $SleepSeconds",
			"exit $ExitCode"
		)
		Set-Content -Path $Path -Value $lines -Encoding UTF8
	}

	function Read-FileShared {
		# [System.IO.File]::ReadAllText() opens with a share mode that can
		# collide with a still-open writer handle (the wrapper's own
		# -RedirectStandardOutput/-RedirectStandardError file stays open for
		# the child process's whole lifetime) - the same reason
		# build-queue.ps1's own tail loop opens its log files with explicit
		# FileShare.ReadWrite instead of ReadAllText. Mirror that here for any
		# file we poll while the wrapper may still be writing it.
		param([string]$Path)
		if (-not (Test-Path $Path)) { return '' }
		$fs = $null
		try {
			$fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
			$sr = New-Object System.IO.StreamReader($fs)
			return $sr.ReadToEnd()
		} catch {
			return ''
		} finally {
			if ($null -ne $fs) { $fs.Dispose() }
		}
	}

	function Start-BuildQueueWrapper {
		param(
			[string]$IsolatedRoot,
			[string]$Exec,
			[string]$Op = 'msbuild',
			[string]$OutLog,
			[string]$ErrLog
		)
		$originalProfile = $env:USERPROFILE
		try {
			# Overridden only for the instant Start-Process snapshots the
			# environment block to hand to the child — restored immediately
			# after in the finally, regardless of outcome.
			$env:USERPROFILE = $IsolatedRoot
			$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$script:WrapperPath`" -Op $Op -Exec `"$Exec`""
			$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argString `
				-WindowStyle Hidden -PassThru `
				-RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
			$null = $proc.Handle
			return $proc
		} finally {
			$env:USERPROFILE = $originalProfile
		}
	}

	function Get-SeqFromWrapperOutput {
		param([string]$Path, [int]$TimeoutSeconds = 10)
		$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
		while ((Get-Date) -lt $deadline) {
			$text = Get-SafeValue { Read-FileShared -Path $Path } ''
			if ($text -match 'enqueued as seq=(\d+)') { return [int]$Matches[1] }
			Start-Sleep -Milliseconds 100
		}
		return $null
	}

	function Wait-ForDistinctRunnerPid {
		param([string]$StateRoot, [int]$WrapperPid, [int]$TimeoutSeconds = 20)
		$lockPath = Join-Path $StateRoot 'active.lock'
		$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
		while ((Get-Date) -lt $deadline) {
			if (Test-Path $lockPath) {
				$data = Get-SafeValue { [System.IO.File]::ReadAllText($lockPath) | ConvertFrom-Json } $null
				if ($null -ne $data) {
					$bp = Get-SafeValue { [int]$data.build_pid } 0
					if ($bp -gt 0 -and $bp -ne $WrapperPid) { return $bp }
				}
			}
			Start-Sleep -Milliseconds 150
		}
		return $null
	}

	function Wait-ForPath {
		param([string]$Path, [int]$TimeoutSeconds = 20)
		$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
		while ((Get-Date) -lt $deadline) {
			if (Test-Path $Path) { return $true }
			Start-Sleep -Milliseconds 150
		}
		return (Test-Path $Path)
	}

	function Wait-ForAbsence {
		# The runner writes results/<seq>.json a few lines BEFORE its
		# active.lock removal (stats-ring append in between) - both steps are
		# fast but not atomic with each other, so a bare single check racing
		# right after the result file appears can observe the lock a beat
		# early under load. Poll for absence instead of a one-shot check.
		param([string]$Path, [int]$TimeoutSeconds = 10)
		$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
		while ((Get-Date) -lt $deadline) {
			if (-not (Test-Path $Path)) { return $true }
			Start-Sleep -Milliseconds 150
		}
		return (-not (Test-Path $Path))
	}
}

Describe 'build-queue.ps1 — orphaned-result-on-wrapper-kill regression (the bug fix)' {

	It 'the detached runner records the result and releases the lock even after the wrapper is stopped mid-build' {
		$root = New-IsolatedRoot
		$stateRoot = Get-QueueStateRoot -IsolatedRoot $root
		$stub = Join-Path $root 'stub-orphan.ps1'
		New-StubExec -Path $stub -SleepSeconds 6 -ExitCode 1
		$outLog = Join-Path $root 'wrapper.out.log'
		$errLog = Join-Path $root 'wrapper.err.log'

		$wrapper = Start-BuildQueueWrapper -IsolatedRoot $root -Exec $stub -Op 'msbuild' -OutLog $outLog -ErrLog $errLog
		$runnerPid = $null
		try {
			$seq = Get-SeqFromWrapperOutput -Path $outLog
			$seq | Should -Not -BeNullOrEmpty

			$runnerPid = Wait-ForDistinctRunnerPid -StateRoot $stateRoot -WrapperPid $wrapper.Id
			$runnerPid | Should -Not -BeNullOrEmpty

			# Kill the WRAPPER ONLY — this is the bug's exact trigger (Bash
			# 2-min timeout -> exit 143, or any crash). The detached runner
			# is a distinct process and must keep running.
			Stop-Process -Id $wrapper.Id -Force -ErrorAction SilentlyContinue
			Start-Sleep -Milliseconds 400
			(Get-Process -Id $wrapper.Id -ErrorAction SilentlyContinue) | Should -BeNullOrEmpty

			$resultPath = Join-Path $stateRoot "results\$seq.json"
			(Wait-ForPath -Path $resultPath -TimeoutSeconds 20) | Should -Be $true

			$result = Get-Content -Raw -Path $resultPath | ConvertFrom-Json
			$result.seq | Should -Be $seq
			$result.exit_code | Should -Be 1

			# No orphaned slot lingering for the next waiter.
			(Wait-ForAbsence -Path (Join-Path $stateRoot 'active.lock')) | Should -Be $true

			$statusOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:StatusPath -StateRoot $stateRoot
			($statusOutput -join "`n") | Should -Match 'queue idle'
		} finally {
			Get-SafeValue { Stop-Process -Id $wrapper.Id -Force -ErrorAction SilentlyContinue }
			if ($null -ne $runnerPid) {
				Get-SafeValue { Stop-Process -Id $runnerPid -Force -ErrorAction SilentlyContinue }
			}
		}
	}
}

Describe 'build-queue.ps1 — happy path (regression: demoted Step 5 does not double-act)' {

	It 'wrapper survives to completion with exactly one seq-named result file, released lock, and matching exit code' {
		foreach ($exitCode in 0, 1) {
			$root = New-IsolatedRoot
			$stateRoot = Get-QueueStateRoot -IsolatedRoot $root
			$stub = Join-Path $root "stub-happy-$exitCode.ps1"
			New-StubExec -Path $stub -SleepSeconds 2 -ExitCode $exitCode
			$outLog = Join-Path $root 'wrapper.out.log'
			$errLog = Join-Path $root 'wrapper.err.log'

			$wrapper = Start-BuildQueueWrapper -IsolatedRoot $root -Exec $stub -Op 'msbuild' -OutLog $outLog -ErrLog $errLog
			try {
				$exited = $wrapper.WaitForExit(30000)
				$exited | Should -Be $true
				$wrapper.ExitCode | Should -Be $exitCode

				$seq = Get-SeqFromWrapperOutput -Path $outLog -TimeoutSeconds 5
				$seq | Should -Not -BeNullOrEmpty

				$resultsDir = Join-Path $stateRoot 'results'
				$resultFiles = @(Get-ChildItem -Path $resultsDir -Filter "$seq.json" -ErrorAction SilentlyContinue)
				$resultFiles.Count | Should -Be 1

				$result = Get-Content -Raw -Path $resultFiles[0].FullName | ConvertFrom-Json
				$result.seq | Should -Be $seq
				$result.exit_code | Should -Be $exitCode

				(Wait-ForAbsence -Path (Join-Path $stateRoot 'active.lock') -TimeoutSeconds 5) | Should -Be $true
			} finally {
				Get-SafeValue { if (-not $wrapper.HasExited) { Stop-Process -Id $wrapper.Id -Force -ErrorAction SilentlyContinue } }
			}
		}
	}
}

Describe 'build-queue.ps1 — status shortcut / op presence (build-queue-harness-diagnostic-gaps Defect 3)' {

	It 'no -Op and no -Status fails fast with an actionable error naming -Status and no enqueue' {
		$root = New-IsolatedRoot
		$stateRoot = Get-QueueStateRoot -IsolatedRoot $root
		$outLog = Join-Path $root 'out.log'
		$errLog = Join-Path $root 'err.log'
		$originalProfile = $env:USERPROFILE
		try {
			$env:USERPROFILE = $root
			$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$script:WrapperPath`""
			$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argString `
				-WindowStyle Hidden -PassThru -Wait `
				-RedirectStandardOutput $outLog -RedirectStandardError $errLog
		} finally {
			$env:USERPROFILE = $originalProfile
		}
		$proc.ExitCode | Should -Be 1
		$err = Get-Content -Raw -Path $errLog
		$err | Should -Match '-Op is required'
		$err | Should -Match '-Status'
		# Side-effect-free: no ticket/seq was allocated.
		(Test-Path (Join-Path $stateRoot 'tickets')) -and @(Get-ChildItem -Path (Join-Path $stateRoot 'tickets') -ErrorAction SilentlyContinue).Count -gt 0 | Should -Be $false
	}

	It '-Status delegates to build-queue-status.ps1 and returns without enqueuing' {
		$root = New-IsolatedRoot
		$stateRoot = Get-QueueStateRoot -IsolatedRoot $root
		$outLog = Join-Path $root 'out.log'
		$errLog = Join-Path $root 'err.log'
		$originalProfile = $env:USERPROFILE
		try {
			$env:USERPROFILE = $root
			$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$script:WrapperPath`" -Status"
			$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argString `
				-WindowStyle Hidden -PassThru -Wait `
				-RedirectStandardOutput $outLog -RedirectStandardError $errLog
		} finally {
			$env:USERPROFILE = $originalProfile
		}
		# The status reader exits 0 on an idle/empty queue; the key contract is
		# that -Status enqueues nothing (no tickets dir populated).
		$proc.ExitCode | Should -Be 0
		(Test-Path (Join-Path $stateRoot 'tickets')) -and @(Get-ChildItem -Path (Join-Path $stateRoot 'tickets') -ErrorAction SilentlyContinue).Count -gt 0 | Should -Be $false
	}
}

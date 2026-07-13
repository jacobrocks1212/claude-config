<#
.SYNOPSIS
  Pester v5 tests for build-queue-runner.ps1 — the self-releasing detached
  build runner (docs/bugs/build-queue-orphaned-result-on-wrapper-kill, WU-1).

.DESCRIPTION
  Standalone repro of the runner in isolation, per PHASES.md Phase 1's Repro
  gate: given a stub -Exec and a seeded -StateRoot, the runner (1) records the
  real exit code into results/<seq>.json even though the stub's own `exit N`
  runs inside a NESTED powershell.exe grandchild (the nested-exit invariant —
  the stub's exit must not abort the runner's own bookkeeping), (2) releases
  active.lock ONLY when its .seq matches -Seq (never a successor's lock), and
  (3) is idempotent across repeated invocations for the same seq.

  The runner itself ends with `exit $exitCode`, so every invocation here goes
  through a REAL nested powershell.exe child (never `& $RunnerPath` in-process,
  which would terminate the Pester host — the same gotcha PHASES.md documents
  for the runner's own internal invocation of the filtered script).

  Fixtures live under Pester's $TestDrive exclusively — the real
  ~/.claude/state/build-queue/ is never touched.
#>

BeforeAll {
	$script:RunnerPath = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
	$script:HygienePath = Join-Path $PSScriptRoot 'build-queue-hygiene.ps1'
	. $script:HygienePath

	function Get-SafeValue {
		param([scriptblock]$Block, $Fallback = $null)
		try { & $Block } catch { $Fallback }
	}

	function Invoke-DelayedBuildLogClassify {
		<#
		.SYNOPSIS
		  Mirrors runner.ps1's build-log classify block (Read-WithRetry feeding
		  Test-BuildProducedNoOutput) against a log file whose content lands on a
		  REAL background thread after -DelayMs milliseconds -- independent of
		  Start-Process/-Exec, since the SPEC (build-queue-nxbuild-false-no-output-fail)
		  found the actual Start-Process-redirect race unreproducible on this
		  machine even with a real node child. This exercises the retry-window
		  ARITHMETIC the fix widens, using the runner's REAL Read-WithRetry /
		  Test-BuildProducedNoOutput functions (dot-sourced from hygiene.ps1, not
		  reimplemented).
		#>
		param(
			[Parameter(Mandatory = $true)][string]$LogPath,
			[Parameter(Mandatory = $true)][int]$ArrivalDelayMs,
			[Parameter(Mandatory = $true)][int]$MaxAttempts,
			[Parameter(Mandatory = $true)][int]$DelayMs,
			[string]$Content = 'NX Successfully ran target build for project cognito-spa and 4 tasks it depends on'
		)

		$ps = [powershell]::Create()
		$null = $ps.AddScript({
			param($path, $delayMs, $content)
			Start-Sleep -Milliseconds $delayMs
			[System.IO.File]::WriteAllText($path, $content)
		}).AddArgument($LogPath).AddArgument($ArrivalDelayMs).AddArgument($Content)
		$handle = $ps.BeginInvoke()

		try {
			$logText = Read-WithRetry -MaxAttempts $MaxAttempts -DelayMs $DelayMs -Parse {
				if (-not (Test-Path $LogPath)) { return $null }
				$t = Get-SafeValue { [System.IO.File]::ReadAllText($LogPath) } $null
				if ([string]::IsNullOrEmpty($t)) { return $null }
				$t
			} -Fallback $null

			return Test-BuildProducedNoOutput -LogText $logText
		} finally {
			$null = $ps.EndInvoke($handle)
			$ps.Dispose()
		}
	}

	function New-FixtureStateRoot {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'results') -Force
		return $root
	}

	function Write-FixtureActiveLock {
		param([string]$StateRoot, [int]$Seq)
		$path = Join-Path $StateRoot 'active.lock'
		$body = [ordered]@{
			seq          = $Seq
			build_pid    = 999999
			op           = 'msbuild'
			worktree     = 'C:\fake-worktree'
			started_at   = (Get-Date).ToString('o')
			log_path     = $null
			machine_perf = $null
		} | ConvertTo-Json -Compress
		[System.IO.File]::WriteAllText($path, $body)
		return $path
	}

	function New-StubExec {
		param([string]$Path, [int]$SleepSeconds = 1, [int]$ExitCode = 0)
		$lines = @(
			"Start-Sleep -Seconds $SleepSeconds",
			"exit $ExitCode"
		)
		Set-Content -Path $Path -Value $lines -Encoding UTF8
	}

	function Invoke-Runner {
		param([string]$Exec, [int]$Seq, [string]$StateRoot)
		$null = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:RunnerPath `
			-Exec $Exec -Seq $Seq -StateRoot $StateRoot 2>$null
		return $LASTEXITCODE
	}
}

Describe 'build-queue-runner.ps1 — self-releasing result + lock bookkeeping (WU-1 repro)' {

	It 'records the real exit code, writes the seq-named result file, and releases the matching-seq active.lock' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureActiveLock -StateRoot $root -Seq 42
		$stub = Join-Path $root 'stub-match.ps1'
		New-StubExec -Path $stub -SleepSeconds 1 -ExitCode 7

		$runnerExit = Invoke-Runner -Exec $stub -Seq 42 -StateRoot $root

		# Nested-exit invariant: the stub's own `exit 7` (inside the nested
		# grandchild) must NOT have aborted the runner's bookkeeping below.
		$runnerExit | Should -Be 7

		$resultPath = Join-Path $root 'results\42.json'
		Test-Path $resultPath | Should -Be $true
		$result = Get-Content -Raw -Path $resultPath | ConvertFrom-Json
		$result.seq | Should -Be 42
		$result.exit_code | Should -Be 7

		Test-Path (Join-Path $root 'active.lock') | Should -Be $false
	}

	It 'exits with the exec exit code and writes the result even for a passing (exit 0) build' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureActiveLock -StateRoot $root -Seq 5
		$stub = Join-Path $root 'stub-pass.ps1'
		New-StubExec -Path $stub -SleepSeconds 1 -ExitCode 0

		$runnerExit = Invoke-Runner -Exec $stub -Seq 5 -StateRoot $root

		$runnerExit | Should -Be 0
		$result = Get-Content -Raw -Path (Join-Path $root 'results\5.json') | ConvertFrom-Json
		$result.exit_code | Should -Be 0
		Test-Path (Join-Path $root 'active.lock') | Should -Be $false
	}
}

Describe 'build-queue-runner.ps1 — seq-scoped lock release never touches a successor' {

	It 'leaves a mismatched active.lock untouched while still writing its own result' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureActiveLock -StateRoot $root -Seq 99
		$stub = Join-Path $root 'stub-guard.ps1'
		New-StubExec -Path $stub -SleepSeconds 1 -ExitCode 3

		$runnerExit = Invoke-Runner -Exec $stub -Seq 42 -StateRoot $root

		$runnerExit | Should -Be 3

		$lockPath = Join-Path $root 'active.lock'
		Test-Path $lockPath | Should -Be $true
		$lock = Get-Content -Raw -Path $lockPath | ConvertFrom-Json
		$lock.seq | Should -Be 99

		$result = Get-Content -Raw -Path (Join-Path $root 'results\42.json') | ConvertFrom-Json
		$result.seq | Should -Be 42
		$result.exit_code | Should -Be 3
	}
}

Describe 'build-queue-runner.ps1 — idempotent result write' {

	It 'produces stable seq/exit_code content across repeated invocations for the same seq' {
		$root = New-FixtureStateRoot
		$stub = Join-Path $root 'stub-idempotent.ps1'
		New-StubExec -Path $stub -SleepSeconds 1 -ExitCode 5

		$firstExit = Invoke-Runner -Exec $stub -Seq 10 -StateRoot $root
		$resultPath = Join-Path $root 'results\10.json'
		$first = Get-Content -Raw -Path $resultPath | ConvertFrom-Json

		$secondExit = Invoke-Runner -Exec $stub -Seq 10 -StateRoot $root
		$second = Get-Content -Raw -Path $resultPath | ConvertFrom-Json

		$firstExit | Should -Be 5
		$secondExit | Should -Be 5
		$first.seq | Should -Be $second.seq
		$first.exit_code | Should -Be $second.exit_code
		$second.seq | Should -Be 10
		$second.exit_code | Should -Be 5
	}
}

Describe 'build-queue-runner.ps1 — widened build-log classify retry window (build-queue-nxbuild-false-no-output-fail)' {
	# RED/GREEN pair: a build log whose content lands on a background thread at
	# ~150ms elapsed -- past the OLD 3x/50ms (~100ms) settle budget, but well
	# inside the NEW 10x/100ms (~1s) budget the runner's classify call site now
	# passes. Uses the REAL Read-WithRetry / Test-BuildProducedNoOutput functions
	# (via Invoke-DelayedBuildLogClassify above) — never reimplemented.

	It 'RED: under the OLD 100ms budget, a log landing at 150ms is misclassified no-output' {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $root -Force
		$logPath = Join-Path $root 'seq-old.build.log'

		$noOutput = Invoke-DelayedBuildLogClassify -LogPath $logPath -ArrivalDelayMs 150 -MaxAttempts 3 -DelayMs 50

		# This IS the bug: a genuinely-successful build (real content landed at
		# 150ms) gets force-failed as no-output because the old budget gave up too
		# soon.
		$noOutput | Should -BeTrue
	}

	It 'GREEN: under the NEW widened budget, the SAME 150ms-delayed log classifies as produced-output' {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $root -Force
		$logPath = Join-Path $root 'seq-new.build.log'

		$noOutput = Invoke-DelayedBuildLogClassify -LogPath $logPath -ArrivalDelayMs 150 -MaxAttempts 10 -DelayMs 100

		$noOutput | Should -BeFalse
	}

	It 'GREEN: a log that never arrives still classifies no-output (genuine failure is not masked)' {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $root -Force
		$logPath = Join-Path $root 'seq-never.build.log'

		# ArrivalDelayMs far beyond the widened budget's ~1s ceiling -- the widened
		# window absorbs a transient flush lag, it does not mask a build that truly
		# produced nothing.
		$noOutput = Invoke-DelayedBuildLogClassify -LogPath $logPath -ArrivalDelayMs 5000 -MaxAttempts 10 -DelayMs 100

		$noOutput | Should -BeTrue
	}

	It 'source pin: the runner''s build-log classify call site passes the widened -MaxAttempts/-DelayMs' {
		$source = Get-Content -Raw -Path $script:RunnerPath
		$source | Should -Match 'Read-WithRetry -MaxAttempts 10 -DelayMs 100 -Parse \{'
	}

	It 'source pin: the test-counts and active.lock Read-WithRetry call sites stay at the ORIGINAL default (unwidened)' {
		$source = Get-Content -Raw -Path $script:RunnerPath
		# Both remaining call sites in the runner take no -MaxAttempts/-DelayMs
		# override (i.e. they still use Read-WithRetry's own 3x/50ms default) --
		# the widening is scoped to the build-log no-output classify path only.
		$countsCallSite = [regex]::Match($source, '\$counts = Read-WithRetry -Parse \{')
		$countsCallSite.Success | Should -BeTrue

		$lockCallSite = [regex]::Match($source, '\$lockSeq = Read-WithRetry -Parse \{')
		$lockCallSite.Success | Should -BeTrue
	}
}

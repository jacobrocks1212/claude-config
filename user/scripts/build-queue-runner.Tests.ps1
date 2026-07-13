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

	function Get-SafeValue {
		param([scriptblock]$Block, $Fallback = $null)
		try { & $Block } catch { $Fallback }
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

<#
.SYNOPSIS
  Pester v5 regression tests for the foreground early-return + test-op poison-
  sweep gate — docs/bugs/build-queue-foreground-wait-blocks-past-terminal-outcome.

.DESCRIPTION
  Proves the ORIGINAL symptom is gone on the serving path:

  1. Wait-ForRecordedOutcome (the extracted foreground wait/outcome logic the
     wrapper build-queue.ps1 now calls) returns PROMPTLY the moment a terminal
     results/<seq>.json is recorded — it does NOT block on full runner-process
     liveness (the process-liveness probe is never even consulted, and it never
     sleeps), and it re-emits the correct authoritative banner as its result,
     for the no-output (exit 3), zero-match (exit 5), and a normal pass case.
     This is the inverse of the old `while (-not $proc.HasExited)` gate that
     stalled the agent's foreground Bash through post-outcome hygiene.

  2. Test-ShouldSweepPoisonedArtifacts (the extracted runner poison-sweep gate)
     does NOT fire for a zero-result TEST op (exit 3/5) and STILL fires for a
     genuinely-failed BUILD op.

  All fixtures live under Pester's $TestDrive; the real
  ~/.claude/state/build-queue/ is never touched.
#>

BeforeAll {
	$script:HygienePath = Join-Path $PSScriptRoot 'build-queue-hygiene.ps1'
	. $script:HygienePath

	function Write-FixtureResult {
		param([string]$ResultPath, [hashtable]$Body)
		$dir = Split-Path -Parent $ResultPath
		if (-not (Test-Path $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
		[System.IO.File]::WriteAllText($ResultPath, ($Body | ConvertTo-Json -Compress -Depth 5))
		return $ResultPath
	}

	function New-FixtureResultPath {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		return (Join-Path (Join-Path $root 'results') '7.json')
	}
}

Describe 'Wait-ForRecordedOutcome — returns promptly on a recorded terminal outcome' {

	It 'returns result-recorded WITHOUT consulting process-liveness or sleeping when the result is already present' {
		$path = New-FixtureResultPath
		$null = Write-FixtureResult -ResultPath $path -Body ([ordered]@{
			seq       = 7
			exit_code = 0
			op        = 'mstest'
			counts    = [ordered]@{ passed = 3; failed = 0; total = 3 }
			hygiene   = [ordered]@{ result_fidelity = 'verified'; build_fidelity = 'n/a' }
		})

		# A process-liveness probe that would report "still alive" forever, and a
		# sleep that records every call. The OLD wrapper (while -not HasExited)
		# would spin here; the new helper must return on the recorded result
		# WITHOUT ever consulting liveness or sleeping.
		$script:aliveCalls = 0
		$script:sleepCalls = 0
		$aliveProbe = { $script:aliveCalls++; $true }
		$sleepProbe = { param($ms) $script:sleepCalls++ }

		$outcome = Wait-ForRecordedOutcome -ResultPath $path `
			-IsProcessAlive $aliveProbe -Sleep $sleepProbe -PollIntervalMs 1

		$outcome.Outcome  | Should -BeExactly 'result-recorded'
		$outcome.ExitCode | Should -Be 0
		$script:aliveCalls | Should -Be 0
		$script:sleepCalls | Should -Be 0
	}

	It 're-emits the PASS banner for a recorded green test run' {
		$path = New-FixtureResultPath
		$null = Write-FixtureResult -ResultPath $path -Body ([ordered]@{
			seq       = 7
			exit_code = 0
			op        = 'mstest'
			counts    = [ordered]@{ passed = 10; failed = 0; total = 10 }
			hygiene   = [ordered]@{ result_fidelity = 'verified'; build_fidelity = 'n/a' }
		})

		$outcome = Wait-ForRecordedOutcome -ResultPath $path -IsProcessAlive { $true }
		$outcome.Outcome | Should -BeExactly 'result-recorded'

		$banner = Format-BuildQueueBanner -Seq 7 -Op 'mstest' -ExitCode ([int]$outcome.ExitCode) `
			-ResultFidelity $outcome.Result.hygiene.result_fidelity `
			-BuildFidelity $outcome.Result.hygiene.build_fidelity `
			-Counts @{ passed = 10; failed = 0; total = 10 }
		$banner | Should -Match 'RESULT=PASS'
		$outcome.ExitCode | Should -Be 0
	}

	It 're-emits the no-output (exit 3) FAIL-shaped banner for a zero-result test op' {
		$path = New-FixtureResultPath
		$null = Write-FixtureResult -ResultPath $path -Body ([ordered]@{
			seq       = 7
			exit_code = 3
			op        = 'mstest'
			counts    = $null
			hygiene   = [ordered]@{ result_fidelity = 'no-output'; build_fidelity = 'n/a' }
		})

		$outcome = Wait-ForRecordedOutcome -ResultPath $path -IsProcessAlive { $true }
		$outcome.Outcome  | Should -BeExactly 'result-recorded'
		$outcome.ExitCode | Should -Be 3

		$banner = Format-BuildQueueBanner -Seq 7 -Op 'mstest' -ExitCode 3 `
			-ResultFidelity 'no-output' -BuildFidelity 'n/a' -Counts $null
		$banner | Should -Match 'RESULT=FAIL'
		$banner | Should -Match 'result_fidelity=no-output'
	}

	It 're-emits the NO-TESTS-MATCHED (exit 5) banner for a zero-match filter' {
		$path = New-FixtureResultPath
		$null = Write-FixtureResult -ResultPath $path -Body ([ordered]@{
			seq       = 7
			exit_code = 5
			op        = 'mstest'
			counts    = [ordered]@{ passed = 0; failed = 0; total = 0 }
			hygiene   = [ordered]@{ result_fidelity = 'no-tests-matched'; build_fidelity = 'n/a' }
		})

		$outcome = Wait-ForRecordedOutcome -ResultPath $path -IsProcessAlive { $true }
		$outcome.Outcome  | Should -BeExactly 'result-recorded'
		$outcome.ExitCode | Should -Be 5

		$banner = Format-BuildQueueBanner -Seq 7 -Op 'mstest' -ExitCode 5 `
			-ResultFidelity 'no-tests-matched' -BuildFidelity 'n/a' `
			-Counts @{ passed = 0; failed = 0; total = 0 }
		$banner | Should -Match 'RESULT=NO-TESTS-MATCHED'
	}

	It 'awaits a deferred result and returns result-recorded once it lands (still-live runner)' {
		$path = New-FixtureResultPath
		$null = New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force

		# Runner "alive" for the first two polls, then the result appears.
		$script:polls = 0
		$aliveProbe = {
			$script:polls++
			if ($script:polls -eq 2) {
				[System.IO.File]::WriteAllText($path, '{"seq":7,"exit_code":0,"op":"nxbuild","hygiene":{"result_fidelity":"n/a","build_fidelity":"verified"}}')
			}
			$true
		}

		$outcome = Wait-ForRecordedOutcome -ResultPath $path `
			-IsProcessAlive $aliveProbe -Sleep { param($ms) } -PollIntervalMs 1
		$outcome.Outcome  | Should -BeExactly 'result-recorded'
		$outcome.ExitCode | Should -Be 0
	}
}

Describe 'Wait-ForRecordedOutcome — fallback when the runner dies without a readable result' {

	It 'returns process-exited when the process is gone and no result was recorded' {
		$path = New-FixtureResultPath
		$null = New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force

		$outcome = Wait-ForRecordedOutcome -ResultPath $path -IsProcessAlive { $false }
		$outcome.Outcome  | Should -BeExactly 'process-exited'
		$outcome.ExitCode | Should -Be $null
	}

	It 'treats a null exit_code (degraded exception write) as NOT ready and falls back to process-exited' {
		$path = New-FixtureResultPath
		$null = Write-FixtureResult -ResultPath $path -Body ([ordered]@{
			seq       = 7
			exit_code = $null
			ended_at  = '2026-07-13T00:00:00.0000000Z'
		})

		$outcome = Wait-ForRecordedOutcome -ResultPath $path -IsProcessAlive { $false }
		$outcome.Outcome | Should -BeExactly 'process-exited'
	}
}

Describe 'Test-ShouldSweepPoisonedArtifacts — build-op-only gate' {

	It 'does NOT sweep for a zero-result test op (exit 3 no-output)' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $false -ExitCode 3 -PoisonSweep 'dotnet-dll' -Worktree 'C:\wt' | Should -Be $false
	}

	It 'does NOT sweep for a zero-match test op (exit 5)' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $false -ExitCode 5 -PoisonSweep 'dotnet-dll' -Worktree 'C:\wt' | Should -Be $false
	}

	It 'DOES sweep for a genuinely-failed build op (exit 1)' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $true -ExitCode 1 -PoisonSweep 'dotnet-dll' -Worktree 'C:\wt' | Should -Be $true
	}

	It 'DOES sweep for a no-output build op forced to exit 1' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $true -ExitCode 1 -PoisonSweep 'dotnet-dll' -Worktree 'C:\wt' | Should -Be $true
	}

	It 'does NOT sweep for a green build op (exit 0)' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $true -ExitCode 0 -PoisonSweep 'dotnet-dll' -Worktree 'C:\wt' | Should -Be $false
	}

	It 'does NOT sweep for a green test op (exit 0)' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $false -ExitCode 0 -PoisonSweep 'dotnet-dll' -Worktree 'C:\wt' | Should -Be $false
	}

	It 'does NOT sweep when the profile poison_sweep is not dotnet-dll' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $true -ExitCode 1 -PoisonSweep 'none' -Worktree 'C:\wt' | Should -Be $false
	}

	It 'does NOT sweep when there is no worktree' {
		Test-ShouldSweepPoisonedArtifacts -IsBuildOp $true -ExitCode 1 -PoisonSweep 'dotnet-dll' -Worktree '' | Should -Be $false
	}
}

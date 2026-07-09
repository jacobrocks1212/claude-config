<#
.SYNOPSIS
  Pester v5 tests for build-queue-await.ps1 — the followable-wait primitive.

.DESCRIPTION
  Verifies the one runtime-coupled assumption of
  docs/bugs/subagent-backgrounds-verification-ends-turn-before-green:
  reading a real fixture results/<seq>.json and calling the REAL
  Format-BuildQueueBanner reproduces the same authoritative banner the
  wrapper prints, as the LAST stdout line, with the process exit code
  mirroring the fixture's exit_code. Also covers: the distinct await-timeout
  exit (result not yet present), defensive reads (missing op/counts/hygiene),
  and genuine blocking-until-present (a deferred results write is awaited,
  not treated as absent).

  Fixtures live under Pester's $TestDrive exclusively — the real
  ~/.claude/state/build-queue/ is never touched.
#>

BeforeAll {
	$script:AwaitPath   = Join-Path $PSScriptRoot 'build-queue-await.ps1'
	$script:HygienePath = Join-Path $PSScriptRoot 'build-queue-hygiene.ps1'

	# Real banner composer, for parity assertions against the helper's output.
	. $script:HygienePath

	function New-FixtureStateRoot {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'results') -Force
		return $root
	}

	function Write-FixtureResult {
		param([string]$StateRoot, [int]$Seq, [hashtable]$Body)
		$path = Join-Path (Join-Path $StateRoot 'results') "$Seq.json"
		[System.IO.File]::WriteAllText($path, ($Body | ConvertTo-Json -Compress -Depth 5))
		return $path
	}

	function Invoke-Await {
		param(
			[int]$Seq,
			[string]$StateRoot,
			[int]$TimeoutSeconds = 0,
			[int]$PollIntervalMs = 50
		)
		$lines = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:AwaitPath `
			-Seq $Seq -StateRoot $StateRoot -TimeoutSeconds $TimeoutSeconds -PollIntervalMs $PollIntervalMs 2>$null)
		return [pscustomobject]@{
			Lines    = $lines
			LastLine = if ($lines.Count -gt 0) { $lines[-1] } else { $null }
			ExitCode = $LASTEXITCODE
		}
	}
}

Describe 'build-queue-await.ps1 — banner parity with Format-BuildQueueBanner' {

	It 're-emits the PASS banner for a green test run and exits 0' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureResult -StateRoot $root -Seq 41 -Body ([ordered]@{
			seq       = 41
			exit_code = 0
			op        = 'mstest'
			counts    = [ordered]@{ passed = 10; failed = 0; total = 10 }
			hygiene   = [ordered]@{ result_fidelity = 'verified'; build_fidelity = 'n/a' }
		})

		$expected = Format-BuildQueueBanner -Seq 41 -Op 'mstest' -ExitCode 0 `
			-ResultFidelity 'verified' -BuildFidelity 'n/a' `
			-Counts @{ passed = 10; failed = 0; total = 10 }

		$run = Invoke-Await -Seq 41 -StateRoot $root
		$run.LastLine | Should -BeExactly $expected
		$run.LastLine | Should -Match 'RESULT=PASS'
		$run.ExitCode | Should -Be 0
	}

	It 're-emits the FAIL banner for a red build and exits with the build exit code' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureResult -StateRoot $root -Seq 42 -Body ([ordered]@{
			seq       = 42
			exit_code = 1
			op        = 'msbuild'
			counts    = $null
			hygiene   = [ordered]@{ result_fidelity = 'n/a'; build_fidelity = 'verified' }
		})

		$expected = Format-BuildQueueBanner -Seq 42 -Op 'msbuild' -ExitCode 1 `
			-ResultFidelity 'n/a' -BuildFidelity 'verified' -Counts $null

		$run = Invoke-Await -Seq 42 -StateRoot $root
		$run.LastLine | Should -BeExactly $expected
		$run.LastLine | Should -Match 'RESULT=FAIL'
		$run.ExitCode | Should -Be 1
	}

	It 're-emits the NO-TESTS-MATCHED banner for a zero-match filter and exits 5' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureResult -StateRoot $root -Seq 43 -Body ([ordered]@{
			seq       = 43
			exit_code = 5
			op        = 'mstest'
			counts    = [ordered]@{ passed = 0; failed = 0; total = 0 }
			hygiene   = [ordered]@{ result_fidelity = 'no-tests-matched'; build_fidelity = 'n/a' }
		})

		$expected = Format-BuildQueueBanner -Seq 43 -Op 'mstest' -ExitCode 5 `
			-ResultFidelity 'no-tests-matched' -BuildFidelity 'n/a' `
			-Counts @{ passed = 0; failed = 0; total = 0 }

		$run = Invoke-Await -Seq 43 -StateRoot $root
		$run.LastLine | Should -BeExactly $expected
		$run.LastLine | Should -Match 'RESULT=NO-TESTS-MATCHED'
		$run.ExitCode | Should -Be 5
	}

	It 'forces FAIL on a log-failure-override build even with exit_code 0' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureResult -StateRoot $root -Seq 44 -Body ([ordered]@{
			seq       = 44
			exit_code = 0
			op        = 'msbuild'
			hygiene   = [ordered]@{ result_fidelity = 'n/a'; build_fidelity = 'log-failure-override' }
		})

		$run = Invoke-Await -Seq 44 -StateRoot $root
		$run.LastLine | Should -Match 'RESULT=FAIL'
		$run.ExitCode | Should -Be 0
	}
}

Describe 'build-queue-await.ps1 — defensive reads (today''s runner shape)' {

	It 'composes the banner when op/counts/hygiene are absent (current runner omits op)' {
		$root = New-FixtureStateRoot
		$null = Write-FixtureResult -StateRoot $root -Seq 45 -Body ([ordered]@{
			seq       = 45
			exit_code = 0
			ended_at  = '2026-07-09T00:00:00.0000000Z'
		})

		$expected = Format-BuildQueueBanner -Seq 45 -Op '' -ExitCode 0 `
			-ResultFidelity $null -BuildFidelity $null -Counts $null

		$run = Invoke-Await -Seq 45 -StateRoot $root
		$run.LastLine | Should -BeExactly $expected
		$run.ExitCode | Should -Be 0
	}
}

Describe 'build-queue-await.ps1 — await-timeout (result not yet present)' {

	It 'exits with the distinct timeout code and names the seq when no result appears' {
		$root = New-FixtureStateRoot

		$run = Invoke-Await -Seq 99 -StateRoot $root -TimeoutSeconds 0
		$run.ExitCode | Should -Be 124
		($run.Lines -join "`n") | Should -Match 'result not yet present for seq=99'
	}

	It 'timeout exit code is distinct from every build exit code shape (0/1/4/5)' {
		124 | Should -Not -BeIn @(0, 1, 3, 4, 5)
	}
}

Describe 'build-queue-await.ps1 — genuinely blocks until the result appears' {

	It 'awaits a deferred results write and then emits the banner (backgrounded-build serving path)' {
		$root = New-FixtureStateRoot
		$resultsDir = Join-Path $root 'results'

		# Simulate the detached runner finishing AFTER the await starts.
		$writer = Start-Job -ScriptBlock {
			param($Dir)
			Start-Sleep -Milliseconds 900
			$body = '{"seq":46,"exit_code":0,"op":"nxbuild","hygiene":{"result_fidelity":"n/a","build_fidelity":"verified"}}'
			[System.IO.File]::WriteAllText((Join-Path $Dir '46.json'), $body)
		} -ArgumentList $resultsDir

		try {
			$run = Invoke-Await -Seq 46 -StateRoot $root -TimeoutSeconds 15 -PollIntervalMs 100

			$expected = Format-BuildQueueBanner -Seq 46 -Op 'nxbuild' -ExitCode 0 `
				-ResultFidelity 'n/a' -BuildFidelity 'verified' -Counts $null

			$run.LastLine | Should -BeExactly $expected
			$run.ExitCode | Should -Be 0
		} finally {
			$null = Get-SafeValue { Remove-Job -Job $writer -Force }
		}
	}
}

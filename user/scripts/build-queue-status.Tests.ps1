<#
.SYNOPSIS
  Pester v5 tests for build-queue-status.ps1's hygiene-counts surfacing
  (docs/bugs/build-queue-outcome-opacity-and-inspect-deny, item 2a follow-up).

.DESCRIPTION
  build-queue-runner.ps1 has recorded a test op's Passed/Failed/Total counts
  into results/<seq>.json's hygiene.counts field since Phase 3 of this bug's
  fix, but build-queue-status.ps1's hygiene line never surfaced it -- an agent
  still had to `cat results/<seq>.json` to see pass/fail counts, exactly the
  inspection the outcome-legibility fix was meant to make unnecessary. These
  tests pin the new `counts(passed/failed/total)=` segment.

  Each test runs the REAL script (invoked out-of-process, mirroring
  build-queue.Tests.ps1's convention for this same script) against an
  isolated, fabricated $StateRoot -- no active.lock, no tickets, a single
  hand-written results/<seq>.json. Mutates nothing outside $TestDrive.
#>

BeforeAll {
	$script:StatusPath = Join-Path $PSScriptRoot 'build-queue-status.ps1'

	function New-IsolatedStateRoot {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'results') -Force
		return $root
	}

	function Write-FakeResult {
		param(
			[string]$StateRoot,
			[int]$Seq = 1,
			[hashtable]$Hygiene = $null
		)
		$resultPath = Join-Path $StateRoot "results\$Seq.json"
		$obj = @{ seq = $Seq; exit_code = 0; ended_at = '2026-07-12T00:00:00Z' }
		if ($null -ne $Hygiene) { $obj.hygiene = $Hygiene }
		($obj | ConvertTo-Json -Depth 6) | Set-Content -Path $resultPath -Encoding UTF8
	}

	function Invoke-BuildQueueStatus {
		param([string]$StateRoot)
		& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:StatusPath -StateRoot $StateRoot
	}
}

Describe 'build-queue-status.ps1 -- hygiene counts surfacing' {

	It 'renders passed/failed/total when hygiene.counts is present (test op)' {
		$root = New-IsolatedStateRoot
		Write-FakeResult -StateRoot $root -Seq 42 -Hygiene @{
			vbcscompiler_recycled = $false
			result_fidelity       = 'verified'
			build_fidelity        = 'n/a'
			counts                = @{ passed = 12; failed = 3; total = 15 }
		}

		$output = Invoke-BuildQueueStatus -StateRoot $root
		($output -join "`n") | Should -Match 'counts\(passed/failed/total\)=12/3/15'
	}

	It 'renders n/a when hygiene.counts is absent (build op)' {
		$root = New-IsolatedStateRoot
		Write-FakeResult -StateRoot $root -Seq 7 -Hygiene @{
			vbcscompiler_recycled = $true
			result_fidelity       = 'n/a'
			build_fidelity        = 'verified'
		}

		$output = Invoke-BuildQueueStatus -StateRoot $root
		($output -join "`n") | Should -Match 'counts\(passed/failed/total\)=n/a'
	}

	It 'renders n/a when hygiene.counts.total is null (malformed counts)' {
		$root = New-IsolatedStateRoot
		Write-FakeResult -StateRoot $root -Seq 9 -Hygiene @{
			vbcscompiler_recycled = $false
			result_fidelity       = 'no-tests-matched'
			build_fidelity        = 'n/a'
			counts                = @{ passed = $null; failed = $null; total = $null }
		}

		$output = Invoke-BuildQueueStatus -StateRoot $root
		($output -join "`n") | Should -Match 'counts\(passed/failed/total\)=n/a'
	}

	It 'still prints "hygiene: (not recorded)" and no counts segment when the result carries no hygiene block at all' {
		$root = New-IsolatedStateRoot
		Write-FakeResult -StateRoot $root -Seq 3 -Hygiene $null

		$output = Invoke-BuildQueueStatus -StateRoot $root
		$joined = $output -join "`n"
		$joined | Should -Match 'hygiene: \(not recorded\)'
		$joined | Should -Not -Match 'counts\('
	}

	It 'prints "queue idle" when there is no active build, no waiters, and no results at all' {
		$root = New-IsolatedStateRoot
		$output = Invoke-BuildQueueStatus -StateRoot $root
		($output -join "`n") | Should -Match 'queue idle'
	}
}

Describe 'build-queue-status.ps1 -- dead-holder unmasking (build-queue-harness-diagnostic-gaps Defect 4)' {

	It 'renders "Active Build (STALE)" with a DEAD marker when the holder pid is dead and no result was written' {
		$root = New-IsolatedStateRoot
		# A definitely-dead pid: spawn a process, wait for it to exit, reuse its id.
		$deadProc = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-Command', 'exit 0' -PassThru -WindowStyle Hidden
		$deadProc.WaitForExit()
		Start-Sleep -Milliseconds 200
		$lock = [ordered]@{ seq = 501; build_pid = $deadProc.Id; op = 'nxbuild'; worktree = 'C:\r'; started_at = (Get-Date).AddMinutes(-2).ToString('o'); log_path = 'x.log'; machine_perf = $null } | ConvertTo-Json -Compress
		[System.IO.File]::WriteAllText((Join-Path $root 'active.lock'), $lock)

		$joined = (Invoke-BuildQueueStatus -StateRoot $root) -join "`n"
		$joined | Should -Match 'Active Build \(STALE\)'
		$joined | Should -Match '\[DEAD - no result written\]'
		$joined | Should -Not -Match '=== Active Build ===[^(]'
	}

	It 'renders a normal "Active Build" (not STALE) when the holder pid is alive' {
		$root = New-IsolatedStateRoot
		# The test process itself is a guaranteed-alive holder pid.
		$lock = [ordered]@{ seq = 502; build_pid = $PID; op = 'nxbuild'; worktree = 'C:\r'; started_at = (Get-Date).ToString('o'); log_path = 'x.log'; machine_perf = $null } | ConvertTo-Json -Compress
		[System.IO.File]::WriteAllText((Join-Path $root 'active.lock'), $lock)

		$joined = (Invoke-BuildQueueStatus -StateRoot $root) -join "`n"
		$joined | Should -Match '=== Active Build ==='
		$joined | Should -Not -Match 'STALE'
	}

	It 'does NOT unmask as STALE when the dead holder DID write a result (build completed, lock not yet cleared)' {
		$root = New-IsolatedStateRoot
		Write-FakeResult -StateRoot $root -Seq 503 -Hygiene @{ result_fidelity = 'n/a'; build_fidelity = 'verified' }
		$deadProc = Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-Command', 'exit 0' -PassThru -WindowStyle Hidden
		$deadProc.WaitForExit()
		Start-Sleep -Milliseconds 200
		$lock = [ordered]@{ seq = 503; build_pid = $deadProc.Id; op = 'nxbuild'; worktree = 'C:\r'; started_at = (Get-Date).ToString('o'); log_path = 'x.log'; machine_perf = $null } | ConvertTo-Json -Compress
		[System.IO.File]::WriteAllText((Join-Path $root 'active.lock'), $lock)

		$joined = (Invoke-BuildQueueStatus -StateRoot $root) -join "`n"
		$joined | Should -Not -Match 'STALE'
	}
}

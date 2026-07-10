<#
.SYNOPSIS
  Pester v5 tests for build-queue-runner.ps1 — merged suite covering both the
  self-releasing detached runner (WU-1 repro,
  docs/bugs/build-queue-orphaned-result-on-wrapper-kill) AND the crash-safe
  two-phase result write (docs/bugs/build-queue-timeout-kill-reaps-detached-runner).

.DESCRIPTION
  Two complementary concern groups share this file:

  (1) Self-releasing result + lock bookkeeping (WU-1): given a stub -Exec and a
      seeded -StateRoot, the runner records the real exit code even though the
      stub's `exit N` runs inside a NESTED powershell.exe grandchild, releases
      active.lock ONLY when its .seq matches -Seq, is idempotent across repeated
      invocations, and honors the widened build-log classify retry window
      (build-queue-nxbuild-false-no-output-fail).

  (2) Crash-safe two-phase write: reproduces the incident serving path — a RED
      build whose runner is killed (TerminateProcess) mid-hygiene — asserting the
      EARLY result write already persisted the truthful outcome, active.lock is
      honestly left for the next enqueue's dead-tick reclaim, the final write
      merges real hygiene over the early write, and build-queue-await.ps1 returns
      the real RED outcome instead of a misleading exit 124. Also covers
      Write-BuildQueueResult unit behavior.

  Each concern group carries its own BeforeAll setup below (helper names are
  disjoint across the two; Get-SafeValue defined in the first is reused by the
  second). Fixtures live under Pester's $TestDrive exclusively — the real
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

BeforeAll {
	$script:ScriptsDir  = $PSScriptRoot
	$script:RunnerPath  = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
	$script:HygienePath = Join-Path $PSScriptRoot 'build-queue-hygiene.ps1'
	$script:AwaitPath   = Join-Path $PSScriptRoot 'build-queue-await.ps1'

	# Real module — for Format-BuildQueueBanner parity assertions and the
	# Write-BuildQueueResult unit tests.
	. $script:HygienePath

	$script:SpawnedPids = [System.Collections.ArrayList]::new()

	function New-RunnerSandbox {
		<#
		  Copies the real runner into a $TestDrive sandbox beside a shim
		  build-queue-hygiene.ps1 (the runner dot-sources by $PSScriptRoot, so
		  the shim is picked up). The shim loads the REAL module first, then
		  overrides the dangerous/slow ops. -SweepBehavior:
		    fast  -> Remove-PoisonedArtifacts returns one fake quarantined path
		    block -> Remove-PoisonedArtifacts sleeps 120s (kill window)
		#>
		param([ValidateSet('fast', 'block')][string]$SweepBehavior = 'fast')

		$sandbox = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $sandbox -Force
		Copy-Item $script:RunnerPath (Join-Path $sandbox 'build-queue-runner.ps1')

		$sweepBody = if ($SweepBehavior -eq 'block') {
			"Start-Sleep -Seconds 120`r`n`treturn @()"
		} else {
			"return @('C:\poisoned\Fake.dll')"
		}

		$shim = @'
. '{HYGIENE}'
function Reset-CompilerServer { param($OtherBuildActive = $false) return $true }
function Stop-DllLockers { param([string]$WorktreeRoot) return @() }
function Remove-PoisonedArtifacts {
	param([string]$WorktreeRoot)
	{SWEEP}
}
'@
		$shim = $shim.Replace('{HYGIENE}', $script:HygienePath).Replace('{SWEEP}', $sweepBody)
		[System.IO.File]::WriteAllText((Join-Path $sandbox 'build-queue-hygiene.ps1'), $shim)
		return $sandbox
	}

	function New-StateRoot {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'results') -Force
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force
		return $root
	}

	function New-Worktree {
		$wt = Join-Path $TestDrive ("wt-" + [Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $wt -Force
		[System.IO.File]::WriteAllText((Join-Path $wt 'placeholder.txt'), 'x')
		return $wt
	}

	function New-ExecScript {
		param([Parameter(Mandatory = $true)][string[]]$Lines)
		$path = Join-Path $TestDrive ("exec-" + [Guid]::NewGuid().ToString('N') + '.ps1')
		[System.IO.File]::WriteAllText($path, ($Lines -join "`r`n"))
		return $path
	}

	function New-RedBuildExec {
		New-ExecScript -Lines @(
			"Write-Output 'Compiling FakeProject 1/3 ...'"
			"Write-Output 'Compiling FakeProject 2/3 ...'"
			"Write-Output 'FakeThing.cs(12,3): error CS1739: fake overload resolution failure'"
			"Write-Output 'Build FAILED.'"
			"Write-Output '    23 Error(s)'"
			'exit 1'
		)
	}

	function New-GreenBuildExec {
		New-ExecScript -Lines @(
			"Write-Output 'Compiling FakeProject 1/3 ...'"
			"Write-Output 'Compiling FakeProject 2/3 ...'"
			"Write-Output 'Compiling FakeProject 3/3 ...'"
			"Write-Output 'Build succeeded.'"
			"Write-Output '    0 Warning(s)'"
			"Write-Output '    0 Error(s)'"
			"Write-Output 'Time Elapsed 00:00:01.23'"
			'exit 0'
		)
	}

	function New-RedTestExec {
		New-ExecScript -Lines @(
			"Write-Output 'Starting test execution, please wait...'"
			"Write-Output 'Failed FakeTest2 [12 ms]'"
			"Write-Output 'Results: Passed=3 Failed=2 Total=5'"
			'exit 1'
		)
	}

	function Write-ActiveLock {
		param([string]$StateRoot, [int]$Seq)
		$body = [ordered]@{
			seq        = $Seq
			build_pid  = 0
			op         = 'msbuild'
			started_at = (Get-Date).ToString('o')
		} | ConvertTo-Json -Compress
		[System.IO.File]::WriteAllText((Join-Path $StateRoot 'active.lock'), $body)
	}

	function Start-RunnerProcess {
		param(
			[string]$Sandbox,
			[string]$ExecPath,
			[int]$Seq,
			[string]$StateRoot,
			[string]$Worktree,
			[string]$Op,
			[string]$OpKind
		)
		$runner = Join-Path $Sandbox 'build-queue-runner.ps1'
		$logsDir = Join-Path $StateRoot 'logs'
		$argString = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -Exec `"$ExecPath`" -Seq $Seq -StateRoot `"$StateRoot`" -Worktree `"$Worktree`" -Op $Op -OpKind $OpKind -Hygiene dotnet"
		$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $argString `
			-RedirectStandardOutput (Join-Path $logsDir "$Seq.log") `
			-RedirectStandardError  (Join-Path $logsDir "$Seq.err.log") `
			-WindowStyle Hidden -PassThru
		$null = $proc.Handle
		$null = $script:SpawnedPids.Add($proc.Id)
		return $proc
	}

	function Get-ResultJson {
		param([string]$StateRoot, [int]$Seq)
		$path = Join-Path (Join-Path $StateRoot 'results') "$Seq.json"
		return Get-SafeValue {
			if (-not (Test-Path -LiteralPath $path)) { return $null }
			$text = [System.IO.File]::ReadAllText($path)
			if ([string]::IsNullOrWhiteSpace($text)) { return $null }
			$text | ConvertFrom-Json
		} $null
	}

	function Wait-Until {
		param([scriptblock]$Condition, [int]$TimeoutSec = 45, [int]$PollMs = 150)
		$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSec)
		while ([DateTime]::UtcNow -lt $deadline) {
			if (& $Condition) { return $true }
			Start-Sleep -Milliseconds $PollMs
		}
		return [bool](& $Condition)
	}

	function Invoke-Await {
		param([int]$Seq, [string]$StateRoot, [int]$TimeoutSeconds = 0, [int]$PollIntervalMs = 50)
		$lines = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:AwaitPath `
			-Seq $Seq -StateRoot $StateRoot -TimeoutSeconds $TimeoutSeconds -PollIntervalMs $PollIntervalMs 2>$null)
		return [pscustomobject]@{
			Lines    = $lines
			LastLine = if ($lines.Count -gt 0) { $lines[-1] } else { $null }
			ExitCode = $LASTEXITCODE
		}
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
Describe 'build-queue-runner.ps1 — crash-safe early write (kill-mid-hygiene serving path)' {

	AfterEach {
		# Reap any runner still blocked in the shim sweep (kill tests do this
		# themselves; this is the failure-path safety net).
		foreach ($spawnedPid in @($script:SpawnedPids)) {
			$null = Get-SafeValue { Stop-Process -Id $spawnedPid -Force -ErrorAction Stop }
		}
		$script:SpawnedPids.Clear()
	}

	It 'RED build: killed mid-sweep leaves a truthful result and await returns the RED outcome, not 124' {
		$sandbox = New-RunnerSandbox -SweepBehavior 'block'
		$root    = New-StateRoot
		$wt      = New-Worktree
		$exec    = New-RedBuildExec
		Write-ActiveLock -StateRoot $root -Seq 71

		$proc = Start-RunnerProcess -Sandbox $sandbox -ExecPath $exec -Seq 71 `
			-StateRoot $root -Worktree $wt -Op 'msbuild' -OpKind 'build'

		# The EARLY write lands while the runner is still blocked in the
		# RED-only quarantine sweep (the incident's multi-minute kill window).
		(Wait-Until { $null -ne (Get-ResultJson -StateRoot $root -Seq 71) }) | Should -BeTrue
		$proc.HasExited | Should -BeFalse

		$early = Get-ResultJson -StateRoot $root -Seq 71
		$early.exit_code | Should -Be 1
		$early.hygiene.status | Should -BeExactly 'pending'
		$early.hygiene.build_fidelity | Should -BeExactly 'verified'
		$early.hygiene.result_fidelity | Should -BeExactly 'n/a'
		@($early.hygiene.quarantined_artifacts).Count | Should -Be 0
		$early.op | Should -BeExactly 'msbuild'

		# The untrappable kill (TerminateProcess — the Bash-tool timeout
		# tree-kill class) mid-hygiene.
		Stop-Process -Id $proc.Id -Force
		(Wait-Until { $proc.HasExited } -TimeoutSec 15) | Should -BeTrue

		# The truthful result survives the kill; hygiene is honestly pending.
		$after = Get-ResultJson -StateRoot $root -Seq 71
		$after.exit_code | Should -Be 1
		$after.hygiene.status | Should -BeExactly 'pending'

		# Lock release sits AFTER hygiene by design (it serializes hygiene
		# against the next build): the stranded lock self-heals via the next
		# enqueue's dead-tick reclaim — unchanged contract.
		Test-Path (Join-Path $root 'active.lock') | Should -BeTrue

		# await now surfaces the build's real RED outcome instead of 124.
		$run = Invoke-Await -Seq 71 -StateRoot $root
		$run.ExitCode | Should -Be 1
		$expected = Format-BuildQueueBanner -Seq 71 -Op 'msbuild' -ExitCode 1 `
			-ResultFidelity 'n/a' -BuildFidelity 'verified' -Counts $null
		$run.LastLine | Should -BeExactly $expected
		$run.LastLine | Should -Match 'RESULT=FAIL'
	}

	It 'RED test op: killed mid-hygiene result carries the parsed counts; await banner reports tests=/failed=' {
		$sandbox = New-RunnerSandbox -SweepBehavior 'block'
		$root    = New-StateRoot
		$wt      = New-Worktree
		$exec    = New-RedTestExec

		$proc = Start-RunnerProcess -Sandbox $sandbox -ExecPath $exec -Seq 73 `
			-StateRoot $root -Worktree $wt -Op 'mstest' -OpKind 'test'

		(Wait-Until { $null -ne (Get-ResultJson -StateRoot $root -Seq 73) }) | Should -BeTrue
		$proc.HasExited | Should -BeFalse

		$early = Get-ResultJson -StateRoot $root -Seq 73
		$early.exit_code | Should -Be 1
		$early.hygiene.status | Should -BeExactly 'pending'
		$early.hygiene.result_fidelity | Should -BeExactly 'verified'
		$early.counts.passed | Should -Be 3
		$early.counts.failed | Should -Be 2
		$early.counts.total  | Should -Be 5

		Stop-Process -Id $proc.Id -Force
		(Wait-Until { $proc.HasExited } -TimeoutSec 15) | Should -BeTrue

		$run = Invoke-Await -Seq 73 -StateRoot $root
		$run.ExitCode | Should -Be 1
		$expected = Format-BuildQueueBanner -Seq 73 -Op 'mstest' -ExitCode 1 `
			-ResultFidelity 'verified' -BuildFidelity 'n/a' `
			-Counts @{ passed = 3; failed = 2; total = 5 }
		$run.LastLine | Should -BeExactly $expected
		$run.LastLine | Should -Match 'tests=5 failed=2'
	}
}

Describe 'build-queue-runner.ps1 — final write merges real hygiene over the early write' {

	AfterEach {
		foreach ($spawnedPid in @($script:SpawnedPids)) {
			$null = Get-SafeValue { Stop-Process -Id $spawnedPid -Force -ErrorAction Stop }
		}
		$script:SpawnedPids.Clear()
	}

	It 'RED build (fast sweep): status=complete, real hygiene fields, lock released, stats appended, no bare-True stdout leak' {
		$sandbox = New-RunnerSandbox -SweepBehavior 'fast'
		$root    = New-StateRoot
		$wt      = New-Worktree
		$exec    = New-RedBuildExec
		Write-ActiveLock -StateRoot $root -Seq 72

		$proc = Start-RunnerProcess -Sandbox $sandbox -ExecPath $exec -Seq 72 `
			-StateRoot $root -Worktree $wt -Op 'msbuild' -OpKind 'build'
		(Wait-Until { $proc.HasExited } -TimeoutSec 60) | Should -BeTrue
		$proc.ExitCode | Should -Be 1

		$res = Get-ResultJson -StateRoot $root -Seq 72
		$res.exit_code | Should -Be 1
		$res.hygiene.status | Should -BeExactly 'complete'
		$res.hygiene.vbcscompiler_recycled | Should -Be $true
		@($res.hygiene.quarantined_artifacts) | Should -Contain 'C:\poisoned\Fake.dll'
		$res.hygiene.build_fidelity | Should -BeExactly 'verified'
		$res.op | Should -BeExactly 'msbuild'
		$res.duration_seconds | Should -Not -BeNullOrEmpty

		# Lock released post-hygiene (normal flow — unchanged contract).
		Test-Path (Join-Path $root 'active.lock') | Should -BeFalse

		# ETA/stats ring appended where the final outcome is known.
		$statsPath = Join-Path (Join-Path $root 'stats') 'msbuild.json'
		Test-Path $statsPath | Should -BeTrue
		@((Get-Content -Raw $statsPath | ConvertFrom-Json)).seq | Should -Contain 72

		# The unassigned Stop-BuildJobTree return no longer leaks a bare
		# 'True' into the runner's stdout (logs/<seq>.log).
		$stdoutLines = @(Get-Content (Join-Path (Join-Path $root 'logs') '72.log') -ErrorAction SilentlyContinue)
		@($stdoutLines | Where-Object { $null -ne $_ -and $_.Trim() -eq 'True' }).Count | Should -Be 0
	}

	It 'GREEN build: single-pass flow ends status=complete with exit 0 and no sweep' {
		$sandbox = New-RunnerSandbox -SweepBehavior 'fast'
		$root    = New-StateRoot
		$wt      = New-Worktree
		$exec    = New-GreenBuildExec
		Write-ActiveLock -StateRoot $root -Seq 74

		$proc = Start-RunnerProcess -Sandbox $sandbox -ExecPath $exec -Seq 74 `
			-StateRoot $root -Worktree $wt -Op 'msbuild' -OpKind 'build'
		(Wait-Until { $proc.HasExited } -TimeoutSec 60) | Should -BeTrue
		$proc.ExitCode | Should -Be 0

		$res = Get-ResultJson -StateRoot $root -Seq 74
		$res.exit_code | Should -Be 0
		$res.hygiene.status | Should -BeExactly 'complete'
		$res.hygiene.build_fidelity | Should -BeExactly 'verified'
		@($res.hygiene.quarantined_artifacts).Count | Should -Be 0
		Test-Path (Join-Path $root 'active.lock') | Should -BeFalse
	}
}

Describe 'Write-BuildQueueResult (unit — real hygiene module)' {

	It 'writes the result atomically and returns the recorded ended_at stamp' {
		$root = New-StateRoot
		$stamp = Write-BuildQueueResult -StateRoot $root -Seq 5 -ExitCode 1 `
			-Counts $null -Op 'msbuild' -StartedAt '2026-07-10T00:00:00.0000000Z' -DurationSeconds 1.5 `
			-Hygiene ([ordered]@{ status = 'pending'; result_fidelity = 'n/a'; build_fidelity = 'verified' })

		$stamp | Should -Not -BeNullOrEmpty
		$res = Get-ResultJson -StateRoot $root -Seq 5
		$res.exit_code | Should -Be 1
		$res.ended_at | Should -BeExactly $stamp
		$res.hygiene.status | Should -BeExactly 'pending'
		$res.op | Should -BeExactly 'msbuild'
		$res.duration_seconds | Should -Be 1.5
	}

	It 'a second (final) write fully overwrites the early write — merge semantics are final-over-early' {
		$root = New-StateRoot
		$null = Write-BuildQueueResult -StateRoot $root -Seq 6 -ExitCode 1 -Op 'msbuild' `
			-Hygiene ([ordered]@{ status = 'pending'; vbcscompiler_recycled = $false; quarantined_artifacts = @() })
		$null = Write-BuildQueueResult -StateRoot $root -Seq 6 -ExitCode 1 -Op 'msbuild' `
			-Hygiene ([ordered]@{ status = 'complete'; vbcscompiler_recycled = $true; quarantined_artifacts = @('C:\poisoned\Fake.dll') })

		$res = Get-ResultJson -StateRoot $root -Seq 6
		$res.hygiene.status | Should -BeExactly 'complete'
		$res.hygiene.vbcscompiler_recycled | Should -Be $true
		@($res.hygiene.quarantined_artifacts) | Should -Contain 'C:\poisoned\Fake.dll'
	}

	It 'omits op/started_at/duration_seconds when Op is empty (legacy result shape)' {
		$root = New-StateRoot
		$null = Write-BuildQueueResult -StateRoot $root -Seq 7 -ExitCode 0 `
			-Hygiene ([ordered]@{ status = 'pending' })

		$res = Get-ResultJson -StateRoot $root -Seq 7
		$res.exit_code | Should -Be 0
		@($res.PSObject.Properties.Name) | Should -Not -Contain 'op'
		@($res.PSObject.Properties.Name) | Should -Not -Contain 'started_at'
		@($res.PSObject.Properties.Name) | Should -Not -Contain 'duration_seconds'
	}

	It 'never throws and returns $null on an unwritable state root (fail-open)' {
		# A FILE where the state root should be: results/ cannot be created
		# beneath it and the write throws internally — the helper must swallow
		# it and return $null (a throw here fails the test by itself).
		$blocker = Join-Path $TestDrive ('blocker-' + [Guid]::NewGuid().ToString('N') + '.txt')
		[System.IO.File]::WriteAllText($blocker, 'x')
		$out = Write-BuildQueueResult -StateRoot $blocker -Seq 8 -ExitCode 0 `
			-Hygiene ([ordered]@{ status = 'pending' }) -ErrorAction SilentlyContinue
		$out | Should -BeNullOrEmpty
	}
}

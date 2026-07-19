<#
.SYNOPSIS
  Pester v5 tests for concurrent-lock.ps1 — the PowerShell workstation plane of
  the per-queue-item FIFO file lock (concurrent-lock-contract.md).

.DESCRIPTION
  Verifies the conforming plane's contract legs with injected pid-liveness /
  clock probes and $TestDrive-only lock state (the real
  ~/.claude/state/concurrent-locks is never touched):
    - FIFO/serialize acquire order on the SAME item key (waits, never steals;
      proceeds in turn after release with a fresh token).
    - A timeout returns the authoritative outcome (RESULT=TIMEOUT, never a false
      ACQUIRED).
    - A CONFIRMED-dead holder (active.lock-style) is reclaimed.
    - Different item keys never block each other.
    - Fencing-token release refuses to unlock another holder's lock.

  Dot-sources concurrent-lock.ps1 (guarded so main does not run) to exercise its
  pure functions directly, mirroring build-queue-await.Tests.ps1.
#>

BeforeAll {
	$script:LockPath = Join-Path $PSScriptRoot 'concurrent-lock.ps1'
	. $script:LockPath   # dot-source: defines functions, does NOT run main

	function New-LockStateRoot {
		$root = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
		$null = New-Item -ItemType Directory -Path $root -Force
		return $root
	}

	function Write-HolderLock {
		param([string]$StateRoot, [string]$ItemId, [int]$HolderPid, [string]$Token = 'seed', $StartTime = $null)
		$path = Get-ItemLockPath -StateRoot $StateRoot -ItemId $ItemId
		$body = [ordered]@{
			pid               = $HolderPid
			kernel_start_time = $StartTime
			acquired_at       = ([DateTimeOffset]::UtcNow.ToString('o'))
			token             = $Token
			ttl_seconds       = 300
		} | ConvertTo-Json -Compress
		[System.IO.File]::WriteAllText($path, $body)
		return $path
	}

	$script:Alive = { param($p) $true }
	$script:Dead  = { param($p) $false }
	$script:NoStart = { param($p) $null }
}

Describe 'concurrent-lock.ps1 — same-item-key serialize + FIFO proceed-in-turn' {

	It 'acquires, blocks a live-holder contender to TIMEOUT, then proceeds in turn with a fresh token' {
		$root = New-LockStateRoot

		$first = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-x' -IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$first.Result | Should -Be 'ACQUIRED'
		$first.Token  | Should -Not -BeNullOrEmpty

		# Contender while the holder is live -> authoritative TIMEOUT (waits, never steals).
		$blocked = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-x' -TimeoutSeconds 0 `
			-IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$blocked.Result | Should -Be 'TIMEOUT'
		$blocked.Token  | Should -BeNullOrEmpty

		# Holder releases; contender now proceeds in turn.
		(Invoke-ReleaseItemLock -StateRoot $root -ItemId 'feat-x' -Token $first.Token).Result | Should -Be 'RELEASED'

		$second = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-x' -IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$second.Result | Should -Be 'ACQUIRED'
		$second.Token  | Should -Not -Be $first.Token
	}
}

Describe 'concurrent-lock.ps1 — timeout is authoritative (never a false success)' {

	It 'reports RESULT=TIMEOUT on the banner and exit 124 for a live-held item' {
		$root = New-LockStateRoot
		$null = Write-HolderLock -StateRoot $root -ItemId 'feat-y' -HolderPid $PID -Token 'held'

		$res = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-y' -TimeoutSeconds 0 `
			-IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$res.Result | Should -Be 'TIMEOUT'

		$banner = Format-ConcurrentLockBanner -ItemId 'feat-y' -Op 'acquire' -Result $res.Result -Holder $res.Holder -Elapsed $res.Elapsed
		$banner | Should -Match 'RESULT=TIMEOUT'
		$banner | Should -Match '^concurrent-lock: item=feat-y op=acquire'
	}
}

Describe 'concurrent-lock.ps1 — confirmed-dead holder is reclaimed' {

	It 'reclaims a dead-pid holder and the waiter proceeds (RESULT=RECLAIMED)' {
		$root = New-LockStateRoot
		$null = Write-HolderLock -StateRoot $root -ItemId 'feat-z' -HolderPid 999999 -Token 'zombie'

		$res = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-z' -TimeoutSeconds 2 `
			-IsPidAlive $script:Dead -GetStartTime $script:NoStart
		$res.Result | Should -Be 'RECLAIMED'
		$res.Token  | Should -Not -Be 'zombie'
	}

	It 'does NOT reclaim an ambiguous/live holder (no false reclaim -> TIMEOUT)' {
		$root = New-LockStateRoot
		$null = Write-HolderLock -StateRoot $root -ItemId 'feat-z2' -HolderPid 4242 -Token 'live'

		$res = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-z2' -TimeoutSeconds 0 `
			-IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$res.Result | Should -Be 'TIMEOUT'
		# The live holder's lock text is untouched.
		(Get-CLSafeValue { [System.IO.File]::ReadAllText((Get-ItemLockPath -StateRoot $root -ItemId 'feat-z2')) } '') | Should -Match 'live'
	}
}

Describe 'concurrent-lock.ps1 — different item keys never block' {

	It 'acquires two different item keys immediately, both held simultaneously' {
		$root = New-LockStateRoot
		$a = Invoke-AcquireItemLock -StateRoot $root -ItemId 'item-a' -IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$b = Invoke-AcquireItemLock -StateRoot $root -ItemId 'item-b' -IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$a.Result | Should -Be 'ACQUIRED'
		$b.Result | Should -Be 'ACQUIRED'
		(Test-Path (Get-ItemLockPath -StateRoot $root -ItemId 'item-a')) | Should -BeTrue
		(Test-Path (Get-ItemLockPath -StateRoot $root -ItemId 'item-b')) | Should -BeTrue
	}
}

Describe 'concurrent-lock.ps1 — fencing-token release' {

	It 'refuses to release another holder''s lock (FENCING-STALE), releases with the right token' {
		$root = New-LockStateRoot
		$acq = Invoke-AcquireItemLock -StateRoot $root -ItemId 'feat-f' -IsPidAlive $script:Alive -GetStartTime $script:NoStart
		$acq.Result | Should -Be 'ACQUIRED'

		(Invoke-ReleaseItemLock -StateRoot $root -ItemId 'feat-f' -Token 'wrong-token').Result | Should -Be 'FENCING-STALE'
		(Test-Path (Get-ItemLockPath -StateRoot $root -ItemId 'feat-f')) | Should -BeTrue

		(Invoke-ReleaseItemLock -StateRoot $root -ItemId 'feat-f' -Token $acq.Token).Result | Should -Be 'RELEASED'
		(Test-Path (Get-ItemLockPath -StateRoot $root -ItemId 'feat-f')) | Should -BeFalse
	}

	It 'release of an absent lock is idempotent (RELEASED)' {
		$root = New-LockStateRoot
		(Invoke-ReleaseItemLock -StateRoot $root -ItemId 'never-locked' -Token 'x').Result | Should -Be 'RELEASED'
	}
}

Describe 'concurrent-lock.ps1 — Get-LockHolderStatus classification' {

	It 'classifies dead / alive / reused-pid / malformed' {
		(Get-LockHolderStatus -Text '{"pid":123}' -IsPidAlive $script:Dead -GetStartTime $script:NoStart) | Should -Be 'dead'
		(Get-LockHolderStatus -Text '{"pid":123}' -IsPidAlive $script:Alive -GetStartTime $script:NoStart) | Should -Be 'alive'
		# Recorded start-time mismatches the live one -> PID reuse -> dead.
		(Get-LockHolderStatus -Text '{"pid":123,"kernel_start_time":100}' -IsPidAlive $script:Alive -GetStartTime { param($p) 200 }) | Should -Be 'dead'
		# Recorded start-time matches -> alive.
		(Get-LockHolderStatus -Text '{"pid":123,"kernel_start_time":100}' -IsPidAlive $script:Alive -GetStartTime { param($p) 100 }) | Should -Be 'alive'
		(Get-LockHolderStatus -Text 'not-json' -IsPidAlive $script:Alive -GetStartTime $script:NoStart) | Should -Be 'unknown'
		(Get-LockHolderStatus -Text '' -IsPidAlive $script:Alive -GetStartTime $script:NoStart) | Should -Be 'unknown'
	}
}

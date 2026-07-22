<#
.SYNOPSIS
  Pester v5 smoke tests for build-queue-hygiene.ps1.

.DESCRIPTION
  Verifies: (1) the public Job-Object functions (plus Reset-CompilerServer)
  are defined after dot-sourcing, (2) failure paths return the benign
  sentinel without throwing (fail-open), and (3) a static guard that the
  module source never contains a process-name-glob kill of a BUILD-TREE
  process (dotnet/testhost/msbuild — Locked Decision 2: those are reaped
  via Job-Object membership ONLY, never by name, so a sibling worktree's
  live build is never torn down). The guard deliberately EXEMPTS the one
  sanctioned name-targeted kill — VBCSCompiler recycle (Locked Decision 1)
  — which is safe because the queue serializes builds machine-wide.
#>

BeforeAll {
	$script:ModulePath = Join-Path $PSScriptRoot 'build-queue-hygiene.ps1'
	. $script:ModulePath
}

Describe 'build-queue-hygiene module surface' {
	It 'defines New-BuildJobObject' {
		Get-Command New-BuildJobObject -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'defines Add-ProcessToBuildJob' {
		Get-Command Add-ProcessToBuildJob -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'defines Stop-BuildJobTree' {
		Get-Command Stop-BuildJobTree -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'defines Reset-CompilerServer' {
		Get-Command Reset-CompilerServer -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}
}

Describe 'fail-open behavior on failure paths' {
	# NOTE: per the child-scope quirk documented throughout this file (DLL Locker Reap /
	# Set-LockFileAtomic / Get-BuildQueueOccupancy NOTEs) -- `{ $result = Foo } | Should -Not
	# -Throw` invokes the scriptblock via Pester in a CHILD scope, so the inner `$result =`
	# assignment never writes through to the outer `$result` (which stays $null). This is the
	# SAME child-scope-discard defect class as build-queue-buildlogpath-child-scope-forces-no-output-fail,
	# living in the test file itself. Fixed via try/catch (which does NOT introduce a new
	# PowerShell scope), matching the safe assign-on-its-own-line style used elsewhere in this file.
	It 'Add-ProcessToBuildJob returns $false without throwing for zero handles' {
		$threw = $false
		$result = $null
		try {
			$result = Add-ProcessToBuildJob -JobHandle ([IntPtr]::Zero) -ProcessHandle ([IntPtr]::Zero)
		} catch {
			$threw = $true
		}
		$threw | Should -Be $false
		$result | Should -Be $false
	}

	It 'Stop-BuildJobTree returns $false without throwing for a zero handle' {
		$threw = $false
		$result = $null
		try {
			$result = Stop-BuildJobTree -JobHandle ([IntPtr]::Zero)
		} catch {
			$threw = $true
		}
		$threw | Should -Be $false
		$result | Should -Be $false
	}
}

Describe 'Locked Decision 2 — no build-tree global process-name kill (VBCSCompiler exempt per Locked Decision 1)' {
	It 'module source does not pipe a build-tree Get-Process to Stop-Process' {
		$source = Get-Content -Raw -Path $script:ModulePath
		$source | Should -Not -Match 'Get-Process[^|]*\b(dotnet|testhost|msbuild)\b[^|]*\|\s*Stop-Process'
	}

	It 'module source does not contain a Stop-Process -Name invocation of a build-tree process' {
		$source = Get-Content -Raw -Path $script:ModulePath
		$source | Should -Not -Match 'Stop-Process\s+-Name\s+["'']?(dotnet|testhost|msbuild)'
	}

	It 'module source DOES contain the sanctioned VBCSCompiler recycle (Locked Decision 1 pinned in place)' {
		$source = Get-Content -Raw -Path $script:ModulePath
		$source | Should -Match 'VBCSCompiler'
	}
}

Describe 'Reset-CompilerServer' {
	It 'is defined after dot-sourcing' {
		Get-Command Reset-CompilerServer -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'does not throw and returns a [bool]' {
		# Per the same child-scope quirk (see 'fail-open behavior on failure paths' above):
		# try/catch, not a `{ } | Should -Not -Throw` scriptblock, so $result survives.
		$threw = $false
		$result = $null
		try {
			$result = Reset-CompilerServer
		} catch {
			$threw = $true
		}
		$threw | Should -Be $false
		($result -eq $true -or $result -eq $false) | Should -Be $true
	}
}

Describe 'Remove-PoisonedArtifacts' {
	BeforeAll {
		$script:TestWorktree = Join-Path $env:TEMP ("rpa-pester-" + [guid]::NewGuid().ToString('N'))

		$script:BinDir = Join-Path $script:TestWorktree 'bin\Debug'
		$script:ObjDir = Join-Path $script:TestWorktree 'obj\Debug'
		New-Item -ItemType Directory -Path $script:BinDir -Force | Out-Null
		New-Item -ItemType Directory -Path $script:ObjDir -Force | Out-Null

		$script:XDllPath = Join-Path $script:BinDir 'x.dll'
		$script:YDllPath = Join-Path $script:ObjDir 'y.dll'
		$script:GoodDllPath = Join-Path $script:BinDir 'good.dll'

		# x.dll - 0 bytes (bin/)
		[System.IO.File]::WriteAllBytes($script:XDllPath, [byte[]]@())

		# y.dll - 3 bytes, no MZ magic (obj/)
		[System.IO.File]::WriteAllBytes($script:YDllPath, [byte[]](0x00, 0x01, 0x02))

		# good.dll - starts with MZ (0x4D 0x5A), 64 bytes total, nonzero (bin/)
		$goodBytes = New-Object byte[] 64
		$goodBytes[0] = 0x4D
		$goodBytes[1] = 0x5A
		[System.IO.File]::WriteAllBytes($script:GoodDllPath, $goodBytes)
	}

	AfterAll {
		Remove-Item -Path $script:TestWorktree -Recurse -Force -ErrorAction SilentlyContinue
	}

	It 'does not throw' {
		{ Remove-PoisonedArtifacts -WorktreeRoot $script:TestWorktree } | Should -Not -Throw
	}

	It 'deletes the 0-byte DLL under bin/' {
		Remove-PoisonedArtifacts -WorktreeRoot $script:TestWorktree | Out-Null
		Test-Path $script:XDllPath | Should -Be $false
	}

	It 'deletes the truncated/invalid-PE DLL under obj/' {
		Test-Path $script:YDllPath | Should -Be $false
	}

	It 'leaves the valid-PE DLL in place' {
		Test-Path $script:GoodDllPath | Should -Be $true
	}

	It 'returns exactly the two quarantined paths' {
		# Re-seed (prior Its already deleted x/y) for an isolated return-value assertion.
		[System.IO.File]::WriteAllBytes($script:XDllPath, [byte[]]@())
		[System.IO.File]::WriteAllBytes($script:YDllPath, [byte[]](0x00, 0x01, 0x02))

		$result = @(Remove-PoisonedArtifacts -WorktreeRoot $script:TestWorktree)

		$result.Count | Should -Be 2
		$result | Should -Contain $script:XDllPath
		$result | Should -Contain $script:YDllPath
	}
}

Describe 'Test-BuildLogFailure' {
	It 'does not throw for a real failure-shaped log' {
		{ Test-BuildLogFailure -Log "Build FAILED.`r`nerror MSB3027: Could not copy.`r`n2 Error(s)" } | Should -Not -Throw
	}

	It 'detects the seq-346 failure shape (Build FAILED + error MSB3027 + 2 Error(s))' {
		$log = "Build FAILED.`r`nerror MSB3027: Could not copy `"x.dll`" to `"y.dll`". Exceeded retry count.`r`n2 Error(s)"
		$result = Test-BuildLogFailure -Log $log
		$result.failed | Should -Be $true
		$result.signature | Should -Be 'Build FAILED'
	}

	It 'detects error MSB3021 as a failure signature when it is the first match' {
		$log = "Some preamble line`r`nerror MSB3021: Unable to copy file.`r`n1 Error(s)"
		$result = Test-BuildLogFailure -Log $log
		$result.failed | Should -Be $true
		$result.signature | Should -Be 'error MSB3021'
	}

	It 'detects a nonzero Error(s) count line as a failure signature' {
		$log = "Some preamble line`r`n3 Error(s)"
		$result = Test-BuildLogFailure -Log $log
		$result.failed | Should -Be $true
		$result.signature | Should -Match 'Error\(s\)'
	}

	It 'returns a non-failure result for a clean successful build log' {
		$log = "Build succeeded.`r`n0 Warning(s)`r`n0 Error(s)"
		$result = Test-BuildLogFailure -Log $log
		$result.failed | Should -Be $false
		$result.signature | Should -Be $null
	}

	It 'accepts a [string[]] log (array of lines) equivalently' {
		$lines = @('Build FAILED.', 'error MSB3027: Could not copy.', '2 Error(s)')
		$result = Test-BuildLogFailure -Log $lines
		$result.failed | Should -Be $true
		$result.signature | Should -Be 'Build FAILED'
	}

	It 'does not throw and fails open (non-failure) for $null input' {
		{ Test-BuildLogFailure -Log $null } | Should -Not -Throw
		$result = Test-BuildLogFailure -Log $null
		$result.failed | Should -Be $false
	}

	It 'does not throw and fails open (non-failure) for an empty string input' {
		{ Test-BuildLogFailure -Log '' } | Should -Not -Throw
		$result = Test-BuildLogFailure -Log ''
		$result.failed | Should -Be $false
	}

	It 'does not throw and fails open (non-failure) for a non-string bad input' {
		{ Test-BuildLogFailure -Log 12345 } | Should -Not -Throw
		$result = Test-BuildLogFailure -Log 12345
		$result.failed | Should -Be $false
	}
}

Describe 'DLL Locker Reap' {
	# NOTE: per the child-scope quirk that plagues the 3 known pre-existing
	# failures, these tests NEVER use `{ $r = Foo } | Should -Not -Throw` and then
	# read $r afterward. Each function call is assigned on its OWN line and the
	# assertion is separate — mirroring the passing Remove-PoisonedArtifacts style.

	It 'defines Get-DllLockers' {
		Get-Command Get-DllLockers -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'defines Stop-DllLockers' {
		Get-Command Stop-DllLockers -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'Get-DllLockers does not throw and returns empty for a nonexistent worktree (fail-open)' {
		$bogus = Join-Path $env:TEMP ("dlr-nonexistent-" + [guid]::NewGuid().ToString('N'))
		{ Get-DllLockers -WorktreeRoot $bogus } | Should -Not -Throw
		$result = @(Get-DllLockers -WorktreeRoot $bogus)
		$result.Count | Should -Be 0
	}

	It 'Stop-DllLockers does not throw and returns empty for a nonexistent worktree (fail-open)' {
		$bogus = Join-Path $env:TEMP ("dlr-nonexistent-" + [guid]::NewGuid().ToString('N'))
		{ Stop-DllLockers -WorktreeRoot $bogus } | Should -Not -Throw
		$result = @(Stop-DllLockers -WorktreeRoot $bogus)
		$result.Count | Should -Be 0
	}

	Context 'no-op — an unlocked DLL is held by nobody' {
		BeforeAll {
			$script:NoLockWorktree = Join-Path $env:TEMP ("dlr-nolock-" + [guid]::NewGuid().ToString('N'))
			$script:NoLockBinDir = Join-Path $script:NoLockWorktree 'bin\Debug'
			New-Item -ItemType Directory -Path $script:NoLockBinDir -Force | Out-Null
			$script:NoLockDll = Join-Path $script:NoLockBinDir 'unlocked.dll'
			$bytes = New-Object byte[] 64
			$bytes[0] = 0x4D
			$bytes[1] = 0x5A
			[System.IO.File]::WriteAllBytes($script:NoLockDll, $bytes)
		}

		AfterAll {
			Remove-Item -Path $script:NoLockWorktree -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'Get-DllLockers reports no lockers for an unlocked DLL' {
			$result = @(Get-DllLockers -WorktreeRoot $script:NoLockWorktree)
			$result.Count | Should -Be 0
		}

		It 'Stop-DllLockers reaps nothing for an unlocked DLL' {
			$result = @(Stop-DllLockers -WorktreeRoot $script:NoLockWorktree)
			$result.Count | Should -Be 0
		}
	}

	Context 'spawned-handle fixture — a helper process HOLDS a handle on bin/Debug/*.dll' {
		BeforeAll {
			$script:LockWorktree = Join-Path $env:TEMP ("dlr-lock-" + [guid]::NewGuid().ToString('N'))
			$script:LockBinDir = Join-Path $script:LockWorktree 'bin\Debug'
			New-Item -ItemType Directory -Path $script:LockBinDir -Force | Out-Null
			$script:LockedDll = Join-Path $script:LockBinDir 'locked.dll'
			$bytes = New-Object byte[] 64
			$bytes[0] = 0x4D
			$bytes[1] = 0x5A
			[System.IO.File]::WriteAllBytes($script:LockedDll, $bytes)

			# Spawn a helper that opens the DLL with NO sharing and HOLDS it for 30s.
			$holdCmd = "`$fs=[System.IO.File]::Open('$($script:LockedDll)','Open','Read','None'); Start-Sleep 30; `$fs.Close()"
			$script:Holder = Start-Process powershell -PassThru -WindowStyle Hidden `
				-ArgumentList '-NoProfile', '-Command', $holdCmd
			$script:HolderPid = $script:Holder.Id

			# Wait for the handle to actually be held (up to ~5s): the file becomes
			# non-openable-with-sharing-None once the holder has it.
			$deadline = (Get-Date).AddSeconds(5)
			while ((Get-Date) -lt $deadline) {
				$held = $false
				try {
					$probe = [System.IO.File]::Open($script:LockedDll, 'Open', 'Read', 'None')
					$probe.Close()
				} catch {
					$held = $true
				}
				if ($held) { break }
				Start-Sleep -Milliseconds 200
			}
		}

		AfterAll {
			# Kill the holder even if a test failed / never terminated it, so no
			# 30s-sleeping powershell leaks out of the run.
			if ($script:HolderPid) {
				Stop-Process -Id $script:HolderPid -Force -ErrorAction SilentlyContinue
			}
			Remove-Item -Path $script:LockWorktree -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'Get-DllLockers reports the holder PID' {
			$lockers = @(Get-DllLockers -WorktreeRoot $script:LockWorktree)
			$pids = @($lockers | ForEach-Object { $_.pid })
			$pids | Should -Contain $script:HolderPid
		}

		It 'Stop-DllLockers terminates the holder and returns its PID' {
			$reaped = @(Stop-DllLockers -WorktreeRoot $script:LockWorktree)
			$reaped | Should -Contain $script:HolderPid

			# The handle is now freed — the DLL can be re-opened with no-sharing / removed.
			Start-Sleep -Milliseconds 300
			$freed = $false
			try {
				$probe = [System.IO.File]::Open($script:LockedDll, 'Open', 'Read', 'None')
				$probe.Close()
				$freed = $true
			} catch {
				$freed = $false
			}
			$freed | Should -Be $true
		}
	}

	Context 'scope guard — VBCSCompiler-exempt, never an out-of-worktree kill (Locked Decision 2 intent)' {
		BeforeAll {
			$script:ScopeWorktree = Join-Path $env:TEMP ("dlr-scope-" + [guid]::NewGuid().ToString('N'))
			$script:ScopeBinDir = Join-Path $script:ScopeWorktree 'bin\Debug'
			New-Item -ItemType Directory -Path $script:ScopeBinDir -Force | Out-Null
			$script:ScopeDll = Join-Path $script:ScopeBinDir 'scope.dll'
			$bytes = New-Object byte[] 64
			$bytes[0] = 0x4D
			$bytes[1] = 0x5A
			[System.IO.File]::WriteAllBytes($script:ScopeDll, $bytes)
		}

		AfterAll {
			Remove-Item -Path $script:ScopeWorktree -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'Stop-DllLockers only returns PIDs that Get-DllLockers reported for THIS worktree' {
			$lockers = @(Get-DllLockers -WorktreeRoot $script:ScopeWorktree)
			$lockerPids = @($lockers | ForEach-Object { $_.pid })

			$reaped = @(Stop-DllLockers -WorktreeRoot $script:ScopeWorktree)

			# Every reaped PID MUST have been one Get-DllLockers reported for this
			# worktree — no global process-name kill, no out-of-scope termination.
			foreach ($rpid in $reaped) {
				$lockerPids | Should -Contain $rpid
			}
		}

		It 'module source contains a VBCSCompiler-exempt filter in the locker reap (Locked Decision 1)' {
			$source = Get-Content -Raw -Path $script:ModulePath
			$source | Should -Match 'VBCSCompiler'
		}
	}
}

Describe 'Set-LockFileAtomic' {
	# NOTE: per the child-scope quirk documented above (and the DLL Locker Reap block's
	# NOTE), every call is assigned on its OWN line with the assertion on the NEXT line --
	# never `{ $result = Foo } | Should -Not -Throw` followed by reading $result.

	BeforeAll {
		$script:LockDestPath = Join-Path $env:TEMP ("slfa-pester-" + [guid]::NewGuid().ToString('N') + '.json')
		$script:LockTempPath = "$($script:LockDestPath).tmp"
	}

	AfterAll {
		Remove-Item -Path $script:LockDestPath -Force -ErrorAction SilentlyContinue
		Remove-Item -Path $script:LockTempPath -Force -ErrorAction SilentlyContinue
	}

	It 'defines Set-LockFileAtomic' {
		Get-Command Set-LockFileAtomic -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'writes the lock body atomically (temp-then-move) and returns $true' {
		$body = '{"seq":5,"build_pid":1234,"op":"msbuild"}'
		$result = Set-LockFileAtomic -Path $script:LockDestPath -Body $body
		$result | Should -Be $true
	}

	It 'round-trips the lock body at the destination with no truncation' {
		$lockJson = [System.IO.File]::ReadAllText($script:LockDestPath) | ConvertFrom-Json
		$lockJson.seq | Should -Be 5
		$lockJson.build_pid | Should -Be 1234
		$lockJson.op | Should -Be 'msbuild'
	}

	It 'leaves no temp file behind after a successful move' {
		# Pre-seed a dummy temp file so this assertion is only satisfied when
		# Set-LockFileAtomic actually ran and cleaned it up as part of the
		# move -- otherwise it would vacuously pass just because nothing
		# ever created $script:LockTempPath.
		Set-Content -Path $script:LockTempPath -Value 'placeholder' -Force
		Set-LockFileAtomic -Path $script:LockDestPath -Body '{"seq":9,"build_pid":42,"op":"nxbuild"}' | Out-Null
		Test-Path $script:LockTempPath | Should -Be $false
	}
}

Describe 'Get-ActiveLockStatusFromText' {
	It 'defines Get-ActiveLockStatusFromText' {
		Get-Command Get-ActiveLockStatusFromText -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'returns "alive" for valid JSON with a build_pid when the probe returns $true' {
		$text = '{"seq":5,"build_pid":1234,"op":"msbuild"}'
		$result = Get-ActiveLockStatusFromText -Text $text -IsPidAlive { param($p) $true }
		$result | Should -Be 'alive'
	}

	It 'returns "dead" for valid JSON with a build_pid when the probe returns $false' {
		$text = '{"seq":5,"build_pid":1234,"op":"msbuild"}'
		$result = Get-ActiveLockStatusFromText -Text $text -IsPidAlive { param($p) $false }
		$result | Should -Be 'dead'
	}

	It 'returns "unknown" for an empty/whitespace lock text' {
		$result = Get-ActiveLockStatusFromText -Text '' -IsPidAlive { param($p) $true }
		$result | Should -Be 'unknown'
	}

	It 'returns "unknown" for garbage/truncated non-JSON text' {
		$result = Get-ActiveLockStatusFromText -Text '{ this is not json' -IsPidAlive { param($p) $true }
		$result | Should -Be 'unknown'
	}

	It 'returns "unknown" when the JSON object is missing a build_pid field' {
		$result = Get-ActiveLockStatusFromText -Text '{"seq":5}' -IsPidAlive { param($p) $true }
		$result | Should -Be 'unknown'
	}
}

Describe 'Test-ShouldReclaimLock' {
	It 'defines Test-ShouldReclaimLock' {
		Get-Command Test-ShouldReclaimLock -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'reclaims when the observation run is all-dead at exactly the threshold and IsLowestSeq is $true' {
		$result = Test-ShouldReclaimLock -Observations @('dead', 'dead', 'dead') -StaleThreshold 3 -IsLowestSeq $true
		$result | Should -Be $true
	}

	It 'does not reclaim when every observation is "unknown" (all-unknown never reclaims)' {
		$result = Test-ShouldReclaimLock -Observations @('unknown', 'unknown', 'unknown', 'unknown') -StaleThreshold 3 -IsLowestSeq $true
		$result | Should -Be $false
	}

	It 'does not reclaim when an "unknown" observation resets the consecutive-dead run below threshold' {
		$result = Test-ShouldReclaimLock -Observations @('dead', 'unknown', 'dead', 'dead') -StaleThreshold 3 -IsLowestSeq $true
		$result | Should -Be $false
	}

	It 'does not reclaim when IsLowestSeq is $false even with enough consecutive dead observations' {
		$result = Test-ShouldReclaimLock -Observations @('dead', 'dead', 'dead') -StaleThreshold 3 -IsLowestSeq $false
		$result | Should -Be $false
	}

	It 'reclaims when the trailing consecutive-dead run meets a lower threshold' {
		$result = Test-ShouldReclaimLock -Observations @('alive', 'dead', 'dead') -StaleThreshold 2 -IsLowestSeq $true
		$result | Should -Be $true
	}

	It 'reclaims an age-stale lock on the first dead observation below the consecutive-dead threshold' {
		$result = Test-ShouldReclaimLock -Observations @('dead') -StaleThreshold 3 -IsLowestSeq $true -LockAgeMinutes 45
		$result | Should -Be $true
	}

	It 'does not reclaim an age-stale lock when the trailing observation is not dead' {
		$result = Test-ShouldReclaimLock -Observations @('dead', 'unknown') -StaleThreshold 3 -IsLowestSeq $true -LockAgeMinutes 45
		$result | Should -Be $false
	}

	It 'does not reclaim on age when the lock is younger than the age threshold' {
		$result = Test-ShouldReclaimLock -Observations @('dead') -StaleThreshold 3 -IsLowestSeq $true -LockAgeMinutes 5
		$result | Should -Be $false
	}

	It 'does not reclaim on age when age is unknown (default -1) even with a trailing dead below threshold' {
		$result = Test-ShouldReclaimLock -Observations @('dead') -StaleThreshold 3 -IsLowestSeq $true
		$result | Should -Be $false
	}

	It 'does not reclaim an age-stale lock when IsLowestSeq is $false' {
		$result = Test-ShouldReclaimLock -Observations @('dead') -StaleThreshold 3 -IsLowestSeq $false -LockAgeMinutes 45
		$result | Should -Be $false
	}
}

Describe 'Get-BuildQueueOccupancy' {
	# NOTE: per the child-scope quirk documented above (DLL Locker Reap / Set-LockFileAtomic
	# blocks' NOTEs), every call is assigned on its OWN line with the assertion on the NEXT
	# line -- never `{ $result = Foo } | Should -Not -Throw` followed by reading $result.
	#
	# $PID (this process) is used as a guaranteed-ALIVE pid; 999999999 as a guaranteed-DEAD pid.

	It 'defines Get-BuildQueueOccupancy' {
		Get-Command Get-BuildQueueOccupancy -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	Context 'count 0 -- only self / empty' {
		BeforeAll {
			$script:OccEmptyRoot = Join-Path $env:TEMP ("occ-empty-" + [guid]::NewGuid().ToString('N'))
			$script:OccEmptyTicketsDir = Join-Path $script:OccEmptyRoot 'tickets'
			New-Item -ItemType Directory -Path $script:OccEmptyTicketsDir -Force | Out-Null
		}

		AfterAll {
			Remove-Item -Path $script:OccEmptyRoot -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'returns 0 for an empty tickets dir and no active.lock' {
			$result = Get-BuildQueueOccupancy -StateRoot $script:OccEmptyRoot -SelfSeq 1
			$result | Should -Be 0
		}

		It 'returns 0 for a lone self ticket (self excluded)' {
			$selfTicketPath = Join-Path $script:OccEmptyTicketsDir '1.json'
			[System.IO.File]::WriteAllText($selfTicketPath, (@{ seq = 1; pid = $PID } | ConvertTo-Json -Compress))

			$result = Get-BuildQueueOccupancy -StateRoot $script:OccEmptyRoot -SelfSeq 1
			$result | Should -Be 0
		}
	}

	Context 'count 1 -- one OTHER live seq holds the lock' {
		BeforeAll {
			$script:OccOneRoot = Join-Path $env:TEMP ("occ-one-" + [guid]::NewGuid().ToString('N'))
			New-Item -ItemType Directory -Path (Join-Path $script:OccOneRoot 'tickets') -Force | Out-Null
			$script:OccOneLock = Join-Path $script:OccOneRoot 'active.lock'
			[System.IO.File]::WriteAllText($script:OccOneLock, (@{ seq = 2; build_pid = $PID } | ConvertTo-Json -Compress))
		}

		AfterAll {
			Remove-Item -Path $script:OccOneRoot -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'returns 1' {
			$result = Get-BuildQueueOccupancy -StateRoot $script:OccOneRoot -SelfSeq 1
			$result | Should -Be 1
		}
	}

	Context 'count 2 -- two OTHER live seqs (active.lock + a ticket)' {
		BeforeAll {
			$script:OccTwoRoot = Join-Path $env:TEMP ("occ-two-" + [guid]::NewGuid().ToString('N'))
			$script:OccTwoTicketsDir = Join-Path $script:OccTwoRoot 'tickets'
			New-Item -ItemType Directory -Path $script:OccTwoTicketsDir -Force | Out-Null

			$script:OccTwoLock = Join-Path $script:OccTwoRoot 'active.lock'
			[System.IO.File]::WriteAllText($script:OccTwoLock, (@{ seq = 2; build_pid = $PID } | ConvertTo-Json -Compress))

			$otherTicketPath = Join-Path $script:OccTwoTicketsDir '3.json'
			[System.IO.File]::WriteAllText($otherTicketPath, (@{ seq = 3; pid = $PID } | ConvertTo-Json -Compress))
		}

		AfterAll {
			Remove-Item -Path $script:OccTwoRoot -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'returns 2' {
			$result = Get-BuildQueueOccupancy -StateRoot $script:OccTwoRoot -SelfSeq 1
			$result | Should -Be 2
		}
	}

	Context 'dead-pid does NOT count' {
		BeforeAll {
			$script:OccDeadRoot = Join-Path $env:TEMP ("occ-dead-" + [guid]::NewGuid().ToString('N'))
			New-Item -ItemType Directory -Path (Join-Path $script:OccDeadRoot 'tickets') -Force | Out-Null
			$script:OccDeadLock = Join-Path $script:OccDeadRoot 'active.lock'
			[System.IO.File]::WriteAllText($script:OccDeadLock, (@{ seq = 2; build_pid = 999999999 } | ConvertTo-Json -Compress))
		}

		AfterAll {
			Remove-Item -Path $script:OccDeadRoot -Recurse -Force -ErrorAction SilentlyContinue
		}

		It 'returns 0' {
			$result = Get-BuildQueueOccupancy -StateRoot $script:OccDeadRoot -SelfSeq 1
			$result | Should -Be 0
		}
	}

	Context 'fail-open -- absent state dir' {
		It 'does not throw and returns 0' {
			$bogusRoot = Join-Path $env:TEMP ("occ-bogus-" + [guid]::NewGuid().ToString('N'))
			{ Get-BuildQueueOccupancy -StateRoot $bogusRoot -SelfSeq 1 } | Should -Not -Throw

			$result = Get-BuildQueueOccupancy -StateRoot $bogusRoot -SelfSeq 1
			$result | Should -Be 0
		}
	}
}

Describe 'Reset-CompilerServer occupancy gate (-OtherBuildActive)' {
	# NOTE: same child-scope discipline as above -- assign on its own line, assert on the next.

	It 'skips the recycle and returns $false when -OtherBuildActive $true (concurrency gate)' {
		{ Reset-CompilerServer -OtherBuildActive $true } | Should -Not -Throw

		$result = Reset-CompilerServer -OtherBuildActive $true
		$result | Should -Be $false
	}

	It 'does not throw when -OtherBuildActive $false (sole -- performs the normal recycle path)' {
		{ Reset-CompilerServer -OtherBuildActive $false } | Should -Not -Throw
	}

	It 'returns a [bool] on the normal (non-gated) path when -OtherBuildActive $false' {
		$result = Reset-CompilerServer -OtherBuildActive $false
		($result -eq $true -or $result -eq $false) | Should -Be $true
	}
}

Describe 'Format-BuildQueueBanner' {
	# NOTE: same child-scope discipline as above -- assign on its own line, assert on the next
	# (except where the task explicitly wants a `{ } | Should -Not -Throw` guard, in which case
	# the throw-guard call and the value-read call are both made, matching the Reset-CompilerServer
	# pattern above).

	It 'defines Format-BuildQueueBanner' {
		Get-Command Format-BuildQueueBanner -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'PASS: renders tests=/failed= and (result_fidelity=...) with NO next-action suffix' {
		$result = Format-BuildQueueBanner -Seq 614 -Op mstest -ExitCode 0 -ResultFidelity verified -BuildFidelity verified -Counts @{ passed = 312; failed = 0; total = 312 }
		$result | Should -Be 'build-queue: seq=614 op=mstest RESULT=PASS tests=312 failed=0 (result_fidelity=verified)'
	}

	It 'FAIL via non-zero exit code: RESULT=FAIL with the read-logs next-action naming the seq' {
		$result = Format-BuildQueueBanner -Seq 620 -Op msbuild -ExitCode 1 -ResultFidelity verified -BuildFidelity verified
		$result | Should -Be 'build-queue: seq=620 op=msbuild RESULT=FAIL (result_fidelity=verified) -> read logs/620.build.err.log'
	}

	It 'FAIL via log-failure-override (exit 0): a test op names its actual seq err.log (no .build. infix)' {
		$result = Format-BuildQueueBanner -Seq 621 -Op nxtest -ExitCode 0 -ResultFidelity verified -BuildFidelity log-failure-override
		$result | Should -Be 'build-queue: seq=621 op=nxtest RESULT=FAIL (result_fidelity=verified) -> read logs/621.err.log'
	}

	It 'NO-TESTS-MATCHED takes precedence over the exit code and gets the widen-filter next-action' {
		$result = Format-BuildQueueBanner -Seq 622 -Op mstest -ExitCode 5 -ResultFidelity no-tests-matched -BuildFidelity verified
		$result | Should -Be 'build-queue: seq=622 op=mstest RESULT=NO-TESTS-MATCHED (result_fidelity=no-tests-matched) -> widen the filter and retry'
	}

	It 'staleness: exit code 4 gets the rebuild-stale-DLL next-action' {
		$result = Format-BuildQueueBanner -Seq 623 -Op msbuild -ExitCode 4 -ResultFidelity verified -BuildFidelity verified
		$result | Should -Be 'build-queue: seq=623 op=msbuild RESULT=FAIL (result_fidelity=verified) -> rebuild (stale DLL)'
	}

	It 'null-counts safety: does not throw and omits the tests= segment' {
		{ Format-BuildQueueBanner -Seq 624 -Op mstest -ExitCode 0 -ResultFidelity verified -BuildFidelity verified -Counts $null } | Should -Not -Throw

		$result = Format-BuildQueueBanner -Seq 624 -Op mstest -ExitCode 0 -ResultFidelity verified -BuildFidelity verified -Counts $null
		$result | Should -Be 'build-queue: seq=624 op=mstest RESULT=PASS (result_fidelity=verified)'
	}
}

Describe 'Get-ProjectDlls (WU-1 shared per-project DLL enumerator)' {
	# NOTE: per the child-scope quirk documented in DLL Locker Reap, every function
	# call is assigned on its OWN line with the assertion on the NEXT line.

	BeforeAll {
		$script:GpdWorktree = Join-Path $env:TEMP ("gpd-pester-" + [guid]::NewGuid().ToString('N'))
		# Per-project subdir layout (NOT worktree-root bin/obj) — the exact shape the
		# worktree-root-only sweep was blind to.
		$script:GpdBinDebug   = Join-Path $script:GpdWorktree 'Cognito\bin\Debug\netstandard2.0'
		$script:GpdObjDebug   = Join-Path $script:GpdWorktree 'Cognito.Core\obj\Debug'
		$script:GpdBinRelease = Join-Path $script:GpdWorktree 'Cognito\bin\Release'
		New-Item -ItemType Directory -Path $script:GpdBinDebug -Force | Out-Null
		New-Item -ItemType Directory -Path $script:GpdObjDebug -Force | Out-Null
		New-Item -ItemType Directory -Path $script:GpdBinRelease -Force | Out-Null

		$mz = New-Object byte[] 64
		$mz[0] = 0x4D
		$mz[1] = 0x5A
		$script:GpdBinDebugDll   = Join-Path $script:GpdBinDebug 'Cognito.dll'
		$script:GpdObjDebugDll   = Join-Path $script:GpdObjDebug 'Cognito.Core.dll'
		$script:GpdBinReleaseDll = Join-Path $script:GpdBinRelease 'Cognito.dll'
		[System.IO.File]::WriteAllBytes($script:GpdBinDebugDll, $mz)
		[System.IO.File]::WriteAllBytes($script:GpdObjDebugDll, $mz)
		[System.IO.File]::WriteAllBytes($script:GpdBinReleaseDll, $mz)
	}

	AfterAll {
		Remove-Item -Path $script:GpdWorktree -Recurse -Force -ErrorAction SilentlyContinue
	}

	It 'defines Get-ProjectDlls' {
		Get-Command Get-ProjectDlls -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'no filter: enumerates *.dll across per-project bin AND obj subdirs' {
		$paths = @(Get-ProjectDlls -WorktreeRoot $script:GpdWorktree | ForEach-Object { $_.FullName })
		$paths | Should -Contain $script:GpdBinDebugDll
		$paths | Should -Contain $script:GpdObjDebugDll
		$paths | Should -Contain $script:GpdBinReleaseDll
	}

	It 'bin/Debug filter: restricts to per-project bin/Debug DLLs only' {
		$paths = @(Get-ProjectDlls -WorktreeRoot $script:GpdWorktree -PathSegmentFilter 'bin/Debug' | ForEach-Object { $_.FullName })
		$paths | Should -Contain $script:GpdBinDebugDll
		$paths | Should -Not -Contain $script:GpdObjDebugDll
		$paths | Should -Not -Contain $script:GpdBinReleaseDll
	}

	It 'fail-open: does not throw and returns empty for a nonexistent worktree' {
		$bogus = Join-Path $env:TEMP ("gpd-nonexistent-" + [guid]::NewGuid().ToString('N'))
		{ Get-ProjectDlls -WorktreeRoot $bogus } | Should -Not -Throw
		$result = @(Get-ProjectDlls -WorktreeRoot $bogus)
		$result.Count | Should -Be 0
	}
}

Describe 'Remove-PoisonedArtifacts — per-project sweep (WU-1)' {
	BeforeEach {
		$script:PpWorktree   = Join-Path $env:TEMP ("rpa-pp-" + [guid]::NewGuid().ToString('N'))
		$script:PpBinDebug   = Join-Path $script:PpWorktree 'Cognito\bin\Debug\netstandard2.0'
		$script:PpObjDebug   = Join-Path $script:PpWorktree 'Cognito.Core\obj\Debug'
		$script:PpBinRelease = Join-Path $script:PpWorktree 'Cognito\bin\Release'
		New-Item -ItemType Directory -Path $script:PpBinDebug -Force | Out-Null
		New-Item -ItemType Directory -Path $script:PpObjDebug -Force | Out-Null
		New-Item -ItemType Directory -Path $script:PpBinRelease -Force | Out-Null

		# 0-byte poisoned DLL under a per-project bin/Debug subdir (the regression pin).
		$script:PpZeroDll = Join-Path $script:PpBinDebug 'Cognito.dll'
		[System.IO.File]::WriteAllBytes($script:PpZeroDll, [byte[]]@())

		# Truncated non-MZ DLL under a per-project obj/Debug subdir.
		$script:PpTruncDll = Join-Path $script:PpObjDebug 'Cognito.Core.dll'
		[System.IO.File]::WriteAllBytes($script:PpTruncDll, [byte[]](0x00, 0x00, 0x00, 0x00))

		# Valid-PE DLL under a per-project subdir — must be left alone.
		$mz = New-Object byte[] 64
		$mz[0] = 0x4D
		$mz[1] = 0x5A
		$script:PpGoodDll = Join-Path $script:PpBinDebug 'Valid.dll'
		[System.IO.File]::WriteAllBytes($script:PpGoodDll, $mz)

		# Poisoned DLL under bin/Release — the no-filter sweep must ALSO reach it.
		$script:PpReleaseDll = Join-Path $script:PpBinRelease 'Cognito.dll'
		[System.IO.File]::WriteAllBytes($script:PpReleaseDll, [byte[]]@())
	}

	AfterEach {
		Remove-Item -Path $script:PpWorktree -Recurse -Force -ErrorAction SilentlyContinue
	}

	It 'quarantines a 0-byte DLL under a per-project bin/Debug subdir (regression pin)' {
		Remove-PoisonedArtifacts -WorktreeRoot $script:PpWorktree | Out-Null
		Test-Path $script:PpZeroDll | Should -Be $false
	}

	It 'quarantines a truncated (non-MZ) DLL under a per-project obj/Debug subdir' {
		Remove-PoisonedArtifacts -WorktreeRoot $script:PpWorktree | Out-Null
		Test-Path $script:PpTruncDll | Should -Be $false
	}

	It 'leaves a valid-PE DLL under a per-project subdir alone' {
		Remove-PoisonedArtifacts -WorktreeRoot $script:PpWorktree | Out-Null
		Test-Path $script:PpGoodDll | Should -Be $true
	}

	It 'sweeps both configs: a poisoned bin/Release DLL is also quarantined (no path filter)' {
		Remove-PoisonedArtifacts -WorktreeRoot $script:PpWorktree | Out-Null
		Test-Path $script:PpReleaseDll | Should -Be $false
	}

	It 'returns the quarantined per-project paths' {
		$result = @(Remove-PoisonedArtifacts -WorktreeRoot $script:PpWorktree)
		$result | Should -Contain $script:PpZeroDll
		$result | Should -Contain $script:PpTruncDll
	}
}

Describe 'Get-DllLockers — per-project enumeration (WU-1)' {
	BeforeAll {
		$script:GdlWorktree = Join-Path $env:TEMP ("gdl-pp-" + [guid]::NewGuid().ToString('N'))
		# DLL under a per-project bin/Debug subdir (NOT worktree-root bin/Debug), the
		# shape the old <root>/bin-only enumeration could not see.
		$script:GdlBinDebug = Join-Path $script:GdlWorktree 'Cognito\bin\Debug\netstandard2.0'
		New-Item -ItemType Directory -Path $script:GdlBinDebug -Force | Out-Null
		$mz = New-Object byte[] 64
		$mz[0] = 0x4D
		$mz[1] = 0x5A
		$script:GdlDll = Join-Path $script:GdlBinDebug 'Cognito.dll'
		[System.IO.File]::WriteAllBytes($script:GdlDll, $mz)
	}

	AfterAll {
		Remove-Item -Path $script:GdlWorktree -Recurse -Force -ErrorAction SilentlyContinue
	}

	It 'enumeration reaches a per-project bin/Debug DLL (via the shared filter)' {
		$paths = @(Get-ProjectDlls -WorktreeRoot $script:GdlWorktree -PathSegmentFilter 'bin/Debug' | ForEach-Object { $_.FullName })
		$paths | Should -Contain $script:GdlDll
	}

	It 'Get-DllLockers does not throw for a per-project bin/Debug fixture and returns empty when unlocked (fail-open)' {
		{ Get-DllLockers -WorktreeRoot $script:GdlWorktree } | Should -Not -Throw
		$result = @(Get-DllLockers -WorktreeRoot $script:GdlWorktree)
		$result.Count | Should -Be 0
	}
}

Describe 'Read-WithRetry (WU-2 flush-retry helper)' {
	# Counter-closure scriptblocks — no filesystem/timing dependency. -DelayMs 0
	# keeps the tests instant; sleep-between-attempts semantics are unchanged.
	# Per the child-scope quirk: each Read-WithRetry call is on its OWN line and
	# the assertion is separate.

	It 'defines Read-WithRetry' {
		Get-Command Read-WithRetry -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'returns on the first non-null attempt and invokes the parse block exactly once' {
		$script:rwrCalls = 0
		$parse = { $script:rwrCalls++; 'value' }
		$result = Read-WithRetry -Parse $parse -MaxAttempts 3 -DelayMs 0
		$result | Should -Be 'value'
		$script:rwrCalls | Should -Be 1
	}

	It 'retries up to -MaxAttempts when the parse block always returns $null and returns the fallback sentinel' {
		$script:rwrCalls = 0
		$parse = { $script:rwrCalls++; $null }
		$result = Read-WithRetry -Parse $parse -MaxAttempts 3 -DelayMs 0 -Fallback 'FALLBACK'
		$script:rwrCalls | Should -Be 3
		$result | Should -Be 'FALLBACK'
	}

	It 'returns the default fallback ($null) after -MaxAttempts is exhausted' {
		$script:rwrCalls = 0
		$parse = { $script:rwrCalls++; $null }
		$result = Read-WithRetry -Parse $parse -MaxAttempts 2 -DelayMs 0
		$script:rwrCalls | Should -Be 2
		$result | Should -BeNullOrEmpty
	}

	It 'succeeds on the Nth attempt: returns the value and invokes the parse block exactly N times' {
		$script:rwrCalls = 0
		$parse = { $script:rwrCalls++; if ($script:rwrCalls -lt 3) { $null } else { 'ready' } }
		$result = Read-WithRetry -Parse $parse -MaxAttempts 5 -DelayMs 0
		$result | Should -Be 'ready'
		$script:rwrCalls | Should -Be 3
	}
}

Describe 'Test-BuildProducedNoOutput (WU-1 build-output classifier)' {
	# Child-scope discipline: each function call on its OWN line, assertion on the next.

	It 'defines Test-BuildProducedNoOutput' {
		Get-Command Test-BuildProducedNoOutput -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'classifies a $null log (missing log path) as no-output' {
		$result = Test-BuildProducedNoOutput -LogText $null
		$result | Should -BeTrue
	}

	It 'classifies an empty (0-byte) log as no-output' {
		$result = Test-BuildProducedNoOutput -LogText ''
		$result | Should -BeTrue
	}

	It 'classifies a whitespace-only log as no-output' {
		$result = Test-BuildProducedNoOutput -LogText "   `r`n`t  `n "
		$result | Should -BeTrue
	}

	It 'classifies a near-empty log (below the default 40-char threshold) as no-output' {
		# 12 non-whitespace chars, well under the default MinChars=40 threshold.
		$result = Test-BuildProducedNoOutput -LogText 'Build ok.'
		$result | Should -BeTrue
	}

	It 'pins the near-empty threshold: a log exactly at -MinChars is NOT no-output; one below IS' {
		# 10-char trimmed body; -MinChars 10 => at threshold => produced output ($false).
		$atThreshold = Test-BuildProducedNoOutput -LogText '0123456789' -MinChars 10
		$atThreshold | Should -BeFalse

		$belowThreshold = Test-BuildProducedNoOutput -LogText '012345678' -MinChars 10
		$belowThreshold | Should -BeTrue
	}

	It 'classifies a real non-empty MSBuild log as produced-output ($false)' {
		$realLog = @'
Microsoft (R) Build Engine version 16.11.2+f32259642 for .NET Framework
Copyright (C) Microsoft Corporation. All rights reserved.

  Restored C:\ws\Cognito\Cognito.csproj (in 512 ms).
  Cognito -> C:\ws\Cognito\bin\Debug\netstandard2.0\Cognito.dll

Build succeeded.
    0 Warning(s)
    0 Error(s)

Time Elapsed 00:00:07.42
'@
		$result = Test-BuildProducedNoOutput -LogText $realLog
		$result | Should -BeFalse
	}

	It 'classifies a terse Nx log WITH ANSI codes as produced-output (not false-no-output) — build-queue-nxbuild-terse-output-false-fail' {
		# Simulates a real Nx build with terse success output and ANSI color codes.
		# Without ANSI stripping, this log has ~50 raw characters but would fail the
		# MinChars=40 check and be falsely classified as "no output".
		# With stripping, the cleaned text is "Building cognito-client...NX  Successfully ran target build for project cognito-client"
		# which is ~100+ chars and passes the threshold.
		$esc = [char]27
		$terseNxLog = 'Building cognito-client...' + "`r`n" + $esc + '[0m' + $esc + '[36mNX' + $esc + '[39m  ' + $esc + '[32mSuccessfully ran target build for project cognito-client' + $esc + '[0m'
		$result = Test-BuildProducedNoOutput -LogText $terseNxLog
		$result | Should -BeFalse
	}

	It 'classifies a very terse log (below threshold even after ANSI stripping) as no-output' {
		# A log that is genuinely empty/truncated, even after ANSI stripping.
		$esc = [char]27
		$veryTerse = 'x' + $esc + '[0my'
		$result = Test-BuildProducedNoOutput -LogText $veryTerse
		$result | Should -BeTrue
	}
}

Describe 'Strip-AnsiCodes (ANSI escape sequence removal)' {
	It 'defines Strip-AnsiCodes' {
		Get-Command Strip-AnsiCodes -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'returns empty string for $null input' {
		$result = Strip-AnsiCodes -Text $null
		$result | Should -BeExactly ''
	}

	It 'returns empty string for whitespace-only input' {
		$result = Strip-AnsiCodes -Text "   `r`n`t  "
		$result | Should -BeExactly ''
	}

	It 'removes a simple ANSI color code (ESC[0m reset)' {
		$esc = [char]27
		$input = 'hello' + $esc + '[0mworld'
		$result = Strip-AnsiCodes -Text $input
		$result | Should -BeExactly 'helloworld'
	}

	It 'removes ANSI color codes with parameters (ESC[32m green, ESC[1;32m bold-green)' {
		$esc = [char]27
		$input = $esc + '[32mgreen' + $esc + '[0m' + $esc + '[1;32mbold-green' + $esc + '[0m'
		$result = Strip-AnsiCodes -Text $input
		$result | Should -BeExactly 'greenbold-green'
	}

	It 'removes webpackbar-style ANSI sequences (real Nx output)' {
		$esc = [char]27
		$input = '[webpackbar] ' + $esc + '[32m✔' + $esc + '[39m Form-client: Compiled successfully'
		$result = Strip-AnsiCodes -Text $input
		$result | Should -BeExactly '[webpackbar] ✔ Form-client: Compiled successfully'
	}

	It 'preserves regular text and non-ANSI special characters' {
		$input = "Line 1`r`nLine 2 (no codes here)"
		$result = Strip-AnsiCodes -Text $input
		$result | Should -BeExactly $input
	}

	It 'handles a complex multi-line log with mixed ANSI codes' {
		$esc = [char]27
		$input = 'Building ' + $esc + '[36mcognito-client' + $esc + '[39m...' + "`r`n" + $esc + '[0m' + $esc + '[36mNX' + $esc + '[39m  ' + $esc + '[32mSuccessfully ran target build for project cognito-client' + $esc + '[0m'
		$result = Strip-AnsiCodes -Text $input
		# After stripping, should have the plain text without ANSI codes
		$result | Should -Match 'Building cognito-client'
		$result | Should -Match 'Successfully ran target build'
		# Verify ANSI codes are gone (the escape character should be stripped)
		$result | Should -Not -Match ([char]27)
	}
}

Describe 'Format-BuildQueueBanner — build_fidelity no-output arm (WU-1)' {
	# Child-scope discipline: assign on its own line, assert on the next.

	It 'no-output + forced exit=1: RESULT=FAIL with the delete-obj/bin-and-rebuild next-action' {
		$result = Format-BuildQueueBanner -Seq 640 -Op msbuild -ExitCode 1 -ResultFidelity verified -BuildFidelity no-output
		$result | Should -Be 'build-queue: seq=640 op=msbuild RESULT=FAIL (result_fidelity=verified) -> build produced no output; delete obj/bin and rebuild'
	}

	It 'regression: a normal PASS (exit 0, build_fidelity verified) is unchanged (no next-action)' {
		$result = Format-BuildQueueBanner -Seq 641 -Op msbuild -ExitCode 0 -ResultFidelity verified -BuildFidelity verified
		$result | Should -Be 'build-queue: seq=641 op=msbuild RESULT=PASS (result_fidelity=verified)'
	}
}

Describe 'Format-BuildQueueBanner - op-aware no-output remedy (build-queue-nxbuild-false-no-output-fail)' {
	# Child-scope discipline: assign on its own line, assert on the next.

	It 'nxbuild no-output gets the nx-appropriate remedy, NOT the dotnet obj/bin text' {
		$result = Format-BuildQueueBanner -Seq 833 -Op nxbuild -ExitCode 1 -ResultFidelity verified -BuildFidelity no-output
		$result | Should -Be 'build-queue: seq=833 op=nxbuild RESULT=FAIL (result_fidelity=verified) -> build produced no output; re-run the nx target (npx nx build)'
	}

	It 'msbuild no-output KEEPS the original dotnet remedy (no regression - pinned alongside WU-1)' {
		$result = Format-BuildQueueBanner -Seq 834 -Op msbuild -ExitCode 1 -ResultFidelity verified -BuildFidelity no-output
		$result | Should -Be 'build-queue: seq=834 op=msbuild RESULT=FAIL (result_fidelity=verified) -> build produced no output; delete obj/bin and rebuild'
	}

	It 'an unrecognized/unknown op falls back to the dotnet remedy (safe default)' {
		$result = Format-BuildQueueBanner -Seq 835 -Op some-future-op -ExitCode 1 -ResultFidelity verified -BuildFidelity no-output
		$result | Should -Be 'build-queue: seq=835 op=some-future-op RESULT=FAIL (result_fidelity=verified) -> build produced no output; delete obj/bin and rebuild'
	}
}

Describe 'Get-HygieneHighlight (WU-3 status-view highlight selector)' {
	# Pure highlight-selection helper shared by build-queue-status.ps1 and this test.
	# Child-scope discipline: assign on its own line, assert on the next.

	It 'defines Get-HygieneHighlight' {
		Get-Command Get-HygieneHighlight -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
	}

	It 'build-op no-output selects the distinct red BUILD LIED - produced no output arm' {
		$hl = Get-HygieneHighlight -BuildFidelity 'no-output' -ResultFidelity 'n/a'
		$hl.Suffix | Should -Match 'produced no output'
		$hl.Color | Should -Be 'Red'
	}

	It 'copy-lock override still selects its own red BUILD LIED - copy-lock arm' {
		$hl = Get-HygieneHighlight -BuildFidelity 'log-failure-override' -ResultFidelity 'n/a'
		$hl.Suffix | Should -Match 'copy-lock override'
		$hl.Color | Should -Be 'Red'
	}

	It 'test-op result_fidelity no-output still selects the yellow UNVERIFIED arm (distinct from build-op no-output)' {
		$hl = Get-HygieneHighlight -BuildFidelity 'n/a' -ResultFidelity 'no-output'
		$hl.Suffix | Should -Match 'no test output captured'
		$hl.Color | Should -Be 'Yellow'
	}

	It 'build-op no-output takes precedence over a coincident test-op no-output result_fidelity' {
		$hl = Get-HygieneHighlight -BuildFidelity 'no-output' -ResultFidelity 'no-output'
		$hl.Suffix | Should -Match 'produced no output'
		$hl.Color | Should -Be 'Red'
	}

	It 'copy-lock override takes precedence over a coincident test-op no-output result_fidelity' {
		$hl = Get-HygieneHighlight -BuildFidelity 'log-failure-override' -ResultFidelity 'no-output'
		$hl.Suffix | Should -Match 'copy-lock override'
		$hl.Color | Should -Be 'Red'
	}

	It 'a clean verified build selects no highlight (empty suffix, null color)' {
		$hl = Get-HygieneHighlight -BuildFidelity 'verified' -ResultFidelity 'n/a'
		$hl.Suffix | Should -BeNullOrEmpty
		$hl.Color | Should -BeNullOrEmpty
	}
}

Describe 'scope-in-caller guard — hygiene dot-source is a top-level statement (regression guard)' {
	# NOTE: this Describe block does NOT dot-source or invoke any of the three callers below --
	# they are top-level scripts with param() blocks that EXECUTE real queue/build/status
	# machinery on load. Every assertion here reads caller SOURCE via AST parse only.
	#
	# Bug context: each caller loads build-queue-hygiene.ps1 via
	#   Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }
	# Get-SafeValue invokes its scriptblock with `& $Block`, which runs in a CHILD scope --
	# so every function the dot-source defines is discarded and undefined back in the
	# caller's real script scope. The fix (a later work unit) moves the dot-source to a
	# top-level `try { . ... } catch { }` instead. This guard is RED today (dot-source is
	# wrapped in a Get-SafeValue scriptblock argument) and must go GREEN once the dot-source
	# becomes a true top-level statement.
	#
	# Uses BeforeAll (not a bare Describe-body function def) and It -ForEach (not a bare
	# foreach loop) -- Pester v5 splits Discovery from Run, so code/loop-vars outside
	# BeforeAll/It only exist at Discovery time and are gone by the time It bodies run.

	BeforeAll {
		function Test-HasScriptBlockExpressionAncestor {
			param($Node)

			$ancestor = $Node.Parent
			while ($null -ne $ancestor) {
				if ($ancestor -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) {
					return $true
				}
				$ancestor = $ancestor.Parent
			}
			return $false
		}
	}

	It "dot-sources build-queue-hygiene.ps1 at script scope, not inside Get-SafeValue (<_>)" -ForEach @('build-queue.ps1', 'build-queue-runner.ps1', 'build-queue-status.ps1') {
		$callerName = $_
		$callerPath = Join-Path $PSScriptRoot $callerName

		$ast = [System.Management.Automation.Language.Parser]::ParseFile($callerPath, [ref]$null, [ref]$null)

		$dotSources = $ast.FindAll({
			param($n)
			$n -is [System.Management.Automation.Language.CommandAst] -and
				$n.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot
		}, $true)

		$hygieneDotSources = @($dotSources | Where-Object { $_.Extent.Text -match 'build-queue-hygiene\.ps1' })
		$hygieneDotSources.Count | Should -Be 1 -Because "there should be exactly one dot-source of build-queue-hygiene.ps1 in $callerName"

		$isNestedInScriptBlock = Test-HasScriptBlockExpressionAncestor -Node $hygieneDotSources[0]
		$isNestedInScriptBlock | Should -Be $false -Because "the build-queue-hygiene.ps1 dot-source in $callerName must be a top-level statement (e.g. inside a top-level try{}), not a scriptblock argument to Get-SafeValue -- otherwise & `$Block runs it in a child scope and every function it defines is discarded"
	}
}

Describe 'scope-in-caller guard -- buildLogPath assignment is main-scope, not Get-SafeValue child scope (regression guard)' {
	# NOTE: this Describe block does NOT dot-source or invoke build-queue-runner.ps1 -- it is a
	# top-level script with a param() block that EXECUTES real build machinery on load. Every
	# assertion here reads the caller SOURCE via AST parse only.
	#
	# Bug context: build-queue-runner.ps1 initializes $buildLogPath = $null at script (main)
	# scope, then re-assigns it INSIDE a `Get-SafeValue { ... $buildLogPath = Join-Path
	# $logsDir "$Seq.build.log" ... }` scriptblock argument. Get-SafeValue invokes its
	# scriptblock with `& $Block`, which runs in a CHILD scope -- so that re-assignment is
	# discarded and the main-scope $buildLogPath stays $null. The downstream build-log
	# classifier then reads $null and force-fails every successful build. The fix (a later
	# work unit) moves the $buildLogPath = Join-Path ... assignment out of the Get-SafeValue
	# scriptblock into a top-level (or try{}/if{} statement-block, NOT scriptblock-expression)
	# statement. This guard is RED today (the assignment is nested inside a Get-SafeValue
	# scriptblock argument) and must go GREEN once the assignment becomes a true main-scope
	# statement.
	#
	# Uses its own BeforeAll-scoped helper (Pester v5 splits Discovery from Run, so helpers
	# defined outside BeforeAll/It only exist at Discovery time and are gone by the time It
	# bodies run) -- independent of the sibling Describe block above so this guard has no
	# cross-block dependency.

	BeforeAll {
		function Test-HasScriptBlockExprAncestor2 {
			param($Node)

			$ancestor = $Node.Parent
			while ($null -ne $ancestor) {
				if ($ancestor -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) {
					return $true
				}
				$ancestor = $ancestor.Parent
			}
			return $false
		}
	}

	It 'assigns $buildLogPath = Join-Path ...build.log at main scope, not inside Get-SafeValue' {
		$callerPath = Join-Path $PSScriptRoot 'build-queue-runner.ps1'

		$ast = [System.Management.Automation.Language.Parser]::ParseFile($callerPath, [ref]$null, [ref]$null)

		$assignments = $ast.FindAll({
			param($n)
			$n -is [System.Management.Automation.Language.AssignmentStatementAst]
		}, $true)

		$buildLogPathAssignments = @($assignments | Where-Object {
			$_.Left.Extent.Text -match 'buildLogPath' -and $_.Right.Extent.Text -match 'build\.log'
		})
		$buildLogPathAssignments.Count | Should -Be 1 -Because 'there should be exactly one $buildLogPath = Join-Path ... "$Seq.build.log" assignment in build-queue-runner.ps1 (distinct from the $buildLogPath = $null initializer)'

		$isNestedInScriptBlock = Test-HasScriptBlockExprAncestor2 -Node $buildLogPathAssignments[0]
		$isNestedInScriptBlock | Should -Be $false -Because 'the $buildLogPath build-log-path assignment in build-queue-runner.ps1 must be a main/script-scope statement, not a scriptblock argument to Get-SafeValue -- otherwise & $Block runs it in a child scope, the main-scope $buildLogPath stays $null, and the downstream build-log classifier force-fails every successful build'
	}
}

Describe 'Get-BuildQueueOpsManifest (build-queue-generalization manifest loader)' {
	BeforeEach {
		$script:RepoRoot = Join-Path $TestDrive ("repo-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
		$script:ConfigDir = Join-Path (Join-Path $script:RepoRoot '.claude') 'skill-config'
		$null = New-Item -ItemType Directory -Path $script:ConfigDir -Force
		$script:ManifestPath = Join-Path $script:ConfigDir 'build-queue-ops.json'
	}

	It 'parses a valid manifest and returns path/version/ops' {
		$body = @{
			version = 1
			ops = @{
				msbuild = @{ exec = '.claude/scripts/build-filtered.ps1'; kind = 'build'; hygiene = 'dotnet'; skill = '/msbuild'; deny = @('dotnet build') }
				mstest  = @{ exec = '.claude/scripts/test-filtered.ps1'; kind = 'test'; hygiene = 'dotnet'; skill = '/mstest'; deny = @('dotnet test') }
			}
		} | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText($script:ManifestPath, $body)

		$manifest = Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot
		$manifest | Should -Not -BeNullOrEmpty
		$manifest.path | Should -Be $script:ManifestPath
		$manifest.version | Should -Be 1
		@($manifest.ops.PSObject.Properties).Count | Should -Be 2
		$manifest.ops.msbuild.hygiene | Should -Be 'dotnet'
	}

	It 'returns $null silently for a missing manifest file' {
		$result = Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot
		$result | Should -BeNullOrEmpty
	}

	It 'returns $null (fail-open, no throw) for malformed JSON' {
		[System.IO.File]::WriteAllText($script:ManifestPath, '{ not json !!!')
		$result = $null
		{ $script:mf = Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot -WarningAction SilentlyContinue } | Should -Not -Throw
		$script:mf | Should -BeNullOrEmpty
	}

	It 'returns $null for an unsupported version' {
		$body = @{ version = 2; ops = @{ x = @{ exec = 'a.ps1'; kind = 'build'; hygiene = 'none' } } } | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText($script:ManifestPath, $body)
		Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot -WarningAction SilentlyContinue | Should -BeNullOrEmpty
	}

	It 'returns $null when an op is missing required exec' {
		$body = @{ version = 1; ops = @{ x = @{ kind = 'build'; hygiene = 'none' } } } | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText($script:ManifestPath, $body)
		Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot -WarningAction SilentlyContinue | Should -BeNullOrEmpty
	}

	It 'returns $null when an op has an invalid kind' {
		$body = @{ version = 1; ops = @{ x = @{ exec = 'a.ps1'; kind = 'deploy'; hygiene = 'none' } } } | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText($script:ManifestPath, $body)
		Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot -WarningAction SilentlyContinue | Should -BeNullOrEmpty
	}

	It 'returns $null when an op has an unknown hygiene profile id' {
		$body = @{ version = 1; ops = @{ x = @{ exec = 'a.ps1'; kind = 'build'; hygiene = 'jvm' } } } | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText($script:ManifestPath, $body)
		Get-BuildQueueOpsManifest -RepoRoot $script:RepoRoot -WarningAction SilentlyContinue | Should -BeNullOrEmpty
	}

	It 'parses the committed Cognito manifest (repo fixture) with four dotnet ops' {
		$committedCfg = Join-Path (Split-Path -Parent $PSScriptRoot) 'repos\cognito-forms\.claude\skill-config\build-queue-ops.json'
		if (-not (Test-Path $committedCfg)) {
			# user/scripts -> repo root is two levels up
			$committedCfg = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'repos\cognito-forms\.claude\skill-config\build-queue-ops.json'
		}
		Test-Path $committedCfg | Should -Be $true

		$fixtureRoot = Join-Path $TestDrive 'cognito-fixture'
		$fixtureCfg = Join-Path (Join-Path $fixtureRoot '.claude') 'skill-config'
		$null = New-Item -ItemType Directory -Path $fixtureCfg -Force
		Copy-Item $committedCfg (Join-Path $fixtureCfg 'build-queue-ops.json')

		$manifest = Get-BuildQueueOpsManifest -RepoRoot $fixtureRoot
		$manifest | Should -Not -BeNullOrEmpty
		$opNames = @($manifest.ops.PSObject.Properties | ForEach-Object { $_.Name }) | Sort-Object
		($opNames -join ',') | Should -Be 'msbuild,mstest,nxbuild,nxtest'
		foreach ($p in $manifest.ops.PSObject.Properties) {
			$p.Value.hygiene | Should -Be 'dotnet'
		}
	}
}

Describe 'Get-HygieneProfile (closed profile registry)' {
	It 'dotnet profile pins exactly todays behavior (recycle + dll sweep + msbuild signatures + locker reap)' {
		$p = Get-HygieneProfile -Name 'dotnet'
		$p.name | Should -Be 'dotnet'
		$p.recycle_compiler_server | Should -Be $true
		$p.poison_sweep | Should -Be 'dotnet-dll'
		$p.log_failure_signatures | Should -Be 'msbuild'
		$p.reap_dll_lockers | Should -Be $true
	}

	It 'rust-tauri profile never enables the dotnet-only sweeps' {
		$p = Get-HygieneProfile -Name 'rust-tauri'
		$p.recycle_compiler_server | Should -Be $false
		$p.poison_sweep | Should -BeNullOrEmpty
		$p.log_failure_signatures | Should -Be 'cargo'
		$p.reap_dll_lockers | Should -Be $false
	}

	It 'none profile is reap-only (no recycle, no sweep, no signature scan)' {
		$p = Get-HygieneProfile -Name 'none'
		$p.recycle_compiler_server | Should -Be $false
		$p.poison_sweep | Should -BeNullOrEmpty
		$p.log_failure_signatures | Should -BeNullOrEmpty
		$p.reap_dll_lockers | Should -Be $false
	}

	It 'an empty name resolves to the dotnet profile (legacy byte-compat)' {
		$p = Get-HygieneProfile -Name ''
		$p.name | Should -Be 'dotnet'
	}

	It 'an unknown name warns and falls back to none (safe floor), never throws' {
		$p = $null
		{ $script:up = Get-HygieneProfile -Name 'jvm' -WarningAction SilentlyContinue } | Should -Not -Throw
		$script:up.name | Should -Be 'none'
		$script:up.recycle_compiler_server | Should -Be $false
	}
}

Describe 'Test-BuildLogFailure - cargo signature set (rust-tauri profile)' {
	It 'flags a rustc coded error' {
		$log = "   Compiling app v0.1.0`nerror[E0308]: mismatched types"
		$r = Test-BuildLogFailure -Log $log -SignatureSet 'cargo'
		$r.failed | Should -Be $true
		$r.signature | Should -Be 'error[E0308]'
	}

	It 'flags a bare error: line (could not compile)' {
		$log = "warning: unused variable`nerror: could not compile app"
		$r = Test-BuildLogFailure -Log $log -SignatureSet 'cargo'
		$r.failed | Should -Be $true
		$r.signature | Should -Match 'could not compile'
	}

	It 'does not flag a clean cargo log with warnings only' {
		$log = "warning: unused import`n    Finished release [optimized] target(s) in 92.31s"
		$r = Test-BuildLogFailure -Log $log -SignatureSet 'cargo'
		$r.failed | Should -Be $false
	}

	It 'does not flag MSBuild signatures under the cargo set' {
		$log = "Build FAILED.`n    3 Error(s)"
		$r = Test-BuildLogFailure -Log $log -SignatureSet 'cargo'
		$r.failed | Should -Be $false
	}

	It 'default (no -SignatureSet) stays the msbuild set - byte-compat' {
		$r = Test-BuildLogFailure -Log 'Build FAILED'
		$r.failed | Should -Be $true
		$r.signature | Should -Be 'Build FAILED'
	}

	It 'an unknown signature set falls back to msbuild (conservative default)' {
		$r = Test-BuildLogFailure -Log 'Build FAILED' -SignatureSet 'gradle'
		$r.failed | Should -Be $true
	}
}

Describe 'Resolve-BuildQueueOp (wrapper op resolution seam)' {
	BeforeEach {
		$script:RepoRoot = Join-Path $TestDrive ("resolve-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
		$script:ConfigDir = Join-Path (Join-Path $script:RepoRoot '.claude') 'skill-config'
		$null = New-Item -ItemType Directory -Path $script:ConfigDir -Force
		$script:ManifestPath = Join-Path $script:ConfigDir 'build-queue-ops.json'
		$body = @{
			version = 1
			ops = @{
				'tauri-build' = @{ exec = '.claude/scripts/tauri-build-filtered.ps1'; kind = 'build'; hygiene = 'rust-tauri'; skill = '/tauri-build'; deny = @('tauri build') }
			}
		} | ConvertTo-Json -Depth 5
		[System.IO.File]::WriteAllText($script:ManifestPath, $body)
	}

	It 'resolves a manifested op: exec defaulted repo-relative, kind/hygiene threaded' {
		$r = Resolve-BuildQueueOp -RepoRoot $script:RepoRoot -Op 'tauri-build'
		$r.ok | Should -Be $true
		$r.source | Should -Be 'manifest'
		$r.exec | Should -Be (Join-Path $script:RepoRoot '.claude/scripts/tauri-build-filtered.ps1')
		$r.kind | Should -Be 'build'
		$r.hygiene | Should -Be 'rust-tauri'
	}

	It 'an explicit -Exec overrides the manifest entry (D8 back-compat)' {
		$explicit = Join-Path $script:RepoRoot 'custom.ps1'
		$r = Resolve-BuildQueueOp -RepoRoot $script:RepoRoot -Op 'tauri-build' -Exec $explicit
		$r.ok | Should -Be $true
		$r.exec | Should -Be $explicit
		$r.hygiene | Should -Be 'rust-tauri'
	}

	It 'an unknown op in a manifested repo fails with an error naming the manifest path and registered ops' {
		$r = Resolve-BuildQueueOp -RepoRoot $script:RepoRoot -Op 'bogus'
		$r.ok | Should -Be $false
		$r.error | Should -Match 'bogus'
		$r.error | Should -Match ([regex]::Escape($script:ManifestPath))
		$r.error | Should -Match 'tauri-build'
	}

	It 'legacy fallback: no manifest + legacy op + explicit exec resolves with dotnet hygiene and inferred kind' {
		$bare = Join-Path $TestDrive ("bare-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
		$null = New-Item -ItemType Directory -Path $bare -Force
		$exec = Join-Path $bare 'test-filtered.ps1'
		$r = Resolve-BuildQueueOp -RepoRoot $bare -Op 'mstest' -Exec $exec
		$r.ok | Should -Be $true
		$r.source | Should -Be 'legacy'
		$r.kind | Should -Be 'test'
		$r.hygiene | Should -Be 'dotnet'
		$r.exec | Should -Be $exec
	}

	It 'legacy fallback: no manifest + unknown op fails naming the expected manifest path' {
		$bare = Join-Path $TestDrive ("bare-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
		$null = New-Item -ItemType Directory -Path $bare -Force
		$r = Resolve-BuildQueueOp -RepoRoot $bare -Op 'tauri-build'
		$r.ok | Should -Be $false
		$r.error | Should -Match 'build-queue-ops.json'
	}

	It 'legacy fallback: no manifest + legacy op WITHOUT -Exec fails actionably' {
		$bare = Join-Path $TestDrive ("bare-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
		$null = New-Item -ItemType Directory -Path $bare -Force
		$r = Resolve-BuildQueueOp -RepoRoot $bare -Op 'msbuild'
		$r.ok | Should -Be $false
		$r.error | Should -Match '-Exec is required'
	}
}

Describe 'runner/wrapper profile dispatch - rust-tauri/none never reach dotnet-only hygiene (source guards)' {
	It 'runner gates Reset-CompilerServer behind $profileRecycles' {
		$runnerPath = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
		$source = Get-Content -Raw -Path $runnerPath
		$source | Should -Match '(?s)if\s*\(\$profileRecycles\)\s*\{.*Reset-CompilerServer'
	}

	It 'runner gates Remove-PoisonedArtifacts behind the dotnet-dll poison_sweep' {
		$runnerPath = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
		$source = Get-Content -Raw -Path $runnerPath
		$source | Should -Match "profilePoisonSweep\s+-eq\s+'dotnet-dll'"
	}

	It 'runner gates Stop-DllLockers behind $profileReapsLockers' {
		$runnerPath = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
		$source = Get-Content -Raw -Path $runnerPath
		$source | Should -Match '\$isBuildOp\s+-and\s+\$profileReapsLockers'
	}

	It 'wrapper gates its release recycle behind the profile record' {
		$wrapperPath = Join-Path $PSScriptRoot 'build-queue.ps1'
		$source = Get-Content -Raw -Path $wrapperPath
		$source | Should -Match '(?s)if\s*\(\$wrapperRecycles\)\s*\{.*Reset-CompilerServer'
	}

	It 'Test-BuildProducedNoOutput stays wired for build ops independent of profile (SPEC: profile-independent)' {
		$runnerPath = Join-Path $PSScriptRoot 'build-queue-runner.ps1'
		$source = Get-Content -Raw -Path $runnerPath
		$source | Should -Match 'Test-BuildProducedNoOutput\s+-LogText'
		$source | Should -Not -Match 'profileLogSignatures[^\r\n]*Test-BuildProducedNoOutput'
	}
}

Describe 'Add-BuildQueueStatsEntry (eta-priority-lanes duration ring)' {
	It 'creates the per-op stats ring file on first append' {
		$root = Join-Path $TestDrive 'ring-create'
		$null = New-Item -ItemType Directory -Path $root -Force
		Add-BuildQueueStatsEntry -StateRoot $root -Op 'mstest' -Seq 1 -DurationSeconds 12.3 -ExitCode 0 -EndedAt '2026-07-09T10:00:00Z' | Should -BeTrue
		$path = Join-Path $root 'stats\mstest.json'
		Test-Path $path | Should -BeTrue
		$entries = @(([System.IO.File]::ReadAllText($path) | ConvertFrom-Json) | ForEach-Object { $_ })
		$entries.Count | Should -Be 1
		[double]$entries[0].duration_seconds | Should -Be 12.3
	}

	It 'ring-caps at 20 entries keeping the newest' {
		$root = Join-Path $TestDrive 'ring-cap'
		$null = New-Item -ItemType Directory -Path $root -Force
		1..25 | ForEach-Object {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'msbuild' -Seq $_ -DurationSeconds $_ -ExitCode 0 -EndedAt ''
		}
		$entries = @(([System.IO.File]::ReadAllText((Join-Path $root 'stats\msbuild.json')) | ConvertFrom-Json) | ForEach-Object { $_ })
		$entries.Count | Should -Be 20
		[int]$entries[0].seq | Should -Be 6
		[int]$entries[19].seq | Should -Be 25
	}

	It 'stores failed runs too (the estimator filters, not the ring)' {
		$root = Join-Path $TestDrive 'ring-fail'
		$null = New-Item -ItemType Directory -Path $root -Force
		$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'nxtest' -Seq 1 -DurationSeconds 5 -ExitCode 1 -EndedAt ''
		$entries = @(([System.IO.File]::ReadAllText((Join-Path $root 'stats\nxtest.json')) | ConvertFrom-Json) | ForEach-Object { $_ })
		$entries.Count | Should -Be 1
		[int]$entries[0].exit_code | Should -Be 1
	}

	It 'fails open (returns $false, no throw) for a blank state root' {
		{ Add-BuildQueueStatsEntry -StateRoot ' ' -Op 'mstest' -Seq 1 -DurationSeconds 1 -ExitCode 0 } | Should -Not -Throw
		Add-BuildQueueStatsEntry -StateRoot ' ' -Op 'mstest' -Seq 1 -DurationSeconds 1 -ExitCode 0 | Should -BeFalse
	}
}

Describe 'Get-BuildQueueEta (median estimator)' {
	It 'returns $null when no stats file exists' {
		$root = Join-Path $TestDrive 'eta-none'
		$null = New-Item -ItemType Directory -Path $root -Force
		Get-BuildQueueEta -StateRoot $root -Op 'mstest' | Should -BeNullOrEmpty
	}

	It 'returns $null under 3 successful samples (cold start)' {
		$root = Join-Path $TestDrive 'eta-cold'
		$null = New-Item -ItemType Directory -Path $root -Force
		$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'mstest' -Seq 1 -DurationSeconds 10 -ExitCode 0
		$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'mstest' -Seq 2 -DurationSeconds 20 -ExitCode 0
		Get-BuildQueueEta -StateRoot $root -Op 'mstest' | Should -BeNullOrEmpty
	}

	It 'computes the odd-count median of successful runs' {
		$root = Join-Path $TestDrive 'eta-odd'
		$null = New-Item -ItemType Directory -Path $root -Force
		foreach ($d in @(10, 30, 20)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'msbuild' -Seq $d -DurationSeconds $d -ExitCode 0
		}
		Get-BuildQueueEta -StateRoot $root -Op 'msbuild' | Should -Be 20
	}

	It 'computes the even-count median (mean of the middle pair)' {
		$root = Join-Path $TestDrive 'eta-even'
		$null = New-Item -ItemType Directory -Path $root -Force
		foreach ($d in @(10, 20, 30, 40)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'msbuild' -Seq $d -DurationSeconds $d -ExitCode 0
		}
		Get-BuildQueueEta -StateRoot $root -Op 'msbuild' | Should -Be 25
	}

	It 'excludes failed runs from the estimate' {
		$root = Join-Path $TestDrive 'eta-fail'
		$null = New-Item -ItemType Directory -Path $root -Force
		foreach ($d in @(10, 20, 30)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'nxbuild' -Seq $d -DurationSeconds $d -ExitCode 0
		}
		foreach ($d in @(500, 600, 700)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'nxbuild' -Seq $d -DurationSeconds $d -ExitCode 1
		}
		Get-BuildQueueEta -StateRoot $root -Op 'nxbuild' | Should -Be 20
	}

	It 'uses only the LAST 10 successful runs' {
		$root = Join-Path $TestDrive 'eta-window'
		$null = New-Item -ItemType Directory -Path $root -Force
		1..15 | ForEach-Object {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'mstest' -Seq $_ -DurationSeconds ($_ * 10) -ExitCode 0
		}
		# Last 10 durations: 60..150 -> median = (100 + 110) / 2 = 105
		Get-BuildQueueEta -StateRoot $root -Op 'mstest' | Should -Be 105
	}
}

Describe 'Format-EtaDuration' {
	It 'formats null as a question mark' {
		Format-EtaDuration $null | Should -Be '?'
	}
	It 'formats seconds' {
		Format-EtaDuration 42 | Should -Be '42s'
	}
	It 'formats minutes + seconds' {
		Format-EtaDuration 190 | Should -Be '3m 10s'
	}
	It 'formats hours + minutes' {
		Format-EtaDuration 3900 | Should -Be '1h 5m'
	}
	It 'floors negatives to 0s' {
		Format-EtaDuration -5 | Should -Be '0s'
	}
}

Describe 'Test-LaneClaimEligible (lane admission truth table, D5)' {
	It 'fast head jumps ahead of an older heavy waiter when under the cap' {
		$tickets = @(@{ seq = 3; lane = 'heavy' }, @{ seq = 5; lane = 'fast' })
		Test-LaneClaimEligible -SelfSeq 5 -Tickets $tickets -FastPasses 0 -MaxFastPasses 3 | Should -BeTrue
		Test-LaneClaimEligible -SelfSeq 3 -Tickets $tickets -FastPasses 0 -MaxFastPasses 3 | Should -BeFalse
	}

	It 'K consecutive fast passes hand the slot to the heavy head' {
		$tickets = @(@{ seq = 3; lane = 'heavy' }, @{ seq = 5; lane = 'fast' })
		Test-LaneClaimEligible -SelfSeq 3 -Tickets $tickets -FastPasses 3 -MaxFastPasses 3 | Should -BeTrue
		Test-LaneClaimEligible -SelfSeq 5 -Tickets $tickets -FastPasses 3 -MaxFastPasses 3 | Should -BeFalse
	}

	It 'is FIFO within the heavy lane' {
		$tickets = @(@{ seq = 3; lane = 'heavy' }, @{ seq = 7; lane = 'heavy' })
		Test-LaneClaimEligible -SelfSeq 3 -Tickets $tickets -FastPasses 0 | Should -BeTrue
		Test-LaneClaimEligible -SelfSeq 7 -Tickets $tickets -FastPasses 0 | Should -BeFalse
	}

	It 'is FIFO within the fast lane' {
		$tickets = @(@{ seq = 2; lane = 'fast' }, @{ seq = 9; lane = 'fast' })
		Test-LaneClaimEligible -SelfSeq 2 -Tickets $tickets -FastPasses 0 | Should -BeTrue
		Test-LaneClaimEligible -SelfSeq 9 -Tickets $tickets -FastPasses 0 | Should -BeFalse
	}

	It 'treats a laneless (legacy) ticket as heavy' {
		$tickets = @(@{ seq = 4 }, @{ seq = 6; lane = 'fast' })
		Test-LaneClaimEligible -SelfSeq 4 -Tickets $tickets -FastPasses 3 | Should -BeTrue
	}

	It 'heavy head claims when no fast waiter exists, regardless of the counter' {
		$tickets = @(@{ seq = 8; lane = 'heavy' })
		Test-LaneClaimEligible -SelfSeq 8 -Tickets $tickets -FastPasses 0 | Should -BeTrue
	}

	It 'fast head claims at the cap when NO heavy waiter exists (anti-livelock carve-out)' {
		$tickets = @(@{ seq = 5; lane = 'fast' })
		Test-LaneClaimEligible -SelfSeq 5 -Tickets $tickets -FastPasses 3 | Should -BeTrue
	}

	It 'returns $false for a self seq not present in the ticket set (fail-safe)' {
		Test-LaneClaimEligible -SelfSeq 99 -Tickets @(@{ seq = 1; lane = 'heavy' }) -FastPasses 0 | Should -BeFalse
	}
}

Describe 'Get-FastPassCount / Set-FastPassCount (starvation counter)' {
	It 'reads a missing counter as MaxFastPasses (fast privilege suspended - old behavior, never livelock)' {
		$root = Join-Path $TestDrive 'fp-missing'
		$null = New-Item -ItemType Directory -Path $root -Force
		Get-FastPassCount -StateRoot $root -MaxFastPasses 3 | Should -Be 3
	}

	It 'reads a corrupt counter as MaxFastPasses' {
		$root = Join-Path $TestDrive 'fp-corrupt'
		$null = New-Item -ItemType Directory -Path $root -Force
		[System.IO.File]::WriteAllText((Join-Path $root 'fast-passes.count'), 'garbage')
		Get-FastPassCount -StateRoot $root -MaxFastPasses 3 | Should -Be 3
	}

	It 'round-trips Set then Get' {
		$root = Join-Path $TestDrive 'fp-roundtrip'
		$null = New-Item -ItemType Directory -Path $root -Force
		Set-FastPassCount -StateRoot $root -Count 2 | Should -BeTrue
		Get-FastPassCount -StateRoot $root -MaxFastPasses 3 | Should -Be 2
	}

	It 'reset to 0 reads back 0 (heavy-claim reset)' {
		$root = Join-Path $TestDrive 'fp-reset'
		$null = New-Item -ItemType Directory -Path $root -Force
		$null = Set-FastPassCount -StateRoot $root -Count 3
		$null = Set-FastPassCount -StateRoot $root -Count 0
		Get-FastPassCount -StateRoot $root -MaxFastPasses 3 | Should -Be 0
	}
}

Describe 'Format-BuildQueueBanner carries no ETA (D3 outcome-only pin)' {
	It 'PASS banner contains no eta/remaining/approx text' {
		$b = Format-BuildQueueBanner -Seq 700 -Op mstest -ExitCode 0 -ResultFidelity verified -BuildFidelity verified -Counts @{ passed = 10; failed = 0; total = 10 }
		$b | Should -Not -Match 'eta'
		$b | Should -Not -Match 'remaining'
		$b | Should -Not -Match ([regex]::Escape([string][char]0x2248))
	}

	It 'FAIL banner contains no eta/remaining/approx text' {
		$b = Format-BuildQueueBanner -Seq 701 -Op msbuild -ExitCode 1 -ResultFidelity verified -BuildFidelity verified
		$b | Should -Not -Match 'eta'
		$b | Should -Not -Match 'remaining'
		$b | Should -Not -Match ([regex]::Escape([string][char]0x2248))
	}

	It 'banner formatting function source references no ETA machinery' {
		$source = Get-Content -Raw -Path $script:ModulePath
		$bannerBody = [regex]::Match($source, '(?s)function Format-BuildQueueBanner \{.*?\r?\n\}').Value
		$bannerBody | Should -Not -Match 'Get-BuildQueueEta'
		$bannerBody | Should -Not -Match 'eta-start'
	}
}

Describe 'ops-manifest lane field (D4 - tolerant validation + resolution)' {
	It 'loads a manifest whose ops carry valid lane values' {
		$root = Join-Path $TestDrive 'lane-valid'
		$dir = Join-Path $root '.claude\skill-config'
		$null = New-Item -ItemType Directory -Path $dir -Force
		$json = '{"version":1,"ops":{"mstest":{"exec":"t.ps1","kind":"test","hygiene":"dotnet","skill":"/mstest","deny":[],"lane":"fast"}}}'
		[System.IO.File]::WriteAllText((Join-Path $dir 'build-queue-ops.json'), $json)
		$m = Get-BuildQueueOpsManifest -RepoRoot $root
		$m | Should -Not -BeNullOrEmpty
	}

	It 'tolerates an INVALID lane value (warns, does not reject the manifest)' {
		$root = Join-Path $TestDrive 'lane-invalid'
		$dir = Join-Path $root '.claude\skill-config'
		$null = New-Item -ItemType Directory -Path $dir -Force
		$json = '{"version":1,"ops":{"mstest":{"exec":"t.ps1","kind":"test","hygiene":"dotnet","skill":"/mstest","deny":[],"lane":"purple"}}}'
		[System.IO.File]::WriteAllText((Join-Path $dir 'build-queue-ops.json'), $json)
		$m = Get-BuildQueueOpsManifest -RepoRoot $root 3>$null
		$m | Should -Not -BeNullOrEmpty
	}

	It 'Resolve-BuildQueueOp threads a fast lane from the manifest entry' {
		$root = Join-Path $TestDrive 'lane-resolve-fast'
		$dir = Join-Path $root '.claude\skill-config'
		$null = New-Item -ItemType Directory -Path $dir -Force
		$json = '{"version":1,"ops":{"mstest":{"exec":"t.ps1","kind":"test","hygiene":"dotnet","skill":"/mstest","deny":[],"lane":"fast"}}}'
		[System.IO.File]::WriteAllText((Join-Path $dir 'build-queue-ops.json'), $json)
		$r = Resolve-BuildQueueOp -RepoRoot $root -Op 'mstest'
		$r.ok | Should -BeTrue
		$r.lane | Should -Be 'fast'
	}

	It 'Resolve-BuildQueueOp defaults an ABSENT lane to heavy (legacy manifest byte-compat)' {
		$root = Join-Path $TestDrive 'lane-resolve-absent'
		$dir = Join-Path $root '.claude\skill-config'
		$null = New-Item -ItemType Directory -Path $dir -Force
		$json = '{"version":1,"ops":{"msbuild":{"exec":"b.ps1","kind":"build","hygiene":"dotnet","skill":"/msbuild","deny":[]}}}'
		[System.IO.File]::WriteAllText((Join-Path $dir 'build-queue-ops.json'), $json)
		$r = Resolve-BuildQueueOp -RepoRoot $root -Op 'msbuild'
		$r.ok | Should -BeTrue
		$r.lane | Should -Be 'heavy'
	}

	It 'Resolve-BuildQueueOp normalizes an INVALID lane to heavy' {
		$root = Join-Path $TestDrive 'lane-resolve-invalid'
		$dir = Join-Path $root '.claude\skill-config'
		$null = New-Item -ItemType Directory -Path $dir -Force
		$json = '{"version":1,"ops":{"mstest":{"exec":"t.ps1","kind":"test","hygiene":"dotnet","skill":"/mstest","deny":[],"lane":"purple"}}}'
		[System.IO.File]::WriteAllText((Join-Path $dir 'build-queue-ops.json'), $json)
		$r = Resolve-BuildQueueOp -RepoRoot $root -Op 'mstest' 3>$null
		$r.ok | Should -BeTrue
		$r.lane | Should -Be 'heavy'
	}

	It 'legacy (no-manifest) resolution rides the heavy lane' {
		$root = Join-Path $TestDrive 'lane-resolve-legacy'
		$null = New-Item -ItemType Directory -Path $root -Force
		$r = Resolve-BuildQueueOp -RepoRoot $root -Op 'mstest' -Exec 'x.ps1'
		$r.ok | Should -BeTrue
		$r.lane | Should -Be 'heavy'
	}

	It 'the committed Cognito manifest classifies test ops fast and build ops heavy' {
		$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
		$manifestPath = Join-Path $repoRoot 'repos\cognito-forms\.claude\skill-config\build-queue-ops.json'
		$m = [System.IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
		$m.ops.mstest.lane | Should -Be 'fast'
		$m.ops.nxtest.lane | Should -Be 'fast'
		$m.ops.msbuild.lane | Should -Be 'heavy'
		$m.ops.nxbuild.lane | Should -Be 'heavy'
	}
}

Describe 'Get-BuildQueueWaitEta (D3 composition)' {
	It 'returns 0 eta-start with an idle queue and a null eta-done for an unknown self op' {
		$root = Join-Path $TestDrive 'weta-idle'
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'tickets') -Force
		$eta = Get-BuildQueueWaitEta -StateRoot $root -SelfSeq 5 -SelfOp 'mstest' -SelfLane 'fast'
		$eta.eta_start_seconds | Should -Be 0
		$eta.eta_done_seconds | Should -BeNullOrEmpty
	}

	It 'composes active-remaining + eligible-ahead with warm stats' {
		$root = Join-Path $TestDrive 'weta-warm'
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'tickets') -Force
		foreach ($d in @(100, 100, 100)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'msbuild' -Seq $d -DurationSeconds $d -ExitCode 0
		}
		foreach ($d in @(50, 50, 50)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'mstest' -Seq $d -DurationSeconds $d -ExitCode 0
		}
		# Active msbuild started just now (remaining ~= 100); one heavy msbuild waiter ahead of self.
		$lock = '{"seq":1,"build_pid":' + $PID + ',"op":"msbuild","started_at":"' + (Get-Date).ToString('o') + '"}'
		[System.IO.File]::WriteAllText((Join-Path $root 'active.lock'), $lock)
		$t = '{"seq":2,"pid":' + $PID + ',"op":"msbuild","lane":"heavy","started_wait_at":"' + (Get-Date).ToString('o') + '"}'
		[System.IO.File]::WriteAllText((Join-Path $root 'tickets\2.json'), $t)
		$eta = Get-BuildQueueWaitEta -StateRoot $root -SelfSeq 3 -SelfOp 'mstest' -SelfLane 'heavy'
		$eta.eta_start_seconds | Should -BeGreaterThan 190
		$eta.eta_start_seconds | Should -BeLessThan 210
		$eta.eta_done_seconds | Should -BeGreaterThan 240
		$eta.eta_done_seconds | Should -BeLessThan 260
	}

	It 'collapses to null when ANY term lacks history (unknown-term honesty)' {
		$root = Join-Path $TestDrive 'weta-collapse'
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'tickets') -Force
		$lock = '{"seq":1,"build_pid":' + $PID + ',"op":"cold-op","started_at":"' + (Get-Date).ToString('o') + '"}'
		[System.IO.File]::WriteAllText((Join-Path $root 'active.lock'), $lock)
		$eta = Get-BuildQueueWaitEta -StateRoot $root -SelfSeq 3 -SelfOp 'mstest' -SelfLane 'fast'
		$eta.eta_start_seconds | Should -BeNullOrEmpty
		$eta.eta_done_seconds | Should -BeNullOrEmpty
	}

	It 'a fast self skips heavy waiters ahead (lane-order approximation)' {
		$root = Join-Path $TestDrive 'weta-fastskip'
		$null = New-Item -ItemType Directory -Path (Join-Path $root 'tickets') -Force
		foreach ($d in @(50, 50, 50)) {
			$null = Add-BuildQueueStatsEntry -StateRoot $root -Op 'mstest' -Seq $d -DurationSeconds $d -ExitCode 0
		}
		# No active lock; one heavy waiter with a LOWER seq that fast-self jumps.
		$t = '{"seq":2,"pid":' + $PID + ',"op":"msbuild","lane":"heavy","started_wait_at":"' + (Get-Date).ToString('o') + '"}'
		[System.IO.File]::WriteAllText((Join-Path $root 'tickets\2.json'), $t)
		$eta = Get-BuildQueueWaitEta -StateRoot $root -SelfSeq 3 -SelfOp 'mstest' -SelfLane 'fast'
		$eta.eta_start_seconds | Should -Be 0
		$eta.eta_done_seconds | Should -Be 50
	}
}

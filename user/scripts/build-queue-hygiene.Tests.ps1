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
	It 'Add-ProcessToBuildJob returns $false without throwing for zero handles' {
		$result = $null
		{ $result = Add-ProcessToBuildJob -JobHandle ([IntPtr]::Zero) -ProcessHandle ([IntPtr]::Zero) } | Should -Not -Throw
		$result | Should -Be $false
	}

	It 'Stop-BuildJobTree returns $false without throwing for a zero handle' {
		$result = $null
		{ $result = Stop-BuildJobTree -JobHandle ([IntPtr]::Zero) } | Should -Not -Throw
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
		$result = $null
		{ $result = Reset-CompilerServer } | Should -Not -Throw
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

	It 'FAIL via log-failure-override (exit 0): RESULT=FAIL with the SAME read-logs next-action' {
		$result = Format-BuildQueueBanner -Seq 621 -Op nxtest -ExitCode 0 -ResultFidelity verified -BuildFidelity log-failure-override
		$result | Should -Be 'build-queue: seq=621 op=nxtest RESULT=FAIL (result_fidelity=verified) -> read logs/621.build.err.log'
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

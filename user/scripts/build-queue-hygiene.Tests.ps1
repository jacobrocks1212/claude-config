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

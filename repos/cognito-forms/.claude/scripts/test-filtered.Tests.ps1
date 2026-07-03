BeforeAll {
    . "$PSScriptRoot\test-filtered.ps1"
}

Describe "Test-SummaryLine" {
    It "recognizes a modern passing summary line and parses counts" {
        $result = Test-SummaryLine "Passed!  - Failed: 0, Passed: 42, Skipped: 0, Total: 42, Duration: 1 s"
        $result.isSummary | Should -Be $true
        $result.passed | Should -Be 42
        $result.failed | Should -Be 0
        $result.total | Should -Be 42
    }

    It "recognizes a modern failing summary line and parses counts" {
        $result = Test-SummaryLine "Failed! - Failed: 3, Passed: 39, Skipped: 0, Total: 42"
        $result.isSummary | Should -Be $true
        $result.passed | Should -Be 39
        $result.failed | Should -Be 3
        $result.total | Should -Be 42
    }

    It "still recognizes legacy 'Test Run Passed.' summary line" {
        $result = Test-SummaryLine "Test Run Passed."
        $result.isSummary | Should -Be $true
    }

    It "still recognizes legacy 'Total tests:' summary line" {
        $result = Test-SummaryLine "Total tests: 42"
        $result.isSummary | Should -Be $true
    }

    It "still recognizes legacy '    Passed:' summary line" {
        $result = Test-SummaryLine "    Passed: 42"
        $result.isSummary | Should -Be $true
    }

    It "does not recognize a non-summary line" {
        $result = Test-SummaryLine "Building..."
        $result.isSummary | Should -Be $false
    }
}

Describe "Test-StaleTestDll" {
    BeforeAll {
        $script:TestRoot = Join-Path $env:TEMP "test-filtered-stale-dll-$([guid]::NewGuid())"
        New-Item -ItemType Directory -Path $script:TestRoot -Force | Out-Null
    }

    AfterAll {
        Remove-Item -Path $script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    It "returns false when the DLL is newer than all source files" {
        $projectDir = Join-Path $script:TestRoot "fresh"
        New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
        $sourceFile = Join-Path $projectDir "Foo.cs"
        Set-Content -Path $sourceFile -Value "class Foo {}"

        Start-Sleep -Milliseconds 50
        $dllPath = Join-Path $projectDir "Foo.dll"
        Set-Content -Path $dllPath -Value "binary"

        $result = Test-StaleTestDll -DllPath $dllPath -ProjectDir $projectDir
        $result | Should -Be $false
    }

    It "returns true when a source file is newer than the DLL" {
        $projectDir = Join-Path $script:TestRoot "stale"
        New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
        $dllPath = Join-Path $projectDir "Foo.dll"
        Set-Content -Path $dllPath -Value "binary"

        Start-Sleep -Milliseconds 50
        $sourceFile = Join-Path $projectDir "Foo.cs"
        Set-Content -Path $sourceFile -Value "class Foo {}"

        $result = Test-StaleTestDll -DllPath $dllPath -ProjectDir $projectDir
        $result | Should -Be $true
    }

    It "returns true when the DLL does not exist" {
        $projectDir = Join-Path $script:TestRoot "missing"
        New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
        $dllPath = Join-Path $projectDir "DoesNotExist.dll"

        $result = Test-StaleTestDll -DllPath $dllPath -ProjectDir $projectDir
        $result | Should -Be $true
    }

    It "does not throw when the DLL is missing" {
        $projectDir = Join-Path $script:TestRoot "missing-no-throw"
        New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
        $dllPath = Join-Path $projectDir "DoesNotExist.dll"

        { Test-StaleTestDll -DllPath $dllPath -ProjectDir $projectDir } | Should -Not -Throw
    }
}

Describe "Resolve-TestDllPath" {
    BeforeAll {
        $script:TestRoot = Join-Path $env:TEMP "resolve-test-dll-$([guid]::NewGuid())"
        New-Item -ItemType Directory -Path $script:TestRoot -Force | Out-Null
    }

    AfterAll {
        Remove-Item -Path $script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    It "resolves a bin\Debug\<name>.dll layout to that path" {
        $projectDir = Join-Path $script:TestRoot "debug-layout"
        $debugDir = Join-Path (Join-Path $projectDir "bin") "Debug"
        New-Item -ItemType Directory -Path $debugDir -Force | Out-Null
        $expectedPath = Join-Path $debugDir "Foo.dll"
        Set-Content -Path $expectedPath -Value "binary"

        $result = Resolve-TestDllPath -ProjectDir $projectDir -TestDll "Foo"
        $result | Should -Be $expectedPath
    }

    It "resolves a bin\<name>.dll layout with no Debug subdirectory to the bin copy" {
        $projectDir = Join-Path $script:TestRoot "bin-only-layout"
        $binDir = Join-Path $projectDir "bin"
        New-Item -ItemType Directory -Path $binDir -Force | Out-Null
        $expectedPath = Join-Path $binDir "Foo.dll"
        Set-Content -Path $expectedPath -Value "binary"

        $result = Resolve-TestDllPath -ProjectDir $projectDir -TestDll "Foo"
        $result | Should -Be $expectedPath
    }

    It "resolves multiple copies to the shallowest bin copy even when a deeper copy is newer" {
        $projectDir = Join-Path $script:TestRoot "multi-copy-layout"
        $binDir = Join-Path $projectDir "bin"
        $autoTestDir = Join-Path $binDir "AutoTest"
        New-Item -ItemType Directory -Path $autoTestDir -Force | Out-Null

        $shallowPath = Join-Path $binDir "Foo.dll"
        Set-Content -Path $shallowPath -Value "binary"

        Start-Sleep -Milliseconds 50
        $deepPath = Join-Path $autoTestDir "Foo.dll"
        Set-Content -Path $deepPath -Value "binary"

        $result = Resolve-TestDllPath -ProjectDir $projectDir -TestDll "Foo"
        $result | Should -Be $shallowPath
    }

    It "returns the conventional bin\Debug path without throwing when the DLL has not been built" {
        $projectDir = Join-Path $script:TestRoot "not-built-layout"
        New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
        $expectedPath = Join-Path (Join-Path (Join-Path $projectDir "bin") "Debug") "Foo.dll"

        $result = Resolve-TestDllPath -ProjectDir $projectDir -TestDll "Foo"
        $result | Should -Be $expectedPath

        { Resolve-TestDllPath -ProjectDir $projectDir -TestDll "Foo" } | Should -Not -Throw
    }
}

Describe "Get-TestOutcomeExitCode" {
    It "returns 5 when a summary was seen and Total is 0 (zero-match filter)" {
        $result = Get-TestOutcomeExitCode -SummarySeen $true -Total 0 -ResultLineCount 0 -DotnetExit 0
        $result | Should -Be 5
    }

    It "returns 0 when a summary was seen with a nonzero Total and DotnetExit is 0 (all-pass)" {
        $result = Get-TestOutcomeExitCode -SummarySeen $true -Total 42 -ResultLineCount 42 -DotnetExit 0
        $result | Should -Be 0
    }

    It "passes through a nonzero DotnetExit when a summary was seen with a nonzero Total (real failure)" {
        $result = Get-TestOutcomeExitCode -SummarySeen $true -Total 39 -ResultLineCount 39 -DotnetExit 1
        $result | Should -Be 1
    }

    It "returns 3 when no summary was seen and no result lines were captured (genuine zero-output)" {
        $result = Get-TestOutcomeExitCode -SummarySeen $false -Total $null -ResultLineCount 0 -DotnetExit 0
        $result | Should -Be 3
    }
}

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

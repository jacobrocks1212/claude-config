BeforeAll {
    . "$PSScriptRoot\build-filtered.ps1"
}

Describe "Get-ProjectsMissingAssets" {
    BeforeAll {
        $script:TestRoot = Join-Path $env:TEMP "build-filtered-assets-$([guid]::NewGuid())"
        New-Item -ItemType Directory -Path $script:TestRoot -Force | Out-Null
    }

    AfterAll {
        Remove-Item -Path $script:TestRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    It "returns nothing for a single project whose obj\project.assets.json exists" {
        $projDir = Join-Path $script:TestRoot "restored-proj"
        $objDir = Join-Path $projDir "obj"
        New-Item -ItemType Directory -Path $objDir -Force | Out-Null
        Set-Content -Path (Join-Path $objDir "project.assets.json") -Value "{}"
        $target = Join-Path $projDir "Foo.csproj"
        Set-Content -Path $target -Value "<Project />"

        $result = @(Get-ProjectsMissingAssets -Target $target)
        $result.Count | Should -Be 0
    }

    It "reports a single project whose obj\ is wiped" {
        $projDir = Join-Path $script:TestRoot "wiped-proj"
        New-Item -ItemType Directory -Path $projDir -Force | Out-Null
        $target = Join-Path $projDir "Foo.csproj"
        Set-Content -Path $target -Value "<Project />"

        $result = @(Get-ProjectsMissingAssets -Target $target)
        $result | Should -Contain "Foo.csproj"
    }

    It "reports only the wiped project from a solution listing several" {
        $slnDir = Join-Path $script:TestRoot "sln-mixed"
        $restoredDir = Join-Path $slnDir "Restored"
        $wipedDir = Join-Path $slnDir "Wiped"
        New-Item -ItemType Directory -Path (Join-Path $restoredDir "obj") -Force | Out-Null
        New-Item -ItemType Directory -Path $wipedDir -Force | Out-Null
        Set-Content -Path (Join-Path (Join-Path $restoredDir "obj") "project.assets.json") -Value "{}"
        Set-Content -Path (Join-Path $restoredDir "Restored.csproj") -Value "<Project />"
        Set-Content -Path (Join-Path $wipedDir "Wiped.csproj") -Value "<Project />"
        $sln = Join-Path $slnDir "All.sln"
        @(
            'Microsoft Visual Studio Solution File, Format Version 12.00'
            'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Restored", "Restored\Restored.csproj", "{11111111-1111-1111-1111-111111111111}"'
            'EndProject'
            'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Wiped", "Wiped\Wiped.csproj", "{22222222-2222-2222-2222-222222222222}"'
            'EndProject'
        ) | Set-Content -Path $sln

        $result = @(Get-ProjectsMissingAssets -Target $sln)
        $result | Should -Contain "Wiped\Wiped.csproj"
        $result | Should -Not -Contain "Restored\Restored.csproj"
    }

    It "returns nothing when the solution file does not exist" {
        $result = @(Get-ProjectsMissingAssets -Target (Join-Path $script:TestRoot "missing.sln"))
        $result.Count | Should -Be 0
    }

    It "does not throw on a malformed target path" {
        { Get-ProjectsMissingAssets -Target "Foo.csproj" } | Should -Not -Throw
    }
}

Describe "Get-BuildArgs" {
    It "keeps --no-restore for the normal incremental case" {
        $result = @(Get-BuildArgs -BuildTarget "C:\r\Cognito.sln" -RestoreRequested $false -MissingAssets @())
        $result | Should -Contain "--no-restore"
    }

    It "drops --no-restore when a target project has a wiped obj\ so the build restores instead of silently no-oping" {
        $result = @(Get-BuildArgs -BuildTarget "C:\r\Cognito.sln" -RestoreRequested $false -MissingAssets @("Wiped\Wiped.csproj"))
        $result | Should -Not -Contain "--no-restore"
    }

    It "drops --no-restore when restore was explicitly requested" {
        $result = @(Get-BuildArgs -BuildTarget "C:\r\Cognito.sln" -RestoreRequested $true -MissingAssets @())
        $result | Should -Not -Contain "--no-restore"
    }

    It "always targets dotnet build with minimal verbosity" {
        $result = @(Get-BuildArgs -BuildTarget "C:\r\Foo.csproj" -RestoreRequested $false -MissingAssets @())
        $result[0] | Should -Be "build"
        $result[1] | Should -Be "C:\r\Foo.csproj"
        $result | Should -Contain "-verbosity:minimal"
    }
}

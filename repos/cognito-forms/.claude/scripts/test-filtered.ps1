# Run tests with filtered output using dotnet test
# Shows: passed/failed test names, error messages, and summary
# Streams output in real-time instead of buffering

param(
    [string]$Filter = "",
    [string]$TestDll = "Cognito.UnitTests"
)

$ErrorActionPreference = "Continue"

# Recognizes both legacy and modern `dotnet test` summary lines and parses
# pass/fail/total counts where available. Pure function - safe to dot-source
# and unit test without invoking dotnet.
function Test-SummaryLine([string]$line) {
    $modernMatch = [regex]::Match($line, '^\s*(Passed|Failed)!\s+-\s+Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+),\s*Total:\s*(\d+)')
    if ($modernMatch.Success) {
        return @{
            isSummary = $true
            failed    = [int]$modernMatch.Groups[2].Value
            passed    = [int]$modernMatch.Groups[3].Value
            total     = [int]$modernMatch.Groups[5].Value
        }
    }

    if ($line -match 'Test Run (Passed|Failed)|^Total tests:|^\s+Passed\s*:|^\s+Failed\s*:') {
        return @{
            isSummary = $true
            failed    = $null
            passed    = $null
            total     = $null
        }
    }

    return @{
        isSummary = $false
        failed    = $null
        passed    = $null
        total     = $null
    }
}

function Test-StaleTestDll([string]$DllPath, [string]$ProjectDir) {
    try {
        if (-not (Test-Path $DllPath)) {
            return $true
        }

        $dllTime = (Get-Item $DllPath).LastWriteTime

        $resultsDir = Join-Path $HOME '.claude\state\build-queue\results'
        try {
            if (Test-Path $resultsDir) {
                $latestResult = Get-ChildItem -Path $resultsDir -Filter '*.json' -ErrorAction Stop |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 1
                if ($latestResult) {
                    $resultJson = Get-Content -Raw -Path $latestResult.FullName -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
                    if ($resultJson.hygiene.build_fidelity -eq 'log-failure-override') {
                        return $true
                    }
                }
            }
        } catch {
        }

        if (-not (Test-Path $ProjectDir)) {
            return $true
        }

        $sourceFiles = Get-ChildItem -Path $ProjectDir -Recurse -Include *.cs,*.csproj -ErrorAction Stop
        if (-not $sourceFiles) {
            return $false
        }

        $newestSource = ($sourceFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime

        return $newestSource -gt $dllTime
    } catch {
        return $true
    }
}

function Resolve-TestDllPath([string]$ProjectDir, [string]$TestDll) {
    $binDir = Join-Path $ProjectDir 'bin'
    $fallback = Join-Path (Join-Path $binDir 'Debug') "$TestDll.dll"

    try {
        if (-not (Test-Path $binDir)) {
            return $fallback
        }

        $matches = Get-ChildItem -Path $binDir -Recurse -Filter "$TestDll.dll" -File -ErrorAction SilentlyContinue
        if (-not $matches) {
            return $fallback
        }

        $best = $matches | Sort-Object `
            @{ Expression = { ($_.FullName.Substring($binDir.Length).Trim('\').Split('\')).Count } }, `
            @{ Expression = 'LastWriteTime'; Descending = $true } |
            Select-Object -First 1

        return $best.FullName
    } catch {
        return $fallback
    }
}

function Invoke-Main {
    $projectRoot = (git rev-parse --show-toplevel 2>$null) -replace '/', '\'
    if (-not $projectRoot) {
        Write-Error "Not inside a git repository"
        exit 1
    }
    $testProjectPath = "$projectRoot\$TestDll\$TestDll.csproj"

    $testDllProjectDir = "$projectRoot\$TestDll"
    $testDllPath = Resolve-TestDllPath -ProjectDir $testDllProjectDir -TestDll $TestDll
    if (Test-StaleTestDll -DllPath $testDllPath -ProjectDir $testDllProjectDir) {
        Write-Host "WARN: $testDllPath is stale or missing relative to source changes. Run /msbuild first to rebuild before trusting test results." -ForegroundColor Yellow
        exit 4
    }

    Write-Host "Running tests$(if ($Filter) { " (filter: $Filter)" })..." -ForegroundColor Cyan

    $inFailBlock = $false
    $failBlockLines = 0
    $resultLineCount = 0
    $summarySeen = $false

    # Stream output line by line using pipeline instead of buffering
    $dotnetArgs = @("test", $testProjectPath, "--no-build", "--verbosity", "normal")
    if ($Filter) {
        $dotnetArgs += "--filter"
        $dotnetArgs += $Filter
    }

    & dotnet @dotnetArgs 2>&1 | ForEach-Object {
        $line = $_.ToString()

        # Passed test - show it
        if ($line -match '^\s+Passed\s+\S') {
            Write-Host $line -ForegroundColor Green
            $inFailBlock = $false
            $resultLineCount++
        }
        # Failed test - start capturing block
        elseif ($line -match '^\s+Failed\s+\S') {
            Write-Host $line -ForegroundColor Red
            $inFailBlock = $true
            $failBlockLines = 0
            $resultLineCount++
        }
        # Inside a fail block - show error details (limit lines)
        elseif ($inFailBlock -and $failBlockLines -lt 6) {
            if ($line -match 'Error Message:|Stack Trace:') {
                Write-Host $line -ForegroundColor Yellow
                $failBlockLines++
            }
            elseif ($line -match '\S') {
                Write-Host $line -ForegroundColor Red
                $failBlockLines++
            }
        }
        # Summary lines
        else {
            $summary = Test-SummaryLine $line
            if ($summary.isSummary) {
                $inFailBlock = $false
                $summarySeen = $true
                if ($line -match 'Failed') {
                    Write-Host $line -ForegroundColor Red
                } else {
                    Write-Host $line -ForegroundColor Green
                }
                if ($null -ne $summary.total) {
                    Write-Host "Results: Passed=$($summary.passed) Failed=$($summary.failed) Total=$($summary.total)" -ForegroundColor Cyan
                }
            }
        }
    }

    $dotnetExit = $LASTEXITCODE

    # Distinguished exit for a zero-output run
    if ($resultLineCount -eq 0 -and -not $summarySeen) {
        Write-Host "WARN: No test results captured (zero tests matched filter or summary not parsed)" -ForegroundColor Yellow
        exit 3
    }

    exit $dotnetExit
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-Main
}

# Run tests with filtered output using dotnet test
# Shows: passed/failed test names, error messages, and summary
# Streams output in real-time instead of buffering

param(
    [string]$Filter = "",
    [string]$TestDll = "Cognito.UnitTests"
)

$ErrorActionPreference = "Continue"
$projectRoot = (git rev-parse --show-toplevel 2>$null) -replace '/', '\'
if (-not $projectRoot) {
    Write-Error "Not inside a git repository"
    exit 1
}
$testProjectPath = "$projectRoot\$TestDll\$TestDll.csproj"

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
    elseif ($line -match 'Test Run (Passed|Failed)|^Total tests:|^\s+Passed\s*:|^\s+Failed\s*:') {
        $inFailBlock = $false
        $summarySeen = $true
        if ($line -match 'Failed') {
            Write-Host $line -ForegroundColor Red
        } else {
            Write-Host $line -ForegroundColor Green
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

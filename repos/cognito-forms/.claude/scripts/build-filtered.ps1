# Build Cognito solution with filtered output
# Only shows errors and build summary (no warnings, no project output)
# Streams output in real-time instead of buffering

param(
    [switch]$Restore,
    [switch]$Test,
    [string]$TestProject = "Cognito.Forms.UnitTests/Cognito.Forms.UnitTests.csproj",
    [string]$Project = ""
)

$ErrorActionPreference = "Continue"
$projectRoot = (git rev-parse --show-toplevel 2>$null) -replace '/', '\'
if (-not $projectRoot) {
    Write-Error "Not inside a git repository"
    exit 1
}

# Build
Write-Host "Building solution..." -ForegroundColor Cyan

$buildTarget = if ($Project) { "$projectRoot\$Project" } else { "$projectRoot\Cognito.sln" }
$buildArgs = @("build", $buildTarget, "-verbosity:minimal")
if (-not $Restore) {
    $buildArgs += "--no-restore"
}

$hasOutput = $false
$pattern = '(error\s+(CS|MSB|NU|BC)\d+|Build (FAILED|SUCCEEDED)|^\s*\d+\s+Error|failed\s*$|---->)'

# Stream build output line by line
& dotnet @buildArgs 2>&1 | ForEach-Object {
    $line = $_.ToString()
    if ($line -match $pattern) {
        $hasOutput = $true
        if ($line -match 'error|failed|FAILED') {
            Write-Host $line -ForegroundColor Red
        } elseif ($line -match 'SUCCEEDED') {
            Write-Host $line -ForegroundColor Green
        } else {
            Write-Host $line
        }
    }
}

if (-not $hasOutput) {
    # No errors or summary found - likely successful
    Write-Host "Build SUCCEEDED (0 Errors)" -ForegroundColor Green
}

# Run tests if requested
if ($Test) {
    Write-Host "`nRunning tests..." -ForegroundColor Cyan

    $testArgs = @("test", "$projectRoot\$TestProject", "--no-build", "--verbosity", "normal")
    $inFailBlock = $false
    $failBlockLines = 0

    # Stream test output line by line
    & dotnet @testArgs 2>&1 | ForEach-Object {
        $line = $_.ToString()

        # Passed test - show it
        if ($line -match '^\s+Passed\s+\S') {
            Write-Host $line -ForegroundColor Green
            $inFailBlock = $false
        }
        # Failed test - start capturing block
        elseif ($line -match '^\s+Failed\s+\S') {
            Write-Host $line -ForegroundColor Red
            $inFailBlock = $true
            $failBlockLines = 0
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
            if ($line -match 'Failed') {
                Write-Host $line -ForegroundColor Red
            } else {
                Write-Host $line -ForegroundColor Green
            }
        }
    }
}

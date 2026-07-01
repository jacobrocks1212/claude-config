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

# Tracks whether the streamed log itself asserts failure, independent of dotnet's
# exit code. Under MSB3027/MSB3021 (DLL copy-lock) dotnet can print "Build FAILED"
# yet still exit 0 - $LASTEXITCODE alone is not trustworthy in that case.
$buildLogFailure = $false

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

    if ($line -match 'Build FAILED' -or $line -match 'error MSB3027' -or $line -match 'error MSB3021') {
        $buildLogFailure = $true
    } elseif ($line -match '^\s*(\d+)\s+Error') {
        if ([int]$matches[1] -gt 0) {
            $buildLogFailure = $true
        }
    }
}

if (-not $hasOutput) {
    # No errors or summary found - likely successful
    Write-Host "Build SUCCEEDED (0 Errors)" -ForegroundColor Green
}

# dotnet's own exit code, captured immediately after the stream completes.
$buildExit = $LASTEXITCODE

# The build is a failure if the log itself asserted failure OR dotnet exited
# nonzero. Prefer dotnet's nonzero code when present; otherwise fall back to 1
# so a log-detected failure never masquerades as exit 0.
if ($buildLogFailure -or $buildExit -ne 0) {
    $effectiveExit = if ($buildExit -ne 0) { $buildExit } else { 1 }
} else {
    $effectiveExit = 0
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

    # Combine severities: a nonzero test exit must still surface even if the
    # build itself succeeded, and a build failure must not be masked by a
    # passing test run.
    $testExit = $LASTEXITCODE
    if ($testExit -ne 0) {
        $effectiveExit = $testExit
    }
}

exit $effectiveExit

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

# Returns the projects under $Target whose obj\project.assets.json is missing
# (a wiped obj/). Building such a target with --no-restore silently compiles
# nothing, so the caller must restore first. For a .sln target the project
# list is parsed from the solution file; for a single project the target's own
# directory is checked. Any probe error returns an empty list (fail toward the
# current --no-restore behavior). Pure filesystem probe - safe to dot-source
# and unit test without invoking dotnet.
function Get-ProjectsMissingAssets {
    param([string]$Target)
    $missing = @()
    try {
        if ($Target -like '*.sln') {
            if (-not (Test-Path $Target)) { return $missing }
            $slnDir = Split-Path -Parent $Target
            foreach ($line in (Get-Content $Target)) {
                if ($line -match '=\s*"[^"]+",\s*"([^"]+\.csproj)"') {
                    $rel = $matches[1] -replace '/', '\'
                    $projDir = Split-Path -Parent (Join-Path $slnDir $rel)
                    if (-not $projDir) { continue }
                    if (-not (Test-Path (Join-Path $projDir 'obj\project.assets.json'))) {
                        $missing += $rel
                    }
                }
            }
        } else {
            $projDir = Split-Path -Parent $Target
            if ($projDir -and -not (Test-Path (Join-Path $projDir 'obj\project.assets.json'))) {
                $missing += (Split-Path -Leaf $Target)
            }
        }
    } catch {
        return @()
    }
    return $missing
}

# Decides the dotnet build argument list. --no-restore stays the default for
# the normal incremental case, but is dropped when any target project has a
# wiped obj/ (missing project.assets.json) so the build restores inline
# instead of silently producing nothing. Pure - safe to dot-source and unit
# test without invoking dotnet.
function Get-BuildArgs {
    param(
        [string]$BuildTarget,
        [bool]$RestoreRequested,
        [string[]]$MissingAssets
    )
    $buildArgList = @("build", $BuildTarget, "-verbosity:minimal")
    if (-not $RestoreRequested -and (@($MissingAssets).Count -eq 0)) {
        $buildArgList += "--no-restore"
    }
    return $buildArgList
}

function Invoke-Main {
    $projectRoot = (git rev-parse --show-toplevel 2>$null) -replace '/', '\'
    if (-not $projectRoot) {
        Write-Error "Not inside a git repository"
        exit 1
    }

    # Build
    Write-Host "Building solution..." -ForegroundColor Cyan

    $buildTarget = if ($Project) { "$projectRoot\$Project" } else { "$projectRoot\Cognito.sln" }

    $missingAssets = @()
    if (-not $Restore) {
        $missingAssets = @(Get-ProjectsMissingAssets -Target $buildTarget)
        if ($missingAssets.Count -gt 0) {
            Write-Host "project.assets.json missing (wiped obj/) for: $($missingAssets -join ', ')" -ForegroundColor Yellow
            Write-Host "Restoring inline instead of --no-restore (a --no-restore build against a wiped obj/ silently produces nothing)..." -ForegroundColor Yellow
        }
    }
    $buildArgs = @(Get-BuildArgs -BuildTarget $buildTarget -RestoreRequested:([bool]$Restore) -MissingAssets $missingAssets)

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
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-Main
}

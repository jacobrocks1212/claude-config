# Run frontend tests with filtered output using Nx/Jest
# Shows: PASS/FAIL, test names, error details, and summary
# Streams output in real-time instead of buffering

param(
    [string]$Project = "cognito-spa",
    [string]$Pattern = "",
    [string]$Filter = "",
    [int]$FailureLines = 10,
    [switch]$NoCoverage
)

$ErrorActionPreference = "Continue"
$gitRoot = (git rev-parse --show-toplevel 2>$null) -replace '/', '\'
if (-not $gitRoot) {
    Write-Error "Not inside a git repository"
    exit 1
}
$projectRoot = Join-Path $gitRoot "Cognito.Web.Client"

Push-Location $projectRoot
try {
    $displayFilter = if ($Pattern) { " (pattern: $Pattern)" } elseif ($Filter) { " (filter: $Filter)" } else { "" }
    Write-Host "Running tests for $Project$displayFilter..." -ForegroundColor Cyan

    # Build nx test args
    $nxArgs = @("test", $Project)

    # Add passthrough args after --
    $passthroughArgs = @()
    if ($Pattern) {
        $passthroughArgs += "--testPathPattern=`"$Pattern`""
    }
    if ($Filter) {
        $passthroughArgs += "--testNamePattern=`"$Filter`""
    }
    if ($NoCoverage) {
        $passthroughArgs += "--no-coverage"
    }

    if ($passthroughArgs.Count -gt 0) {
        $nxArgs += "--"
        $nxArgs += $passthroughArgs
    }

    $inFailBlock = $false
    $failBlockLines = 0
    $inSummary = $false

    # Patterns
    $passPatterns = @(
        'PASS\s+\S',
        '^\s*[✓√]\s+'
    )
    $passPattern = $passPatterns -join '|'

    $failPatterns = @(
        'FAIL\s+\S',
        '^\s*[✗×●]\s+'
    )
    $failPattern = $failPatterns -join '|'

    $summaryPatterns = @(
        '^Tests?:',
        '^Test Suites?:',
        '^Time:',
        '^Ran all',
        'Tests:\s+\d+',
        '\d+ passed',
        '\d+ failed'
    )
    $summaryPattern = $summaryPatterns -join '|'

    $errorDetailPatterns = @(
        'Expected:',
        'Received:',
        'expect\(',
        'at Object\.',
        'at .+\.spec\.',
        'at .+\.test\.'
    )
    $errorDetailPattern = $errorDetailPatterns -join '|'

    # Stream test output line by line
    & npx nx @nxArgs 2>&1 | ForEach-Object {
        $line = $_.ToString()

        # PASS line
        if ($line -match $passPattern) {
            Write-Host $line -ForegroundColor Green
            $inFailBlock = $false
            $inSummary = $false
        }
        # FAIL line - start capturing block
        elseif ($line -match $failPattern) {
            Write-Host $line -ForegroundColor Red
            $inFailBlock = $true
            $failBlockLines = 0
            $inSummary = $false
        }
        # Inside a fail block - show error details (limit lines)
        elseif ($inFailBlock -and $failBlockLines -lt $FailureLines) {
            if ($line -match $errorDetailPattern -or $line -match 'Error:|expect|at ') {
                Write-Host $line -ForegroundColor Yellow
                $failBlockLines++
            }
            elseif ($line -match '\S' -and $line -notmatch '^\s*$') {
                Write-Host $line -ForegroundColor Red
                $failBlockLines++
            }
        }
        # Summary lines
        elseif ($line -match $summaryPattern) {
            $inFailBlock = $false
            $inSummary = $true
            if ($line -match 'failed|FAIL') {
                Write-Host $line -ForegroundColor Red
            } elseif ($line -match 'passed|PASS') {
                Write-Host $line -ForegroundColor Green
            } else {
                Write-Host $line -ForegroundColor Cyan
            }
        }
        # Continue showing summary block
        elseif ($inSummary -and $line -match '\S') {
            if ($line -match 'failed') {
                Write-Host $line -ForegroundColor Red
            } elseif ($line -match 'passed') {
                Write-Host $line -ForegroundColor Green
            } else {
                Write-Host $line -ForegroundColor Cyan
            }
        }
    }
} finally {
    Pop-Location
}

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
        # A '|'-alternation pattern (e.g. "FileA|FileB|FileC") cannot be passed as a
        # single --testPathPattern value on Windows: nx spawns the jest executor as a
        # child process through cmd.exe, and a bare '|' on that inner command line is
        # interpreted as a shell pipe operator (splitting the command and failing
        # silently with zero jest output). Jest treats multiple positional arguments as
        # testPathPattern regexes combined with OR, so splitting the alternation into
        # separate positional args is semantically identical to a single "A|B|C" regex
        # while keeping every argument free of shell-hostile characters. A pattern with
        # no '|' yields a single positional arg (equivalent to --testPathPattern).
        foreach ($frag in ($Pattern -split '\|')) {
            if ($frag) { $passthroughArgs += $frag }
        }
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

    # Capture output and exit code together. Piping through ForEach-Object can
    # obscure the native exit code, so capture all lines first, then process them.
    # This ensures $LASTEXITCODE reflects npx's actual exit code, not ForEach-Object's.
    $allOutput = @(& npx nx @nxArgs 2>&1)
    $nxExit = $LASTEXITCODE

    $hasResults = $false
    $resultLineCount = 0

    # Stream test output line by line
    $allOutput | ForEach-Object {
        $line = $_.ToString()

        # PASS line
        if ($line -match $passPattern) {
            Write-Host $line -ForegroundColor Green
            $inFailBlock = $false
            $inSummary = $false
            $resultLineCount++
            $hasResults = $true
        }
        # FAIL line - start capturing block
        elseif ($line -match $failPattern) {
            Write-Host $line -ForegroundColor Red
            $inFailBlock = $true
            $failBlockLines = 0
            $inSummary = $false
            $resultLineCount++
            $hasResults = $true
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
            $hasResults = $true
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

    # Determine exit code using build-queue conventions (matching test-filtered.ps1):
    # - Exit 3 if no test results were captured (nx failed to run or produced no output)
    # - Exit 5 if a test filter was used and matched zero tests (future enhancement)
    # - Otherwise, forward nx's exit code (0 for success, non-zero for failure)
    if (-not $hasResults -and $nxExit -eq 0) {
        # No results captured, but nx said success — this shouldn't happen in normal test runs.
        # The build queue classifies this as result_fidelity='no-output'.
        Write-Host "WARN: No test results captured from nx (build may have failed to initialize)" -ForegroundColor Yellow
        exit 3
    }

    # Forward the underlying nx exit code. When nx exits non-zero (e.g., target not found,
    # tests failed, or build errors), we propagate that so the queue correctly reports FAIL.
    exit $nxExit
} finally {
    Pop-Location
}

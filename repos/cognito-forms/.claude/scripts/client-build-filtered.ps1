# Build frontend projects with filtered output
# Only shows errors and build summary (no verbose Nx/Rspack output)
# Streams output in real-time instead of buffering

param(
    [string]$Project = "",
    [switch]$All,
    [string[]]$Targets = @("build")
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
    # Build args
    if ($All) {
        Write-Host "Building all frontend projects..." -ForegroundColor Cyan
        $nxArgs = @("run-many", "--targets=$($Targets -join ',')")
    } elseif ($Project) {
        Write-Host "Building $Project..." -ForegroundColor Cyan
        $nxArgs = @("run", "$Project`:$($Targets[0])")
    } else {
        Write-Host "Building cognito-spa (default)..." -ForegroundColor Cyan
        $nxArgs = @("run", "cognito-spa:build")
    }

    $hasOutput = $false
    $hasError = $false

    # Patterns to match
    $errorPatterns = @(
        'error TS\d{4}:',           # TypeScript errors
        'ERROR in',                  # Webpack/Rspack errors
        'Module (build|parse) failed',
        'Module not found',
        'Cannot find module',
        'SyntaxError:',
        'TypeError:',
        'ReferenceError:',
        '\[ERROR\]',
        'Failed to compile'
    )
    $errorPattern = $errorPatterns -join '|'

    $summaryPatterns = @(
        'Successfully ran target',
        'failed',
        'Compiled',
        'NX\s+Successfully',
        'NX\s+.*failed',
        'Build at:',
        'webpack compiled',
        'rspack compiled'
    )
    $summaryPattern = $summaryPatterns -join '|'

    # Stream Nx output line by line
    & npx nx @nxArgs 2>&1 | ForEach-Object {
        $line = $_.ToString()

        # Check for errors
        if ($line -match $errorPattern) {
            $hasOutput = $true
            $hasError = $true
            Write-Host $line -ForegroundColor Red
        }
        # Check for summary lines
        elseif ($line -match $summaryPattern) {
            $hasOutput = $true
            if ($line -match 'failed|ERROR') {
                Write-Host $line -ForegroundColor Red
            } elseif ($line -match 'Successfully|Compiled|compiled successfully') {
                Write-Host $line -ForegroundColor Green
            } else {
                Write-Host $line -ForegroundColor Yellow
            }
        }
        # Show context lines after errors (indented continuation)
        elseif ($hasError -and $line -match '^\s{2,}\S') {
            Write-Host $line -ForegroundColor Red
        }
    }

    if (-not $hasOutput) {
        Write-Host "Build SUCCEEDED (no errors)" -ForegroundColor Green
    }
} finally {
    Pop-Location
}

# Audit-RepoCleanup.ps1
# Read-only audit of a repo for well-known disposable build artifacts.
# Reports total bytes consumed by each category so you can decide what to clean.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\Audit-RepoCleanup.ps1 -Root "C:\Users\JacobMadsen\source\repos\Cognito Forms"
#   powershell -ExecutionPolicy Bypass -File .\Audit-RepoCleanup.ps1 -Root "C:\Users\JacobMadsen\source\repos\algobooth"

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$Root,
    [string]$ReportPath = ''
)

$ErrorActionPreference = 'Continue'

if (-not (Test-Path -LiteralPath $Root)) {
    Write-Error "Root '$Root' does not exist."
    return
}

if (-not $ReportPath) {
    $safeName = (Split-Path $Root -Leaf) -replace '[^a-zA-Z0-9_-]', '_'
    $ReportPath = "C:\temp\audit-$safeName.txt"
}
if (-not (Test-Path 'C:\temp')) { New-Item -ItemType Directory -Path 'C:\temp' | Out-Null }

function Format-Size {
    param([double]$Bytes)
    if ($Bytes -ge 1TB) { return ("{0:N2} TB" -f ($Bytes / 1TB)) }
    if ($Bytes -ge 1GB) { return ("{0:N2} GB" -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ("{0:N2} MB" -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ("{0:N2} KB" -f ($Bytes / 1KB)) }
    return "$Bytes B"
}

function Get-DirSize {
    param([string]$Path)
    $total = 0L
    try {
        $files = [System.IO.Directory]::EnumerateFiles($Path, '*', [System.IO.SearchOption]::AllDirectories)
        foreach ($f in $files) {
            try {
                $fi = New-Object System.IO.FileInfo($f)
                if (-not ($fi.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                    $total += $fi.Length
                }
            } catch { }
        }
    } catch { }
    return $total
}

# Helper: find directories matching a name, but DON'T recurse into matches
# (so node_modules inside node_modules is ignored, avoiding double-count).
function Find-Dirs {
    param(
        [string]$StartPath,
        [string[]]$Names
    )
    $results = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($StartPath)
    while ($stack.Count -gt 0) {
        $cur = $stack.Pop()
        try {
            $children = [System.IO.Directory]::EnumerateDirectories($cur)
        } catch { continue }
        foreach ($c in $children) {
            try {
                $info = New-Object System.IO.DirectoryInfo($c)
                if ($info.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { continue }
            } catch { continue }
            $leaf = Split-Path -Leaf $c
            if ($Names -contains $leaf) {
                $results.Add($c) | Out-Null
                # Don't recurse into a matched directory
            } else {
                $stack.Push($c) | Out-Null
            }
        }
    }
    return $results
}

function Find-Files {
    param(
        [string]$StartPath,
        [string[]]$Patterns,
        [string[]]$SkipDirs = @('node_modules', '.git', 'target', 'bin', 'obj', '.nx', '.next', 'dist', 'build', 'out')
    )
    # Manual traversal so we can skip heavy subtrees (node_modules in monorepos
    # can have millions of files and blow up the scan to 20+ minutes).
    $results = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($StartPath)
    while ($stack.Count -gt 0) {
        $cur = $stack.Pop()
        try {
            foreach ($f in [System.IO.Directory]::EnumerateFiles($cur)) {
                foreach ($pat in $Patterns) {
                    if ([System.IO.Path]::GetFileName($f) -like $pat) {
                        $results.Add($f) | Out-Null
                        break
                    }
                }
            }
        } catch { }
        try {
            foreach ($d in [System.IO.Directory]::EnumerateDirectories($cur)) {
                $leaf = Split-Path -Leaf $d
                if ($SkipDirs -contains $leaf) { continue }
                try {
                    $info = New-Object System.IO.DirectoryInfo($d)
                    if ($info.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { continue }
                } catch { continue }
                $stack.Push($d) | Out-Null
            }
        } catch { }
    }
    return $results
}

$log = New-Object System.Text.StringBuilder
function Log {
    param([string]$Msg, [string]$Color = 'Gray')
    Write-Host $Msg -ForegroundColor $Color
    [void]$log.AppendLine($Msg)
}

Log "=== Cleanup audit: $Root ===" 'Cyan'
Log "Generated: $(Get-Date)"
Log ''

# Define the cleanup categories
$categories = @(
    @{ Label = 'node_modules (npm/pnpm)';          Dirs = @('node_modules') },
    @{ Label = '.NET build output (bin/)';         Dirs = @('bin') },
    @{ Label = '.NET intermediate (obj/)';         Dirs = @('obj') },
    @{ Label = 'Rust target/';                     Dirs = @('target') },
    @{ Label = 'Next.js .next/';                   Dirs = @('.next') },
    @{ Label = 'Nx cache (.nx/)';                  Dirs = @('.nx') },
    @{ Label = 'Vite/webpack dist/build/out';      Dirs = @('dist','build','out') },
    @{ Label = 'Python __pycache__';               Dirs = @('__pycache__') },
    @{ Label = 'Python venvs';                     Dirs = @('.venv','venv','env') },
    @{ Label = 'Jest/Vitest coverage/';            Dirs = @('coverage') },
    @{ Label = 'Tool caches';                      Dirs = @('.pytest_cache','.mypy_cache','.ruff_cache','.turbo','.cache','.parcel-cache') },
    @{ Label = 'Visual Studio .vs/';               Dirs = @('.vs') },
    @{ Label = 'JetBrains .idea/';                 Dirs = @('.idea') },
    @{ Label = 'TestResults/';                     Dirs = @('TestResults') }
)

$totalReclaim = 0L
$findings = @()

foreach ($cat in $categories) {
    $dirs = Find-Dirs -StartPath $Root -Names $cat.Dirs
    if (-not $dirs -or $dirs.Count -eq 0) { continue }
    $catTotal = 0L
    foreach ($d in $dirs) {
        $catTotal += Get-DirSize -Path $d
    }
    if ($catTotal -eq 0) { continue }
    $totalReclaim += $catTotal
    $findings += [pscustomobject]@{
        Category = $cat.Label
        Count    = $dirs.Count
        Bytes    = $catTotal
        Size     = Format-Size $catTotal
        Dirs     = $dirs
    }
}

# Report summary
Log '=== Category summary (largest first) ===' 'Cyan'
Log ("{0,-40} {1,5} {2,12}" -f 'Category', 'Count', 'Size')
Log ("{0,-40} {1,5} {2,12}" -f ('-' * 40), '-----', ('-' * 12))
foreach ($f in ($findings | Sort-Object Bytes -Descending)) {
    Log ("{0,-40} {1,5} {2,12}" -f $f.Category, $f.Count, $f.Size)
}
Log ''
Log ("TOTAL potential reclaim: {0}" -f (Format-Size $totalReclaim)) 'Green'
Log ''

# Detail: top paths in each category
Log '=== Per-category details (top 10 largest paths) ===' 'Cyan'
foreach ($f in ($findings | Sort-Object Bytes -Descending)) {
    Log ''
    Log ("--- {0} ({1}, {2} dirs) ---" -f $f.Category, $f.Size, $f.Count) 'Yellow'
    $sized = foreach ($d in $f.Dirs) {
        [pscustomobject]@{
            SizeBytes = Get-DirSize -Path $d
            Path      = $d
        }
    }
    foreach ($s in ($sized | Sort-Object SizeBytes -Descending | Select-Object -First 10)) {
        Log ("  {0,10}  {1}" -f (Format-Size $s.SizeBytes), $s.Path)
    }
    if ($f.Count -gt 10) {
        Log ("  ... and $($f.Count - 10) more")
    }
}

# Large stray files (build artifacts outside known dirs)
Log ''
Log '=== Large individual files (>= 100 MB) ===' 'Cyan'
$bigFiles = Find-Files -StartPath $Root -Patterns @('*.zip','*.log','*.pack','*.exe','*.msi','*.tar.gz','*.7z','*.iso','*.vhdx','*.bin','*.pdb','*.dump','*.nupkg','*.dll','*.node')
$bigFiles = $bigFiles | ForEach-Object {
    try {
        $fi = New-Object System.IO.FileInfo($_)
        if ($fi.Length -ge 100MB) {
            [pscustomobject]@{ SizeBytes = $fi.Length; Size = Format-Size $fi.Length; Path = $_ }
        }
    } catch { }
} | Sort-Object SizeBytes -Descending | Select-Object -First 20
if ($bigFiles) {
    foreach ($b in $bigFiles) {
        Log ("  {0,10}  {1}" -f $b.Size, $b.Path)
    }
} else {
    Log '  (none)'
}

Log ''
Log "Report written to $ReportPath" 'Green'
$log.ToString() | Out-File -LiteralPath $ReportPath -Encoding UTF8

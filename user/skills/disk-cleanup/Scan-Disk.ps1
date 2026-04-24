# Scan-Disk.ps1
# Read-only disk analyzer. Three modes are combined in one script:
#   - Drive summary (all mounted drives)
#   - Top folders under -Root, sized recursively (single-pass, no O(N*depth) blowup)
#   - Drill-in: for each of the top N folders, list their immediate children above a threshold
#   - Known disk hogs: pre-canned list of paths worth checking (temp, caches, etc.)
#
# Usage examples:
#   .\Scan-Disk.ps1                                         # scan C:\ at default settings
#   .\Scan-Disk.ps1 -Root 'C:/Users/JacobMadsen' -DrillIntoTop 10
#   .\Scan-Disk.ps1 -Root 'C:/' -MinSizeMB 500 -TopFolders 40
#   .\Scan-Disk.ps1 -CsvOut 'C:\temp\disk-report.csv'
#
# Report is written to C:\temp\scan-<root>.txt so an agent can Read it directly.

[CmdletBinding()]
param(
    [string]$Root = 'C:/',
    [int]$TopFolders = 40,
    [int]$TopFiles = 30,
    [double]$MinSizeMB = 250,
    [int]$DrillIntoTop = 10,
    [double]$DrillMinSizeMB = 50,
    [string]$CsvOut = '',
    [string]$ReportPath = ''
)

$ErrorActionPreference = 'Continue'

if (-not (Test-Path -LiteralPath $Root)) {
    Write-Error "Root path '$Root' does not exist."
    return
}

$Root = (Resolve-Path -LiteralPath $Root).Path

if (-not $ReportPath) {
    $safeName = ($Root -replace '[:\\/ ]', '_').Trim('_')
    $ReportPath = "C:\temp\scan-$safeName.txt"
}
if (-not (Test-Path 'C:\temp')) { New-Item -ItemType Directory -Path 'C:\temp' | Out-Null }

$minBytes = [long]($MinSizeMB * 1MB)
$drillMinBytes = [long]($DrillMinSizeMB * 1MB)

function Format-Size {
    param([double]$Bytes)
    if ($Bytes -ge 1TB) { return ('{0:N2} TB' -f ($Bytes / 1TB)) }
    if ($Bytes -ge 1GB) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ('{0:N2} MB' -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ('{0:N2} KB' -f ($Bytes / 1KB)) }
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

$log = New-Object System.Text.StringBuilder
function Log {
    param([string]$Msg, [string]$Color = 'Gray')
    Write-Host $Msg -ForegroundColor $Color
    [void]$log.AppendLine($Msg)
}

Log ("=== Disk scan: {0} ===" -f $Root) 'Cyan'
Log ("Generated: {0}" -f (Get-Date))
Log ''

# --- Drive summary ---
Log '=== Drive summary ===' 'Cyan'
$drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null }
foreach ($d in $drives) {
    $total = $d.Used + $d.Free
    $pct = if ($total -gt 0) { '{0:N1}%' -f (100 * $d.Free / $total) } else { 'n/a' }
    Log ("  {0}:  Used={1,10}  Free={2,10}  Total={3,10}  Free%={4}" -f $d.Name, (Format-Size $d.Used), (Format-Size $d.Free), (Format-Size $total), $pct)
}

# --- Top-level folder sizing under Root (single-pass) ---
Log ''
Log ("=== Sizing top-level folders under {0} ===" -f $Root) 'Cyan'
$topLevel = Get-ChildItem -LiteralPath $Root -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { -not ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) }

$folderResults = New-Object System.Collections.Generic.List[object]
$i = 0
foreach ($d in $topLevel) {
    $i++
    Write-Progress -Activity 'Sizing folders' -Status $d.Name -PercentComplete (100 * $i / $topLevel.Count)
    $size = Get-DirSize -Path $d.FullName
    if ($size -ge $minBytes) {
        $folderResults.Add([pscustomobject]@{
            SizeBytes = $size
            Size      = Format-Size $size
            Path      = $d.FullName
        }) | Out-Null
    }
}
Write-Progress -Activity 'Sizing folders' -Completed

$sortedFolders = $folderResults | Sort-Object SizeBytes -Descending
Log ("--- Top {0} folders (>= {1} MB) ---" -f $TopFolders, $MinSizeMB)
foreach ($r in ($sortedFolders | Select-Object -First $TopFolders)) {
    Log ("  {0,10}  {1}" -f $r.Size, $r.Path)
}

# --- Top individual files under Root ---
Log ''
Log ("=== Top {0} files (>= {1} MB) ===" -f $TopFiles, $MinSizeMB) 'Cyan'
$fileResults = New-Object System.Collections.Generic.List[object]
try {
    $allFiles = [System.IO.Directory]::EnumerateFiles($Root, '*', [System.IO.SearchOption]::AllDirectories)
    foreach ($f in $allFiles) {
        try {
            $fi = New-Object System.IO.FileInfo($f)
            if ($fi.Length -ge $minBytes -and -not ($fi.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                $fileResults.Add([pscustomobject]@{
                    SizeBytes    = $fi.Length
                    Size         = Format-Size $fi.Length
                    LastModified = $fi.LastWriteTime
                    Path         = $fi.FullName
                }) | Out-Null
            }
        } catch { }
    }
} catch {
    Log ("  (File enumeration partial: {0})" -f $_) 'Yellow'
}
$sortedFiles = $fileResults | Sort-Object SizeBytes -Descending | Select-Object -First $TopFiles
foreach ($r in $sortedFiles) {
    Log ("  {0,10}  {1:yyyy-MM-dd}  {2}" -f $r.Size, $r.LastModified, $r.Path)
}

# --- Drill-in for the top N folders ---
Log ''
Log ("=== Drilling into top {0} folders (children >= {1} MB) ===" -f $DrillIntoTop, $DrillMinSizeMB) 'Cyan'
$drillResults = New-Object System.Collections.Generic.List[object]
foreach ($r in ($sortedFolders | Select-Object -First $DrillIntoTop)) {
    Log ''
    Log ("  --- {0} ({1}) ---" -f $r.Path, $r.Size) 'Yellow'
    $children = Get-ChildItem -LiteralPath $r.Path -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { -not ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) }
    $sub = New-Object System.Collections.Generic.List[object]
    foreach ($c in $children) {
        $s = Get-DirSize -Path $c.FullName
        if ($s -ge $drillMinBytes) {
            $obj = [pscustomobject]@{
                SizeBytes = $s
                Size      = Format-Size $s
                Path      = $c.FullName
            }
            $sub.Add($obj) | Out-Null
            $drillResults.Add($obj) | Out-Null
        }
    }
    foreach ($s in ($sub | Sort-Object SizeBytes -Descending | Select-Object -First 15)) {
        Log ("    {0,10}  {1}" -f $s.Size, $s.Path)
    }
}

# --- Known disk hogs ---
Log ''
Log '=== Known disk hogs ===' 'Cyan'
$suspectPaths = @(
    "$env:LOCALAPPDATA\Temp",
    "$env:LOCALAPPDATA\Microsoft\Windows\INetCache",
    "$env:LOCALAPPDATA\Microsoft\Windows\WebCache",
    "$env:LOCALAPPDATA\Packages",
    "$env:LOCALAPPDATA\NuGet\v3-cache",
    "$env:LOCALAPPDATA\pip\Cache",
    "$env:USERPROFILE\.nuget\packages",
    "$env:USERPROFILE\.gradle",
    "$env:USERPROFILE\.m2\repository",
    "$env:USERPROFILE\.cargo\registry",
    "$env:USERPROFILE\AppData\Local\Google\Chrome\User Data\Default\Cache",
    "$env:USERPROFILE\AppData\Local\Microsoft\Edge\User Data\Default\Cache",
    "$env:USERPROFILE\AppData\Local\JetBrains",
    "$env:USERPROFILE\AppData\Local\Docker",
    "$env:USERPROFILE\AppData\Local\pnpm",
    "$env:USERPROFILE\AppData\Local\Yarn\Cache",
    "$env:USERPROFILE\AppData\Roaming\npm-cache",
    'C:\Windows\SoftwareDistribution\Download',
    'C:\Windows\Temp',
    'C:\Windows\Installer',
    'C:\Windows\WinSxS',
    'C:\ProgramData\Package Cache',
    'C:\ProgramData\Docker'
)
$suspectResults = New-Object System.Collections.Generic.List[object]
foreach ($p in $suspectPaths) {
    if (Test-Path -LiteralPath $p) {
        $size = Get-DirSize -Path $p
        $suspectResults.Add([pscustomobject]@{
            SizeBytes = $size
            Size      = Format-Size $size
            Path      = $p
        }) | Out-Null
    }
}
foreach ($r in ($suspectResults | Sort-Object SizeBytes -Descending)) {
    Log ("  {0,10}  {1}" -f $r.Size, $r.Path)
}

# --- Optional CSV export ---
if ($CsvOut) {
    $export = @()
    $export += $sortedFolders | Select-Object @{N='Kind';E={'Folder'}}, Size, SizeBytes, @{N='LastModified';E={''}}, Path
    $export += $sortedFiles   | Select-Object @{N='Kind';E={'File'}},   Size, SizeBytes, LastModified, Path
    $export += $suspectResults| Select-Object @{N='Kind';E={'Suspect'}},Size, SizeBytes, @{N='LastModified';E={''}}, Path
    $export | Export-Csv -LiteralPath $CsvOut -NoTypeInformation -Encoding UTF8
    Log ("CSV exported to {0}" -f $CsvOut) 'Green'
}

Log ''
Log ("Report written to {0}" -f $ReportPath) 'Green'
$log.ToString() | Out-File -LiteralPath $ReportPath -Encoding UTF8

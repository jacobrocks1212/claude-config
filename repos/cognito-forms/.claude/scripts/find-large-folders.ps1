# Find Large Folders Script
param(
    [string]$Path = "C:\Users\JacobMadsen",
    [int]$TopN = 25,
    [int]$MinSizeMB = 500
)

function Get-FolderSize {
    param([string]$FolderPath)
    try {
        $size = (Get-ChildItem -Path $FolderPath -Recurse -Force -ErrorAction SilentlyContinue |
                 Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
        return [math]::Round($size / 1MB, 0)
    } catch {
        return 0
    }
}

Write-Host "=== SCANNING COMMON CACHE/TEMP LOCATIONS ===" -ForegroundColor Cyan
Write-Host ""

$knownLocations = @(
    @{Path="$env:TEMP"; Name="Windows Temp"},
    @{Path="$env:LOCALAPPDATA\Temp"; Name="Local Temp"},
    @{Path="$env:LOCALAPPDATA\npm-cache"; Name="NPM Cache"},
    @{Path="$env:APPDATA\npm-cache"; Name="NPM Cache (Roaming)"},
    @{Path="$env:LOCALAPPDATA\NuGet\v3-cache"; Name="NuGet Cache"},
    @{Path="$env:USERPROFILE\.nuget\packages"; Name="NuGet Packages"},
    @{Path="$env:LOCALAPPDATA\Microsoft\VisualStudio"; Name="VS Local Data"},
    @{Path="$env:APPDATA\Code\Cache"; Name="VS Code Cache"},
    @{Path="$env:APPDATA\Code\CachedData"; Name="VS Code Cached Data"},
    @{Path="$env:APPDATA\Code\CachedExtensions"; Name="VS Code Cached Extensions"},
    @{Path="$env:APPDATA\Code\CachedExtensionVSIXs"; Name="VS Code VSIX Cache"},
    @{Path="$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache"; Name="Chrome Cache"},
    @{Path="$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache"; Name="Edge Cache"},
    @{Path="$env:LOCALAPPDATA\Yarn\Cache"; Name="Yarn Cache"},
    @{Path="$env:APPDATA\npm"; Name="NPM Global"},
    @{Path="$env:USERPROFILE\.cache"; Name="User Cache"},
    @{Path="$env:USERPROFILE\Downloads"; Name="Downloads"},
    @{Path="$env:USERPROFILE\.docker"; Name="Docker"},
    @{Path="$env:LOCALAPPDATA\Docker"; Name="Docker Desktop"},
    @{Path="$env:PROGRAMDATA\Docker"; Name="Docker Data"},
    @{Path="C:\Windows\Temp"; Name="Windows System Temp"},
    @{Path="$env:LOCALAPPDATA\Packages"; Name="Windows Store Apps"}
)

foreach ($loc in $knownLocations) {
    if (Test-Path $loc.Path) {
        $sizeMB = Get-FolderSize -FolderPath $loc.Path
        if ($sizeMB -ge 100) {
            $sizeGB = [math]::Round($sizeMB / 1024, 2)
            if ($sizeGB -ge 1) {
                Write-Host ("{0,-35} {1,8:N2} GB" -f $loc.Name, $sizeGB) -ForegroundColor $(if($sizeGB -ge 5){"Red"}elseif($sizeGB -ge 2){"Yellow"}else{"White"})
            } else {
                Write-Host ("{0,-35} {1,8:N0} MB" -f $loc.Name, $sizeMB)
            }
            Write-Host "   $($loc.Path)" -ForegroundColor DarkGray
        }
    }
}

Write-Host ""
Write-Host "=== SCANNING FOR node_modules FOLDERS ===" -ForegroundColor Cyan
Write-Host "(This may take a moment...)" -ForegroundColor DarkGray
Write-Host ""

$sourceRepos = "C:\Users\JacobMadsen\source\repos"
if (Test-Path $sourceRepos) {
    $nodeModules = Get-ChildItem -Path $sourceRepos -Filter "node_modules" -Directory -Recurse -ErrorAction SilentlyContinue -Depth 5
    $nmSizes = @()
    foreach ($nm in $nodeModules) {
        $sizeMB = Get-FolderSize -FolderPath $nm.FullName
        if ($sizeMB -ge 200) {
            $nmSizes += [PSCustomObject]@{
                Path = $nm.FullName
                SizeMB = $sizeMB
            }
        }
    }
    $nmSizes | Sort-Object SizeMB -Descending | ForEach-Object {
        $sizeGB = [math]::Round($_.SizeMB / 1024, 2)
        Write-Host ("{0,8:N2} GB  {1}" -f $sizeGB, $_.Path) -ForegroundColor $(if($sizeGB -ge 2){"Red"}elseif($sizeGB -ge 1){"Yellow"}else{"White"})
    }
}

Write-Host ""
Write-Host "=== SCANNING FOR bin/obj FOLDERS (Build Outputs) ===" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $sourceRepos) {
    $buildFolders = @()
    Get-ChildItem -Path $sourceRepos -Directory -Recurse -ErrorAction SilentlyContinue -Depth 6 |
        Where-Object { $_.Name -eq "bin" -or $_.Name -eq "obj" } |
        ForEach-Object {
            $sizeMB = Get-FolderSize -FolderPath $_.FullName
            if ($sizeMB -ge 200) {
                $buildFolders += [PSCustomObject]@{
                    Path = $_.FullName
                    SizeMB = $sizeMB
                }
            }
        }

    $totalBuildMB = ($buildFolders | Measure-Object -Property SizeMB -Sum).Sum
    $totalBuildGB = [math]::Round($totalBuildMB / 1024, 2)
    Write-Host "Total bin/obj over 200MB each: $totalBuildGB GB" -ForegroundColor Yellow

    $buildFolders | Sort-Object SizeMB -Descending | Select-Object -First 10 | ForEach-Object {
        $sizeGB = [math]::Round($_.SizeMB / 1024, 2)
        Write-Host ("{0,8:N2} GB  {1}" -f $sizeGB, $_.Path)
    }
}

Write-Host ""
Write-Host "=== TOP LEVEL FOLDERS IN source\repos ===" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $sourceRepos) {
    Get-ChildItem -Path $sourceRepos -Directory | ForEach-Object {
        $sizeMB = Get-FolderSize -FolderPath $_.FullName
        [PSCustomObject]@{
            Name = $_.Name
            SizeMB = $sizeMB
        }
    } | Sort-Object SizeMB -Descending | Select-Object -First 15 | ForEach-Object {
        $sizeGB = [math]::Round($_.SizeMB / 1024, 2)
        Write-Host ("{0,8:N2} GB  {1}" -f $sizeGB, $_.Name) -ForegroundColor $(if($sizeGB -ge 10){"Red"}elseif($sizeGB -ge 5){"Yellow"}else{"White"})
    }
}

Write-Host ""
Write-Host "=== RECYCLE BIN ===" -ForegroundColor Cyan
try {
    $shell = New-Object -ComObject Shell.Application
    $recycleBin = $shell.NameSpace(0xA)
    $rbItems = $recycleBin.Items()
    $rbSize = 0
    foreach ($item in $rbItems) {
        $rbSize += $recycleBin.GetDetailsOf($item, 2) -replace '[^\d]'
    }
    # Alternative method
    $rbPath = "C:\`$Recycle.Bin"
    if (Test-Path $rbPath) {
        $rbSizeMB = Get-FolderSize -FolderPath $rbPath
        $rbSizeGB = [math]::Round($rbSizeMB / 1024, 2)
        Write-Host "Recycle Bin: approximately $rbSizeGB GB" -ForegroundColor $(if($rbSizeGB -ge 1){"Yellow"}else{"White"})
    }
} catch {
    Write-Host "Could not determine Recycle Bin size" -ForegroundColor DarkGray
}

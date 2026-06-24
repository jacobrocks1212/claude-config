# Quick disk space scan
$ErrorActionPreference = "SilentlyContinue"

function Size($path) {
    if (!(Test-Path $path)) { return 0 }
    [math]::Round((Get-ChildItem $path -Recurse -Force -EA SilentlyContinue | Measure-Object Length -Sum).Sum/1GB, 2)
}

Write-Host "=== CACHES & TEMP (safe to clear) ===" -ForegroundColor Cyan
$locs = @{
    "Windows Temp" = "$env:LOCALAPPDATA\Temp"
    "NuGet Packages" = "$env:USERPROFILE\.nuget\packages"
    "NPM Cache" = "$env:LOCALAPPDATA\npm-cache"
    "VS Code Cache" = "$env:APPDATA\Code\Cache"
    "VS Code CachedData" = "$env:APPDATA\Code\CachedData"
    "VS Code Extensions" = "$env:USERPROFILE\.vscode\extensions"
    "Downloads" = "$env:USERPROFILE\Downloads"
    "Chrome Cache" = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Cache"
    "Edge Cache" = "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Cache"
    "VS ComponentCache" = "$env:LOCALAPPDATA\Microsoft\VisualStudio\17.0\ComponentModelCache"
}

$results = @()
foreach ($name in $locs.Keys) {
    $path = $locs[$name]
    $gb = Size $path
    if ($gb -ge 0.1) {
        $results += [PSCustomObject]@{Name=$name; GB=$gb; Path=$path}
    }
}
$results | Sort-Object GB -Descending | ForEach-Object {
    Write-Host ("{0,8:N2} GB  {1}" -f $_.GB, $_.Name) -ForegroundColor $(if($_.GB -ge 3){"Red"}elseif($_.GB -ge 1){"Yellow"}else{"White"})
    Write-Host ("           {0}" -f $_.Path) -ForegroundColor DarkGray
}
$total = ($results | Measure-Object GB -Sum).Sum
Write-Host ("`nSubtotal: {0:N2} GB" -f $total) -ForegroundColor Green

Write-Host "`n=== node_modules IN source\repos ===" -ForegroundColor Cyan
$nmTotal = 0
Get-ChildItem "C:\Users\JacobMadsen\source\repos" -Directory | ForEach-Object {
    $nmPath = Join-Path $_.FullName "node_modules"
    $nmPath2 = Join-Path $_.FullName "Cognito.Web.Client\node_modules"

    foreach ($p in @($nmPath, $nmPath2)) {
        if (Test-Path $p) {
            $gb = Size $p
            if ($gb -ge 0.5) {
                Write-Host ("{0,8:N2} GB  {1}" -f $gb, $p) -ForegroundColor Yellow
                $nmTotal += $gb
            }
        }
    }
}
Write-Host ("`nnode_modules total: {0:N2} GB" -f $nmTotal) -ForegroundColor Green

Write-Host "`n=== LARGE PROJECT FOLDERS ===" -ForegroundColor Cyan
Write-Host "(Consider deleting unused projects)" -ForegroundColor DarkGray
Get-ChildItem "C:\Users\JacobMadsen\source\repos" -Directory | ForEach-Object {
    $gb = Size $_.FullName
    [PSCustomObject]@{Name=$_.Name; GB=$gb}
} | Sort-Object GB -Descending | Select-Object -First 10 | ForEach-Object {
    Write-Host ("{0,8:N2} GB  {1}" -f $_.GB, $_.Name) -ForegroundColor $(if($_.GB -ge 5){"Yellow"}else{"White"})
}

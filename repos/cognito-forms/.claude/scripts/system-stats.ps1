# System Stats Script
Write-Host "=== MEMORY ===" -ForegroundColor Cyan
$os = Get-CimInstance Win32_OperatingSystem
$totalGB = [math]::Round($os.TotalVisibleMemorySize/1MB,1)
$freeGB = [math]::Round($os.FreePhysicalMemory/1MB,1)
$usedGB = $totalGB - $freeGB
$pct = [math]::Round(($usedGB/$totalGB)*100,1)
Write-Host "Used: $usedGB GB / $totalGB GB ($pct%)"

Write-Host "`n=== CPU ===" -ForegroundColor Cyan
Get-CimInstance Win32_Processor | ForEach-Object {
    Write-Host "Model: $($_.Name)"
    Write-Host "Cores: $($_.NumberOfCores) physical, $($_.NumberOfLogicalProcessors) logical"
    Write-Host "Load: $($_.LoadPercentage)%"
}

Write-Host "`n=== DISK ===" -ForegroundColor Cyan
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    $sizeGB = [math]::Round($_.Size/1GB,1)
    $freeGB = [math]::Round($_.FreeSpace/1GB,1)
    $usedPct = [math]::Round((($_.Size-$_.FreeSpace)/$_.Size)*100,1)
    Write-Host "$($_.DeviceID) - $freeGB GB free / $sizeGB GB ($usedPct% used)"
}

Write-Host "`n=== TOP 15 PROCESSES BY MEMORY ===" -ForegroundColor Cyan
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 | ForEach-Object {
    $mb = [math]::Round($_.WorkingSet64/1MB)
    Write-Host ("{0,-30} {1,6} MB  CPU: {2,8:N1}s" -f $_.ProcessName, $mb, $_.CPU)
}

Write-Host "`n=== TOP 10 PROCESSES BY CPU TIME ===" -ForegroundColor Cyan
Get-Process | Where-Object { $_.CPU -gt 0 } | Sort-Object CPU -Descending | Select-Object -First 10 | ForEach-Object {
    $mb = [math]::Round($_.WorkingSet64/1MB)
    Write-Host ("{0,-30} CPU: {1,10:N1}s  {2,6} MB" -f $_.ProcessName, $_.CPU, $mb)
}

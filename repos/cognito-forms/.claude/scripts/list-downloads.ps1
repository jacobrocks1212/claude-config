Get-ChildItem "C:\Users\JacobMadsen\Downloads" -File |
    Sort-Object Length -Descending |
    Select-Object -First 30 |
    ForEach-Object {
        $mb = [math]::Round($_.Length/1MB, 1)
        $date = $_.LastWriteTime.ToString("yyyy-MM-dd")
        Write-Host ("{0,10} MB  {1}  {2}" -f $mb, $date, $_.Name)
    }

Write-Host ""
$total = (Get-ChildItem "C:\Users\JacobMadsen\Downloads" -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("Total: {0:N2} GB" -f ($total/1GB))

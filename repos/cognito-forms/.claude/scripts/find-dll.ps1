Get-ChildItem -Path "C:\Users\JacobMadsen\source\repos\Cognito Forms" -Filter "System.Text.RegularExpressions.dll" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(bin|obj|packages)\\' } |
    ForEach-Object { "{0,8} {1}" -f $_.Length, $_.FullName }

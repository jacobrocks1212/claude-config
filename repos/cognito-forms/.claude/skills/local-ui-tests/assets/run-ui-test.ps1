# Run one (or a filtered set of) Cognito.Forms.UnitTests Selenium test(s) with --no-build,
# bypassing test-filtered.ps1's false "stale" check for this project (it outputs to bin\, not bin\Debug\).
# Invoke THROUGH the build queue so `dotnet` runs inside PowerShell (not the Bash hook):
#   powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" `
#     -Op mstest -Exec "<this-script>" -Method "<TestNameOrFilter>"
# Build first: /msbuild -Project "Cognito.Forms.UnitTests/Cognito.Forms.UnitTests.csproj"
# Output is UTF-16; decode with: iconv -f UTF-16LE -t UTF-8 <out> | grep -E 'Passed|Failed|Error Message|Stack Trace'
param([string]$Method = "")
$ErrorActionPreference = "Continue"
$root = (git rev-parse --show-toplevel 2>$null) -replace '/', '\'
$proj = "$root\Cognito.Forms.UnitTests\Cognito.Forms.UnitTests.csproj"
$out  = Join-Path $env:TEMP "ui-test-run.txt"
if ([string]::IsNullOrWhiteSpace($Method)) { throw "Pass -Method '<TestNameOrFilter>' (matched via FullyQualifiedName~)." }
& dotnet test $proj --no-build --filter "FullyQualifiedName~$Method" --verbosity normal *> $out
"=== EXIT $LASTEXITCODE  out=$out ===" | Out-File $out -Append -Encoding utf8
Write-Host "ui-test done, exit=$LASTEXITCODE, output: $out"

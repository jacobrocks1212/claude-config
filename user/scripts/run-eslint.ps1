param([string]$FilePath)

# Extract Cognito.Web.Client directory from file path
if ($FilePath -match '(.*Cognito\.Web\.Client)') {
    $webClientDir = $Matches[1]
    Push-Location $webClientDir
    try {
        npx eslint --fix $FilePath 2>&1
    } finally {
        Pop-Location
    }
}

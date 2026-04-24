# fix-line-endings.ps1
# Called by Claude Code hook after Write/Edit to ensure CRLF line endings
param(
    [string]$FilePath
)

if (-not $FilePath -or -not (Test-Path $FilePath)) {
    exit 0
}

# Only process text files (skip binary)
$textExtensions = @('.ts', '.tsx', '.js', '.jsx', '.json', '.vue', '.css', '.scss', '.html', '.md', '.cs', '.xml', '.yaml', '.yml', '.ps1', '.sh', '.txt')
$ext = [System.IO.Path]::GetExtension($FilePath).ToLower()
if ($ext -notin $textExtensions) {
    exit 0
}

# Read file as bytes to preserve exact content
$bytes = [System.IO.File]::ReadAllBytes($FilePath)
$content = [System.Text.Encoding]::UTF8.GetString($bytes)

# Check if file has any LF without preceding CR
if ($content -match "(?<!\r)\n") {
    # Normalize: remove all CR first, then add CRLF
    $normalized = $content -replace "`r", ''
    $fixed = $normalized -replace "`n", "`r`n"
    [System.IO.File]::WriteAllText($FilePath, $fixed, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Fixed line endings: $FilePath"
}

# Convention-aware EOL normalizer hook (PostToolUse: Edit|Write and Bash)
#
# The Cognito Forms repo commits a MIXED EOL convention (`.cs` = CRLF, the
# `Cognito/NotificationTemplates/**` templates = LF; `.gitattributes` is `* -crlf`,
# so git neither normalizes nor flags this). A blanket "force CRLF" rule corrupts the
# LF-committed files and inflates their diffs. This hook instead makes each file's
# working-tree EOL MATCH its committed convention, so edits stay minimal-diff:
#
#   - Tracked file:   TARGET = DOMINANT EOL of its HEAD blob (CRLF if CRLF lines outnumber
#                     bare-LF lines, else LF). A few stray CRLF in a mostly-LF file (or vice
#                     versa) does NOT flip the whole file — minority lines converge to the
#                     majority, never the reverse.
#   - New/untracked:  TARGET = dominant EOL of same-extension siblings in its directory,
#                     else CRLF (the .editorconfig default for genuinely-new files).
# It then converts the file's bytes to TARGET — ADDING a CR before a bare LF for a CRLF
# target, or STRIPPING the CR from every CRLF for an LF target.
#
# WORKTREE-AWARE: all Cognito worktrees (main + Cognito Forms-B/C/D + future + detached temp
# worktrees) share ONE settings.json that invokes THIS file by absolute path, so every
# worktree runs this copy. repoRoot is resolved PER-INVOCATION from the active file/cwd, then
# gated by git-common-dir equality against the canonical Cognito repo. This makes the hook
# follow whichever worktree fired it while staying a strict no-op in any other repo
# (claude-config, etc.) — the common-dir gate replaces the old hardcoded-path scope limiter.
#
# Edit|Write: normalizes the single edited file (tool_input.file_path). Runs LAST
#   (after eslint/stylelint --fix) so formatter output is corrected too.
# Bash: in-place stream editors (`sed -i`, `perl -i`, `awk ... inplace`, dos2unix/unix2dos)
#   bypass Edit/Write and silently rewrite EOL. Bash gives us no file_path, so we walk
#   git status (of the ACTIVE worktree) and normalize each modified file. This is SAFE despite
#   the broad scan because every file is matched to its OWN committed EOL — an unrelated
#   LF-committed bystander is left LF, a CRLF-committed file is left CRLF. Extend $inPlaceEdit
#   below if a new in-place tool bites us.
#
# Byte-level so encoding/BOM is preserved; idempotent (only writes on change).
# Testability: honors $env:CRLF_HOOK_REPOROOT as the CANONICAL-repo override (unset in production).

$ErrorActionPreference = 'Stop'
$ok = @{ continue = $true } | ConvertTo-Json -Compress

try {
    $data = [Console]::In.ReadToEnd() | ConvertFrom-Json
}
catch {
    $ok; exit
}

# Resolve a path to its absolute form; $null on failure.
function Resolve-Abs([string]$p) {
    if (-not $p) { return $null }
    try { return (Resolve-Path -LiteralPath $p -ErrorAction Stop).Path } catch { return $null }
}

# Run a git query under -C $dir, returning trimmed stdout ($null on non-zero/empty/failure).
# Wrapped so native git stderr never trips $ErrorActionPreference='Stop'.
function Invoke-Git([string]$dir, [string[]]$gitArgs) {
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & git -C $dir @gitArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $out = ($out | Out-String).Trim()
        if (-not $out) { return $null }
        return $out
    }
    catch { return $null }
    finally { $ErrorActionPreference = $eap }
}

# git may report a relative common dir (e.g. ".git"); make it absolute relative to $dir.
function Get-CommonDirAbs([string]$dir) {
    $cd = Invoke-Git $dir @('rev-parse', '--git-common-dir')
    if (-not $cd) { return $null }
    if (-not [System.IO.Path]::IsPathRooted($cd)) { $cd = Join-Path $dir $cd }
    return (Resolve-Abs $cd)
}

# CANONICAL Cognito repo (test override via env). Its common dir is the scope key every
# legitimate worktree must share.
$canonical = if ($env:CRLF_HOOK_REPOROOT) { $env:CRLF_HOOK_REPOROOT } else { 'C:\Users\JacobMadsen\source\repos\Cognito Forms' }
$canonical = Resolve-Abs $canonical
if (-not $canonical) { $ok; exit }
$canonicalCommon = Get-CommonDirAbs $canonical
if (-not $canonicalCommon) { $ok; exit }

# Path relative to the active repoRoot using forward slashes (git wants forward slashes in HEAD:path).
function Get-RelPath([string]$full) {
    $root = $script:RepoRoot.TrimEnd('\', '/')
    $rel = $full.Substring($root.Length).TrimStart('\', '/')
    return ($rel -replace '\\', '/')
}

# Dominant EOL of a byte array: 'crlf' if CRLF lines outnumber bare-LF lines, else 'lf'.
# A mixed blob (e.g. a mostly-LF .cs with a few stray CRLF lines) resolves to its MAJORITY,
# so we never CR-prefix hundreds of bare LFs just because one CRLF appears first.
# Tie (including a file with no line breaks) => 'crlf' (the .editorconfig default).
function Get-DominantEol([byte[]]$b) {
    $crlf = 0
    $lf = 0
    for ($i = 0; $i -lt $b.Length; $i++) {
        if ($b[$i] -eq 0x0A) {
            if ($i -gt 0 -and $b[$i - 1] -eq 0x0D) { $crlf++ } else { $lf++ }
        }
    }
    if ($lf -gt $crlf) { return 'lf' }
    return 'crlf'
}

# Resolve TARGET EOL ('crlf' or 'lf') for a file. $relpath uses forward slashes.
function Get-TargetEol([string]$full, [string]$relpath) {
    # 1. Tracked file: match the DOMINANT EOL of the committed HEAD blob. One git process:
    # `cat-file blob` is the documented raw-bytes path (no autocrlf filtering, unlike `show`),
    # captured via cmd `>` redirection because PowerShell's pipeline mangles raw bytes.
    # A non-zero exit (untracked path, transient failure) falls through to the sibling fallback
    # instead of trusting a possibly-empty temp file.
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        & cmd /c "git -C `"$script:RepoRoot`" cat-file blob `"HEAD:$relpath`" > `"$tmp`" 2>nul" | Out-Null
        $code = $LASTEXITCODE
        if ($code -eq 0) {
            $blob = [System.IO.File]::ReadAllBytes($tmp)
            return (Get-DominantEol $blob)
        }
    }
    finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }

    # 2. New/untracked: dominant EOL of same-extension siblings in the directory.
    $ext = [System.IO.Path]::GetExtension($full)
    $dir = [System.IO.Path]::GetDirectoryName($full)
    $crlfCount = 0
    $lfCount = 0
    if ($ext -and $dir -and (Test-Path -LiteralPath $dir)) {
        $siblings = Get-ChildItem -LiteralPath $dir -File -Filter "*$ext" -ErrorAction SilentlyContinue
        foreach ($sib in $siblings) {
            if ($sib.FullName -eq $full) { continue }
            try {
                $sb = [System.IO.File]::ReadAllBytes($sib.FullName)
                if ($sb.Length -eq 0) { continue }
                if ((Get-DominantEol $sb) -eq 'crlf') { $crlfCount++ } else { $lfCount++ }
            }
            catch { }
        }
    }
    if ($crlfCount -gt $lfCount) { return 'crlf' }
    if ($lfCount -gt $crlfCount) { return 'lf' }
    return 'crlf'   # .editorconfig default
}

function NormalizeFile([string]$full) {
    if (-not $full -or -not (Test-Path -LiteralPath $full -PathType Leaf)) { return }
    try { $full = (Resolve-Path -LiteralPath $full).Path } catch { return }

    # Scope: only files inside the active worktree root.
    if (-not $full.StartsWith($script:RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) { return }

    # Shell scripts must stay LF regardless of convention.
    if ($full -match '\.sh$') { return }

    $bytes = [System.IO.File]::ReadAllBytes($full)
    if ($bytes.Length -eq 0) { return }

    # Binary guard: a NUL byte in the first 8KB => treat as binary, leave untouched.
    $scan = [Math]::Min($bytes.Length, 8192)
    for ($i = 0; $i -lt $scan; $i++) {
        if ($bytes[$i] -eq 0) { return }
    }

    $relpath = Get-RelPath $full
    $target = Get-TargetEol $full $relpath

    $out = New-Object 'System.Collections.Generic.List[byte]' ($bytes.Length + 64)
    $changed = $false

    if ($target -eq 'crlf') {
        # Ensure every LF is preceded by a CR.
        for ($i = 0; $i -lt $bytes.Length; $i++) {
            $b = $bytes[$i]
            if ($b -eq 0x0A -and ($i -eq 0 -or $bytes[$i - 1] -ne 0x0D)) {
                $out.Add(0x0D)
                $changed = $true
            }
            $out.Add($b)
        }
    }
    else {
        # Strip the CR from every CRLF (\r\n -> \n). Bare CRs (not before LF) are left alone.
        for ($i = 0; $i -lt $bytes.Length; $i++) {
            $b = $bytes[$i]
            if ($b -eq 0x0D -and ($i + 1) -lt $bytes.Length -and $bytes[$i + 1] -eq 0x0A) {
                $changed = $true
                continue
            }
            $out.Add($b)
        }
    }

    if ($changed) {
        [System.IO.File]::WriteAllBytes($full, $out.ToArray())
    }
}

# Resolve the active worktree root from $startDir and set $script:RepoRoot — but ONLY if
# that worktree shares the canonical repo's common .git dir. Every Cognito worktree (main +
# B/C/D + temp detached) shares one common dir; every other repo differs, so this gate keeps
# the hook a strict no-op outside the Cognito worktree family without hardcoding worktree names.
# Returns $true when $script:RepoRoot is set and in-scope.
function Set-ActiveRepoRoot([string]$startDir) {
    if (-not $startDir -or -not (Test-Path -LiteralPath $startDir)) { return $false }
    $candidateCommon = Get-CommonDirAbs $startDir
    if (-not $candidateCommon -or -not ($candidateCommon -ieq $canonicalCommon)) { return $false }
    $top = Invoke-Git $startDir @('rev-parse', '--show-toplevel')
    if (-not $top) { return $false }
    $top = Resolve-Abs ($top -replace '/', '\')
    if (-not $top) { return $false }
    $script:RepoRoot = $top
    return $true
}

# Edit|Write: a single known file. Start dir = the file's directory.
$filePath = $data.tool_input.file_path
if ($filePath) {
    $startDir = $null
    try { $startDir = Split-Path -Parent $filePath } catch { }
    if (Set-ActiveRepoRoot $startDir) {
        NormalizeFile $filePath
    }
    $ok; exit
}

# Bash: only act when the command plausibly rewrote files in place. This keeps the
# git scan off the hot path for read-only commands (grep -i, ls, git log, ...).
$cmd = [string]$data.tool_input.command
if (-not $cmd) { $ok; exit }

$inPlaceEdit = '(?i)(\bsed\b[^|&;]*\s-i|\bperl\b[^|&;]*\s-i|\bg?awk\b[^|&;]*inplace|\bdos2unix\b|\bunix2dos\b)'
if ($cmd -notmatch $inPlaceEdit) { $ok; exit }

# Start dir = the command's cwd (the active worktree), falling back to $PWD.
$startDir = if ($data.cwd) { [string]$data.cwd } else { $PWD.Path }
if (-not (Set-ActiveRepoRoot $startDir)) { $ok; exit }

$ErrorActionPreference = 'Continue'
try {
    $status = & git -C $script:RepoRoot -c core.quotepath=false status --porcelain --untracked-files=all 2>$null
}
catch {
    $ok; exit
}

foreach ($line in $status) {
    if (-not $line -or $line.Length -lt 4) { continue }
    $rel = $line.Substring(3)
    if ($rel -match ' -> ') { $rel = ($rel -split ' -> ')[-1] }   # renames: take the new path
    $rel = $rel.Trim('"')
    NormalizeFile (Join-Path $script:RepoRoot $rel)
}

$ok

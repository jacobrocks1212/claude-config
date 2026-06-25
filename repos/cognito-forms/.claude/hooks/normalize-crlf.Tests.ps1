# Self-contained TDD harness for normalize-crlf.ps1.
#
# The hook hard-codes the Cognito repo root but honors an optional $env:CRLF_HOOK_REPOROOT
# override (production-inert: unset in production). These tests spin up throwaway `git init`
# repos, commit fixtures with known EOL, drive the hook over stdin JSON, and assert the
# working-tree bytes converge on each file's committed (or sibling/default) EOL.
#
# Run: powershell.exe -ExecutionPolicy Bypass -File normalize-crlf.Tests.ps1
# Exits non-zero if any case fails.

$ErrorActionPreference = 'Stop'
$HookPath = Join-Path $PSScriptRoot 'normalize-crlf.ps1'

if (-not (Test-Path -LiteralPath $HookPath)) {
    Write-Host "FAIL: hook not found at $HookPath" -ForegroundColor Red
    exit 1
}

$script:Pass = 0
$script:Fail = 0

function Assert([bool]$cond, [string]$name) {
    if ($cond) {
        $script:Pass++
        Write-Host "PASS: $name" -ForegroundColor Green
    }
    else {
        $script:Fail++
        Write-Host "FAIL: $name" -ForegroundColor Red
    }
}

# --- helpers -------------------------------------------------------------

function New-TempRepo {
    $dir = Join-Path ([System.IO.Path]::GetTempPath()) ("crlfhook_" + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    & git -C $dir init -q 2>&1 | Out-Null
    & git -C $dir config user.email "test@test.local" 2>&1 | Out-Null
    & git -C $dir config user.name "Test" 2>&1 | Out-Null
    & git -C $dir config commit.gpgsign false 2>&1 | Out-Null
    return $dir
}

# Add a linked worktree to $repo at $repo/<name> on a new branch; returns the worktree path.
function New-Worktree([string]$repo, [string]$name) {
    $wt = Join-Path $repo $name
    & git -C $repo worktree add -q -b "$name`_br" $wt 2>&1 | Out-Null
    return $wt
}

function Write-Bytes([string]$path, [byte[]]$bytes) {
    $full = [System.IO.Path]::GetFullPath($path)
    [System.IO.File]::WriteAllBytes($full, $bytes)
}

function Read-Bytes([string]$path) {
    return [System.IO.File]::ReadAllBytes([System.IO.Path]::GetFullPath($path))
}

# Build bytes from logical lines joined with the requested EOL (no trailing newline added
# unless $trailing). ASCII text only.
function Make-Bytes([string[]]$lines, [string]$eol, [bool]$trailing = $true) {
    $sep = if ($eol -eq 'crlf') { "`r`n" } else { "`n" }
    $text = ($lines -join $sep)
    if ($trailing) { $text += $sep }
    return [System.Text.Encoding]::ASCII.GetBytes($text)
}

function Commit-File([string]$repo, [string]$relpath, [byte[]]$bytes) {
    $full = Join-Path $repo $relpath
    $parent = Split-Path -Parent $full
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Write-Bytes $full $bytes
    # -crlf attribute so git stores bytes verbatim (mirrors Cognito's `.gitattributes * -crlf`).
    $ga = Join-Path $repo '.gitattributes'
    if (-not (Test-Path -LiteralPath $ga)) { Write-Bytes $ga ([System.Text.Encoding]::ASCII.GetBytes("* -crlf`n")) }
    & git -C $repo add -A 2>&1 | Out-Null
    & git -C $repo commit -q -m "fixture $relpath" 2>&1 | Out-Null
}

# Invoke the hook with a tool_input.file_path payload against $repo.
function Invoke-HookFile([string]$repo, [string]$fileFull) {
    $payload = @{ tool_input = @{ file_path = $fileFull } } | ConvertTo-Json -Compress
    $prev = $env:CRLF_HOOK_REPOROOT
    $env:CRLF_HOOK_REPOROOT = $repo
    try {
        $out = $payload | & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $HookPath 2>&1
    }
    finally {
        if ($null -eq $prev) { Remove-Item Env:CRLF_HOOK_REPOROOT -ErrorAction SilentlyContinue }
        else { $env:CRLF_HOOK_REPOROOT = $prev }
    }
    return $out
}

# Invoke the hook with a tool_input.command payload against $repo. The payload's top-level
# `cwd` is the active worktree the Bash command ran in (defaults to $repo).
function Invoke-HookCmd([string]$repo, [string]$command, [string]$cwd = $null) {
    if (-not $cwd) { $cwd = $repo }
    $payload = @{ cwd = $cwd; tool_input = @{ command = $command } } | ConvertTo-Json -Compress
    $prev = $env:CRLF_HOOK_REPOROOT
    $env:CRLF_HOOK_REPOROOT = $repo
    try {
        $out = $payload | & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $HookPath 2>&1
    }
    finally {
        if ($null -eq $prev) { Remove-Item Env:CRLF_HOOK_REPOROOT -ErrorAction SilentlyContinue }
        else { $env:CRLF_HOOK_REPOROOT = $prev }
    }
    return $out
}

# Invoke the hook with raw stdin text (for malformed-JSON contract test).
function Invoke-HookRaw([string]$repo, [string]$stdin) {
    $prev = $env:CRLF_HOOK_REPOROOT
    $env:CRLF_HOOK_REPOROOT = $repo
    try {
        $out = $stdin | & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $HookPath 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        if ($null -eq $prev) { Remove-Item Env:CRLF_HOOK_REPOROOT -ErrorAction SilentlyContinue }
        else { $env:CRLF_HOOK_REPOROOT = $prev }
    }
    return [pscustomobject]@{ Out = ($out -join "`n"); Code = $code }
}

function Has-CRLF([byte[]]$b) {
    for ($i = 1; $i -lt $b.Length; $i++) { if ($b[$i] -eq 0x0A -and $b[$i-1] -eq 0x0D) { return $true } }
    return $false
}

function Has-BareLF([byte[]]$b) {
    for ($i = 0; $i -lt $b.Length; $i++) {
        if ($b[$i] -eq 0x0A -and ($i -eq 0 -or $b[$i-1] -ne 0x0D)) { return $true }
    }
    return $false
}

function Count-CRLF([byte[]]$b) {
    $n = 0
    for ($i = 1; $i -lt $b.Length; $i++) { if ($b[$i] -eq 0x0A -and $b[$i-1] -eq 0x0D) { $n++ } }
    return $n
}

function Count-BareLF([byte[]]$b) {
    $n = 0
    for ($i = 0; $i -lt $b.Length; $i++) {
        if ($b[$i] -eq 0x0A -and ($i -eq 0 -or $b[$i-1] -ne 0x0D)) { $n++ }
    }
    return $n
}

function Bytes-Equal([byte[]]$a, [byte[]]$b) {
    if ($a.Length -ne $b.Length) { return $false }
    for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { return $false } }
    return $true
}

$repos = @()

try {
    # --- Case 1: tracked committed-CRLF, working tree wrongly LF -> restore CRLF ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'a.cs' (Make-Bytes @('using System;', 'class A {}') 'crlf')
        $full = Join-Path $repo 'a.cs'
        Write-Bytes $full (Make-Bytes @('using System;', 'class A {}') 'lf')   # corrupt to LF
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert ((Has-CRLF $b) -and -not (Has-BareLF $b)) 'Case1: tracked CRLF file restored to CRLF'
    }.Invoke()

    # --- Case 2: tracked committed-LF (.html template), working tree CRLF -> restore LF (THE regression) ---
    {
        $repo = New-TempRepo; $script:repos += $repo
        New-Item -ItemType Directory -Path (Join-Path $repo 'NotificationTemplates') -Force | Out-Null
        Commit-File $repo 'NotificationTemplates/t.html' (Make-Bytes @('<div>', '</div>') 'lf')
        $full = Join-Path $repo 'NotificationTemplates/t.html'
        Write-Bytes $full (Make-Bytes @('<div>', '</div>') 'crlf')   # corrupt to CRLF
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert ((Has-BareLF $b) -and -not (Has-CRLF $b)) 'Case2: tracked LF template restored to LF (regression fixed)'
    }.Invoke()

    # --- Case 3: tracked file already matching committed EOL -> no write (idempotent) ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'b.cs' (Make-Bytes @('class B {}') 'crlf')
        $full = Join-Path $repo 'b.cs'
        $before = Read-Bytes $full
        $mtimeBefore = (Get-Item -LiteralPath $full).LastWriteTimeUtc
        Start-Sleep -Milliseconds 50
        Invoke-HookFile $repo $full | Out-Null
        $after = Read-Bytes $full
        $mtimeAfter = (Get-Item -LiteralPath $full).LastWriteTimeUtc
        Assert ((Bytes-Equal $before $after) -and ($mtimeBefore -eq $mtimeAfter)) 'Case3: matching EOL not rewritten (bytes+mtime unchanged)'
    }.Invoke()

    # --- Case 4a: new untracked file, CRLF siblings -> CRLF ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'src/x1.cs' (Make-Bytes @('class X1 {}') 'crlf')
        Commit-File $repo 'src/x2.cs' (Make-Bytes @('class X2 {}') 'crlf')
        $full = Join-Path $repo 'src/new.cs'
        Write-Bytes $full (Make-Bytes @('class New {}') 'lf')   # new file, wrong EOL
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert ((Has-CRLF $b) -and -not (Has-BareLF $b)) 'Case4a: untracked file w/ CRLF siblings -> CRLF'
    }.Invoke()

    # --- Case 4b: new untracked file, LF siblings -> LF ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'tpl/a.html' (Make-Bytes @('<a>') 'lf')
        Commit-File $repo 'tpl/b.html' (Make-Bytes @('<b>') 'lf')
        $full = Join-Path $repo 'tpl/new.html'
        Write-Bytes $full (Make-Bytes @('<new>') 'crlf')   # new file, wrong EOL
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert ((Has-BareLF $b) -and -not (Has-CRLF $b)) 'Case4b: untracked file w/ LF siblings -> LF'
    }.Invoke()

    # --- Case 4c: new untracked file, no siblings -> CRLF (editorconfig default) ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'readme.txt' (Make-Bytes @('hi') 'crlf')   # different extension, not a sibling
        $full = Join-Path $repo 'lonely.cs'
        Write-Bytes $full (Make-Bytes @('class Lonely {}') 'lf')
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert ((Has-CRLF $b) -and -not (Has-BareLF $b)) 'Case4c: untracked file w/ no siblings -> CRLF default'
    }.Invoke()

    # --- Case 5: .sh file -> left LF regardless ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'script.sh' (Make-Bytes @('#!/bin/sh', 'echo hi') 'crlf')  # committed CRLF even
        $full = Join-Path $repo 'script.sh'
        Write-Bytes $full (Make-Bytes @('#!/bin/sh', 'echo hi') 'lf')   # working tree LF
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert (-not (Has-CRLF $b)) 'Case5: .sh left LF (never CRLFed even when committed CRLF)'
    }.Invoke()

    # --- Case 6: binary file (contains NUL) -> untouched ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        $bin = [byte[]]@(0x48, 0x00, 0x49, 0x0A, 0x4A)   # H NUL I LF J  (bare LF present)
        Commit-File $repo 'data.bin' $bin
        $full = Join-Path $repo 'data.bin'
        $before = Read-Bytes $full
        Invoke-HookFile $repo $full | Out-Null
        $after = Read-Bytes $full
        Assert (Bytes-Equal $before $after) 'Case6: binary file (NUL) untouched'
    }.Invoke()

    # --- Case 7: Bash branch, perl -i, mixed repo -> each file ends at its committed EOL ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'code.cs' (Make-Bytes @('class C {}') 'crlf')
        Commit-File $repo 'page.html' (Make-Bytes @('<p>') 'lf')
        $csFull = Join-Path $repo 'code.cs'
        $htmlFull = Join-Path $repo 'page.html'
        # Simulate an agent's manual LF normalization that wrongly flips BOTH:
        Write-Bytes $csFull (Make-Bytes @('class C {}', 'edit') 'lf')      # CRLF file now LF (wrong)
        Write-Bytes $htmlFull (Make-Bytes @('<p>', 'edit') 'crlf')         # LF file now CRLF (wrong)
        Invoke-HookCmd $repo "perl -i -pe 's/\r\n/\n/g' page.html" | Out-Null
        $cs = Read-Bytes $csFull
        $html = Read-Bytes $htmlFull
        $csOk = (Has-CRLF $cs) -and -not (Has-BareLF $cs)
        $htmlOk = (Has-BareLF $html) -and -not (Has-CRLF $html)
        Assert ($csOk -and $htmlOk) 'Case7: Bash branch normalizes each modified file to its own committed EOL'
    }.Invoke()

    # --- Case 9: tracked blob with mixed EOL, bare-LF DOMINANT -> target LF (not first-CRLF) ----
    # Mirrors Cognito.Core/Anthropic/*.cs (a few CRLF lines among hundreds of bare-LF).
    {
        $repo = New-TempRepo; $script:repos += $repo
        # 2 CRLF lines + 200 LF lines, committed as-is (mostly LF).
        $crlfSeg = [System.Text.Encoding]::ASCII.GetBytes("a`r`nb`r`n")
        $lfLines = (1..200 | ForEach-Object { "line$_" }) -join "`n"
        $lfSeg = [System.Text.Encoding]::ASCII.GetBytes($lfLines + "`n")
        $committed = $crlfSeg + $lfSeg
        Commit-File $repo 'mixed.cs' $committed
        $full = Join-Path $repo 'mixed.cs'
        $before = Read-Bytes $full
        # Sanity on the fixture: bare-LF must dominate.
        $fixtureDominantLF = (Count-BareLF $before) -gt (Count-CRLF $before)
        Invoke-HookFile $repo $full | Out-Null
        $after = Read-Bytes $full
        # Dominant target is LF: the hook must NOT CR-prefix the 200 bare LFs (the first-CRLF
        # bug would jump CRLF 2 -> 202). Converging the 2 stray CRLF down to LF is acceptable
        # (minimal diff toward the dominant convention); CRLF count must never INCREASE.
        $stillLfDominant = (Count-BareLF $after) -gt (Count-CRLF $after)
        $notMassCRLFed = (Count-CRLF $after) -le (Count-CRLF $before)
        Assert ($fixtureDominantLF -and $stillLfDominant -and $notMassCRLFed) 'Case9: mixed blob, bare-LF dominant -> LF target (not first-CRLF -> mass CRLF)'
    }.Invoke()

    # --- Case 10a: sibling worktree resolves correctly (common-dir gate PASSES) ----
    # repoRoot must follow the file into a linked worktree, normalizing to THAT worktree's HEAD.
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'seed.cs' (Make-Bytes @('seed') 'crlf')   # main needs >=1 commit before worktree add
        $wt = New-Worktree $repo 'wt2'
        Commit-File $wt 'w.cs' (Make-Bytes @('class W {}') 'crlf')   # committed CRLF in the worktree
        $full = Join-Path $wt 'w.cs'
        Write-Bytes $full (Make-Bytes @('class W {}') 'lf')          # corrupt working tree to LF
        # Env override = MAIN repo; the worktree shares main's common dir, so the gate passes
        # and repoRoot resolves to the worktree (not main).
        Invoke-HookFile $repo $full | Out-Null
        $b = Read-Bytes $full
        Assert ((Has-CRLF $b) -and -not (Has-BareLF $b)) 'Case10a: file in sibling worktree normalized to worktree HEAD EOL'
    }.Invoke()

    # --- Case 10b: out-of-family repo is a strict NO-OP (common-dir gate FAILS) ----
    {
        $repo = New-TempRepo; $script:repos += $repo       # canonical (env override) repo
        $other = New-TempRepo; $script:repos += $other     # unrelated repo, different common dir
        Commit-File $other 'x.cs' (Make-Bytes @('class X {}') 'crlf')
        $full = Join-Path $other 'x.cs'
        $corrupt = Make-Bytes @('class X {}') 'lf'
        Write-Bytes $full $corrupt
        Invoke-HookFile $repo $full | Out-Null   # canonical=$repo, file lives in $other
        $b = Read-Bytes $full
        Assert (Bytes-Equal $corrupt $b) 'Case10b: file outside the Cognito worktree family left untouched'
    }.Invoke()

    # --- Case 10c: Bash branch targets the worktree named by cwd, not main ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        Commit-File $repo 'seed.cs' (Make-Bytes @('seed') 'crlf')
        # Commit MAIN's tracked file BEFORE adding the worktree, so main's later `git add -A`
        # is never invoked while the embedded wt3 dir exists (avoids git's embedded-repo warning).
        Commit-File $repo 'main.cs' (Make-Bytes @('class M {}') 'crlf')
        $wt = New-Worktree $repo 'wt3'
        Commit-File $wt 'code.cs' (Make-Bytes @('class C {}') 'crlf')   # CRLF-committed in worktree
        Commit-File $wt 'page.html' (Make-Bytes @('<p>') 'lf')         # LF-committed in worktree
        # MAIN's main.cs is corrupted but must NOT be touched (proves scan targets the worktree).
        $mainFull = Join-Path $repo 'main.cs'
        $mainCorrupt = Make-Bytes @('class M {}') 'lf'
        Write-Bytes $mainFull $mainCorrupt
        # Corrupt both worktree files in the wrong direction:
        $csFull = Join-Path $wt 'code.cs'
        $htmlFull = Join-Path $wt 'page.html'
        Write-Bytes $csFull (Make-Bytes @('class C {}', 'edit') 'lf')
        Write-Bytes $htmlFull (Make-Bytes @('<p>', 'edit') 'crlf')
        Invoke-HookCmd $repo "sed -i 's/x/y/' page.html" $wt | Out-Null
        $cs = Read-Bytes $csFull
        $html = Read-Bytes $htmlFull
        $main = Read-Bytes $mainFull
        $csOk = (Has-CRLF $cs) -and -not (Has-BareLF $cs)
        $htmlOk = (Has-BareLF $html) -and -not (Has-CRLF $html)
        $mainUntouched = Bytes-Equal $mainCorrupt $main
        Assert ($csOk -and $htmlOk -and $mainUntouched) 'Case10c: Bash branch scans the cwd worktree (main left untouched)'
    }.Invoke()

    # --- Case 8: malformed/empty stdin -> {"continue":true} and exit 0 ----
    {
        $repo = New-TempRepo; $script:repos += $repo
        $r1 = Invoke-HookRaw $repo ''
        $r2 = Invoke-HookRaw $repo 'not json at all {{{'
        $ok1 = ($r1.Out -match '"continue"\s*:\s*true') -and ($r1.Code -eq 0)
        $ok2 = ($r2.Out -match '"continue"\s*:\s*true') -and ($r2.Code -eq 0)
        Assert ($ok1 -and $ok2) 'Case8: malformed/empty stdin -> {"continue":true} exit 0'
    }.Invoke()
}
finally {
    foreach ($r in $script:repos) {
        try { Remove-Item -LiteralPath $r -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}

Write-Host ""
Write-Host "==== Summary: $script:Pass passed, $script:Fail failed ====" -ForegroundColor Cyan
if ($script:Fail -gt 0) { exit 1 } else { exit 0 }

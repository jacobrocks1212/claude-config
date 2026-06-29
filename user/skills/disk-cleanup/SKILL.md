---
name: disk-cleanup
description: Audit and recover disk space on Jacob's Windows dev machine. Invoke when the user reports low disk space or asks to analyze/clean up disk usage. Use the read-only scan scripts first, then target the biggest offenders with the destructive scripts only after explicit approval.
version: 1.0.0
allowed-tools: ["Bash", "Read", "Edit", "Write"]
---

# Disk Cleanup

A runbook for systematically recovering disk space on Jacob's Windows dev box. All scripts live in `$env:USERPROFILE\.claude\skills\disk-cleanup\`. Read-only scripts are safe to run any time. Destructive scripts require confirmation and should be run from an **elevated PowerShell** (admin).

Scripts use absolute paths in every example below so you never need to `cd` first.

## Environment conventions

- **Paths**: Use absolute Windows paths. In bash prompts, prefer forward slashes: `'C:/Users/JacobMadsen/...'`. Avoid trailing backslash before a closing double-quote (`"C:\"` breaks bash's escape handling; use `'C:/'` instead).
- **Encoding**: Write PowerShell scripts as ASCII-only. Windows PowerShell 5.1 reads `.ps1` without BOM as ANSI/Windows-1252, so em-dashes or smart quotes cause parse errors. Stick to plain `-`, `'`, `"`.
- **Long-running scans**: launch via `Bash` with `run_in_background=true`, tell the user an estimate, then `ScheduleWakeup` for a check-in. Scripts write reports under `C:\temp\` so the model can `Read` the output directly.
- **Admin**: Scripts requiring admin start with `#Requires -RunAsAdministrator` or a manual check. The user usually already has an elevated pwsh open — reuse it rather than prompting UAC via `Start-Process -Verb RunAs` (which can't be accepted from the agent).

## Workflow

### Phase 1 — Survey (read-only)

1. **Drive summary + top folders across C:\**
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Scan-Disk.ps1" -Root 'C:/' -MinSizeMB 500
   ```
   `Scan-Disk.ps1` has no `-Depth` parameter. Its knobs are `-Root`, `-TopFolders` (default 40), `-TopFiles` (default 30), `-MinSizeMB` (default 250), `-DrillIntoTop` (default 10), `-DrillMinSizeMB` (default 50), `-CsvOut`, `-ReportPath`. A single run already produces the top-level folder list, the top files, a drill-in of the top `-DrillIntoTop` folders, and a `Known disk hogs` section — so this one command covers most of the survey.
   Produces `C:\temp\scan-<root>.txt`. Look for:
   - `pagefile.sys` / `hiberfil.sys` (see Phase 4)
   - `C:\temp` (almost always disposable)
   - `C:\Windows\WinSxS` (use DISM, never manual delete)
   - `C:\Users\<user>` total (drill in next)

2. **User profile drill-in**
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Scan-Disk.ps1" -Root 'C:/Users/JacobMadsen' -DrillIntoTop 10
   ```
   The top-level sizer can undercount directories like `AppData` due to access-denied junctions. The drill-in bypasses that by re-entering the directory to size its children.

3. **Per-repo sizing** for large `source/repos` folders — use `Scan-Disk.ps1` with `-Root` set to the repos dir, or drill in one level via the script.

4. **Active-repo cleanup audit**
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Audit-RepoCleanup.ps1" -Root "C:/Users/JacobMadsen/source/repos/<repo>"
   ```
   Reports `node_modules`, `bin`, `obj`, Rust `target`, `.next`, `.nx`, `dist/build/out`, Python caches, IDE caches, `TestResults`, `coverage`, and large stray files. Categorizes so Jacob can decide which are regeneratable vs in-active-use.

### Phase 2 — Quick wins (safe, reversible)

These can run without per-item approval if Jacob OK'd the category:

- `cleanmgr /sageset:65535` then `cleanmgr /sagerun:65535` — Disk Cleanup "system files" mode; nukes Windows Update cleanup, delivery optimization, driver packages, etc.
- `Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase` — WinSxS cleanup, typically 2-6 GB. `/ResetBase` is permanent.
- `Clear-RecycleBin -Force`
- `scoop cleanup *; scoop cache rm *`
- `dotnet nuget locals all --clear`
- `docker system prune -a --volumes` (Docker Desktop must be running)

### Phase 3 — Large deletions (confirm each)

- **Long-path build folders (node_modules, Rust target/)**: Explorer fails with "Invalid MS-DOS function" because of MAX_PATH. Use the robocopy mirror trick:
   ```powershell
   mkdir C:\temp\_empty
   robocopy C:\temp\_empty <targetPath> /MIR /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
   Remove-Item <targetPath> -Recurse -Force
   Remove-Item C:\temp\_empty -Force
   ```

- **Repo build artifacts**: prefer `git clean -xfd --dry-run` first to see what would go; don't mass-delete without review in repos Jacob is actively working in.

- **Orphan IIS app pool profiles**: If `C:\Users\` has a bunch of folders matching `<project>-<something>`, those are almost certainly IIS app pool user profiles (not worktrees — see `worktree-wizard-gap` below). Use:
   ```powershell
   # Audit only
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Remove-CognitoFormsProfiles.ps1"
   # Apply (removes orphan profiles whose app pool is gone)
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Remove-CognitoFormsProfiles.ps1" -Apply
   # Also tear down the app pools themselves
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Remove-CognitoFormsProfiles.ps1" -Apply -RemoveAppPools
   ```

### Phase 4 — OS-level tweaks (require reboot)

- **Hibernation file** (`hiberfil.sys`, often 10+ GB):
  `powercfg /h off` from elevated shell. Removes immediately. Disables Fast Startup — rarely missed on a dev box.

- **Pagefile** — only shrink if commit charge is comfortably under RAM. Check first:
   ```powershell
   Get-CimInstance Win32_OperatingSystem | Select-Object `
     @{N='TotalRAM_GB';E={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}},
     @{N='CommitInUse_GB';E={[math]::Round(($_.TotalVirtualMemorySize - $_.FreeVirtualMemory)/1MB,1)}}
   Get-CimInstance Win32_PageFileUsage | Select-Object Name, AllocatedBaseSize, PeakUsage
   ```
   If peak usage << allocated and commit << RAM, shrink it:
   ```powershell
   powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.claude\skills\disk-cleanup\Set-Pagefile.ps1" -SizeMB 16384
   ```
   Requires reboot for the file to physically shrink. Default target: 16 GB. Never set to 0 (breaks crash dumps).

## Gotchas and lessons learned

### `Remove-Item` on `C:\Users\` subfolders requires admin
Even for folders owned by Administrators, deleting children of `C:\Users\` from a non-elevated shell returns "Access denied". Always use Jacob's existing elevated pwsh for profile-removal work.

### "Worktree shells" in `C:\Users\` are actually IIS app pool profiles
`worktree-wizard.ps1` creates IIS app pools named `Cognito Forms-<branch>`. When a pool first serves a request, Windows materializes a user profile at `C:\Users\Cognito Forms-<branch>\`. The teardown path removes the pool but does NOT remove the profile. Over months this accumulates into dozens of 3 MB orphan folders. **Don't try to delete them with `Remove-Item`** — use `Remove-CimInstance` on `Win32_UserProfile` (what `Remove-CognitoFormsProfiles.ps1` does).

### Windows PowerShell 5.1 encoding
`Write`-created `.ps1` files are UTF-8 no BOM. PowerShell 5.1 reads them as ANSI unless they have a BOM. Non-ASCII characters (em-dash, smart quotes, curly apostrophes) get mangled into byte sequences that break parsing. **Keep scripts ASCII-only.**

### `Directory.EnumerateFiles` recursion with AllDirectories throws on first access-denied directory
Wrap per-file operations in `try/catch`. Access-denied on `C:\$Recycle.Bin\S-1-5-18`, `AppData` subjunctions, and system profiles is the norm.

### Folder-size algorithms: O(N * depth) bites at profile depth
The original `Analyze-DiskUsage.ps1` recursively sized the root AND every descendant to depth N, re-walking subtrees once per ancestor. For a dev profile with 1617 folders containing millions of files (node_modules, .git packs), this ran 15+ minutes. **`Scan-Disk.ps1` does single-pass plus drill-in — keep it that way.**

### `C:\temp\strudel-build` / Tauri builds are massive
Tauri/Rust `target/` directories routinely hit 10-20 GB. They're disposable and regenerate on next `cargo build`. Long paths in `src-tauri/target/*/deps/` are the usual "Invalid MS-DOS function" culprits.

## Suggested remediation (`worktree-wizard.ps1`)

`Cognito Forms/worktree-wizard.ps1` at `Teardown-IIS-DualSite` already removes the site and pool but leaves the user profile. See the edit applied to the main branch adding `Remove-CimInstance` on `Win32_UserProfile` right after `Remove-WebAppPool`. The side-repo copy still needs the same fix.

## File inventory

| File | Purpose | Admin? | Destructive? |
|------|---------|--------|--------------|
| `Scan-Disk.ps1` | Drive summary, top folders/files, drill-in, known hogs | No | No |
| `Audit-RepoCleanup.ps1` | Categorized cleanup audit for a repo (build artifacts) | No | No |
| `Remove-CognitoFormsProfiles.ps1` | Audit + remove orphan IIS app pool profiles | Yes | Yes (with `-Apply`) |
| `Set-Pagefile.ps1` | Set fixed pagefile size (default 16 GB) | Yes | Yes (reboot required) |

All scripts write their reports to `C:\temp\` so the agent can `Read` them directly.

---
name: local-site
description: USE WHEN user has issues with their local development site, IIS, SSL certificates, or local environment. USE WHEN user mentions "local site", "local.cognito.dev", "connection not secure", "IIS", "certificate expired", "can't access local", "site not loading", or "https error". Triggers on "local site", "local.cognito.dev", "harness.cognito.dev", "IIS", "certificate", "SSL", "connection not secure", "localhost", "dev environment", "local environment".
---

# Local Site Troubleshooting

## Environment Overview

**Local URLs:**
- Main site: `https://local.cognito.dev/`
- Harness: `https://harness.cognito.dev/`
- Webpack dev server: `https://localhost:3000/` (uses mkcert)

**IIS Configuration:**
- App Pool: `CognitoForms` (NetworkService with user profile loaded)
- Sites: `cognito-services`, `cognito-harness`
- SSL: Wildcard cert `*.cognito.dev` on port 443

**Config Files:**
- `Cognito.Services/Web.Local.config` - Local service config
- `Cognito.Forms.UnitTests/appSettings.Local.config` - Test config
- `Cognito.QueueJob/App.Local.config` - Queue job config

## Process Scripts Reference

Located in `./process/`:

| Script | Purpose | Elevated? |
|--------|---------|-----------|
| `initial-setup.ps1` | Full dev environment setup | Mixed |
| `setup-sites.ps1` | Create IIS sites, app pools, SSL bindings, hosts | Yes |
| `create-local-cert.ps1 -TLD cognito.dev` | Generate wildcard SSL cert | Yes |
| `install-webpack-cert.ps1` | Generate mkcert cert for localhost | No |
| `build-solution.ps1` | Build Cognito.sln with MSBuild | No |
| `generate-user-config.ps1` | Create local config files | No |
| `set-machinekey-permissions.ps1` | Grant MachineKeys folder access | Yes |
| `install-apps.ps1` | Install dev tools (VS Code, mkcert, etc.) | No |
| `install-node.ps1` | Install Node.js v24.1.0 via nvm + pnpm | No |

## Troubleshooting Workflow

### Step 1: Identify the Issue

Ask:
1. What URL is failing? (`local.cognito.dev`, `localhost`, webpack?)
2. What error? (SSL, 500, connection refused?)
3. When did it last work?

### Step 2: Common Issues

#### SSL "Connection not secure"

**For `*.cognito.dev` (IIS):**

1. Check certificate expiry:
```powershell
cmd.exe /c "certutil -store Root > C:\temp\certs.txt"
# Then grep for cognito.dev and check NotAfter date
```

2. If expired, regenerate (elevated PowerShell):
```powershell
cd "C:\Users\JacobMadsen\source\repos\Cognito Forms"
.\process\create-local-cert.ps1 -TLD cognito.dev
.\process\setup-sites.ps1
```

3. Delete old expired certs:
```powershell
certutil -delstore Root [thumbprint]
```

4. Clear Chrome cert cache or test in Incognito

**For `localhost` (webpack):**

1. Check mkcert CA:
```powershell
mkcert -install
```

2. Regenerate if needed:
```powershell
del webpack-dev-cert.pem webpack-dev-cert-key.pem
.\process\install-webpack-cert.ps1
```

#### IIS Not Responding (503)

1. Check IIS status:
```powershell
iisreset /status
```

2. Check app pool (elevated):
```powershell
Import-Module WebAdministration
Get-WebAppPoolState CognitoForms
Restart-WebAppPool CognitoForms
```

3. Check Event Viewer for crashes

#### 500 Errors

1. Verify `Web.Local.config` exists
2. Run `.\process\generate-user-config.ps1`
3. Check Azure auth in VS: Tools > Azure Service Authentication
4. Fix machine key permissions:
```powershell
.\process\set-machinekey-permissions.ps1
```

#### BadImageFormatException / Reference Assembly Errors

**Symptom:** Error like "Cannot load a reference assembly for execution" or "Reference assemblies should not be loaded for execution" with `System.Text.RegularExpressions` or similar System.* assemblies.

**Root Cause:** The `Cognito` project targets `netstandard2.0` and has `<CopyLocalLockFileAssemblies>true</CopyLocalLockFileAssemblies>` in its csproj. This copies .NET Standard facade/reference assemblies to its output. When `Cognito.Services` builds and references `Cognito`, these facade assemblies can end up in the IIS bin folder. IIS then tries to load them at runtime, which fails because they're compile-time-only assemblies.

**Quick Fix:**
```powershell
# Stop IIS to release file locks (elevated)
iisreset /stop

# Delete the problematic DLLs from bin folders
Remove-Item -Force "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Services\bin\System.Text.RegularExpressions.dll"
Remove-Item -Force "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito\bin\Debug\netstandard2.0\System.Text.RegularExpressions.dll"

# Restart IIS
iisreset /start
```

**Find all problematic DLLs:**
```powershell
Get-ChildItem -Path "C:\Users\JacobMadsen\source\repos\Cognito Forms" -Filter "System.Text.RegularExpressions.dll" -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.FullName -like '*\bin\*' }
```

**If it keeps recurring after rebuilds:** The `System.Text.RegularExpressions` PackageReference in `Cognito.Services\Cognito.Services.csproj` is unnecessary for .NET Framework 4.7.2 (it's built-in). Removing the package reference would be a permanent fix.

#### Hosts File Missing Entries

Check:
```powershell
type C:\windows\system32\drivers\etc\hosts | findstr cognito
```

Should have:
```
127.0.0.1       local.cognito.dev
127.0.0.1       harness.cognito.dev
```

If missing, run `.\process\setup-sites.ps1` (elevated)

#### Nx Project Graph Failure

**Symptom:** `pnpm serve:spa` (or any Nx command) fails with:
```
NX   Failed to process project graph.
The "nx/js/dependencies-and-lockfile" plugin threw an error while creating dependencies:
Target project does not exist: npm:<package>@<version>
```

**Root Cause:** The Nx daemon's cached project graph is stale — it references npm packages that no longer match what's in `node_modules` or the lockfile (e.g. after a branch switch, merge from main, or dependency update).

**Fix:**
```powershell
cd Cognito.Web.Client
npx nx reset       # Clear Nx daemon cache
pnpm install       # Ensure node_modules matches lockfile
pnpm serve:spa     # Retry
```

If `pnpm install` reports the lockfile is already up to date and the error persists, try a clean reinstall:
```powershell
Remove-Item -Recurse -Force node_modules
pnpm install
```

#### Node/Webpack Issues

1. Check version:
```powershell
node -v  # Should be 24.1.0
nvm list
nvm use 24.1.0
```

2. Reinstall deps:
```powershell
cd Cognito.Web.Client
pnpm install
```

#### pnpm Install Fails with "UNKNOWN: unknown error, open"

**Symptom:** `pnpm install` fails near the end with:
```
UNKNOWN: unknown error, open 'C:\...\node_modules\<package>\package.json'
```
All ~4000 packages resolve and download, but it fails when writing to node_modules.

**Root Causes:**
1. **Corrupted scoop nvm** — files in `~\scoop\apps\nvm\current\` show as directories with year 1600 timestamps
2. **Wrong Node version** — Node 24.13.0+ has a regression; project requires exactly 24.1.0
3. **Node 20 won't work** — causes `ERR_UNKNOWN_FILE_EXTENSION` for `.mts` config files

**Diagnosis:**
```powershell
# Check nvm installation health
ls C:\Users\JacobMadsen\scoop\apps\nvm\current\
# If files show as directories or have 1600 dates, nvm is corrupted

# Check Node version
node -v  # Must be exactly 24.1.0
```

**Fix (corrupted scoop nvm):**
```powershell
# 1. Install fresh nvm-windows via winget (not scoop)
winget install CoreyButler.NVMforWindows --accept-package-agreements

# 2. Restart terminal (important!)

# 3. Install and use correct Node version
nvm install 24.1.0
nvm use 24.1.0

# 4. Verify
node -v  # Should show v24.1.0

# 5. Clean install
cd Cognito.Web.Client
Remove-Item -Recurse -Force node_modules
pnpm install
```

**If you accidentally downgraded to Node 20:**
You'll see `ERR_UNKNOWN_FILE_EXTENSION` for `.mts` files when running rspack. Fix by switching back to Node 24.1.0:
```powershell
nvm use 24.1.0
```

**Optional cleanup (after fix works):**
```powershell
# Remove corrupted scoop nvm
scoop uninstall nvm

# Remove Windows Defender exclusions if you added them during troubleshooting
Remove-MpPreference -ExclusionPath "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client\node_modules"
Remove-MpPreference -ExclusionPath "C:\Users\JacobMadsen\AppData\Local\pnpm"
```

### Step 3: Nuclear Option

Re-run setup with recreate flag:
```powershell
# Elevated PowerShell
.\process\setup-sites.ps1 -recreate
```

## Quick Diagnostics

```powershell
# Cert expiry
cmd.exe /c "certutil -store Root > C:\temp\certs.txt"
# Then search for cognito.dev

# SSL bindings
netsh http show sslcert

# Hosts
Select-String -Path "C:\windows\system32\drivers\etc\hosts" -Pattern "cognito"

# Connectivity
Test-NetConnection -ComputerName local.cognito.dev -Port 443
```

#### NuGet Global Cache Empty / MSB3030 "Could not copy file"

**Symptom:** Hundreds of MSB3030 errors like `Could not copy the file "C:\Users\...\.nuget\packages\<pkg>\...\<name>.dll" because it was not found`. Also CS0246 errors for basic types (`HashSet<>`, `List<>`). The `dotnet restore` claims success but packages aren't in the global cache.

**Root Cause:** After the SDK-style migration, the NuGet global packages cache (`~\.nuget\packages\`) can be empty while the old solution-level `packages/` folder still has 500+ packages. SDK-style projects ONLY use the global cache — `dotnet restore` can "succeed" (resolving the dependency graph) without actually downloading missing packages.

**Diagnosis:**
```powershell
# Check how many packages are in the global cache (should be 300+)
(Get-ChildItem "$env:USERPROFILE\.nuget\packages\" -Directory).Count

# If only a handful, the cache needs to be repopulated
```

**Fix (must be done in order — VS must be CLOSED first):**
```powershell
# 1. Close Visual Studio

# 2. Shut down MSBuild server nodes (they lock FodyCommon.dll)
& 'C:\Program Files\dotnet\dotnet.exe' build-server shutdown

# 3. Delete project.nuget.cache files to force all projects to re-evaluate
Get-ChildItem 'C:\Users\JacobMadsen\source\repos\Cognito Forms' -Recurse -Filter 'project.nuget.cache' | Remove-Item -Force

# 4. Restore WITHOUT --force (--force is destructive — it deletes existing packages before re-extracting)
dotnet restore "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.sln"

# 5. Build WITHOUT restore (dotnet build's implicit restore re-locks Fody before completing)
dotnet build "C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.sln" --no-restore -verbosity:minimal

# 6. Reopen Visual Studio — packages are already in cache, VS restore will just validate
```

**Key gotchas:**
- **NEVER use `dotnet restore --force`** when Fody might be locked — `--force` deletes existing packages before re-extracting, and if it fails midway (Fody lock), the deleted packages are gone
- Instead of `--force`, delete `project.nuget.cache` files — this forces NuGet to re-evaluate all projects without destructively wiping the package cache
- `dotnet build` with implicit restore will fail on Fody — always separate restore from build
- `dotnet build-server shutdown` must be run via PowerShell (`& 'C:\Program Files\dotnet\dotnet.exe' build-server shutdown`) to avoid hook interception
- VS must be closed during restore — VS's MSBuild processes lock Fody, and if VS auto-restores with force mode, it can wipe the cache

## Important Notes

- **`dotnet build`** works with SDK-style projects; use `.\process\build-solution.ps1` or Visual Studio as alternatives
- Most scripts auto-elevate when needed
- After cert changes, restart Chrome completely
- IIS changes may need `iisreset`

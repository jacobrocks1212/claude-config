---
name: local-ui-tests
description: Run Cognito Forms Selenium UI tests locally against a worktree IIS site on a Docker Selenium grid — full setup, run loop, and the environment gotchas that block a fresh machine.
argument-hint: [test-name-filter]
---

# Local UI Tests (Selenium, worktree, Docker grid)

Run the `Cognito.Forms.UnitTests` Selenium/browser tests **locally** — against a git-worktree IIS backend on a local Docker Selenium grid — so you can get real DOM/data truth and iterate without waiting on the ADO AutoTest pipeline (build definition 202).

The canonical tree (`C:\Users\JacobMadsen\source\repos\Cognito Forms`) owns `local.cognito.dev`. A **worktree** gets its own site (e.g. `c.cognito.dev`) via a one-time provisioning script so the two never collide. **Never point local test config at the canonical backend** — keep the worktree's process separate.

Everything the run needs (config repoints, host-resolver rules, the PFX copy) is **local-only churn**. None of it may be committed — revert it all before merge (see "Revert before merge").

---

## When to use

- You need to see *why* a UI test fails (browser console, live DOM), which the ADO pipeline and the harness's screenshot-only `catch` don't surface.
- You're classifying AutoTest failures as product-regression vs test-logic vs model-shape and need a local oracle.
- Prefer running the **real preexisting test** as the oracle; only hand-roll a diagnostic method when you specifically need to dump `driver.Manage().Logs.GetLog("browser")` / DOM on a load failure.

---

## Prerequisites (one-time per worktree)

1. **Docker Desktop + WSL2 running**, with the Selenium grid up (`selenium-hub` + `selenium-node`, chrome pinned to the app.config `version`, hub on `localhost:4444`). Confirm: `curl -s http://localhost:4444/status` → `"ready": true`.
2. **SSL wildcard cert** `*.cognito.dev` installed (LocalMachine\Root + \My). Provisioned by `process\create-local-cert.ps1` / `process\renew-local-cert.ps1`. This is the TLS cert, distinct from the encryption cert below.
3. **Worktree IIS DualSite provisioned** (ELEVATED, once — persists across reboot). Use the bundled `assets/setup-worktree-site.ps1`:
   ```powershell
   # from an ELEVATED PowerShell, in the worktree root
   .\_setup-worktree-site.ps1 -Name 'C' -SpaPort 7795
   ```
   Result: `https://c.cognito.dev` → this worktree's `Cognito.Services`. It rewrites the worktree `web.config`/`.env`/`.csproj` to the new domain+port — **local-only churn, do not commit**. You do **not** re-run this after a reboot; provisioning ≠ running state.

---

## Run procedure

### 1. Bring the stack up

- **Backend (IIS):** the app pool auto-starts on first request. **Cold start JIT-compiles for ~40–110 s** → first response is often a 302 after a long delay; warm requests are ~0.1–1 s. Be patient; do not mistake a slow cold start for a down site. Warm it: `curl -sk --max-time 180 https://c.cognito.dev/ -o /dev/null -w "%{http_code} %{time_total}s\n"`.
- **Dev servers (worktree ports):** SPA on **7795**, client/admin.js on **7797** (canonical uses 7775/7777 — do not reuse). Run `pnpm serve:spa` / the client serve script in the worktree. `serve` is not hook-blocked.
- **Grid:** confirm `"ready": true` (see gotchas for the session-leak fix).

### 2. Point the test host at the worktree site (local-only edits)

- `Cognito.Forms.UnitTests/app.config`:
  - `test:BaseUrl` = `https://c.cognito.dev/`, `test:ServicesBaseUrlHTTP` = `http://c.cognito.dev/`
  - `<driver name="grid" type="OpenQA.Selenium.Remote.RemoteWebDriver, WebDriver" remoteAddress="http://localhost:4444/wd/hub" browser="chrome" version="<pinned>" />`
- `Cognito.Forms.UnitTests/UI/UITest.cs` (Chrome options): add
  `--host-resolver-rules=MAP c.cognito.dev 192.168.65.254,MAP localhost:7795 192.168.65.254:7795,MAP localhost:7797 192.168.65.254:7797`
  (`192.168.65.254` = the Docker/WSL host gateway; lets the container's Chrome reach the host's IIS + dev servers). `--ignore-certificate-errors` should already be present.
- `Cognito.Forms.UnitTests/UI/UITest.cs` (RemoteWebDriver ctor): bump the per-command timeout to `TimeSpan.FromMinutes(3)` — the 60 s default is too short for a cold builder-page load (see gotchas).
- `Cognito.Services/web.config`: `clientScriptPath` must point at the **worktree** client port (`https://localhost:7797/dist`), not canonical `7777`.

### 3. Build, then run a real test

Build first (tests run `--no-build`):
```
/msbuild -Project "Cognito.Forms.UnitTests/Cognito.Forms.UnitTests.csproj"
```
Then run. `/mstest -TestDll "Cognito.Forms.UnitTests"` works now (the false-stale bug is fixed). The bundled runner `assets/run-ui-test.ps1` is an equivalent alternative — it runs `dotnet test --no-build` inside the PowerShell exec (so `dotnet` isn't Bash-hook-blocked) and writes to `%TEMP%\ui-test-run.txt`:
```
powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue.ps1" \
  -Op mstest -Exec "<skill-dir>/assets/run-ui-test.ps1" -Method "<TestNameOrFilter>"
```
Output is UTF-16 — decode with `iconv -f UTF-16LE -t UTF-8 "$TEMP/ui-test-run.txt"` before grepping for `Passed`/`Failed`/`Error Message`/`Stack Trace`. **Judge pass/fail from that log tail ("Passed"/"Failed"/"Test Run Failed"), never the queue exit code or the results json — both are unreliable for `Cognito.Forms.UnitTests`.**

### 4. One test at a time

The grid runs **`maxSessions=1`**. Run a single test (or a small serial filter) per invocation; a parallel/leaked session blocks the next run.

---

## Gotchas (each of these blocked a fresh worktree; all are local-only)

| Symptom | Cause | Fix |
|---|---|---|
| Every entries test 500s; `entity-meta/initialize`/`entries-page/model` return 500 `No encryption certificate found … thumbprint …` | `CertUtil.GetCertificate` needs the encryption cert. Its file fallback loads **`Cognito-Staging.pfx`** (thumbprint `7AADDD…`, pwd `vc3123!!`) by walking up from the IIS app `BaseDirectory`. The build copies it to the **test** bins + worktree root, **not** to `Cognito.Services\bin\`. | Copy `Cognito-Staging.pfx` into `Cognito.Services\` **and** `Cognito.Services\bin\`. (This recycles the app pool → expect one cold start.) |
| `The test files directory '…\TestFiles' doesn't exist` from `establishsession` | The worktree's `Cognito.Forms.UnitTests\TestFiles` lacks the `Everyone` ACE the canonical tree inherits, so the app-pool identity can't read the seed store. | `icacls "…\Cognito.Forms.UnitTests\TestFiles" /grant "*S-1-1-0:(OI)(CI)(M)" /T /C /Q` (non-elevated as owner). |
| Grid stuck `"ready": false`; `DELETE /session/<id>` says "Unable to find session" | A test died before quitting its driver and leaked its only session (`maxSessions=1`). | `docker restart selenium-node`, then poll `/status` until `"ready": true` (~15 s). |
| `HTTP 000` / long hangs right after any `web.config`/`bin\` change | Editing `web.config` or writing into `bin\` forces an app-pool recycle → cold-start JIT. | Warm with a patient request (`--max-time 180`); the first hit returns 302 in ~40–110 s, then it's fast. |
| `#progress` / entries grid `NoSuchElementException` even though auth works | Usually a downstream symptom of the backend 500s above (page never renders), **not** a selector bug. Fix the 500 first, then re-read the failure. | — |
| `<encryptingCertThumbprint>` looks empty but differs between trees | Canonical = clean U+200E; a mojibaked worktree copy = `â€Ž` (double-UTF-8). **Red herring** — `CertUtil.ThumbprintCleanser` strips all non-ASCII to empty, so the PFX fallback is what matters. | Ignore, or set it to match canonical. Not the cause of the 500. |
| Cold builder-page `GoToUrl` fails `WebDriverException: HTTP request … /url timed out after 60 seconds` at `UITest.Execute` | `RemoteWebDriver`'s default per-command timeout is **60 s**; a cold `…/new` builder route (SPA+client chunk compile + model build on first hit in a fresh browser) exceeds it — not a selector/logic bug. | Bump the ctor: `new RemoteWebDriver(uri, caps, TimeSpan.FromMinutes(3))` in `UITest.cs`. Warming the page first helps, but the SPA route recompiles per fresh session. |
| Every endpoint (incl. `svc/feature-flags`) returns a Configuration Error YSOD — "Could not load … 'GemBox.Document, Version=…' … manifest does not match" — surfacing as `IsFeatureEnabled` → `Assert.Fail("Failed to parse feature flags…")` | A merge bumped the `GemBox.Document` `PackageReference`, but `--no-restore`/incremental builds never recopied the new DLL into `Cognito.Services\bin\`, so the bin DLL's **manifest** version ≠ what the compiled `Cognito.*.dll` expects. (FileVersion ≠ AssemblyVersion — check the manifest via `[Reflection.AssemblyName]::GetAssemblyName(dll).Version`.) | Fastest unblock: copy the version the loader error says it "wants" into `Cognito.Services\bin\` from `~/.nuget/packages/gembox.document/<ver>/lib/net462/`, then warm (recycles the pool). Proper fix = clean rebuild + `-Restore` (incremental resists it). |
| `POST …/makePayment` 500s locally even for manual "Mark as Paid"; payment tests fail only locally | Env limit, **not** the flag — local order data differs from CI (`ProcessorName: null` → manual path) and the server exception only lands in App Insights. Flag-OFF CI hits the same endpoint and is green. | Classify payment-cluster failures from CI / the feature team, not locally. |
| A `[FeatureFlag(…, false)]` test still sees the flag ON; can't reproduce a flag-OFF baseline locally | `UI.IsFeatureEnabled` reads `svc/feature-flags`, which reflects the **global** `Web.config` force-on → reports `True` regardless of the per-test attribute. | A true flag-OFF baseline needs reverting the force-on + an app recycle. Use the last flag-OFF CI build as the flag-OFF baseline instead. |
| A test passes alone but fails in a multi-test batch (`Sequence contains no matching element`); or state carries between local runs (an entry stuck Refunded) | The live IIS server never runs MSTest `[ClassCleanup]`, so local runs **accumulate store mutations** CI's fresh per-test seed never has. Some once-per-form UI (e.g. a security-choice dialog) is consumed by the first test in a batch. | Re-run a suspect straggler **in isolation** before blaming the fix. `<disableTestStoreAutoSave>true</disableTestStoreAutoSave>` in `Web.Local.config` (untracked) protects the pristine seed; clearing mutations needs a **w3wp recycle**, which requires **elevation** — ask Jacob for an elevated `iisreset`/apppool recycle (non-elevated `Stop-Process w3wp` = Access denied). |

### Build & recompile gotchas

- **The `--no-restore` recompile trap.** `build-filtered.ps1` passes `--no-restore`. If a `.cs` edit won't take and you `rm -rf …/obj`, the next `/msbuild -Project` **silently no-ops** (exit 0, empty log, DLL stays yesterday-dated) — the obj wipe removed `project.assets.json`, making it *worse*. Correct recovery: `rm -rf Cognito.Forms.UnitTests/obj` **and** `rm -f bin/Cognito.Forms.UnitTests.{dll,pdb}` (deleting the output DLL also defeats the incremental up-to-date check), then `/msbuild -Project "…" -Restore`. Verify a literal actually landed with a **UTF-16** grep (`grep -aP "f\x00i\x00n\x00d…"`) — C# string literals are UTF-16 in the PE, so ASCII grep always misses. Output path is flat `bin/` (not `bin/Debug/` — `AppendTargetFrameworkToOutputPath=false`).
- **Build-script path is repo-local, not `$HOME`.** The build `-Exec` target is `$REPO_ROOT/.claude/scripts/build-filtered.ps1` — there is **no** `~/.claude/scripts/build-filtered.ps1`. Pointing `-Exec` at `$HOME/…` no-ops (exit 0, empty log, nothing built), indistinguishable from an incremental skip. Use `REPO_ROOT=$(git rev-parse --show-toplevel)`. (The queue *runner* `build-queue.ps1` genuinely lives at `$HOME/.claude/scripts/` — only the `-Exec` script is repo-local.) The Bash PreToolUse hook also blocks any command string containing `*-filtered.ps1` (even `grep`/`cat`/`readlink`) — read those scripts with the Read tool via their `claude-config` path.

**How AutoTest CI differs:** `Web.AutoTestDynamic.config` sets `environment="Testing"`, the real thumbprint `7AADDD…`, and `encryptingCertLocation=#{CERT_LOCATION}#`; the pipeline installs the cert. Locally you rely on the `Cognito-Staging.pfx` file fallback instead.

---

## Revert before merge

The local run mutates files that must **not** land in the PR. Before finalizing, confirm `git diff main` shows **only** intended flag-aware test changes + product fixes:

- `Cognito.Services/web.config` — `clientScriptPath` port, `<domain>`, `spaAssetsUrl`, any thumbprint edit, and any feature-flag flip.
- `Cognito.Forms.UnitTests/app.config` — `test:BaseUrl`, `test:ServicesBaseUrlHTTP`, `<driver>` grid entry.
- `Cognito.Forms.UnitTests/UI/UITest.cs` — `--host-resolver-rules`, the `TimeSpan.FromMinutes(3)` RemoteWebDriver command-timeout arg, and any Chrome-option churn.
- Delete any throwaway `_Diag*.cs` diagnostic methods.
- The `Cognito-Staging.pfx` copies in `Cognito.Services\`/`bin\`, any manual `Cognito.Services\bin\GemBox.Document.dll` version swap, `_setup-worktree-site.ps1`, `.env` churn, and `sh.exe.stackdump` files are untracked local artifacts — leave them out of the commit. Before final flag-OFF/flag-ON validation, do a clean rebuild (`-Restore`) so the bin matches `main`.
- `Web.Local.config` `<disableTestStoreAutoSave>` — untracked; leave it out of the commit.

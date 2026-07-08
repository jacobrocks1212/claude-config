---
name: production-build
description: Build the AlgoBooth production app on this test machine and hand off the installer for manual smoke-testing. Runs test-production.ps1 (pull → conditional deps → tauri build → open installer).
argument-hint: "[--install] [--clean] [--skip-pull] [--no-install-deps]"
---

# Production Build (AlgoBooth test machine)

This machine is a **test box, not a dev box**. Use this skill to produce the real
production bundle — the exact installer users get — and hand it off for a manual
smoke test (including real-device audio). It wraps the repo-root script
`test-production.ps1`, which does pull → conditional dep installs → `tauri build` →
open the installer.

**When to use:** Jacob wants to test the current production app on this machine —
"build the production app", "give me something to test", "/production-build".

## Steps

1. **Map flags to script switches.** Translate any arguments into the PowerShell
   switches the script accepts (see table). No args → a plain pull + build + open
   the installer folder.

   | Argument | Script switch | Effect |
   |----------|---------------|--------|
   | `--install` | `-Install` | Auto-launch the installer after a successful build |
   | `--clean` | `-Clean` | Wipe `dist/` + `cargo clean` first (fresh build) |
   | `--skip-pull` | `-SkipPull` | Build the current checkout without pulling |
   | `--no-install-deps` | `-NoInstallDeps` | Never run `npm install`, even if a lockfile changed |

2. **Run the script** from the repo root, mapping each requested flag:

   ```
   powershell.exe -ExecutionPolicy Bypass -File "C:\Users\JacobMadsen\source\repos\algobooth\test-production.ps1" [switches]
   ```

   This is a long-running build (Rust release + Vite + sidecar). Let it finish —
   do not interrupt or assume failure on slowness.

3. **Surface the outcome.** Report concisely:
   - Whether the source updated (commit short-SHAs) and whether deps were reinstalled.
   - Build success/failure.
   - The installer path the script reported (under `target\release\bundle\` at the
     workspace root — this is a Cargo workspace, so the target dir is NOT under `src-tauri\`).
   - The reminder that it's an **unsigned** build (SmartScreen warns — "More info" →
     "Run anyway").

4. **On build failure (HARD REQUIREMENT — Preexisting Issue Resolution):** Claude is
   the sole engineer for this repo. Do not just hand the error back. Diagnose with
   `systematic-debugging` and resolve per the repo's issue-size policy in
   `CLAUDE.md` (small → fix inline; medium → Sonnet subagent; large/unclear →
   `docs/bugs/`). A red build is a bug to fix, not a status to report.

## Notes

- The script enforces a **clean working tree** before pulling (a test box must not
  carry local edits) and warns if not on `main`. `--skip-pull` bypasses the pull.
- `tauri build` is self-sufficient: its `beforeBuildCommand` (`npm run build:all`)
  type-checks + builds the frontend and the sidecar, and the sidecar is bundled via
  `tauri.conf.json` `resources`. Do not separately run `sidecar:build`.
- Build the **plain release** (no `capture`/MCP feature) — manual testing should
  exercise exactly what ships.
- The script (`test-production.ps1`) is tracked by the **algobooth** repo. This skill
  lives in `claude-config` and is not tracked by algobooth's git.

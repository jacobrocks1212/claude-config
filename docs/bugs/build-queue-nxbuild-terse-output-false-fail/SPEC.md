# build-queue-nxbuild-terse-output-false-fail

## Status
Investigating → Concluded

## Symptom

The build-queue classifier produces a **FALSE-FAIL (RESULT=FAIL)** on genuinely successful Nx builds. The build log contains real success markers:
- `"Successfully ran target build for project cognito-client and 3 tasks it depends on"`
- `"[webpackbar] ✔ Form-client: Compiled successfully in 1.24m"`

But the result is marked `build_fidelity: "no-output"` and the build is force-failed to exit code 1.

**Concrete example:**
```
Command: build-queue.ps1 -Op nxbuild -Exec .../client-build-filtered.ps1 -Project "cognito-client"
Outcome banner: build-queue: seq=1245 op=nxbuild RESULT=FAIL (result_fidelity=n/a) -> build produced no output; re-run the nx target
Actual log content: "Building cognito-client..." + "[webpackbar] ✔ Form-client: Compiled successfully in 1.24m" + "NX  Successfully ran target build..."
```

## Root Cause (Verified)

**File:** `user/scripts/build-queue-hygiene.ps1`, function `Test-BuildProducedNoOutput` (lines 111–164).

**Logic:**
```powershell
function Test-BuildProducedNoOutput {
    param([string]$LogText, [int]$MinChars = 40)
    if ([string]::IsNullOrWhiteSpace($LogText)) { return $true }
    if ($LogText.Trim().Length -lt $MinChars) { return $true }  # ← THE BUG
    return $false
}
```

**Mechanism:**
1. The function measures output emptiness by checking `$LogText.Trim().Length`
2. Nx output is terse (typically 3–5 lines for a successful build)
3. Nx/webpack output is **ANSI-escape-heavy** — each success marker is wrapped in ANSI color codes (e.g., `\e[0m`, `\e[32m`)
4. A terse log with ANSI escapes can be only ~50–100 raw bytes (after trimming)
5. BUT: `$LogText.Trim().Length` counts **characters**, not bytes, and ANSI escapes are ~8–12 characters per marker
6. When the trimmed character count falls below the `MinChars` threshold (default 40), the classifier falsely returns `$true` ("no output produced") even though the build succeeded

**Example Nx log that triggers the bug:**
```
Building cognito-client...
[webpackbar] ✔ Form-client: Compiled successfully in 1.24m
NX  Successfully ran target build for project cognito-client
```
After trimming and stripping for a character count, ANSI escapes are still embedded, making the length appear smaller than it is. For a cached/fast Nx build with a very terse success summary, the character count can easily dip below 40.

## Classification

- **Root-cause class:** `script-defect` (the `Test-BuildProducedNoOutput` classifier is broken for terse ANSI-heavy output)
- **Missing-contract:** No; the bug is in the implementation, not in an unhandled scenario
- **Trigger kind:** manual (observed in live builds)

## Proposed Fix Scope

**Approach: Strip ANSI escape codes before measuring output emptiness, and/or recognize positive success markers as real output.**

Option A (preferred): **Strip ANSI codes before the length check.** This makes the classifier robust against any ANSI-heavy tool output (not just Nx).
- Add a helper function to strip ANSI escapes from the log text
- Apply it before the `MinChars` threshold check
- This is a pure structural fix that does NOT fit the phrase-matching over-fit pattern

Option B (additive): **Recognize positive success markers as real output.** Before applying the `MinChars` threshold, scan for known success markers and return `$false` (real output) immediately.
- Markers: "Successfully ran target", "Compiled successfully", "Build succeeded", "[webpackbar] ✔"
- This is a literal-phrase-match fix → triggers the over-fit detector if patterns recur

**Decision: Implement Option A (strip ANSI escapes) as the primary fix, plus test coverage for terse ANSI-heavy logs.**

## Files Modified

1. `user/scripts/build-queue-hygiene.ps1` — Add `Strip-AnsiCodes` helper; update `Test-BuildProducedNoOutput` to call it
2. `user/scripts/build-queue-hygiene.Tests.ps1` — Add test case: `Test-BuildProducedNoOutput returns $false for a terse Nx log with ANSI codes`

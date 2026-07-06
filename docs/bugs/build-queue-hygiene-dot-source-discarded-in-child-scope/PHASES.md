# Implementation Phases — Build-queue hygiene dot-source scope fix

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config Windows PowerShell build-queue tooling; no Tauri/MCP app surface. Verified via Pester (`build-queue-hygiene.Tests.ps1`) + the SPEC's isolated PowerShell repro.

## Cross-feature Integration Notes

(Omit this section — there are no hard deps on Complete upstreams. The SPEC has no `**Depends on:**` block.)

### Phase 1: Move hygiene dot-source out of the `Get-SafeValue` child scope in all three callers

**Scope:** Fix the single root cause — `Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }` invokes its scriptblock via `& $Block` (child scope), so every hygiene function defined by the dot-source is discarded on return and is undefined in the caller's real script scope. Replace each of the three occurrences with a top-level `try { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') } catch { }` (script-scope preserving, still fail-open on a missing/broken hygiene file). Also correct the stale `build-queue-status.ps1:26-30` comment, which claims the highlight degrades "only on a load error" — in reality the child-scope discard makes the degrade the PERMANENT state today. Add a regression guard (written FIRST, RED) that structurally asserts the dot-source is a top-level statement in each caller, without executing the callers.

**Deliverables:**
- [x] `user/scripts/build-queue-hygiene.Tests.ps1`: add the RED regression guard (new `Describe` block) asserting, for each of `build-queue.ps1`, `build-queue-runner.ps1`, `build-queue-status.ps1`, that the statement dot-sourcing `build-queue-hygiene.ps1` is a **top-level statement** — NOT nested inside a `Get-SafeValue { … }` / `& { … }` scriptblock. Confirm this test is RED against the current tree before touching the three caller scripts (it must fail because the dot-source is currently wrapped in `Get-SafeValue` in all three).
- [x] `user/scripts/build-queue.ps1:47-49`: replace `Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }` with a top-level `try { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') } catch { }`.
- [x] `user/scripts/build-queue-runner.ps1:66-68`: same fix, same replacement text.
- [x] `user/scripts/build-queue-status.ps1:31`: same fix, same replacement text.
- [x] `user/scripts/build-queue-status.ps1:26-30`: rewrite the stale comment — remove the "only on a load error" framing; state plainly that the previous `Get-SafeValue`-wrapped dot-source discarded hygiene functions into a child scope on every run (permanent degrade, not an error-path edge case), and that the fix restores them to script scope while keeping the `try/catch` fail-open for a genuinely missing/broken hygiene file.
- [x] Tests: the new regression guard in `build-queue-hygiene.Tests.ps1` (RED before the three edits, GREEN after).

**Minimum Verifiable Behavior:** `Invoke-Pester -Path user/scripts/build-queue-hygiene.Tests.ps1` passes in full, including the new scope-in-caller regression guard, after the three edits (and fails on the guard alone, before the edits, proving RED→GREEN). AND the SPEC's minimal isolation repro confirms the mechanism directly:
```powershell
function Get-SafeValue { param($b) try { & $b } catch {} }
Get-SafeValue { . .\build-queue-hygiene.ps1 }; (Get-Command New-BuildJobObject -EA SilentlyContinue) -ne $null   # -> False (before fix / unpatched pattern)
try { . .\build-queue-hygiene.ps1 } catch { }; (Get-Command New-BuildJobObject -EA SilentlyContinue) -ne $null   # -> True (after fix / top-level pattern)
```

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] <!-- verification-only --> `Invoke-Pester -Path user/scripts/build-queue-hygiene.Tests.ps1` passes in full, including the new scope-in-caller guard, on the patched tree.
- [x] <!-- verification-only --> The SPEC's minimal isolation repro (top-level `try { . hygiene.ps1 } catch {}` vs. the old `Get-SafeValue { . hygiene.ps1 }`) confirms hygiene functions resolve at script scope after the fix. OPTIONAL heavier manual check (operator, on a real Cognito worktree): a real queued build (e.g. `/nxbuild`) waits for the real build to finish, prints the authoritative `RESULT` banner as the wrapper's last stdout line, and `results/<seq>.json` contains the rich verdict-bearing shape (`counts`/`hygiene`) instead of the bare 3-field fallback.

**MCP Integration Test Assertions:**
N/A — no MCP-runtime-observable behavior (PowerShell tooling; verified via Pester + isolated PS repro).

**Prerequisites:** None

**Files likely modified:**
- `user/scripts/build-queue.ps1` — move the hygiene dot-source (`:47-49`) out of `Get-SafeValue` into top-level `try { . … } catch {}`
- `user/scripts/build-queue-runner.ps1` — same fix at `:66-68`
- `user/scripts/build-queue-status.ps1` — same fix at `:31` + rewrite the stale `:26-30` comment
- `user/scripts/build-queue-hygiene.Tests.ps1` — add the scope-in-caller regression guard (structural, does NOT execute the caller scripts)

**Testing Strategy:**
TDD, RED before GREEN. The existing `build-queue-hygiene.Tests.ps1` dot-sources `build-queue-hygiene.ps1` directly at top level in its `BeforeAll` block, so it has always passed despite the production bug — it proves hygiene.ps1's own functions are correct in isolation but says nothing about how the three CALLER scripts import them. The new guard closes that gap.

Do NOT naively dot-source `build-queue.ps1` / `build-queue-runner.ps1` / `build-queue-status.ps1` to check `Get-Command` on the resulting scope — those are top-level scripts with `param()` blocks that EXECUTE the queue wrapper/runner/status logic on load (they would try to run the real build-queue machinery as a side effect of being sourced by a test). The guard must assert the SCOPE of the dot-source statement in each caller's *source text* without executing the caller. Two viable mechanisms (leave the exact choice to the implementer):
1. **AST-based (preferred for robustness):** `[System.Management.Automation.Language.Parser]::ParseFile($callerPath, [ref]$null, [ref]$null)` to get the script's `Ast`, then use `FindAll(...)` to locate the `DotSourceOperator` (or the command-invocation node whose `InvocationOperator` is `.`) that targets `build-queue-hygiene.ps1`, and walk its `Parent` chain to assert it is NOT inside a `ScriptBlockExpressionAst` that is itself the sole/last statement passed to a function named `Get-SafeValue` (or any `& { ... }` invoke-block) — i.e. the dot-source's nearest enclosing statement list must be the file's top-level `Ast.EndBlock`/`Ast.BeginBlock` statements, not a nested `ScriptBlockAst`.
2. **Text-based (simpler, acceptable if carefully scoped):** read each caller's raw text, locate the line(s) matching the dot-source pattern (`\.\s*\(Join-Path \$PSScriptRoot 'build-queue-hygiene\.ps1'\)`), and assert that line is NOT preceded (within the immediately enclosing brace block) by an unclosed `Get-SafeValue {` or bare `& {` opener — e.g. by checking the line sits at column 0 (or the script's baseline top-level indent) and is not the sole statement of a `{ ... }` block passed as an argument. This is more fragile to reformatting than the AST approach but is a legitimate fallback if AST parsing proves awkward in the test harness.

Either approach directly guards the SPEC's stated recurrence risk: "if someone re-wraps the dot-source" back into a `Get-SafeValue`/`& { }` scriptblock, the guard goes RED again.

**Integration Notes for Next Phase:**
- The regression guard must assert the dot-source's SCOPE structurally (AST or a carefully-scoped text check), never by executing `build-queue.ps1` / `build-queue-runner.ps1` / `build-queue-status.ps1` directly — those scripts run real queue/build/status logic on load. See Testing Strategy above for both viable mechanisms.
- Fail-open is retained by design (SPEC Open Question 1 recommendation): a missing/broken hygiene file still degrades to the `Get-Command`-guarded fallback branches in each caller — only the *scope* mistake is fixed, and the new regression guard makes a re-regression of that specific mistake non-silent.
- OPTIONAL out-of-scope follow-up (former Theory 2, explicitly NOT planned here): persisting the composed verdict into `results/<seq>.json` for the genuine background-poll path (`nxbuild/SKILL.md:38`). Decide separately, or fold into `docs/bugs/build-queue-orphaned-result-on-wrapper-kill`.

## Implementation Notes

#### Batch 1 (WU-1 — RED regression guard) — 2026-07-06
- **Work completed:** Appended one new `Describe` block (`scope-in-caller guard …`) at the end of `user/scripts/build-queue-hygiene.Tests.ps1` (lines 940-991, +53 lines). It AST-parses each of the three callers via `[System.Management.Automation.Language.Parser]::ParseFile`, filters `CommandAst` dot-source nodes (`InvocationOperator == Dot`) to those referencing `build-queue-hygiene.ps1`, asserts exactly one per file, and walks the node's `.Parent` chain asserting NO `ScriptBlockExpressionAst` ancestor (the `Get-SafeValue { … }`/`& { … }` signature). Never dot-sources/invokes the callers.
- **Proof-of-RED (independently re-run by the orchestrator):** `Invoke-Pester` → 97 passed / 6 failed. The 3 NEW guard `It`s (one per caller) all fail with `Expected $false … but got $true` — the dot-source's ancestor chain DOES contain a `ScriptBlockExpressionAst` today. RED for the right reason (not a setup/compile error).
- **Pre-existing baseline noise (NOT in scope, left untouched):** 3 unrelated failures pre-date this work — `Add-ProcessToBuildJob`/`Stop-BuildJobTree` zero-handle (`got $null`) and `Reset-CompilerServer` `[bool]` read (`got $false`). These are the documented Pester child-scope-`$result` quirk failures; baseline was 97/3 before the guard, 97/6 after (the +3 are the guard's RED).
- **Pitfall handled by the test-agent:** Pester v5 splits Discovery from Run — a bare `foreach`/`function` in the `Describe` body only exists at Discovery time. Fixed by moving the helper into `BeforeAll` and using `It -ForEach @(…)` with `<_>` templating (correct v5 per-item naming idiom).
- **Review verdict:** PASS — ground-truth verified (wc -l 991, grep line 940, status all matched); assertion-vs-intent clean (`It` name matches the `Should -Be $false` assertion; not tautological — passes iff the dot-source is genuinely top-level).
- **Files modified:** `user/scripts/build-queue-hygiene.Tests.ps1`.

#### Batch 2 (WU-2 — three scope fixes + status comment rewrite) — 2026-07-06
- **Work completed (Sonnet impl-agent):** Moved each of the three `Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }` dot-sources to a top-level `try { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') } catch { }` — `build-queue.ps1:47-49`, `build-queue-runner.ps1:66-68`, `build-queue-status.ps1` (was line 31, now line 35 after the comment grew). Rewrote the stale `build-queue-status.ps1:26-30` comment to state the child-scope discard was a PERMANENT every-run degrade (not a load-error edge case) and that the top-level `try/catch` retains fail-open for a genuinely missing/broken hygiene file. `Get-SafeValue` function definitions and all its other legitimate value-guard uses left untouched.
- **Ground-truth verified (orchestrator re-ran):** exactly ONE hygiene dot-source per file, all top-level; the remaining `Get-SafeValue {` matches are the function defs + genuine value-guards (none the hygiene import); diffstat +14/−10 across the 3 files.
- **Proof-of-GREEN (orchestrator re-ran):** `Invoke-Pester` → 100 passed / 3 failed. The 3 scope-in-caller guard `It`s (one per caller) all PASS now (`… at script scope, not inside Get-SafeValue`). The 3 remaining failures are the SAME documented pre-existing baseline noise (Add-ProcessToBuildJob/Stop-BuildJobTree zero-handle, Reset-CompilerServer `[bool]` read) — unchanged by this work. Clean RED→GREEN (Batch 1 97/6 → Batch 2 100/3).
- **Mechanism confirmed (SPEC isolation repro):** old `Get-SafeValue { . hygiene.ps1 }` → `New-BuildJobObject` defined=**False** (child-scope discard); fixed `try { . hygiene.ps1 } catch {}` → defined=**True** (resolves at script scope). Both Runtime Verification rows satisfied by the same run (MCP runtime: not-required).
- **Files modified:** `user/scripts/build-queue.ps1`, `user/scripts/build-queue-runner.ps1`, `user/scripts/build-queue-status.ps1`.

## Review Notes

**Review verdict:** PASS (2026-07-06) — decomposition matches the Concluded SPEC and the verified touchpoint audit. Single fix phase; file:line targets confirmed against the real tree; verification distributed within the phase (Pester scope-in-caller guard + isolated PS repro); no gate-owned rows; verdict-persistence explicitly out of scope per operator decision.

**Batch 1 review verdict:** PASS (2026-07-06) — RED regression guard authored and independently confirmed RED for the right reason (3 new guard Its fail on the `ScriptBlockExpressionAst`-on-ancestor-chain assertion). See Implementation Notes Batch 1.

**Batch 2 review verdict:** PASS (2026-07-06) — three scope fixes + comment rewrite applied exactly as planned; ground-truth verified (one top-level hygiene dot-source per file; `Get-SafeValue` defs/uses intact); QG GREEN (100/3, the 3 guard Its flipped RED→GREEN, baseline noise unchanged); SPEC isolation repro confirms the mechanism (child-scope False → script-scope True). See Implementation Notes Batch 2.

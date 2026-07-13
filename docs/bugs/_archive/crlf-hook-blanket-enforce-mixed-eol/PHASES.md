# Implementation Phases — CRLF Hook Blanket-Enforces EOL Against a Mixed-EOL Repo

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a claude-config harness defect (a PowerShell hook fired
by the Cognito Forms repo's `.claude/settings.json`), verified via a self-contained Pester
suite (`normalize-crlf.Tests.ps1`, temp `git init`/`git worktree add` fixtures + real stdin-JSON
+ byte assertions) — the repo's established hook-verification harness for this class of defect,
same shape as `user/scripts/test_hooks.py` for bash hooks. There is no `mcp-tool-catalog.md` in
this repo, so the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The SPEC's own `## Resolution (implemented)` section states the fix was already landed
  directly** ("Fixed directly (hook-side only, per the decided direction) rather than routed
  through `/plan-bug`"), bypassing the normal `/plan-bug` → PHASES.md → `/execute-plan` route.
  This bug dir had `SPEC.md` only (no `PHASES.md`, no `FIXED.md`) at the start of this pass —
  the code fix and the pipeline bookkeeping had diverged: the former was done, the latter never
  ran. Per the operator protocol ("the fix may have pre-landed"), this phase is
  **verification-only**: confirm the landed fix on disk, re-run its test suite fresh, and close
  the pipeline bookkeeping gap.
- **`user/scripts/fix-line-endings.ps1` (this subagent's owned file) is explicitly OUT of this
  bug's decided fix scope.** The SPEC's `## Decided Fix Direction` section scopes the fix
  "hook-side only (claude-config)" to `Cognito Forms/.claude/hooks/normalize-crlf.ps1` (a
  *different*, unrelated script despite the superficial name/behavior similarity — it lives in
  the Cognito Forms repo's `.claude/hooks/`, tracked at
  `repos/cognito-forms/.claude/hooks/normalize-crlf.ps1`, and fires on Cognito's own
  `PostToolUse Edit|Write` / `Bash` hooks). The SPEC's `## Affected Area` table lists
  `fix-line-endings.ps1` only as a **sibling** with the "same blanket-CRLF flaw" and says
  explicitly "deliberately unwired — do not wire"; the `## Open Questions` section notes
  factoring a shared helper to retire it as **"Out of decided scope; note only."** No `/plan-bug`
  ever committed to changing this file, so there is nothing for this phase to implement against
  it — verifying that it remains byte-identical (still unwired, still blanket-CRLF, exactly as
  root `CLAUDE.md`'s Hooks table documents and justifies) IS the correct disposition.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. `**Related:**` cites
`docs/bugs/windows-portability-in-probe-glue-and-field-validators/` (the prior EOL bug whose
Resolution first decided to leave `fix-line-endings.ps1` unwired) — that decision is reaffirmed,
not revisited, by this bug's own Decided Fix Direction. No coordination coupling with any other
in-flight work in this scope (bug dir + `fix-line-endings.ps1` only).

---

### Phase 1: Verify the pre-landed hook-side fix; confirm `fix-line-endings.ps1` is correctly out of scope

**Scope:** No code change to `user/scripts/fix-line-endings.ps1` (none was ever in decided
scope). Verify: (a) the Cognito `normalize-crlf.ps1` rewrite described in the SPEC's
`## Resolution (implemented)` is present on disk and tracked, (b) its test suite is genuinely
green on a fresh run (not just trusted from the SPEC's prose), (c) `fix-line-endings.ps1`
remains untouched/unwired as documented, and (d) close the pipeline-bookkeeping gap (this
PHASES.md + Status flip + `FIXED.md`) that the direct-fix bypass left open.

**TDD:** no new tests written — this is a verification pass over an EXISTING test suite
(`normalize-crlf.Tests.ps1`, 14 Pester cases) that was authored as part of the pre-landed fix.

**Status:** Complete

**Deliverables:**
- [x] Confirm `repos/cognito-forms/.claude/hooks/normalize-crlf.ps1` exists, is tracked (`git log`
  shows `5597395b fix(cognito-hooks): convention-aware cross-worktree CRLF normalizer`), and is
  wired into `repos/cognito-forms/.claude/settings.json`'s `PostToolUse Edit|Write` + `Bash`
  hooks by absolute path.
- [x] Confirm `manifest.psd1`'s `cognito-forms` entry lists `hooks\normalize-crlf.ps1` under
  `DotClaudeFiles` (tracked/reviewable/shared across worktrees, per the SPEC's Decided Fix
  Direction item 3).
- [x] Re-run `repos/cognito-forms/.claude/hooks/normalize-crlf.Tests.ps1` fresh (Pester 6.0.0) and
  confirm all 14 cases pass — not merely trusted from the SPEC's narrative.
- [x] Confirm `user/scripts/fix-line-endings.ps1` (this subagent's owned file) has NOT been
  modified since repo bootstrap (`git log` shows only the initial bootstrap commit touching it)
  and still contains the blanket force-CRLF behavior root `CLAUDE.md`'s Hooks/Scripts tables
  describe and justify leaving unwired. No edit made — none was in decided scope.
- [x] Flip `**Status:**` to `Fixed` in `SPEC.md` and this `PHASES.md`; write `FIXED.md`.

**Implementation Notes (2026-07-12):** The Cognito-side hook rewrite, its 14-case Pester suite,
and the `manifest.psd1` tracking entry were all already present on disk (commit `5597395b`,
2026-06-25) — this bug's actual root-cause fix had landed nine sessions before this bug dir was
picked up for pipeline close-out; only `SPEC.md` existed in the dir (no `PHASES.md`/`FIXED.md`).
Re-running the suite fresh confirmed **14/14 green** (no drift since landing). `git status`
confirms `fix-line-endings.ps1` carries zero uncommitted changes and `git log -- <path>` shows
no commit since bootstrap — consistent with "out of decided scope; do not wire." Files touched
this phase: `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/PHASES.md` (new),
`docs/bugs/crlf-hook-blanket-enforce-mixed-eol/SPEC.md` (Status flip),
`docs/bugs/crlf-hook-blanket-enforce-mixed-eol/FIXED.md` (new). No hook script, settings.json,
or `fix-line-endings.ps1` edit was needed or made.

**Minimum Verifiable Behavior:** `powershell.exe -Command "Import-Module Pester -RequiredVersion
6.0.0 -Force; Invoke-Pester -Path 'repos/cognito-forms/.claude/hooks/normalize-crlf.Tests.ps1'
-Output Detailed"` reports `14 passed, 0 failed`.

**Runtime Verification** *(checked by the pre-existing Pester suite — this IS the hook's
runtime, driven via real stdin-JSON + real temp-git fixtures):*
- [x] <!-- verification-only --> An LF-committed template corrupted to CRLF is restored to LF by
  the deployed hook, and a CRLF-committed `.cs` corrupted to LF is restored to CRLF (the two
  original bidirectional symptoms). **Verified 2026-07-12 (re-run):** `Case1: tracked CRLF file
  restored to CRLF` and `Case2: tracked LF template restored to LF (regression fixed)` — both
  PASS.
- [x] <!-- verification-only --> The Bash branch normalizes each modified file to its OWN
  committed convention (not a blanket rewrite) — the Repro-B mechanism. **Verified 2026-07-12
  (re-run):** `Case7: Bash branch normalizes each modified file to its own committed EOL` — PASS.
- [x] <!-- verification-only --> Full suite, fresh run, 2026-07-12: `14 passed, 0 failed` (all
  cases: Case1, Case2, Case3, Case4a/b/c, Case5, Case6, Case7, Case8, Case9, Case10a/b/c).

**MCP Integration Test Assertions:** N/A — no app-runtime surface; the hook's runtime observable
is the subprocess pipe / file-byte outcome, asserted directly by the Pester suite above.

**Prerequisites:** None (single phase).

**Files likely modified:**
- `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/SPEC.md` — Status flip only (verified: currently
  `Concluded`, its own `## Resolution (implemented)` section already narrates the landed fix).
- `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/PHASES.md` — this file (new).
- `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/FIXED.md` — receipt (new).
- `user/scripts/fix-line-endings.ps1` — **verified, NOT modified** (out of decided scope).

**Testing Strategy:** Re-run the existing `normalize-crlf.Tests.ps1` Pester suite fresh (do not
trust the SPEC's narrated 14/14 as current-state proof) and cross-check `manifest.psd1` +
`settings.json` wiring on disk.

**Integration Notes for Next Phase:** None — final phase. This bug is being closed directly by
this subagent (interactive/operator-directed close-out, not the `__mark_fixed__` orchestrator
gate) per the assigned protocol — `FIXED.md` records `provenance: operator-directed-interactive`
accordingly, and no archive move is performed here (git state mutation is orchestrator-owned).

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

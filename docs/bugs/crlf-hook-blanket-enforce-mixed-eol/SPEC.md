# CRLF Hook Blanket-Enforces EOL Against a Mixed-EOL Repo — Investigation Spec

> `normalize-crlf.ps1` enforces a single blanket convention (CRLF on every non-`.sh` file) on the Cognito Forms repo, but the repo's *committed* EOL is mixed: `.cs` is CRLF, `NotificationTemplates/**/*.html` is LF. The hook therefore force-CRLFs LF-committed files (inflating their diffs), and its Bash branch silently reverts manual `perl -i`/`sed -i` LF normalization by re-CRLFing **every** git-modified file. `.gitattributes` (`* -crlf`) tells git to ignore EOL entirely, so nothing authoritative declares per-type EOL and every actor — the hook, agents, `.editorconfig` — guesses, and each guess breaks the other file type.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-25
**Placement:** docs/bugs/crlf-hook-blanket-enforce-mixed-eol
**Related:** `user/scripts/fix-line-endings.ps1`, `docs/bugs/windows-portability-in-probe-glue-and-field-validators/` (prior EOL bug; rationale for leaving `fix-line-endings.ps1` unwired), Cognito `Cognito Forms/.claude/hooks/normalize-crlf.ps1` (the defective hook), Cognito `Cognito Forms/.claude/settings.json` (wiring)

<!-- Status lifecycle: Investigating -> Concluded. Root cause proven below; fix direction decided with Jacob (per-type-mixed convention, hook-side-only). Ready for /plan-bug. -->

---

## Verified Symptoms

1. **[VERIFIED]** During a Jun 25 session, a blanket LF-normalization run flipped committed-**CRLF** `.cs` files (`AccountEmailDispatchRegistry.cs`, `CognitoPayAccountEmailServiceTests.cs`, `CognitoPayTemplatesTests.cs`) to LF, producing whole-file diff stats despite only a few real changed lines. *(Confirmed: user screenshot #1 — the `/simplify` → spec session.)*
2. **[VERIFIED]** The repo's committed EOL is genuinely **mixed**, confirmed authoritatively via `git ls-files --eol` (index field) and `git cat-file blob … | xxd`: `Cognito/NotificationTemplates/**/*.html` = **122 CRLF / 10 LF / 2 mixed**; `Cognito.Core/Services/Payment/*.cs` = **61 CRLF / 3 LF**; `*.sh` = **6 LF**. Individual LF-committed templates include `PayoutSucceeded.html`, `NegativeBalanceOrReserveHold.html`, `DisputeNew.html`. *(Confirmed: `git ls-files --eol`, `git cat-file blob`.)*
   - **Methodology gotcha (load-bearing):** `git show HEAD:<path>` applies `core.autocrlf` conversion on output and reports CRLF for an LF-committed blob — do **not** trust it for EOL checks. `grep -c $'\r'` in Git Bash here matched empty and returned the line count for every file (false "all CRLF"). The only authoritative tools are `git ls-files --eol` and `git cat-file blob … | xxd | grep 0d0a`.
3. **[VERIFIED]** `.editorconfig` declares a blanket `[*] end_of_line = crlf` and `AGENTS.md:66` mandates CRLF — both contradict the LF-committed `.html` templates. *(Confirmed: file reads.)*
4. **[VERIFIED]** `.gitattributes` at the Cognito repo root is `*    -crlf`, which disables git's EOL normalization/enforcement for all files; global `core.autocrlf=true` is therefore overridden to a no-op per file. Git neither normalizes nor flags the mixed state. *(Confirmed: `.gitattributes` read + `git config --get core.autocrlf`.)*
5. **[VERIFIED]** The recurring friction is **bidirectional**: agents that assume "all LF" break `.cs` (symptom 1); the hook that assumes "all CRLF" breaks `.html`. Two distinct Jun 25 sessions (`9eafedaf-…`, `eddd868f-…`) each spent real effort fighting EOL — manual `perl` normalization, a hung consistency-check agent on whole-file diffs. *(Confirmed: session transcripts.)*

## Reproduction Steps

**A — hook force-CRLFs an LF template (diff inflation):**
1. In the Cognito repo, Edit or Write any file under `Cognito/NotificationTemplates/**` whose committed sibling is LF.
2. The `PostToolUse Edit|Write` branch of `normalize-crlf.ps1` runs and force-CRLFs the file.
3. **Observed:** the file now differs from its LF-committed blob on every line → whole-file diff.

**B — hook reverts a manual LF fix (the "still occurring" path):**
1. Agent writes a new HTML template (Windows Write tool emits CRLF) and, to match LF siblings, runs `perl -i -pe 's/\r\n/\n/g' <file>`.
2. The command matches `normalize-crlf.ps1`'s `$inPlaceEdit` regex (`\bperl\b…\s-i`), so the `PostToolUse Bash` branch scans `git status --porcelain` and re-CRLFs **every** modified text file in the repo.
3. **Observed:** the just-applied LF normalization is silently undone; unrelated LF-committed modified files may also be flipped to CRLF.

**Expected:** working-tree EOL stays equal to the file's committed EOL (per-type: `.cs`=CRLF, the LF templates=LF), so edits produce minimal diffs and manual normalization is not fought.
**Actual:** a single blanket CRLF rule is applied regardless of the file's actual committed convention.
**Consistency:** deterministic given the inputs above.

## Evidence Collected

### Source Code — `Cognito Forms/.claude/hooks/normalize-crlf.ps1` (untracked; created Jun 23, fired Jun 25)
- `NormalizeFile` (lines 25–58) adds a `0x0D` before any `0x0A` lacking one — i.e. forces CRLF — for any file inside the repo root. The **only** exemptions are `.sh` (line 33) and binary (NUL-byte guard, lines 38–42). There is **no** per-type/per-path awareness: the header comment (line 2) states it enforces `.editorconfig`'s blanket `end_of_line = crlf`.
- `Edit|Write` branch (lines 60–65): normalizes the single edited file → **Repro A**.
- `Bash` branch (lines 67–88): on `$inPlaceEdit` match (regex line 72: `sed -i`, `perl -i`, `awk inplace`, `dos2unix`, `unix2dos`), it walks `git status --porcelain` (line 76) and calls `NormalizeFile` on **every** modified path (lines 82–88) → **Repro B**. The blast radius is "all modified files," not "the file the command touched."

### Runtime Evidence — session transcripts
- `9eafedaf-06d8-46eb-9b4c-ac5d4d58991e` (Jun 25): blanket LF-normalization flipped CRLF `.cs` → LF; discovered via `file`/`git show HEAD:…`; remediated with `perl -i -pe 's/\r\n/\n/g'` on the new HTML only, deliberately **not** touching the `.cs` files. Matches screenshot #1.
- `eddd868f-c318-45bf-85d6-31142a677700` (Jun 25): Phase-2 `.cs` files showed whole-file diffs after working-tree EOL conversion; a backgrounded consistency-check agent hung 10+ min scanning EOL on whole-file diffs; resolved by `TaskStop` + inline pass.

### Git History / Config
- The hook is **not version-controlled anywhere**: `git ls-files repos/cognito-forms/.claude/hooks/` is empty in claude-config, and the manifest's cognito-forms entry symlinks `DotClaudeDirs = @('skill-config','skills','knowledge')` — **no `hooks`**. `normalize-crlf.ps1` is a loose local file in the Cognito repo's `.claude/hooks/`, invisible to `git status` in both repos. This is why "the work we did earlier" appears in no history.
- Prior EOL bug `windows-portability-in-probe-glue-and-field-validators` (claude-config commit `f6d66259`, Jun 19) deliberately left `user/scripts/fix-line-endings.ps1` **unwired** because it also normalizes *to* CRLF and would worsen a `\n`-only downstream validator. Same blanket-CRLF flaw class as this hook.

### Related Documentation
- `docs/bugs/CLAUDE.md`: harness-defect investigations; descriptive slugs; no work-item tracker.
- `.editorconfig` (`[*] end_of_line = crlf`) and `AGENTS.md:66` are the mis-stated "source of truth" the hook trusts; they do not match the committed `.html` reality.

## Theories

### Theory 1: Blanket convention vs. mixed reality (root cause)
- **Hypothesis:** The hook applies one EOL rule (CRLF) to a repo whose committed convention is per-type mixed, so it corrupts the EOL of every file type it guesses wrong about (`.html` templates). The symmetric agent failure (LF guess breaking `.cs`) is the same root cause from the other side: no authoritative per-type EOL declaration exists, because `.gitattributes` `* -crlf` opts git out of enforcement.
- **Supporting evidence:** Symptoms 1–4; hook source lines 30–53 (no per-type branch); committed-blob EOL divergence by extension.
- **Status:** Confirmed.

### Theory 2: Over-broad Bash blast radius reverts correct fixes
- **Hypothesis:** Even once an agent correctly normalizes a file, the Bash branch re-CRLFs all modified files, undoing the fix and flipping bystanders — the concrete "still occurring" mechanism.
- **Supporting evidence:** hook lines 76–88 (whole-`git status` rewrite on any in-place editor); Repro B.
- **Status:** Confirmed.

### Theory 3: Untracked hook → drift and invisibility (contributing)
- **Hypothesis:** Because the hook is outside version control and the symlink manifest, it can't be reviewed, diffed, or kept consistent across worktrees, and fixes to it won't propagate.
- **Supporting evidence:** empty `git ls-files`; manifest `DotClaudeDirs` lacks `hooks`.
- **Status:** Confirmed (secondary).

## Proven Findings

1. The defect is a **blanket-vs-mixed EOL mismatch**, not a Windows tooling quirk. The hook (CRLF-everywhere) and agents (LF-everywhere) are both wrong because the repo legitimately commits `.cs` as CRLF and the notification-template `.html` as LF, and no machine-enforced per-type declaration exists.
2. The Bash branch's "normalize every git-modified file" behavior is the active mechanism that keeps the friction recurring after a correct manual fix.
3. The hook is untracked and unmanaged, so it has no review/propagation path.

## Decided Fix Direction (for /plan-bug)

Confirmed with Jacob via `AskUserQuestion`:

- **Convention = per-type mixed (codify reality):** `.cs` = CRLF, the LF-committed templates stay LF. The hook must become **convention-aware** rather than blanket-CRLF. Recommended source of truth, hook-side only: **match the file's committed EOL** — for a tracked file, normalize the working tree to its HEAD-blob EOL; for a new/untracked file, fall back to the dominant EOL of same-extension siblings in its directory (else `.editorconfig`'s CRLF default). This makes "minimal diff" the literal invariant the hook enforces.
- **Scope = hook-side only (claude-config):** no change to the team-owned Cognito `.gitattributes`/`.editorconfig`. The fix lives in `normalize-crlf.ps1`. Also: (a) **scope the Bash branch** to the file(s) the command actually touched, not all of `git status`; (b) **bring the hook under version control** — move it into `claude-config/repos/cognito-forms/.claude/hooks/` and add a `hooks` symlink mapping to the manifest's cognito-forms entry so it is tracked, reviewable, and shared across worktrees.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| EOL hook (logic) | `Cognito Forms/.claude/hooks/normalize-crlf.ps1` | Blanket CRLF on mixed repo; over-broad Bash blast radius |
| Hook wiring | `claude-config/repos/cognito-forms/.claude/settings.json` (PostToolUse `Edit\|Write` + `Bash`) | Wires the hook by absolute path |
| Version control | `claude-config/manifest.psd1` (cognito-forms `DotClaudeDirs`) | Hook untracked / not symlinked |
| Sibling script | `claude-config/user/scripts/fix-line-endings.ps1` | Same blanket-CRLF flaw; deliberately unwired — do not wire |

## Open Questions

- For new/untracked files where no same-extension sibling exists in the directory, is `.editorconfig`'s CRLF the right fallback, or should the hook leave brand-new files untouched and let the first commit set the convention? (Resolve in `/plan-bug`.)
- Should the convention-aware logic be factored into a shared helper so the unwired `fix-line-endings.ps1` can be retired rather than left as a blanket-CRLF foot-gun? (Out of decided scope; note only.)

## Resolution (implemented)

Fixed directly (hook-side only, per the decided direction) rather than routed through `/plan-bug`.

**Hook rewrite** — `repos/cognito-forms/.claude/hooks/normalize-crlf.ps1` now resolves a per-file TARGET EOL and converts to it (bidirectional: adds CR for a CRLF target, strips CR for an LF target), replacing the blanket force-CRLF:
- Tracked file → TARGET = **dominant** EOL of the committed HEAD blob (CRLF count vs bare-LF count; tie → CRLF). Dominant (not first-CRLF-wins) so intra-file `i/mixed` blobs — e.g. `Cognito.Core/Anthropic/*.cs` at 359 LF + 63 CRLF — are not force-flipped to all-CRLF.
- New/untracked file → dominant EOL of same-extension siblings in its directory, else CRLF (`.editorconfig` default).
- Raw committed bytes read via `git cat-file blob HEAD:<rel>` (NOT `git show`, which autocrlf-corrupts output); single git process with exit-code check (a git failure no longer silently downgrades the target to LF).
- Preserved: `.sh`→LF exemption, NUL-byte binary guard, empty-file skip, repo-root scope guard, JSON-stdin contract, idempotency. The Bash-branch whole-`git status` scan is **intentionally retained** — under match-committed-EOL it is a safe healing pass (each modified file → its own committed convention), which also corrects a wrongly-LF'd `.cs` from a stray `perl -i`.

**Cross-worktree** — all four worktrees (main + `Cognito Forms-B/C/D`) share ONE `settings.json` (itself a symlink into claude-config) that invokes the hook by absolute path to the main copy, so every worktree executes the same file. `$repoRoot` is now resolved **per-invocation** — Edit/Write from the edited `file_path`'s dir, Bash from the command `cwd` — via `git -C <startDir> rev-parse --show-toplevel`. Scope is gated by **git-common-dir equality** (`rev-parse --git-common-dir` of the candidate vs the canonical repo), not a hardcoded path or a B/C/D allowlist: every Cognito worktree (incl. future and temp detached worktrees) shares one common `.git`, so the hook auto-follows whichever worktree fired it while staying a strict no-op in any other repo (claude-config, etc.). Canonical override via `$env:CRLF_HOOK_REPOROOT` (test-only).

**TDD** — `repos/cognito-forms/.claude/hooks/normalize-crlf.Tests.ps1`: self-contained harness (temp `git init` / `git worktree add` repos, real stdin JSON, byte assertions), **14/14 green**, covering CRLF-restore, LF-restore (the core regression), idempotency, sibling fallback, `.sh`, binary, the Bash branch, the JSON contract, the dominant-EOL `i/mixed` case, and the cross-worktree cases (Case10a: file in a sibling worktree → normalized to that worktree's HEAD EOL; Case10b: file in an unrelated repo → bytes untouched; Case10c: Bash branch scans the `cwd` worktree, main left untouched). Testability via `$env:CRLF_HOOK_REPOROOT` (production-inert).

**Version control + deployment** — hook added to `manifest.psd1` cognito-forms `DotClaudeFiles` so it is tracked/reviewable/shared across worktrees (it was a loose untracked file). Live wiring is unchanged (settings.json absolute path to the main copy). The live main copy had **drifted stale** (7387 B vs the 11217 B source — the prior hardlink had broken), which is why the friction kept recurring: edits to the versioned source never reached the executing file. It has been **re-linked** to the versioned copy (`fsutil hardlink list` shows both paths share one inode; contents byte-identical). Symlink creation still requires elevation this process lacks, so the durable form is pending — run `setup.ps1 repair` from an elevated PowerShell to convert the hardlink to a managed symlink. *(Caveat: an editor that writes-new-then-renames breaks a hardlink and silently re-introduces drift — the symlink is the durable form.)*

**Live validation** — against the real **worktree B** (`Cognito Forms-B`), both directions verified end-to-end through the deployed hook with the real stdin-JSON contract: an LF-committed template (`DisputeLost.html`) corrupted to CRLF was restored to LF, and a CRLF-committed `.cs` (`CognitoPayAccountAlertService.cs`) corrupted to LF was restored to CRLF — each leaving `git diff` clean. This confirms the dynamic `repoRoot` + git-common-dir gate follow the active worktree (the old hook was a no-op in B). Unit suite 14/14 green.

### Deferred follow-ups (not in this fix)
- **`.sh`-only shell guard** misses `.bash`/`.zsh`/extensionless shebang scripts (low risk in this repo).

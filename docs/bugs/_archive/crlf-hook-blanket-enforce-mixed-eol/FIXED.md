---
kind: fixed
feature_id: crlf-hook-blanket-enforce-mixed-eol
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: Pester (normalize-crlf.Tests.ps1, re-run fresh, 14/14 green)
auto_ticked_rows: 0
---

# Completion Receipt

`crlf-hook-blanket-enforce-mixed-eol` marked fixed on 2026-07-12. Root cause: the Cognito Forms
repo's `normalize-crlf.ps1` `PostToolUse` hook enforced one blanket EOL convention (force-CRLF on
every non-`.sh` file) against a repo whose *committed* EOL is genuinely per-type mixed (`.cs` =
CRLF, `NotificationTemplates/**/*.html` = LF) — so it corrupted the EOL of every LF-committed
template it touched (inflating diffs to whole-file), and its `Bash` branch additionally reverted
correct manual LF fixes by re-CRLFing every git-modified file on any in-place-editor command.

## What was fixed, and by whom

The code fix — a rewrite of `Cognito Forms/.claude/hooks/normalize-crlf.ps1` (tracked at
`repos/cognito-forms/.claude/hooks/normalize-crlf.ps1`) into a **convention-aware** normalizer
that matches each file's own HEAD-committed dominant EOL (tracked file → dominant EOL of the
committed blob; untracked file → dominant EOL of same-extension directory siblings, else CRLF
default; `.sh` stays exempt) — was already landed **directly**, bypassing the normal
`/plan-bug` → PHASES.md route, in commit `5597395b` ("fix(cognito-hooks): convention-aware
cross-worktree CRLF normalizer", 2026-06-25), per the SPEC's own `## Resolution (implemented)`
section. That commit also added a 14-case Pester suite (`normalize-crlf.Tests.ps1`) and tracked
the hook in `manifest.psd1`'s `cognito-forms` `DotClaudeFiles` (previously a loose, untracked
file — the reason the fix had "landed" invisibly to a casual `git log` skim of this bug dir).

This close-out pass (2026-07-12, this subagent) did **no code fix** — it re-verified the
pre-landed fix on disk and closed the pipeline-bookkeeping gap the direct-fix bypass left open
(`SPEC.md` was still `Concluded`, and no `PHASES.md`/`FIXED.md` existed for this bug dir).

**`user/scripts/fix-line-endings.ps1` — this subagent's owned file for this bug — required no
change.** The SPEC's `## Decided Fix Direction` scopes the fix "hook-side only" to the *different*
Cognito repo hook above; `fix-line-endings.ps1` is listed only as a same-defect-class sibling,
explicitly "deliberately unwired — do not wire", with retiring/factoring it noted as
**"Out of decided scope; note only."** No fork exists here to resolve — the SPEC already settled
the scope with Jacob via `AskUserQuestion` before this bug reached `/plan-bug`.

## Symptom reproduction — evidence the defect is gone

**Original symptom (SPEC Verified Symptoms 1 & 2, 2026-06-25):** the hook force-CRLFed an
LF-committed template (whole-file diff) and, separately, the Bash branch re-CRLFed every
git-modified file after any `perl -i`/`sed -i` in-place edit — silently reverting correct manual
LF normalization.

**Evidence the symptom is gone (2026-07-12, re-verified fresh — not merely trusted from the
SPEC's narrative):**

```
powershell.exe -Command "Import-Module Pester -RequiredVersion 6.0.0 -Force; \
  Invoke-Pester -Path 'repos/cognito-forms/.claude/hooks/normalize-crlf.Tests.ps1' -Output Detailed"

PASS: Case1: tracked CRLF file restored to CRLF
PASS: Case2: tracked LF template restored to LF (regression fixed)
PASS: Case3: matching EOL not rewritten (bytes+mtime unchanged)
PASS: Case4a/4b/4c: untracked-file sibling-EOL fallback (CRLF / LF / no-sibling default)
PASS: Case5: .sh left LF (never CRLFed even when committed CRLF)
PASS: Case6: binary file (NUL) untouched
PASS: Case7: Bash branch normalizes each modified file to its own committed EOL
PASS: Case8: malformed/empty stdin -> {"continue":true} exit 0
PASS: Case9: mixed blob, bare-LF dominant -> LF target (not first-CRLF -> mass CRLF)
PASS: Case10a/10b/10c: cross-worktree scope (sibling worktree normalized; unrelated repo/main untouched)

==== Summary: 14 passed, 0 failed ====
```

Case2 and Case7 are the direct regression proofs for the two original symptoms: an LF-committed
template is now restored to LF (not force-CRLFed), and the Bash branch normalizes each modified
file to *its own* committed convention rather than blanket-CRLFing the whole `git status`.

Also confirmed on disk: `git log -- repos/cognito-forms/.claude/hooks/normalize-crlf.ps1` shows
the single landing commit `5597395b`; `manifest.psd1`'s `cognito-forms` entry lists
`hooks\normalize-crlf.ps1` under `DotClaudeFiles`; `repos/cognito-forms/.claude/settings.json`
wires the hook by absolute path on `PostToolUse Edit|Write` and `Bash`. `git log --
user/scripts/fix-line-endings.ps1` shows only the repo-bootstrap commit — confirming zero drift
on the file this subagent owned, consistent with it being out of decided scope.

## Gates run

- `Invoke-Pester -Path 'repos/cognito-forms/.claude/hooks/normalize-crlf.Tests.ps1'` → 14 passed,
  0 failed (fresh re-run, 2026-07-12).
- `git status --short` / `git log -- <path>` spot-checks confirming (a) the Cognito hook fix,
  its tests, and its manifest entry are all present and committed, and (b)
  `user/scripts/fix-line-endings.ps1` carries no uncommitted changes and no post-bootstrap commit.

## Files touched this close-out pass

- `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/PHASES.md` — new (single verification-only
  phase).
- `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/SPEC.md` — `**Status:**` flipped to `Fixed`.
- `docs/bugs/crlf-hook-blanket-enforce-mixed-eol/FIXED.md` — this receipt (new).

No hook script, `settings.json`, `manifest.psd1`, or `user/scripts/fix-line-endings.ps1` edit was
needed or made — the code fix was already correct and committed; the only gap was pipeline
bookkeeping (this bug dir's own `SPEC.md`/`PHASES.md`/`FIXED.md` trio never caught up to the
direct-fix bypass that landed the code).

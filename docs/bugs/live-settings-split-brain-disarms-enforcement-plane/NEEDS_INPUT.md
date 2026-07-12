---
kind: needs-input
feature_id: live-settings-split-brain-disarms-enforcement-plane
written_by: execute-plan
class: product
decisions:
  - Per-machine statusLine/env home now that the settings.local.json overlay is confirmed non-viable (D1)
  - Whether setup.py should gain a live hook/symlink check (WU-8) given it conflicts with cross-platform-setup's Locked Decision D6
date: 2026-07-12
next_skill: execute-plan
---

# /execute-plan --batch (part 2, WU-6) — Needs Input

Both decisions surfaced while executing `plans/fix-settings-split-brain-part-2.md` WU-6
(D1's per-machine content fork, pre-authorized as NEEDS_INPUT-eligible by the plan itself)
and while pre-checking WU-8 against `--provenance-lookup` before editing `setup.py`. The
unambiguous portion of WU-6 — folding `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` into the tracked
`user/settings.json` — has already landed this cycle (the plan explicitly says this half
"never halts"). The live `~/.claude/settings.json` symlink has **NOT** been restored yet —
per the plan's explicit instruction, restoring it before D1 resolves would silently switch
this machine's actively-working status line to a config that is not confirmed functional
here, which is exactly the "do NOT guess the overlay behavior" case the plan calls out.

## Decision Context

### 1. Per-machine statusLine/env home now that the settings.local.json overlay is confirmed non-viable (D1)

**Problem:** The live (untracked) `~/.claude/settings.json` currently renders a working pwsh
one-liner `statusLine` (branch + model + context% — the git-bash/pwsh-specific command visible
at `~/.claude/settings.json:2-5`) plus `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: "75"` (already
folded into tracked SSOT this cycle, unaffected by this decision). The tracked `user/settings.json`
instead sets `"statusLine": {"type": "command", "command": "ccstatusline", "padding": 0}`. The
plan's D1 sub-question asked whether Claude Code's `settings.json`↔`settings.local.json` merge
precedence would let the pwsh command live in a `settings.local.json` overlay instead of being
folded into the shared tracked file. I dispatched a `claude-code-guide` research agent to check
official docs: **`settings.local.json` is a project-scoped (`.claude/settings.local.json`)
concept only — it does not exist at the user level (`~/.claude/settings.local.json`) per
Anthropic's own settings documentation**, even though this repo's manifest happens to symlink
`~/.claude/settings.local.json` → `user/settings.local.json` today (that file only carries a
`permissions.allow` array, which may or may not actually merge at that scope — unverified). So
the overlay path the plan flagged as the "genuinely divergent content" destination is not
available. Separately, I checked whether the tracked default (`ccstatusline`) is actually usable
on this machine: `ccstatusline` is **not on PATH** and **not npm-cached** (`npx ccstatusline
--version` fails — "canceled due to missing packages and no YES option"), so restoring the
symlink as-is would silently degrade this machine's status line from a working display to a
broken/non-invoking command every session, until/unless `ccstatusline` is installed.

**Options:**
- **Fold the pwsh statusLine command into the tracked `user/settings.json`, replacing `ccstatusline` (Recommended)** — Preserves this machine's currently-working status line with zero regression; fully reversible (one JSON edit). Risk: the command is Windows/pwsh-specific (`pwsh -NoProfile`, `$env:USERPROFILE`), so if any *other* machine is actively using this same tracked file today (a non-Windows workstation or a cloud session), its status line would break in the other direction. I cannot verify from this workstation alone whether that's a live concern (cross-platform-setup exists, but I have no evidence of an actively-used non-Windows Claude Code session against this exact tracked file today).
- **Install/adopt `ccstatusline` on this machine and accept the tracked default as-is** — Aligns this laptop with whatever the intended cross-machine default already is; requires an `npm install -g ccstatusline` (or equivalent) step and configuring it to reproduce (or replace) the current branch/model/context% display — unverified effort/behavior parity.
- **Leave the live file's statusLine untouched (defer the symlink restore for statusLine only) and land everything else** — Not actually available: Claude Code only reads one `~/.claude/settings.json`; there is no partial-restore mechanism that fixes the hook-registration split while leaving `statusLine` on the old file. Restoring the symlink is all-or-nothing for this file.

**Recommendation:** Fold the pwsh statusLine into tracked `user/settings.json` — it's the only option with zero verified regression risk on the one machine I can observe; the cross-machine risk is real but currently unverified/hypothetical, whereas the `ccstatusline`-is-broken-here risk is confirmed.

### 2. Whether setup.py should gain a live hook/symlink check (WU-8) given it conflicts with cross-platform-setup's Locked Decision D6

**Problem:** This bug's `PHASES.md` Phase 3 deliverable 4 / plan WU-8 says: "`setup.py` gains
the parallel live hook/symlink check (currently absent — `cmd_check` only compares symlink
resolution)." Before editing `setup.py` I ran the mandated `--provenance-lookup setup.py` and
then read `docs/features/cross-platform-setup/SPEC.md` D6: **"Ported `check` surface: symlink
state only; `setup.ps1`'s warn-only advisories stay PowerShell-side"** — an already-Locked
Decision (`mechanical-internal (auto-accepted)`, but still resolved and documented as
"a deliberate, permanent divergence (not a TODO)") that explicitly excludes the turn-routing
hook-registration advisory from `setup.py`'s ported surface, specifically to avoid tripling the
port's surface for zero cloud value. Neither this bug's `SPEC.md` (Fix Scope 5, which names only
`setup.ps1`) nor its `PHASES.md`/plan (which independently added the `setup.py` deliverable) shows
any awareness of D6 — this looks like an authoring gap in the `/spec-phases`/`/write-plan` step
for this bug, not a deliberate supersession. Note Phase 2 of this SAME bug already built
`user/scripts/doc-drift-lint.py --live`, which is stdlib, fully cross-platform, and performs
exactly the deep content check WU-8 wants (byte/symlink-resolution comparison against the
tracked SSOT) — it already satisfies the cross-platform-parity *spirit* of WU-8 without touching
`setup.py` at all.

**Options:**
- **Drop the `setup.py` change from WU-8; rely on `doc-drift-lint.py --live` for cross-platform parity (Recommended)** — Respects D6 as-is (no re-litigation), avoids a duplicate SSOT for "is the live file caught up" logic, and is arguably *more* correct than what WU-8 asked for since `--live` already runs on every host. WU-8 becomes a no-op / scope note in PHASES.md; WU-7 (the `setup.ps1` warn-pass extension, which SPEC Fix Scope 5 does call for) proceeds unaffected.
- **Proceed with WU-8 as written, treating it as a deliberate supersession of D6** — Adds the parallel check to `setup.py`, but this means quietly overturning a previously-Locked Decision from a different feature's SPEC without that SPEC being updated to reflect it — the kind of silent Locked-Decision conflict the harness's own provenance-lookup step exists to catch.
- **Amend `cross-platform-setup`'s D6 explicitly (new decision record) to narrow its scope, then implement WU-8** — Most "correct" from an audit-trail standpoint (D6 gets a documented amendment rather than a silent override) but is more process than this P0 bug's remaining scope warrants; better suited to a follow-up hardening item if the operator wants `setup.py` to gain the check.

**Recommendation:** Drop the `setup.py` change from WU-8 and rely on `doc-drift-lint.py --live` — it satisfies the underlying need without contradicting D6, and keeps this bug's scope from silently amending an unrelated feature's Locked Decision.

## What's landed vs. pending

- **Landed this cycle:** `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE: "75"` folded into tracked `user/settings.json` (unambiguous per the plan; committed).
- **Pending on this decision:** the rest of WU-6 (statusLine fold/decision + the live symlink restore itself), and Batch 2 (WU-7 `setup.ps1` warn-pass extension, WU-8 `setup.py` parallel check) — both are `Blocked by: WU-6` per the plan's Execution Schedule, so they were not started this cycle.
- Once resolved, re-run `/execute-plan plans/fix-settings-split-brain-part-2.md --batch` to resume: it will land the statusLine choice, restore the symlink (`setup.py repair` / `setup.ps1 repair`), confirm the `.bak`, then proceed to WU-7 (and WU-8 only if decision 2 is answered "proceed as written" or "amend D6 first").

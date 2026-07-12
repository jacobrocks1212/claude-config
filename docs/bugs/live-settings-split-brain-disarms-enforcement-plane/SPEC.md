# Live settings split-brain disarms the enforcement plane — Investigation Spec

> The live `~/.claude/settings.json` on this laptop is an untracked plain file registering ONLY
> the two turn-routing hooks, while the tracked `user/settings.json` registers the ~10 OTHER
> enforcement hooks and has NEVER carried the dispatch guard. Each half of the enforcement plane
> is dead wherever the other file rules: on this laptop none of the containment/sentinel/build/
> push/kill guards have been registered since Jun 11; on any symlink-intact machine (and the
> cloud bootstrap) the verbatim-dispatch guard is unwired. No automatic check detects either half.

**Status:** Concluded
**Priority:** P0
**Last updated:** 2026-07-11
**Related:** `docs/specs/turn-routing-enforcement/` (SPEC.md:114 "Settings placement" deliberately declared per-machine registration and deferred unification; `REGISTRATION.md` is the paste-fragment design this spec retires); `docs/bugs/legacy-tool-input-env-hooks-dead/` (two of the disarmed hooks are ALSO dead code internally — fixing registration alone does not revive them); `docs/bugs/powershell-tool-bypasses-bash-matched-guards/` (the reconciled SSOT is where the widened matchers must land — sequence together); the `multi-repo-concurrent-runs` per-repo hook scoping note (root `CLAUDE.md` Hooks section) — the lazy hooks are marker-gated per-repo, which is what makes merging them into the tracked file safe.

## Verified Symptom

All facts re-verified live on this machine, 2026-07-11.

1. **The live file is a plain file, not the manifest-declared symlink.** `~/.claude/settings.json` is a regular file (1851 bytes, mtime **Jun 11 23:24**). `manifest.psd1:14` declares it a File symlink to `user/settings.json` (under the `# File symlinks` header at line 11). `setup.ps1:195-198` would report it `REAL (not symlinked)` — but only when someone manually runs the check; nothing runs it automatically.

2. **The live file registers ONLY the turn-routing pair.** Its `hooks` object is exactly the `REGISTRATION.md` fragment: `lazy-route-inject.sh` (UserPromptSubmit, SessionStart matcher `compact`, PostCompact) + `lazy-dispatch-guard.sh` (PreToolUse matcher `Agent|Task`). Nothing else — not even `pr-review-cache-guard.sh`, which REGISTRATION.md's own merge example shows coexisting.

3. **The tracked file registers the other ~10 hooks and has NEVER carried the guard.** `user/settings.json` registers: `load-branch-docs-context.sh` (SessionStart:31), `execute-plan-compact-reorient.sh` (:41) + the inline plan-recovery `bash -c` (:46), `pr-review-cache-guard.sh` (PreToolUse Read, :58), the five-hook PreToolUse `Bash` chain (:64-91: `block-work-repo-git-push.sh`, `block-terminal-kill.sh`, `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`), `lazy-cycle-containment.sh` again (Skill, :98), and the Write|Edit pair (:104-117: `block-noncanonical-blocker-write.sh`, `block-sentinel-write-on-stray-branch.sh`). `git log -S "lazy-dispatch-guard" -- user/settings.json` returns **zero commits** — the guard registration was never tracked.

4. **Consequence A — this laptop has run guard-less since ≥ Jun 11 23:24.** None of the containment / sentinel-write / long-build / build-queue / push / kill hooks have been registered here. Corroboration: the ONLY `hook-events.jsonl` under `~/.claude/state/**` (`state/abf2a6.../hook-events.jsonl`) contains a **single synthetic** long-build deny (`repo_root: "C:/tmp"`, ts 2026-07-11 22:19 — a manual pipe test during this investigation); zero organic guard events exist across all state dirs.

5. **Consequence B — the dispatch guard is unwired wherever the symlink IS intact.** `setup.py bootstrap --target User` materializes the manifest mapping, linking the live path to `user/settings.json` — which lacks the guard. The cloud bootstrap `.claude/hooks/session-start.sh` (CLAUDE_CODE_REMOTE guard at :33, bootstrap call at :45) exists, per its own header (lines 5-15), precisely so "the by-reference cycle dispatch … via the guard's updatedInput" loads — yet the file it links in does not register `lazy-dispatch-guard.sh`. The entire verbatim-dispatch enforcement edifice depends on an untracked per-machine file.

6. **Detection is structurally absent in every layer:**
   - `user/scripts/doc-drift-lint.py` `check_hooks` (:202) compares root `CLAUDE.md` `## Hooks` ↔ the **repo** `user/settings.json` only — the live file is out of scope.
   - `setup.ps1:215-259` is a warn-only pass that checks ONLY the two turn-routing hooks are in the live file (they are, here — the check passes on the broken machine) and never checks the tracked hooks are live; it also only runs manually.
   - `user/scripts/test_hooks.py` mount-site tests (`test_straybranch_registered_in_settings` :4673, asserting at :4677; `test_longbuild_guard_registered_in_settings` :4828, asserting at :4832) read `_REPO_ROOT / "user" / "settings.json"` — the repo file, correctly green while the live machine is disarmed.

7. **Field-evidence blindness (downstream corollary).** Deny-ledger / hook-events / incident-scan / KPI-efficacy signals on this machine **undercount from Jun 11 to the fix date** — the guards that would have emitted them were not registered. Consumers (`incident-scan.py`, efficacy evaluation, retro grading) must treat that window as partially blind, not as evidence of zero friction.

## Root Cause

**Classification: `config-split-brain` (two contradicting placement designs, no reconciliation contract, no live-state check).**

The surface→source trace: `docs/specs/turn-routing-enforcement/SPEC.md:114` ("Settings placement") deliberately declared hook *registration* per-machine — "hook registration must be added to each machine's live settings.json" — and explicitly deferred cross-machine unification out of scope. `REGISTRATION.md` operationalized that as a paste-this-fragment instruction against the live file. But `manifest.psd1:14` simultaneously declares that same live path a symlink to the tracked file. Executing the REGISTRATION.md design therefore *required* the live path to be (or become) a real file — and on this laptop the fragment was pasted **wholesale** (mtime Jun 11 23:24, the Phase-6 arming date per REGISTRATION.md's pipe-test record of 2026-06-11), replacing rather than merging: the live file lacks every tracked-file hook including `pr-review-cache-guard.sh` from REGISTRATION.md's own merge example. The two hook sets were never reconciled in either direction (the guard was never added to the tracked file; the tracked hooks were never re-added to the live file), and no automatic check inspects the live file's symlink status or content.

## Fix Scope (Concluded)

1. **Reconcile both hook sets into tracked `user/settings.json` as the single SSOT.** Merge the turn-routing pair (lazy-route-inject on UserPromptSubmit / SessionStart-compact / PostCompact; lazy-dispatch-guard on PreToolUse `Agent|Task`) alongside the existing ~10 registrations. This is safe on all machines: the lazy hooks are **marker-gated per-repo** (`lazy-state.py --marker-present --repo-root <cwd>`, fail-open, marker-absent fast path) — per-machine placement buys nothing.
2. **Restore the symlink on this laptop via setup repair** (`setup.ps1` / `setup.py repair`), after diffing the live file for genuinely per-machine content (its `statusLine` is a pwsh one-liner vs the tracked `ccstatusline`; it carries `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`) — see D1.
3. **Rewrite/retire `REGISTRATION.md`'s per-machine design** and amend `SPEC.md` §Settings placement: registration now ships in the tracked file; the fragment doc becomes historical. Keep the pipe-test run records.
4. **Add a `--live` check mode to `doc-drift-lint.py`**: PASS iff the live `~/.claude/settings.json` is a symlink AND resolves to the repo file (content-identical as fallback for copy-based hosts). Surface it through an existing periodic surface — see D2 — so drift self-announces instead of waiting for a manual `setup.ps1` run.
5. **Extend `setup.ps1:215-259`'s warn pass** (or replace it with the `--live` check) to verify the FULL tracked hook set is live, not just the turn-routing pair — the current check passes on exactly this failure.
6. **Blind-window annotation:** record Jun 11 → fix-date as a partially-blind window for this machine's hook-derived signals wherever efficacy/KPI baselines consume them (see D3).

## Decisions

- **D1 — Where does genuinely per-machine content live?** The live file's pwsh `statusLine` and `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` differ from the tracked file. *Recommendation:* fold acceptable values into the tracked SSOT (the tracked file already tolerates machine-specific content, e.g. the `C:/Users/JacobMadsen/...` marketplace path); anything truly divergent moves to `settings.local.json` — noting that file is itself manifest-mapped (`manifest.psd1:15`), so a genuinely untracked overlay may need a manifest carve-out. Open sub-question: confirm Claude Code's settings.json/settings.local.json merge precedence for `statusLine` before relying on the overlay.
- **D2 — Surfacing vehicle for the `--live` check:** lazy-route-inject banner (fires every prompt-submit in marked runs; cheap symlink+resolve stat) vs `lazy-state --probe` vs a SessionStart hook. *Recommendation:* lazy-route-inject banner line + a `lazy-state --probe` field, both calling the same `doc-drift-lint.py --live` helper; a SessionStart registration would itself live in the file being checked (bootstrap circularity) so keep it as reinforcement only.
- **D3 — Blind-window treatment:** annotate vs backfill vs ignore. *Recommendation:* annotate only (a machine-scoped `blind_window` note where incident-scan/efficacy read hook-events); backfilling is impossible (events were never generated) and silently ignoring re-poisons efficacy baselines.
- **D4 — Sequencing with the sibling specs:** *Recommendation:* land this reconciliation FIRST; `powershell-tool-bypasses-bash-matched-guards` (matcher widening) and `legacy-tool-input-env-hooks-dead` (hook rewrites) both edit the same SSOT and should stack on top, so the revived/widened registrations are never re-split.

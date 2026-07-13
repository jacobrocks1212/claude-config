# Legacy TOOL_INPUT env hooks are dead code — Investigation Spec

> `block-terminal-kill.sh` and `block-work-repo-git-push.sh` — both registered in the tracked
> `user/settings.json` PreToolUse Bash chain — read `$TOOL_INPUT_command`, an environment variable
> the hook interface never populates (the interface is stdin JSON). The command string is always
> empty, every regex misses, and the hooks exit 0 on all inputs. The mobile-workflow terminal-kill
> protection and the work-repo push protection have been illusory since introduction (May 2026).

**Status:** Fixed
**Priority:** P1
**Last updated:** 2026-07-12
**Related:** `docs/bugs/_archive/live-settings-split-brain-disarms-enforcement-plane/` (on this laptop these hooks are additionally NOT REGISTERED at all — the live file lacks the whole Bash chain; fixing the split-brain alone would arm two hooks that still do nothing); `docs/bugs/powershell-tool-bypasses-bash-matched-guards/` (a rewritten kill-block matched only on `Bash` is instantly bypassable via the PowerShell tool, where `Stop-Process` is a native cmdlet — the rewrite must land with the widened matcher); `docs/specs/turn-routing-enforcement/` (owns the deny-via-JSON fail-OPEN hook contract these predate).

## Verified Symptom

All facts re-verified live, 2026-07-11.

1. **Both scripts read a never-populated env var.** `user/hooks/block-terminal-kill.sh:5` and `user/hooks/block-work-repo-git-push.sh:6` both open with `command="$TOOL_INPUT_command"`. The Claude Code hook interface delivers the PreToolUse payload as **stdin JSON**; every modern hook in `user/hooks/` (lazy-cycle-containment, long-build-ownership-guard, build-queue-enforce, the Write|Edit sentinel pair, lazy-dispatch-guard) parses stdin. Neither legacy script reads stdin at all.

2. **Empirically dead — piped matching payloads pass clean (2026-07-11):**
   - `{"tool_name":"Bash","tool_input":{"command":"taskkill /F /IM node.exe"}}` → `block-terminal-kill.sh` exit **0**, no output.
   - `{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}` → `block-work-repo-git-push.sh` exit **0**, no output.
   With `$TOOL_INPUT_command` unset, `command` is empty; every `grep -qiE` misses; the fall-through `exit 0` allows.

3. **Both are REGISTERED, so this is registered dead code, not an unwired script.** `user/settings.json` PreToolUse `matcher: Bash` chain registers `block-work-repo-git-push.sh` (:68) and `block-terminal-kill.sh` (:73), and the root `CLAUDE.md` Hooks table documents both as active (:275-276).

4. **`block-work-repo-git-writes.sh` shares the defect but is unregistered.** `user/hooks/block-work-repo-git-writes.sh:5` reads the same env var; `CLAUDE.md:277` already documents it as **NOT registered** ("kept as the legacy standalone variant" overlapping the push hook).

5. **Zero test coverage.** `grep` for `block-terminal-kill` / `block-work-repo` in `user/scripts/test_hooks.py` returns nothing — the pipe-test harness that guards every modern hook never covered these, which is why the defect survived ~2 months.

6. **Contract divergence: `exit 2` denies.** `block-terminal-kill.sh` denies via `exit 2` (:10, :14, :20, :26), as does the push hook (:23) and the writes variant (:17). The repo's established contract (per the long-build-ownership-guard row in `CLAUDE.md` and the turn-routing containment table) is fail-OPEN with deny-via-JSON `permissionDecision`, because a PreToolUse non-zero exit is a hard blocking error, not a clean deny.

7. **Provenance:** `block-work-repo-git-push.sh` landed in `f8719a8` (2026-05-08); `block-terminal-kill.sh` in `ee90cc5` (2026-05-11, "/lazy autonomous dispatcher + mobile workflow infrastructure"). Whether a `TOOL_INPUT_*` env interface ever existed in any harness version was not established — see D3 — but it demonstrably does not work on the current harness.

## Root Cause

**Classification: `interface-contract-mismatch` (hooks authored against a nonexistent `TOOL_INPUT_*` env-var interface; never pipe-tested, so the mismatch was invisible).**

Surface→source trace: hook allows everything → `command` is empty on every invocation → `block-terminal-kill.sh:5` / `block-work-repo-git-push.sh:6` assign from `$TOOL_INPUT_command` → the harness populates no such variable; the payload arrives on stdin, which the scripts never read. The absence of any `test_hooks.py` coverage for either hook (item 5) is the second-order cause: every hook that IS pipe-tested had this class of defect forced out at authoring time.

## Fix Scope (Concluded)

1. **Rewrite both registered hooks on the stdin-JSON interface,** modeled on the sibling skeleton (`block-noncanonical-blocker-write.sh`: python3→python resolution, inline `-c` body — not a heredoc, `try/except → exit 0` fail-OPEN, deny-via-JSON `permissionDecision`). Preserve the behavioral rules: terminal-kill's taskkill/Stop-Process/kill-except-kill-port/exit-logout-shutdown/wt.exe blocks; push hook's `git push` + work-email (`jacob@cognitoforms.com`) + `CLAUDE_PUSH_APPROVED=1` bypass. Re-verify the bypass-token check against how `/push` actually composes the command (prefix match `^CLAUDE_PUSH_APPROVED=1\b` on the raw command string).
2. **Replace `exit 2` with the deny-via-JSON fail-OPEN contract** so a deny is a clean structured deny and an internal error never hard-blocks the tool call.
3. **Add pipe tests to `user/scripts/test_hooks.py`:** deny leg + allow leg + malformed-payload fail-open leg per hook, plus mount-site registration tests mirroring `test_longbuild_guard_registered_in_settings` (:4828) so a future deregistration is caught.
4. **Retire `block-work-repo-git-writes.sh`** (superseded by the push hook; unregistered by documented decision) with an archived/ trail rather than a third rewrite — see D1.
5. **Land with the widened tool matcher** from `docs/bugs/powershell-tool-bypasses-bash-matched-guards/` — reviving a kill-block that `Stop-Process` via the PowerShell tool walks straight past would re-create the illusion this spec removes.
6. **Update the root `CLAUDE.md` Hooks table rows** (:275-277) to reflect the rewrite and the writes-variant retirement.

## Decisions

- **D1 — Rewrite vs retire, per hook.** The protections' motivations still hold (the mobile/remote workflow is current — `restart-windows-claude` exists; work-repo push policy is standing). *Recommendation:* rewrite `block-terminal-kill.sh` and `block-work-repo-git-push.sh`; retire `block-work-repo-git-writes.sh` to `archived/` with a pointer to the push hook. If the operator no longer wants the mobile kill-guard, retiring BOTH kill/push with an archived trail is the honest alternative — silently keeping dead code is the only wrong option.
- **D2 — Deny mechanism:** keep `exit 2` (it does block, with stderr fed back) vs deny-via-JSON. *Recommendation:* deny-via-JSON fail-OPEN, matching every other guard in the repo; uniformity is what lets `test_hooks.py`'s shared helpers assert decisions.
- **D3 — Provenance question (open, non-blocking):** whether `TOOL_INPUT_*` env vars ever worked on an older harness version was not verified either way; it does not change the fix. Do not spend investigation budget on it unless an archaeology need arises.

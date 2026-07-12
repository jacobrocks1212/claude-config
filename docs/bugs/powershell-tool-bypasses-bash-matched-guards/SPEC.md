# PowerShell tool bypasses every Bash-matched command guard — Investigation Spec

> Every command guard is matched on tool `"Bash"` only, and the three inline second layers
> early-allow any non-Bash tool. Harness sessions on this machine expose a PowerShell tool whose
> payload carries the same `command` field — so `git push`, `Stop-Process`, `python lazy-state.py
> --run-end`, long builds, build-queue-gated ops, and sentinel writes via `Set-Content` cleanly
> bypass containment, long-build ownership, build-queue enforcement, and the (revived) push/kill
> blocks when issued through PowerShell instead of Bash.

**Status:** Concluded
**Priority:** P1
**Last updated:** 2026-07-11
**Related:** `docs/bugs/_archive/live-settings-split-brain-disarms-enforcement-plane/` (the widened matchers must land in the reconciled SSOT `user/settings.json` — sequence after it; on this laptop the Bash chain is currently not registered AT ALL, so the bypass is presently moot here and live on correctly-wired machines); `docs/bugs/legacy-tool-input-env-hooks-dead/` (the rewritten kill/push hooks must ship PowerShell-matched or they are reborn bypassed — `Stop-Process` is a native cmdlet); `docs/specs/turn-routing-enforcement/` (containment design; its `Agent|Task`-matched dispatch guard is NOT affected — PowerShell cannot dispatch agents); `docs/bugs/_archive/build-queue-enforce-cd-prefix-bypass/` (prior art: the same guard family's matcher-coverage failure class); `docs/bugs/_archive/cycle-subagent-runs-orchestrator-work/` (prior art: the Skill-tool bypass of the same enumerated-tool pattern, fixed by widening).

## Verified Symptom

All facts re-verified live, 2026-07-11.

1. **A PowerShell command tool exists on this machine's harness sessions.** The current session's tool inventory exposes a `PowerShell` tool alongside `Bash`, taking the same `command` string parameter (observed directly in-session; this is the Windows-native shell tool, not `powershell.exe` invoked through Bash).

2. **Every command-guard registration matches `"Bash"` only.** Tracked `user/settings.json` PreToolUse: the five-hook chain under `matcher: "Bash"` (:64) — `block-work-repo-git-push.sh`, `block-terminal-kill.sh`, `lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`; plus `lazy-cycle-containment.sh` under `matcher: "Skill"` (:94). No registration anywhere names PowerShell. (The live laptop file registers none of these at all — the split-brain spec.)

3. **The inline second layers ALSO early-allow non-Bash tools,** so widening matchers alone is insufficient:
   - `user/hooks/lazy-cycle-containment.sh:412` — `if tool_name != "Bash": _allow()`
   - `user/hooks/long-build-ownership-guard.sh:269` — `if payload.get("tool_name", "") != "Bash": ...` (allow)
   - `user/hooks/build-queue-enforce.sh:538` — same pattern.

4. **Bypass surface (per guard, all structural — a matching command via the PowerShell tool reaches no hook):**
   - *lazy-cycle-containment:* `python lazy-state.py --run-end` / routing flags, second-feature commits, `/lazy*` re-entry via commands — the whole runaway-op set.
   - *long-build-ownership-guard:* `cargo build --release` / `tauri build` / `npm run build` from a subagent, defeating the LONG-BUILD-OWNERSHIP-TAKEOVER redirect.
   - *build-queue-enforce:* every manifest-gated build op; ironic because build ops on this stack are natively PowerShell-shaped (`build-queue.ps1`, msbuild).
   - *push/kill blocks (post-revival):* `git push`, and `Stop-Process`/`taskkill` — `Stop-Process` being a PowerShell-native cmdlet makes the PowerShell tool the *likelier* emission path for exactly the command the kill-guard exists to stop.
   - *Sentinel writes:* `Set-Content`/`Out-File`/`>` to `BLOCKED*.md`/`NEEDS_INPUT.md` etc. bypass the `Write|Edit`-matched sentinel pair (`user/settings.json:104`) — same class as the Bash heredoc/redirection blind spot (item 5).

5. **Related pre-existing blind spot (context, not this bug):** command-level writes via Bash heredoc/redirection already bypass the `Write|Edit` sentinel hooks. The noncanonical-blocker class has a load-bearing **read-time backstop** (`lazy_core.detect_noncanonical_blocker`, `user/scripts/lazy_core.py:5251`, called from the state scripts' Step 3; the write hook's header at `block-noncanonical-blocker-write.sh:5-9` names it explicitly). The stray-branch sentinel class has **no read-time analog** — for it, the write-time hook is the only layer, and command-level writes (Bash or PowerShell) walk past it. `build-queue-enforce.sh`'s documented "accepted `cd`-into-another-repo blind spot" (root CLAUDE.md Hooks table) is the same accepted-gap genre.

6. **Not affected:** `lazy-dispatch-guard.sh` (PreToolUse `Agent|Task`) — the PowerShell tool cannot dispatch agents. The `Skill`-matcher containment leg is likewise orthogonal.

## Root Cause

**Classification: `enumerated-tool-allowlist drift` (missing-contract).**

Surface→source trace: a guarded command via the PowerShell tool executes unchecked → no PreToolUse registration matches (matchers enumerate `Bash`/`Skill`/`Write|Edit`/`Read` — `user/settings.json:53-117`) → and even if one did, the inline gates at `lazy-cycle-containment.sh:412`, `long-build-ownership-guard.sh:269`, `build-queue-enforce.sh:538` allow any `tool_name != "Bash"`. The guards were authored when Bash was the only command-execution tool the harness exposed; the harness later grew a PowerShell tool with identical command semantics; nothing — no test, no lint, no doc contract — asserts "every command-execution tool the harness exposes is covered by the command-guard chain." Prior art shows the class recurs: the Skill-tool bypass (`cycle-subagent-runs-orchestrator-work`) was the same drift one tool earlier.

## Fix Scope (Concluded)

1. **Widen the registrations** in the (post-split-brain-reconciliation) SSOT `user/settings.json`: `matcher: "Bash"` → `"Bash|PowerShell"` for the full command chain.
2. **Widen the inline gates** at the three cited lines to a shared command-tool set (`{"Bash", "PowerShell"}`), factored so the next command tool is a one-line addition — ideally a `lazy_core` constant all three import/embed consistently.
3. **Per-guard regex audit against PowerShell syntax** (each guard's patterns were written for POSIX sh):
   - segment separators: PowerShell uses `;` (and 7.x `&&`/`||`); `build-queue-enforce`'s segment-start anchor and `long-build-ownership-guard`'s first-real-token logic must tokenize PS segments correctly (call operator `&`, backtick continuation, `powershell.exe -Command` nesting).
   - env-prefix conventions differ (`$env:NAME='x'; cmd` vs `NAME=x cmd`) — affects `BUILD_QUEUE_BYPASS=1` / `CLAUDE_PUSH_APPROVED=1` bypass-token recognition and the long-build env-assignment-prefix skip.
   - kill semantics: add `Stop-Process` awareness where only `kill`/`taskkill` word-boundary regexes exist (terminal-kill already regexes `Stop-Process`, but its rewrite must keep it).
4. **Pipe tests per guard** in `user/scripts/test_hooks.py` with `tool_name: "PowerShell"` payloads — deny leg + allow leg each — plus a **meta-test** asserting every command-guard registration's matcher includes every member of the command-tool set (the missing contract from Root Cause, made mechanical).
5. **Sentinel command-write class (bounded):** do not attempt full command parsing for `Set-Content`/redirection writes; instead add a read-time stray-branch backstop mirroring `detect_noncanonical_blocker` (closes the one sentinel class with no second layer) — see D2.
6. **Docs:** update the root `CLAUDE.md` Hooks table trigger column (`PreToolUse (Bash, PowerShell)`) and note the widened contract in the turn-routing containment table.

## Decisions

- **D1 — Exact `tool_name` string (open, verify-first):** the tool is named `PowerShell` in the session tool inventory, and PreToolUse matchers match tool names — but the exact `tool_name` value delivered in the hook payload for this tool was NOT empirically captured (no hook is currently registered for it to log one). *Recommendation:* before hardcoding, register a temporary logging hook with matcher `"PowerShell"` (or `".*"`) and capture one real payload; then pin matcher + inline-set to the observed string. Treat this as the fix's first work unit, not an assumption.
- **D2 — Sentinel command-write coverage:** (a) regex-hunt `Set-Content`/`Out-File`/`>` targets inside command guards, (b) read-time backstops, or (c) accept the gap documented. *Recommendation:* (b) for stray-branch (mechanical, mirrors the proven noncanonical pattern); keep (c) explicitly documented for the rest — command-string write detection is unwinnable against quoting/subexpression forms and would bloat fail-open surface.
- **D3 — Sequencing:** *Recommendation:* land after `live-settings-split-brain-disarms-enforcement-plane` reconciles the SSOT (else the widened matchers land in a file that isn't live on this laptop), and together with the `legacy-tool-input-env-hooks-dead` rewrites so the revived hooks are born widened.
- **D4 — Other command-execution surfaces (open, bounded):** confirm during fix whether any additional non-Bash command tool exists on any active host (e.g. a future `Terminal`/`Shell` variant, WSL-side differences); the D4 meta-test from Fix Scope §4 turns this from a recurring audit into a one-line set update.

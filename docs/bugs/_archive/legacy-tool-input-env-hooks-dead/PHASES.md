# Implementation Phases — Legacy TOOL_INPUT env hooks are dead code

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; these are shell hooks verified via subprocess **pipe tests** in `user/scripts/test_hooks.py` (the repo's established hook-verification harness), the "build-tooling / repo-config, no app integration" untestable class. There is no `mcp-tool-catalog.md` in this repo, so the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The PreToolUse hook interface delivers its payload as stdin JSON (`{tool_name, tool_input:{command}, cwd, ...}`), NOT `$TOOL_INPUT_*` env vars.** *Runtime-coupled, already VALIDATED* by two independent pieces of on-disk evidence: (1) the SPEC's live piping (item 2) shows the env-var hooks exit 0 on every matching payload; (2) **every modern hook in `user/hooks/` parses stdin** — `block-noncanonical-blocker-write.sh` is a working reference (`raw = sys.stdin.read(); payload = json.loads(raw)`). The Phase-1 pipe tests ARE the runtime validation of the rewrite (they drive the real hook via `subprocess.run(..., input=<json>)` and assert the deny/allow decision) — verification is distributed into Phase 1, not deferred.
- **The exact `tool_name` string the harness delivers for the PowerShell command tool is NOT empirically captured** (sibling bug `powershell-tool-bypasses-bash-matched-guards` D1 owns that capture as "its first work unit"). This plan **removes the dependency on that string**: the rewritten hook bodies read `tool_input.command` **tool-name-agnostically** (they do NOT reject `tool_name != "Bash"`), so a `git push` / `Stop-Process` command denies regardless of which command tool emitted it — and the Phase-1 PowerShell-payload pipe tests assert the deny on the *command match*, independent of the exact `tool_name` literal. The only place the literal matters is the `settings.json` matcher string; see the Cross-feature Integration Note.

## Cross-feature Integration Notes

There is no `**Depends on:**` block in the SPEC (only a `**Related:**` line), so no upstream PHASES.md look-back applies. Two sibling bugs are **coordination-coupled** (documented here because they share files, not because a hard queue dep exists):

- **`powershell-tool-bypasses-bash-matched-guards` (sibling bug, Concluded) — the FULL PowerShell widening is ITS scope, not this bug's.** That bug owns: widening ALL five command-guard matchers, refactoring the inline `tool_name != "Bash"` early-allow gates in the *other three* hooks (`lazy-cycle-containment.sh`, `long-build-ownership-guard.sh`, `build-queue-enforce.sh`), the PS-syntax regex audit of those guards, the **meta-test** asserting every command-guard matcher covers every command-execution tool, and the **empirical `tool_name` capture (its D1)**. This bug touches PowerShell only to the minimal extent its own Fix-Scope item 5 demands — see the ⚖ note in Phase 1: the two *revived* hooks are born PowerShell-safe (tool-name-agnostic bodies) and their matcher is widened to `Bash|PowerShell`, so the kill/push protection is not reborn illusory (`Stop-Process` is a PowerShell-native cmdlet). When the sibling bug lands its meta-test + D1 capture, these two matchers already satisfy it; if D1 reveals a `tool_name` literal other than `PowerShell`, the sibling's meta-test corrects the string uniformly across all guards — this bug's tool-name-agnostic bodies need no second rewrite.
- **Sequencing precondition MET:** the sibling's D3 says land the widening only after `live-settings-split-brain-disarms-enforcement-plane` reconciles the SSOT `user/settings.json`. That bug is **Fixed + archived** (git log: `df853515 fix(live-settings-split-brain…): mark fixed and archive`; the sibling SPEC's `**Related:**` places it under `_archive/`). So widening these two matchers in the tracked SSOT now is safe.

---

### Phase 1: Rewrite the two REGISTERED hooks on the stdin-JSON interface (+ pipe tests, matcher widen)

**Scope:** Replace the dead `command="$TOOL_INPUT_command"` bodies of `block-terminal-kill.sh` and `block-work-repo-git-push.sh` with the proven stdin-JSON + deny-via-JSON fail-OPEN skeleton, preserving every behavioral rule, and prove the fix with pipe tests. This is the load-bearing behavioral phase — after it, the push/kill protection is actually live (on Bash and PowerShell payloads) instead of a no-op on all inputs.

**TDD:** yes. Write the failing pipe tests FIRST (they fail against the current dead hooks — the deny leg gets exit 0 / no output today), then rewrite the hooks green.

**Status:** Complete (implementation landed; runtime-verification rows below are covered GREEN by the pipe tests)

**Deliverables:**
- [x] `block-terminal-kill.sh` rewritten on the `block-noncanonical-blocker-write.sh` skeleton: `python3`→`python` resolution, inline `-c` body (NOT a heredoc — a heredoc binds python's stdin and swallows the payload), `read`-into-`_PY` then `"$PYTHON" -c "$_PY"`, top-level `try: main() / except SystemExit: raise / except Exception: sys.exit(0)` fail-OPEN, `_deny(reason)` emitting `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":...}}`, shell side always `exit 0`. Body reads `tool_input.command` and applies the behavioral rules **without gating on `tool_name`** (a terminate command is one whatever tool emits it).
- [x] `block-terminal-kill.sh` preserves ALL four behavioral rules verbatim in intent: (1) `\b(taskkill|Stop-Process)\b` deny; (2) `\bkill\b` deny EXCEPT when the command also matches `kill-port` (the `/mcp-test` `npx kill-port` allowance); (3) `\b(exit|logout|Stop-Computer|Restart-Computer|shutdown)\b` deny; (4) `\bwt\.exe\b` deny. `Stop-Process` awareness is retained (do not drop it — the sibling PowerShell bug depends on it surviving the rewrite).
- [x] `block-work-repo-git-push.sh` rewritten on the same skeleton: reads `tool_input.command`; fast-allow when the command does not match `\bgit\s+push\b`; allow when the command matches the bypass token `^CLAUDE_PUSH_APPROVED=1\b` (prefix on the raw command string — re-verify against how `/push` composes it); else deny only when `git config user.email` equals `jacob@cognitoforms.com` (work-repo gate). The deny reason names `/push` as the corrective action.
- [x] Both hooks emit the deny as JSON `permissionDecision: deny` — **never `exit 2`** (a PreToolUse non-zero exit is a hard blocking error; deny-via-JSON is the repo contract per `user/hooks/CLAUDE.md`).
- [x] `user/settings.json`: widen the PreToolUse matcher covering these two hooks so they run for the PowerShell command tool too. Because the shared `matcher: "Bash"` block also carries three hooks owned by the sibling bug, split so the two revived hooks are registered under a `Bash|PowerShell` matcher while the other three stay `Bash` for now (the sibling bug widens them). See the ⚖ note below.
- [x] Tests (`user/scripts/test_hooks.py`, append a new section): for EACH of the two hooks — **deny leg** (a matching command → fresh subprocess output parses to `permissionDecision: deny`), **allow leg** (a non-matching / bypass-token / non-work-email command → exit 0, no deny JSON), **malformed-payload fail-open leg** (`not-json` on stdin → exit 0, no deny), and a **PowerShell-payload deny leg** (`{"tool_name":"PowerShell","tool_input":{"command":"Stop-Process ..."}}` / `git push` → deny — proving the tool-name-agnostic body). Reuse `_run_bash(script, stdin_text, env)` + `_base_env(state_dir)`; build payloads as `{tool_name, tool_input:{command}}` JSON (mirror `_bqe_payload`). For the push hook's work-email leg, set up a throwaway git repo with `user.email jacob@cognitoforms.com` (mirror `_init_cognito_worktree`) or stub via env — assert the allow leg for a non-work email.
- [x] Tests: **registration meta-tests** mirroring `test_longbuild_guard_registered_in_settings()` (:5029) — assert `block-terminal-kill.sh` and `block-work-repo-git-push.sh` are each registered as a PreToolUse command whose matcher **includes both `Bash` and `PowerShell`** (parse `settings.json`, find the block(s) registering each hook, assert the matcher string contains both tool names). This makes the "revived hooks are born widened" contract mechanical (a future deregistration OR a matcher narrowing is caught).

**Implementation Notes (2026-07-12):** Both hooks rewritten on the `block-noncanonical-blocker-write.sh` stdin-JSON skeleton (python3→python resolution; inline `-c` body via `read -r -d '' _PY`; `try/except SystemExit: raise / except Exception: sys.exit(0)` fail-OPEN; `_deny`/`_allow` helpers; shell side always `exit 0`). Bodies read `tool_input.command` tool-name-agnostically, so a Stop-Process/git-push fired via the PowerShell tool denies exactly like via Bash. Behavioral rules ported to Python `re.search(..., re.IGNORECASE)` (grep -qiE parity), incl. the `kill-port` allowance and the escaped `wt\.exe`. The push hook threads the payload `cwd` into `git config user.email` and denies only on `jacob@cognitoforms.com`; bypass via `^CLAUDE_PUSH_APPROVED=1\b`. `settings.json` PreToolUse Bash block split: push+kill pair → `matcher: "Bash|PowerShell"`; the other three (containment, ownership-guard, build-queue-enforce) stay `matcher: "Bash"` with ownership-guard-before-enforce order preserved. Gate: `python user/scripts/test_hooks.py` → **172/172** (was 162/172; the 10 new deny/registration legs were RED-for-the-right-reason against the dead hooks first — `stdout=''` / `matcher='Bash'`). NOTE the revived hooks are now LIVE in-session: a Bash command containing the word `kill`/`exit` (or `git push` in a work repo) is now denied. **doc-drift-lint reports 2 findings** (CLAUDE.md Hooks table still says `Bash` for these two rows) — DELIBERATELY LEFT for Phase 2 (part 2), which reconciles the table + retires `block-work-repo-git-writes.sh`. Files: `user/hooks/block-terminal-kill.sh`, `user/hooks/block-work-repo-git-push.sh`, `user/settings.json`, `user/scripts/test_hooks.py`.

**Minimum Verifiable Behavior:** `python user/scripts/test_hooks.py` (the module's `__main__` runner, or `pytest user/scripts/test_hooks.py -k "terminal_kill or git_push"`) is GREEN, and the new deny-leg tests genuinely fail when run against the pre-rewrite hooks (RED-for-the-right-reason: the dead hook returns exit 0 / empty for a matching kill/push command). Concretely: `printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | bash user/hooks/block-work-repo-git-push.sh` in a work-email repo prints a `permissionDecision: deny` JSON object (today it prints nothing).

**Runtime Verification** *(checked by the pipe tests — the hooks' runtime IS the subprocess pipe):*
- [x] <!-- verification-only --> A matching `taskkill`/`Stop-Process`/`kill` (non-`kill-port`)/`exit`/`wt.exe` command piped to `block-terminal-kill.sh` as stdin JSON yields `permissionDecision: deny`; `npx kill-port 3333` and a non-matching command yield exit 0 / no deny. **Verified 2026-07-12:** `test_termkill_denies_taskkill`, `test_termkill_denies_stop_process`, `test_termkill_denies_bare_kill`, `test_termkill_denies_exit`, `test_termkill_denies_wt_exe`, `test_termkill_allows_kill_port`, `test_termkill_allows_plain_command` — all GREEN (`python -m pytest user/scripts/test_hooks.py -k "termkill or push" -q` → 17 passed).
- [x] <!-- verification-only --> A `git push` command in a `jacob@cognitoforms.com` repo piped to `block-work-repo-git-push.sh` yields deny; the same command prefixed `CLAUDE_PUSH_APPROVED=1`, or in a non-work-email repo, yields allow. **Verified 2026-07-12:** `test_push_denies_in_work_repo`, `test_push_allows_with_bypass_token`, `test_push_allows_in_non_work_repo`, `test_push_allows_non_push_command` — GREEN (same run above).
- [x] <!-- verification-only --> A malformed (non-JSON) stdin payload to either hook yields exit 0 with no deny (fail-OPEN). **Verified 2026-07-12:** `test_termkill_malformed_fails_open`, `test_push_malformed_fails_open` — GREEN (same run above).
- [x] <!-- verification-only --> A `{"tool_name":"PowerShell", ...}` matching payload to either hook yields deny (tool-name-agnostic body proven). **Verified 2026-07-12:** `test_termkill_powershell_payload_denies`, `test_push_powershell_payload_denies`, plus the registration meta-tests `test_termkill_registered_widened_matcher` / `test_push_registered_widened_matcher` — GREEN (same run above).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in this repo; the hooks' runtime observable is the subprocess pipe decision, asserted directly by the Phase-1 pipe tests above.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/block-terminal-kill.sh` — rewrite (verified exists, 29 lines, currently `command="$TOOL_INPUT_command"` at :5 with four `exit 2` legs). **Reuse the skeleton of `user/hooks/block-noncanonical-blocker-write.sh`** (`_allow`/`_deny` helpers, `-c` invocation, fail-OPEN wrapper) — do NOT invent a new shape.
- `user/hooks/block-work-repo-git-push.sh` — rewrite (verified exists, 26 lines, `$TOOL_INPUT_command` at :6, bypass-token check at :14, work-email gate at :20).
- `user/scripts/test_hooks.py` — append tests (verified exists, 6833 lines). **Reuse `_run_bash` (:265), `_base_env` (:292), the `test_longbuild_guard_registered_in_settings` pattern (:5029), and `_init_cognito_worktree`-style git-repo setup (:5067)** — do NOT add a new subprocess harness.
- `user/settings.json` — widen the two hooks' matcher to `Bash|PowerShell` (verified: both currently under the single `matcher: "Bash"` PreToolUse block at :99–:126).

**⚖ policy: PowerShell-matcher coupling to sibling bug → widen these two hooks in-cycle (most complete), demarcate the rest.** Fix-Scope item 5 ("land with the widened tool matcher") is in THIS SPEC's own scope, and the option to defer it entirely differs only in completeness/sequencing (not user-visible product behavior) — so per D7 the two revived hooks are born PowerShell-matched here, with tool-name-agnostic bodies so the empirically-unresolved `tool_name` literal (sibling D1) is not a blocker. The FULL widening of the other three guards + the cross-guard meta-test + the PS-syntax regex audit remain the sibling bug's scope (Cross-feature Integration Note). This is strictly non-worsening: a wrong-guess `PowerShell` literal matches nothing (no regression) and is corrected by the sibling's meta-test; a right literal closes the bypass now.

**Testing Strategy:** Pure pipe testing — drive each rewritten hook as a subprocess with a crafted stdin JSON payload and assert the parsed decision, exactly as the existing hook tests do. RED-for-the-right-reason is provable by running the new deny tests against the un-rewritten hooks first.

**Integration Notes for Next Phase:**
- The deny-via-JSON contract and the `python3`→`python` resolution are load-bearing repo conventions (`user/hooks/CLAUDE.md`): "Deny is JSON, not an exit code" and "Fail-OPEN is mandatory."
- After this phase, `user/settings.json` still registers `block-terminal-kill.sh` + `block-work-repo-git-push.sh` (now widened) and still does NOT register `block-work-repo-git-writes.sh` — Phase 2 retires that file and reconciles the root `CLAUDE.md` Hooks table so `doc-drift-lint.py` stays green.

---

### Phase 2: Retire `block-work-repo-git-writes.sh` and reconcile the docs

**Status:** Complete (file move + archived/CLAUDE.md row landed in `2f1e3eda`; root CLAUDE.md Hooks-table reconciliation — the one outstanding gap — completed in this close-out pass; `doc-drift-lint.py` GREEN)

**Scope:** Retire the unregistered, same-defect `block-work-repo-git-writes.sh` variant to `archived/` (SPEC D1 — it's superseded by the now-live push hook and unregistered by documented decision; a third rewrite is wasted effort), and update the root `CLAUDE.md` Hooks table so its three rows reflect reality. `doc-drift-lint.py` is the mechanical gate that the table now agrees with `settings.json`.

**TDD:** no (a `git mv` + documentation reconciliation; the gate is the existing `doc-drift-lint.py`, not a new unit test).

**Deliverables:**
- [x] `git mv user/hooks/block-work-repo-git-writes.sh archived/block-work-repo-git-writes.sh` (retire, do not rewrite). Add a row to `archived/CLAUDE.md` recording the retirement with a pointer to `block-work-repo-git-push.sh` as the live successor and the reason (shared `$TOOL_INPUT_command` dead-code defect + unregistered-by-decision, SPEC D1). — landed in `2f1e3eda` ("WU-5 retire writes-variant to archived/"); confirmed on disk: `archived/block-work-repo-git-writes.sh` exists, `user/hooks/block-work-repo-git-writes.sh` does not, `archived/CLAUDE.md` carries the retirement row.
- [x] Root `CLAUDE.md` Hooks table: update the `block-terminal-kill.sh` and `block-work-repo-git-push.sh` rows to reflect the stdin-JSON rewrite, the deny-via-JSON fail-OPEN contract, and the widened `PreToolUse (Bash, PowerShell)` trigger; update the `block-work-repo-git-writes.sh` row from "NOT registered (script exists in `user/hooks/`…)" to "**retired to `archived/`**" (it no longer exists in `user/hooks/`, so a "script exists" claim would itself be drift). — this was the ONE Phase-2 gap found on close-out audit (2026-07-12): the three rows were still Phase-0 prose after commits `030531c7`/`2f1e3eda` landed. Fixed in this pass: the `block-terminal-kill.sh` / `block-work-repo-git-push.sh` rows now read `PreToolUse (Bash, PowerShell)` and describe the rewrite; the writes-variant row now reads `**NOT registered** — retired to \`archived/\`` and carries a `<!-- doc-drift:deliberate-divergence -->` marker (the row necessarily fails doc-drift-lint's on-disk check — the file no longer lives in `user/hooks/` by design — so it is exempted in place per the linter's documented D2 escape hatch, same pattern as `docs/features/doc-drift-linter/SPEC.md`'s own example row).
- [x] `user/hooks/CLAUDE.md`: if it names `block-work-repo-git-writes.sh` as a live sibling, update the reference to point at the archived location (grep-check; do not leave a dangling in-directory reference). — grep-verified 2026-07-12: `user/hooks/CLAUDE.md` has zero references to `block-work-repo-git-writes.sh`; no dangling reference existed, no edit needed.

**Minimum Verifiable Behavior:** `python user/scripts/doc-drift-lint.py --repo-root .` exits 0 — the root `CLAUDE.md` Hooks table now matches `user/settings.json` registrations (both revived rows present + widened; the retired row no longer claims a `user/hooks/` script; the NOT-registered assertions stay coherent). `git status` shows `block-work-repo-git-writes.sh` moved (deletion from `user/hooks/` + addition under `archived/`), not deleted-and-lost.

**Implementation Notes (2026-07-12, close-out):** The file move (`2f1e3eda`) and `archived/CLAUDE.md` row landed earlier and were confirmed intact. The one outstanding gap was the root `CLAUDE.md` Hooks-table reconciliation (deliverable 2 above) — completed in this pass. Gate: `python user/scripts/doc-drift-lint.py --repo-root .` → `doc-drift-lint: 5 checks, 0 drift findings, 2 exempted divergences` (exit 0). The two exempted divergences are the writes-variant retirement row (this bug, deliberate) and a pre-existing unrelated `algobooth` manifest divergence (out of scope for this bug). Files touched this pass: `CLAUDE.md` (root, Hooks table rows only).

**Runtime Verification** *(checked by the doc-drift linter — no app runtime):*
- [x] <!-- verification-only --> `doc-drift-lint.py --repo-root .` exit 0 after the table edits and the file move (the Hooks-table ↔ settings.json cross-check passes). **Verified 2026-07-12:** `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0 (`5 checks, 0 drift findings, 2 exempted divergences`).

**MCP Integration Test Assertions:** N/A — documentation + file-move phase, no runtime-observable behavior.

**Prerequisites:**
- Phase 1: the two hooks are rewritten and their `settings.json` matcher is widened — the Hooks-table rows Phase 2 writes must describe the Phase-1 end state, and `doc-drift-lint.py` cross-checks against the Phase-1 `settings.json`.

**Files likely modified:**
- `user/hooks/block-work-repo-git-writes.sh` → `archived/block-work-repo-git-writes.sh` — `git mv` (verified exists, 20 lines, same `$TOOL_INPUT_command` defect at :5).
- `archived/CLAUDE.md` — add the deprecation-trail row (verified `archived/` dir exists).
- `CLAUDE.md` (root) — update the three Hooks-table rows (verified: rows for these hooks are documented in the Hooks table; the writes-variant row currently reads "NOT registered … script exists in `user/hooks/`").
- `user/hooks/CLAUDE.md` — reconcile any reference to the retired file (grep-verify before editing).

**Testing Strategy:** Run `doc-drift-lint.py --repo-root .` (the linter self-checks THIS repo is drift-clean); confirm exit 0. Manually confirm the `git mv` preserves history (deletion + addition, not a fresh file).

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate (orchestrator-owned) flips the SPEC/PHASES top-level `**Status:**` and writes `FIXED.md` after the validation tail; do NOT flip status or write `FIXED.md` from within these phases.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to `Fixed`, writes the `FIXED.md` receipt, and archives the bug once both phases' verification passes. This is NOT a checkbox in either phase.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

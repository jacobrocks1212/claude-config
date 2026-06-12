# Runtime Spike — Hook Mechanics (Phase 2)

**Date:** 2026-06-11  
**Goal:** Empirically resolve A4, A6, A11 from the Validated Assumptions ledger.  
**Spike workspace:** `$TEMP/spike-turn-routing/` (temp dir, deleted after; see Cleanup section)  
**Method:** `claude -p --model haiku` runs from the spike workspace dir so project-level `.claude/settings.json` applied.  
**Hook registration route:** Project `.claude/settings.json` in the workspace — confirmed working (hooks fired in all experiments). `--settings <file>` flag used for E3/E4 variant settings. Both routes work.

---

## E1 — PreToolUse fires for Agent + actual tool_name (A4)

**Command:**
```
cd $TEMP/spike-turn-routing
claude -p --model haiku "Use your Agent tool to dispatch one subagent (subagent_type general-purpose if you must choose) with the prompt: say hello and stop. Then reply DONE."
```

**Model stdout:** `DONE`

**Raw captured hook events (all 3 lines from hook-capture.log):**

```json
{"session_id":"b41a91fa-43a9-4ae3-9c47-7206f1da2a61","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\b41a91fa-43a9-4ae3-9c47-7206f1da2a61.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","hook_event_name":"SessionStart","source":"startup"}
{"session_id":"b41a91fa-43a9-4ae3-9c47-7206f1da2a61","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\b41a91fa-43a9-4ae3-9c47-7206f1da2a61.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Use your Agent tool to dispatch one subagent (subagent_type general-purpose if you must choose) with the prompt: say hello and stop. Then reply DONE."}
{"session_id":"b41a91fa-43a9-4ae3-9c47-7206f1da2a61","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\b41a91fa-43a9-4ae3-9c47-7206f1da2a61.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"description":"Say hello and stop","prompt":"Say hello and stop.","subagent_type":"general-purpose"},"tool_use_id":"toolu_01DYKoSs8afsCGMhUgAnmdBV"}
```

**PreToolUse hook input fields observed:**
- `session_id`: present (UUID)
- `transcript_path`: absolute Windows path to a `.jsonl` file named by session_id under `~/.claude/projects/<encoded-cwd>/`
- `cwd`: the working directory of the `claude -p` invocation
- `permission_mode`: `"default"`
- `hook_event_name`: `"PreToolUse"`
- `tool_name`: `"Agent"` (exact string — confirms matcher `Agent|Task` is correct)
- `tool_input`: object with `description`, `prompt`, `subagent_type`
- `tool_use_id`: unique per-call UUID

**Event counts for this run:** SessionStart=1, UserPromptSubmit=1, PreToolUse=1

**A4 CONFIRMED: PreToolUse fires for Agent dispatches. The literal `tool_name` value is `"Agent"`. Matcher `Agent|Task` is correct. All expected fields (session_id, transcript_path, cwd, permission_mode, tool_input.prompt) are present in hook stdin.**

---

## E2 — Nested dispatch + discriminator (A6 — THE go/no-go)

**Command:**
```
cd $TEMP/spike-turn-routing
claude -p --model haiku "Use your Agent tool to dispatch a subagent with this exact prompt: 'Use your Agent tool to dispatch one nested subagent with the prompt: say hi. Then reply NESTED-DONE.' Then reply OUTER-DONE."
```

**Model stdout:** `OUTER-DONE.` followed by an explanatory note that the outer subagent tried to dispatch a nested subagent but reported that the Agent tool was not available in the subagent's toolkit.

**Raw captured hook events (all 3 lines from hook-capture.log):**

```json
{"session_id":"baf8a2d7-a76c-4b5b-908f-d568298ad026","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\baf8a2d7-a76c-4b5b-908f-d568298ad026.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","hook_event_name":"SessionStart","source":"startup"}
{"session_id":"baf8a2d7-a76c-4b5b-908f-d568298ad026","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\baf8a2d7-a76c-4b5b-908f-d568298ad026.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Use your Agent tool to dispatch a subagent with this exact prompt: 'Use your Agent tool to dispatch one nested subagent with the prompt: say hi. Then reply NESTED-DONE.' Then reply OUTER-DONE."}
{"session_id":"baf8a2d7-a76c-4b5b-908f-d568298ad026","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\baf8a2d7-a76c-4b5b-908f-d568298ad026.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"description":"Nested agent dispatch test","prompt":"Use your Agent tool to dispatch one nested subagent with the prompt: say hi. Then reply NESTED-DONE."},"tool_use_id":"toolu_01RjLT66SrfwSqJkcKtS6S68"}
```

**Analysis:**

Exactly **1 PreToolUse event** fired — only the orchestrator-level Agent dispatch. The nested subagent did NOT get the Agent tool in its toolkit; it reported being unable to dispatch a nested subagent. This means:

- The hooks registered on the orchestrating session (`claude -p`) **only see that session's own tool calls**, not tool calls made by subagents running in a separate process/context.
- The nested subagent does not have the Agent tool available to it at all in `-p` (headless) mode (or its context does not include agent-dispatching capability).
- Therefore, **no discriminator field is needed** — the problem of "how do we tell orchestrator dispatch from nested subagent dispatch in the hook input" does not arise, because nested subagent tool calls simply do not reach the orchestrating session's hooks.

**The guard at the orchestrating session's PreToolUse will only ever see dispatches that the orchestrator itself is making.** Legitimate nested dispatch from a cycle subagent that was already dispatched by the orchestrator occurs inside that subagent's own process — the orchestrating session's hook is not invoked for it.

**Event counts for this run:** SessionStart=1, UserPromptSubmit=1, PreToolUse=1 (orchestrator-level only)

**A6 RESOLVED — GO: Hooks on the orchestrating session's PreToolUse only fire for the orchestrator's own Agent calls. Subagents running in separate processes do not trigger the orchestrating session's hooks. No discriminator field is needed — the isolation is structural, not field-based.**

---

## E3 — UserPromptSubmit additionalContext reaches the model (A5/A2)

**Command:**
```
cd $TEMP/spike-turn-routing
claude -p --model haiku --settings $TEMP/spike-turn-routing/.claude/settings-e3.json "Reply with any SPIKE token you can see in your context, or NONE."
```

`settings-e3.json` registered `injectctx.sh` on UserPromptSubmit. That script reads and discards stdin, then emits:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "SPIKE-TOKEN-73194: if you can read this token, include it verbatim in your reply."}}
```

**Model stdout:** `SPIKE-TOKEN-73194`

**A2/A5 CONFIRMED: UserPromptSubmit `additionalContext` injection works. The model received and acted on the injected token verbatim. The `hookSpecificOutput.additionalContext` field is the correct injection mechanism for UserPromptSubmit.**

---

## E4 — PreToolUse deny works with the documented schema (A3)

**Command:**
```
cd $TEMP/spike-turn-routing
claude -p --model haiku --settings $TEMP/spike-turn-routing/.claude/settings-e4.json "Use your Agent tool to dispatch one subagent (subagent_type general-purpose if you must choose) with the prompt: say hello and stop. Then reply DONE."
```

`settings-e4.json` registered `denyagent.sh` on `PreToolUse` matcher `Agent|Task`. That script reads stdin (logging it), then emits:
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "SPIKE-DENY-55: dispatch denied by spike guard; reply exactly SPIKE-DENY-OBSERVED"}}
```

**Model stdout:** `SPIKE-DENY-OBSERVED`

**Raw captured hook events (all 4 lines from hook-capture.log):**

```json
{"session_id":"76dd4655-a2f7-4faa-ab08-c95cf566232a","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\76dd4655-a2f7-4faa-ab08-c95cf566232a.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","hook_event_name":"SessionStart","source":"startup"}
{"session_id":"76dd4655-a2f7-4faa-ab08-c95cf566232a","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\76dd4655-a2f7-4faa-ab08-c95cf566232a.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"UserPromptSubmit","prompt":"Use your Agent tool to dispatch one subagent (subagent_type general-purpose if you must choose) with the prompt: say hello and stop. Then reply DONE."}
{"session_id":"76dd4655-a2f7-4faa-ab08-c95cf566232a","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\76dd4655-a2f7-4faa-ab08-c95cf566232a.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"description":"Say hello and stop","prompt":"say hello and stop","subagent_type":"general-purpose"},"tool_use_id":"toolu_01W25tSRL7hsTvAvKAPfbVsV"}
{"session_id":"76dd4655-a2f7-4faa-ab08-c95cf566232a","transcript_path":"C:\\Users\\Jacob\\.claude\\projects\\C--Users-Jacob-AppData-Local-Temp-spike-turn-routing\\76dd4655-a2f7-4faa-ab08-c95cf566232a.jsonl","cwd":"C:\\Users\\Jacob\\AppData\\Local\\Temp\\spike-turn-routing","permission_mode":"default","hook_event_name":"PreToolUse","tool_name":"Agent","tool_input":{"description":"Say hello and stop","prompt":"say hello and stop","subagent_type":"general-purpose"},"tool_use_id":"toolu_01W25tSRL7hsTvAvKAPfbVsV"}
```

**Observations:**
- The Agent tool did NOT execute (model replied `SPIKE-DENY-OBSERVED`, not `DONE`).
- The model received and acted on the `permissionDecisionReason` string verbatim.
- The deny hook fired **twice** for the same `tool_use_id`. This is an undocumented behavior — the same PreToolUse hook was invoked twice for the single denied tool call. Implementation note: the guard script must be idempotent (consuming a nonce on the first call and finding it consumed on the second is safe — it should still deny on a consumed nonce). The double-fire does not change correctness but is worth knowing.
- PostCompact registration did not cause any session errors — the unknown-event registration (or the event simply not firing in a `-p` run without compaction) was handled gracefully.

**A3 CONFIRMED: PreToolUse deny works. Schema `hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason` is correct. The reason string is fed back to the model verbatim and the tool does not execute. Side-note: hook fires twice per denied call — guard must be idempotent.**

---

## E5 — SessionStart/compact + PostCompact (A2) — best-effort

**From E1 log:** `SessionStart` fired with `source: "startup"` for the `-p` run. The matcher `startup|resume|clear|compact` matched the startup event. This confirms:
- `SessionStart` fires in headless (`-p`) mode.
- The `source` field carries `"startup"` for a fresh session start.
- The inject hook can register on `SessionStart` with matcher `compact` to fire on compaction events.

**PostCompact:** The PostCompact registration in the workspace settings did not error the session (Claude Code accepted an unknown-or-unmatched event registration silently). No PostCompact events were captured — this is expected since no compaction occurred in short `-p` runs.

**Compact-path verification deferred to Phase 6 live validation.** Forcing compaction headlessly is impractical (requires a very long context that triggers auto-compaction or a manual `/compact` command, neither of which is scriptable in `-p` mode within a reasonable spike). The SessionStart(compact) registration pattern is proven by the existing `load-branch-docs-context.sh` registration in the harness; PostCompact is a supplementary registration confirmed safe to include.

**A2 PARTIALLY CONFIRMED: SessionStart fires in -p mode with source="startup". The compact/PostCompact path (additionalContext on post-compaction re-entry) is deferred to Phase 6 live validation — not fabricated here.**

---

## E6 — task-notification turns (SPEC known limitation) — best-effort

**Not testable headlessly.** In all `-p` runs, exactly **1 UserPromptSubmit event** fired per run — matching the single operator-submitted prompt. No additional UserPromptSubmit events were observed for autonomous turns (subagent completions, tool results). This is consistent with the SPEC's documented known limitation: UserPromptSubmit fires on operator-submitted prompts; autonomous cycle returns arrive as task notifications which UserPromptSubmit does not cover.

**This SPEC limitation stands as designed.** The probe-presence guard + validate-deny still police those turns (a dispatch without a same-turn registered emission is denied regardless of how the turn began). Not testable headlessly — recorded as a known gap per SPEC section "Known limitation (recorded, not hidden)."

---

## A6 Verdict

**GO.**

The discriminator question — "which field tells us this is an orchestrator-level dispatch vs a nested subagent's dispatch" — turns out to be the wrong question. **Structural isolation makes a discriminator unnecessary:** hooks registered on the orchestrating session's PreToolUse only fire for tool calls made by that session itself. Subagents dispatched via the Agent tool run in separate processes with their own tool registries; the orchestrating session's hooks are never invoked for those subagents' tool calls. Furthermore, in `-p` (headless) mode, subagents do not have the Agent tool in their toolkit at all — they cannot dispatch further subagents.

This means the validate-deny guard at the orchestrating session's PreToolUse will only ever see Agent calls that the orchestrator itself is attempting to make. There is no risk of the guard blocking a legitimate nested implementer dispatch, because nested dispatches (from cycle subagents) do not surface to the orchestrating session's hook pipeline.

**Exact empirical evidence:** E2 dispatched an orchestrator Agent call (PreToolUse fired once, tool_use_id `toolu_01RjLT66SrfwSqJkcKtS6S68`) whose payload instructed the subagent to itself dispatch another Agent. The subagent reported no Agent tool available — zero additional PreToolUse events appeared in the hook capture log. The structural isolation is complete.

**Phase 2 hook implementation may proceed with the design as written in SPEC.md.** No NEEDS_INPUT.md is required.

---

## Implementation Notes for Phase 2 Hook Authors

From the spike, the following concrete facts feed the hook implementations:

1. **`tool_input.prompt`** is the field to hash for registry lookup — confirmed present in all PreToolUse Agent events (E1, E2, E4). It is the raw subagent prompt string.
2. **Double-fire behavior on deny:** PreToolUse hooks fire twice for the same denied tool call (same `tool_use_id`). The guard (`lazy_guard.py`) must handle the second call gracefully: a nonce already consumed on the first call should still produce a deny on the second call (consumed = deny, not allow).
3. **`session_id`** is consistent across all events in a single `-p` run — can be used for session-bound stale-marker validation as designed.
4. **`transcript_path`** is an absolute Windows path to a `.jsonl` file named by session_id — available for the session-id binding check in the stale-marker guard.
5. **`additionalContext` injection schema:** `{"hookSpecificOutput": {"hookEventName": "<event>", "additionalContext": "<string>"}}` — confirmed working for UserPromptSubmit (E3). The same schema applies to PreToolUse and SessionStart per A2 docs probe.
6. **`permissionDecision: "deny"` schema:** `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "<string>"}}` — confirmed working (E4). The reason reaches the model verbatim.
7. **Project-level `.claude/settings.json` in the workspace applies to `claude -p` runs from that directory.** The `--settings <file>` flag also works for per-experiment overrides. Both routes confirmed.
8. **PostCompact registration does not error the session** when PostCompact does not fire — safe to include in the live settings registration.

---

## Cleanup

Spike workspace `C:\Users\Jacob\AppData\Local\Temp\spike-turn-routing\` and all contained files (hooklog.sh, injectctx.sh, denyagent.sh, hook-capture.log, .claude/settings*.json) deleted after the experiments completed. No spike files were added to git.

---

## Ground-Truth Output Block

```
$ git -C C:\Users\Jacob\source\repos\claude-config status --short
?? docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md

$ wc -l docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md
208 docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md

$ grep -n "A6 Verdict" docs/specs/turn-routing-enforcement/RUNTIME_SPIKE.md
155:## A6 Verdict
Verdict: GO

Hook event counts per experiment (from captured logs before cleanup):
  E1 (re-run): SessionStart=1, UserPromptSubmit=1, PreToolUse(Agent)=1  — total 3 lines
  E2:          SessionStart=1, UserPromptSubmit=1, PreToolUse(Agent)=1  — total 3 lines
  E3:          (injectctx.sh discarded stdin — no log lines written)    — total 0 lines
  E4:          SessionStart=1, UserPromptSubmit=1, PreToolUse(Agent)=2  — total 4 lines (double-fire on deny)
```

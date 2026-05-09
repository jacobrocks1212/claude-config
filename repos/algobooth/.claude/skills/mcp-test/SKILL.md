---
name: mcp-test
description: Start tauri:dev, wait for MCP readiness, then dispatch a Sonnet subagent with a persisted test scenario
argument-hint: <test description — e.g. "test mix knob crossfade" or "verify queue fire sequence">
---

# MCP Test

Start the AlgoBooth dev server if not already running, wait for full MCP readiness, then dispatch a Sonnet subagent to execute a persisted test scenario via the MCP HTTP API.

---

## Step 1: Parse Arguments

Extract the user's test description from `$ARGUMENTS`. If empty, use **AskUserQuestion**: "What should the MCP test subagent do?"

---

## Step 2: Health Check and Server Start

```bash
curl -s http://localhost:3333/health
```

- **200 OK** → Server running. Set `server_was_running = true`. Skip to Step 3.
- **Connection refused** → Not running. Start it now:

  1. Kill any stale process:
     ```bash
     taskkill /F /IM algobooth.exe 2>$null
     ```

  2. Start dev server in background using `run_in_background: true`:
     ```bash
     npm run tauri:dev
     ```

  3. Set `server_was_running = false` — health and readiness checks will happen in Step 4 (after scenario resolution).

**Key optimization:** Do NOT wait for the server here. Proceed immediately to Step 3 (scenario resolution). The dev server takes 3-5 minutes to compile and boot — use that time for scenario research and drafting. The readiness check in Step 4 will block only if the server isn't ready by then.

---

## Step 3: Resolve or Create Test Scenario

Do this **while the dev server is booting** (if it was started in Step 2). Scenario resolution is pure I/O — reading docs, possibly writing a new file — and overlaps perfectly with the 3-5 minute compile+boot time.

Test scenarios live in `docs/testing/mcp-tests/`. Read `docs/testing/mcp-tests/CLAUDE.md` for the format spec.

### 3a. Check for existing scenario

Scan `docs/testing/mcp-tests/*.md` (excluding CLAUDE.md) for a file that matches the user's `$ARGUMENTS`. Match by:
- File name similarity (e.g., user says "mix knob crossfade" → `mix-knob-crossfade.md`)
- Description section content

If found → read it and confirm with the user: "Found existing test scenario: `docs/testing/mcp-tests/{name}.md`. Run it as-is, or update?"
- **Run as-is** → proceed to Step 4 with this file path
- **Update** → edit the file, then proceed

### 3b. Create new scenario (if none exists)

#### Research existing docs first

Before writing anything, search for guidance and similar patterns:

1. Read `docs/testing/mcp-tests/CLAUDE.md` — the format spec and conventions for test scenarios
2. Read ALL existing scenario files in `docs/testing/mcp-tests/*.md` (excluding CLAUDE.md) — look for:
   - **Reusable patterns** — setup sequences, assertion styles, watermark polling approaches that the new scenario should follow for consistency
   - **Partial overlap** — an existing scenario may already cover some of the behavior being tested; avoid duplicating assertions and cross-reference instead
   - **Conventions** — dB thresholds, wait durations, phase structure, and naming patterns established by prior scenarios
3. Check `docs/MCP_USAGE_GUIDE.md` — specifically the **Audio Architecture** and **Tool Reference** sections for the tools and parameters needed
4. Check `docs/features/` for any spec related to the behavior under test — the scenario's assertions should align with the spec's defined behavior, not ad-hoc assumptions

Use findings from this research to inform the scenario structure, assertion thresholds, and phase organization.

#### Draft the scenario

Translate the user's `$ARGUMENTS` into a test scenario file:

1. Map each user instruction to specific MCP tool calls with exact parameters
2. Replace UI concepts with MCP-native terms:
   - "set active channel to X" → `POST /tools/set_active_editor {"editor": "X"}` for UI focus, plus `update_code` or `load_test_tone` with `channel: "X"` for audio routing
   - "switch channel" → `POST /tools/switch_editor` (toggles between main/cue)
   - "enable playback" → `POST /tools/play`
   - "set mixer to 50%" → `POST /tools/set_mix_knob {"value": N}` (0=Cue, 100=Master)
   - "verify audio is audible" → check `get_audio_silence_diagnostics` (with optional `channel` param) or `get_evaluation_result`
   - "press keyboard shortcut" → `POST /tools/simulate_keyboard {"key": "Space", "modifiers": ["ctrl"]}`
   - "wait for event X" → `POST /tools/wait_for_event {"pattern": "X", "timeout_ms": 5000}`
   - "check if animation finished" → `GET /tools/get_animation_state` (wait for `animating: false`)
   - "verify toast notification" → `GET /tools/get_toast_history`
   - "check focus state" → `GET /tools/get_focus_state`
   - "verify code evaluation" → `GET /tools/get_evaluation_result`
   - "capture specific element" → `POST /tools/capture_screenshot {"selector": ".performance-strip"}` (see selector reference below)
3. **Use validated CSS selectors** for `capture_screenshot`. The following selectors are tested and produce correctly-scoped captures:

   | Selector | Captures |
   |----------|----------|
   | `.performance-strip` | Full transport bar (play/stop, mixer, navigation) |
   | `.document-editor` | Code editor area |
   | `.cm-editor` | CodeMirror editor only (code content) |
   | `.custom-header-bar` | Top header/title bar |
   | `.studio-main-row` | Editor + RHS panels row |
   | `.studio-mode-layout` | Full layout minus header bar |
   | `.strip-zone--transport` | Play/stop button + status indicator |
   | `.strip-zone--mixer` | Cue/Master crossfader |
   | `.strip-zone--navigation` | F1-F4 panel toggle buttons |
   | `.rhs-panel-area` | Right-hand side panels (empty/tiny when collapsed) |

   **WARNING:** `.transport-bar` does NOT exist — use `.performance-strip` for the transport bar. If a selector is not found in the DOM, `capture_screenshot` silently falls back to full-page capture (same size as no selector). Always verify targeted captures are smaller than full-page.

4. Write positive AND negative assertions with step references and evidence expectations
5. Write the file to `docs/testing/mcp-tests/{kebab-case-name}.md` following the format in the CLAUDE.md
6. Show the user the file path and a brief summary before proceeding

---

## Step 4: Wait for App Readiness

Now that the scenario is ready, ensure the dev server is fully initialized before dispatching the test subagent.

**If `server_was_running` is true** (from Step 2), skip the health poll and go directly to the readiness check.

**If `server_was_running` is false**, first poll `/health` with exponential backoff using the Monitor tool:

```bash
for delay in 5 10 20 30 30 30 30 30 30 30 30 30 30 30 30; do
  curl -s http://localhost:3333/health && echo "READY" && break
  echo "Waiting ${delay}s..."
  sleep $delay
done
```

Total timeout: 450s. If health never responds → report BLOCKING failure and stop.

**Then, for all cases**, run the app readiness check. The `/health` endpoint responds as soon as the Rust HTTP server starts, but Vue stores and MCP event listeners initialize later.

Poll with exponential backoff: 10s, 15s, 20s, 30s, 45s, 60s (6 retries, ~180s max).

**Key detail:** Do NOT filter by `evt_filter: "store_"` — store telemetry events only fire when store *actions* run (user interaction), not during initialization. Use **unfiltered** events and check `total_lines` instead, which counts all session events including `session_start`, `log_info`, etc. that fire during Vue/Pinia boot.

Use this exact script (handles JSON with or without spaces around colons):

```bash
for delay in 10 15 20 30 45 60; do
  result=$(curl -s -X POST http://localhost:3333/tools/get_session_events \
    -H "Content-Type: application/json" -d '{"limit": 1}' 2>/dev/null)
  total=$(echo "$result" | grep -oE '"total_lines" *: *[0-9]+' | grep -oE '[0-9]+')
  if [ -n "$total" ] && [ "$total" -gt 10 ]; then
    echo "READY: total_lines=$total"
    exit 0
  fi
  echo "Not ready (total_lines=${total:-null}), waiting ${delay}s..."
  sleep $delay
done
echo "TIMEOUT"
exit 1
```

**Ready** when `total_lines > 10` — this means the session logger is running and Vue has initialized enough to emit log events.

If all 6 retries exhausted → report BLOCKING failure and stop.

---

## Step 5: Dispatch Sonnet Subagent

Launch a **Sonnet** subagent via the Agent tool (`model: "sonnet"`). The prompt references files by path — do NOT inline their content.

Replace `{SCENARIO_PATH}` with the test scenario file path from Step 3.

```
You are testing the AlgoBooth Tauri desktop app via its MCP HTTP API on localhost:3333.
The app is already running and fully initialized.

## Reference Documentation (read these files)

- docs/MCP_USAGE_GUIDE.md — Audio architecture, complete tool reference, endpoint formats
- docs/testing/MCP_INTEGRATION_GUIDE.md — Test scenarios, event validation, session log analysis, confidence scoring

## Test Scenario (read this file)

{SCENARIO_PATH}

This file contains: a description of what is being tested, numbered MCP-native instructions to execute, and assertion tables (positive and negative) to validate against.

## Session Telemetry

- **POST /tools/get_session_events** — read session.jsonl events. Params: `limit`, `offset`, `since_line` (watermark polling), `evt_filter` (prefix filter like "audio_", "store_")
- **GET /tools/get_session_meta** — session metadata including `session_dir` path
- **POST /tools/wait_for_event** — block until a matching event appears in session.jsonl. Params: `pattern` (substring match), `timeout_ms` (default 5000, max 30000). Returns `{ matched, event, elapsed_ms }`. Use this instead of manual watermark polling loops.
- **Analysis:** `npx tsx scripts/analyze-session.ts <session_dir>/` — generates structured summary.md

## Observation Tools

- **GET /tools/get_toast_history** — session-scoped ring buffer (max 100) of toast/notification events with message, type, shown_at_us, dismissed_at_us
- **GET /tools/get_focus_state** — query document.activeElement: `{ selector, component, focusable }`
- **GET /tools/get_scroll_state** — scroll position of queue panel and pattern list containers
- **GET /tools/get_animation_state** — `{ animating: boolean, active_transitions: string[] }` via Web Animations API
- **GET /tools/get_evaluation_result** — last Strudel evaluation result: `{ status: "success"|"error"|"pending"|"none", error_message, voices_triggered, evaluated_at_us }`

## Control Tools

- **POST /tools/simulate_keyboard** — dispatch a synthetic KeyboardEvent: `{ key: "Space", modifiers: ["ctrl"] }`. Returns `{ dispatched: boolean, action_fired: string|null }` where `action_fired` is the matched keyboard binding action name. Use this instead of store mutations for keyboard-driven interactions.
- **POST /tools/capture_screenshot** — supports optional `{ selector: ".css-selector" }` for targeted DOM element capture. When selector is provided, only that element is captured (smaller PNG, faster). When omitted, captures full page. **Validated selectors:** `.performance-strip` (transport bar), `.document-editor` (code editor), `.cm-editor` (CodeMirror only), `.custom-header-bar` (top bar), `.studio-main-row` (editor + RHS panels), `.strip-zone--transport` (play/stop), `.strip-zone--mixer` (crossfader), `.strip-zone--navigation` (F1-F4 buttons), `.rhs-panel-area` (RHS panels — empty when collapsed). WARNING: `.transport-bar` does NOT exist — use `.performance-strip`.

## Setup (run FIRST, before the test scenario)

1. POST /tools/stop
2. POST /tools/update_code {"channel": "main", "code": ""}
3. POST /tools/update_code {"channel": "cue", "code": ""}
4. POST /tools/queue_clear
5. Wait 2s
5.5. Verify clear succeeded: GET /tools/get_audio_silence_diagnostics — confirm `mainCode` and `cueCode` are both empty strings. If either contains code, retry steps 2-3 and re-verify. If still not empty after retry, report BLOCKING failure.
6. Capture event baseline: POST /tools/get_session_events {"limit": 1} → note total_lines

## Execution Protocol

1. Run Setup above
2. Execute the Instructions from the test scenario file, step by step
3. **Audio verification gate:** After any step that starts playback with a pattern, wait 3-5s then call `GET /tools/get_audio_silence_diagnostics`. If `v2VoicesTriggered == 0`, the pattern is not producing audio — report BLOCKING failure with the diagnostics response and stop. Do not proceed with measurements on silent audio.
4. **Code evaluation verification:** After `update_code`, check the `evaluation_result` field in the response (status: "success", "error", or "pending"). If "pending", poll `GET /tools/get_evaluation_result` (up to 3 retries, 500ms apart) until status resolves. Use `get_evaluation_result` for async evaluation checks between steps.
5. **Animation settling:** Before any screenshot after a UI-mutating action, call `GET /tools/get_animation_state`. If `animating: true`, wait 500ms and retry (up to 3 retries). Only capture screenshots when animations have settled.
6. **Visual verification:** After UI-mutating actions (view mode change, panel toggle, layout switch), wait for animation settling (step 5), then `POST /tools/capture_screenshot`. For targeted verification, use `{ selector: ".performance-strip" }` to capture specific components instead of full-page screenshots. Read the returned PNG path to visually verify the expected UI state.
7. **Event-driven waiting:** Instead of fixed `sleep` delays after actions, prefer `POST /tools/wait_for_event {"pattern": "event_name", "timeout_ms": 5000}` to block until the expected event appears in the session log. This is faster and more reliable than fixed delays.
8. After each phase, collect events using `wait_for_event` or the watermark polling pattern
9. Validate every assertion (positive, negative, AND visual) from the scenario's Assertions tables
10. Score each assertion: VERIFIED (100%), PARTIAL (50-75%), CONTRADICTED (0%)

## Rules

- Use curl via Bash: GET for read-only, POST with -H "Content-Type: application/json" -d '{...}' for mutations
- **Prefer `wait_for_event` over fixed delays** — instead of `sleep 3`, use `POST /tools/wait_for_event {"pattern": "audio_rms_batch", "timeout_ms": 5000}` to wait precisely until the expected event appears. Fall back to fixed delays only when no specific event is expected.
- **Prefer `get_evaluation_result` over voice count checks** — after `update_code`, check the inline `evaluation_result` or poll `get_evaluation_result` for definitive success/error/pending status instead of relying solely on `v2VoicesTriggered`.
- **Prefer targeted screenshots** — use `capture_screenshot` with `{ selector: ".performance-strip" }` to capture specific UI regions. Full-page screenshots are noisy; targeted captures are smaller and focus on the area under test.
- **Check animation state before screenshots** — call `get_animation_state` and wait for `animating: false` before capturing, to avoid mid-transition artifacts.
- **Use `simulate_keyboard` for keyboard-driven tests** — dispatches real KeyboardEvents through the same path as user keypresses, resolves the matching keyboard binding action.
- **Screenshots:** Use the Read tool on the returned PNG path — Claude Code can natively view PNG images. Describe what you see (layout, panels, controls) in the Evidence column.
- Screenshot limitations: WebGL/canvas elements (waveforms, Hydra) render blank. Focus on verifying layout structure, panel visibility, and control state.
- **Channel-scoped diagnostics:** Use `get_audio_silence_diagnostics` with `{ channel: "main" }` or `{ channel: "cue" }` to check per-channel audio state instead of always checking the global response.
- Do NOT read or search source code files (src/, src-tauri/) — use only the reference docs and MCP API responses
- Do NOT modify any source code
- If an operation fails, report what happened rather than retrying silently
- **`v2VoicesTriggered` is cumulative:** This counter is global (main+cue combined) and never resets during a session. A nonzero value does NOT mean audio is currently playing — only that voices were triggered at some point. Use `queueLen > 0` from `get_audio_silence_diagnostics` as the reliable "sidecar has active patterns" check instead.

## Report Format

### Assertion Results
| # | Type | Assertion | Result | Evidence |
|---|------|-----------|--------|----------|
| P1 | Positive | ... | VERIFIED / CONTRADICTED | Raw event data or dB values |
| N1 | Negative | ... | VERIFIED / CONTRADICTED | ... |
| V1 | Visual | ... | VERIFIED / CONTRADICTED | Screenshot observation |

### Overall Score: X% of assertions verified

### Coverage Gaps (MANDATORY)
For any aspect you could NOT fully test:
| # | Behavior | Reason | Workaround | Suggested Fix |
|---|----------|--------|------------|---------------|
| 1 | ... | ... | ... | ... |

If no gaps: "No coverage gaps — all behaviors verified via MCP."
```

---

## Step 6: Report Results

After the subagent completes, summarize its findings to the user:

1. **Test results** — assertion pass/fail with evidence, overall score
2. **Coverage gaps** — present the gaps table prominently; these need manual testing or new MCP tooling
3. **Blocking issues** — any failures or errors that prevented testing
4. **Scenario file** — remind the user which file was used/created: `docs/testing/mcp-tests/{name}.md`

If coverage gaps suggest missing MCP tools that would be straightforward to add, note them as candidates for a follow-up `/spec` or `/add-phase`.

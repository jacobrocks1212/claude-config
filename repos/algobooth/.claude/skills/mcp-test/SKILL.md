---
name: mcp-test
description: Start tauri:dev, wait for MCP readiness, then dispatch a Sonnet subagent with a persisted test scenario
argument-hint: <test description — e.g. "test mix knob crossfade" or "verify queue fire sequence" or "tier:0">
---

# MCP Test

Start the AlgoBooth dev server if not already running, wait for full MCP readiness, then dispatch a Sonnet subagent to execute a persisted test scenario via the MCP HTTP API.

---

## Step 1: Parse Arguments

Extract the user's test description from `$ARGUMENTS`. If empty, use **AskUserQuestion**: "What should the MCP test subagent do?"

### Step 1.5: Tier Batch Mode

If `$ARGUMENTS` matches the pattern `tier:N` (e.g., `tier:0`, `tier:2`), activate **Tier Batch Mode**:

1. Look up the scenario list for that tier from the table below.
2. Execute each scenario sequentially: run Steps 2–6.5 for each, calling `POST /tools/reset_state` between scenarios to ensure a clean slate.
3. After all scenarios complete, report a per-scenario summary table:

   | Scenario | Score | Blocking Issues | Coverage Gaps |
   |----------|-------|-----------------|---------------|
   | infra-health-readiness | X% | — | — |
   | ... | ... | ... | ... |

4. **Stop here** — do not continue to Step 2 as a single-scenario run.

#### Tier → Scenario Mapping

| Tier | Scenarios |
|------|-----------|
| 0 | infra-health-readiness, infra-session-telemetry, infra-screenshot-capture, infra-state-reset |
| 1 | play-stop-lifecycle, test-tone-loading, code-evaluation, tempo-control |
| 2 | channel-muting, mix-knob-crossfade, dual-channel-isolation |
| 3 | pattern-bank-crud, code-history, pattern-import-export |
| 4 | queue-crud, queue-fire-sequence, queue-timed-advance, cue-promote-transition, transition-modes, cancel-transition |
| 5 | view-mode-switching, hud-controls, editor-switching, panel-visibility, island-controls, master-editor-lock |
| 6 | setlist-crud, setlist-round-trip, settings-persistence, notification-toasts |
| 7 | invalid-code-recovery, empty-channel-handling, rapid-state-changes |
| 8 | bug-007-require-crypto-telemetry |

Each scenario name corresponds to the file `docs/testing/mcp-tests/{scenario-name}.md`.

---

## Step 2: Server Lifecycle — Kill, Start, and Verify

**CRITICAL: Test isolation requires a fresh server.** The Strudel sidecar maintains internal state (cycle counter, pattern scheduling, PLL clock) that persists across `reset_state` calls. A sidecar that connected in a prior session may report `is_connected: true` but have a stuck `current_cycle: 0.0`, producing zero voices. The ONLY reliable fix is a full app restart.

### When to restart (ALWAYS do this)

**Default behavior: always kill and restart.** Prior sessions leave the sidecar in an unpredictable state. `reset_state` clears frontend/store state but does NOT restart the sidecar process or reset its internal cycle counter.

```bash
npx kill-port 3333
```

`npx kill-port 3333` is the reliable way to stop the server. Do NOT use `taskkill /F /IM algobooth.exe` — the `tauri dev` watcher may respawn the process before you can restart cleanly.

After killing, start fresh:

```bash
npm run tauri:dev
```

Use `run_in_background: true` for this command. Set `server_was_running = false`. Health and readiness checks happen in Step 4.

**Key optimization:** Do NOT wait for the server here. Proceed immediately to Step 2.5 (scenario resolution). The dev server takes 3-5 minutes to compile and boot — use that time for scenario research and drafting. The readiness check in Step 4 will block only if the server isn't ready by then.

### Exception: skip restart ONLY when ALL of these are true

1. Health check returns 200: `curl -s http://localhost:3333/health`
2. Sidecar is connected AND cycling: `curl -s http://localhost:3333/tools/get_sidecar_status` shows `is_connected: true`
3. No Rust code has been modified since the server started (no new tools, no registration changes, no feature flag changes)
4. The user explicitly says the server is in a known-good state (e.g., "server is already running, just run the test")

If ALL four conditions are met → set `server_was_running = true` and skip to Step 2.5.

If ANY condition fails → kill and restart as described above.

### Step 2.5: Verify New Tools Are Registered (MANDATORY after code changes)

If the test scenario targets **recently added or modified MCP tools** (e.g., the user says "validate the new tools we just added"), the server may be running stale code from before those tools were compiled. This step catches that.

Wait for health to respond first (poll if needed), then:

1. Check the expected tool count or probe a specific new tool:
   ```bash
   curl -s http://localhost:3333/info | python -c "import sys,json; print(len(json.load(sys.stdin)['tools']))"
   ```
   Or probe the specific new tool directly:
   ```bash
   curl -s -X POST http://localhost:3333/tools/<new_tool_name> -H "Content-Type: application/json" -d '{}'
   ```

2. **If the tool returns 404 or the tool count is lower than expected** → the server is running stale code. Restart it:
   ```bash
   npx kill-port 3333
   ```
   Then re-run `npm run tauri:dev` in background and wait for health + readiness in Step 4.

3. **If the tool responds (even with a parameter validation error)** → the server has the latest code. Proceed.

**Why this matters:** MCP HTTP routes are registered at compile time via `inventory::submit!` macros in `registrations.rs`. Hot-reload only covers frontend (Vue/TypeScript) changes. Any Rust-side change (new tools, modified registrations, feature flag changes) requires a full Rust recompile and server restart. The `#[tool]` attribute (rmcp) and the `register_tool_*!` macro (inventory) are both required — missing the inventory registration causes 404s at runtime even though the code compiles clean.

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

#### Verify behavioral assumptions via exploration (MANDATORY for new scenarios)

Before writing any assertions, **probe the actual MCP tool behavior** by running a lightweight exploration against the live app. This prevents writing assertions based on assumed semantics that don't match reality (e.g., assuming an undo stack records "new code" when it actually records "old code").

1. Identify the key MCP tools the scenario will test
2. For each tool, run a minimal round-trip via `curl` to capture:
   - **Response shape** — exact field names, types, nesting (e.g., `new_code` vs `restored_code`, `remaining_history` vs `count`)
   - **Behavioral semantics** — what the tool actually does (e.g., does `undo_code` return the popped entry or the new current state? does history record the replaced code or the new code?)
   - **Side effects** — does the operation trigger session events? which event names? synchronous or deferred?
   - **Timing** — does the state change appear immediately in subsequent reads, or is there a propagation delay?
3. Record the findings as notes to inform assertion design
4. If any finding contradicts your initial assumptions from the docs, adjust the scenario design BEFORE writing it — do NOT write assertions based on doc assumptions alone

**Example exploration for code history:**
```bash
# Check baseline
curl -s -X POST http://localhost:3333/tools/get_code_history -H "Content-Type: application/json" -d '{"channel":"main"}'
# Set code and check what history records
curl -s -X POST http://localhost:3333/tools/update_code -H "Content-Type: application/json" -d '{"channel":"main","code":"test_a"}'
sleep 1
curl -s -X POST http://localhost:3333/tools/update_code -H "Content-Type: application/json" -d '{"channel":"main","code":"test_b"}'
sleep 1
curl -s -X POST http://localhost:3333/tools/get_code_history -H "Content-Type: application/json" -d '{"channel":"main"}'
# → Discovery: latest history entry is "test_a" (replaced code), NOT "test_b" (new code)
# Clean up
curl -s -X POST http://localhost:3333/tools/update_code -H "Content-Type: application/json" -d '{"channel":"main","code":""}'
```

This step requires the app to be running. If the app is not yet ready (Step 2 started it), wait for health + readiness first (Step 4), then come back and run exploration before drafting the scenario.

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

## Step 3.5: Validate Scenario File

Before dispatching the subagent, verify the resolved scenario file contains all required sections. This prevents a wasted subagent run on a malformed file.

Read the scenario file and check for the presence of **all** of the following sections:

| Required Section | What to look for |
|-----------------|-----------------|
| Description | A `## Description` heading with non-empty content |
| Prerequisites | A `## Prerequisites` heading with non-empty content |
| Instructions | A `## Instructions` heading with numbered steps |
| Assertions — Positive | A `### Positive` (or `## Assertions` containing a Positive sub-table) with at least one row |
| Assertions — Negative | A `### Negative` sub-table with at least one row |

**If all sections are present** → proceed to Step 4.

**If any section is missing or empty** → stop immediately and report the validation error to the user:

```
SCENARIO VALIDATION FAILED: docs/testing/mcp-tests/{name}.md

Missing or empty sections:
  - Prerequisites
  - Assertions (Negative)

Fix the scenario file and re-run /mcp-test.
```

Do NOT dispatch the subagent until validation passes.

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

### Sidecar Readiness Gate

After `total_lines > 10` is confirmed, check that the Strudel sidecar has booted and connected:

```bash
curl -s http://localhost:3333/tools/get_sidecar_status
```

Verify the response contains `"is_connected": true`.

- **Connected** → proceed to the audio pipeline smoke test below.
- **Not connected** (e.g., `is_connected: false`, connection refused, or missing field) → report BLOCKED:

  ```
  BLOCKED: Sidecar not connected.
  get_sidecar_status response: {raw response here}

  The Strudel sidecar must be connected before running tests that touch the audio pipeline.
  Wait for the sidecar to boot and re-run /mcp-test, or check for sidecar startup errors in the dev console.
  ```

  Do NOT dispatch the subagent.

### Audio Pipeline Smoke Test (MANDATORY)

**This catches the "stale sidecar" problem.** A sidecar may report `is_connected: true` but have a stuck cycle counter, producing zero voices. Verify the full pipeline works end-to-end before dispatching the subagent.

1. Load a test tone and play:
   ```bash
   curl -s -X POST http://localhost:3333/tools/load_test_tone -H "Content-Type: application/json" -d '{"channel":"main"}'
   sleep 2
   curl -s -X POST http://localhost:3333/tools/play -H "Content-Type: application/json" -d '{}'
   sleep 5
   ```

2. Check audio is active:
   ```bash
   curl -s http://localhost:3333/tools/get_audio_silence_diagnostics
   ```
   Verify `queueLen > 0` (sidecar has active patterns). If `queueLen == 0` AND `v2VoicesTriggered == 0`, the audio pipeline is not working.

3. **If pipeline is working** (`queueLen > 0`) → clean up and proceed to Step 5:
   ```bash
   curl -s -X POST http://localhost:3333/tools/stop -H "Content-Type: application/json" -d '{}'
   curl -s -X POST http://localhost:3333/tools/update_code -H "Content-Type: application/json" -d '{"channel":"main","code":""}'
   ```

4. **If pipeline is dead** (`queueLen == 0`, `v2VoicesTriggered == 0`) → the sidecar is stuck. Kill and restart:
   ```bash
   npx kill-port 3333
   ```
   Re-run `npm run tauri:dev` in background, wait for full readiness (re-do Step 4 from the top). If the pipeline fails a second time, report BLOCKING failure — do NOT dispatch the subagent on a dead pipeline.

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

1. POST /tools/reset_state
2. POST /tools/stop
3. POST /tools/unlock_master_editor
4. POST /tools/update_code {"channel": "main", "code": ""}
5. POST /tools/update_code {"channel": "cue", "code": ""}
6. POST /tools/queue_clear
7. Wait 2s
7.5. Verify clear succeeded: GET /tools/get_audio_silence_diagnostics — confirm `mainCode` and `cueCode` are both empty strings. If either contains code, retry steps 4-5 and re-verify. If still not empty after retry, report BLOCKING failure.
8. Capture event baseline: POST /tools/get_session_events {"limit": 1} → note total_lines

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
11. **Audio Quality Contracts** — after all behavioral assertions pass, execute any Audio Quality Contracts found in the scenario's SPEC.md (see below)

## Audio Quality Contracts

After completing all behavioral assertions (steps 1-10 above), check whether the test scenario's source SPEC.md contains a `## Audio Quality Contracts` section. If it does, execute each contract row as a structured audio quality assertion.

### Contract Table Format

Each contract row in the SPEC.md has these columns:

| Column | Description |
|--------|-------------|
| ID | Unique contract identifier (e.g., `AQ-EQ-01`) |
| Condition | What to set up via MCP tools (Strudel pattern, controls) |
| Channel | Which audio bus to capture: `main`, `cue`, or `mix` |
| Tool | Which audio quality tool to call (e.g., `audio_pitch`, `audio_filter`) |
| Measurement | Which field in the tool's JSON response to assert on |
| Assert | Expected value — range `[380, 420]`, threshold `< 0.5`, or boolean `== true` |

### Execution Protocol

For each contract row:

1. **Set up Condition** — evaluate the Strudel pattern via `POST /tools/update_code` or `POST /tools/load_test_tone`, adjust controls as needed
2. **Start playback** — `POST /tools/play` if not already playing
3. **Wait 2-3s** for audio to stabilize (use `sleep 3` or `wait_for_event` with `audio_rms_batch`)
4. **Capture audio** — `POST /tools/audio_capture { "channel": "<Channel>" }`
5. **Run measurement** — call the specified Tool with `{ "capture_id": "<id>" }` plus any required params from the Condition column
6. **Assert** — extract the Measurement field from the response and compare against the Assert value
7. **Release capture** — `POST /tools/audio_release { "capture_id": "<id>" }`
8. **Report** — `AQ-EQ-01: PASS` or `AQ-EQ-01: FAIL — cutoff_hz was 482 Hz, expected [380, 420]`

### Available Audio Quality Tools

| Tool | Description | Key Response Fields |
|------|-------------|-------------------|
| `audio_capture` | Capture audio snapshot → returns `capture_id` | `capture_id`, `peak_dbfs`, `rms_dbfs` |
| `audio_release` | Release a capture to free memory | `released` |
| `audio_artifact_scan` | Detect clicks, clipping, dropouts, DC drift | `clean`, `clicks.count`, `clipping.clip_count` |
| `audio_pitch` | Measure pitch via FFT + zero-crossing | `dominant_frequency_hz`, `confidence`, `cents_error` |
| `audio_spectrum` | Spectral analysis | `spectral_centroid_hz`, `noise_floor_dbfs`, `peak_dbfs` |
| `audio_filter` | Filter characterization | `cutoff_hz`, `rolloff_db_per_octave` |
| `audio_distortion` | THD, aliasing, IMD | `thd_percent`, `aliasing_ratio_db`, `aliasing_audible` |
| `audio_lufs` | Integrated loudness (LUFS) | `integrated_lufs` |
| `audio_reverb` | RT60, EDT, C80, echo density | `rt60_seconds`, `edt_seconds`, `c80_db`, `ned_score` |
| `audio_stereo` | Stereo analysis | `balance`, `mid_side_ratio_db`, `mean_correlation` |
| `audio_dynamics` | Attack/release timing | `attack_ms`, `release_ms`, `compressor_attack_ms` |
| `audio_modulation` | LFO/tremolo detection | `detected`, `rate_hz`, `depth` |

### Contract Results in Report

Append a separate section to the report for Audio Quality Contracts:

```
### Audio Quality Contracts
| ID | Tool | Measurement | Expected | Actual | Result |
|----|------|-------------|----------|--------|--------|
| AQ-EQ-01 | audio_filter | cutoff_hz | [380, 420] | 397.2 | PASS |
| AQ-EQ-02 | audio_filter | rolloff_db_per_octave | [-14, -10] | -11.8 | PASS |
```

If no `## Audio Quality Contracts` section exists in the SPEC.md, skip this step entirely — contracts are opt-in.

## Rules

- Use curl via Bash: GET for read-only, POST with -H "Content-Type: application/json" -d '{...}' for mutations
- **Realistic pacing between actions** — insert a brief `sleep 1` between sequential MCP actions to simulate real user interaction timing. Without pacing, actions fire back-to-back faster than any human could operate, causing `wait_for_event` to miss synchronous events and failing to reflect real-world usage patterns. Use `wait_for_event` when you know which event to expect; use `sleep 1` as a minimum between other sequential actions. Always insert `sleep 0.5` *before* `wait_for_event` if the triggering action fires events synchronously.
- **Prefer `wait_for_event` over long fixed delays** — instead of `sleep 3`, use `POST /tools/wait_for_event {"pattern": "audio_rms_batch", "timeout_ms": 5000}` to wait precisely until the expected event appears. Fall back to fixed delays only when no specific event is expected.
- **Prefer `get_evaluation_result` over voice count checks** — after `update_code`, check the inline `evaluation_result` or poll `get_evaluation_result` for definitive success/error/pending status instead of relying solely on `v2VoicesTriggered`.
- **Prefer targeted screenshots** — use `capture_screenshot` with `{ selector: ".performance-strip" }` to capture specific UI regions. Full-page screenshots are noisy; targeted captures are smaller and focus on the area under test.
- **Check animation state before screenshots** — call `get_animation_state` and wait for `animating: false` before capturing, to avoid mid-transition artifacts.
- **Use `simulate_keyboard` for keyboard-driven tests** — dispatches real KeyboardEvents through the same path as user keypresses, resolves the matching keyboard binding action.
- **Screenshots:** Use the Read tool on the returned PNG path — Claude Code can natively view PNG images. Describe what you see (layout, panels, controls) in the Evidence column. **IMPORTANT:** If the Read tool fails on a screenshot path (e.g., URL parsing error, file not found), do NOT retry — record the screenshot path as evidence with a note "screenshot captured but could not be read" and continue. Never let a screenshot read failure block the test.
- Screenshot limitations: WebGL/canvas elements (waveforms, Hydra) render blank. Focus on verifying layout structure, panel visibility, and control state.
- **Channel switching before code/tone changes:** Before calling `update_code` or `load_test_tone` targeting a channel different from the current active editor, ALWAYS call `set_active_editor` first. This ensures the Channel Indicator UI reflects the switch — just like a real user would select the Cue or Master tab before typing code. The active editor starts as `"master"` by default after setup.
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

---

## Step 6.5: Persist Results and Diff Against Prior Run

After summarizing results to the user (Step 6), write a result file and compare against any prior run.

### 6.5a. Determine the result file path

- **Scenario name:** derive from the scenario file name without extension (e.g., `mix-knob-crossfade` from `mix-knob-crossfade.md`).
- **Date:** today's date in `YYYY-MM-DD` format.
- **Path:** `docs/testing/mcp-tests/results/{scenario-name}-{YYYY-MM-DD}.md`

### 6.5b. Check for a prior result

Scan `docs/testing/mcp-tests/results/` for any file matching `{scenario-name}-*.md` (any date). Sort by filename descending and take the most recent one (if any).

### 6.5c. Write the result file

Write the result file with the following structure:

```markdown
# {Scenario Name} — {YYYY-MM-DD}

## Scenario
File: docs/testing/mcp-tests/{scenario-name}.md

## Assertion Results
| # | Type | Assertion | Result | Evidence |
|---|------|-----------|--------|----------|
| P1 | Positive | ... | VERIFIED / CONTRADICTED | ... |
| N1 | Negative | ... | VERIFIED / CONTRADICTED | ... |

## Overall Coverage
**Score:** X% of assertions verified

## Blocking Issues
{List any blocking issues found, or "None"}

## Coverage Gaps
{Copy the coverage gaps table from the subagent report, or "No coverage gaps"}

## Diff vs Prior Run
{See 6.5d below}
```

### 6.5d. Diff against prior run

**If a prior result file exists:**

Compare the Assertion Results tables row-by-row (match by assertion `#` and `Type`):

- **Regressions** — assertions that were `VERIFIED` in the prior run but are now `CONTRADICTED` or missing.
- **Improvements** — assertions that were `CONTRADICTED` (or missing) in the prior run but are now `VERIFIED`.

Append a diff section to the result file:

```markdown
## Diff vs Prior Run
Prior result: docs/testing/mcp-tests/results/{scenario-name}-{prior-date}.md

### Regressions (previously passing, now failing)
| # | Type | Assertion |
|---|------|-----------|
| P2 | Positive | ... |

### Improvements (previously failing, now passing)
| # | Type | Assertion |
|---|------|-----------|
| N1 | Negative | ... |

_If no regressions:_ "No regressions — all previously passing assertions still pass."
_If no improvements:_ "No improvements vs prior run."
```

**If no prior result exists:**

```markdown
## Diff vs Prior Run
First run — no prior result to compare.
```

### 6.5e. Report to user

After writing the file, tell the user:

```
Results saved to: docs/testing/mcp-tests/results/{scenario-name}-{YYYY-MM-DD}.md
{If regressions found}: ⚠ {N} regression(s) detected vs prior run ({prior-date}).
{If improvements found}: ✓ {N} improvement(s) vs prior run ({prior-date}).
{If first run}: First run recorded.
```

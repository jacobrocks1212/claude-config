## MCP Integration Test (BLOCKING — DO NOT SKIP)

After quality gates pass, validate observable runtime behavior via MCP HTTP tools and session log analysis. This step catches "unit tests pass but system doesn't work" failures.

### Applicability Rule (MANDATORY — read before deciding to skip)

**Check the phase's PHASES.md section for an `MCP Integration Test Assertions` block.** This is the primary signal:

- **Assertions block exists** → This step is **MANDATORY and BLOCKING**. Execute the full protocol below. Do NOT skip, defer, or treat as optional.
- **No assertions block** → Check whether the phase produces runtime-observable changes (see checklist below). If yes, write assertions yourself and proceed. If no, skip.

**Runtime-observable changes checklist** (only used when no assertions block exists):
- [ ] New events that should appear in `session.jsonl`
- [ ] New/modified MCP tool responses
- [ ] Changed audio pipeline behavior
- [ ] New UI state changes that emit telemetry
- [ ] Modified startup/shutdown sequence

If ALL unchecked AND no assertions block in PHASES.md → skip this step. **Otherwise, proceed.**

### Protocol

#### 2. Write Test Assertions

Based on the phase's SPEC.md references and deliverables, write explicit assertions for the test agent. Format:

```
ASSERTIONS:
1. After [trigger action], session events MUST contain event with evt="{expected_event}" and ctx containing {expected_fields}
2. GET /tools/{tool_name} MUST return {expected_shape}
3. After [sequence of actions], {condition} MUST be true
```

Include both **positive** and **negative** assertions:
- Positive: "X MUST exist after Y" (core behavior works)
- Negative: "Z MUST NOT exist" or "error count MUST be 0" (no regressions introduced)
- Regression: "Prior phase's behavior MUST still work" (e.g., store telemetry from P2 unbroken after P3)

**Assertion Scoping Rule (MANDATORY):** Before finalizing assertions, verify each one tests behavior implemented IN THIS PHASE, not behavior planned for a later phase. For each assertion, answer: "Which phase's deliverables make this assertion pass?" If the answer is a phase that hasn't been implemented yet, REMOVE the assertion or reclassify it as "expected absent — confirms correct scoping." Common mistakes:
- Testing getter filtering before the filtering phase is implemented
- Testing EventBus→session routing before the routing phase
- Assuming all MCP tool actions flow through the same code path (some use Tauri events, not invoke)

**MCP vs UI Code Path Rule (MANDATORY):** MCP HTTP tools often take DIFFERENT code paths than manual UI interactions. Before writing each assertion, determine which code path the MCP trigger uses:
- MCP `/tools/play` and `/tools/stop` → route to sidecar IPC directly, bypass Pinia store actions → `store_dj_play_success` will NOT fire
- MCP `/tools/mute_channel` → routes through Pinia store → `store_dj_setMainMuted_success` WILL fire
- MCP `/tools/update_code` → calls store directly, bypasses editor composable → `edit_pattern_debounced` will NOT fire
- MCP cannot trigger OS-level key events or DOM clicks → `keyboard_*_fired` and `click_*` events will NOT appear
- Rust-originated events (`audio_rt`, `rust_be`) use `SessionWriter` which omits `trace: null` via `skip_serializing_if` → do NOT assert `trace` field on these

For each assertion, annotate: `(MCP-triggerable)` or `(requires manual testing)`. Only include MCP-triggerable assertions in the subagent protocol. List manual-testing assertions separately as informational.

Read the PHASES.md implementation notes for the current phase to understand what was ACTUALLY built (not just what was planned).

#### 3. Dispatch MCP Test Subagent

Launch a Sonnet subagent with:
- The MCP Integration Testing Guide (`docs/testing/MCP_INTEGRATION_GUIDE.md`)
- The explicit assertions from step 2
- Instructions to: check readiness → baseline events → execute scenarios → poll for new events → run analysis → validate → report

**Subagent prompt template:**
```
You are testing a Tauri desktop app's runtime behavior via its MCP HTTP API (port 3333) and session logs.

GUIDE: Read docs/testing/MCP_INTEGRATION_GUIDE.md for full tool catalog and validation rules.

ASSERTIONS TO VALIDATE:
[paste assertions from step 2]

PROTOCOL:
1. Health check: GET http://localhost:3333/health (EXPONENTIAL BACKOFF — Rust compile can take 3-5 min)
   - If not running: execute `npm run tauri:dev` in background
   - Poll /health with exponential backoff: 5s, 10s, 20s, 30s, then 30s intervals — up to 450s total
   - If Rust code changed since last build: kill existing process, rebuild triggers automatically
   - Approach: use a bash loop with increasing sleep: `for delay in 5 10 20 30 30 30 30 30 30 30 30 30 30 30 30; do curl -s .../health && break; sleep $delay; done`
2. App readiness check (CRITICAL — do NOT skip, EXPONENTIAL BACKOFF):
   - POST /tools/get_session_events {"limit": 5, "evt_filter": "store_"}
   - If zero store events: the Vue frontend is not yet initialized
   - Retry with exponential backoff: 10s, 20s, 30s, 45s, 60s, 60s — up to 6 retries (~225s max)
   - Health endpoint responds before Vue mounts — MCP event listeners activate 30-165s after health passes
   - Alternative readiness probe: POST /tools/play → wait 3s → POST /tools/stop → check for tauri_* or store_* events. If none appear, continue backoff retries.
3. Capture event baseline: POST /tools/get_session_events {"limit": 1} — note total_lines as your watermark
4. Execute test scenarios via HTTP calls to localhost:3333/tools/{tool_name}
5. Poll for new events (EXPONENTIAL BACKOFF — DO NOT use a single fixed-delay check):
   - Wait 5s initial delay
   - POST /tools/get_session_events {"since_line": <baseline_total_lines>, "limit": 500}
   - If fewer events than expected: backoff retry at 5s, 10s, 15s, 20s, 25s — up to 5 retries
   - Note: readiness-probe events (step 2) count as valid test evidence if they match assertions
6. Get session metadata: GET /tools/get_session_meta — note session_dir path
7. Run analysis script for supplementary validation:
   npx tsx scripts/analyze-session.ts <session_dir>/
   Read the generated summary.md — anomaly detection catches issues raw event scanning misses
8. Validate each assertion against collected events + analysis output
9. Score confidence per rubric: VERIFIED (100%), PARTIAL (50-75%), UNVERIFIED (0-25%), CONTRADICTED (0%)
10. Report in structured format

IMPORTANT:
- Do NOT modify any source code
- If the app fails to start after 90s, report as blocking issue and exit
- If assertions fail, report exactly what was expected vs. what was found
- Include raw evidence (event JSON from get_session_events) for each assertion
- Use since_line to isolate YOUR test's events from pre-existing session noise
- Use the analysis script summary.md as supplementary evidence
- If a readiness-probe action (play/stop) produces events matching assertions, those count — do not discard them
- NEVER cache session paths — re-resolve via GET /tools/get_session_meta before every session log read. App restarts create new session directories; a stale path means you're reading the wrong session.

REPORT FORMAT:
Include these sections in your report:
1. **Assertions table** — each assertion with result, confidence, and raw evidence
2. **Analysis script findings** — key insights from summary.md
3. **Scoping validation** — confirm which assertions were correctly scoped to this phase vs. would have tested later phases; note any EventBus-only behavior that can't be verified until its routing phase is implemented
4. **Overall score** — percentage of assertions VERIFIED
5. **Blocking issues** — any CONTRADICTED assertions or errors
```

#### 4. Evaluate Results

| Overall Score | Action |
|--------------|--------|
| All VERIFIED | Proceed to next batch/phase |
| Any PARTIAL | Investigate — may be timing issue (retry) or partial implementation (fix) |
| Any CONTRADICTED | BLOCKING — dispatch fix subagent, then re-test |
| Any UNVERIFIED | If critical to spec → BLOCKING. If nice-to-have → note and proceed |

#### 5. Fix Failures (if needed)

If assertions fail:
1. Dispatch a fix subagent with: the failing assertion, the actual evidence, and the relevant source files
2. After fix, re-run the MCP test subagent with the same assertions
3. Maximum 2 fix attempts. If still failing → escalate via Blocking Issue Protocol

### Confidence Scoring Rubric

| Score | Meaning | Evidence Required |
|-------|---------|-------------------|
| 100% VERIFIED | Event/response matches spec exactly | Exact event line from session.jsonl or exact JSON response |
| 75% PARTIAL | Event exists but schema partially matches | Event present, some fields missing or different |
| 50% PLAUSIBLE | Code exists and compiles but no runtime evidence | Source code inspection only |
| 25% UNLIKELY | Code exists but evidence suggests it's not active | Feature flag off, module not mounted, etc. |
| 0% CONTRADICTED | Evidence directly contradicts expectation | Expected event absent, or wrong values found |

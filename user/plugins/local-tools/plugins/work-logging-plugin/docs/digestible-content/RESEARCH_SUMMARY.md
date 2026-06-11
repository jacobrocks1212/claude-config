# Digestible Content — Research Summary

> Key findings from Gemini Deep Research and their impact on the baseline spec.

**Research source:** [RESEARCH.md](./RESEARCH.md)
**Date:** 2026-05-04

---

## Key Findings

### 1. ntfy.sh Clipboard Actions: Platform Asymmetry

**Finding:** The ntfy.sh `copy` action type works natively on Android (v1.23.0+) but is **blocked on Windows browsers** due to DOM interaction security models. Web Push notifications cannot programmatically access the clipboard in the background.

**Impact:** Windows requires the **ntfy-desktop** Electron app for full clipboard support. This app uses ntfy-toast (fork of SnoreToast) to interface directly with the Windows Action Center, bypassing browser restrictions. A single ntfy payload works cross-platform — the `copy` action definition is platform-agnostic; interpretation depends on the receiving client.

**Decision:** Require ntfy-desktop on Windows. Android uses the official ntfy app. One payload, two functional clients.

### 2. Claude Code Session Bootstrapping

**Finding:** `claude "prompt"` (without `-p`) starts an interactive REPL, processes the prompt, and stays open for follow-up. `claude "/interview-study rate-limiting"` correctly invokes the skill and enters interactive mode. The `CLAUDE_CONFIG_DIR` environment variable controls which config directory is loaded.

**Impact:** Confirms our wrapper script approach. The `study` command sets `CLAUDE_CONFIG_DIR=~/.claude-personal` and runs `claude "/interview-study <slug>"`. No pre-created sessions needed — context is fresh every time.

**Decision:** Reuse `~/.claude-personal` profile (all personal skills/MCPs available). The study skill itself handles pedagogical context.

### 3. PostToolUse Hook Data Schema

**Finding:** The PostToolUse hook receives a comprehensive JSON payload via **stdin** containing `tool_input` (exact arguments passed to the MCP tool) and `tool_response`. The hook also gets `tool_name` for filtering.

**Impact:** The background script can extract the work log entry directly from stdin — no disk re-read, no race conditions. The hook script filters on `tool_name == "work_log_append"` and passes the full `tool_input` to the evaluation script.

**Decision:** Hook reads stdin JSON, extracts `tool_input`, pipes it to the background Python script.

### 4. Windows Process Detachment

**Finding:** Spawning background processes from Claude Code hooks on Windows Git Bash causes a visible `conhost.exe` console window flash. This is a known issue (anthropics/claude-code#51867) caused by Node.js `child_process.spawn()` behavior on Win32. Neither `nohup` nor `&` prevents it.

**Impact:** Must use **`pythonw.exe`** (windowless Python binary) with `cmd //c start` to fully detach without visual disruption.

**Recommended spawning pattern:**
```bash
cmd //c start "" "pythonw.exe" "/path/to/scripts/evaluate_and_notify.py"
```

**Decision:** Hook uses `pythonw.exe` + `cmd //c start` for zero-flash background execution. Stdin data must be passed via temp file since `cmd //c start` doesn't support pipe input.

### 5. Microlearning Science Validation

**Finding:** Research confirms that:
- Brief, contextual learning interventions at the moment of relevance leverage the Self-Reference Effect (SRE) for superior encoding
- Notifications at **task boundaries** (post-completion) align with cognitive troughs — perceived as relevant suggestions rather than interruptions
- Mobile microlearning with user-activity-based contextual cues outperforms fixed-schedule reminders

**Impact:** Validates the PostToolUse trigger timing. The architecture accurately targets the natural trough in the developer's cognitive load cycle.

### 6. Notification Fatigue

**Finding:** Research recommends a debounce mechanism. Burst notifications during intense coding sessions trigger fatigue. However, the risk is mitigated when the binary threshold is highly selective and notifications are perceived as "flexible suggestions that can be safely deferred."

**Impact:** We're keeping no rate limit but acknowledging the risk. The binary haiku threshold must remain exceptionally stringent. If fatigue emerges in practice, a 1-hour debounce is the recommended first mitigation.

---

## Spec Adjustments from Research

| Area | Baseline | Adjusted |
|------|----------|----------|
| Windows notification client | Generic "ntfy.sh" | **ntfy-desktop** (Electron app) required |
| Process spawning | Generic "detached background process" | **`pythonw.exe` + `cmd //c start`** pattern |
| Hook data access | "Extract from tool call" | **Read `tool_input` from stdin JSON** |
| Study session command | TBD | **`claude "/interview-study <slug>"`** via wrapper |
| Study profile | TBD | **Reuse `~/.claude-personal`** (no dedicated profile) |
| Rate limiting | No limit | **No limit** (kept, with debounce as known fallback) |
| Context passing | TBD | **Deferred** — wrapper passes slug to skill; skill loads context via MCP tools at runtime |

## Ideas Adopted from Research

- **`pythonw.exe` spawning pattern** — eliminates console window flash on Windows
- **stdin-based data extraction** — avoids disk race conditions
- **Single payload, dual client** — ntfy `copy` action is platform-agnostic
- **Task boundary timing** — validated by cognitive research as optimal intervention point

## Risks Identified

1. **ntfy-desktop maintenance** — Electron app is community-maintained (Aetherinox). If abandoned, fallback to PowerShell BurntToast.
2. **Haiku threshold drift** — Binary yes/no without numeric scoring means threshold consistency depends on prompt engineering. Monitor false positive rate.
3. **Stdin-to-temp-file bridge** — Since `cmd //c start` doesn't support piping, the hook must write stdin to a temp file and pass the path. Adds a cleanup step.
4. **Notification fatigue during heavy sessions** — Accepted risk. First mitigation if needed: 1-hour debounce in the Python script.

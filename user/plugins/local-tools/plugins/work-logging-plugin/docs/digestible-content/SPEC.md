# Digestible Content — Feature Specification

> Passive study surfacing: automatically surface relevant interview prep artifacts as you work, delivered as non-blocking notifications with one-tap study session entry.

**Status:** Final Draft
**Priority:** P1
**Last updated:** 2026-05-04
**Depends on:** work-logging-plugin v2 (work log, features, KB, vault generation)

---

## Executive Summary

The interview prep system captures work, synthesizes features, correlates to KB topics, and generates an Obsidian vault — but all of it is on-demand. The engineer must actively choose to study. Digestible Content closes this gap by **passively surfacing learning opportunities at the moment they're most relevant**: right after completing work that demonstrates an interview-worthy concept.

A PostToolUse hook fires after every `work_log_append` call. The hook reads the work log entry from stdin (the hook receives the full `tool_input` JSON), writes it to a temp file, and spawns `scripts/evaluate_and_notify.py` as a fully detached background process using `pythonw.exe` (to avoid the Windows `conhost.exe` console flash). The script invokes headless Claude (haiku) with a single prompt containing the work entry and compact KB index, asking for a binary surface/don't-surface decision. If the work strongly correlates to a KB topic, a rich notification is sent via ntfy.sh — delivered to both **ntfy-desktop** on Windows 11 (native toast with clipboard action) and the **ntfy Android app** on Pixel 10.

The notification includes a personalized 1-2 sentence summary of how the work demonstrates the concept, plus a "Study" action button that copies a `study /interview-study <slug>` command to the clipboard. The `study` wrapper script sets `CLAUDE_CONFIG_DIR=~/.claude-personal` and launches an interactive Claude (Opus) session with the study skill pre-invoked. Vault updates only happen during these active study sessions or manual vault regeneration — never as a side-effect of passive surfacing.

The system is designed to be **zero-friction and non-blocking** — notifications arrive at task boundaries (when cognitive load is naturally lower), most are glanced at and dismissed, and study sessions are entered only when the engineer chooses. Research on microlearning and the Self-Reference Effect confirms that contextual cues tied to self-generated work produce superior encoding and retention compared to scheduled study.

---

## Data Flow

```
Skill session completes
       │
       ▼
work_log_append (MCP tool)
       │
       ▼
PostToolUse hook fires
       │
       ├─ Reads tool_input from stdin JSON
       ├─ Filters: tool_name == "work_log_append"
       ├─ Writes tool_input to temp file (e.g., /tmp/eval-<uuid>.json)
       ├─ Spawns: cmd //c start "" pythonw.exe scripts/evaluate_and_notify.py <temp-file>
       └─ Exits immediately (hook returns success, active session unblocked)
                                    │
                                    ▼
                     scripts/evaluate_and_notify.py (detached, windowless)
                                    │
                                    ├─ Reads work log entry from temp file
                                    ├─ Loads compact KB index (154 topics: slug, name, domain, description)
                                    ├─ Invokes: claude -p <prompt> --model haiku --output-format json
                                    │   Prompt: work entry + KB index → "Does this directly demonstrate
                                    │   any topic? Return strongest match + summary, or null."
                                    ├─ Parses response: {"surface": bool, "slug": str, "domain": str,
                                    │                    "summary": str}
                                    │
                                    ├── surface == false → cleanup temp file, exit silently
                                    │
                                    └── surface == true → POST to ntfy.sh topic
                                              │
                                              ├─ Title: 📚 {topic_name}
                                              ├─ Body: personalized 1-2 sentence summary
                                              ├─ Action: copy "study /interview-study {slug}"
                                              ├─ Tags: domain (e.g., system-design)
                                              └─ Cleanup temp file, exit
                                                        │
                                                        ▼
                                              Delivered to:
                                              ├─ Windows 11: ntfy-desktop → native toast + clipboard
                                              └─ Pixel 10: ntfy app → notification + clipboard

                                    Later, when user is ready:
                                              │
                                              ▼
                                    Paste & run: study /interview-study <slug>
                                              │
                                              ├─ ~/.local/bin/study wrapper:
                                              │   export CLAUDE_CONFIG_DIR=~/.claude-personal
                                              │   exec claude --model claude-opus-4-6 "$@"
                                              │
                                              ▼
                                    Interactive Claude session (Opus)
                                    /interview-study loads KB topic + correlated features + work log
                                    Socratic Q&A, story elaboration, vault updates via managed blocks
```

---

## Technical Design

### 1. PostToolUse Hook

**Registration:** Plugin hook configuration (`.claude-plugin/hooks.json` or `settings.json`).

**Hook script:** `hooks/evaluate-surfacing.sh`

```bash
#!/usr/bin/env bash
# PostToolUse hook for work_log_append
# Reads tool_input from stdin, spawns background evaluation, exits immediately.

# Read stdin JSON payload
INPUT=$(cat)

# Filter: only fire for work_log_append
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null)
if [[ "$TOOL_NAME" != *"work_log_append"* ]]; then
  exit 0
fi

# Extract tool_input and write to temp file
TEMP_FILE=$(mktemp /tmp/eval-XXXXXX.json)
echo "$INPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
json.dump(data.get('tool_input', {}), open('$TEMP_FILE', 'w'))
" 2>/dev/null

# Spawn detached background evaluation (windowless on Windows)
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)/scripts"
cmd //c start "" pythonw.exe "$SCRIPT_DIR/evaluate_and_notify.py" "$TEMP_FILE" &>/dev/null

exit 0
```

**Key details:**
- Hook reads full `tool_input` from stdin JSON — no disk re-read needed
- Uses `pythonw.exe` + `cmd //c start` to prevent `conhost.exe` console flash (Windows-specific)
- Temp file bridges stdin data to the detached process (since `cmd //c start` doesn't support pipes)
- Hook exits immediately — active Claude Code session is never blocked

### 2. Background Evaluation Script (`scripts/evaluate_and_notify.py`)

**Input:** Path to temp JSON file containing the work log entry's `tool_input`.

**Process:**
1. Read and parse the temp file
2. Load compact KB index from `~/.interview-prep/knowledge-bank/` using `KnowledgeBank` class
3. Construct evaluation prompt with work entry + KB index
4. Invoke `claude -p - --model haiku --output-format json` via subprocess
5. Parse response: `{"surface": true/false, "slug": "...", "domain": "...", "summary": "..."}`
6. If `surface == true`: POST to ntfy.sh with title, body, and `copy` action
7. Cleanup temp file
8. Log outcome to `~/.interview-prep/surfacing-log.jsonl` (append-only, for diagnostics)

**Error handling:**
- All external calls (haiku, ntfy) wrapped in try/except
- Failures logged to `~/.interview-prep/surfacing-errors.log`
- Never affects the active Claude Code session (fully detached process)

**Haiku evaluation prompt:**
```
You are an expert software engineering interview coach.

A developer just completed this work:
- Title: {title}
- Summary: {summary}
- Project: {project}
- Technologies: {technologies}
- Patterns: {patterns}

Here are 154 interview preparation topics across 4 domains:
{compact_kb_index}

Does this work DIRECTLY demonstrate any of these topics? Only surface if the
work shows intentional, deep engagement with the topic's core principles —
not tangential usage of a related technology.

Respond with JSON only:
- If strong match: {"surface": true, "slug": "<topic-slug>", "domain": "<domain>", "summary": "<1-2 sentences explaining how THIS work demonstrates the topic, written in second person>"}
- If no strong match: {"surface": false}
```

### 3. ntfy.sh Notification

**Delivery:** Single HTTP POST to ntfy.sh topic. The `copy` action is platform-agnostic — interpreted correctly by both ntfy-desktop (Windows) and the ntfy Android app.

**Payload example:**
```bash
curl -s \
  -H "Title: 📚 Rate Limiting" \
  -H "Tags: system-design" \
  -H "Actions: copy, Study, study /interview-study rate-limiting" \
  -H "Authorization: Bearer tk_<token>" \
  -d "Your Cognito Pay spec uses token bucket rate limiting for multi-provider payment routing — a classic approach to protecting downstream services from burst traffic." \
  https://ntfy.sh/<topic>
```

**Clients:**
| Platform | Client | Clipboard Support |
|----------|--------|-------------------|
| Windows 11 | ntfy-desktop (Electron, system tray) | Full — native toast action |
| Android (Pixel 10) | ntfy app (Play Store) | Full — v1.23.0+ |

**Security:** Either self-hosted ntfy (Docker, `auth-default-access: deny-all`) or hosted ntfy.sh with reserved topic + access token. Access tokens are rotatable and avoid hardcoding passwords.

### 4. Study Wrapper Script (`~/.local/bin/study`)

```bash
#!/usr/bin/env bash
# Wrapper for entering interview study sessions from surfacing notifications.
# Uses the personal Claude profile (not work profile).
export CLAUDE_CONFIG_DIR="$HOME/.claude-personal"
exec claude --dangerously-skip-permissions --model claude-opus-4-6 "$@"
```

**Clipboard command:** `study /interview-study rate-limiting`

This starts an interactive Claude (Opus) session that:
1. Invokes `/interview-study rate-limiting`
2. The skill calls `get_study_context` to load KB entry + correlated features + work log
3. Presents the study brief and enters Socratic Q&A mode
4. All personal skills, settings, and MCP servers are available

**Note:** The `--dangerously-skip-permissions` flag mirrors the existing `claude-personal` alias. The wrapper uses `~/.claude-personal` config dir (not `~/.claude`) to load personal settings, not work settings.

### 5. Surfacing Log (`~/.interview-prep/surfacing-log.jsonl`)

Append-only diagnostic log. Records every evaluation outcome (surfaced or not) for monitoring threshold quality.

```json
{
  "timestamp": "2026-05-04T18:32:00Z",
  "work_title": "Cognito Pay — Payment Processing Integration",
  "work_project": "cognito-forms",
  "surfaced": true,
  "topic_slug": "rate-limiting",
  "topic_domain": "system-design",
  "summary": "Your Cognito Pay spec uses token bucket rate limiting..."
}
```

---

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trigger mechanism | PostToolUse hook on `work_log_append` | Zero-latency, fires exactly when work is logged. Validated by research: task boundaries are optimal interruption points |
| Notification transport | ntfy.sh | Free, open-source, cross-platform pub/sub. Single payload works on both Android and Windows clients |
| Windows client | ntfy-desktop (Electron) | Required for clipboard action support — browser-based Web Push blocks clipboard access (DOM security model) |
| Android client | ntfy app (Play Store) | Native `copy` action support since v1.23.0 |
| Evaluation model | Headless Claude (haiku) | Cheap, fast. Single CLI call with compact KB index (~3K tokens). Only study sessions use Opus |
| Decision threshold | Binary yes/no | Haiku decides directly. Prompt encodes selectivity: "only surface if work DIRECTLY demonstrates the topic's core principles" |
| Rate limiting | None | Trust the binary threshold. Research acknowledges fatigue risk during bursts; 1-hour debounce is the pre-identified mitigation if needed |
| Process spawning | `pythonw.exe` + `cmd //c start` | Prevents `conhost.exe` console flash on Windows (known Claude Code issue #51867) |
| Hook data access | Read `tool_input` from stdin JSON | PostToolUse hook receives full tool arguments via stdin. Avoids disk re-read race conditions |
| Stdin bridge | Temp file | `cmd //c start` doesn't support pipe input. Hook writes temp file, script reads and cleans up |
| Study profile | Reuse `~/.claude-personal` | All personal skills/MCPs/settings available. Study skill handles pedagogical context itself |
| Wrapper script | `~/.local/bin/study` | Expands `claude-personal` alias for non-interactive contexts. Clipboard gets a clean `study /interview-study <slug>` |
| Context passing | Slug-based (skill loads context at runtime) | The study skill calls `get_study_context` with the topic slug. All context is loaded fresh from MCP tools, not baked into the command |
| Scope (v1) | Notification + study entry only | No vault auto-updates from surfacing. Vault changes happen in active study sessions or `/interview-generate` |
| Claude API | None — headless CLI only | Consistent with all interview-prep tooling. Uses subscription via `claude` CLI |

---

## Prerequisites / Setup

1. **ntfy-desktop** installed on Windows 11 (system tray, configured with topic + auth token)
2. **ntfy app** installed on Pixel 10 (configured with same topic + auth token)
3. **ntfy.sh topic** created (self-hosted or hosted with reserved topic + access token)
4. **`~/.local/bin/study`** wrapper script installed and on PATH
5. **`pythonw.exe`** available (ships with standard Python Windows install)

---

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed 4-phase breakdown.

| Phase | Title | Risk |
|-------|-------|------|
| 1 | Evaluation Engine | High — prompt engineering, subprocess parsing |
| 2 | ntfy.sh Client | Medium — HTTP client, action syntax, auth |
| 3 | Hook + CLI Entrypoint | Medium — Windows process spawning, stdin bridging |
| 4 | Study Wrapper + Hardening | Low — wrapper script, diagnostics, error paths |

---

## Non-Goals (v1)

- No vault auto-updates from passive surfacing
- No spaced repetition scheduling from surfacings (SRS stays in Obsidian)
- No notification history/dashboard (surfacing-log.jsonl is diagnostic only)
- No user preference learning (e.g., "show me fewer behavioral topics")
- No multi-topic notifications (max 1 topic per surfacing event)
- No rate limiting (deferred mitigation: 1-hour debounce if fatigue emerges)

---

## Research References

- [RESEARCH.md](./RESEARCH.md) — Full Gemini Deep Research output
- [RESEARCH_SUMMARY.md](./RESEARCH_SUMMARY.md) — Key findings and spec adjustments

Research-driven decisions:
- **`pythonw.exe` spawning** — prevents `conhost.exe` flash (research §4, source: anthropics/claude-code#51867)
- **ntfy-desktop requirement** — browser clipboard blocked by DOM security (research §2, source: ntfy docs)
- **stdin `tool_input` extraction** — hook receives full JSON payload (research §4, source: Claude Code hooks reference)
- **Task boundary timing** — validated by microlearning + SRE research (research §5, sources: IEEE, Frontiers, PMC)
- **`claude "prompt"` interactive bootstrapping** — confirmed by CLI reference (research §3)

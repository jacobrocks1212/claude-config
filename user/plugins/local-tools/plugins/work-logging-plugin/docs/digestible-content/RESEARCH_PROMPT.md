# Digestible Content — Deep Research Prompt

## Research Question

How should a developer-facing passive study system deliver non-blocking, context-rich notifications from a CLI tool (Claude Code) to both Windows desktop and Android, and what are the best mechanisms for bootstrapping a follow-up interactive CLI session with pre-loaded context?

## Context

### System Overview
I have a Claude Code plugin (Python MCP server) that passively captures my engineering work into a structured log. The system synthesizes features, correlates them to a 154-topic knowledge bank (system design, behavioral, OOD, algorithms), and generates an Obsidian vault with domain-specific narratives (ISTART stories, ADRs, etc.).

**The gap:** Everything is on-demand. I must actively choose to study. I want the system to **surface learning opportunities passively** — right after I complete work that demonstrates an interview-worthy concept.

### Decided Architecture
- **Trigger:** A Claude Code PostToolUse hook fires after work is logged, spawning a detached background Python script
- **Evaluation:** Headless Claude CLI (haiku model) evaluates the work against the KB index in a single call, making a binary surface/don't-surface decision
- **Notification:** ntfy.sh delivers a rich summary + "Study" action button to Windows desktop and Android (Pixel 10)
- **Study entry:** The action button copies a CLI command to the clipboard. The user pastes it to start a fresh interactive Claude session (Opus model) with the study context pre-loaded
- **No Claude API:** All Claude interactions are headless CLI (`claude -p`) using my subscription
- **Scope:** Notification + study entry only. No vault auto-updates from passive surfacing.

### Tech Stack
- Plugin: Python 3.12, FastMCP, running as stdio MCP server in Claude Code
- Claude Code: CLI tool with PostToolUse hooks (shell scripts), session continuation support
- Headless Claude: `claude -p "prompt" --model haiku --output-format json` subprocess pattern (already used in this project)
- Platforms: Windows 11 (primary dev machine), Pixel 10 (Android, notifications only)

## Baseline Spec Summary

1. PostToolUse hook on `work_log_append` → spawns detached `scripts/evaluate_and_notify.py`
2. Script loads work log entry + compact KB index → single headless haiku call → binary yes/no
3. If yes: sends ntfy.sh notification with topic name, personalized 1-2 sentence summary, and "Study" clipboard action
4. User pastes `study <slug>` command → starts interactive Claude Code session with `/interview-study` skill and trigger context
5. `~/.local/bin/study` wrapper expands `claude-personal` alias (sets `CLAUDE_CONFIG_DIR`, model preference)

## Research Areas

### 1. ntfy.sh: Notification Delivery & Actions

- **Clipboard actions on Android:** Does ntfy support a "copy to clipboard" action type natively on Android? If not, what's the closest alternative (e.g., `view` action that opens a URL with the command, `broadcast` intent)?
- **Windows toast notifications:** How do ntfy.sh notifications surface on Windows 11? Options include: ntfy desktop app, browser-based web push, PowerShell polling script, or third-party ntfy-windows client. Which approach provides native toast notifications with action buttons?
- **Action button cross-platform:** Can a single ntfy message define actions that work correctly on both Android (ntfy app) and Windows (whatever client is used)? Or do we need platform-conditional logic?
- **Topic security:** What's the recommended approach for securing a private ntfy topic? Token-based auth? Self-hosting vs. hosted ntfy.sh with access tokens?
- **Notification payload limits:** Max body length, title length, and action count for ntfy messages.
- **Alternative transports:** If ntfy.sh proves limiting for the clipboard use case, what alternatives exist? (Pushover, Gotify, Bark, custom FCM, Telegram bot)

### 2. Claude Code: Session Context Injection

- **`claude --resume` and `claude --continue`:** How do these work exactly? Can I pre-create a session with context and give the user a session ID to resume later?
- **Prompt-first sessions:** Can `claude "some initial prompt"` start an interactive session that first processes the prompt then drops into interactive mode? Or does `-p` always mean non-interactive?
- **System prompt injection:** Is there a way to inject a system prompt or context file when starting a Claude Code session? (e.g., `--system-prompt`, `--context-file`, or environment variable)
- **Skill invocation from CLI:** Can a skill be invoked directly from the command line? e.g., `claude '/interview-study rate-limiting'` — does this work, and does it enter interactive mode after the skill completes?
- **MCP tool pre-invocation:** Could the study command pre-invoke an MCP tool to load context before dropping into interactive mode?
- **Session handoff patterns:** Are there established patterns in the Claude Code ecosystem for one process (background evaluator) preparing context that another process (interactive session) consumes?

### 3. PostToolUse Hook: Data Access & Spawning

- **Hook input format:** What data does a Claude Code PostToolUse hook receive? Specifically: does it get the tool's input arguments, the tool's output, both, or just the tool name? This determines whether the hook can extract the work log entry directly or needs to re-read it from disk.
- **Background process spawning:** What's the recommended way for a Claude Code hook (shell script) to spawn a long-running background process that outlives the hook? `nohup`, `start /b`, `disown`, or PowerShell `Start-Process -NoNewWindow`?
- **Hook environment:** Does the hook run in the same shell environment as the user's terminal? (Important for PATH, Python venv activation, etc.)
- **Hook failure handling:** If the background script fails (haiku timeout, ntfy unreachable), how should errors be handled? The active session must never be affected.

### 4. Passive Learning / Microlearning Research

- **Microlearning effectiveness:** What does research say about the effectiveness of brief, contextual learning interventions vs. dedicated study sessions? Is there evidence that a 1-2 sentence notification at the moment of relevance aids retention?
- **Notification fatigue in developer tools:** What's the research on notification frequency thresholds for developer-facing tools? At what point do passive notifications become noise? (We've chosen no rate limiting — is this wise?)
- **Contextual cueing in learning:** The Self-Reference Effect (SRE) underpins our v2 design. Does research support that real-time contextual cues (seeing "your work demonstrates X" right after doing X) enhance SRE encoding compared to delayed review?
- **Spaced surfacing:** Even without formal SRS, is there value in tracking which topics have been surfaced and biasing toward less-seen topics over time? (Currently out of scope but good to understand the research basis.)

### 5. Prior Art & Patterns

- **Developer notification systems:** How do existing tools (GitHub notifications, CI/CD alerts, Dependabot, CodeClimate) handle non-blocking developer notifications? What patterns have succeeded/failed?
- **"Learning while working" tools:** Are there existing tools or products that surface learning content in the context of development work? (e.g., Codacy coaching, SonarQube education, VS Code extensions that teach patterns)
- **CLI-to-notification bridges:** Established patterns for CLI tools sending desktop/mobile notifications. Any OSS projects that do this well?
- **Study session bootstrapping:** How do other tools handle "start a session with pre-loaded context"? Any patterns from Jupyter, tmux, or IDE session restoration that apply?

## Specific Questions

1. Can ntfy.sh action buttons copy arbitrary text to the clipboard on Android? What about Windows?
2. What's the most reliable way to get native Windows 11 toast notifications from ntfy.sh?
3. Does Claude Code support starting an interactive session with a pre-loaded prompt/context (not `-p` non-interactive mode)?
4. What data does a Claude Code PostToolUse hook receive in its stdin/environment?
5. What's the recommended pattern for a shell hook to spawn a detached Python process on Windows (Git Bash)?
6. Is there evidence that micro-notifications at the moment of skill application improve retention compared to batched review?
7. What notification frequency is optimal for developer-facing tools — is "no rate limit" sustainable when the binary threshold is highly selective?
8. Are there existing Claude Code plugins or MCP servers that send external notifications as part of their workflow?
9. What's the security model for ntfy.sh topics — can I prevent others from publishing to my topic?
10. Has anyone built a "learning while coding" notification system before? What worked and what didn't?

## Output Format

Please structure findings as:

1. **Executive Summary** — Key findings in 3-5 bullets
2. **ntfy.sh Deep Dive** — Capabilities, limitations, platform-specific behavior, recommended setup
3. **Claude Code Session Mechanics** — What's possible for context injection, interactive session bootstrapping
4. **Hook Architecture** — Data flow, spawning patterns, error isolation
5. **Learning Science** — Evidence for/against micro-notification learning, recommended frequency
6. **Prior Art** — Existing tools and patterns, lessons learned
7. **Recommendations** — Specific, actionable recommendations for each open question
8. **Risks & Mitigations** — What could go wrong and how to handle it

---
name: gemini
description: USE WHEN the user explicitly asks for Gemini/Google AI or a second opinion from another AI model. Triggers on 'Gemini', 'ask Gemini', 'second opinion'.
---

# Gemini Research Integration

## Overview

Query Gemini models via REST API with persistent session storage. All research is saved to `~/source/repos/research/` for future reference.

**Two backends available:**
1. **REST API** (preferred) - Direct HTTP calls via `gemini-research.py`, zero dependencies, session saving
2. **CLI wrapper** (legacy) - Wraps `gemini` CLI via `gemini.py`, requires CLI installed

## CRITICAL: Always Dispatch as a Task Agent

**NEVER run Gemini queries in the main conversation.** Always dispatch via a background Task agent to preserve the orchestrating session's context window.

The subagent acts as an interpreter — it runs the script, reads the full Gemini response, and returns only a compact summary to the orchestrator. This prevents large responses from polluting the main session's context.

## CRITICAL: Never Auto-Fallback to Different Models

**If a Gemini query fails (429, 503, or any error), DO NOT automatically retry with a different model.**

- Report the error back to the user exactly as received
- The user must explicitly request a different model
- Never silently switch from `gemini-2.5-pro` to `gemini-2.5-flash` or any other model
- This applies to rate limits, quota errors, and service unavailability

**Why:** Silent model fallback changes the quality/capability of the response without user awareness. Users must make informed decisions about model tradeoffs.

### Standard query

```
Task tool:
  subagent_type: "general-purpose"
  description: "Gemini research query"
  run_in_background: true
  prompt: |
    Research question: "YOUR QUESTION CONTEXT HERE"

    Run this command:
    python "C:/Users/JacobMadsen/.claude/scripts/gemini-research.py" generate "YOUR PROMPT HERE" --model gemini-2.5-pro

    After getting the response, return:
    1. A compact summary of findings relevant to the research question (key points, actionable details, code snippets if applicable)
    2. The session directory path (printed to stderr by the script) so I can read response.md for full context if needed

    Do NOT return the full Gemini response. Distill it to what's actionable.
```

### Long prompt (file-based)

For long prompts, write to a temp file first, then use `--prompt-file`:

```
Task tool:
  subagent_type: "general-purpose"
  description: "Gemini deep research"
  run_in_background: true
  prompt: |
    Research question: "YOUR QUESTION CONTEXT HERE"

    Run this command:
    python "C:/Users/JacobMadsen/.claude/scripts/gemini-research.py" deep-research --prompt-file "C:/path/to/prompt.md" --timeout 600

    After getting the response, return:
    1. A compact summary of findings relevant to the research question
    2. The session directory path for full context

    Do NOT return the full Gemini response. Distill it to what's actionable.
```

## REST API Script (Preferred)

**Script:** `~/.claude/scripts/gemini-research.py`

### Commands

| Command | Description | Async? |
|---------|-------------|--------|
| `list-models` | List available generative models | No |
| `generate "prompt" [--model MODEL]` | Sync content generation | No |
| `deep-research "prompt" [--poll-interval 45] [--timeout 3600]` | Async deep research with polling | Yes |

### Usage

```bash
# List models
python ~/.claude/scripts/gemini-research.py list-models

# Generate content (default: gemini-2.5-pro)
python ~/.claude/scripts/gemini-research.py generate "Explain WebAssembly component model"

# Generate with specific model
python ~/.claude/scripts/gemini-research.py generate "Compare React and Vue" --model gemini-2.5-flash

# Deep research (long-running, polls until complete)
python ~/.claude/scripts/gemini-research.py deep-research "Current state of WebAssembly" --timeout 600

# Load prompt from file (for long prompts)
python ~/.claude/scripts/gemini-research.py generate --prompt-file /path/to/prompt.md
```

### Models

| Model | Use Case |
|-------|----------|
| `gemini-2.5-pro` | Default. Best quality, reasoning tasks |
| `gemini-2.5-flash` | Fast responses, simpler queries |
| `gemini-3-pro-preview` | Latest preview model |

### Session Storage

All queries are automatically saved to:
```
~/source/repos/research/{mode}/YYYY-MM-DD_HHMMSS/
  prompt.md       # The prompt sent
  response.md     # Full model response
  metadata.json   # Model, tokens, timing, etc.
```

### API Key

Loaded in order:
1. `~/.claude/gemini.env` (dedicated config file)
2. `GEMINI_API_KEY` environment variable

### Error Handling

- **401/403**: Invalid API key
- **404**: Model or endpoint not available
- **429**: Rate limited (wait and retry)

## CLI Wrapper (Legacy)

**Script:** `~/.claude/skills/gemini/scripts/gemini.py`

Wraps the `gemini` CLI tool. Requires Gemini CLI installed.

```bash
uv run ~/.claude/skills/gemini/scripts/gemini.py "<prompt>" [working_dir]
```

- **Timeout:** 7200000ms (2 hours), always set `timeout: 7200000` on Bash tool
- **Model:** Configured via `GEMINI_MODEL` env var (default: `gemini-3-pro-preview`)

## Notes

- REST API script is zero-dependency (Python stdlib only)
- Both scripts are cross-platform (Windows/macOS/Linux)
- Research directory (`~/source/repos/research/`) is a git repo for versioning

---
name: log
description: Manually trigger interview-prep work logging if not already done this session
argument-hint: [optional: skill name to log as]
model: haiku
---

# Log Work

Manually trigger the interview-prep work log for the current session. Use when a session produced meaningful engineering output but the work log wasn't called automatically.

---

## Step 1: Check If Already Logged

Review the full conversation history for any prior call to `mcp__plugin_interview-prep-plugin_interview-prep__interview_work_log_append`.

- **If found:** Tell the user work was already logged this session. Show the `title` and `project` that were recorded. Stop here.
- **If not found:** Continue to Step 2.

---

## Step 2: Determine What Was Done

Scan the session to reconstruct the work performed. Identify:

- **Skill used** — which skill drove the work (e.g. `fix`, `implement-phase`, `spec`). If `$ARGUMENTS` specifies a skill name, use that. If no skill was invoked (ad-hoc work), use `manual`.
- **Project** — repo name or cwd basename
- **Title** — short descriptive title of the work
- **Summary** — 1-2 sentences describing what was accomplished
- **Files modified** — list of file paths changed during the session
- **Branch** — current git branch (run `git branch --show-current` if in a git repo, else `null`)
- **Commit** — HEAD short SHA (run `git rev-parse --short HEAD` if in a git repo, else `null`)

Also gather optional fields if evident from the session:

- **Technologies** — languages, frameworks, tools used
- **Patterns** — design/architectural patterns applied
- **Technical context** — 2-4 sentences on approach, decisions, tradeoffs

If the session is too minimal to extract a meaningful title and summary, use **AskUserQuestion**: "What work should I log? Give me a short title and what was accomplished."

---

## Step 3: Build the Tool Call

Construct the parameters following the work-log reference:

!`cat ~/.claude/skills/_components/work-log.md`

---

## Step 4: Call the Tool

Call `mcp__plugin_interview-prep-plugin_interview-prep__interview_work_log_append` with the constructed parameters.

Report the result to the user: title logged, project, and persisted path.

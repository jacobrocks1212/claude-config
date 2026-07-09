---
name: mine-sessions
description: Mine Claude Code session transcripts for patterns, friction, and evidence across past sessions without blowing up context. Use when asked to look back at prior sessions.
argument-hint: [what to investigate]
---

# Mine Sessions

Look back at past Claude Code sessions to identify patterns and draw evidence-backed conclusions — e.g. "how does `/execute-plan` behave after compaction", "where does the build workflow waste turns", "find every session that hit error X", "how big is context at the start of these sessions".

The whole point of this skill is to make session history a **queryable dataset**, not a pile of opaque logs. The single most important rule: **never read raw transcripts into your context.** A busy session is multiple megabytes of JSON; a handful of them will bury you. Always **extract signals first** with the scripts here, narrow to a few high-signal sessions, then read only targeted regions.

---

## Where session history lives

Claude Code writes one **JSONL transcript per session**:

```
~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl
```

- `<encoded-cwd>` is the session's absolute working directory with path separators and colons replaced by `-`. Example: cwd `C:\Users\me\source\repos\Foo` → dir `C--Users-me-source-repos-Foo`.
- **Each git worktree is its own cwd**, so it gets its own sibling project dir (e.g. `...-Foo`, `...-Foo-B`, `...-Foo-myfeature`). When mining a repo, scan **all** dirs whose name contains the repo slug, not just the canonical one.
- One project dir typically holds many `.jsonl` files (one per session). Sizes range from a few KB to tens of MB.

Find the relevant dirs first:
```bash
ls -d ~/.claude/projects/*<repo-slug>*
```

---

## Transcript record anatomy

Each line is one JSON object. The fields that matter for mining:

- **`type`** — `user`, `assistant`, plus harness bookkeeping lines (`summary`, `attachment`, `mode`, `file-history-snapshot`, `queue-operation`, …). Filter to `user`/`assistant` for conversation content.
- **`message`** — the actual message: `{ role, content, usage }`.
  - **`content`** — a string, OR an array of blocks: `{type:"text"}`, `{type:"tool_use", name, input}`, `{type:"tool_result", content, is_error}`.
  - **`usage`** — on assistant turns: `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. **Their sum = the model's context footprint at that turn** — the key signal for "how full was the window". Track it across turns to see the compaction sawtooth.
- **Slash-command invocations** appear in user-message text as `<command-name>/foo</command-name>` (with the expanded skill body following). This is how you find "every session that ran /foo".
- **Subagents (Agent/Task tool):** the *dispatch* (`tool_use` name `Agent`/`Task`, with `model`/`subagent_type`/`prompt`/`description`) and the agent's *final report* (`tool_result`) live inline in the parent transcript. The subagent's **internal turns** are stored separately — current Claude Code writes them to a sibling directory `~/.claude/projects/<encoded-cwd>/<parent-session-uuid>/subagents/agent-<id>.jsonl` (one file per subagent). They are NOT `isSidechain` lines in the parent file (older builds inlined them that way; this setup does not). **This matters a lot:** if the real work is delegated to subagents (builds, edits, test runs happen inside them), a scan of only top-level `<uuid>.jsonl` files MISSES it. When assessing "what subagents actually did", glob `<parent>/subagents/*.jsonl` too (or pass `--include-subagents` to `digest_sessions.py`). Each subagent file is itself a normal transcript — render it with `render_session.py`.
- **Compaction:** when the window fills, the harness compacts and injects a continuation summary as a new user turn (text begins "This session is being continued…"). Count these to measure how often a session compacted.
- **`timestamp`** — ISO time per line; first/last give wall-clock duration.

---

## The persisted toolkit (use these first; extend them when they fall short)

Two scripts ship with this skill under `scripts/`. They are pure-stdlib Python (no `jq`, no pip installs) and UTF-8-safe on Windows.

### 1. `digest_sessions.py` — scan many, extract signals
Produces a per-session digest (printed table + optional JSON) so you can rank/triage sessions before reading any of them.

```bash
python ~/.claude/skills/mine-sessions/scripts/digest_sessions.py \
    --match <repo-slug> --command execute-plan --out digest.json
```
Per-session signals: size, message counts, first/median/max context tokens, compaction count, tool-use histogram, slash-commands invoked, Agent dispatches + models, tool-error count, duration. Filters: `--match` (project-dir substring, repeatable), `--command` (slash command invoked, repeatable/OR), `--grep` (regex over raw text), `--frustration` (collect candidate human-correction messages). `--out` writes full JSON; `--top N` limits the printed table (0 = all). Run with `-h` for the full list.

### 2. `render_session.py` — read ONE session, linearized & greppable
After the digest narrows the field, render a single transcript to readable text (one block per turn, tool calls summarized, context tokens and markers per turn). Then `grep`/read only the regions you need.

```bash
python ~/.claude/skills/mine-sessions/scripts/render_session.py <session.jsonl> \
    --grep "COMPACTION" --max-chars 300 > out.txt
```
Turn headers look like `===== [#42 assistant ctx=187432] <<COMPACTION>> =====`. Filters: `--grep` (regex over rendered turn text), `--ctx-min K` (only turns with ≥K-thousand-token footprint), `--max-chars` (per-turn truncation). Useful greps once rendered: `<<COMPACTION>>`, `<<HUMAN>>`, `<<TOOL_ERROR>>`, `[Agent `, `[Skill `, `[Bash]`, or any domain string.

### 3. `attribute_predispatch.py` — attribute context up to the first subagent dispatch
Answers "what fills the window before the orchestrator dispatches its first agent". Walks each
transcript until the first `Agent`/`Task` tool_use, bucketing the bytes every source contributed:
`command-expansion` / `user-text` (incl. skill-body expansions and continuation summaries) /
`assistant-text` / `tool:<name>` — with per-file breakout for `Read` and per-command for `Bash`.
Reports turn-1 ctx (the startup baseline, which lives outside the transcript), dispatch-turn ctx,
per-session tables, cross-session category medians, and the top individual contributors (files).

```bash
python ~/.claude/skills/mine-sessions/scripts/attribute_predispatch.py \
    --from-digest digest.json --min-agents 1 --top 25 --out attribution.json
```
Accepts positional `.jsonl` paths or `--from-digest` (a `digest_sessions.py --out` file; filter
with `--min-agents`, cap with `--top-sessions`). `--until-tool` retargets the stop tool.
`--full` attributes the ENTIRE transcript (no dispatch cutoff; the "dispatch" columns become
end-of-run) — use it for subagent transcripts (`subagents/agent-*.jsonl`) and sessions that
never dispatch.

---

## Extending the toolkit (REQUIRED when the scripts lack what you need)

These scripts are seeds, not a frozen API. When your investigation needs a signal they don't extract (a new tool pattern, a domain-specific marker, a different aggregation, a cross-session join):

1. **Prefer extending the existing script** — add the signal to `digest_sessions.py` (per-session field) or a new marker/filter to `render_session.py`. Keep them general (parameterize, don't hardcode one investigation's specifics).
2. **If the need is genuinely separate**, write a new script under `scripts/` with a clear `--help` and a docstring explaining the signal it extracts.
3. **Persist the change back into this skill** (`~/.claude/skills/mine-sessions/scripts/` resolves through a symlink into the `claude-config` repo — edit the real target there if the Edit tool refuses the symlink). A one-off script left in a scratchpad is wasted; the next agent should inherit your tool. Update this SKILL.md's toolkit list if you add a script.
4. Keep them **stdlib-only and UTF-8-safe** (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`) so they run unchanged on Windows.

---

## Workflow

1. **Locate** the project dir(s): `ls -d ~/.claude/projects/*<slug>*` — include worktree siblings.
2. **Digest** with `digest_sessions.py` (filter by `--command`/`--grep`). Read the table + JSON, not the transcripts.
3. **Triage**: rank sessions by the signal you care about (max context, compactions, errors, agent count, duration).
4. **Deep-read** only the top few with `render_session.py`, grepping to the regions of interest. Cite session UUID + turn index as evidence.
5. **For broad sweeps**, fan out subagents — give each a batch of session paths plus the script paths and a precise question, and have them return structured findings (not raw dumps). One agent should not read dozens of multi-MB files itself.
6. **Conclude** with quantified, cited findings.

---

## Windows gotchas

- **No `jq`** on this machine — use Python (the scripts already do).
- **Force UTF-8 stdout** in any new script, or Windows `cp1252` will crash on transcript content.
- In the Bash tool, shell variables don't cross into a `python - <<'PY'` heredoc — pass paths as `sys.argv` or compute them inside Python (`os.path.expanduser`).
- Quote paths with spaces; project dirs and transcript paths are safe (no spaces) but repo source paths often aren't.

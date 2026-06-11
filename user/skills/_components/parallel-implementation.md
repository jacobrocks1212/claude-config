## Implement Approved Changes (Parallel Sonnet Subagents)

After the user approves which improvements to implement, dispatch the work via parallel Sonnet subagents. The orchestrator (you) must NOT call `Edit` or `Write` on source files — compose `Agent` tool calls instead.

### Partitioning Rules

1. **Group by file ownership** — changes to the same file go to the same subagent
2. **Separate by language** — Rust changes vs TypeScript changes vs Markdown in different agents
3. **Maximize parallelism** — independent file sets run concurrently
4. **Self-contained prompts** — each subagent has zero prior context; include: file paths, exact changes needed, surrounding code context, project conventions

### Dispatch Protocol

1. **Partition** the approved changes into work units (apply rules above)
2. **Announce** the partition: "Implementing N changes across M parallel subagents"
3. **Compose Agent calls** — one per work unit, all independent units in a single message for parallel execution:

```
Agent({
  description: "...",
  model: "sonnet",
  prompt: "<FULL self-contained context: what to change, why, file paths, code patterns to follow, project rules>"
})
```

4. **Review results** — for each completed subagent:
   - Verify the change matches the approved proposal
   - Check for accidental side effects
   - Confirm no file conflicts between agents

5. **Fix conflicts** — if two agents touched the same file or produced inconsistent changes, dispatch a fix-up agent

6. **Run quality gates** — after all agents complete:
   - Run the project's quality gates (see the quality-gates component or project CLAUDE.md for commands)
   - Fix failures via targeted subagent, re-run

### What the Orchestrator May Edit Directly

- `CLAUDE.md` files (any level)
- `PHASES.md` files
- Skill files (`~/.claude/skills/**/*.md`, `~/.claude-personal/skills/**/*.md`)
- Component files (`~/.claude/skills/_components/*.md`)
- Configuration files (`settings.json`, `skill-config/`)

### What MUST Go to Subagents

- Any `.ts`, `.js`, `.rs`, `.vue`, `.py`, `.tsx`, `.jsx` file
- Test files
- Build configuration that requires code-level knowledge

### Failure Protocol

If a subagent produces incorrect output after 2 retries:
1. Report which change failed and why
2. Skip that change and proceed with others
3. Include failed change in the final summary as "deferred — requires manual intervention"

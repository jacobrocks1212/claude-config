## Launch Subagents (MANDATORY — DO NOT SKIP)

### Partitioning Rules

**Critical constraint: No two subagents in the same batch may modify the same file.**

Partition deliverables into **work units** — groups of deliverables assignable to a single Sonnet subagent. Then group work units into **batches** where all units in a batch can run in parallel (no file overlap). Batch 1 runs first, Batch 2 after Batch 1 completes, etc.

### Launch Pattern

Launch Sonnet subagents in parallel (model: "sonnet", NO worktree isolation).

### TDD Protocol (injected automatically — every subagent inherits this)

!`cat ~/.claude/skills/_components/tdd-protocol.md`

### Every Subagent Prompt MUST Include

1. The relevant SPEC.md sections (quoted or summarized — subagents have no prior context)
2. The exact deliverables from PHASES.md (or bug description and root cause for fix work)
3. Relevant Integration Notes from prior phases (imports, patterns, gotchas)
4. Exact file paths to create/modify and exact test file paths
5. TDD instructions: write failing test FIRST, verify it fails (red), implement code, verify it passes (green)
6. Files NOT to touch (owned by other subagents in this batch)
7. Test commands to run for verification
8. Required return format: summary of implementation/fix, tests written, issues encountered

---

## Failed Subagent Recovery Protocol (MANDATORY)

### Monitor for Failures

After launching each batch, monitor every subagent for failure signals:
- Rate limit errors (429, quota exceeded)
- Crashes or unexpected termination
- Tool errors that halt progress
- Context overflow / token limit exceeded
- No output or stalled execution

### On Failure: Assess Completion

When a subagent fails, immediately assess its partial output:

1. Read all files the failed agent was assigned (from disk — treat disk state as ground truth)
2. Compare actual file state against the agent's deliverable list
3. Estimate completion percentage based on completed vs. remaining deliverables

### If < 95% Complete: Re-Dispatch (MANDATORY — DO NOT absorb into orchestrating session)

**NEVER do the failed agent's remaining work yourself.** Re-dispatch a new Sonnet subagent with:

1. The original prompt verbatim (same deliverables, same constraints, TDD requirements, file ownership rules, test commands)
2. A recovery preamble prepended to the prompt:

```
RECOVERY CONTEXT — A previous agent failed partway through this work.

Already completed (confirmed from disk):
- [List each file already created or modified, with a one-line description of its state]

Remaining work (do NOT redo completed items):
- [List deliverables not yet done based on disk state]

Resume from where the failed agent stopped. Do not re-create or overwrite already-completed files unless they are incomplete or broken.
```

3. Explicit instruction to verify each "already completed" file before touching it

### If ≥ 95% Complete: Orchestrator Completes Directly

If the failed agent was ≥ 95% complete (only trivial, minimal work remains), the orchestrating agent may complete the remaining work inline. Document what was completed and why re-dispatch was skipped.

### Re-Dispatch Limits

- Maximum **2 re-dispatch attempts** per work unit
- If a work unit fails after 2 re-dispatches, **escalate immediately** using the Blocking Issue Protocol — do not attempt further retries or absorb the work yourself

### Re-Dispatch Attempt Tracking

Track per work unit:
- Attempt 1: original launch
- Attempt 2: first re-dispatch (include recovery context)
- Attempt 3: second re-dispatch (include full recovery context from both prior attempts)
- Attempt 4+: BLOCKED — escalate

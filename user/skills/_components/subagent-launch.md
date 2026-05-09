## Launch Subagents — Test-First Pipeline (MANDATORY — DO NOT SKIP)

**HARD CONSTRAINT — READ BEFORE PROCEEDING:** ALL source and test code changes in this step MUST be made by Sonnet subagents via the `Agent` tool. You are the orchestrator. You compose prompts and dispatch agents — you do NOT call `Edit` or `Write` on any source, test, config, or implementation file. If you catch yourself about to write code inline, STOP, compose an `Agent({ model: "sonnet", prompt: "..." })` call instead, and dispatch it. There are ZERO exceptions to this rule for non-trivial work.

### TDD Decision Gate

!`cat ~/.claude/skills/_components/tdd-protocol.md`

---

### Phase A — Test Agents (TDD Work Units Only)

Skip this phase entirely if no work units in this batch have TDD=yes.

Launch Sonnet subagents **in parallel** (model: "sonnet", NO worktree isolation) — one per TDD work unit.

#### Test Agent Prompt Template

Every test agent prompt MUST include:

1. The relevant SPEC.md sections (quoted or summarized — subagents have no prior context)
2. The exact deliverables from PHASES.md this test covers
3. Exact test file paths to create
4. Test commands to run for verification
5. Files NOT to touch (owned by other agents in this batch)
6. The test agent briefing:

!`cat ~/.claude/skills/_components/tdd-test-agent.md`

#### Post-Phase-A Gate

After all test agents complete:

1. Verify test files were created at the expected paths
2. Confirm tests fail for the expected reasons (not compile errors or import misses)
3. If any test agent failed to produce valid failing tests, apply the Failed Agent Recovery Protocol below before proceeding to Phase B

---

### Phase B — Implementation Agents (ALL Work Units)

Launch Sonnet subagents **in parallel** (model: "sonnet", NO worktree isolation) — one per work unit.

#### Implementation Agent Prompt Template (TDD Work Units)

For work units with TDD=yes, every implementation agent prompt MUST include:

1. The relevant SPEC.md sections (quoted or summarized — subagents have no prior context)
2. The exact deliverables from PHASES.md
3. Relevant Integration Notes from prior phases (imports, patterns, gotchas)
4. Exact file paths to create/modify (implementation files only)
5. Paths to the failing test files written in Phase A — these define the contract
6. Test commands to run for verification
7. Files NOT to touch (owned by other agents, including test files)
8. The implementation agent briefing:

!`cat ~/.claude/skills/_components/implementation-agent.md`

#### Implementation Agent Prompt Template (Non-TDD Work Units)

For work units with TDD=no, every implementation agent prompt MUST include:

1. The relevant SPEC.md sections (quoted or summarized — subagents have no prior context)
2. The exact deliverables from PHASES.md (or bug description and root cause for fix work)
3. Relevant Integration Notes from prior phases (imports, patterns, gotchas)
4. Exact file paths to create/modify
5. Files NOT to touch (owned by other agents in this batch)
6. Required return format: summary of implementation, files modified, issues encountered

---

## Failed Subagent Recovery Protocol (MANDATORY)

Applies to both Phase A (test agents) and Phase B (implementation agents).

### Monitor for Failures

After launching each phase, monitor every subagent for failure signals:
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

1. The original prompt verbatim (same deliverables, same constraints, same phase — test or implementation)
2. A recovery preamble prepended to the prompt:

```
RECOVERY CONTEXT — A previous [test/implementation] agent failed partway through this work.

Already completed (confirmed from disk):
- [List each file already created or modified, with a one-line description of its state]

Remaining work (do NOT redo completed items):
- [List deliverables not yet done based on disk state]

Resume from where the failed agent stopped. Do not re-create or overwrite already-completed files unless they are incomplete or broken.
```

3. Explicit instruction to verify each "already completed" file before touching it

### If >= 95% Complete: Orchestrator Completes Directly

If the failed agent was >= 95% complete (only trivial, minimal work remains), the orchestrating agent may complete the remaining work inline. Document what was completed and why re-dispatch was skipped.

### Re-Dispatch Limits

- Maximum **2 re-dispatch attempts** per work unit per phase
- If a work unit fails after 2 re-dispatches, **escalate immediately** using the Blocking Issue Protocol — do not attempt further retries or absorb the work yourself

### Re-Dispatch Attempt Tracking

Track per work unit per phase (test or implementation):
- Attempt 1: original launch
- Attempt 2: first re-dispatch (include recovery context)
- Attempt 3: second re-dispatch (include full recovery context from both prior attempts)
- Attempt 4+: BLOCKED — escalate

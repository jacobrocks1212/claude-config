# Execution Completion Summary — required end-of-run report templates

Read by `/execute-plan` at Step 4 (completion time only — deliberately NOT inlined into the
skill body, so its bytes are never resident before the run's final stretch). Emit the blocks
below in order. Do NOT elide any of them — the census lines are how the orchestrator and
`/lazy-batch-retro` audits detect contract violations; silent compliance theatre is the
failure mode they exist to prevent.

## 1. Behavior enabled by this execution (MANDATORY)

Summarize the **actual product behavior newly enabled** by this plan execution — capability,
not changelog (❌ "Added `exportChart()` to chart.ts" / ✅ "Users can export charts as PNG").
Only behavior actually wired up end-to-end; scope strictly to THIS execution (not prior phases,
not future ones). Both sections required — write `- (none)` rather than omitting a heading.

```
## Behavior enabled by this execution

### User-facing
- {capability the user can now exercise, as a verb phrase}
- ...

### Non-user-facing
- {capability now available to developers/operators/downstream systems}
- ...
```

## 2. Feature-level summary (CONDITIONAL — only if the spec completed)

If **every deliverable checkbox in PHASES.md is now `- [x]`** (verify:
`python ~/.claude/scripts/phases-slice.py <PHASES.md> --index-only` — every phase tally full),
additionally print the cumulative capability set for the whole feature. Skip when any
deliverable remains unchecked. Same capability-not-changelog rules; feature name from SPEC.md's
title (fallback: PHASES.md title).

```
## Feature complete: {feature name}

### User-facing behavior delivered by this feature
- ...

### Non-user-facing behavior delivered by this feature
- ...
```

## 3. Final summary + dispatch/gate census (MANDATORY)

```
Plan execution complete: {plan-file-path}
Tasks completed: {count}

Sub-subagent dispatch census (per Execution Model Enforcement contract):
  Sonnet test-agents dispatched: {test_agent_count}
  Sonnet impl-agents dispatched: {impl_agent_count}
  Total Sonnet sub-subagents:    {total_count}
  Batches with source/test changes: {batches_with_source_changes}
  Contract status: {OK | CONTRACT_VIOLATION: <details>}

Quality gate census:
  Workspace-level QG runs: {qg_count}
  Targeted-only runs:      {targeted_count}
  Gate status: {OK | INCOMPLETE: workspace QG did not run on batch <N>}
```

Lane plans (Cognito): count each inline-TDD lane agent as one test-agent AND one impl-agent
(per the lane contract's dispatch-census note). If the contract was violated, the
contract_status line must say so explicitly.

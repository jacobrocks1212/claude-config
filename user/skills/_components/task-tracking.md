### Task Tracking (MANDATORY FIRST ACTION — DO NOT SKIP, DO NOT DEFER)

**STOP.** This is the first executable step of this plan. Do NOT start any batch, write any code, or dispatch any subagent until every sub-step below is complete. If you skip this section, all subsequent task-status updates will fail silently and progress tracking will be lost.

#### 1. Load Task Tools (BLOCKING GATE)

Call ToolSearch NOW to load the task tools. This is a hard prerequisite — nothing else proceeds until these four tools are available in your tool list:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

After ToolSearch returns, verify you received schemas for all four tools: `TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`. If any are missing, call ToolSearch again. If still missing after a second attempt, STOP and report the error to the user — do not proceed without task tools.

#### 2. Create Tasks for All Work Units (IMMEDIATELY — before any batch)

For each TDD work unit, call TaskCreate twice:
- **Title:** `[Batch N] WU-X Tests: [scope summary]`
- **Description:** Test files to create, deliverables covered, batch assignment
- **Status:** `not_started`

- **Title:** `[Batch N] WU-X Impl: [scope summary]`
- **Description:** Files to create/modify, deliverables covered, batch assignment
- **Status:** `not_started`

For each non-TDD work unit, call TaskCreate once:
- **Title:** `[Batch N] WU-X: [scope summary]`
- **Description:** Files to modify, deliverables covered, batch assignment
- **Status:** `not_started`

For each review step, call TaskCreate:
- **Title:** `[Batch N] Review`
- **Status:** `not_started`

For each quality-gate step, call TaskCreate:
- **Title:** `[Batch N] Quality Gates`
- **Status:** `not_started`

#### 3. Update Tasks as Work Progresses

**Phase A — Test agents (TDD WUs only):**
- **Before launching test agent:** TaskUpdate `WU-X Tests` → `in_progress`
- **After test agent succeeds:** TaskUpdate `WU-X Tests` → `completed`
- **After test agent fails:** TaskUpdate `WU-X Tests` → `failed`

**Phase B — Implementation agents (all WUs):**
- **Before launching impl agent:** TaskUpdate `WU-X Impl` (or `WU-X` for non-TDD) → `in_progress`
- **After impl agent succeeds:** TaskUpdate → `completed`
- **After impl agent fails:** TaskUpdate → `failed`

**Review and QG:**
- **Before starting review:** TaskUpdate `[Batch N] Review` → `in_progress`
- **After review passes:** TaskUpdate `[Batch N] Review` → `completed`
- **Before running quality gates:** TaskUpdate `[Batch N] Quality Gates` → `in_progress`
- **After quality gates pass:** TaskUpdate `[Batch N] Quality Gates` → `completed`

#### 4. Retry Protocol

If a test or implementation agent fails and is re-dispatched:
1. TaskUpdate original task → `failed`
2. TaskCreate a new task titled `[Batch N] WU-X [Tests/Impl] (retry): [scope summary]` → `not_started`
3. Proceed from step 3 above for the new task

#### 5. Completion Verification

Before reporting completion, call TaskList and verify every task created during this execution is in `completed` status. If any task is not `completed`, investigate and resolve before proceeding.

#### Rules

- Task creation happens at the **orchestrating agent level** — subagents do not have task tool access and must not be asked to create or update tasks
- Update tasks **promptly** — do not batch updates
- Keep titles concise but descriptive enough to identify the work unit at a glance

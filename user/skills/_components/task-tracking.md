### Task Tracking (MANDATORY — DO NOT SKIP)

#### 1. Load Task Tools

Use ToolSearch to load the task tools if not already available:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

#### 2. Create Tasks for All Work Units (after partitioning)

For each work unit, call TaskCreate:
- **Title:** `[Batch N] Work Unit X: [scope summary]`
- **Description:** Files to modify, deliverables covered, batch assignment
- **Status:** `not_started`

For each review step, call TaskCreate:
- **Title:** `[Batch N] Review`
- **Status:** `not_started`

For each quality-gate step, call TaskCreate:
- **Title:** `[Batch N] Quality Gates`
- **Status:** `not_started`

#### 3. Update Tasks as Work Progresses

- **Before launching a subagent:** TaskUpdate → `in_progress`
- **After subagent succeeds:** TaskUpdate → `completed`
- **After subagent fails:** TaskUpdate → `failed`
- **Before starting review:** TaskUpdate `[Batch N] Review` → `in_progress`
- **After review passes:** TaskUpdate `[Batch N] Review` → `completed`
- **Before running quality gates:** TaskUpdate `[Batch N] Quality Gates` → `in_progress`
- **After quality gates pass:** TaskUpdate `[Batch N] Quality Gates` → `completed`

#### 4. Retry Protocol

If a work unit fails and is re-dispatched:
1. TaskUpdate original task → `failed`
2. TaskCreate a new task titled `[Batch N] Work Unit X (retry): [scope summary]` → `not_started`
3. Proceed from step 3 above for the new task

#### 5. Completion Verification

Before reporting completion, call TaskList and verify every task created during this execution is in `completed` status. If any task is not `completed`, investigate and resolve before proceeding.

#### Rules

- Task creation happens at the **orchestrating agent level** — subagents do not have task tool access and must not be asked to create or update tasks
- Update tasks **promptly** — do not batch updates
- Keep titles concise but descriptive enough to identify the work unit at a glance

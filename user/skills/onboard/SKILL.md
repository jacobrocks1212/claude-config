---
name: onboard
description: Read-only codebase onboarding — structure, entry points, real execution paths, code-grounded explanation. Use when orienting in an unfamiliar repo or asking 'where do I start'.
argument-hint: "[area or question, e.g. 'payments flow' or 'where submissions persist']"
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Agent"]
---

# Codebase Onboarding

Get a developer productive in an unfamiliar codebase fast. Read the source, trace the
paths, and state the facts. Nothing extra.

**What the user wants oriented:**
$ARGUMENTS

If `$ARGUMENTS` is empty, orient the whole repository. Otherwise scope the trace to the
named area or question.

---

## Two invariants (non-negotiable)

1. **Read-only.** Never modify the repository, generate patches, or change state. This skill
   has no `Write`/`Edit` access by design. Do not run build/test/run tooling either
   (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`, `tauri:dev`, `/mcp-test`, package installs) —
   those build, mutate, or launch the app.
2. **Facts only.** State what the code does, citing the files you actually inspected. Do not
   infer intent, evaluate quality, or recommend changes. If it was not in the code you read,
   do not state it.

## Stay in scope

Do **not** drift into code review, refactoring plans, redesign, optimization advice, "safer
edit location" suggestions, or product-feature commentary. You describe the system as it is;
you do not improve it. When inspection is partial, say exactly which files you read and which
you did not — never imply whole-repo comprehension after reading one subsystem.

---

## Repo-specific anchors

If running inside a configured repo, the block below loads that repo's entry points, layer
map, "read these first" shortcuts, and newcomer traps. Outside a configured repo it falls back
to a generic discovery guide. Read it before tracing — it tells you where to start.

!`cat .claude/skill-config/onboarding-repo-map.md 2>/dev/null || cat ~/.claude/skills/_components/onboarding-repo-map.md`

---

## Workflow

### Step 1 — Inventory & classification
Identify manifests, lockfiles, framework markers, build tools, and top-level directories.
Classify the repo: application / library / monorepo / service / plugin / mixed workspace.
Focus on code-bearing directories. For a broad repo, dispatch parallel **Explore** subagents
(one per region) to map concurrently and keep your own context clean — collect their findings,
do not re-walk what they covered.

### Step 2 — Entry-point discovery
Find the startup files, routers, request handlers, CLI commands, workers, and package exports —
the smallest set of files that define how the system starts and receives work.

### Step 3 — Execution & data-flow tracing
Follow one concrete path end-to-end: entry → validation → orchestration → core logic →
persistence / side-effects → output. Name the real file at each hop. Note where async jobs,
queues, cron, background workers, or client-side state alter the flow. If the user scoped a
question, trace that path specifically.

### Step 4 — Boundary & ownership analysis
Identify module seams, package boundaries, shared utilities, and duplicated responsibilities.
Separate stable public interfaces from implementation detail. Surface dead code, migration
artifacts, and misleading names **descriptively** ("despite the name, `manager` is the
application service layer") — not as problems to fix.

### Step 5 — Output
Emit the three-level output below, in order.

---

## Output contract

```markdown
# Codebase Orientation Map

## 1-Line Summary
[One sentence: what this codebase / scoped area is.]

## 5-Minute Explanation
- **Primary tasks in code**: [what the code does]
- **Primary inputs**: [HTTP requests, CLI args, messages, files, function args]
- **Primary outputs**: [responses, DB writes, files, events, rendered UI]
- **Key files**: [`path` — responsibility]
- **Main code paths**: [entry → orchestration → core logic → outputs]

## Deep Dive
- **Type / runtime**: [web app / API / monorepo / CLI / library — and language(s)]
- **Entry points**:
  - `path/to/entry` — why it matters
  - `path/to/router` — why it matters
- **Top-level structure**:
  | Path | Purpose | Notes |
  |------|---------|-------|
- **Key boundaries**: presentation / application-domain / persistence-I/O / cross-cutting
- **Responsibilities by file**: [`file` → responsibility]
- **Detailed code flow**:
  1. Entry at `path/to/entry`
  2. Routing/handler in `path/to/handler`
  3. Business logic in `path/to/service`
  4. Persistence / side effects in `path/to/repo-or-job`
  5. Result returns through `path/to/response-layer`
- **How the pieces map together**: [imports, calls, dispatches, handlers, persistence]
- **If you read 3 files first**: [the highest-leverage files for a newcomer]

## Inspection honesty
- **Files inspected**: [full list]
- **Files NOT inspected**: [relevant areas you did not open]
```

---

## Communication style

- Lead with facts: "This is a C# API with controllers in `Cognito.Services`, services in
  `Cognito`, and domain contracts in `Cognito.Core`."
- Cite evidence: "Stated from `BaseController.cs` and `FormController.cs`."
- Reduce search cost: "If you only read three files first, read these."
- Translate abstractions in plain language, descriptively.
- Be honest about limits: "I inspected the controller and service; I did not open the queue
  workers." Quote function/class/route/config names exactly when they matter.

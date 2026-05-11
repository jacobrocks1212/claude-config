**THIS STEP IS NON-NEGOTIABLE.** You MUST call `interview_work_log_append` before ending this skill. Do not skip this step due to context pressure, compaction, or perceived irrelevance. If you are about to produce a final message without having called this tool, STOP and call it first.

Call the `interview_work_log_append` MCP tool (interview-prep server) to record this session's work. This is the authoritative record for tracking all skill-driven work across projects over time. Do NOT use Bash file writes or store this data in project-local files.

**`timestamp` is auto-generated** — the tool sets it to UTC ISO-8601. Do not pass a timestamp.

**Common parameters (pass directly to the tool):**

| Parameter | Value |
|-----------|-------|
| `skill` | Skill name that produced this work (e.g. `fix`, `implement-phase`, `spec`) |
| `project` | Repo name or cwd basename |
| `title` | Short descriptive title of what was planned/done |
| `summary` | 2-4 sentences. Go beyond "what" — name the architectural patterns, system design concepts, and engineering tradeoffs involved. Mention scale/performance considerations, data flow patterns, API design choices, concurrency concerns, or reliability strategies when relevant. Think: "what would make this useful in an interview conversation?" Bad: "Fixed DC bias bug in voice synth." Good: "Fixed boundary validation bug in Rust DSP pipeline where the pw parameter defaulted to 0, producing DC output. Added input validation at the module boundary with clamping semantics — a defensive programming pattern that prevents silent corruption in signal processing chains." |
| `files_modified` | Array of file paths modified during this work |
| `branch` | Current git branch, or `null` |
| `commit` | HEAD short sha, or `null` |
| `phases_md` | Path to PHASES.md if applicable, or `null` |
| `spec_md` | Path to SPEC.md if applicable, or `null` |
| `technologies` | Array of frameworks, languages, and tools used (e.g. `["TypeScript", "React", "PostgreSQL"]`) |
| `patterns` | Array of design/architectural patterns applied — use kebab-case slugs that map to system design and OOD concepts (e.g. `["factory-pattern", "append-only-log", "content-hash-dedup", "batch-processing", "event-sourcing"]`) |
| `technical_context` | 3-5 sentences expanding on the engineering depth. Cover: (1) the problem space and constraints that drove the design, (2) alternatives considered and why they were rejected, (3) specific tradeoffs accepted (e.g. consistency vs. availability, memory vs. CPU, simplicity vs. extensibility). Name concrete system design concepts: caching strategies, data partitioning, idempotency, rate limiting, pub/sub, CQRS, etc. This field is the richest signal for downstream interview topic correlation. |

**Conditional fields — pass via the `extra` dict, include ALL that match the current skill:**

| Field | When skill is | Value |
|-------|---------------|-------|
| `bug_summary` | `fix` | One-line user report of the bug |
| `root_cause` | `fix` | One or two sentences explaining the root cause |
| `category` | `fix` | One of: `requirements-change` \| `inadequate-test-coverage` \| `inadequate-research` \| `incorrect-spec` \| `integration-gap` \| `environment-platform` \| `regression` \| `ui-ux-polish` \| `tooling-config` \| `other` |
| `category_justification` | `fix` | One sentence justifying the category |
| `regression_tests` | `fix` | Array of test paths added to prevent recurrence |
| `skills_updated` | `fix` | Array of `{ "skill": "<name>", "path": "<path>", "rule_added": "<summary>" }` |
| `skills_update_note` | `fix` | Reason if no skills were updated, else `null` |
| `phase_number` | `implement-phase`, `implement-phase-batch` | Phase number(s) implemented |
| `work_units_completed` | `implement-phase`, `implement-phase-batch` | Count of work units completed |
| `batches_completed` | `implement-phase`, `implement-phase-batch` | Count of batches completed |
| `phases_produced` | `spec-phases`, `spec-phases-batch` | Number of phases produced in the decomposition |
| `features_decomposed` | `spec-phases`, `spec-phases-batch` | Number of features decomposed |
| `speculative_count` | `spec-phases-batch` | Number of speculative phase breakdowns |
| `spec_status` | `spec` | `draft` or `final` |
| `research_conducted` | `spec` | `true` or `false` |
| `plan_path` | `writing-plans` | Path where the plan was saved |
| `superseded_phases` | `add-phase` | Array of phase numbers superseded by the new phase, or `[]` |

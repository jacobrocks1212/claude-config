### Evidence Gathering (Parallel Subagents)

Before the context synthesis below, launch parallel research subagents to collect all available
evidence that grounds this feature in what already exists and what was actually requested. Each
subagent returns structured findings. **Adapt the set to what's available** — skip any subagent
whose data source doesn't exist. This step is **mechanical evidence gathering — no user
decisions** — so it runs identically in interactive and `--batch` mode.

**`/spec` in this repo accepts an ADO work-item id** (a bare number, `#56565`, `AB#56565`, or an
ADO work-item URL) in place of — or alongside — a prose feature description. When one is present,
the work-item context subagent (F, below) fetches that item and its related items **first**, so
the rest of the evidence gathering — and the whole spec — is grounded in what was actually
requested rather than a paraphrase.

Fold every finding into Phase 0's context synthesis and into Phase 1b's dependency / reuse
discovery: an existing system surfaced here is a **reuse candidate**, not a reason to write new
code.

#### Subagent A: Conversation & Session History

**Prompt:** Search recent conversation and session history for prior discussion of this feature.

1. Check the current conversation for: prior framing of the request, constraints already stated, options weighed, files mentioned
2. Search `~/.claude-personal/projects/` and `~/.claude/projects/` for recent `.jsonl` session files mentioning the feature's load-bearing terms
3. Extract: what has already been decided, what was explicitly ruled out, and any open questions already surfaced

Report format: chronological list of relevant prior context with source attribution.

#### Subagent B: Recent Activity (git history)

**Prompt:** Check recent git activity — in this repo AND in the sibling `../cog-docs` docs repo — for work relevant to this feature.

1. In the Cognito Forms worktree: run `git log --oneline -30` and `git log --oneline --all -50 -i --grep "<load-bearing term>"` for commits touching the feature's area; run `git log -p -S "<key symbol/term>"` to find where related code was last changed
2. In `../cog-docs`: run `git -C ../cog-docs log --oneline -30 -- docs/features docs/bugs` to surface recently-authored specs/plans in the area
3. Run `git diff` (unstaged) and `git diff --cached` (staged) in the worktree to see current in-flight work in the area

Report format: timeline of relevant commits (sha, subject, files) across both repos plus any in-flight uncommitted work, each annotated with why it's relevant.

#### Subagent C: Related Documentation (cog-docs + repo)

**Prompt:** Find existing documentation, specs, and prior art for this feature's area — the canonical docs live in the sibling `../cog-docs` repo.

1. Read the repo `CLAUDE.local.md` and the relevant subdirectory `CLAUDE.local.md` files (Cognito.Core, Cognito, Cognito.Services, Cognito.Web.Client, …) for architecture context and gotchas in the area
2. Search `../cog-docs/docs/features/` for existing feature specs that touch the same subsystem — feature dirs are named `<WI_ID>-<slug>` or a bare `<slug>` (e.g. `57100-person-forms-adoption-tracking`, `audit-log-patch-sections`). Read the SPEC.md Executive Summary / Technical Design of each match
3. Search `../cog-docs/docs/bugs/` for related bug investigations (open and archived) in the same area
4. Search `../cog-docs/docs/product/` for product-identity / knowledge-base docs that frame the feature
5. Note any spec that overlaps or conflicts — these become dependency candidates in Phase 1b and must not be contradicted

Report format: list of related documents (path + one-line relevance), flagging any overlap/conflict the new spec must reconcile.

#### Subagent D: Current Behavior / Runtime Evidence (only if the feature modifies existing behavior)

**Prompt:** If this feature changes or extends behavior that already ships, capture how the current system behaves so the spec builds on reality.

1. Skip this subagent entirely for a purely greenfield capability with no existing behavior to modify
2. Otherwise, identify the current user-facing behavior the feature will change and how it is produced (existing tests, a manual trace, logs)
3. Extract: the current behavior, its edge cases, and any constraints the existing implementation imposes on the new design

Report format: a concise description of current behavior + the constraints it places on the feature. (Omit if greenfield.)

#### Subagent E: Source Code Analysis (existing systems to build on)

**Prompt:** Read the source in the area this feature will touch to inventory what can be reused or extended. Load the `csharp-cognito` and `architecture-patterns` skills first for backend areas; `vue`, `vue-composition-api`, `nx-workspace-patterns` for frontend areas.

1. Based on the feature description / work item, identify the likely affected projects, services, and code paths (backend: `Cognito.Core`/`Cognito`/`Cognito.Services`; frontend: `Cognito.Web.Client/apps/*` + `libs/*`)
2. Read the relevant source end-to-end — focus on existing services, abstractions, extension points, and data models the feature could build on. Use the tree-sitter MCP (`get_file_structure`, `find_symbol_usages`) before reading large files
3. Identify: what already exists that the feature should extend rather than reimplement, and the patterns/conventions (DI, storage, model.js) the new code must follow

Report format: annotated map of existing Cognito systems the feature can build on, with explicit reuse candidates (these feed Phase 1b.7 Reuse-First Discovery).

#### Subagent F: ADO Work Item Context

**Only launch if** the user's description references (or is) an ADO work-item id (a bare number, `#56565`, `AB#56565`, or an ADO work-item URL).

**Prompt:** Use the Azure DevOps MCP to fetch the referenced work item and its related items, grounding the spec in what was actually requested.

1. Resolve the work-item id from the user's description (bare number / `#id` / `AB#id` / ADO URL)
2. Via the Azure DevOps MCP work-item tools, fetch the item: title, description, acceptance criteria, state, priority, area/iteration path, tags, and the full discussion/comment history
3. Follow the work item's relations (parent epic/feature, children, related, and linked PRs/commits) and fetch each related item's title + state for surrounding scope
4. If the ADO MCP is unavailable, disconnected, or failing, fall back to `az boards work-item show --id <id>` (and `az boards work-item relation show --id <id>`) per `AGENTS.md`, telling the user you are using the CLI fallback for this session
5. Extract: the requested behavior, acceptance criteria, in-scope vs out-of-scope signals, prior triage/discussion, and the canonical `<WI_ID>` that will name the `../cog-docs/docs/features/<WI_ID>-<slug>/` directory (see `../cog-docs/docs/features/CLAUDE.md` for the naming convention)

Report format: a structured work-item summary (id, title, state, requested behavior, acceptance criteria) plus a short list of related items with their relevance, and the resolved `<WI_ID>` for the feature directory name.

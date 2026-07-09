### Evidence Gathering (Parallel Subagents)

Before the context synthesis below, launch parallel research subagents to collect all available
evidence that grounds this feature in what already exists and what was actually requested. Each
subagent returns structured findings. **Adapt the set to what's available** — skip any subagent
whose data source doesn't exist (e.g. no tracker, no runtime the feature touches). This step is
**mechanical evidence gathering — no user decisions** — so it runs identically in interactive and
`--batch` mode.

**If the user's description is (or references) a work-item id**, the work-item context subagent
(F, below) fetches that item and its related items **first**, so the rest of the evidence
gathering — and the whole spec — is grounded in what was actually requested rather than a
paraphrase.

Fold every finding into Phase 0's context synthesis and into Phase 1b's dependency / reuse
discovery: an existing system surfaced here is a **reuse candidate**, not a reason to write new
code.

#### Subagent A: Conversation & Session History

**Prompt:** Search recent conversation and session history for prior discussion of this feature.

1. Check the current conversation for: prior framing of the request, constraints already stated, options weighed, files mentioned
2. Search `~/.claude/projects/` (and `~/.claude-personal/projects/`) for recent `.jsonl` session files mentioning the feature's load-bearing terms
3. Extract: what has already been decided, what was explicitly ruled out, and any open questions already surfaced

Report format: chronological list of relevant prior context with source attribution.

#### Subagent B: Recent Activity (git history)

**Prompt:** Check recent git activity for work relevant to this feature.

1. Run `git log --oneline -30` and search it (and `git log --oneline --all -50 -i --grep "<load-bearing term>"`) for commits touching the feature's area
2. Run `git diff --stat HEAD~10` and `git log -p -S "<key symbol/term>"` to find where related code was last changed and by which commit
3. Run `git diff` (unstaged) and `git diff --cached` (staged) to see current uncommitted work in the area

Report format: timeline of relevant commits (sha, subject, files) plus any in-flight uncommitted work, each annotated with why it's relevant to this feature.

#### Subagent C: Related Documentation

**Prompt:** Find existing documentation, specs, and prior art for this feature's area.

1. Read the project `CLAUDE.md` / `CLAUDE.local.md` for architecture context, conventions, and known gotchas in the area
2. Search the spec directory (resolved in Phase 0) for existing feature specs and bug docs that touch the same subsystem — open and read the Executive Summary / Technical Design of each match
3. Check subdirectory `CLAUDE.md` files near the code the feature will touch
4. Note any spec that overlaps or conflicts — these become dependency candidates in Phase 1b and must not be contradicted

Report format: list of related documents (path + one-line relevance), flagging any overlap/conflict the new spec must reconcile.

#### Subagent D: Current Behavior / Runtime Evidence (only if the feature modifies existing behavior)

**Prompt:** If this feature changes or extends behavior that already ships, capture how the current system behaves so the spec builds on reality.

1. Skip this subagent entirely for a purely greenfield capability with no existing behavior to modify
2. Otherwise, identify the current user-facing behavior the feature will change and how it is produced (logs, existing tests, a manual trace)
3. Extract: the current behavior, its edge cases, and any constraints the existing implementation imposes on the new design

Report format: a concise description of current behavior + the constraints it places on the feature. (Omit if greenfield.)

#### Subagent E: Source Code Analysis (existing systems to build on)

**Prompt:** Read the source in the area this feature will touch to inventory what can be reused or extended.

1. Based on the feature description, identify the likely affected files, services, and code paths
2. Read the relevant source end-to-end — focus on existing abstractions, extension points, and data models the feature could build on
3. Identify: what already exists that the feature should extend rather than reimplement, and any patterns/conventions the new code must follow

Report format: annotated map of existing systems the feature can build on, with explicit reuse candidates (these feed Phase 1b.7 Reuse-First Discovery).

#### Subagent F: Work Item Context (if a tracker is in use)

**Only launch if** the project uses an issue/work-item tracker AND the user's description references (or is) a work-item id.

**Prompt:** Fetch the referenced work item and its related items to ground the spec in what was actually requested.

1. Parse the user's description for a work-item id (a bare number, `#123`, `AB#123`, or a tracker URL)
2. Fetch the work item: title, description, acceptance criteria, state, priority, area/iteration, tags, and the full discussion/comment history
3. Follow the work item's relations (parent epic/feature, children, related items, linked PRs/commits) and fetch each related item's title + state for surrounding scope
4. Extract: the requested behavior, acceptance criteria, in-scope vs out-of-scope signals, prior discussion, and the resolved id for downstream directory naming

Report format: a structured work-item summary (id, title, state, requested behavior, acceptance criteria) plus a short list of related items with their relevance, and the resolved id for the feature directory name.

# Write PR Description

Use this skill when writing or rewriting pull request descriptions to ensure consistent, high-quality documentation of changes.

## Trigger Phrases
- "write pr description"
- "rewrite pr description"
- "update pr description"
- "create pr description"

## PR Description Format

All PR descriptions MUST follow this exact structure:

```markdown
# [Concise, imperative PR title summarizing the net change]

## Background
- [Business need or capability being added]
- [Scale/performance requirements if relevant]
- [Key architectural decision summary]

## Solution
[1-2 sentence high-level summary describing the architecture]

### File Changes
**[Component Name]:**
- `file.ts` (new): [Purpose]
- `file.ts`: [What changed]

### Test Coverage
- `test-file.ts`: [Scenarios covered]

**Work Items:** [AB#<id> references, when found — omit this section entirely if no work item applies]
```

## Core Principles

1. **4000 character limit**: PR descriptions MUST be capped at 4000 characters maximum. Prioritize architectural decisions and key components over exhaustive file lists.

2. **Describe current state, not the journey**: PR descriptions document the NET result of the branch — what exists NOW vs main. Never mention:
   - Files that were added AND deleted in the same branch (they don't exist in the final diff)
   - Previous approaches that were tried and abandoned
   - Refactoring iterations or intermediate states
   - What was "replaced" or "superseded" (just describe what IS)

3. **Architecture over files**: Lead with high-level architectural concepts (e.g., "read model", "write path", "linking modes") rather than file-by-file lists. Group related files by their architectural role.

4. **Section structure**: A single H1 PR title (`# ...`) leads the description, followed by the Background and Solution main sections. A `**Work Items:**` section is appended at the end only when a work item is found.

4a. **PR title**: The description MUST open with a single H1 (`# <title>`). Make it concise and imperative (e.g., `Classify target action viability and add Create New Person Entries toggle`), summarizing the net change. No trailing period, no PR number, no work-item id in the title.

5. **Backticks required**: All file names, function names, variable names, class names, identifiers, and code references must be enclosed in backticks (e.g., `computeImageValue`, `PersonEntryId`). Do NOT bold file names.

6. **No stale references**: Never include test counts, line counts, commit hashes, or version numbers.

7. **Test Coverage section**: REQUIRED when test files changed. List test files with high-level scenario descriptions.

8. **Length management**: When approaching the limit:
   - Group files by architectural component (e.g., "Write path: `IndexBuilder.cs`, `EntryIndexService.cs`")
   - Omit obvious supporting files (DTOs, test implementations)
   - Focus on components that represent key decisions

9. **No em dashes**: The PR description MUST NOT contain em dashes (`—`). Use a comma, colon, parentheses, or two separate sentences instead. This applies to the generated description text only, not to file names or code identifiers.

10. **Work item references**: When the branch addresses a work item, reference it as `AB#<WI_ID>` (e.g., `AB#56565`). Infer the WI ID from the branch name, commit messages, or the conversation. Place the reference(s) in a final `**Work Items:**` section at the end of the description (after Test Coverage), not in the Background. Use the bare `AB#<WI_ID>` form, not a URL or `#<WI_ID>`. List multiple work items separated by commas. When no work item is found, omit the section entirely.

## File Annotation Conventions

| Annotation | When to Use |
|------------|-------------|
| `(new)` | File added in this branch |
| `(deleted)` | File removed from main — only include if deletion is architecturally significant |
| No annotation | File modified |

**Note:** Files that were both added and deleted in the same branch should NOT appear at all.

## Example

```markdown
# Add PersonSubmissions read model for person-scoped entry queries

## Background
- CognitoPay needs to query all entries related to a person at scale (10K+ entries)
- `PersonEntryId` serves as the canonical `CustomerId` — no separate Customer entity needed

## Solution
Introduce a `PersonSubmissions` Cosmos read model partitioned by `PersonEntryId`. Write path integrates with `IndexBuilder` to maintain the index during entry saves. Three linking modes supported: `SameForm`, `PersonField`, and `FieldMapping`.

### File Changes
**Read Model:**
- `PersonSubmissionIndex.cs` (new): Cosmos document with denormalized status/color
- `PersonSubmissionRepository.cs` (new): Paginated queries with filtering and continuation tokens
- `PersonSubmissionController.cs` (new): API endpoints (`POST /query`, `GET /summary`)

**Write Path:**
- `IndexBuilder.cs`: Added `SubmitterPersonEntryIdUpdate` to compute linked person during index build
- `EntryIndexService.cs`: Cosmos index writes + `ResolveFieldMappingAsync` for email matching

**Configuration:**
- `SubmitterPersonSettings.cs` (new): Per-form linking mode configuration
- `Form.cs`: Added `SubmitterPersonSettings` property

**Guest Enhancement:**
- `EntryIndexSchema.cs`: Added `GuestAssignment.IndexingComplete` to skip O(n) fallback scan

### Test Coverage
- `PersonSubmissionsIndexingTests.cs`: Write path for all linking modes, status propagation
- `PersonSubmissionControllerTests.cs`: API authorization and validation

**Work Items:** AB#56565
```

## Process

### Step 1: Identify NET Branch Changes (Critical)

**IMPORTANT:** Use `git diff` against the merge-base to see only NET changes. This automatically excludes files that were added and then deleted in the same branch.

```bash
# Find merge-base and diff against it
MERGE_BASE=$(git merge-base main HEAD)
git diff --name-status $MERGE_BASE..HEAD
```

The `--name-status` output shows NET changes only:
- `A` = File exists in branch but not in main (added)
- `M` = File exists in both, content differs (modified)
- `D` = File exists in main but not in branch (deleted from main)
- `R` = Renamed (shows as `R100 old-path new-path`)

**Key insight:** If a file was added and later deleted within the branch, it will NOT appear in this diff at all — which is correct, since the NET change is nothing.

### Step 2: Identify Architectural Components

Before listing files, identify the high-level architectural components:
- **Read model**: Cosmos containers, repositories, query patterns
- **Write path**: Index builders, services that write data
- **Configuration**: Settings, form builder UI
- **API layer**: Controllers, endpoints
- **Enhancements**: Optimizations to existing systems (e.g., `GuestAssignment.IndexingComplete`)

### Step 3: Write Background
Focus on the business need — what capability is being added. Do NOT mention previous approaches or what's being replaced.

### Step 4: Write Solution Summary
Describe the architecture in 1-2 sentences using the component names from Step 2.

### Step 5: Document by Component
Group file changes by architectural component rather than listing alphabetically:
```markdown
### File Changes
**Read Model:**
- `PersonSubmissionRepository.cs` (new): Cosmos repository with pagination and filtering
- `PersonSubmissionController.cs` (new): API endpoints for querying

**Write Path:**
- `IndexBuilder.cs`: Added `SubmitterPersonEntryIdUpdate` for computing linked person
- `EntryIndexService.cs`: Integration with write path
```

### Step 6: Document Tests
Group test files by what they cover (write path tests, repository tests, etc.)

### Step 7: Validate
- Opens with a single H1 PR title (`# ...`): concise, imperative, no trailing period, no PR number
- Under 4000 characters
- No journey language (replaced, superseded, previous)
- All identifiers in backticks
- Architecture-first, not file-first
- No em dashes (`—`) anywhere in the description
- Work item(s) referenced as `AB#<WI_ID>` in a final `**Work Items:**` section (if a WI applies); section omitted when none found

### Step 8: Deliver the Description

Decide where the finished description goes based on whether a feature doc directory exists for this work:

1. **Infer the feature doc directory from the conversation.** Look for a feature directory already in play this session (e.g., a `plans/<feature>/` folder, a `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/<feature>/` directory, or a SPEC/PHASES doc location referenced in chat). The directory associated with the current branch's feature is the target.

2. **If a feature doc directory exists:**
   - If a PR description doc already exists there (e.g., `PR_DESCRIPTION.md` or similar), **update it in place** with the new content.
   - Otherwise, **write a new `PR_DESCRIPTION.md`** (or a clearly-named `*-pr-description.md`) into that directory.
   - Tell the user the path you wrote to.

3. **If no feature doc directory can be inferred:** Do NOT write a file. Return the description in a **single fenced code block** for easy copy-paste. Watch the formatting: the description itself contains fenced code blocks and backticks, so wrap the whole thing in a higher-level fence (e.g., a `````md` four-backtick fence) so the inner triple-backtick blocks render correctly inside it.

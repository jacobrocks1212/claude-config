---
# decision 4 (dispatch-guard-denies-workstation-subsubagent-split): this skill's
# contract orchestrates sub-subagents. --cycle-begin copies this capability onto
# the cycle marker so the dispatch guard honors the workstation sub-subagent
# exemption without a hardcoded skill list.
subagent-model: true
name: spec-bug
description: Investigate a complex bug or issue — gather evidence, verify symptoms, produce an investigation spec, then optionally transition to /fix
argument-hint: [bug description, area of concern, or work-item id]
---

# Spec Bug

Structured investigation workflow for bugs and issues that turn out more complex than expected. Gathers all available evidence via parallel subagents, confirms symptoms interactively with the user, and produces an investigation SPEC.md as the source of truth. Optionally transitions into `/fix` for implementation planning.

**When to use:**
- A bug or issue is more complex than initially expected
- You want to document what's known before attempting a fix
- You need to separate verified symptoms from theories
- Before starting work on a tricky issue (proactive investigation)

**User's description:**
$ARGUMENTS

---

## Collaboration Stance (MANDATORY)

!`cat .claude/skill-config/team-architect-stance.md 2>/dev/null || cat ~/.claude/skills/_components/team-architect-stance.md`

---

## Step 1: Context Gathering (Parallel Subagents)

!`cat .claude/skill-config/cog-doc-track-open.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-open.md`

Launch parallel research subagents to collect all available evidence. Each subagent returns structured findings. Adapt the subagent set based on what's available — skip subagents whose data sources don't exist.

If the user's description is (or references) a work-item id, the work-item context subagent (F, below) fetches that item and its related items first, so the rest of the investigation is grounded in what was actually reported.

### Subagent A: Conversation & Session History

**Prompt:** Search for evidence of the issue in recent conversation and session history.

1. Check the current conversation for: error messages, failed commands, unexpected behavior, theories discussed, files mentioned
2. Search `~/.claude-personal/projects/` for recent `.jsonl` session files mentioning relevant keywords
3. Extract: what was attempted, what failed, what was observed, any theories or hypotheses already explored

Report format: chronological list of relevant findings with source attribution.

### Subagent B: Recent Activity

**Prompt:** Check recent git activity for context.

1. Run `git log --oneline -20` and `git diff --stat HEAD~5` to understand recent changes
2. Run `git diff` (unstaged) and `git diff --cached` (staged) to see current uncommitted work
3. Identify: what was recently changed, what skills were used, what files were modified

Report format: timeline of recent work with file lists and commit messages.

### Subagent C: Related Documentation

**Prompt:** Search for existing documentation related to this issue.

1. Read project `CLAUDE.md` for architecture context and known gotchas
2. Search `docs/bugs/` for related bug docs (open and archived)
3. Search `docs/features/` for feature specs that touch the affected area
4. Check subdirectory `CLAUDE.md` files near the affected code

Report format: list of related documents with relevance summary for each.

!`cat .claude/skill-config/spec-bug-runtime-evidence.md 2>/dev/null || cat ~/.claude/skills/_components/spec-bug-runtime-evidence.md`

### Subagent E: Source Code Analysis

**Prompt:** Read the source code in the affected area to understand the current implementation.

1. Based on the bug description, identify the likely affected files and code paths
2. Read the relevant source files end-to-end
3. Identify: control flow, state management, error handling, edge cases
4. Note any code that looks suspicious, fragile, or inconsistent with surrounding patterns

Report format: annotated code path summary with flagged areas of concern.

!`cat .claude/skill-config/spec-bug-work-item-context.md 2>/dev/null || cat ~/.claude/skills/_components/spec-bug-work-item-context.md`

---

## Step 2: Synthesize Findings

After all subagents return, synthesize their findings into three categories:

### 2a. Evidence Inventory

| Source | Key Finding | Confidence |
|--------|------------|------------|
| conversation | ... | high/medium/low |
| git log | ... | ... |
| session logs | ... | ... |
| source code | ... | ... |
| docs | ... | ... |

### 2b. Preliminary Theories

Based on the evidence, form 1-3 hypotheses about root cause. For each:
- **Theory:** one-sentence description
- **Supporting evidence:** what points to this theory
- **Contradicting evidence:** what argues against it
- **Verification method:** how to confirm or rule out

### 2c. Open Questions

List anything that can't be determined from the evidence alone — these become AskUserQuestion items in Step 3.

---

## Step 2.5: Reuse & Convergence Analysis (BLOCKING)

Before verifying symptoms or shaping a fix, inventory the existing systems the fix should build on or converge toward. For a bug, the highest-value finding is often an existing *correct* implementation the buggy code should be refactored to match — not new code.

!`cat .claude/skill-config/reuse-first-discovery.md 2>/dev/null || cat ~/.claude/skills/_components/reuse-first-discovery.md`

---

## Step 3: Verify Symptoms with User

Use **AskUserQuestion** to confirm the user's actual experience. This is critical — don't assume. Each confirmed answer becomes a **verified symptom** in the spec.

Ask about:
- **Observed behavior:** "When you [action], what exactly happens? Is it [description from evidence]?"
- **Expected behavior:** "What should happen instead?"
- **Reproduction:** "Is this consistent or intermittent? Any specific conditions?"
- **Scope:** "Does this affect [related area] too, or just [primary area]?"
- **Timeline:** "When did this start? After a specific change?"

Limit to 2-4 focused questions per round. Continue rounds until symptoms are clear.

Mark each confirmed item as `VERIFIED` in the spec. Mark unconfirmed items as `REPORTED` or `SUSPECTED`.

**`symptom-verified` ≠ `cause-traced` (MANDATORY distinction).** These status tags describe a
**symptom** — an observed behavior confirmed with the user. A `[VERIFIED]` symptom means *the
symptom is real*; it says **nothing** about *why* it happens. A causal finding ("symptom X is
produced by value/code Y") is a separate claim carrying its own label — `traced` (serving-path
chain cited `file:line`, fix-site-on-path shown) or `asserted` (hypothesis). **Never let a
`[VERIFIED]` symptom upgrade an `asserted` cause to fact** — that laundering is the exact 57585
failure. Symptom verification and cause tracing are enforced separately: symptoms here in Step 5,
causes by the root-cause trace gate at Step 6.

---

## Step 4: Determine Placement

Infer whether this belongs in `docs/features/` or `docs/bugs/` based on context:

**Signals for `docs/bugs/`:**
- A previously working behavior is now broken
- The issue is a regression
- There's no associated feature spec
- The user describes it as a bug, error, or broken behavior

**Signals for `docs/features/`:**
- The issue is within an in-progress feature (has an existing SPEC.md or PHASES.md)
- The "bug" is really a missing or incomplete implementation
- The user is investigating behavior for a planned feature

**If ambiguous**, use **AskUserQuestion:**
> "This issue touches [area]. Should I file this as a bug investigation (`docs/bugs/`) or as part of a feature spec (`docs/features/[group]/`)?"

### Directory creation

- **Bug:** `docs/bugs/{bug-dir}/SPEC.md` — name `{bug-dir}` per the repo's `docs/bugs/CLAUDE.md` naming convention (e.g. `<WI_ID>-<slug>` where bugs map to work items, or a descriptive `<slug>` otherwise). Read that file first; do not assume a fixed format.
- **Feature:** `docs/features/{group}/{feature-slug}/SPEC.md` — use existing feature directory if one exists, or create new

For bugs, also create the standard bug doc header fields alongside the investigation spec format.

---

## Step 5: Write the Investigation SPEC

Write the SPEC.md with this structure. Before writing, run `git branch --show-current`: if the result matches `^p/`, stamp `**Branch:** \`<branch>\`` into the header (after `**Related:**`); if on `main`/`master` or any non-`p/` branch, omit the `**Branch:**` line — the branch may not yet exist at spec time, and `/spec-phases` is the primary stamp point.

```markdown
# {Title} — Investigation Spec

> One-line summary of the issue.

**Status:** Investigating
**Severity:** {P0 | P1 | P2 | Low}
**Discovered:** {today's date}
**Placement:** {docs/bugs or docs/features path}
**Related:** {links to related specs, bugs, or phases}
**Branch:** `{p/* branch — omit if not yet on a work branch}`

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug
                    (which authors PHASES.md from this concluded spec) instead of re-running
                    /spec-bug.  Set this when the investigation is complete and ready for
                    implementation planning.
-->

---

## Verified Symptoms

<!-- Each symptom confirmed directly with the user via AskUserQuestion -->

1. **[VERIFIED]** {symptom description} — {how confirmed}
2. **[VERIFIED]** {symptom description} — {how confirmed}
3. **[REPORTED]** {unconfirmed symptom} — {source}

## Reproduction Steps

<!-- MUST be a concrete, followable recipe — exact command, HTTP call, or manual UI steps —
     NOT free prose. This is the artifact the symptom-reproduction gate
     (_components/symptom-reproduction-gate.md) binds to at completion: the serving-path
     regression test / runtime artifact that proves the ORIGINAL symptom is gone maps back to
     these steps. A SPEC whose repro is vague prose (no runnable/followable steps) blocks that
     completion gate — write steps someone else could execute verbatim. -->

1. {exact step — command / HTTP call / UI action}
2. {exact step}
3. {observed result at the reported surface}

**Expected:** {what should happen}
**Actual:** {what does happen}
**Consistency:** {always | intermittent | conditions}

## Evidence Collected

### Source Code
{Annotated code path findings from Subagent E}

### Runtime Evidence
{Session log findings, error events, anomalies from Subagent D}

### Git History
{Recent changes, relevant commits from Subagent B}

### Related Documentation
{Existing specs, bug docs, CLAUDE.md entries from Subagent C}

## Theories

### Theory 1: {name}
- **Hypothesis:** {description}
- **Supporting evidence:** {list}
- **Contradicting evidence:** {list}
- **Status:** Unverified | Likely | Confirmed | Ruled Out

### Theory 2: {name}
...

## Proven Findings

<!-- Move theories here as they are confirmed or ruled out -->

{findings confirmed through investigation}

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| ... | ... | ... |

## Open Questions

- {question that needs further investigation}
```

If the spec becomes large (>200 lines), split supplementary evidence into a sibling `EVIDENCE.md` file and reference it from the main SPEC.

---

## Step 6: Transition to /fix

After writing the spec, present a summary to the user:

> **Investigation spec created at `{path}`.**
>
> **Verified symptoms:** {count}
> **Theories:** {count} ({confirmed count} confirmed)
> **Severity:** {severity}
>
> Ready to create a fix plan?

**Concluding the investigation — status transition (MANDATORY):**

**Root-cause trace gate (SEAM A — HARD BLOCK, runs BEFORE the status flip):**

!`cat ~/.claude/skills/_components/root-cause-trace-gate.md`

Apply the gate above before flipping `Investigating → Concluded`: for each causal finding this
SPEC intends to lock, the symptom's serving path must be **`traced`** (chain cited `file:line`,
fix-site-on-path shown), not merely **`asserted`**. An `asserted` link may NOT conclude this SPEC
— interactive: refuse and name the untraced link; `--batch`: write `NEEDS_INPUT.md`
(`written_by: root-cause-trace-gate`) and STOP. Do not proceed to the transition below until the
finding is `traced`.

When the investigation reaches a proven conclusion — root cause identified, affected area understood, theories confirmed or ruled out — you MUST update the SPEC's `**Status:**` line from `Investigating` to `Concluded` before stopping or transitioning. This is the signal that `bug-state.py` uses to route to `/plan-bug` (which authors `PHASES.md`) rather than re-dispatching `/spec-bug`. Leaving it as `Investigating` causes `bug-state.py` to loop `/spec-bug` indefinitely.

**Interactive path:** When the user chooses "Create fix plan now" or "Not yet" and the investigation has reached a clear conclusion, flip `**Status:** Investigating` to `**Status:** Concluded` in the SPEC before proceeding.

**Batch/non-interactive path** (`--batch`, as dispatched by `/lazy-bug-batch`): Use this rule:
- If the investigation reached a **proven conclusion** (root cause identified, sufficient findings for fix planning): write the SPEC with `**Status:** Concluded`. The pipeline will advance to `/plan-bug` on its next cycle.
- If the investigation did **NOT** conclude (needs more evidence, an ambiguous root cause, or a human decision required): leave `**Status:** Investigating` and write `NEEDS_INPUT.md` explaining what is still unresolved. **This pre-conclusion sentinel MUST carry `stub_origin: true` in its frontmatter** (stub-origin-provisional-exclusion): the root cause the fix would build on is unconfirmed, so the decisions are foundation-shaping and permanently excluded from `--park-provisional` auto-acceptance — they always park for the operator. (Sentinels written AFTER the investigation concluded do not carry the marker.) Do NOT falsely mark `Concluded` — a premature `Concluded` causes `/plan-bug` to fabricate phases from incomplete findings, which is worse than pausing.

Use **AskUserQuestion** (interactive only):
- **"Create fix plan now"** — Flip SPEC to `**Status:** Concluded`, then invoke the `fix` skill, passing the SPEC path and a synthesized bug description derived from the verified symptoms and strongest theory
- **"Not yet"** — Flip SPEC to `**Status:** Concluded` (investigation is done), then stop. The spec is the deliverable.
- **"Need more investigation"** — Do NOT flip status; return to Step 3 for additional symptom verification or Step 1 to gather more evidence

When transitioning to `/fix`, pass the investigation spec path so `/fix` can read verified symptoms and proven findings instead of re-investigating from scratch.

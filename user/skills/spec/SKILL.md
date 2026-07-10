---
description: Brainstorm, research, and draft a feature spec
argument-hint: [feature description or work-item id]
allowed-tools: ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "AskUserQuestion", "Agent", "WebSearch"]
name: spec
---

# Feature Spec Workflow

You are helping the user create a new feature specification. This is a **3-phase** interactive workflow. Follow each phase strictly — do not skip ahead.

**User's feature description:**
$ARGUMENTS

---

## Collaboration Stance (MANDATORY)

!`cat .claude/skill-config/team-architect-stance.md 2>/dev/null || cat ~/.claude/skills/_components/team-architect-stance.md`

---

## Global Rule: Chat-Presented Options MUST Match the Picker 1:1 (HARD REQUIREMENT)

This skill repeatedly uses a "surface full context in chat, THEN call `AskUserQuestion`" pattern (Step 1b.4/1b.5, Step 1c brainstorming, Phase 3 Step 4/5). Whenever you do this, the chat block is the **expanded explanation OF the picker** — never a different or larger set of choices.

**The questions and options in the chat block MUST correspond 1:1 and verbatim with the questions and options you pass to `AskUserQuestion`:**

- **Same number of questions**, in the same order.
- **Same number of options per question**, in the same order.
- **Same labels/titles** — each picker `label` must be the exact chat option label, or a length-truncated shortening of it (never a re-worded or different label).
- **Same recommendation** — the option you recommend in chat must be the same option flagged/highlighted in the picker.
- **Recommended option FIRST (HARD REQUIREMENT).** The recommended option MUST be listed FIRST (option A / position 1) in BOTH the chat block and the `AskUserQuestion` picker, with `(Recommended)` appended to its label. Never recommend an option (e.g. "Recommendation: C") while listing it second or third — that mismatch is the exact defect this rule forbids. If you change which option you recommend, you MUST reorder it to the top of BOTH the chat block and the picker — and move the `(Recommended)` suffix with it — BEFORE calling `AskUserQuestion`. Chat and picker must agree on the set/order of options AND on which one sits at position 1.

The **only** allowed differences are unavoidable picker-length truncations: (a) a picker `label` may be a shortened form of the chat option's bolded label, and (b) a picker option `description` may be truncated relative to the chat's full pros/cons. The *set* of choices must be identical.

**If you revise the questions or options after writing the chat block, you MUST rewrite the chat block to match BEFORE calling `AskUserQuestion`.** A chat block that presents 3 options and a picker that offers 4 (or differently-worded options, or a different recommendation) is a defect — it confuses the user, who reads the rich chat block and then sees a mismatched picker. Re-read your chat block against your `AskUserQuestion` payload immediately before the call and confirm they match.

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation (typically from `/lazy-batch` / `/lazy-batch-cloud`). Batch mode drives **Phase 1 (baseline brainstorm), Phase 2 (research-prompt generation), and Phase 3 (research integration)** autonomously — the loop advances on its own and pauses only when a genuine *product-behavior* decision needs the user. The mechanism is uniform across Phase 1 and Phase 3: do the mechanical work autonomously, auto-accept mechanical-internal decisions, and surface product-behavior decisions via `NEEDS_INPUT.md` — which `/lazy-batch`'s Step 1g resolves with `AskUserQuestion` and then resumes (it does NOT halt the run). Phase 2 is purely mechanical: it writes `RESEARCH_PROMPT.md` and returns; the `needs-research` gate is what pauses the loop for Gemini.

**Per-phase eligibility for `NEEDS_INPUT.md`** (per the halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`):

| Phase | When | Pre/post research | May write `NEEDS_INPUT.md`? |
|-------|------|--------------------|------------------------------|
| Phase 1 (brainstorming) | First `/spec` invocation (no SPEC.md) | Pre-research | **Yes — for product-behavior decisions that GATE the baseline** (scope / ownership / core UX / user-facing defaults). These are user-authority calls research can never answer. Auto-accept mechanical-internal decisions. **Research-*answerable* questions go into `RESEARCH_PROMPT.md` (Phase 2), never `NEEDS_INPUT.md`.** A true "can't proceed at all" → `BLOCKED.md` with `blocker_kind: pre-research-input-required`. See "Phase 1 under `--batch`" below. |
| Phase 2 (research prompt generation) | SPEC.md exists, no RESEARCH.md | Pre-research | **No** — runs mechanically, writes `RESEARCH_PROMPT.md`, returns. Placeholder open questions go INTO the prompt for Gemini to answer; never lift them via `NEEDS_INPUT.md`. The `needs-research` gate pauses the loop. |
| Phase 3 (research integration) | SPEC.md + RESEARCH.md both present | **Post-research** | **Yes — MANDATORY for product-behavior decisions, even when a strong recommendation exists.** See "Phase 3 under `--batch`" below for the always-halt rule and the product-behavior vs. mechanical-internal classification. |

Detect Phase context: examine `{spec-dir}/{feature-slug}/`:
- No SPEC.md → Phase 1 (autonomous brainstorm contract below)
- SPEC.md exists, no RESEARCH.md → Phase 2 (mechanical research-prompt generation below)
- SPEC.md + RESEARCH.md both present → Phase 3 finalization (below)

**Phase 1 under `--batch`:**

Phase 1 is normally an interactive brainstorm. Under `--batch` it runs autonomously with the SAME product-behavior contract Phase 3 uses, so the loop advances until a decision the user must own surfaces — then pauses via `NEEDS_INPUT.md` / Step 1g rather than hard-halting.

1. **Do the mechanical Phase 1 work autonomously** (no `AskUserQuestion`): Phase 0 project-context discovery, the Step 1b dependency-block search (upstream + downstream), and the Step 1c one-shot Atomic Decomposition Gate. These are analysis, not preference — complete them and record the results in the draft.
2. **Draft the baseline `SPEC.md`** (the same structure Phase 3 finalizes later). Auto-accept every **mechanical-internal** decision using the single defensible option. For each unresolved **product-behavior** decision, write an explicit `## Open Questions` entry / inline `TBD (pending input)` marker — do NOT invent an answer. **Writing the draft is required** (this DIVERGES from Phase 3's "do not write a half-finished SPEC.md" rule, which holds only because in Phase 3 SPEC.md already exists): in Phase 1 the draft must exist on disk so the Step 1g apply-resolution subagent has a document to propagate the user's answers into. **Stamp the mandatory `**Friction-reduction feature:** {yes|no}` classification line** into the draft header (friction-kpi-registry measurability gate — see Step 8.5); a `yes` also owes a `## KPI Declaration` section (name registry row ids and/or draft new rows). The full gate runs at the Phase 3 Step 8.5 finalization checkpoint, but the classification line must be present from the baseline draft on.
3. **Classify every Phase 1 decision** as `product-behavior` or `mechanical-internal` using the definitions in "Phase 3 under `--batch`" below, then route by class:
   - **`product-behavior` decisions that GATE the baseline** (scope: what's in v1; ownership: which subsystem owns this; core UX shape; user-facing defaults) → collect into `NEEDS_INPUT.md` (Halt protocol below). These are user-authority calls research cannot decide, so they are NOT deferred into the research prompt. **The Phase-1 sentinel MUST carry `stub_origin: true` in its frontmatter** (stub-origin-provisional-exclusion): these decisions shape a baseline the operator has never seen, so they are permanently excluded from `--park-provisional` auto-acceptance — they always park for the operator. (Post-research Phase-3 sentinels do NOT carry the marker; that baseline is operator-locked.)
   - **research-answerable questions** (prior art, technical tradeoffs, industry conventions, "what do similar products do") → do NOT write `NEEDS_INPUT.md`. Leave them as `## Open Questions` in the draft; Phase 2 harvests them into `RESEARCH_PROMPT.md`.
   - **`mechanical-internal`** → auto-accept silently.
4. **Cap the `NEEDS_INPUT.md` round at the top 4 gating decisions** (sentinel schema cap). If more than 4 product-behavior decisions gate the baseline, surface the top 4 by impact and record the rest as `## Open Questions` — they resurface in Phase 3's post-research rounds (which support multiple rounds). **Phase 1 gets a single `NEEDS_INPUT.md` round**, because once `SPEC.md` exists the next probe routes to Phase 2.
5. **If NO product-behavior decision gates the baseline** (the brief is unambiguous on scope / ownership / UX), finalize the baseline draft and return normally — the next cycle advances to Phase 2. Note this in your Phase 1 summary ("no gating decisions; auto-drafted baseline").
6. **Genuine blocker** — the brief is so ambiguous that even a placeholder baseline + research prompt cannot be drafted → write `BLOCKED.md` with `blocker_kind: pre-research-input-required`. This is the ONLY Phase 1 path that halts the run; reserve it for true "can't proceed at all," not "pick option A or B" (which is `NEEDS_INPUT.md`).

This contract **REPLACES** Phase 1's interactive brainstorming loop: run the mechanical sub-steps below (Step 1a "Understand Before Architecting", Step 1b dependency search, Step 1c's one-shot Atomic Decomposition Gate) but do NOT run Step 1c's iterative `AskUserQuestion` refinement rounds or any other `AskUserQuestion` in Phase 1 — the baseline draft (step 2) plus the single `NEEDS_INPUT.md` round (step 4) are how a batch run captures the choices a human would otherwise make in those rounds.

**Phase 2 under `--batch`:**

Phase 2 is mechanical — it generates `RESEARCH_PROMPT.md`. Under `--batch`, run Phase 2 to completion exactly as interactive mode does (compose the prompt, apply the identity prepend if present, length-check), then **return normally instead of the interactive "STOP and wait for the file path."** Do NOT write `NEEDS_INPUT.md` and do NOT refuse — placeholder open questions go INTO the research prompt for Gemini. The orchestrator's next probe sees `RESEARCH_PROMPT.md` with no `RESEARCH.md` and halts the loop at the `needs-research` gate, which is where the user runs Gemini and supplies the results.

**Phase 3 under `--batch`:**

- **Skip the chat-visible "Open Decisions" block.** No human will read it — `/lazy-batch` runs without a chat audience. The rich `## Decision Context` body inside `NEEDS_INPUT.md` (see Halt protocol below) is what reaches the user via the orchestrator's re-print + `AskUserQuestion` flow.
- **Classify every Phase 3 decision as `product-behavior` or `mechanical-internal`** before considering whether to auto-accept. The classification dictates the halt requirement:
  - **`product-behavior`** — the decision changes anything the user sees, does, or experiences: UX shape, scope (what's in v1 vs later), user-facing functionality, workflow, defaults, copy, naming visible to the user, error/empty states, data the user inputs or sees, surfaces the user interacts with. Decisions that affect *what the feature does for the user* are product-behavior regardless of how strong your recommendation is.
  - **`mechanical-internal`** — the decision is invisible to the user: which internal helper to use, file placement, naming of internal symbols, internal library choice with no behavioral implications, code-organization tradeoffs, internal data structure choices that don't change the user-facing contract.
- **Product-behavior smells — concrete checklist (always classify as `product-behavior` if any apply; non-exhaustive):**
  - **Defaults** the user sees on first run (initial values, pre-selected options, baseline configuration).
  - **Scope of v1** — which subfeature ships now vs deferred, what controls/surfaces are exposed initially. ("Ship Open by default vs Quantized by default" is the canonical example: research can recommend, but the v1 default is a product call.)
  - **UX shape** — which UI surface the feature lives in, the gesture/hotkey/menu it's accessed from, what's a control vs a hidden internal.
  - **Copy / labels / names** visible to the user.
  - **Error and empty states** — what the user sees when X fails, is unset, or returns nothing.
  - **Workflow shape** — how many steps, ordering, what's optional vs required.
  - **Data the user inputs or sees** — field shapes, formats, units, precision, display rounding.
  - **Configurability boundary** — "this should be user-tunable" vs "this should be fixed in code" is itself a product-behavior call.
  - **Research-multi-option calls** — when research surfaces multiple defensible options at a user-visible level (e.g. "industry uses A or B; here are the tradeoffs"), the *which* is product-behavior even when the recommendation is strong.
  - **Toggles between behavioral modes** — any v1/v2 split, any "configurable vs hard-coded" question, any "shipped continuous vs quantized / opt-in vs opt-out / on by default vs off by default" question.

  **Rule of thumb:** if removing the decision from SPEC.md would change what the user experiences in the running product, it is `product-behavior`. A strong `**Recommendation:**` line does NOT downgrade the classification — under `--batch` the recommendation is preserved as the lead option in the `NEEDS_INPUT.md` `## Decision Context` body and surfaces as the highlighted chip in `AskUserQuestion`.

- **HALT RULE (always-halt on product-behavior):**
  - If **any** Phase 3 decision classifies as `product-behavior`, **halt with `NEEDS_INPUT.md`** that covers all such decisions (capped at 4 per the sentinel schema; if there are more than 4, surface the top 4 by impact and note the rest in the body for a follow-up cycle). Do this **regardless** of how strong your `**My recommendation:**` line is — the user retains final authority over product behavior, and the orchestrator's `AskUserQuestion` surfaces your recommendation alongside the alternatives so the user can confirm or override. Auto-accepting a strong product-behavior recommendation silently is **forbidden** under `--batch`.
  - If **every** Phase 3 decision is `mechanical-internal` AND each has a single defensible recommendation, accept silently and proceed to finalize SPEC.md. This is the only path that skips the halt. If even one mechanical-internal decision is genuinely ambiguous (no clear recommendation), include it in the `NEEDS_INPUT.md` alongside the product-behavior items.
  - If you reach Phase 3 and there are **no decisions at all** (research confirmed the baseline spec without surfacing any new choices), proceed silently. This is rare but legitimate — surface this case in your Phase 3 summary so the orchestrator's cycle log reflects "no decisions surfaced; auto-finalized".
- **Skip every `AskUserQuestion`** in Phase 3 — the orchestrator-side `AskUserQuestion` (driven by the `NEEDS_INPUT.md` rich body) is the user-facing picker. The skill's job under `--batch` is to write the sentinel, not to prompt.
- The Phase 3 finalization checkpoint (Step 8 in Phase 3 — Depends-on dep-block validation) still runs. If the dep block fails validation, that's a hard error, not an ambiguity; surface it and STOP (do not write SPEC.md).
- The cross-boundary validation (Step 9) still runs. Unverified quantities should be marked `(estimated — verify during Phase N)` as in interactive mode.

**Why always-halt on product-behavior:** the autonomous tail is allowed to make mechanical decisions on the user's behalf (helpers, naming, file placement) because those don't change what the product does. Product-behavior decisions DO change what the product does — and the user has explicitly reserved final authority over them. A strong recommendation is still surfaced (it becomes the **Recommendation** line under each `## Decision Context` H3, and a chip option in `AskUserQuestion`), but the user gets to confirm before SPEC.md is finalized in a shape that bakes the choice in.

**Decision-Classification Ledger (MANDATORY return under `--batch` — Phase 1 and Phase 3):**

Every `/spec --batch` cycle MUST emit, as a structured section of its return summary back to the orchestrator, a ledger of every decision the cycle considered (whether baked in, deferred to research, or surfaced via `NEEDS_INPUT.md`). The ledger is the audit signal that the classification step actually ran — `/lazy-batch` and `/lazy-batch-cloud` dispatch a dedicated Opus **input-audit subagent** after the cycle (see their Step 1d.5) that verifies your ledger against the SPEC.md diff and writes its own `NEEDS_INPUT.md` if it finds product-behavior decisions you classified as `mechanical-internal` (or omitted from the ledger entirely). Treat the ledger as a hard contract, not a courtesy.

Format (markdown table embedded in the return summary):

```
### Decision-Classification Ledger

| # | Decision (one line) | Classification | Chosen option | Surfaced via | Rationale |
|---|---------------------|----------------|---------------|--------------|-----------|
| 1 | <decision title>    | product-behavior \| mechanical-internal | <option taken or "deferred to user"> | NEEDS_INPUT.md \| auto-accept \| RESEARCH_PROMPT.md \| Open Questions | <one-line why> |
| 2 | ...                 | ...            | ...           | ...          | ...       |
```

- **Every** decision you made or actively *chose not to make* on the user's behalf belongs in the ledger — not just the controversial ones. Boring mechanical-internal calls (helper placement, internal symbol naming) are still ledger rows; their `Surfaced via: auto-accept` is what the audit checks for incorrectly-classified product calls hiding in the mechanical pile.
- If you classified a decision as `product-behavior`, the `Surfaced via` column MUST be `NEEDS_INPUT.md` (or `Open Questions` if it overflowed the 4-cap and was deferred to a follow-up cycle). Any row with `product-behavior` + `auto-accept` is a self-declared contract violation — don't write it; surface the decision properly.
- If the cycle made **zero** decisions (research confirmed the baseline without surfacing any new choices), emit the ledger heading + a `_(no decisions surfaced this cycle — auto-finalized)_` line. The empty ledger is still required.
- The ledger lives in the **return-to-orchestrator summary**, not in SPEC.md. Do not commit it as a document; the orchestrator reads it from the cycle subagent's response.

**Halt protocol — `NEEDS_INPUT.md`** (shared by Phase 1 and Phase 3):

When at least one decision must be surfaced to the user:

- **In Phase 3**, do NOT write a half-finished SPEC.md — SPEC.md already exists, and the apply-resolution subagent edits it in place after the user answers.
- **In Phase 1**, you HAVE already written the baseline draft per "Phase 1 under `--batch`" step 2 (with the gating product-behavior decisions left as `TBD (pending input)` / `## Open Questions`). That draft is what the apply-resolution subagent propagates the answers into. Do NOT bake an invented answer into the draft for any decision you are surfacing here.

Then, in either phase:

1. Compute `{spec-dir}/{feature-slug}/NEEDS_INPUT.md`.
2. Write the sentinel per the canonical schema in `~/.claude/skills/_components/sentinel-frontmatter.md`. The frontmatter shape is the standard `kind: needs-input` schema; the markdown body MUST use the **rich-body convention** (`## Decision Context` H2 with one H3 per `decisions[i]`) defined in that component. Frame each option with concrete tradeoffs (cost / complexity / risk / reversibility) and include a `**Recommendation:**` line. The orchestrator re-prints this body verbatim to chat before calling `AskUserQuestion`, whose option descriptions are truncated.

   Skeleton (see the component for the full template):

   ```markdown
   ---
   kind: needs-input
   feature_id: {feature-slug}
   written_by: spec
   decisions:
     - <one-line description of decision 1>
     - <one-line description of decision 2>
   date: {today}
   next_skill: spec
   ---

   # /spec --batch — Needs Input

   ## Decision Context

   ### 1. <one-line decision title — must equal decisions[0] verbatim>

   **Problem:** <2-4 sentence framing; cite the research finding or spec
   section that surfaced the choice.>

   **Options:**
   - **<option A>** — <description with tradeoffs.>
   - **<option B>** — <description with tradeoffs.>

   **Recommendation:** <option A or B> — <one-sentence justification.>

   ### 2. <next title matching decisions[1]>
   ...
   ```

3. **Echo the entire `## Decision Context` section to chat output** before returning — see the "Producer responsibilities" subsection in `sentinel-frontmatter.md`. This gives the user visibility during the batch loop without scrolling back through orchestrator state.
4. STOP. Do not call `AskUserQuestion`. Do not write SPEC.md. The orchestrator (`/lazy-batch`) sees the sentinel on the next state-machine cycle, re-prints the rich body, and surfaces the picker.

Strip `--batch` from `$ARGUMENTS` before processing the rest of this skill so phase-detection logic and other paths work unchanged.

---

## Task Tracking (MANDATORY — DO NOT SKIP)

!`cat .claude/skill-config/cog-doc-track-open.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-open.md`

Before any work, load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Phase 0: Project context discovery", description: "Read CLAUDE.md, find spec directory, read related specs" })`
2. `TaskCreate({ subject: "Phase 1: Brainstorm baseline spec", description: "Interactive brainstorming, iterative spec drafting" })`
3. `TaskCreate({ subject: "Phase 2: Research prompt", description: "Draft and save Gemini deep research prompt" })`
4. `TaskCreate({ subject: "Phase 3: Finalize spec", description: "Integrate research, finalize SPEC.md, cross-boundary validation" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

---

## Phase 0: Project Context Discovery

!`cat .claude/skill-config/spec-evidence-gathering.md 2>/dev/null || cat ~/.claude/skills/_components/spec-evidence-gathering.md`

After the evidence-gathering fleet returns, synthesize its findings alongside the steps below.

Before starting, understand the project:

1. Read `CLAUDE.md` (if exists) to understand current architecture and constraints.
2. Find where specs/docs live:
   - Check for `docs/features/`, `docs/specs/`, `specs/`, or `docs/` directories
   - If none exist, propose creating `docs/specs/` and confirm with user
3. Read any existing specs that relate to the proposed feature — avoid contradictions.
4. Identify the tech stack and key constraints from the codebase.

---

## Phase 1: Brainstorm the Baseline Spec

**Goal:** Nail down the core feature concept, scope, and key design decisions through interactive dialogue.

### Step 1a: Understand Before Architecting

Before asking about architecture, technology, or infrastructure, ensure you understand what's actually being built and why. The depth of this step depends on the feature:

- **Automating existing workflows:** Ask the user (or end user, if the developer is a proxy) to describe the current process step by step. Understand where time is lost and what requires human judgment vs. what's mechanical. If the developer is building for someone else, ask for the end user's own description — summaries often miss the real pain points.
- **New capabilities (no existing workflow):** Clarify the desired outcome and key interactions. What does success look like from the user's perspective?
- **Technical/infrastructure features:** Clarify the constraints and integration points. Workflow interviews don't apply here.

Do NOT make architecture or technology decisions until the problem space is understood.

### Step 1b: Resolve Dependencies and Dependees (BLOCKING — before architecture brainstorm)

Before brainstorming architecture, perform an **explicit mechanical search** across all existing specs to identify (a) upstream features this one depends on, and (b) existing downstream features that depend on this one (relevant when this is a re-spec or expansion of a stub). The dependency block is a **hard checkpoint** — Phase 3 will refuse to finalize SPEC.md without it.

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Do NOT skip the mechanical search and rely on intuition or Phase 0 context alone — that's exactly how dep blocks drift into "(none)" when there are real deps. Run every step below.

#### 1b.1. Enumerate the candidate set (mechanical)

1. **List all existing SPEC.md files.** Use the spec directory resolved in Phase 0:
   ```bash
   # Algobooth-style layout
   ls {spec-dir}/*/SPEC.md 2>/dev/null
   # Generic fallback
   find {spec-dir} -name SPEC.md -not -path "*/{this-feature-slug}/*"
   ```
   Skip the feature being authored (if a directory already exists for it).

2. **Read queue/ROADMAP if present.** If `docs/features/queue.json` exists, read it to map feature-id → directory and tier. If `docs/features/ROADMAP.md` exists, read it to learn which features are Complete vs. pending — `hard` deps on Complete upstreams will trigger reality-check via `/realign-spec` in `/lazy` Step 4.6.

3. **Read any project-level dependency catalog** if it exists (e.g., `docs/features/dependency-audit.md`). These pre-classify coupling between features and are gold for candidate selection.

#### 1b.2. Search for upstream dependencies (what THIS feature consumes)

For each candidate SPEC found in 1b.1, identify whether the new feature depends on it. Use both keyword search and section reading:

1. **Extract load-bearing terms** from the user's feature request and Phase 0 synthesis: API names, data types, subsystem names, capability terms. List them.

2. **Grep across all candidate SPECs** for those terms:
   ```bash
   # For each load-bearing term:
   grep -l -i "<term>" {spec-dir}/*/SPEC.md
   ```
   Record matches.

3. **Grep across candidate SPECs for things they EXPOSE** that this feature might consume. Common exposure patterns:
   ```bash
   grep -l -E "^## (Public API|Exposes|Surface|Exports|Provides|IPC|MCP Tools)" {spec-dir}/*/SPEC.md
   grep -l -E "(provides|exposes|exports|publishes|emits|owns)" {spec-dir}/*/SPEC.md
   ```

4. **For each matching SPEC**, open it and read the Executive Summary, Technical Design, and any "Public API"/"Exposes" sections. For each, decide:
   - Does the new feature's design require something this upstream provides? If yes → candidate dep.
   - Classify kind:
     - **hard** — new feature's design hinges on the upstream's concrete contract (API shape, schema, IPC channel). Phase planning will need to read this upstream's PHASES.md.
     - **soft** — new feature needs the upstream to exist but not its impl specifics.
     - **composes** — new feature builds atop the upstream as a peer/extension.
   - Capture a one-sentence reason (used for the dep block's reason field).

#### 1b.3. Search for downstream dependees (what depends on THIS feature)

If this is a re-spec, stub expansion, or expansion of an existing concept, downstream features may already declare a dep on this feature. Surface them so the user knows what will need updating if this SPEC changes contract shape.

1. **Determine the feature-id** for this feature (kebab-case of the name).

2. **Grep all existing SPECs' Depends-on blocks** for this id:
   ```bash
   # Find SPECs that reference this feature-id in their dep block:
   grep -l -E "^- {feature-id} — (hard|soft|composes)" {spec-dir}/*/SPEC.md
   ```
   Also try common variants of the feature-id if the new name might already be referenced under a different slug.

3. **Grep advanced-feature catalogs and research summaries** for the feature-id or its keywords:
   ```bash
   grep -l -i -E "<feature-id>|<load-bearing-terms>" docs/features/*RESEARCH*.md docs/features/*AUDIT*.md 2>/dev/null
   ```

4. For each downstream dependee found, record: `feature-id`, the kind they declared, and the file path. These are not added to the new SPEC's Depends-on block — they're recorded as a side note for the user.

#### 1b.4. Present findings in chat (BEFORE AskUserQuestion)

Surface a single chat-visible block before any picker. The picker UI truncates option descriptions, so the user must see the full evidence inline. Use this structure:

```
## Dependency Search Results

### Upstream candidates (would go into this feature's Depends on: block)

| Feature-id | Kind | Reason | Evidence (file:section) | Confirm? |
|------------|------|--------|--------------------------|----------|
| <id> | hard | <one sentence> | <path>:<section heading> | recommend yes |
| <id> | soft | <one sentence> | <path>:<section heading> | recommend yes/no |
...

(If zero candidates after the search, write: "No upstream dependencies found. Dep block will be `**Depends on:** (none)`.")

### Existing downstream dependees (other SPECs already depending on this feature-id)

| Downstream feature-id | Kind they declared | File |
|-----------------------|--------------------|------|
| <id> | hard | <path>/SPEC.md |
...

(If zero, write: "No existing dependees — this is a leaf or greenfield feature.")

**Implication if contract shifts during this /spec:** the dependees listed above will need to be reality-checked by `/realign-spec` (which `/lazy` runs automatically). No action needed now — just noting it.
```

#### 1b.5. Confirm via AskUserQuestion (only if non-obvious)

If the upstream candidate set has any rows the user might want to add/remove/reclassify, use `AskUserQuestion` to confirm:
- One question per ambiguous candidate, with options like "Keep as hard", "Reclassify as soft", "Drop — not a real dep".
- If every candidate is unambiguous (clear hard deps with strong evidence), skip the picker and proceed.

**HARD REQUIREMENT — match the chat block 1:1.** The candidate rows and per-candidate options you present in the 1b.4 chat block MUST correspond verbatim (modulo picker-label truncation) to the questions and options you pass to `AskUserQuestion` here: same number of questions, same number of options per question, same labels in the same order, same recommendation. If you reclassify or drop a candidate after writing the 1b.4 block, rewrite that block to match before calling the picker. See the **Global Rule** at the top of this skill.

Do NOT ask about dependees — they're informational, not authored here.

#### 1b.6. Record the dep block immediately

Write the confirmed dep block into the in-progress SPEC.md draft using the schema's Form A or Form B verbatim. Treat it as a first-class section, not a TBD placeholder. It will iterate alongside the rest of the spec during brainstorming, but the *shape* must be correct from this point forward.

If you find yourself wanting to defer this ("we'll figure out deps later"), STOP. Deferral is how the look-back mechanism breaks. Lock in the best-evidence block now; revise as brainstorming surfaces new dependencies.

### Step 1b.7: Reuse-First Discovery (BLOCKING — before architecture brainstorm)

Dependencies are resolved; now inventory what already exists *inside* the boundary before designing anything new. This is the load-bearing planning step — exhaust reuse candidates before proposing new code.

!`cat .claude/skill-config/reuse-first-discovery.md 2>/dev/null || cat ~/.claude/skills/_components/reuse-first-discovery.md`

### Step 1c: Brainstorm Architecture & Scope

**Atomic Decomposition Gate (one-shot — run once, before iterative brainstorming begins):**

Before locking in any design decisions, apply first-principles decomposition to the load-bearing terms in the user's feature request and your synthesized understanding from Step 1a. Run this *once* at the start of Step 1c — do NOT repeat per brainstorming round. Surface the decomposition to the user as part of your synthesis so any ambiguity in goals like "simple", "scalable", "robust", "fast", "secure", or domain-specific jargon is resolved before scope and architecture get committed to writing.

!`cat ~/.claude/skills/_components/atomic-thinking.md`

After the decomposition, proceed with iterative brainstorming below.

1. Synthesize your understanding of the feature request and related context.
2. Use `AskUserQuestion` to iteratively refine the spec. **Ask about the problem and desired outcomes before infrastructure details:**
   - **Desired outcomes** — What should the experience look like?
   - **Scope boundaries** — What's in v1 vs future? What's explicitly out of scope?
   - **Technical constraints** — Platform differences? Performance concerns? Integration with existing systems?
   - **Design decisions** — Where there are multiple valid approaches, present options with tradeoffs.
   - **Infrastructure details** — Runtime, repo structure, package manager, etc.
   - **Edge cases** — What happens in unusual scenarios?
3. **Iteratively update the SPEC file** as decisions are locked in. Don't wait until the end — write to `{spec-dir}/{feature-slug}/SPEC.md` after each brainstorming round with confirmed decisions. Mark undecided items as "TBD" or "Open Question".
4. Continue brainstorming rounds until the user signals they're satisfied with the baseline.
5. Summarize the agreed-upon baseline spec clearly before moving to Phase 2.

**Rules for brainstorming:**
- Ask 2-4 focused questions per round (not more).
- Present concrete options where possible — don't ask open-ended "what do you think?" questions.
- **Surface full option context in chat BEFORE calling `AskUserQuestion`.** The picker UI truncates option descriptions (~80 chars on mobile), so the user cannot make an informed decision from labels alone. For every multi-option question you are about to ask, first write a chat-visible block containing: (a) the question and why it matters now, (b) each option as a bullet with a 1-2 sentence description, explicit pros, explicit cons, and any relevant project/research context, (c) which option you'd recommend and why (or "no strong preference — depends on X"). Only after that block goes out, call `AskUserQuestion` with the same options as concise picker labels. The picker is for capturing the choice, not for explaining it.
  - **HARD REQUIREMENT — the chat block and the picker MUST match 1:1.** Same number of questions, same number of options per question, same labels in the same order, same recommendation. The picker `label` may only be a length-truncated shortening of the chat option's bolded label, and the picker `description` may only be a truncation of the chat's full pros/cons — the *set* of choices must be identical. If you revise the questions or options after writing the chat block, rewrite the chat block to match before calling `AskUserQuestion`. See the **Global Rule** at the top of this skill.
- Reference existing project patterns and conventions.
- Flag any conflicts with current architecture early.
- **For UI proposals:** Use `AskUserQuestion` with `markdown` previews to show ASCII wireframe mockups where helpful.
- **Late requirement impact check:** When a new requirement or decision contradicts or significantly changes a previously written spec section, explicitly enumerate which existing sections are affected before rewriting. State: "This changes sections: [list]. Updating all affected sections now." This prevents partial updates where some sections reflect a stale architecture.

---

## Phase 2: Gemini Deep Research Prompt

**Goal:** Draft a comprehensive research prompt for Gemini Deep Research to validate ideas, explore prior art, and surface pitfalls.

1. Create the feature directory: `{spec-dir}/{feature-slug}/`
2. **Resolve the project identity prepend (`IDENTITY_PREPEND_CHAR_BUDGET = 6,000` chars).** The prepend gives Gemini baseline product context. It must be small — a full identity doc can be tens of KB and would blow the textarea cap and waste tokens if pasted verbatim. Probe relative to the **project root** (the working directory `/spec` was invoked from, NOT the claude-config repo), in this priority order.

   **Probe base directory (`{identity-dir}`).** Default: **`docs/product/`** under the project root — the paths in the sub-steps below are relative to it. **Cognito Forms exception:** in the Cognito Forms repo (identify it by a `Cognito.sln` **and** an `AGENTS.md` titled "Cognito Forms Agent Guide" at the project root) the root's `docs` is a gitignored *pointer file*, not a directory, so `docs/product/` cannot resolve there. Cognito Forms keeps its identity docs in the sibling **`../cog-docs/docs/product/`** directory — use that as `{identity-dir}` (so the probes become `../cog-docs/docs/product/PRODUCT_IDENTITY_SUMMARY.md`, etc.). Every other project uses `docs/product/`. Everything else in this step — priority order, budget, self-heal, and the preamble strip — applies identically to the resolved `{identity-dir}`.

   1. **`{identity-dir}/PRODUCT_IDENTITY_SUMMARY.md`** — the dedicated, pre-sized "ready-to-go" Gemini prepend. **If it exists, read it and use it verbatim.** This is the fast path: no condensing, no token burn. Done.
   2. **`{identity-dir}/PRODUCT_IDENTITY.md`** — the full identity doc, used only if the summary above does not exist:
      - **If it is ≤ `IDENTITY_PREPEND_CHAR_BUDGET`**, use it verbatim.
      - **If it is over budget**, do NOT silently truncate and do NOT re-condense from scratch every run. Instead **self-heal once**: condense it to a ~1-page summary at or under the budget (if the doc contains a section explicitly labelled as a paste-ready / "Gemini-Ready" / TL;DR summary, base the condensation on that section rather than re-summarizing the whole doc), **write that condensation to `{identity-dir}/PRODUCT_IDENTITY_SUMMARY.md`**, then use it as the prepend. Every later `/spec` run finds the summary in step 1 and skips condensing entirely. Note in the Phase 2 summary (step 7) that a summary file was generated.
   3. **Neither file exists** — skip the prepend silently. No warning, no error. Not every project has an identity doc, and the prompt is still valid without one.

   Whichever file is used, treat its contents as the identity prepend below.

   **Strip the doc's self-describing preamble (apply HERE, at the convergence point — after resolution, before the content becomes the `## Project context` prepend).** A dedicated identity/prepend doc often opens with meta *about the artifact itself* — a self-labelling title and a run of maintainer/provenance notes — which is noise in the Gemini paste, not product identity. Before using the resolved content as the prepend, remove from the **TOP** of it ONLY:
   - **(a) A leading `# …` H1 that self-labels the artifact.** Be lenient/heuristic about the phrasing (house style — not a brittle exact-string match): strip the leading H1 when it reads as a self-reference to the doc's role rather than as product identity — e.g. it names itself an *identity summary*, a *Gemini prepend* / *Gemini-ready* artifact, a *prepend* / *product context for the LLM*, or similar artifact-labelling. A leading H1 that is genuine product identity (e.g. the product's own name as a title with no artifact-role phrasing) is NOT stripped.
   - **(b) The immediately-following contiguous run of blockquote (`> …`) lines** — provenance / regeneration / maintainer notes (e.g. "pre-sized, ready-to-go", "the budget-friendly condensation", "regenerate when the full doc changes materially"). Blank lines between the H1 and the blockquote run, and between blockquote lines, do not end the run.

   The strip **stops at the first non-blockquote, non-blank line** — i.e. everything from the first substantive section onward (e.g. `## What AlgoBooth is …`) is preserved **verbatim**. This strip is **BOUNDED to the leading preamble**: do NOT scan deeper into the doc, so a legitimate blockquote that appears *inside* later substantive content is never collateral-stripped. Because the strip is applied at this convergence line, it covers all three resolution branches uniformly — the verbatim summary (case 1), the verbatim full doc (case 2), and the case-2 self-heal condensation that writes `PRODUCT_IDENTITY_SUMMARY.md` (which could otherwise re-introduce a self-labelling title on a later run).

   *Worked example.* A doc that opens with `# AlgoBooth — Identity Summary (Gemini Prepend)`, then three provenance blockquotes (`> Pre-sized, ready-to-go …`, `> This is the budget-friendly condensation …`, `> When the full identity doc changes materially …`), then `## What AlgoBooth is …` yields a prepend that begins at `## What AlgoBooth is …` — the H1 and all three blockquotes removed, everything from `## What AlgoBooth is` onward kept verbatim.
3. **Compose the prompt body** per the structure below. Aim to keep the final file (identity prepend + your prompt body) **under `GEMINI_PROMPT_CHAR_CAP = 24,000` characters**.

   <!-- Cap source: Gemini Apps' web UI textarea has a practical per-message limit of ~30,000 characters per Google support docs and community reports
        (https://support.google.com/gemini/answer/16275805, https://support.google.com/gemini/thread/312836444). The Gemini model context window is in the
        millions of tokens, but Deep Research's prompt-input *field* uses the same bounded textarea. 24,000 leaves ~6,000 chars of headroom for paste-buffer
        quirks, mobile browser variability, and prompts that get edited up at copy time. Revisit when Google publishes an authoritative number. -->

   Budget realistically: the resolved identity prepend (step 2) is capped at `IDENTITY_PREPEND_CHAR_BUDGET = 6,000` chars, leaving 18K+ for the prompt body. If you can't keep the *body* under cap, write the file anyway and surface a warning in the Phase 2 summary (see step 6) — the operator can decide whether to truncate manually. Never silently truncate.

   **EVERY `RESEARCH_PROMPT.md` MUST be self-contained and copy-paste-complete on its own (HARD REQUIREMENT — no exceptions).** The operator copies a single `RESEARCH_PROMPT.md` verbatim into Gemini. A reader who opens ANY one feature's `RESEARCH_PROMPT.md` must get a complete, runnable Gemini prompt from that file alone — never a stub that says "see the sibling's prompt."

   - **The pointer/stub anti-pattern is FORBIDDEN.** Do NOT write a short `RESEARCH_PROMPT.md` whose body is a reference to another feature's prompt — e.g. "> Combined with `<other-feature>` research (they ship as a unit) — see `../<other-feature>/RESEARCH_PROMPT.md`, focus Sections 4 & 7." That 3-to-7-line pointer is useless to paste: the operator gets a link, not a research question.
     > **Burned on `d8-effect-chains`, 2026-06-14.** Its `RESEARCH_PROMPT.md` was a 7-line pointer at `../d8-track-infrastructure/RESEARCH_PROMPT.md`. A `/lazy-batch` run halted on it, surfaced the bare pointer, and the orchestrator was tempted to invent a "the sibling already has research, no run needed" exemption. The root cause was upstream — the pointer file should never have been *created*. Surface-time pointer resolution (lazy-batch Step 4) is now only a legacy fallback; new prompts are self-contained by construction here.
   - **Combined-research / "ships as a unit" features (the case that produced the stub):** when two or more features share ONE combined deep-research prompt, the correct output is the **FULL combined prompt content in EACH member feature's `RESEARCH_PROMPT.md`** — never a stub in one pointing at another. Pick the most robust mechanism:
     - **Default — duplicate the full content** into each member's `RESEARCH_PROMPT.md`. Simplest, zero indirection, survives the file being read in isolation, on any platform, and through git/cloud reclaim. This is the recommended choice.
     - **Symlink** each member's `RESEARCH_PROMPT.md` to the canonical one (symlinks work on this machine — Windows Developer Mode is on per AlgoBooth `CLAUDE.md`) ONLY if you have a strong reason to avoid duplication. A symlink reads as the full prompt when opened/copied, so it satisfies self-containment — but it is more fragile than duplication (breaks if the target moves; some tools deref differently). Prefer duplication unless the prompt is very large and drift between copies is a real concern.
     - Either way, the "combined / ships-as-a-unit" framing is **SPEC.md metadata, not prompt substance** — record it in SPEC.md (and, if useful, as prose around the prompt), NOT as a leading blockquote inside the prompt body (see step 4's no-meta-fluff rule). Each member's prompt still stands alone.

4. **Write the file** to `{spec-dir}/{feature-slug}/RESEARCH_PROMPT.md` with the identity prepend (if any) followed by the prompt body:

   ```markdown
   ## Project context

   <verbatim contents of the identity prepend resolved in step 2 — only if one was resolved>

   ---

   # <Research Question heading>

   <prompt body — sections below>
   ```

   If no identity prepend was resolved (step 2 case 3), skip the `## Project context` block AND the `---` separator entirely; start directly with the Research Question heading.

   **No meta-fluff in the prompt body (HARD).** The file content must be PURE research prompt — the operator copies it verbatim into Gemini, so anything that is not part of the actual research question is noise that pollutes the paste. Do NOT include:
   - A leading "> Combined with `<other>` research (they ship as a unit)" blockquote or any other ship-as-a-unit / cross-feature framing (that is SPEC.md metadata — see step 3).
   - Operator/tool metadata headers like "Mode: deep-research", "Model: gemini-2.5-pro", "Paste this into Gemini", or "deep-research mode" — none of that is research substance.

   The `## Project context` identity prepend's **substantive identity content** and the structured prompt sections (below) ARE legitimate prompt content and stay. Everything in the file should be content you want Gemini to actually read and act on. **The one exception inside the prepend:** the identity artifact's *self-describing preamble* — a self-labelling H1 (e.g. "… Identity Summary (Gemini Prepend)") plus the immediately-following maintainer/provenance blockquote run — is the SAME class of meta-fluff this HARD rule bans from the body, and it is **already stripped in step 2** (the preamble-strip sub-step at the convergence line). It is NOT exempt here: the whitelist covers the prepend's substance, not its self-describing meta. (Closing the body-vs-prepend asymmetry: the body rule above banned meta-fluff but the prepend used to ride it in unchallenged.)

**Research prompt structure (the body after the optional identity prepend):**
- **Research Question** — Clear, specific main question
- **Context** — Relevant project context (tech stack, current architecture, what exists today)
- **Baseline Spec Summary** — Condensed version of Phase 1 decisions
- **Research Areas** — Specific things to investigate:
  - Prior art in similar products
  - UI/UX patterns for the specific interaction model
  - Technical approaches and tradeoffs
  - Potential pitfalls, accessibility concerns, performance implications
  - Industry standards or conventions users would expect
- **Specific Questions** — 5-10 targeted questions that would benefit from deep research
- **Output Format Request** — Ask for structured findings with sections, examples, and actionable recommendations

5. **Length check.** After writing, read the file back and measure its character count. Compare against `GEMINI_PROMPT_CHAR_CAP = 24,000`.

6. **Echo the full research prompt to chat in a fenced code block (HARD REQUIREMENT — interactive mode).** After writing `RESEARCH_PROMPT.md` and doing the length check, output the **FULL final research prompt** — the exact file contents, including any identity prepend — to chat inside a fenced code block so the user can copy it directly into Gemini Deep Research without opening the file. Use a **quadruple-backtick fence** (````` ```` `````) to open and close this block, so that any triple-backtick fenced sub-blocks inside the prompt render correctly. Echo the contents verbatim — do not summarize, paraphrase, or abbreviate. (Under `--batch`, skip this echo — batch mode just writes the file and returns; there is no chat audience.)

7. **Phase 2 summary to chat.** Report:
   - The file path written.
   - Which identity prepend was applied and its source path — `PRODUCT_IDENTITY_SUMMARY.md` (fast path), the full `PRODUCT_IDENTITY.md` (under budget), or skipped (neither file present). If the full doc was over budget and you self-healed, state explicitly that you generated `{identity-dir}/PRODUCT_IDENTITY_SUMMARY.md` so future runs are ready-to-go.
   - The actual character count and whether it's under / over the 24,000 cap. If over, state explicitly that the operator may need to trim before pasting into Gemini Deep Research, and suggest which sections (Context / Research Areas / Specific Questions) are most condensable.
   - Confirmation that the full prompt was echoed to chat in a quadruple-backtick fenced code block (per step 6) for direct copy-paste.

8. Tell the user: "Research prompt saved. Run deep research, then give me the file path to the results."
9. **STOP and wait for the user to return with the research file path.**

---

## Phase 3: Integrate Research & Finalize Spec

**Goal:** Incorporate research findings and finalize the complete feature specification.

1. Read the research results file the user provides.
2. Copy it to `{spec-dir}/{feature-slug}/RESEARCH.md`.
3. Write a research summary to `{spec-dir}/{feature-slug}/RESEARCH_SUMMARY.md` (MANDATORY — this file gates downstream workflow) analyzing:
   - Key findings relevant to our baseline spec
   - Ideas we should adopt from prior art
   - Pitfalls or concerns we need to address
   - Any baseline spec decisions that should be revisited based on research
4. **Surface the full decision landscape in chat BEFORE any `AskUserQuestion` call.** After research, the user typically faces several interlocking decisions, and the picker UI truncates option descriptions — so the user cannot answer informed from picker labels alone. Write a chat-visible "Open Decisions" block first, structured as:

   ```
   ## Open Decisions (post-research)

   The research surfaced N decisions that need to be locked in before finalizing the SPEC. Full context for each below — picker questions follow.

   ### Decision 1: {short name}
   **Question:** {what we're deciding}
   **Why it matters now:** {what downstream choices depend on this}
   **Research signal:** {1-2 sentence summary of what RESEARCH.md says about this}

   - **Option A — {label}:** {1-2 sentence description}
     - Pros: {bulleted or comma-separated}
     - Cons: {bulleted or comma-separated}
     - Fit with our stack/constraints: {note}
   - **Option B — {label}:** ...
   - **Option C — {label}:** ...

   **My recommendation:** {Option X, because Y} — or — "no strong preference, depends on {Z}"

   ### Decision 2: ...
   ```

   Cover at minimum: spec adjustments based on research, v1-vs-later prioritization, technical approach clarifications, and any remaining open questions. Use the actual research findings — don't restate generic categories.

5. **Then** use `AskUserQuestion` to capture the choices. Each picker question should match one decision from the chat block above, with concise labels (the full tradeoff context already lives in chat). Ask 2-4 questions per round.

   **HARD REQUIREMENT — the "Open Decisions" chat block and the picker MUST match 1:1.** The decisions and options in the chat block correspond verbatim (modulo picker-label truncation) to the questions and options passed to `AskUserQuestion`: same number of questions, same number of options per question, same option labels in the same order, same recommendation (the chat block's **My recommendation** must be the flagged option in the picker). The picker `label` may only be a length-truncated shortening of the chat option's bolded label, and the picker `description` may only be a truncation of the chat's full pros/cons. If you add, drop, reword, or re-recommend any decision/option after writing the chat block, rewrite the "Open Decisions" block to match before calling `AskUserQuestion`. See the **Global Rule** at the top of this skill.
6. Continue refining until the user is satisfied. On each new round of decisions, repeat the "surface context in chat first, then ask" pattern — re-applying the 1:1 match requirement on every round.
7. Write the final `{spec-dir}/{feature-slug}/SPEC.md` with this structure. Before writing, run `git branch --show-current`: if the result matches `^p/`, stamp `**Branch:** \`<branch>\`` into the header (after `**Last updated:**`); if on `main`/`master` or any non-`p/` branch, omit the `**Branch:**` line — the branch usually does not exist yet at spec time, and `/spec-phases` is the primary stamp point.

```markdown
# {Feature Name} — Feature Specification

> One-line summary

**Status:** Draft
**Priority:** {P0-P3}
**Last updated:** {today's date}
**Branch:** `{p/* branch — omit if not yet on a work branch}`
**Friction-reduction feature:** {yes|no}

<!-- The classification line is MANDATORY (friction-kpi-registry measurability gate, Step 8.5).
     'yes' = reducing harness/process friction is part of this feature's stated purpose; it then
     REQUIRES a `## KPI Declaration` section. 'no' = an ordinary feature. See Step 8.5. -->

**Depends on:**

- {feature-id} — {hard|soft|composes} — {one-sentence reason}
- {feature-id} — {hard|soft|composes} — {one-sentence reason}

(or, if there are no deps, replace the bulleted block with exactly: `**Depends on:** (none)`)

---

## Executive Summary
{2-3 paragraphs describing the feature, its value, and high-level approach}

## User Experience
{Detailed UX description with workflows}

## Technical Design
{Architecture, data model, component changes}

## Implementation Phases
{Phased breakdown with clear deliverables per phase}

## Validation Criteria

For each major observable behavior defined in this spec, define how to verify it works end-to-end:

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| {e.g., "data persisted after save"} | {e.g., "submit the form"} | {e.g., "record exists in database"} | {e.g., "database query, API response"} |

These criteria are used during `/implement-phase-batch` to validate spec alignment. Each row becomes a test assertion.

### Required MCP tooling (capture as a Locked Decision)

When any Validation Criteria row above is verified by calling an **MCP tool**, enumerate those tools and capture them as a **Locked Decision** — NOT only the existing-tool menu, but every tool the validation will REQUIRE TO EXIST (including ones that may have to be BUILT). This predetermines the tool surface at planning time so `/spec-phases`' MCP tool-existence audit can verify each exists and auto-author a build phase on a miss, and so the completion-time coverage gate can assert on it (defense-in-depth — see `docs/bugs/mcp-tooling-not-predetermined-at-planning`).

**CRITICAL — shape it so the gate can see it.** Land the capture in the SPEC's `## Locked Decisions` H2 as a table row (first column = a decision ID like `L4`, or a one-line decision title) — the SAME canonical surface `lazy-state.py --gate-coverage` / `mcp-coverage-audit.md` Step 1 enumerates. Do NOT invent a new section the gate cannot parse. Example row:

```markdown
## Locked Decisions

| ID | Decision |
|----|----------|
| L4 | Required MCP tooling: validation calls `set_slip_pad_template` + `get_scene_state`; both must be registered before `/mcp-test` (build if absent). |
```

If the feature's validation calls no MCP tools, omit this — no Locked Decision is added.

## Open Questions
{Anything still unresolved}

## Research References
{Link to RESEARCH.md and key findings that shaped decisions}
```

!`cat .claude/skill-config/spec-testing-guidance.md 2>/dev/null || cat ~/.claude/skills/_components/spec-testing-guidance.md`

8. **Depends-on Finalization Checkpoint (BLOCKING — before marking Final):**

   Re-verify the `**Depends on:**` block against the final SPEC content. Things change during Phase 3 — research often introduces a new upstream, descopes one, or shifts a `soft` dep to `hard`.

   Apply the schema rules from `~/.claude/skills/_components/dep-block-schema.md` (you read this in Phase 1b). Confirm:

   - The block exists exactly once and is positioned after the frontmatter and before the first design heading.
   - Every line uses ` — ` (space, em-dash U+2014, space) as the separator. Hyphen-minus is invalid.
   - Every `<feature-id>` resolves to a real feature directory using the resolution protocol.
   - Every `<kind>` is one of `hard`, `soft`, `composes`.
   - If no deps, the block reads exactly `**Depends on:** (none)`.

   If any check fails, fix the block before writing the final SPEC.md. Do NOT write the SPEC.md with a malformed or missing dep block — downstream skills (`/spec-phases`, `/write-plan`, `/lazy` Step 4.6, `/realign-spec`) depend on this being parseable, and project-side doc-lint will reject the commit.

8.5. **Friction-KPI Measurability Gate (BLOCKING — before marking Final):**

!`cat .claude/skill-config/spec-friction-kpi-gate.md 2>/dev/null || cat ~/.claude/skills/_components/spec-friction-kpi-gate.md`

9. **Cross-Boundary Validation (before marking Final):**
   Before finalizing any spec that references runtime data access, surface counts, or cross-boundary propagation:
   - **Formulas referencing runtime data** (e.g., "total = sum(lineItems.price)"): Verify the data is accessible at the proposed instrumentation point — read the source code or dispatch a subagent to confirm the variables are in scope
   - **Surface counts** (e.g., "~50 API endpoints"): Run a subagent to grep/count the actual surfaces in the codebase; report the real number
   - **Cross-boundary propagation** (e.g., "auth token flows through middleware"): Verify the boundary contract supports it — check the protocol schema, third-party docs, or IPC layer
   - Mark any unverified quantities with `(estimated — verify during Phase N)` in the spec; never commit to a specific number without evidence

10. Confirm with the user that the spec is complete.

---

## Notes

- The feature slug should be kebab-case, derived from the feature name (e.g., `user-notifications`).
- If the user says "skip research" or similar, skip Phase 2 and go directly to finalizing the spec in Phase 3 (without research integration).
- If the user provides a research file path at any point, treat it as the Phase 2→3 transition.
- Always check for related specs that might conflict or overlap.

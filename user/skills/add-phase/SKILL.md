---
name: add-phase
description: Add a new phase to an existing PHASES.md, checking Implementation Notes and marking superseded phases
argument-hint: <path/to/PHASES.md> [phase description]
---

# Add Phase

Add a new phase to an existing PHASES.md file. Reads all prior phases — including their Implementation Notes — to ensure the new phase is well-informed and consistent. Marks superseded phases if the new phase replaces or obsoletes prior work.

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation (typically from `/lazy-batch` Step 4.6 acting on a `/realign-spec` recommendation).

- Strip `--batch` from `$ARGUMENTS` before processing.
- Steps 1–5 (resolve inputs, read context, analyze, draft, mark superseded) run unchanged.
- **Step 6 (Present for Approval) is skipped.** The orchestrator passes the desired phase title and scope in the description argument; `--batch` mode trusts the orchestrator's framing and proceeds to Step 7.
- **Halt protocol — `NEEDS_INPUT.md`:** if Step 1b cannot resolve the phase description (no description supplied AND no usable context AND the supplied description is genuinely ambiguous about scope), do NOT invent a phase. Instead write `{phases-md-dir}/NEEDS_INPUT.md` per `~/.claude/skills/_components/sentinel-frontmatter.md`:

  ```markdown
  ---
  kind: needs-input
  feature_id: {feature-slug derived from phases-md-dir}
  written_by: add-phase
  decisions:
    - "Phase scope ambiguous — orchestrator did not provide enough context"
  date: {today}
  next_skill: add-phase
  ---

  # /add-phase --batch — Needs Input

  Phase description missing or ambiguous; refusing to invent a phase.
  Re-run `/add-phase` interactively with explicit title + scope.
  ```

  STOP without writing PHASES.md.

- Step 7 (Write Changes) runs unchanged. The change is committed by the caller per the orchestrator's commit policy.

---

## Step 1: Resolve Inputs

### 1a. PHASES.md Path

- If `$ARGUMENTS` contains a `.md` path, use it.
- Otherwise, check session history for a recently-referenced PHASES.md.
- If still unresolved, use **AskUserQuestion**: "Which PHASES.md should I add a phase to?"

### 1b. Phase Description

- If `$ARGUMENTS` contains a description (beyond the path), use it.
- Otherwise, check session history for context about what the user wants to add.
- If still unresolved, use **AskUserQuestion**: "What should this new phase accomplish? Describe the scope and goal."

---

## Step 2: Read Full Context

1. **Read the PHASES.md in full** — every phase. For prior Implementation Notes, apply the sibling-then-embedded read order: check for a sibling `IMPLEMENTATION_NOTES.md` (in the same directory as PHASES.md) first; fall back to embedded `## Implementation Notes` blocks in PHASES.md if the sibling is absent or a bare placeholder. See `~/.claude/skills/_components/implementation-notes-read-order.md` for the canonical rule.
2. **Read the sibling SPEC.md** (same directory) — source of truth for feature requirements.
3. **Read project CLAUDE.md** (if it exists at the project root) — for conventions and patterns.

---

## Step 2.5: Phase-Count Circuit Breaker (BEFORE ANY DRAFTING)

**Motivation:** Retro evidence shows two features expanding 9→19 and 18→30 phases via repeated `/add-phase` corrective tails (`analysis-informed-dsp-updates`, `audio-quality-analysis`; `hardware-override-protocol` scored 24/F under the same dynamic). A >+50% expansion is not "a few follow-ups" — it is a signal the original decomposition is invalid and must be rebuilt, not patched. Counter-calibration (57077): the breaker fired 4× and was overridden 4× — all review-round-sourced from fire 2 on, with `/realign-spec` never taken — and a 100%-override signal protects nothing, which is why review-round correctives are half-weighted and a middle remedy exists below.

### Compute the added-phase ratio

1. **Determine the original phase count.** Inspect the PHASES.md for the highest phase number that was authored in the *initial* spec-phases run. Heuristics (apply in order):
   - A frontmatter or header line of the form `<!-- original-phase-count: N -->` or `**Original phase count:** N` — use N directly.
   - Failing that, count phases whose phase number is ≤ the lowest phase number that carries a `SUPERSEDED` or `(corrective)` annotation, minus 1.
   - Failing that, treat every phase that existed before the first `/add-phase` corrective entry in the Implementation Notes history as original.
   - Failing that, count all phases currently in the file and treat that as the original count (conservative — prevents a false-positive block when the file has no history).
   - Call this value **O**.

   > **Known undercount mode (denominator honesty):** when corrective phases interleave with legitimate design phases, the heuristic that estimates the original count as the pre-first-corrective prefix undercounts here — later design additions get counted as expansion against a stale denominator, inflating the ratio (57077 Phase 12's documented case). When this interleaving is present in the file, every fire message below MUST state this caveat alongside the numbers.

2. **Count phases that would exist after this append.** Let **T** = (current total phases in the file) + 1.

3. **Weight each added phase by its source.** For each of the `T − O` added phases (every phase beyond the original **O**, INCLUDING the phase being appended now), assign a weight:
   - **0.5 (half weight) — review-round-sourced:** the phase was created via `/resolve-review`, or its description / **Context from prior phases** block cites open-PR review comments (a `CHANGES_REQUESTED` round). A bounded review round on a nearly-complete feature is normal delivery, not decomposition failure.
   - **1.0 (full weight) — everything else:** correctives sourced from runtime defects, premise reversals, or internal discoveries, and all `design` additions. These ARE the decomposition-failure signal the breaker exists for.

   Let **W** = the sum of these weights. (`W = T − O` when no added phase is review-round-sourced — identical to the unweighted behavior.)

4. **Compute the added-phase ratio:** `W / O`.

### Decision

| Ratio | Action |
|-------|--------|
| `≤ 0.50` | Proceed normally to Step 3. |
| `> 0.50` | **STOP — circuit breaker fires.** Do not draft or append the phase. |

### Breaker action (when fired)

**Interactive mode:**

Surface the violation to the operator:

> **Phase-count circuit breaker triggered.**
> Original phase count: **O**. Current total: **T−1**. Adding this phase would bring the weighted expansion to **{W/O * 100:.0f}%** over original (weighted added-phase count W = {W}) — exceeding the +50% threshold.
>
> This expansion signal means the original decomposition may be invalid. Three paths:
> 1. **Full rebuild** (for genuine decomposition failure): run `/realign-spec` on the SPEC.md to reconcile the spec with what was actually built, then re-run `/spec-phases` to produce a fresh phase breakdown from the aligned spec.
> 2. **Premise re-audit** (proportionate middle remedy): re-check the SPEC's Locked Decisions / premises against the accumulated corrective evidence — per the premise-grade contradiction ladder in `~/.claude/skills/_components/touchpoint-audit-gate.md` — WITHOUT rebuilding phases. If a premise is contradicted, that's the real defect; if all premises hold, the expansion is likely benign accumulation.
> 3. **Override**: re-invoke `/add-phase` with `--override-circuit-breaker` in the arguments (still logged in the drafted phase's context block).

If the interleaving undercount mode applies (see the denominator-honesty note above), state the caveat in this message alongside the numbers.

Do NOT proceed to Step 3. Stop here.

**Batch mode (`--batch`):**

Write `{phases-md-dir}/NEEDS_INPUT.md` using the sentinel frontmatter schema:

```markdown
---
kind: needs-input
feature_id: {feature-slug derived from phases-md-dir}
written_by: add-phase
decisions:
  - "Phase-count circuit breaker: adding this phase would push weighted expansion to {ratio*100:.0f}% over the original O-phase count (threshold: +50%). Original: O, current: T-1, proposed: T, weighted added count: W."
  - "Path (a) full rebuild: /realign-spec then /spec-phases (genuine decomposition failure). Path (b) premise re-audit: re-check the SPEC's Locked Decisions / premises against the accumulated corrective evidence (touchpoint-audit-gate.md ladder) without rebuilding phases. Path (c) override with --override-circuit-breaker if intentional."
date: {today}
next_skill: add-phase
---

# /add-phase --batch — Circuit Breaker Fired

Adding this phase would bring the weighted added-phase count to **{W}** above the original **O**-phase plan ({ratio*100:.0f}% weighted expansion; threshold +50%; review-round-sourced correctives count at half weight).

A >+50% weighted corrective tail is a signal the original decomposition may be invalid. Three paths:
(a) **Full rebuild** — re-run `/realign-spec` + `/spec-phases` to rebuild from the current SPEC.md (genuine decomposition failure);
(b) **Premise re-audit** — re-check the SPEC's Locked Decisions / premises against the accumulated corrective evidence (per the premise-grade contradiction ladder in `~/.claude/skills/_components/touchpoint-audit-gate.md`) without rebuilding phases;
(c) **Override** — re-invoke `/add-phase --batch --override-circuit-breaker`.
```

If the interleaving undercount mode applies (see the denominator-honesty note above), append the caveat to the sentinel body alongside the numbers.

STOP without writing PHASES.md.

### Override

If `$ARGUMENTS` contains `--override-circuit-breaker`, skip the breaker check and proceed to Step 3. Log a warning in the drafted phase's **Context from prior phases** block:

> ⚠ Phase-count circuit breaker overridden by operator. Expansion is {ratio*100:.0f}% over original count.

---

## Step 3: Analyze Existing Phases

### 3a. Extract State

For each existing phase, record:
- Phase number, title, scope
- Status: all deliverables checked (`[x]`) = complete, any unchecked (`[ ]`) = incomplete
- Implementation Notes (if present): completed date, integration notes, pitfalls, files modified
- Prerequisites and dependencies

### 3b. Mine Implementation Notes

Implementation Notes contain ground truth about what was _actually_ built (vs. what was planned). Find them using the sibling-then-embedded read order: check `IMPLEMENTATION_NOTES.md` (sibling to PHASES.md) first; fall back to embedded blocks in PHASES.md if the sibling is absent. Before drafting the new phase:

- Identify **patterns established** — imports, APIs, conventions the new phase should follow
- Identify **pitfalls documented** — things to avoid or work around
- Identify **actual file paths** — may differ from original plan; use real paths
- Identify **integration seams** — where the new phase connects to completed work

### 3c. Check for Supersession

Compare the new phase's scope against existing phases:

- **Fully superseded:** The new phase completely replaces an existing phase's purpose (e.g., "rewrite X" supersedes "implement X"). Mark as superseded.
- **Partially superseded:** The new phase replaces some deliverables of an existing phase. Mark specific deliverables as superseded, not the whole phase.
- **Not superseded:** The new phase adds net-new functionality alongside existing phases. No marking needed.

---

## Step 3.5: Runtime Assumption Validation (where appropriate — BEFORE DRAFTING THE PHASE)

A new phase often rests on assumptions about how the *running* system behaves — the actual shape of data crossing a boundary, whether an existing code path fires, the live output of a separate process, the rendered result of an audio/effect path. These are NOT provable from source: reading the types or the function body can mislead (a value's runtime shape, a stale build, a module-singleton split, timing). Where the new phase rests on a load-bearing **runtime-coupled** assumption, validate it against the running system BEFORE drafting the phase — or make the validation an explicit early deliverable of the phase itself. Do not draft (and then implement) a phase against a code-read assumption the runtime might contradict. This is especially important for `/add-phase`, which frequently appends *corrective* phases that exist precisely because a prior assumption proved wrong — confirm the new assumption is real before building on it.

!`cat .claude/skill-config/phases-runtime-validation.md 2>/dev/null || cat ~/.claude/skills/_components/phases-runtime-validation.md`

---

## Step 4: Draft the New Phase

Determine the next phase number (highest existing + 1, or fill a gap if prior phases were superseded and removed).

**PREREQUISITE-ORDERING RULE (HARD — ISSUE 1, d8-effect-chains run 2026-06-14).** A corrective/prerequisite phase MUST NOT be numbered AFTER the phase(s) it must precede. Determine the dependency direction first: if the new phase is a **prerequisite** for an existing lower-numbered phase (it builds the foundation that the existing phase documents/depends on), appending it at `highest + 1` INVERTS execution order — the downstream `/write-plan` partitions by phase number and the state machine selects the lowest-phase plan part first, so the prerequisite (high number) routes AFTER its dependents (low number). This is exactly the d8-effect-chains failure: a corrective Phase 6 was a prerequisite for the pre-existing Phase 5 (Phase 5 documents the `.cab()`/`.reverb()` API that Phase 6 builds), and the router oscillated routing Phase 5's plan part before Phase 6's.

When the new phase is a prerequisite for an existing phase **M**, pick ONE (in preference order):

1. **Insert as a fractional phase before M** — number it `Phase (M-1).5` (e.g. `Phase 4.5` to precede `Phase 5`). `parse_phases` and the plan-frontmatter `phases:` field accept non-integer / leading-digit identifiers (`_plan_lowest_phase` extracts the leading digit run), so a fractional number sorts correctly before M. This is the lowest-churn option.
2. **Renumber** — shift M and all subsequent phases up by one and insert the prerequisite at M's old number. Higher churn (every downstream `phases:` reference must move) but yields clean integer numbering.

Either way, the authoritative signal is **execution order = ascending phase number** AND **`/write-plan` part series order** (the `-part-K` filename suffix, honored by `lazy_core._plan_sort_key`). Do NOT rely on a prose "Prerequisites:" note alone to fix ordering — the state machine sorts by number, not by reading prose. If you genuinely cannot avoid a higher-numbered prerequisite (rare), the corrective phase's `/write-plan` part MUST be authored as `-part-1` of the series so the part-series sort overrides the phase-number inversion (this is the routing backstop, but renumber/fractional-insert is preferred — fix the source, not the symptom).

Write the phase using the established PHASES.md format:

```markdown
### Phase N: {Title}

**Status:** {In-progress | Ready | …}
**Phase kind:** {corrective | design}

**Scope:** {Clear description of what's built — informed by Implementation Notes from prior phases}

**Deliverables:**
- [ ] {Concrete output 1}
- [ ] {Concrete output 2}
- [ ] Tests: {What tests verify this phase}

**Prerequisites:**
- {Phase X}: {Specific dependency — reference actual outputs from Implementation Notes, not planned outputs}

**Files likely modified:**
- `path/to/file` — {what changes} (use actual paths from Implementation Notes where applicable)

**Testing Strategy:**
{How this phase is verified in isolation}

**Integration Notes for Next Phase:**
- {What a subsequent phase would need to know}

**Context from prior phases:**
- {Key patterns, pitfalls, or integration details extracted from Implementation Notes that inform this phase's implementation}
```

**Phase-kind tagging (HARD REQUIREMENT — drives the `/retro` re-run gate):** every appended phase MUST carry a `**Phase kind:** corrective | design` line directly under its `**Status:**` line (mirrors the per-phase `**MCP runtime:**` convention; `parse_phases` reads it, defaulting to `design` when absent for back-compat). The tag tells the state machine whether the phase add warrants a fresh `/retro` round:

- **`corrective`** — a fix-phase born from a blocked `/mcp-test` / validation failure whose scope is making the implementation satisfy the **EXISTING** SPEC (it does NOT expand the design surface). A run of purely-corrective additions does NOT re-stale `/retro` — there is no new design for retro to audit, so dragging a retro round in front of the re-validation is pure overhead (measured: `d7-multi-timbral` ran `/retro` 5× for 4 corrective adds, ~520k tok of zero-divergence rounds). **The blocked-resolution `/add-phase` dispatch (when the trigger is a `BLOCKED.md` with `blocker_kind: mcp-validation` or `execute-plan-scope`) and the investigation-dispatch corrective phase MUST tag `corrective`.**
- **`design`** (default) — a phase that expands or changes the design surface (a new feature slice, a new API/algorithm, a re-decomposition). An interactive / operator `/add-phase` defaults to `design` unless the operator says it is a corrective fix. A `design` add DOES re-stale `/retro` (the design changed, so the prior retro graded a surface it no longer fully covers).

When in doubt, tag `design` — it is the safe default (re-audits). Only tag `corrective` when the phase genuinely changes no design surface.

**Deliverables authoring — no gate-owned rows (corrective phases are where these creep in):** pipeline-owned actions are NEVER authored as `- [ ]` rows — not in Deliverables, not under Runtime Verification. The class: SPEC.md/PHASES.md top-level `**Status:**` flips, COMPLETED.md/FIXED.md receipt writes, ROADMAP completion marks, archive moves. These are owned by the `__mark_complete__`/`__mark_fixed__` gate; a checkbox for them is unplannable, untickable work that loops the state machine (live incident 2026-06-11: a `- [ ] Update SPEC.md status to "Complete"` row in d8-live-looping routed write-plan repeatedly). A corrective phase that genuinely needs to record a completion fact authors it as a prose `**Completion (gate-owned):**` note, never a checkbox. Ordinary doc-edit deliverables ("Update SPEC §X wording") stay legitimate checkboxes — the ban is on STATUS/receipt/archive actions only. See `~/.claude/skills/_components/phases-runtime-verification.md` for the full rule + rationale.

**Verification rows carry the canonical marker (HARD — routes the phase to the MCP gate, not write-plan):** a corrective validation phase exists to add "run to PASS via `/mcp-test`" rows, and every Runtime Verification / MCP-validation `- [ ]` row this phase authors MUST carry the canonical `<!-- verification-only -->` marker ON the row (SSOT `lazy_core:_VERIFICATION_ONLY_MARKER`) — or live under a recognized `**Runtime Verification**` / `**MCP Integration Test Assertions:**` subsection. `lazy-state.py`'s `remaining_unchecked_are_verification_only()` is MARKER-FIRST: an *unmarked* verification row is classified as an outstanding **implementation** item, so a phase whose only remaining unchecked rows are unmarked verification rows routes to `write-plan`/`execute-plan` instead of the Step-9 `/mcp-test` gate — the exact loop observed 2026-07-05 (recording-panel Phase 7: a `- [ ] Tests: … run to PASS via /mcp-test` row lacked the marker and routed to write-plan, not mcp-test, until the marker was hand-added). This is the same placement discipline `/write-plan` and `/spec-phases` already mandate; a corrective phase authored via `/add-phase` is the one authoring path that previously did not restate it. See `~/.claude/skills/_components/phases-runtime-verification.md`.

**Reachability smoke when this phase adds a new API surface:** if the corrective phase introduces a NEW user-facing API surface (new MCP tool, pattern-language method/builder, IPC command, UI-reachable action), it carries one in-phase reachability-smoke row under Runtime Verification (tagged `(reachability-smoke — workstation-eligible)`) — this is the same early-runtime discipline Step 3.5 already mandates for runtime-coupled assumptions: prove the new surface is callable end-to-end from the phase that introduces it rather than discovering at the Step-9 MCP gate that it was never reachable (d8-live-looping: 0/16 BLOCKED on an unreachable `track(...).record()` after eight phases). See `~/.claude/skills/_components/phases-runtime-verification.md`.

**Spike return line for a tooling-gap corrective phase (HARD — closes the Spike tooling-existence loop):** when THIS `/add-phase` invocation is the corrective route a **Spike** cycle took because its required tooling did not exist (the trigger is a `SPIKE_VERDICT.md`/`BLOCKED.md` carrying `tooling_ok: false` and naming the missing tooling — the `blocker_kind: runtime-spike-verdict-pending` blocked resolver, or a Step-9.5 `**Spike:** required` gate), the drafted corrective phase (a) tags `**Phase kind:** corrective` (it makes the implementation satisfy the existing SPEC — expose the missing tooling, no new design surface), AND (b) MUST carry a `**Spike:** required — <the original proof goal, verbatim from the Spike's `**Spike:**` line / results doc>` line directly under its `**Status:**`/`**Phase kind:**` lines. That return line is load-bearing: Part 1's `phases_spike_required(spec_path)` / `_read_spike_decision` header gate reads it, so once this tooling phase completes the state machine re-routes to a `spike` cycle to run the proof — control RETURNS to Spike rather than falling through to `__mark_complete__` on un-proven tooling. Do NOT invent a new proof goal — carry the Spike's original goal forward verbatim so the same measurement is run. (The tooling-existence audit itself is NOT re-authored here — the Spike subagent already greps the repo's live tool registry via the `~/.claude/skills/_components/phases-runtime-validation.md` tool-existence audit + the per-repo `mcp-tool-catalog.md`; this WU only wires the corrective phase's return line.) The loop is BOUNDED by the machine — the `spike_tooling_rounds` counter on the entry sentinel is capped (default 3) and the state machine writes `NEEDS_INPUT.md` instead of authoring another corrective phase once the cap is hit (see `lazy_core.spike_tooling_cap_exceeded`), so this authoring path can never spin forever. See `~/.claude/skills/_components/spike-dispatch.md`.

**Seam audit for every mcp-validation corrective phase (HARD REQUIREMENT — not gated by escalation):** if the corrective phase is being authored to resolve a `BLOCKED.md` with `blocker_kind: mcp-validation`, at ANY `retry_count` (including 0 — the FIRST validation failure), the phase MUST carry a **full-chain seam audit** deliverable in addition to the layer-specific fix: enumerate every boundary in the failing path (user surface → sidecar/IPC → command queue/ring → engine apply → final observable) and live-probe each seam post-fix BEFORE the feature re-enters full validation. Consume the `## Seam Enumeration` section of BLOCKED.md as the checklist — the validation cycle now writes it into EVERY mcp-validation `BLOCKED.md`, not only at escalation (`cycle-base-prompt.md` R14 / the AlgoBooth `mcp-test` SKILL). A single-layer corrective phase for an mcp-validation blocker is a drafting error at ANY retry level now — it is how d8-live-looping burned three ~1M-token validation rounds discovering one layer per round (API reachability → unsupported live-input source → audio-thread command-apply drop) back when enumeration + batched scoping were gated behind two prior loops. At `retry_count >= 2` (`validation_escalation: true`) the phase ADDITIONALLY consumes `INVESTIGATION.md` (below) — repeated failure despite a batched seam fix means `/investigate` is now mandatory.

**Consume `INVESTIGATION.md` when present (the investigation cycle's artifact):** when the feature/bug dir carries a CURRENT `INVESTIGATION.md` (freshness: `investigated_commit` == HEAD, or only that investigation's own `diag(...)` commits since — schema in `~/.claude/skills/_components/sentinel-frontmatter.md`), the corrective phase is drafted FROM it, not from narrative: its **confirmed** Hypothesis-Ledger rows are citable as `runtime` evidence in the phase's Validated Assumptions ledger (the evidence column cites the artifact AND its underlying evidence artifact — test name, MCP result, log line); its `## Seam Table` seeds the seam-audit deliverable; its `## Recommended Fix Scope` seeds Files-likely-modified and the phase's do-NOT-touch notes. `refuted` rows MUST NOT be re-planned against. A stale artifact may be cited only as `(stale — re-verify)`. If the escalation conditions hold and no current artifact exists, the resolution flow should have dispatched `/investigate` first (see `~/.claude/skills/_components/investigation-dispatch.md`) — flag the gap rather than drafting from inference.

**Review Guardrails (this phase):** front-load the review pitfalls likely to recur on this phase's files — and, because corrective phases recur on the work they replace, on any superseded phase's files too (Step 3c). Apply the protocol below when present and embed its output in the drafted phase. This is a no-op outside repos that configure a guardrail source:

!`cat .claude/skill-config/phases-review-guardrails.md 2>/dev/null || cat ~/.claude/skills/_components/phases-review-guardrails.md`

---

## Step 5: Mark Superseded Phases

If any phases are superseded (identified in Step 3c):

### Fully Superseded

Add a supersession notice at the top of the phase and strike through all deliverables:

```markdown
### Phase M: {Original Title}

> **⚠️ SUPERSEDED by Phase N: {New Title}** — This phase's scope has been replaced. Do not implement.

**Deliverables:**
- [~] ~~{Original deliverable 1}~~ — superseded
- [~] ~~{Original deliverable 2}~~ — superseded
```

### Partially Superseded

Mark only the specific deliverables that are replaced:

```markdown
- [~] ~~{Superseded deliverable}~~ — superseded by Phase N
- [ ] {Still-valid deliverable}
```

### Already-Completed Phases

Never mark a completed phase (all `[x]`) as superseded. If the new phase _replaces_ completed work (a rewrite), note this in the new phase's scope instead:

```
**Scope:** Rewrite the implementation from Phase M. Phase M's approach of {X} is replaced with {Y} because {reason}.
```

---

## Step 6: Present for Approval

**Under `--batch`:** SKIP this step entirely. The orchestrator's description argument is treated as approval. Proceed to Step 7.

**Interactive mode:** show the user:
1. The drafted new phase
2. Any supersession markings (with before/after)
3. Key context extracted from Implementation Notes that shaped the draft

Use **AskUserQuestion**: "Here's the new phase and any supersession changes. Approve, or adjust?"

---

## Step 7: Write Changes

After approval:
1. Append the new phase to PHASES.md (before any trailing notes/appendix sections)
2. Apply supersession markings to affected phases
3. Read back the modified file to verify formatting is correct

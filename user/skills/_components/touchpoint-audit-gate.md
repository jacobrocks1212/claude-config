## Touchpoint Audit Gate (MANDATORY — DO NOT SKIP)

**Purpose.** Ground this plan in the *actual* state of the codebase before it is written. The
executing agent must not have to re-discover the truth at implementation time. Every file the plan
schedules for modification is verified to exist (or explicitly marked net-new), its real symbols are
read, existing code to reuse is named, refactor targets are called out, and any assumption that
contradicts reality is corrected **in the plan itself — before the artifact is emitted.**

This gate is **read-only**. It dispatches `Explore` subagents and uses the tree-sitter MCP tools; it
never edits source. It runs at planning time, so it is compatible with the orchestrator-no-Edit/Write
constraint of the host skill.

### Step A — Assemble the candidate touchpoint set

Build the list of **existing or to-be-created source files** this plan will modify. Pull from, in order:

1. Candidate touchpoints the host skill already collected (e.g. /spec-phases Step 2's preamble, a
   work-unit's "Files to create/modify", a /fix's suspected files).
2. The SPEC's / PHASES' "Technical Design", "Files likely modified", or equivalent sections.
3. Files you read or grepped while analyzing boundaries / drafting work units.

If the set is empty, you have not done enough analysis — derive it now from the spec/phase/work-unit
scope. A plan that names zero touchpoints cannot be grounded.

### Step B — Verify reality with parallel Explore subagents (ALWAYS)

Do **not** verify inline from memory. Partition the candidate set into coherent groups (by subsystem,
directory, or work unit — aim for 1 group per `Explore` agent, ~3–8 files each) and dispatch the
groups **in parallel in a single message**. For an unfamiliar or large feature, also dispatch one
"abstraction sweep" agent to find pre-existing code the plan may have missed (composables, services,
utilities, base classes that already do part of the job).

Brief each `Explore` agent (read-only — it must NOT edit anything):

> Verify these planned touchpoints against the real codebase. For EACH file below, report:
> - **Exists?** yes / no. If no, is there a sibling/renamed/moved file that is clearly its real home?
> - **Real symbols:** the actual top-level functions, classes, exports, and key methods present
>   (use tree-sitter `get_file_structure`; for non-TS/C#/Vue/JS use Read/Grep).
> - **Reusable code:** existing symbols here (or elsewhere) that the planned change should REUSE
>   instead of writing new — name them with file:symbol.
> - **Refactor needed:** what existing code must change shape (signature, location, split) to
>   accommodate the planned change.
> - **Contradiction:** anything that conflicts with the stated plan assumption — the abstraction
>   already exists, the logic lives in a different layer/file, the API differs, the file is
>   generated/dead. Quote the evidence (file:line or symbol), and say whether the conflict is with
>   a plan *anchor* (path / symbol / layer) or with a stated SPEC *premise* (an Executive-Summary
>   claim, Premise-correction paragraph, Locked Decision, or Validated Assumption).
>
> Files / assumptions to verify:
> [list each candidate file + the one-line assumption the plan makes about it]
>
> Return STRUCTURED findings per file. Do not edit anything. Do not propose the plan — just report
> ground truth.

Use `find_symbol_usages` / `get_callers` to assess blast radius for any symbol the plan will change.

**Fallback — dispatch unavailable:** if this context cannot dispatch subagents (the `Agent` tool
is not exposed to the current agent type, or dispatch is denied by policy in the current run —
e.g. the lazy cycle-subagent inline override), perform the SAME per-file verification inline with
the tree-sitter tools / `Read` / `Grep`, answering every bullet of the briefing above per file.
The gate's substance is the verified audit table, not the dispatch mechanism. Note
`verified: inline (dispatch unavailable)` above the Step C table so the exit check below is
honest about method. Never skip the gate because fan-out failed.

### Step C — Synthesize the verified audit table

Collapse all agent findings into one table. This is the gate's output artifact:

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `src/core/parser.ts` | yes | `class Parser`, `parsePattern()` | refactor | Reuse `parsePattern()`; widen its signature to accept `opts` — do NOT write a new parser |
| `src/composables/useCue.ts` | yes | `useCue()` | reuse | Cue logic lives here, NOT in `Deck.vue` — target this file |
| `src/core/validate.ts` | **NO (net-new)** | — | create | No existing validator; create it next to `parser.ts` |

Rules:
- **No unverified paths.** Every path in the emitted plan/PHASES must appear here as `exists: yes`,
  or be explicitly stamped `net-new (create)`. A path that is neither is a defect — fix it.
- **Name the symbol to reuse.** "Reuse existing code" without a `file:symbol` does not close the
  executor's gap. Be specific enough that the executor extends rather than reinvents.
- **Blast radius.** For each `refactor` row, note who else calls the changed symbol (from
  `get_callers`) so the plan can schedule consumer migration in the same batch.

### Step D — Drift correction (BEFORE the artifact is written)

**Contradiction severity ladder (MANDATORY — classify FIRST, before any correction).** For every
`Contradiction` finding from Step B, classify it on this ladder before touching the plan:

- **Anchor-grade** — the finding changes **WHERE we edit**: file/line drift, a renamed symbol, a
  moved method, an abstraction living in a different layer. Reality disagrees with the plan's
  *anchors*, not with what the feature is supposed to do. Handle per the mechanical-drift /
  design-fork rules below; current behavior is unchanged.
- **Premise-grade** — the finding contradicts a **SPEC premise**: an Executive-Summary claim, a
  "Premise correction" paragraph, a Locked Decision, or a Validated Assumption. If the finding is
  true, it changes **WHAT we build** — correcting it "in the plan" would mean faithfully
  implementing a falsified spec.

**Litmus:** does this finding, if true, change **WHAT** we build (premise-grade) or **WHERE** we
edit (anchor-grade)? Apply it to every contradiction; when in doubt, classify UP — a false halt
costs one question, a demoted premise ships wrong code.

**Premise-grade = HALT.** Never correct a premise-grade contradiction in the plan, and never carry
it forward as a plan-local mitigation:

- **Interactive host skill:** surface the contradiction — quote the Step B evidence (file:line)
  against the exact SPEC text it falsifies — and re-open the premise via `AskUserQuestion`
  BEFORE any drafting continues. The artifact is not written until the premise is confirmed
  or corrected.
- **`--batch`:** write `NEEDS_INPUT.md` per the host skill's existing sentinel conventions,
  quoting both sides (the SPEC premise vs. the audit evidence) in the decision context.

**BANNED — demoting a premise-grade contradiction to a phase-time "trace deliverable".** Turning
"this premise may be false" into "Phase N will trace/verify it" keeps a falsified premise
load-bearing while the plan builds — and hardens — code on top of it.
> **Burned on 57077.** The write-plan audit found "`CognitoOrder`/`CognitoPayment`/`CognitoDispute`
> are `ICosmosEntity` (not `IEntity`) → not swept by `DeleteAllProjectEntities` → the carve-out may
> be a no-op" — a direct falsification of the SPEC's deletion premise — and classified it
> "mechanical drift", downgrading it to a phase-time trace deliverable. The wrong premise shipped,
> got hardened with round-trip tests against a fiction, and stood until a human PR reviewer refuted
> it in one review round ("the cosmos entities are not automatically deleted by anything").

For every **anchor-grade** contradiction, apply the existing two-way split:

- **Mechanical drift** (file moved/renamed, symbol differs, abstraction already exists, target lives
  in a different layer): **correct the plan now.** Rewrite the affected phase boundary / work-unit
  scope / file paths to target reality. Do this silently — it is grounding, not a design decision.
  Record the correction in the plan's notes so the executor sees *why* the path differs from the spec.
- **Genuine design fork** (reality reveals a real product/architecture decision the spec never made —
  e.g. an existing abstraction *could* be reused but doing so changes behavior, or two equally-valid
  homes exist for the new code): do NOT pick arbitrarily. Halt via the host skill's existing
  `NEEDS_INPUT.md` protocol (interactive skills: surface to the user; `--batch`: write the sentinel).
  Mechanical path/naming corrections never halt — only true forks do.

### Step E — Carry the audit into the artifact

The drafting step that follows this gate MUST consume the Step C table:
- **/spec-phases:** every phase's "Files likely modified" uses verified paths + the reuse/refactor
  directive as the "{what changes}" note.
- **/write-plan & /implement-phase{,-batch}:** every work unit's "Files to create/modify" uses
  verified paths, and its "Implementation goal" embeds the reuse/refactor directive so the executor
  extends existing code instead of rediscovering it.
- **/fix{,-mobile}:** the fix's touchpoints are the verified files; the root-cause/fix steps reference
  the real symbols.

**Gate exit check (all must be true before proceeding to draft/write the artifact):**
- [ ] Every candidate touchpoint was verified against the live codebase — by an `Explore` agent,
      or inline per the Step B fallback when dispatch is unavailable (never from memory).
- [ ] The Step C audit table exists and every planned path is `exists: yes` or `net-new`.
- [ ] Every reuse directive names a concrete `file:symbol`.
- [ ] Every contradiction was classified on the severity ladder (anchor-grade vs premise-grade).
      Every anchor-grade one was either corrected in-plan (mechanical) or escalated via
      `NEEDS_INPUT.md` (genuine fork). Every premise-grade one HALTED (`AskUserQuestion` /
      `NEEDS_INPUT.md`) — none was demoted to a phase-time trace deliverable.

If any box is unchecked, do not write the artifact yet.

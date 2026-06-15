# Implementation Phases — Buddy Guidance Enhancement

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this feature edits Claude Code agent/command **markdown prompts** (`agents/journey-planner.md`, `commands/review-pr-buddy.md`, `README.md`) in the `cognito-pr-review` plugin. There is no app integration, build step, compiled code, or MCP-reachable runtime surface. Verification is **manual buddy walk-throughs** against the SPEC's Validation Criteria table (run the command on a real/sample PR and inspect the produced journey file, `buddy-session.json`, and review doc). No automated test harness exists for prompt files, and none is in scope.

## Cross-feature Integration Notes

The sole dependency is `cognito-pr-review-v2 — composes`. `composes` is not a `hard` dep, so the hard-dep upstream PHASES.md look-back (Step 1.5) does not trigger — there is no settled upstream contract this plan must reality-check. This enhancement extends the journey-file Manual Review Guide and the buddy walk loop that `cognito-pr-review-v2` defines, in place, as a peer.

## Touchpoint Audit (verified)

| File | Exists? | Action | Verified anchors + directive |
|------|---------|--------|------------------------------|
| `agents/journey-planner.md` | yes | refactor | Journey File Template — File Change Map table (L96–104, incl. `Tests \| … \| After core` row L102), Manual Review Guide section (L106–122), `_Core changes first, tests last._` note (L108), `Group files logically, not by directory._` note (L104), Behaviour Notes (L205–212). |
| `commands/review-pr-buddy.md` | yes | refactor | Per-Chunk Loop "six steps" (L74–121), `buddy-session.json` schema (L143–172), Phase 2 Collect Curated Content (L184–191), `REVIEWED.md` count template (L226, L238–240), Overview Phase-1 bullet (L22). |
| `README.md` | yes | refactor | Buddy Phase-1 description at **L96** carries the old `keep / dismiss / will-comment / add-own` picker vocabulary and old single-pass framing. |
| `agents/synthesizer-v2.md` | yes | **reuse — DO NOT MODIFY** | Pipeline severity enum is `blocking \| important \| nit` (L29, L42, L108, L113). Sections: `## Critical Findings`, `## Rule-Based Findings` → `### Important` / `### Minor`, `## Reuse & Duplication` → `### Important` / `### Minor`, `## Intra-File Consistency` → `### Important` / `### Minor`, `## Strengths`. **There is no `suggestion` severity and no `### Suggestion` section.** |

**Mechanical drift corrected in-plan (Phase 2):** SPEC §4 specifies a reviewer-facing disposition severity of **Suggestion** and states "Suggestion → minor," but the synthesizer-v2 output format the buddy Phase 2 writer already follows uses `nit` as the minor tier under `### Minor` subsections. The reviewer-facing taxonomy stays **Blocking / Important / Suggestion / Dismiss** (Decision 3), but the Phase 2 writer MUST translate a `suggestion` disposition into the existing `### Minor` (nit) buckets — it must NOT introduce a new `### Suggestion` section, which would break synthesizer-v2 format parity. This is baked into Phase 2's deliverables below.

## Validated Assumptions

- **Phase 1 → Phase 2 field contract (code-provable).** The seam between the two phases is the set of markdown field labels the journey template emits and the buddy parses. This is fully controlled by the author of both files (not a runtime behavior) — Phase 1 fixes the labels, Phase 2 consumes them verbatim. The exact labels are pinned in Phase 1's Integration Notes.
- **Behavioral-clustering quality (runtime-coupled, deferred by design).** Whether the Opus planner *actually* clusters by behavioral thread vs. lapsing into directory groups is observable only by running the planner — it cannot be proven from the prompt text. The SPEC already scopes this as an Open Question validated empirically in **Phase 3**; no earlier spike is warranted because the planner output does not exist until Phase 1 ships. Phase 3's no-regression run is the validation.

---

### Phase 1: Partitioning — `journey-planner.md`

**Scope:** Re-base the journey planner's partitioning guidance and journey-file template on behavioral/dependency clustering. The review unit becomes a self-contained behavioral thread traced across architectural layers; tests are bundled with the code they exercise; an oversized thread is hard-split at 400 LOC; each chunk carries a risk-matched PBR persona, predictive questions, a `complexity` hint, and a `loc_estimate`. This phase defines the **journey field contract** that Phase 2 consumes.

**Deliverables:**
- [x] **1a — Behavioral-thread review unit.** Replace the `_Group files logically, not by directory._` (L104) and Manual Review Guide grouping guidance so each `### Step N` chunk is one behavioral thread spanning the layers that achieve a single objective (e.g. migration + data-access + business-logic together). Add explicit anti-pattern guidance: do not group by directory; do not split one behavioral thread across chunks. State this is LLM-judged by the planner from cached diffs + structural-context (no new tooling).
- [x] **1b — Tests alongside, not last.** Remove the `| Tests | {files} | {purpose} | After core |` row (L102) from the File Change Map template and the `_Core changes first, tests last._` instruction (L108). Each behavioral chunk lists its tests **with** the implementation they exercise, framed as the change's executable oracle; chunk guidance pairs each test with the behavior it covers.
- [x] **1c — Hard 400-LOC split.** Add a planner rule: if a behavioral chunk's changed LOC > 400, subdivide along data-flow / architectural boundaries into sub-chunks each ≤ 400 LOC. No session-time / 60-min ceiling is emitted. Record a per-chunk `loc_estimate` in the journey so the buddy can verify the cap held.
- [x] **1d — Per-chunk persona + predictive questions.** Replace the Manual Review Guide's `**What to look for:**` / `**Key questions:**` fields with **`**Perspective:**`** (a risk-matched PBR persona — e.g. security auditor for API/data-access, DBA for a migration, performance tester for a hot path, concurrency auditor for shared mutable state) and **`**Predictive questions:**`** (boundary-condition / failure-mode questions forcing predictive simulation, not descriptive recall).
- [x] **1e — Complexity signal.** Each chunk carries a `**Complexity:** trivial | non-trivial` hint set from intrinsic difficulty (cross-layer span, unfamiliar subsystem, algorithmic density). Default to `non-trivial` when uncertain. Document that the buddy uses it to scale teach depth.
- [x] **1f — Risk-first ordering.** Among behavioral threads, retain risk-first ordering (critical threads first). Re-Review Priority Order (L69–74) is unchanged in intent but now applies at the behavioral-thread level — update its wording to refer to threads, not bare files.
- [x] Update the Journey File Template (L81–132) and Behaviour Notes (L205–212) to reflect 1a–1f, replacing the generic "Key questions" Behaviour Note (L209) with persona/predictive-question guidance.

#### Implementation Notes (Phase 1)
**Completed:** 2026-06-15
**Work completed:**
- 1a–1f + template/Behaviour-Notes: `agents/journey-planner.md` restructured so the File Change Map header is `Behavioral Thread`, the `| Tests |` row is removed, the Manual Review Guide clusters by behavioral thread (anti-pattern guidance against directory grouping and thread-splitting), the 400-LOC subdivide rule is stated, and each `### Step N` chunk emits the contract fields.
**Field-label contract shipped (load-bearing for Phase 2 — parse these verbatim):**
- `**Files:**`
- `**Perspective:**` (the word is **Perspective**, NOT "Persona")
- `**Predictive questions:**`
- `**Complexity:**` with values `trivial` | `non-trivial`
- `**loc_estimate:**` (grep token `loc_estimate`)
**Integration notes:**
- Phase 2 (`review-pr-buddy.md`) must parse exactly the spellings above; the chunk-extraction copy at the old `**What to look for:**`/`**Key questions:**` site must be replaced with `**Perspective:**`/`**Predictive questions:**`/`**Complexity:**`.
- `complexity` defaults to `non-trivial`; Phase 2's teach-by-complexity branch must treat missing/ambiguous as `non-trivial`.
**Pitfalls & guidance:**
- Part 2 (Triage Validation), Cache-Based File Access, and Input/Output Specification were intentionally left untouched.
**Files modified:**
- `agents/journey-planner.md` — File Change Map table + footer, Manual Review Guide intro + clustering rules + Step template, Re-Review Priority Order wording (thread-level), Behaviour Notes.
**Grep consistency checks:** `| Tests |`=0, `Core changes first, tests last`=0, `Group files logically, not by directory`=0, `Perspective:`=2, `Predictive questions:`=2, `Complexity:`=2, `loc_estimate`=4 — all pass.
**Review verdict:** PASS — ground-truth verified (status/wc/greps matched the subagent block exactly); field-contract spellings exact; no collateral damage.
**Manual rows:** the Phase 1 "Runtime Verification" deliverables remain unchecked — they are Jacob's manual buddy-walk acceptance, not subagent-executable.

**Minimum Verifiable Behavior:** Run the review prep (or `/review-pr` Steps 1–8, which dispatches the journey-planner) on a real multi-layer PR; the produced `PR-{id}-journey.md` Manual Review Guide shows behavioral-thread chunks (each spanning files across layers for one objective), no standalone tests-last chunk, a `Complexity` and `loc_estimate` on every chunk, and a `Perspective` + `Predictive questions` pair per chunk — verifiable without any Phase 2 change.

**Runtime Verification** *(checked by manual buddy walk-through — there is no automated harness):*
- [ ] On a multi-layer PR, every Manual Review Guide chunk is a behavioral thread, not a directory-named group.
- [ ] No chunk's `loc_estimate` exceeds 400; an oversized thread is subdivided.
- [ ] No standalone "tests last" chunk exists; each chunk lists its tests alongside the code they exercise.
- [ ] Every chunk emits `Perspective`, `Predictive questions`, `Complexity`, and `loc_estimate`.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `agents/journey-planner.md` — File Change Map template, Manual Review Guide template + ordering note, Re-Review Priority Order wording, Behaviour Notes.

**Testing Strategy:** Manual. Run prep on (a) a multi-layer PR and (b) a large (>400 changed-LOC thread) PR; inspect the journey file against the four Runtime Verification rows above. No unit tests exist for prompt files.

**Integration Notes for Next Phase:**
- **Field-label contract (load-bearing for Phase 2).** Phase 2's buddy parser must read these exact labels, verbatim, from each `### Step N` chunk: `**Files:**`, `**Perspective:**`, `**Predictive questions:**`, `**Complexity:**` (values `trivial`|`non-trivial`), and the per-chunk `loc_estimate`. Pin whichever spelling Phase 1 ships and do not let Phase 2 drift (e.g. `Persona` vs `Perspective`).
- The chunk is now the unit of *behavioral* grouping; the buddy's "a finding belongs to a chunk if its `file` is in the chunk's `Files` list" rule (review-pr-buddy.md L70–71) still holds, since chunks still enumerate their files.
- `complexity` defaults to `non-trivial` — Phase 2's teach-by-complexity branch must treat a missing/ambiguous value as `non-trivial`.

---

### Phase 2: Guiding loop — `review-pr-buddy.md`

**Scope:** Replace the single-pass six-step per-chunk loop with the two-pass loop (orient → independent read → reconcile → disposition), scale teaching to chunk `complexity`, replace the disposition verbs with the severity taxonomy, add explicit AI-role framing, bump the `buddy-session.json` schema, and update the Phase 2 curated-synthesis severity→section mapping and `REVIEWED.md` counts. Consumes the Phase 1 journey field contract.

**Deliverables:**
- [x] **Two-pass loop (Decision 1).** Rewrite the Per-Chunk Loop (L74–121) to:
  1. **Orient (Decision 2).** Always state a one-line chunk objective. If `Complexity` is `non-trivial`, add a senior-architect teach of what changed and why it matters vs. the journey Objective; for `trivial`, the one-liner is the whole orientation. Deep teaching otherwise available only on explicit reviewer request.
  2. **Independent read — Pass 1.** Present the chunk (implementation + its bundled tests) and pose the chunk's `Perspective` persona + `Predictive questions`. The reviewer reads cold and records their own observations. **Tool findings are NOT shown in this pass** (anti-anchoring). Include explicit AI-role framing: the buddy is a facilitator; the reviewer is sole arbiter of logic correctness.
  3. **Reconcile — Pass 2.** Reveal the chunk's pre-computed findings (investigation / sweep / reuse / intrafile) as a reconciliation against the reviewer's Pass-1 take: overlaps, tool-only flags, and (implicitly) what the tool may have missed.
  4. **Disposition (Decision 3).** For every finding — tool-surfaced and reviewer-authored — capture a **severity** via `AskUserQuestion`: **Blocking / Important / Suggestion / Dismiss**, with an optional free-text note on any non-dismissed finding (this subsumes the old `will-comment`). `add-own` becomes the mechanism by which a Pass-1 observation becomes a severity-tagged finding.
  5. **Checkpoint** to `buddy-session.json`.
  6. **Advance.**
- [x] **AI-role scoping (SPEC §5).** Bake the facilitator framing into the Pass-1 and Pass-2 copy so the reviewer does not defer to the tool on business-logic correctness.
- [x] **`buddy-session.json` schema bump (SPEC §3).** Per-chunk record gains `complexity` (`trivial|non-trivial`), `loc_estimate` (int), and `pass1_observations[]` (`{file, line, note}`). Replace the disposition `verdict` enum `keep|dismiss|will-comment|add-own` with a `severity` field (`blocking|important|suggestion|dismiss`) and add a `source` field (`investigation|sweep|reuse|intrafile|reviewer`). Update the schema block (L143–172) and every reference to the old enum (L104–109, L184–191).
- [x] **Phase 2 severity→section mapping (SPEC §4 + drift correction).** Map dispositions onto the **existing** synthesizer-v2 sections: **Blocking** → `## Critical Findings` (investigation-sourced) / `### Important` (rule/reuse/intrafile); **Important** → `### Important` subsections; **Suggestion** → the existing **`### Minor` (nit)** subsections — do **not** create a `### Suggestion` section. **Dismiss** → excluded. Update Collect Curated Content (L184–191) accordingly.
- [x] **`REVIEWED.md` counts.** Derive `critical` = blocking count, `important` = important count, `minor` = suggestion count from the severity tally (L226, L238–240).
- [x] Update the Overview Phase-1 bullet (L22) and Compaction Recovery references (L72, L132–139) so resume language matches the two-pass loop (recovery still resumes at the first chunk whose `status` ≠ `done`; mechanism unchanged).

#### Implementation Notes (Phase 2)
**Completed:** 2026-06-15
**Work completed:**
- Two-pass loop: rewrote the Per-Chunk Loop in `commands/review-pr-buddy.md` from the single-pass six-step (Teach/Surface/Socratic/Verdict/Checkpoint/Advance) to Orient → Independent Read (Pass 1) → Reconcile (Pass 2) → Disposition → Checkpoint → Advance. Pass 1 withholds tool findings (anti-anchoring); orientation scales to `Complexity` (one-liner for `trivial`, fuller teach for `non-trivial`/missing).
- AI-role framing baked into both Pass-1 and Pass-2 copy: buddy is facilitator, reviewer is sole arbiter of business-logic correctness, tool is a mechanical-triage/cross-file aid.
- Schema bump: per-chunk record gained `complexity`, `loc_estimate`, `pass1_observations[]`; disposition `verdict` enum replaced with `severity` (`blocking|important|suggestion|dismiss`) + new `source` (`investigation|sweep|reuse|intrafile|reviewer`).
- Severity→section mapping and `REVIEWED.md` count derivation + Overview/Compaction-Recovery/report wording all updated.
**Drift guard (held):** `suggestion` maps to the existing `### Minor` (nit) subsections — copy explicitly says "never introduce a new suggestion-level heading." `agents/synthesizer-v2.md` was NOT modified (`git diff --name-only` lists only `review-pr-buddy.md`). `grep -c "### Suggestion"` = 0.
**Field contract (consumed verbatim from Phase 1):** chunk-extraction copy now reads `**Files:**`, `**Perspective:**`, `**Predictive questions:**`, `**Complexity:**`, `**loc_estimate:**`; old `**What to look for:**`/`**Key questions:**` labels are absent (grep = 0). Old buddy verbs `will-comment`/`add-own` removed (grep = 0).
**Integration notes:**
- Reviewer-facing vocabulary (Blocking/Important/Suggestion/Dismiss) + two-pass loop are the user-visible behaviors Phase 3's README update must describe. Phase 3 must NOT document a new synthesizer section.
**Files modified:**
- `commands/review-pr-buddy.md` — Overview Phase-1/2 bullets, Setup chunk-extraction labels, Per-Chunk Loop (six steps rewritten as two-pass), `buddy-session.json` schema, Collect Curated Content severity→section mapping, REVIEWED.md count derivation, Cleanup/report counts, Compaction Recovery wording.
**Grep consistency checks:** `will-comment`=0, `add-own`=0, `What to look for`=0, `Key questions`=0, `pass1_observations`=4, `severity`=14, `### Suggestion`=0, `Perspective:`=2, `Predictive questions:`=2, `Complexity:`=2, `loc_estimate`=2, `source`=13 — all pass.
**Review verdict:** PASS — ground-truth re-run matched the subagent's block exactly; inline diff review confirmed all six deliverables; propagation check clean (only spec docs + README/WU-3 reference old vocab, by design).
**Manual rows:** Phase 2 "Runtime Verification" deliverables remain unchecked — Jacob's manual buddy-walk acceptance, not subagent-executable.

**Minimum Verifiable Behavior:** Walk a single non-trivial chunk in the buddy on a PR whose journey was produced by Phase 1: the buddy gives a fuller teach (vs. a one-liner on a trivial chunk), presents the chunk + tests and the persona/predictive questions, **withholds tool findings until the reconcile step**, then captures a Blocking/Important/Suggestion/Dismiss severity per finding via `AskUserQuestion` — and `buddy-session.json` records `pass1_observations[]` plus `severity`/`source` per disposition.

**Runtime Verification** *(checked by manual buddy walk-through — no automated harness):*
- [ ] Tool findings are not shown during Pass 1; they appear only at the reconcile step.
- [ ] A `trivial` chunk gets a one-line orientation; a `non-trivial` chunk gets a fuller teach.
- [ ] Each disposition in `buddy-session.json` carries a `severity` (`blocking|important|suggestion|dismiss`) and a `source`; `pass1_observations[]` is populated when the reviewer records cold observations.
- [ ] The curated `PR-{id}.md` places a `suggestion` finding under `### Minor` (no `### Suggestion` section appears); `REVIEWED.md` counts match the severity tally.

**Prerequisites:**
- Phase 1: the journey field contract (`Perspective`, `Predictive questions`, `Complexity`, `loc_estimate`) — the buddy parses these labels verbatim. Phase 2 cannot be meaningfully walked until Phase 1 emits compatible journey files.

**Files likely modified:**
- `commands/review-pr-buddy.md` — Overview bullet (L22), Per-Chunk Loop (L74–121), `buddy-session.json` schema (L143–172), Compaction Recovery refs (L132–139), Phase 2 Collect Curated Content (L184–191), `REVIEWED.md` template (L226–240).

**Testing Strategy:** Manual. Walk one `trivial` and one `non-trivial` chunk; confirm the four Runtime Verification rows. Inspect `buddy-session.json` for schema conformance and the curated `PR-{id}.md` for correct severity→section placement (especially `suggestion`→`### Minor`).

**Integration Notes for Next Phase:**
- The reviewer-facing severity vocabulary (Blocking/Important/Suggestion/Dismiss) and the two-pass loop are the user-visible behaviors Phase 3's README update must describe.
- `synthesizer-v2.md` was NOT modified — Phase 2 only maps onto its existing sections. Phase 3 must not document a new synthesizer section.
- If validation (Phase 3) surfaces loop-copy tweaks (e.g. orientation wording, AI-role framing), they land here in `review-pr-buddy.md` — Phase 3 owns README only.

---

### Phase 3: Validation + docs

**Scope:** Empirically validate the restructured flow against the SPEC's Validation Criteria and update user-facing documentation. This is the acceptance gate for the whole feature; it also answers the SPEC's behavioral-clustering Open Question.

**Deliverables:**
- [ ] **No-regression validation.** Re-run the buddy on a sample of previously-reviewed PRs (those with an existing `PR-{id}.md`). Confirm the reviewer surfaces ≥ the findings caught under the old flow, the ordering/caps/personas hold, findings are withheld until Pass 2, and teach scales to complexity. Record results as a short validation note in this spec directory (e.g. `VALIDATION.md`) — not in code.
- [ ] **Behavioral-clustering check (Open Question).** During the runs above, judge whether the planner clustered by behavioral thread or lapsed into directory groups. If prompt-level clustering proves unreliable, note it as a Tier-2 follow-up (deterministic AST/data-flow tooling) — out of scope to fix here.
- [x] **README update.** Rewrite `README.md` L96 (and the surrounding Buddy Review section, L83–96 as needed) to describe the two-pass loop (independent read → reconcile) and the Blocking/Important/Suggestion/Dismiss severity vocabulary, replacing the old `keep / dismiss / will-comment / add-own` + single-pass framing.

#### Implementation Notes (Phase 3 — executable portion only)
**Completed:** 2026-06-15
**Work completed:**
- README update (executable): rewrote the `### Buddy Review` Phase-1 paragraph to describe the two-pass loop — orient (scaled to chunk complexity), Pass 1 independent read (tool findings withheld, anti-anchoring, reviewer is sole arbiter of business-logic correctness), Pass 2 reconcile + per-finding severity (Blocking/Important/Suggestion/Dismiss) with optional comment note; surfaced the risk-matched Perspective persona + Predictive questions. Updated Phase-2 paragraph to "non-dismissed findings … annotated with their severities." Phase 0 + command block left byte-for-byte intact; only the Buddy Review section changed.
- `VALIDATION.md` scaffold (executable): created net-new `docs/specs/buddy-guidance-enhancement/VALIDATION.md` as an EMPTY acceptance checklist — heading, one-line purpose, 5-column table (Behavior | Trigger | Expected Evidence | Result | Notes) populated with all 8 SPEC Validation Criteria rows verbatim, Result/Notes left blank, plus an unselected "Behavioral-clustering quality" line. No results fabricated.
**Drift guard (held):** `agents/synthesizer-v2.md` NOT modified (`git diff --name-only` lists only `README.md`); no `### Suggestion` section heading introduced — README mentions the Suggestion *severity* in prose only, which is the required user-facing vocabulary.
**Manual deliverables intentionally left unchecked:** "No-regression validation" and "Behavioral-clustering check (Open Question)" are Jacob's manual buddy-walk acceptance — they require running the buddy on real PRs and recording outcomes in the scaffolded `VALIDATION.md`. The scaffold is shipped; the runs are not subagent-executable.
**Files modified:**
- `README.md` — Buddy Review section (Phase 1 + Phase 2 paragraphs).
- `docs/specs/buddy-guidance-enhancement/VALIDATION.md` — net-new scaffold.
**Grep consistency checks:** `keep / dismiss / will-comment / add-own`=0, `will-comment`=0, `add-own`=0, severity vocab (`Blocking|Important|Suggestion|Dismiss`)=1, two-pass/anti-anchor mention=1, `VALIDATION.md` exists — all pass.
**Review verdict:** PASS — ground-truth re-run matched the subagent block; inline diff + new-file review confirmed both deliverables; mount-site check confirmed VALIDATION.md is in the spec dir PHASES.md references.

**Minimum Verifiable Behavior:** A `VALIDATION.md` note exists recording the buddy re-run on ≥1 prior PR with a pass/fail against each SPEC Validation Criteria row, and `README.md` no longer contains the strings `keep / dismiss / will-comment / add-own` (its Buddy section describes the two-pass loop + severity vocabulary).

**Runtime Verification** *(checked by manual buddy walk-through — no automated harness):*
- [ ] On a re-run of a prior PR, the reviewer surfaces no fewer real defects than the archived `PR-{id}.md` recorded.
- [ ] The behavioral-clustering quality is recorded (reliable / needs Tier-2 follow-up).
- [ ] `README.md` Buddy section matches the shipped two-pass loop + severity vocabulary.

**Prerequisites:**
- Phase 1 and Phase 2 complete (the journey planner emits the new fields and the buddy walks the two-pass loop).

**Files likely modified:**
- `README.md` — Buddy Review section (L83–96).
- `docs/specs/buddy-guidance-enhancement/VALIDATION.md` — **net-new (create)** — validation note.

**Testing Strategy:** Manual end-to-end. Pick PRs with archived reviews of varying size/complexity (at least one multi-layer and one >400-LOC thread); run the buddy; compare surfaced findings to the archive; verify each SPEC Validation Criteria row.

**Integration Notes for Next Phase:** None — final phase. **Completion (gate-owned):** flipping SPEC.md `**Status:**` to Complete is owned by the completion gate once Phase 3's validation passes; it is not a checkbox here.

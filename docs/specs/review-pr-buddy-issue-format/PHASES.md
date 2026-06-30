# Implementation Phases — Standardized Post-Disposition Issue Format

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is skill/plugin prose; no app runtime or MCP-reachable surface exists in this repo.

## Validated Assumptions

The following were confirmed by read-only Explore audits of the actual codebase. The executor must not re-litigate these.

- **No data-layer / TypeScript change is required.** Every field needed to author the proposed fix and draft PR comment already exists in `processed-findings.json` and is generated at RENDER time. Per source (verified against `scripts/post-process.ts` + agent schemas): `investigation`, `reuse`, and `intrafile` carry `suggestion` + `evidence.snippet` + `evidence.reference` + `hypothesis` (reuse/intrafile also carry `verdict`, `candidate`, `blast_radius`). `sweep` is the ONLY source with NO `evidence.snippet` — it carries `title`, `description`, `suggestion`, `rule_id`, `rule_category`. NO source carries any existing comment/draft field; the "Proposed PR comment" is entirely net-new generated text for all sources. `scripts/post-process.ts` `step4_rank` produces a stable `tier → severity → effective_weight` sort; the renderer MUST preserve it (do not re-sort).
- **The disposition-calibration join is unaffected.** `scripts/disposition-calibration.ts` parses only the leading `<file>:<line>` token from `buddy-session.json` dispositions and joins against `processed-findings.json`; it never reads the rendered `PR-{id}.md`. Adding prose sections to the rendered document or in-chat digest cannot break calibration. The new block MUST NOT alter the canonical `<file>:<line>` / `<file>#<slug>` finding IDs — new sections are additive only.
- **Snippet-grounding asymmetry (a real design constraint carried into both phases).** The `synthesizer-v2` agent is cache-only (`Do NOT read from the local codebase`), so its concrete snippet must come from the cached `evidence.snippet` only; sweep findings (no snippet) get a PROSE fix. The `review-pr-buddy` orchestrator HAS local-`main` read access (the investigation-style carve-out) and MAY ground a richer/fresher snippet, including for sweep. The two surfaces share the SAME block FORMAT; only snippet richness may differ. This asymmetry is documented in both phases below.

---

### Phase 1: Define + apply the standardized issue block in `synthesizer-v2.md` (format SSOT)

**Scope:** Rewrite the per-finding rendering inside the existing `## Output Format` sections of `synthesizer-v2.md` so that every kept finding — across all four sources (investigation, sweep, reuse, intrafile) — is rendered in the canonical standardized block. This file is the single source of format truth (SSOT); Phase 2 consumes the format by reference. Section grouping, omission rules, and the existing tier→severity→weight ordering note are preserved; only the per-finding shape changes.

**Deliverables:**
- [x] Canonical standardized block shape defined inside `synthesizer-v2.md` (as a format reference, e.g., in a new `## Standardized Issue Block` or within `## Output Format` preamble):
  ```
  ### {Issue title}
  **Severity:** {Blocking|Important|Suggestion}   **Source:** {investigation|sweep|reuse|intrafile|reviewer}   **Location:** {file}:{line}   **Confidence:** {CONFIRMED|UNVERIFIED|—}
  **What:** {1–2 line issue statement + why it matters — from hypothesis/description/evidence}
  **Proposed fix:** {concrete before→after snippet when cheap & snippet available; precise prose steps otherwise (always prose for sweep under cache-only)}
  **Proposed PR comment:** {ready-to-paste draft, reviewer-voiced, references file:line — net-new generated text; never auto-posted}
  ```
- [x] All four per-finding render sections (`## Critical Findings` / investigation, `## Rule-Based Findings` / sweep, `## Reuse & Duplication` / reuse, `## Intra-File Consistency` / intrafile) re-expressed to render every kept finding in the uniform block above.
- [x] Per-source field-sourcing guidance present for each source: which JSON fields feed **What** (investigation: `hypothesis`; sweep: `description`; reuse/intrafile: `hypothesis` or `description`), **Proposed fix** (investigation/reuse/intrafile: `suggestion` + `evidence.snippet` when available; sweep: `description` + `suggestion`, prose only), and **Proposed PR comment** (net-new generated text seeded from the fix + `evidence.reference`).
- [x] Fix-form rule explicitly stated: concrete before→after snippet/diff when the fix is small/local AND `evidence.snippet` is available; precise prose resolution steps otherwise. For sweep under the cache-only constraint: always prose (never attempt a live local read).
- [x] Cache-only snippet constraint stated in the `## Cache Boundary` section (or its equivalent): synthesizer-v2 MUST NOT read from the local codebase; snippets sourced exclusively from `evidence.snippet` in `processed-findings.json`.
- [x] Comment style rule stated: draft PR comment is terse, reviewer-voiced, references `file:line` directly; it is what the reviewer pastes on the PR (never auto-posted per `user/CLAUDE.local.md`).
- [x] Section grouping (`## Critical Findings`, `## Rule-Based Findings`, `## Reuse & Duplication`, `## Intra-File Consistency`) and omission rules explicitly preserved (sections with zero kept findings remain omitted).
- [x] Ordering note preserved and called out explicitly: findings are pre-sorted by `tier → severity → effective_weight` by `step4_rank`; DO NOT re-sort inside the renderer.

**Minimum Verifiable Behavior:** Opening `synthesizer-v2.md` and reading `## Output Format` (and surrounding sections) shows a single canonical block shape applied uniformly across all four source types, with per-source field-sourcing notes, the fix-form rule (snippet-when-cheap-else-prose), the cache-only snippet constraint, and a sweep-specific prose-only note. The existing section grouping/omission/ordering rules remain intact and are explicitly called out.

**Runtime Verification** *(checked by inspection / dry-run — NOT by an implementation agent):*
- [ ] <!-- verification-only --> `## Output Format` (or its preamble) in `synthesizer-v2.md` shows the standardized block for all four finding sources — no source retains the old heterogeneous shape (investigation's `**File:** / **Severity:** / **Evidence:** / **Suggestion:**` headers, or sweep/reuse/intrafile one-line bullets).
- [ ] <!-- verification-only --> The sweep section's fix guidance explicitly says "prose only" and does not reference `evidence.snippet` (which sweep findings do not carry).
- [ ] <!-- verification-only --> The cache-only constraint in `## Cache Boundary` (or equivalent) still prohibits local codebase reads; no new instruction contradicts it.
- [ ] <!-- verification-only --> The ordering note ("do not re-sort; findings pre-sorted by tier→severity→weight") is present and unaltered.
- [ ] <!-- verification-only --> Section omission rules (omit sections with zero kept findings) are present and unaltered.
- [ ] <!-- verification-only --> Dry-run (optional): feed a representative `processed-findings.json` with one finding per source type to a synthesizer-v2 session; confirm each finding renders in the standardized block with the correct field sourcing and fix form.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; this is skill/agent-prose defining output format.

**Prerequisites:** None (first phase)

**Files likely modified:**
- `user/plugins/local-tools/plugins/cognito-pr-review/agents/synthesizer-v2.md` — rewrite per-finding rendering in all four source sections to the standardized block; add/update field-sourcing guidance, fix-form rule, cache-only snippet note, comment style rule; preserve section grouping, omission rules, and ordering note.

**Testing Strategy:** Manual inspection of the edited `synthesizer-v2.md` against the standardized block shape defined in the SPEC. Optional: dry-run the agent against a small `processed-findings.json` fixture (one finding per source type) to confirm the rendered output matches the block format. No automated test harness exists for markdown skill prose.

**Integration Notes for Next Phase:** Phase 2 consumes the standardized block format by reference ("the exact synthesizer-v2 output format defined in `agents/synthesizer-v2.md`"). Complete Phase 1 and verify the block is present in `synthesizer-v2.md` before beginning Phase 2. The two phases are file-disjoint (`synthesizer-v2.md` vs. `review-pr-buddy.md`) but MUST run sequentially because Phase 2 references the block shape defined here.

#### Implementation Notes — Phase 1 (2026-06-30)

**Status:** Complete. **Review verdict:** PASS (inline orchestrator edit — markdown prose, plan-permitted; verified via re-read + grep, no subagent ground-truth block applicable).

**Work completed:** Added a new `## Standardized Issue Block` SSOT section to `synthesizer-v2.md` (block shape + per-source field-sourcing table + fix-form rule + comment-style rule). Re-expressed all four `## ` source sections in the `## Output Format` template (`Critical Findings`/investigation, `Rule-Based Findings`/sweep, `Reuse & Duplication`/reuse, `Intra-File Consistency`/intrafile) to render every kept finding in the uniform block; dropped the old heterogeneous shapes (investigation's `File/Severity/Evidence/Suggestion` subsection; the sweep/reuse/intrafile `### Important`/`### Minor` one-line bullets). Reaffirmed cache-only snippet sourcing in `## Cache Boundary`.

**Decisions:** Removed the `### Important`/`### Minor` severity sub-bucketing from sweep/reuse/intrafile (it was part of the old per-finding shape, not the four-`##`-section grouping). Uniformity is achieved by carrying tier in the block's inline `**Severity:**` field; pre-sort order is preserved (each section's render note says "do not re-sort"). File grew 193 → 228 lines.

**Invariants verified intact:** (1) calibration IDs — N/A in this file (no finding-ID definitions); (2) ordering note unaltered (L213, L228); (3) `## Section Omission Rules` unaltered (L202-208); (4) `## Cache Boundary` still prohibits local-codebase reads (L222).

**Files modified:** `user/plugins/local-tools/plugins/cognito-pr-review/agents/synthesizer-v2.md`.

---

### Phase 2: Apply the format in `review-pr-buddy.md` — Phase-2 artifact + new in-chat digest

**Scope:** Update `review-pr-buddy.md` to (a) generate a proposed fix and draft PR comment per kept finding during Phase 2 synthesis, (b) emit those in the standardized block format (defined in Phase 1 / `synthesizer-v2.md`) inside `PR-{id}.md`, and (c) render a new in-chat standardized digest at session close ("Cleanup and Report"). The buddy orchestrator has local-`main` read access and may ground richer snippets than the cache-only synthesizer-v2 path — the same block FORMAT is used on both surfaces; only snippet richness may differ. Finding IDs are not altered (additive-only changes).

**Deliverables:**
- [x] "Collect Curated Content" (≈L296–309) updated: for each kept finding, the buddy generates a proposed fix (snippet-when-cheap using local-`main` read access, else prose) and a draft PR comment (terse, reviewer-voiced, references `file:line`). If the finding carries a reviewer `note`, fold it into / seed the draft PR comment.
- [x] "Review Document Format" (≈L311–328) updated: `PR-{id}.md` emits the standardized block from Phase 1 / `synthesizer-v2.md` for every kept finding. The section referencing "the exact synthesizer-v2 output format" is updated to reflect the new standardized block shape.
- [x] Buddy local-`main` snippet-grounding allowance documented alongside the fix-generation step: buddy MAY use a fresher/richer snippet from local `main` for the "Proposed fix" (including for sweep, which has no `evidence.snippet`); the block FORMAT remains identical to the synthesizer-v2 output — only snippet richness may differ. The asymmetry is explicit.
- [x] "Cleanup and Report" (≈L384–400) updated: at session close, renders a NEW in-chat standardized digest of all kept findings (most-important-first, same block format as `PR-{id}.md`) instead of reporting only counts/paths. The artifact path, journey path, finding counts, and REVIEWED.md status remain present alongside the digest.
- [x] Finding ID Convention (≈L74–81) left unaltered: canonical `<file>:<line>` / `<file>#<slug>` IDs that the disposition-calibration join depends on are not changed by any of the above. All new sections are additive only.

**Minimum Verifiable Behavior:** Opening `review-pr-buddy.md` shows: "Collect Curated Content" instructs per-finding fix + draft-comment generation (with reviewer `note` folding); "Review Document Format" emits the standardized block in `PR-{id}.md` by reference to Phase 1's format; "Cleanup and Report" renders the in-chat digest in the same standardized block format, most-important-first. The "Finding ID Convention" section is unmodified.

**Runtime Verification** *(checked by inspection / dry-run — NOT by an implementation agent):*
- [ ] <!-- verification-only --> "Collect Curated Content" in `review-pr-buddy.md` explicitly instructs generating a proposed fix and draft PR comment for every kept finding, with the reviewer `note` folded into the draft comment when present.
- [ ] <!-- verification-only --> The buddy's local-`main` snippet-grounding allowance is documented alongside the fix-generation step, with the asymmetry vs. synthesizer-v2 (cache-only) called out explicitly.
- [ ] <!-- verification-only --> "Review Document Format" references the standardized block format (from `synthesizer-v2.md` / Phase 1) and no longer describes the old heterogeneous per-source shapes.
- [ ] <!-- verification-only --> "Cleanup and Report" renders an in-chat digest using the standardized block format (not counts/paths only); the digest is ordered most-important-first.
- [ ] <!-- verification-only --> "Finding ID Convention" section is byte-identical to its pre-edit state (or functionally unchanged): `<file>:<line>` / `<file>#<slug>` canonical IDs remain unaltered.
- [ ] <!-- verification-only --> Dry-run (optional): walk a buddy session through Phase 2 with a small `buddy-session.json` fixture; confirm `PR-{id}.md` contains standardized blocks and the in-chat close prints the digest in the standardized format, most-important-first.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; this is skill/agent-prose defining output format.

**Prerequisites:** Phase 1 — the standardized block format must be defined and verified in `synthesizer-v2.md` before Phase 2 references it. Do not begin Phase 2 until Phase 1's Runtime Verification rows have been checked.

**Files likely modified:**
- `user/plugins/local-tools/plugins/cognito-pr-review/commands/review-pr-buddy.md` — update "Collect Curated Content" (fix + draft-comment generation, reviewer `note` folding, local-`main` snippet-grounding note), "Review Document Format" (standardized block emission in `PR-{id}.md`), and "Cleanup and Report" (new in-chat standardized digest); leave "Finding ID Convention" unaltered.

**Testing Strategy:** Manual inspection of the edited `review-pr-buddy.md` sections against the deliverables above. Confirm "Finding ID Convention" is unmodified by diffing against the pre-edit state. Optional: dry-run the buddy through a Phase 2 pass with a small fixture to confirm both surfaces (artifact + in-chat) render the standardized block correctly and in the right order.

**Integration Notes for Next Phase:** No further phases. After Phase 2 is verified, the standardized block format is live on both surfaces (autonomous `/review-pr` via `synthesizer-v2.md`; buddy Phase 2 + in-chat close via `review-pr-buddy.md`). The two files are now bound by the existing format-reference coupling ("the exact synthesizer-v2 output format") — future format changes go into `synthesizer-v2.md` first, then `review-pr-buddy.md` by reference, preserving the SSOT discipline.

#### Implementation Notes — Phase 2 (2026-06-30)

**Status:** Complete. **Review verdict:** PASS (inline orchestrator edit — markdown prose, plan-permitted; verified via `git diff -U0` hunk scoping + grep, no subagent ground-truth block applicable).

**Work completed:** Three edits to `review-pr-buddy.md`. (1) `### Collect Curated Content` — added buddy-authored per-finding "Proposed fix" + "Proposed PR comment" generation; reconciled the now-stale severity→`### Important`/`### Minor` mapping into a `source`→`## section` map (Phase 1 removed the sub-bucketing); documented the local-`main` snippet-grounding allowance and the cache-only-vs-local asymmetry; reviewer `note` folds into the draft comment. (2) `### Review Document Format` — updated the "exact synthesizer-v2 output format" coupling clause to require the Standardized Issue Block for every kept finding and to explicitly retire the old heterogeneous per-source shapes; preserved buddy's section grouping/names and omission rules. (3) `### Cleanup and Report` — added the NEW in-chat standardized digest (most-important-first, same block as `PR-{id}.md`) alongside the existing paths/counts/REVIEWED.md status.

**Drift reconciliation:** The plan's L309 "do NOT invoke the synthesizer-v2 agent" rule was preserved and reframed — the new fix/comment authoring is buddy-authored INLINE synthesis, not an agent call (no contradiction). The severity→subsection mapping was reconciled to match the Phase-1 uniform format (this kept the buddy consistent with the SSOT it consumes by reference).

**Invariants verified intact:** (1) calibration IDs — `### Finding ID Convention` (L74–81) byte-unchanged, confirmed by `git diff` (no hunk touches that region); (2) ordering — both edits state "do not re-sort" / pre-computed `tier → severity → effective_weight`; (3) omission rules preserved in Review Document Format; (4) cache boundary — synthesizer-v2 stays cache-only (Phase 1); buddy's local-`main` snippet is the documented allowed asymmetry, not a boundary violation. File grew 425 → 434 lines.

**Files modified:** `user/plugins/local-tools/plugins/cognito-pr-review/commands/review-pr-buddy.md`.

---

### Phase 3: Apply the standardized block to the buddy's pre-disposition reveal (Phase-1 Reconcile / Pass 2) — D5

**Status:** Complete
**Phase kind:** design

**Scope:** Update `review-pr-buddy.md`'s Phase-1 interactive walk so that the **Reconcile — Pass 2** step (≈L139–178) reveals each pre-computed finding in the **Standardized Issue Block** defined in Phase 1 (`synthesizer-v2.md`) — `### {Issue title}` + `**Severity:** / **Source:** / **Location:** / **Confidence:**`, then `**What:**`, `**Proposed fix:**`, and `**Proposed PR comment:**` — *before* the disposition prompt, so the reviewer sees the proposed fix and the ready-to-paste draft PR comment at the moment they disposition each finding (D5). Pre-disposition, the block's `**Severity:**` carries the **recommended/tool-computed** severity (tier/verdict-derived, distinct from the not-yet-made reviewer disposition); `**Confidence:**` carries the existing `CONFIRMED`/`UNVERIFIED`/`—` label. This is **buddy-only** — the autonomous `/review-pr` / `synthesizer-v2` path has no disposition stage and is NOT touched. The change is to the pre-disposition *display*; it does not alter the Step-4 disposition prompt, the finding-ID convention, or the pre-filters.

**Deliverables:**
- [x] "Reconcile — Pass 2" (≈L167–178) updated: replace the terse grouped-by-source bullet reveal with the Standardized Issue Block for each finding that passes the pre-filters. The block is the same shape Phase 1 defined and Phase 2 emits — only the **Severity** semantics differ pre-disposition (recommended/tool-computed, not the reviewer's verdict). Findings remain **grouped by source** under their section headings (Investigation / Sweep / Reuse & duplication / Intra-file) and keep their pre-computed `tier → severity → effective_weight` order; do not re-sort.
- [x] Pre-disposition fix/comment authoring stated: the buddy authors a **Proposed fix** (snippet-when-cheap using its local-`main` read access, else prose — same cache-only-vs-local asymmetry note as Phase 2; sweep findings have no `evidence.snippet`) and a **Proposed PR comment** (terse, reviewer-voiced, references `file:line`) for **every revealed finding** — including ones the reviewer may subsequently dismiss. (Authoring moves earlier than Phase 2's post-disposition pass; Phase 2's collect/emit logic for kept findings is unchanged and reuses what was already authored.)
- [x] **Severity field semantics for pre-disposition** documented explicitly: `**Severity:**` = the pipeline's recommended/computed severity (from `processed-findings.json` tier / reuse-intrafile verdict→severity), clearly the *recommendation* — NOT the reviewer's disposition (which is captured by the Step-4 prompt that follows). Post-disposition (Phase 2) the same field carries the reviewer's chosen severity. State this distinction so the two surfaces don't read as contradictory.
- [x] **Disposition prompt (Step 4) left unchanged:** the four-value taxonomy (`Blocking / Important / Suggestion / Dismiss`, fixed order, every prompt) and the inline confidence-label rule are preserved verbatim. The standardized block is the *display preceding* the prompt; it must not leak into or alter the `AskUserQuestion` options.
- [x] **Pass-1 anti-anchoring preserved:** findings are still NOT shown in the Independent Read (Pass 1); the block reveal stays in Pass 2 only. The existing _AI-role framing_ notes (reviewer is sole arbiter; tool is a facilitation/triage aid) are preserved.
- [x] **Pre-filters preserved:** the already-commented and stale-Copilot-thread pre-filters (≈L141–163) still run *before* the block reveal and still surface their one-line informational notes (NOT full blocks). Only findings that pass both filters render as standardized blocks.
- [x] Finding ID Convention (≈L74–81) left unaltered: the block's `**Location:**` uses the canonical `<file>:<line>` / `<file>#<slug>` ID (equal to the `finding_ref`); the calibration join is unaffected (additive display change only).

**Minimum Verifiable Behavior:** Opening `review-pr-buddy.md` shows the "Reconcile — Pass 2" step revealing each pre-computed finding (post-pre-filter) in the Standardized Issue Block — grouped by source, pre-computed order preserved — with a recommended/tool-computed `**Severity:**`, the existing confidence label, `**What:**`, `**Proposed fix:**`, and `**Proposed PR comment:**`. The Step-4 disposition prompt's four-value taxonomy and confidence-label rule, the Pass-1 anti-anchoring, the two pre-filters, and the Finding ID Convention are all unchanged.

**Runtime Verification** *(checked by inspection / dry-run — NOT by an implementation agent):*
- [ ] <!-- verification-only --> "Reconcile — Pass 2" renders the Standardized Issue Block per finding (not the old one-line `- {title} [{file}:{line}] (weight: …)` bullets), grouped by source, order preserved.
- [ ] <!-- verification-only --> The pre-disposition `**Severity:**` is documented as the recommended/tool-computed value, explicitly distinct from the reviewer's disposition.
- [ ] <!-- verification-only --> The Step-4 disposition prompt still presents exactly `Blocking / Important / Suggestion / Dismiss` (fixed order) with the inline `CONFIRMED`/`UNVERIFIED`/`—` confidence label — byte-unchanged from pre-edit.
- [ ] <!-- verification-only --> Pass 1 (Independent Read) still shows NO tool findings; the AI-role framing notes are intact.
- [ ] <!-- verification-only --> The already-commented and stale-Copilot pre-filters still run before the reveal and still emit one-line notes (not blocks).
- [ ] <!-- verification-only --> "Finding ID Convention" (≈L74–81) is byte-identical to its pre-edit state.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; skill/command-prose defining interactive presentation format.

**Prerequisites:**
- Phase 1: the Standardized Issue Block format is defined in `synthesizer-v2.md` (Phase 3 references it by the same name, exactly as Phase 2 does). Complete.
- Phase 2: the buddy already consumes the block for the post-disposition artifact + digest; Phase 3 moves the per-finding fix/comment authoring earlier (to Pass 2) and reuses it at Phase 2. Complete.

**Files likely modified:**
- `user/plugins/local-tools/plugins/cognito-pr-review/commands/review-pr-buddy.md` — update "Reconcile — Pass 2" to reveal the Standardized Issue Block per finding (recommended severity + What + Proposed fix + Proposed PR comment); note that fix/comment are now authored at reveal time and reused by Phase 2; leave the Step-4 disposition prompt, Pass-1 anti-anchoring, the two pre-filters, and the Finding ID Convention unaltered.

**Testing Strategy:** Manual inspection of the edited "Reconcile — Pass 2" against the deliverables. Diff Step-4 (Disposition) and "Finding ID Convention" against pre-edit state to confirm they are byte-unchanged. Optional: dry-run a buddy walk on a small fixture; confirm Pass 2 prints standardized blocks (recommended severity) and the disposition prompt is still the four-value taxonomy.

**Integration Notes for Next Phase:** No further phases. After Phase 3, the standardized block is live on all three buddy surfaces (pre-disposition reveal, post-disposition `PR-{id}.md`, in-chat close digest); the autonomous path stays bound to `synthesizer-v2.md` (unchanged by this phase). Format changes continue to flow from `synthesizer-v2.md` (SSOT) into `review-pr-buddy.md` by reference.

**Context from prior phases:**
- Phase 1 removed the `### Important`/`### Minor` severity sub-bucketing; uniformity is via the block's inline `**Severity:**`. Pre-disposition this field is the *recommended* severity — author the reveal so it's clearly a recommendation, not a verdict.
- Phase 2 established the local-`main` snippet-grounding allowance and the cache-only-vs-local asymmetry note; Phase 3 reuses that exact framing for the pre-disposition fix authoring (do not re-derive a different rule).
- The Step-4 disposition prompt's taxonomy is a hard calibration invariant (Phase 4 calibration comparability) — it must not be perturbed by the display change.

#### Implementation Notes — Phase 3 (2026-06-30)

**Status:** Complete. **Review verdict:** PASS (implemented via dispatched subagent — markdown/command prose; orchestrator independently verified the `git diff` scope + all five HARD invariants before committing).

**Work completed:** Two edits to `review-pr-buddy.md`. (1) `#### 3. Reconcile — Pass 2` — replaced the terse grouped-by-source one-line descriptor reveal with the **Standardized Issue Block** (shape copied verbatim from `synthesizer-v2.md`'s `## Standardized Issue Block`); findings stay grouped by source under the four existing headings with the pre-computed `tier → severity → effective_weight` order preserved (explicit "do not re-sort"); added an explicit **pre-disposition `**Severity:**` semantics** paragraph (recommended/tool-computed from `tier` or the reuse/intrafile verdict→severity map; a recommendation, NOT the reviewer's disposition; the same field carries the chosen severity post-disposition); added reveal-time authoring of **Proposed fix + Proposed PR comment for every revealed finding** (incl. ones later dismissed), reusing Phase 2's local-`main` snippet-grounding carve-out + cache-only-vs-local asymmetry framing (sweep always prose, explicit read statement, terse/reviewer-voiced/`file:line`/never-auto-posted comment, Pass-1 `note` seeding). (2) Phase 2 "Collect Curated Content" (one line) — changed "Author …" to "**Reuse** the Proposed fix and Proposed PR comment authored at reveal time … do NOT re-author from scratch," with an escape-hatch fallback to author if a kept finding somehow lacks one.

**Invariants verified intact (orchestrator-confirmed via `git diff`):** (1) Step-4 disposition prompt — four-value taxonomy `Blocking / Important / Suggestion / Dismiss` + inline `CONFIRMED`/`UNVERIFIED`/`—` label byte-unchanged (no hunk in that range); (2) Pass-1 anti-anchoring + AI-role framing intact (no hunk in `#### 2`); (3) both pre-filters + the "Both filters run before the grouped finding display" sentence intact (no hunk in L141–163); (4) "Finding ID Convention" (L74–81) byte-identical (no hunk); (5) `synthesizer-v2.md` untouched (diff --stat = one file). `git diff --stat`: 1 file changed, 20 insertions(+), 3 deletions(-).

**Decisions:** The reuse/intrafile verdict→severity mapping for the recommended-severity explanation was sourced from the plugin `CLAUDE.md` (`refactor`/`reuse` → important, `extend`/`wrap`/`inconsistent` → nit/suggestion) and rendered in the buddy's four-value vocabulary. The Phase-2 forward-reference was kept to a single edited sentence + a one-clause escape-hatch fallback (minimal, per "one writer / minimal cross-section churn").

**Files modified:** `user/plugins/local-tools/plugins/cognito-pr-review/commands/review-pr-buddy.md`. Plugin version bumped `2.8.0 → 2.9.0` (`.claude-plugin/plugin.json`).

---

## Review Notes

**Authoring review verdict:** PASS (2026-06-30). PHASES.md ground-truth verified (91 lines, git status matched the drafting agent's block, no "already complete" claims). Content honors all four locked SPEC decisions (D1 all sources, D2 snippet-where-cheap-else-prose, D3 both surfaces, D4 buddy + synthesizer-v2); uses verified touchpoint paths; documents the sequential Phase 1→2 dependency, the cache-only vs. local-`main` snippet asymmetry, the do-not-re-sort ordering rule, and the calibration-ID preservation guard. No gate-owned checkbox rows; verification-only markers present on all Runtime Verification rows.

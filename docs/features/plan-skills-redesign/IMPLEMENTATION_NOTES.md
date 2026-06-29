# Plan-Skills Redesign — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist), per the D3 writer flip landed in Phase 3. Earlier phases' notes (1–2) remain embedded in PHASES.md because they predate the flip; from Phase 3 onward notes accumulate here.

## Phase 3 — Thin PHASES.md + sibling notes: writer + harness reader (D3 core)

#### Implementation Notes (Phase 3 — Batch 1: WU-1 + WU-2 + WU-3)
**Completed:** 2026-06-29
**Review verdict:** PASS

**OQ2 phase-boundary marker format (settled — explicit deliverable output):**
The phase-boundary marker for slicing PHASES.md is a **level-2-or-3 Markdown heading whose text begins with `Phase` followed by an identifier** — regex `^#{2,3}\s+Phase\s+<id>` (e.g. `## Phase 3 — Thin PHASES.md …`). This is the SAME canonical marker the harness `lazy_core.parse_phases()` already keys off (`_PHASE_HEADING_RE`). Slice readers reuse it rather than inventing a new delimiter; the completed-phases index is the set of these heading lines plus their `**Status:**` lines. **OQ3 resolution:** `IMPLEMENTATION_NOTES.md` is **one file with per-phase `## Phase N — <title>` sections** (the working default), not per-phase files.

**Work completed:**
- WU-1 (writer flip — `_components/phases-update.md`): the shared per-batch writer now appends the Implementation Notes block to a sibling `IMPLEMENTATION_NOTES.md` (resolved as `<dir-of-PHASES.md>/IMPLEMENTATION_NOTES.md`, created if absent, one file with per-phase `## Phase N — <title>` sections). PHASES.md now receives ONLY the deliverable checkbox ticks and stays a thin checklist. Added an explicit reader-tolerance note (sibling-then-embedded) so the flip strands no reader. This very notes block is the first dogfood of the flip.
- WU-2 (slice reads — `source-reread.md` + `execute-plan/SKILL.md`): added a discrete `### PHASES.md slice read` subsection to `source-reread.md` and a `### PHASES.md slice handling` subsection to `execute-plan/SKILL.md`. Both narrow the startup / per-batch / compaction-recovery PHASES.md read to (a) the current-phase slice (offset/limit anchored on the OQ2 marker) plus (b) a compact completed-phases index (heading + `**Status:**` lines), never the whole file. The slice-read edit is authored additively (a new subsection, not a rewrite of the existing "prior Implementation Notes in PHASES.md" item) so Phase 4's sibling-then-embedded notes-read edit merges into the same `source-reread.md` without clobbering — item 2 of the re-read list is intentionally left for Phase 4 to flip to sibling-then-embedded.
- WU-3 (harness reader — `lazy_core.py::phases_show_implementation()` + tests, TDD): extended the predicate with an optional `phases_path: Path | None = None` parameter (backward-compatible — text-only legacy callers unaffected). When `phases_path` is supplied it checks a sibling `IMPLEMENTATION_NOTES.md` FIRST (via new `_sibling_impl_notes_present()` helper + `_SIBLING_IMPL_NOTES_HEADING_RE` matching `^#{2,4}\s+Implementation Notes\b`), then falls back to the embedded `## Implementation Notes` heading in PHASES.md. The sole production caller (`lazy-state.py:2732`) now passes `phases_path=phases_file`. Wrote 4 new tests RED-first (sibling-only→True, embedded-with-path→True, neither→False, empty-scaffold-sibling→False) — all pass; the legacy embedded text-only case stays green.

**Integration notes (for Phase 5):**
- The sibling-then-embedded read order is now established in `phases_show_implementation()`. Phase 4 propagates the SAME idiom to the generic consumer skills (`add-phase`, `lazy`, `lazy-batch`, `realign-spec`, `implement-phase`, `implement-phase-batch`, `spec-phases-batch`, `/spec-phases` Step 1.5) AND to `source-reread.md` item 2 (the "prior Implementation Notes" read), which Phase 3 deliberately left embedded-only.
- `source-reread.md` now has TWO concerns: the Phase-3 slice-read subsection and (incoming Phase 4) the sibling-then-embedded notes read. Merge — do not clobber the slice-read subsection.
- The sibling-evidence signal requires an actual `Implementation Notes` heading block (`#{2,4}`) in the sibling — a bare title/preamble scaffold does NOT count as evidence (prevents a placeholder file from falsely suppressing research).

**Pitfalls & guidance:**
- `_SIBLING_IMPL_NOTES_HEADING_RE` matches 2–4 leading hashes (`#{2,4}`), broader than the embedded-PHASES `_IMPL_NOTES_HEADING_RE` (`#{2,3}`), because the per-batch notes block heading is authored at `####` (`#### Implementation Notes (Phase N)`) while the sibling section heading is `## Phase N — …`. The embedded regex was left unchanged to avoid disturbing the legacy in-PHASES match.
- `remaining_unchecked_are_verification_only()` and `verify_ledger()` were confirmed unaffected — neither parses Notes internals; the diff touches neither, and their tests stayed green.
- `/spec-phases` confirmed thin: it only READS upstream Implementation Notes (look-back, Step 1.5) and never authors/embeds a notes block into the PHASES.md it generates — no fix needed.
- Gate baseline: `pytest test_lazy_core.py` = 824 passed / 5 failed, where all 5 failures reproduce identically on the stashed clean baseline (CRLF/permission snapshot drift + the absent-sibling-`algobooth` real-drivers audit) — zero regressions from this work. `setup.ps1 check` = 89 OK / 5 broken (pre-existing `normalize-crlf.ps1` symlinks). Run gates with `pwsh` (PowerShell 7), not `powershell.exe` 5.1.

**Files modified:**
- `user/skills/_components/phases-update.md` — writer flipped: notes → sibling `IMPLEMENTATION_NOTES.md`; PHASES.md stays thin checklist
- `user/skills/_components/source-reread.md` — added `### PHASES.md slice read` (current-phase slice + completed-phases index; OQ2 marker)
- `user/skills/execute-plan/SKILL.md` — added `### PHASES.md slice handling` (startup/per-batch/recovery slice read)
- `user/scripts/lazy_core.py` — `phases_show_implementation()` gains optional `phases_path`; new `_sibling_impl_notes_present()` + `_SIBLING_IMPL_NOTES_HEADING_RE`; sibling-then-embedded order
- `user/scripts/lazy-state.py` — Step-5 research-gate caller passes `phases_path=phases_file`
- `user/scripts/test_lazy_core.py` — 4 new sibling-then-embedded tests + `_TESTS` registry entries

---

## Phase 4 — Propagate the D3 split across generic consumers (D3 blast radius)

#### Implementation Notes (Phase 4 — Batch 1: WU-1 + Batch 2: WU-2 + WU-3)
**Completed:** 2026-06-29
**Review verdict:** PASS

**Bounding sweep result (VERIFIED):**
Swept all notes-mining phrasings across `user/skills/` with: `grep -rni "Implementation Notes|notes block|mine.*notes|prior.*notes|IMPLEMENTATION_NOTES"`. Found the planned 8-consumer set (`add-phase`, `lazy`, `lazy-batch`, `realign-spec`, `implement-phase`, `implement-phase-batch`, `spec-phases-batch`, `spec-phases`) PLUS 7 additional consumers not in the original planned set: `lazy-batch-retro`, `retro`, `fix`, `fix-mobile`, `write-plan`, `_components/execution-contract.md`, `_components/post-compact-reread.md`. All 15 were updated. `lazy-batch/SKILL.md` had no notes-reading site (only a spin-off authoring reference in `_components/lazy-batch-prompts/cycle-base-prompt.md` line 127 — authoring, not reading — confirmed correct to skip). The sweep is verified complete.

**WU-1 (shared snippet + source-reread.md merge):**
- Created `user/skills/_components/implementation-notes-read-order.md` (16 lines) — canonical single-sourced sibling-then-embedded rule: sibling-first with evidence threshold (`#{2,4}` heading in sibling), embedded fallback, explanation of why sibling-first (D3 writer flip), practical read steps. Makes `!cat`-includable for consumer reference.
- Updated `user/skills/_components/source-reread.md` — item 2 updated to reference sibling-then-embedded; new `### Prior Implementation Notes read (sibling-then-embedded)` subsection added. Phase 3's `### PHASES.md slice read` subsection (lines 9-16) is intact and unchanged — confirmed merge, not clobber.

**WU-2 (consumer group A):**
- `add-phase/SKILL.md` — Step 2 item 1 + Step 3b mine-notes section updated.
- `lazy/SKILL.md` — Research-gate predicate description updated to reflect `phases_show_implementation()` sibling-then-embedded behavior (matching Phase 3's `lazy_core.py` change).
- `lazy-batch/SKILL.md` — No notes-reading site; no edit needed. `cycle-base-prompt.md` reference (line 127) is an authoring spin-off reference, not a read. Confirmed correct.

**WU-3 (consumer group B + extra consumers):**
- `realign-spec/SKILL.md` — upstream PHASES.md read (Step 2 item 3) updated.
- `implement-phase/SKILL.md` — two sites updated (Step 1b + Step 3 Step 4a).
- `implement-phase-batch/SKILL.md` — two sites updated (Step 1b + Phase Selection Loop Step 3).
- `spec-phases/SKILL.md` — Step 1.5 upstream PHASES.md read updated.
- `spec-phases-batch/SKILL.md` — subagent prompt template note added for Complete upstream reads.
- `write-plan/SKILL.md` — Step 1b read updated (extra consumer, added per bounding sweep).
- `fix/SKILL.md` — Step 3b read updated (extra consumer).
- `fix-mobile/SKILL.md` — Step 3b read updated (extra consumer).
- `_components/execution-contract.md` — Phase Selection Loop Step 3 updated (extra consumer).
- `lazy-batch-retro/SKILL.md` — Step 2d artifact read + R-EP-5 rule updated (extra consumer).
- `retro/SKILL.md` — Subagent A prompt + Subagent G compliance check updated (extra consumer).
- `_components/post-compact-reread.md` — item 3 updated (extra consumer).

**Consistency check:** every updated site uses the same sibling-then-embedded idiom with sibling-first, evidence-threshold (content headings required), embedded fallback, and a cross-reference to `implementation-notes-read-order.md`. No `-cognito` variants created. All edits are GENERIC.

**Quality gates:**
- `project-skills.py`: 84 skills / 92 components / 0 errors — PASS. New snippet counted as component 92.
- `lint-skills.py`: no broken !cat patterns, planner resolution clean — PASS.
- `setup.ps1 check`: 89 OK / 5 broken (same pre-existing `normalize-crlf.ps1` symlinks as baseline) — no regressions.
- `pytest test_project_skills.py`: 36/36 passed — PASS.

**Pitfalls & guidance:**
- `lazy-batch/SKILL.md` has no notes-reading site — the `cycle-base-prompt.md` line 127 reference is about AUTHORING a reverse spin-off reference INTO notes (D7 policy), not reading notes. Correct to leave `lazy-batch/SKILL.md` unedited.
- `execution-contract.md` line 100 says "PHASES.md (current phase + prior Implementation Notes)" — this is a brief summary of what `source-reread.md` covers and delegates to it; the component is now updated so the brief summary is accurate-enough. Left as-is intentionally.
- Integration notes for Phase 5: no structural changes needed for Phase 5 (executor parallelism + background builds). The sibling-then-embedded idiom is fully propagated.

**Files modified:**
- `user/skills/_components/implementation-notes-read-order.md` — CREATED (new shared canonical snippet)
- `user/skills/_components/source-reread.md` — item 2 updated + `### Prior Implementation Notes read` subsection added
- `user/skills/add-phase/SKILL.md`
- `user/skills/lazy/SKILL.md`
- `user/skills/realign-spec/SKILL.md`
- `user/skills/implement-phase/SKILL.md`
- `user/skills/implement-phase-batch/SKILL.md`
- `user/skills/spec-phases/SKILL.md`
- `user/skills/spec-phases-batch/SKILL.md`
- `user/skills/write-plan/SKILL.md`
- `user/skills/fix/SKILL.md`
- `user/skills/fix-mobile/SKILL.md`
- `user/skills/_components/execution-contract.md`
- `user/skills/lazy-batch-retro/SKILL.md`
- `user/skills/retro/SKILL.md`
- `user/skills/_components/post-compact-reread.md`
- `docs/features/plan-skills-redesign/PHASES.md` — Phase 4 deliverables checked off, Status → Complete
- `docs/features/plan-skills-redesign/IMPLEMENTATION_NOTES.md` — Phase 4 notes appended

## Phase 5 — Executor parallelism + background builds (D4)

#### Implementation Notes (Phase 5)
**Completed:** 2026-06-29
**Review verdict:** PASS (self-review; this harness has no nested-subagent dispatch, so the orchestrator is the writer and ground-truth is the orchestrator's own VERIFY-anchor grep re-runs, not a falsifiable subagent report).
**Work completed:**
- Same-message file-disjoint batching (D4): added the `#### Same-message file-disjoint batching (MANDATORY)` subsection to the contract's `### Parallelism & background builds` section (the Phase-2-anticipated placeholder — extended, not restructured). Rule: provably file-disjoint WUs (plan batch table marks parallel AND no shared `Files to create/modify`) dispatch as multiple `Agent` blocks in ONE assistant message; seam classification gates what is disjoint; disjointness is a plan-author claim the executor exploits, never one it manufactures.
- Background builds (D4): `#### Background builds (MANDATORY)` subsection — long/Tier-2/typegen builds run `run_in_background: true`, next independent agent dispatched while the build runs, poll `$HOME/.claude/state/build-queue/results/<seq>.json` `exit_code`. Builds stay a serial spine; only agent think/edit/test-author time overlaps; target ~1.5–2× wall-clock per phase, not unbounded fan-out.
- Constraint guard (D4): `#### Constraint guard (MANDATORY)` — a backgrounded build's output is never consumed by a dependent agent before completion, enforced by the existing disjoint-file + seam-classification rules (no new queue machinery); a dependent (Sequenced) agent blocks on the build `exit_code` first.
- `subagent-launch.md` (launch-mechanics twin): added a `### Same-Message Disjoint Batching (MANDATORY)` block before the existing Build Concurrency rule, a sentence tying Build Concurrency to the file-overlap rule, and a `### Background Builds` block. All three point to the contract section as the single-source policy home — launch component carries mechanics, contract carries policy (no duplication, preserves D2 single-sourcing).
- WU-2 (`write-plan-cognito`): made disjointness machine-evident without changing lane semantics. Extended the `Parallel` seam-classification bullet, added a "Make disjointness machine-evident" paragraph (each Parallel-batch lane lists exact files; no two share a file; neither owns `server-types/**`), and reshaped the batch-structure template — `Parallel?` is now documented as the executor's same-message-dispatch signal and a new `Files (disjoint?)` column makes non-overlap machine-checkable.

**OQ4 — long-build signature set (RESOLVED against the queue skills `/msbuild` `/nxbuild` `/mstest` `/nxtest`):**
- **Background (Tier-2 / typegen / long):** full-solution `/msbuild` (no `-Project` — also the authoritative server-typegen trigger), `/msbuild -Test`, the typegen step's `Cognito.Services` build, `/nxbuild -All`, and any fan-out Nx library build (model.js → vuemodel → element-ui chain). Source of truth: msbuild/nxbuild SKILL.md step 4 ("if the build is expected to exceed 10 minutes, run with `run_in_background: true`").
- **Do NOT background (fast, in-loop):** single-project `/msbuild -Project "<csproj>"`, targeted single-project `/nxbuild -Project`, and `--no-build` filtered tests (`/mstest -Filter …`, `/nxtest … -NoCoverage`).

**Integration notes:**
- Policy home is the contract; `subagent-launch.md` and `write-plan-cognito` reference it rather than re-stating it — editing one rule (the contract section) changes behavior everywhere (D2 invariant upheld).
- The `Files (disjoint?)` batch-table column is additive — it does not alter the Cognito lane decomposition, only surfaces the disjointness proof the file-overlap rule already guaranteed so the WU-1 executor check can fire.

**Pitfalls & guidance:**
- The two contract placeholder sections from Phase 2 ("Parallelism & background builds" and "Per-WU verification gate") were extended in place — the blockquoted "Anticipated home …" preamble was replaced by the real rules, keeping the section heading and the trailing baseline bullets. Do NOT restructure the contract around these.

**Quality gates:** (recorded in the Phase 5 batch commit; see gate run below)

**Files modified:**
- `user/skills/_components/execution-contract.md` — D4 rules added to `### Parallelism & background builds`
- `user/skills/_components/subagent-launch.md` — same-message batching + background-build launch mechanics
- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` — machine-evident disjointness + batch-table alignment
- `docs/features/plan-skills-redesign/PHASES.md` — Phase 5 deliverables checked off, Status → Complete
- `docs/features/plan-skills-redesign/plans/all-phases-plan-skills-redesign-part-5.md` — WU-1, WU-2 ticked
- `docs/features/plan-skills-redesign/IMPLEMENTATION_NOTES.md` — Phase 5 notes (this block)

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

**Integration notes (for Phase 4):**
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

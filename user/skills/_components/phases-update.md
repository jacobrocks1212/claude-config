## Update PHASES.md (BLOCKING GATE — DO NOT SKIP OR DEFER)

**This is a blocking gate.** You CANNOT proceed to the next step until PHASES.md has been updated and verified. Skipping this step means the next session (or post-compaction recovery) will not know what was completed.

> **Machine source of truth note (2026-06-15 — d8-effect-chains review).** The completion gate (`--verify-ledger --plan <plan_part>`) reads `deliverables_done` from the **plan part's own `- [ ] WU-N` checkboxes**, NOT from the PHASES.md per-deliverable checkboxes below. In PHASES.md, the durable, must-be-accurate human record is the phase **Status** line + the **Implementation Notes** block (steps 2–3); the per-deliverable `- [ ]`→`- [x]` ticks (step 1) are **best-effort human-readable documentation** — keep them as accurate as you reasonably can, but they no longer gate the pipeline and need not be kept in lockstep with the machine gate. Tick the plan-part `- [ ] WU-N` rows (see execute-plan Per-Step Protocol item 5) as the machine record.

For each completed work unit, two distinct destinations:

- **PHASES.md** receives ONLY the deliverable checkbox ticks (step 1) — it stays a **thin checklist** (phase headings + `- [ ]`/`- [x]` items + anchors). Do NOT append the Implementation Notes block here.
- **A sibling `IMPLEMENTATION_NOTES.md`** (located next to the PHASES.md being updated) receives the per-batch Implementation Notes block (step 2). This keeps PHASES.md from growing monotonically so it is cheap to re-read at startup / per-batch / on compaction recovery.

1. **In PHASES.md** — check off completed deliverables (best-effort human documentation): `- [ ]` → `- [x]`

   **Runtime-spike evidence rule (HARD):** a deliverable or Validated-Assumptions ledger row that claims `runtime` / `spike` confirmation may be ticked ONLY with a cited **runtime artifact** — an MCP tool result, a session-log line, or a test that drives the REAL component (the actual ring/transport/process, not a mock). A static code trace does NOT satisfy a runtime row, however thorough: d8-live-looping's WU-9.0 "runtime spike" was closed on a static trace that concluded "no broken seam" and was wrong twice, costing two further full validation rounds. If a live probe is impossible this cycle (no runtime available), the row STAYS UNTICKED with an explicit `NEEDS_RUNTIME:` note naming what must be observed — never downgrade the confirmation method to close the box.

2. **In the sibling `IMPLEMENTATION_NOTES.md`** — append the Implementation Notes block.

   **Sibling-path resolution:** the file lives in the SAME directory as the PHASES.md you just ticked — i.e. `<dir-of-PHASES.md>/IMPLEMENTATION_NOTES.md` (e.g. for `docs/features/<slug>/PHASES.md` → `docs/features/<slug>/IMPLEMENTATION_NOTES.md`). **Create the file if it does not exist** (first batch of the feature). Use **one file with per-phase sections** (resolved working default): the notes for every phase of a feature accumulate in this single sibling under per-phase section headings.

   File shape — a top-level title plus one `## Phase N — <title>` section per phase, each holding that phase's appended batch blocks:

   ```
   # <Feature> — Implementation Notes

   > Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

   ## Phase N — <title>

   #### Implementation Notes (Phase N)
   **Completed:** YYYY-MM-DD
   **Work completed:**
   - [deliverable]: [what was actually built]
   **Integration notes:**
   - [what the next implementer needs to know]
   **Pitfalls & guidance:**
   - [anything surprising or non-obvious discovered]
   **Files modified:**
   - `path/to/file` — [what changed]
   ```

   When the current phase's `## Phase N — <title>` section already exists (a prior batch in the same phase created it), append this batch's `#### Implementation Notes` block UNDER that existing section. When it does not exist, create the section heading first, then the block. Keep the block content identical to the legacy embedded form (date, work completed, integration notes, pitfalls, files modified) — only the destination changed.

   **Notes must reflect verified disk state, not sub-agent narrative.** Before writing the "Work completed" / "Files modified" sections, confirm them against reality: re-read the actual changed files and the real test-run output — do not transcribe a sub-agent's prose description of what it built. If a previously written notes block is contradicted by the current implementation (e.g. it describes different method names or structure than the code now on disk), correct or strike the stale block rather than appending a contradictory one.

3. **Verify the write:** Re-read both files from disk after editing. Confirm:
   - [ ] In PHASES.md: all completed deliverables show `- [x]` (not still `- [ ]`)
   - [ ] In the sibling `IMPLEMENTATION_NOTES.md`: the Implementation Notes block is present with today's date, under the current phase's `## Phase N — <title>` section
   - [ ] Files modified list is non-empty

   If any check fails, the edit didn't land — fix it before proceeding.

> **Reader tolerance (no flag-day).** Every reader of Implementation Notes (the harness `lazy_core.py::phases_show_implementation()` gate and the generic consumer skills) checks the sibling `IMPLEMENTATION_NOTES.md` **first**, then falls back to the embedded `## Implementation Notes` heading in PHASES.md for in-flight/legacy features authored before this writer flip. Writing notes to the sibling therefore does not strand any reader.

If no PHASES.md applies, explicitly state "No PHASES.md — skipped" and move on.

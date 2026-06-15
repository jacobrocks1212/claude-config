## Update PHASES.md (BLOCKING GATE — DO NOT SKIP OR DEFER)

**This is a blocking gate.** You CANNOT proceed to the next step until PHASES.md has been updated and verified. Skipping this step means the next session (or post-compaction recovery) will not know what was completed.

> **Machine source of truth note (2026-06-15 — d8-effect-chains review).** The completion gate (`--verify-ledger --plan <plan_part>`) reads `deliverables_done` from the **plan part's own `- [ ] WU-N` checkboxes**, NOT from the PHASES.md per-deliverable checkboxes below. In PHASES.md, the durable, must-be-accurate human record is the phase **Status** line + the **Implementation Notes** block (steps 2–3); the per-deliverable `- [ ]`→`- [x]` ticks (step 1) are **best-effort human-readable documentation** — keep them as accurate as you reasonably can, but they no longer gate the pipeline and need not be kept in lockstep with the machine gate. Tick the plan-part `- [ ] WU-N` rows (see execute-plan Per-Step Protocol item 5) as the machine record.

For each completed work unit, update PHASES.md:

1. Check off completed deliverables (best-effort human documentation): `- [ ]` → `- [x]`

   **Runtime-spike evidence rule (HARD):** a deliverable or Validated-Assumptions ledger row that claims `runtime` / `spike` confirmation may be ticked ONLY with a cited **runtime artifact** — an MCP tool result, a session-log line, or a test that drives the REAL component (the actual ring/transport/process, not a mock). A static code trace does NOT satisfy a runtime row, however thorough: d8-live-looping's WU-9.0 "runtime spike" was closed on a static trace that concluded "no broken seam" and was wrong twice, costing two further full validation rounds. If a live probe is impossible this cycle (no runtime available), the row STAYS UNTICKED with an explicit `NEEDS_RUNTIME:` note naming what must be observed — never downgrade the confirmation method to close the box.
2. Add/append an Implementation Notes block:

   ```
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

   **Notes must reflect verified disk state, not sub-agent narrative.** Before writing the "Work completed" / "Files modified" sections, confirm them against reality: re-read the actual changed files and the real test-run output — do not transcribe a sub-agent's prose description of what it built. If a previously written notes block is contradicted by the current implementation (e.g. it describes different method names or structure than the code now on disk), correct or strike the stale block rather than appending a contradictory one.

3. **Verify the write:** Re-read PHASES.md from disk after editing. Confirm:
   - [ ] All completed deliverables show `- [x]` (not still `- [ ]`)
   - [ ] Implementation Notes block is present with today's date
   - [ ] Files modified list is non-empty

   If any check fails, the edit didn't land — fix it before proceeding.

If no PHASES.md applies, explicitly state "No PHASES.md — skipped" and move on.

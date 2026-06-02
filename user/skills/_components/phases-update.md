## Update PHASES.md (BLOCKING GATE — DO NOT SKIP OR DEFER)

**This is a blocking gate.** You CANNOT proceed to the next step until PHASES.md has been updated and verified. Skipping this step means the next session (or post-compaction recovery) will not know what was completed.

For each completed work unit, update PHASES.md:

1. Check off completed deliverables: `- [ ]` → `- [x]`
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

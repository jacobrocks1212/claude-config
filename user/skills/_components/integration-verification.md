## Integration Verification (MANDATORY — DO NOT SKIP)

### Verify Cross-Agent Integration

- Read all files modified across all subagents
- Verify imports resolve, no duplicate code, no conflicting exports
- Run quality gates across all touched areas (not just per-batch — the full relevant suite)

### Verify Spec Alignment

- Re-read the relevant SPEC.md
- Verify every deliverable was implemented correctly per spec
- Fix any deviations

### Verify Full-Stack Coverage for User-Facing APIs (MANDATORY — DO NOT SKIP)

For every new user-facing API added whose output is externally observable (rendered output, I/O, network, file writes):

1. Confirm at least one integration test exercises the full call stack — entry point → business logic → I/O → observable output — and asserts the output is correct.
2. Unit tests at layer boundaries are necessary but **not sufficient** — bugs live at the seams between layers.
3. If the project already has full-stack test infrastructure (e.g. integration test suites, e2e specs, pipeline tests), mirror its existing pattern — do **not** invent a new harness.
4. If no such infrastructure exists, add one test that establishes it.
5. If no user-facing APIs with observable output were added, explicitly state "No full-stack integration tests required" and move on.

Do not mark the phase complete until this check passes.

### Verify Data Flow for Wiring Phases (MANDATORY — DO NOT SKIP)

If this phase connects modules that were previously isolated (e.g., wiring an EventBus to a log sink, connecting a capture layer to a writer, routing events between subsystems), verify the data actually flows end-to-end:

1. **Identify the pipeline:** What is the entry point (event emitter, API call, user action) and what is the observable output (file write, network response, UI update)?
2. **Trace the path:** Read every module in the chain and confirm imports, function calls, and data transforms are correctly wired — not just that each module compiles in isolation.
3. **Require a smoke test:** At minimum, one test must exercise the full path: trigger at the entry point → assert at the observable output. Unit tests on individual modules are necessary but NOT sufficient — integration bugs live at the seams.
4. **If no wiring occurred** in this phase, explicitly state "No data flow verification required — this phase does not connect previously isolated modules" and move on.

**Why this exists:** Isolated module tests pass while end-to-end integration remains broken — wiring bugs live at the seams between layers. This step prevents "all tests pass but the feature doesn't work" scenarios.

### Fix Integration Issues

If issues found: fix them and update PHASES.md (if applicable) with notes about what was fixed.

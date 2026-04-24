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

### Fix Integration Issues

If issues found: fix them and update PHASES.md (if applicable) with notes about what was fixed.

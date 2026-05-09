## TDD Decision Gate

Determines whether a work unit goes through the test-first pipeline (separate test agent → implementation agent) or skips directly to implementation.

### TDD Applies When

- Feature work with **testable behavior** (functions, APIs, business logic, data transformations)
- Bug fixes with a **reproducible root cause** that can be pinned by a regression test
- Any deliverable whose acceptance criteria can be expressed as automated assertions

### TDD Does NOT Apply When

- Pure configuration changes (CI, linting rules, build config)
- Documentation-only changes
- Scaffolding with no testable logic (empty files, directory structure, boilerplate)
- Static asset changes (images, styles with no behavioral impact)

### Pipeline Routing

- **TDD work unit:** Test agent writes failing tests (red) → Implementation agent makes them pass (green)
- **Non-TDD work unit:** Implementation agent executes directly (no test agent phase)

The orchestrating agent assigns each work unit a **TDD flag** during partitioning. This flag determines whether the work unit enters Phase A (test agents) or skips directly to Phase B (implementation agents).

## TDD Protocol (MANDATORY — DO NOT SKIP)

Every subagent follows TDD — a failing test MUST be written BEFORE implementation code.

### Sequence

1. **Write the failing test** — assert the behavior the implementation must satisfy (or, for a fix, pin the bug's root cause)
2. **Verify it fails (red)** — run the test and confirm it fails for the expected reason
3. **Implement the code** — write the minimum code to make the test pass
4. **Verify it passes (green)** — run the test and confirm it now passes

### For Bug Fixes

- The regression test must fail **for the documented root cause**, not for an unrelated reason
- Confirm the test would have failed before the fix was applied
- A symptom-only patch is not acceptable — the test must pin the root cause

### For Feature Implementation

- Write the failing test against the SPEC.md requirements before writing any implementation
- TDD instructions to subagents: "write failing test, verify red, implement, verify green"
- Unit tests at layer boundaries are necessary but **not sufficient** — integration tests are required for user-facing APIs with observable output

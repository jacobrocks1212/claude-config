#### Runtime Assumption Validation Gate (generic)

Enumerate the assumptions your phase plan depends on. Classify each:

- **Code-provable** — fully determinable from source (types, pure logic, constants, a value you can read directly). No runtime check needed.
- **Runtime-coupled** — depends on actual running behavior: the runtime shape/contents of data crossing a boundary, whether an existing code path actually executes, the live output of a separate process or thread, timing/ordering, or a rendered/observable result. Reading source can mislead here.

For each **runtime-coupled, load-bearing** assumption:

1. If the system can be exercised cheaply now (run it, log at a safe boundary, inspect real output), **validate it** and record the OBSERVED ground truth (with evidence) in the plan — a `## Validated Assumptions` note at the top of PHASES.md and in the affected phase's Integration Notes. A validated assumption cites evidence, not a code reference.
2. If validating now is premature (the behavior must be built first), make the validation an **explicit early deliverable** — a Phase 0 / first-phase runtime spike ("instrument and confirm X at the live boundary before building on it"), as a `- [ ]` checkbox. Never let a load-bearing runtime assumption ride unverified into a later phase.

**Skip the gate** only when every load-bearing assumption is code-provable (pure logic, types, UI layout, behavior-preserving refactor with snapshot coverage). Record the skip reason in the plan.

**Anti-pattern:** substituting source-reading for runtime observation when the assumption is about runtime behavior crossing a boundary. Unit-green and a plausible code read are NOT runtime confirmation. When in doubt for cross-boundary or runtime-observable behavior, observe the running system before planning on it.

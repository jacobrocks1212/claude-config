#### Runtime Assumption Validation Gate (generic)

Enumerate the assumptions your phase plan depends on. Classify each:

- **Code-provable** — fully determinable from source (types, pure logic, constants, a value you can read directly). No runtime check needed.
- **Runtime-coupled** — depends on actual running behavior: the runtime shape/contents of data crossing a boundary, whether an existing code path actually executes, the live output of a separate process or thread, timing/ordering, or a rendered/observable result. Reading source can mislead here.

For each **runtime-coupled, load-bearing** assumption:

1. If the system can be exercised cheaply now (run it, log at a safe boundary, inspect real output), **validate it** and record the OBSERVED ground truth (with evidence) in the plan — a `## Validated Assumptions` note at the top of PHASES.md and in the affected phase's Integration Notes. A validated assumption cites evidence, not a code reference.
2. If validating now is premature (the behavior must be built first), make the validation an **explicit early deliverable** — a Phase 0 / first-phase runtime spike ("instrument and confirm X at the live boundary before building on it"), as a `- [ ]` checkbox. Never let a load-bearing runtime assumption ride unverified into a later phase.

**SPEC-example capability audit (MANDATORY before drafting phases).** The SPEC's code examples are a dependency manifest: enumerate every API surface, source type, method, and language construct they consume, and confirm the target system actually supports each one TODAY. For every construct, run a **negative-evidence grep** — search the implementation for explicit rejection paths near the construct's name/type (`unimplemented!`, `todo!`, `return Err`, "not supported", "unsupported") — and record one ledger row per construct (`how-confirmed: grep`, citing the file:line or the absence of hits). A SPEC example that consumes an explicitly-rejected capability is a **planning-time halt** (correct the SPEC or raise NEEDS_INPUT) — never a late validation discovery. (Motivating incident: d8-live-looping's SPEC documented `input(n)` as the canonical record source while the engine carried a literal `return Err("Live input from sidecar IPC is not a supported track source")` — greppable since the rejection landed, discovered only at end-of-feature validation round 2.)

**Skip the gate** only when every load-bearing assumption is code-provable (pure logic, types, UI layout, behavior-preserving refactor with snapshot coverage). Record the skip reason in the plan.

**Anti-pattern:** substituting source-reading for runtime observation when the assumption is about runtime behavior crossing a boundary. Unit-green and a plausible code read are NOT runtime confirmation. When in doubt for cross-boundary or runtime-observable behavior, observe the running system before planning on it. **A spike deliverable executed as a static trace is a violation of this gate**, not a fulfillment of it: a "runtime spike" row may only be satisfied by observing the running system (or a test driving the REAL component — the actual ring/transport, not a mock), and the evidence it records must be a runtime artifact. (d8-live-looping's WU-9.0 "runtime spike" was executed as a static code trace that concluded "no broken seam" — and was wrong twice, costing two further full validation rounds.)

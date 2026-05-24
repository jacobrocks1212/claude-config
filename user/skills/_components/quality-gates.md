### Run Quality Gates (MANDATORY — DO NOT SKIP)

Run the project's quality gates for this batch's changes.

#### Determining which gates to run

!`cat .claude/skill-config/quality-gates.md 2>/dev/null || echo "No project-specific quality gates configured. Check the project CLAUDE.md for build/test commands, or ask the user what verification commands to run."`

#### Full-suite escalation rule

If this batch introduced any of the following, run the **full** project QG (all languages, all test suites) — not just the gate for the changed language:
- A new module that wraps/proxies an existing import (import indirection)
- A struct/interface field addition on a widely-constructed type
- A vitest/jest resolve alias change
- A module rename or re-export path change

This catches delayed blast-zone failures (e.g., 86 tests breaking because test mocks target the old import path) within the batch that caused them, not 15 commits later.

#### Batch frequency (right-sizing within a multi-batch plan part)

Running the full workspace gate after every intermediate batch re-runs the entire suite redundantly — the file-overlap batching already makes batches within a part sequential, so the same suite runs N times for an N-batch part. Right-size it:

- **Intermediate batches** (any batch that is NOT the last in the plan part) MAY run the **targeted/affected gate** — the changed crate's or package's tests (e.g. `cargo test -p <crate>`, `vitest <path>`) — instead of the full workspace gate. This gives fast feedback while iterating.
- **The full workspace gate is MANDATORY (100% pass) at BOTH of these points — no exceptions:**
  1. **At plan-part / phase completion** — before the final commit that authorizes flipping the plan-part status to `Complete` (or marking the phase done). This is the gate that catches any cross-crate/cross-module breakage an intermediate targeted run missed.
  2. **Immediately on any batch that trips a full-suite-escalation trigger** above (import indirection, struct/interface field addition, vitest/jest alias change, module rename/re-export). That batch runs the full workspace gate before it commits, regardless of its position in the part.
- A **single-batch part** is the last batch by definition → the full workspace gate is required for it.

This preserves the safety net (the full suite still runs before any part is declared done, and escalation triggers still force it immediately) while removing the redundant intermediate full-suite reruns.

**100% QG pass required.** Do not check whether failures are preexisting — all failures must be fixed.
If any gate fails, dispatch Sonnet subagent(s) to fix the failures (or, where the contract has no separate subagent — e.g. the cloud inline path — fix them in-session). Re-run the failing gate(s) after fixes.
Repeat until all gates pass. Do NOT proceed to the next batch with failing QGs, and do NOT mark a plan part Complete while the part-end full workspace gate is failing.

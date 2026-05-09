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

**100% QG pass required.** Do not check whether failures are preexisting — all failures must be fixed.
If any gate fails, dispatch Sonnet subagent(s) to fix the failures. Re-run the failing gate(s) after fixes.
Repeat until all gates pass. Do NOT proceed to the next batch with failing QGs.

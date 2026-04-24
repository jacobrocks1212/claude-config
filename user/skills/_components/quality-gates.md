### Run Quality Gates (MANDATORY — DO NOT SKIP)

Run the project's quality gates for this batch's changes.

#### Determining which gates to run

!`cat .claude/skill-config/quality-gates.md 2>/dev/null || echo "No project-specific quality gates configured. Check the project CLAUDE.md for build/test commands, or ask the user what verification commands to run."`

**100% QG pass required.** Do not check whether failures are preexisting — all failures must be fixed.
If any gate fails, dispatch Sonnet subagent(s) to fix the failures. Re-run the failing gate(s) after fixes.
Repeat until all gates pass. Do NOT proceed to the next batch with failing QGs.

# {PROJECT_NAME} - Implementation Plan

## Current Status

- **Active Phase:** Phase 1 - Foundation
- **Last Updated:** {DATE}
- **Blockers:** None

---

## Phase 1: Foundation

Project setup, core infrastructure, and base types.

- [ ] Initialize project with {TECH_STACK}
- [ ] Configure {TEST_FRAMEWORK} for testing
- [ ] Set up linting and formatting
- [ ] Define core data models/types
- [ ] Set up database schema (if applicable)
- [ ] Create project structure (folders, configs)
- [ ] Verify build and test pipeline works

## Phase 2: Core Features

Primary functionality from PRD user stories.

**TDD + Review:** Each feature follows RED → GREEN → REVIEW → REFACTOR:
1. Write failing test (RED)
2. Implement to pass (GREEN)
3. Code review (spawn agent)
4. Address findings (auto-fix minor, confirm significant)
5. Refactor if needed

- [ ] Feature 1: [From PRD Epic 1]
  - [ ] Write test: [describe expected behavior]
  - [ ] Implement: [make test pass]
  - [ ] Review: spawn /code-review agent, address findings
- [ ] Feature 2: [From PRD Epic 1]
  - [ ] Write test: [describe expected behavior]
  - [ ] Implement: [make test pass]
  - [ ] Review: spawn /code-review agent, address findings
- [ ] Feature 3: [From PRD]
  - [ ] Write test: [describe expected behavior]
  - [ ] Implement: [make test pass]
  - [ ] Review: spawn /code-review agent, address findings

## Phase 3: Integration & Polish

Edge cases, integrations, error handling.

- [ ] Error handling for all user-facing operations
- [ ] Input validation at all boundaries
- [ ] Logging and observability
- [ ] Performance optimization
- [ ] Security hardening

## Phase 4: Testing & Documentation

Test coverage and docs before release.

- [ ] Unit tests to {COVERAGE_TARGET}% coverage
- [ ] Integration tests for critical paths
- [ ] E2E tests for key user flows
- [ ] API documentation (if applicable)
- [ ] README with setup instructions
- [ ] Deployment documentation

---

## Session Log

<!-- Claude updates this after each work session -->

### {DATE} - Session 1
- **Completed:**
  - [Task completed]
- **In Progress:**
  - [Task started but not finished]
- **Blocked:**
  - [Any blockers encountered]
- **Next Session:**
  - [Priority for next session]

---

## Quick Reference

### Commands
```bash
# MAIN: Autonomous implementation (spawns subagent)
/vibe-work              # Next task
/vibe-work all          # Complete current phase

# Manual commands (if needed)
{TEST_COMMAND}          # Run tests
{LINT_COMMAND}          # Run linting
{BUILD_COMMAND}         # Build
/commit                 # Commit and push (clean, no AI attribution)
/code-review            # Manual code review
```

### Key Files
- `specs/PRD.md` - User stories and requirements
- `specs/TECH_SPEC.md` - Architecture and schemas
- `CLAUDE.md` - Project context for Claude

---

**Legend:**
- [ ] Not started
- [x] Completed
- [~] In progress (update to [x] when done)

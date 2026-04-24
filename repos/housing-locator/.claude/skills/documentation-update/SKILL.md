---
name: documentation-update
description: USE WHEN planning a phase of work or finishing execution of a phase. USE WHEN updating documentation after completing features, fixing bugs, or making architectural changes. Ensures all relevant docs stay in sync.
triggers:
  - "plan phase"
  - "planning phase"
  - "complete phase"
  - "finish phase"
  - "phase complete"
  - "update docs"
  - "documentation"
  - "update CLAUDE.md"
  - "update roadmap"
  - "update changelog"
  - "/complete-phase"
  - "/execute-phase"
---

# Documentation Update Guide

Keep housing-locator documentation in sync when planning or completing work.

## When to Update

| Scenario | Files to Update |
|----------|-----------------|
| **Planning a phase** | `docs/implementation/CURRENT_PHASE.md`, possibly `ROADMAP.md` |
| **Completing a phase** | `CHANGELOG.md`, `docs/implementation/CURRENT_PHASE.md`, affected `CLAUDE.md` files |
| **Adding new source adapter / module / subsystem** | Create new `CLAUDE.md` in that directory |
| **Changing architecture** | `ARCHITECTURE.md`, relevant `CLAUDE.md` files |
| **Adding / changing a supported housing source** | `docs/sources/REFERENCE.md` (per-source notes: URL patterns, selectors/API endpoints, quirks, rate-limit behavior) |
| **Changing the ranking algorithm** | `docs/ranking/REFERENCE.md` and root `CLAUDE.md` (ranking factors are user-visible) |
| **Changing the config schema** | `config.example.md`/`config.example.yaml` (whichever the project uses) and root `CLAUDE.md` |

## Documentation Files

### Project-Level

| File | Purpose | Update When |
|------|---------|-------------|
| `CLAUDE.md` | Project overview, critical rules, quick reference | Major architectural changes, new commands, new quality gates |
| `CHANGELOG.md` | Version history, user-facing changes | Every completed phase |
| `ROADMAP.md` | Future plans, phase breakdown | Scope changes, new phases, trip itinerary changes |
| `README.md` | Public-facing overview | Major feature additions |
| `ARCHITECTURE.md` | System design, data flow | Architectural changes |

### Implementation Docs

| File | Purpose |
|------|---------|
| `docs/implementation/CURRENT_PHASE.md` | Active phase details, tasks, progress |
| `docs/features/<feature>/SPEC.md` | Per-feature spec from `/spec` |
| `docs/features/<feature>/PHASES.md` | Per-feature phase breakdown from `/spec-phases` |
| `docs/research/` | Saved Gemini research outputs (see global CLAUDE.md) |

### Domain-Specific CLAUDE.md Files

The exact layout depends on the architecture chosen during `/spec` research. Typical candidates once the project has code:

| File | Domain |
|------|--------|
| `src/sources/CLAUDE.md` | Per-source adapter patterns, selector drift handling, rate-limit behavior |
| `src/ranking/CLAUDE.md` | Ranking factors, weights, scoring function |
| `src/config/CLAUDE.md` | Config schema, validation, defaults |
| `src/output/CLAUDE.md` | Output format (markdown/spreadsheet/email) generation |
| `src/lib/CLAUDE.md` | Shared normalization, date/currency, geocoding helpers |

Add or remove rows as the actual directory structure solidifies.

## Phase Planning Checklist

When planning a new phase:

- [ ] Update `docs/implementation/CURRENT_PHASE.md` with:
  - Phase number and title
  - Objectives
  - Tasks with acceptance criteria
  - Dependencies and risks
- [ ] Check if `ROADMAP.md` needs scope adjustments (e.g., new destination added to the trip, new source in scope)
- [ ] Identify which `CLAUDE.md` files will be affected

## Phase Completion Checklist

When completing a phase:

- [ ] Update `CHANGELOG.md` with user-facing changes
- [ ] Update `docs/implementation/CURRENT_PHASE.md`:
  - Mark tasks complete
  - Note any deferred items
  - Update "Next Phase" section
- [ ] Update affected `CLAUDE.md` files:
  - New source adapters / modules / subsystems
  - Changed schemas, interfaces, or output formats
  - New gotchas or critical rules (e.g., a site that bans automation, a source whose data must not be trusted for occupancy count)
- [ ] **Create new `CLAUDE.md`** if you added a new directory with 3+ files or a new domain
- [ ] If a source's scraping behavior changed (new selector, new endpoint, new captcha workaround): update `docs/sources/REFERENCE.md`
- [ ] If ranking factors changed: update `docs/ranking/REFERENCE.md` and root `CLAUDE.md`

## CHANGELOG Format

```markdown
## [Unreleased]

### Added
- Feature description

### Changed
- Change description

### Fixed
- Bug fix description
```

## When to Create a New CLAUDE.md

Create a new `CLAUDE.md` when:

- [ ] Adding a new directory with 3+ related files
- [ ] Creating a new feature domain (source adapters, ranking, output, config)
- [ ] Building a subsystem with non-obvious patterns or invariants (e.g., anti-scraping workarounds, currency/timezone handling)
- [ ] Code has gotchas that took time to figure out

**Location:** Place in the directory root, e.g., `src/sources/trustedhousesitters/CLAUDE.md`

## CLAUDE.md Template

Match the existing pattern — lean but informative:

```markdown
# src/path/to/dir/CLAUDE.md - Feature Name

## Overview

One paragraph explaining the domain's purpose and scope.

## Directory Structure (if >3 files)

| File | Purpose |
|------|---------|
| `fileA.ts` | Brief description |
| `fileB.ts` | Brief description |
| `types.ts` | Shared types |

## Key Types (if applicable)

| Type | Purpose |
|------|---------|
| `FooConfig` | Configuration for X |
| `BarState` | Runtime state for Y |

## Responsibilities

- **Module A** — What it does, what it exports
- **Module B** — What it does, its inputs/outputs

## Integration Points

How this connects to other parts of the system:
- What it reads from config
- What it writes to the output pipeline
- What it depends on from `src/lib/`

## Key Invariants

- Critical rules that must not be broken
- Patterns that prevent bugs
- Non-obvious constraints (e.g., "never log the raw HTML — it may contain PII from listing photos")

## Gotchas

- Things that took time to figure out
- Edge cases to watch for
- Common mistakes to avoid (e.g., "this site returns 200 with an empty body when rate-limited — check body length, not status")

## Test Coverage (if tests exist)

Key test patterns used. Keep specific counts out — they go stale.
```

## CLAUDE.md Update Guidelines

1. **Keep it scannable** — Use tables, bullet points, code blocks
2. **Document gotchas** — Things that took time to figure out
3. **Include file paths** — Help future Claude find relevant code
4. **Don't duplicate** — Reference other CLAUDE.md files instead
5. **Semantic meaning** — Explain *why*, not just *what*
6. **Integration points** — How does this connect to config, ranking, output, other sources?
7. **Avoid volatile info** — Don't embed test counts, exact line numbers, or specific version strings that rot quickly

## Quick Commands

```bash
# Find all CLAUDE.md files
find . -name "CLAUDE.md" -not -path "./.worktrees/*" -not -path "./node_modules/*"

# Check what changed since last commit
git diff --name-only HEAD~1
```

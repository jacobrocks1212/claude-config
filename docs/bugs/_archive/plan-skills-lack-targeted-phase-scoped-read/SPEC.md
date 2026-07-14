# Plan skills lack targeted-phase scoped reads — Investigation Spec

> The `/write-plan` family plans ALL phases and reads PHASES.md in full even when the operator targets a single phase; the deterministic scoped reader (`phases-slice.py`) is never reached on the authoring path.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-10
**Fixed:** 2026-07-14
**Fix commit:** 8fc345dd
**Placement:** docs/bugs/plan-skills-lack-targeted-phase-scoped-read
**Related:** `docs/features/phases-slice-scoped-reads/` (the completed feature that shipped `phases-slice.py` + the script-first `source-reread.md`, scoped to execution-time readers only); `user/skills/_components/source-reread.md` (the scoped-read mandate carrier)

<!-- Status lifecycle: Investigating → Concluded (root cause traced) → Fixed (edits landed on main). -->

---

## Verified Symptoms

1. **[VERIFIED]** Invoking `/write-plan-cognito <path>/PHASES.md phase 9` reads the entire 715-line PHASES.md rather than slicing to phase 9 — confirmed by the operator (screenshot of the run + selection "Add phase-targeting to plan skills"). The trailing `phase 9` token is silently ignored; the skill plans every unchecked phase.
2. **[VERIFIED — by-design boundary]** Full PHASES.md reads in authoring skills are **correct when NOT targeting a subset** — the operator confirmed cross-phase context legitimately needs the whole file ("By-design — keep"). The defect is scoped to the *targeted* invocation, not authoring full-reads in general.

## Reproduction Steps

1. In a Cognito Forms worktree, invoke: `/write-plan-cognito C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/57077-cognito-pay-account-deletion/PHASES.md phase 9`
2. Observe the skill's Step 1 context load: it issues a `Read` of the full PHASES.md (715 lines).
3. Observe Step 2: it scans and plans **all** phases with unchecked deliverables, not just phase 9.

**Expected:** When a phase is explicitly targeted, the skill slices to that phase (+ its Implementation Notes) via `python ~/.claude/scripts/phases-slice.py <PHASES.md> --phase 9 --notes all` and plans only that phase.
**Actual:** The phase token is unparsed; the skill reads the full file and plans every unchecked phase.
**Consistency:** Always — deterministic from the skill prose.

## Evidence Collected

### Source Code (skill prose)

The `/write-plan` family has **no phase-selector in argument parsing** and Step 1b unconditionally reads full:

- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md`
  - `:2` description: "…implementation plan for **ALL phases** across 1+ PHASES.md files"
  - `:3` argument-hint: `<path/to/PHASES1.md> [path/to/PHASES2.md] [...]` — **no phase token**
  - `:61-64` Step 1a "Resolve PHASES.md Paths": "`$ARGUMENTS` must contain 1+ `.md` paths" — only `.md` tokens are recognized; `phase 9` is dropped
  - `:68-69` Step 1b: "For **each** PHASES.md: 1. Read the PHASES.md file **in full**" ← the 715-line read
  - `:91` Step 2: "Scan all loaded PHASES.md files. For each phase with unchecked deliverables" ← plans ALL phases
- `user/skills/write-plan/SKILL.md`
  - `:70` Step 1a: "`$ARGUMENTS` must contain 1+ `.md` paths"
  - `:76` Step 1b: "Read the PHASES.md file **in full**"
- `user/skills/write-plan-cloud/SKILL.md`
  - `:43` Step 1a: "`$ARGUMENTS` must contain 1+ `.md` paths"
  - `:48` Step 1b: "read it **in full**, identify which phases/deliverables this plan covers (the unchecked `- [ ]` items **unless the user scoped a subset**)" — acknowledges subset scoping in prose but has **no mechanism** to parse or honor it

### Related Documentation

- `docs/features/phases-slice-scoped-reads/SPEC.md` (Status: Complete, P1). Its LD3 + "What Shipped" table wired the scoped reader into exactly three sites: `source-reread.md`, `execute-plan/SKILL.md`, and the Cognito lane contract `execution-contract-cognito-lanes.md`. It **deliberately did not target the authoring/plan skills** — so this is uncovered surface, not a regression of that feature.
- `user/skills/_components/source-reread.md:9-18` — the canonical scoped-read command (`phases-slice.py <PHASES.md> --phase <id> --no-preamble`, `--notes <id>|all` to append Implementation-Notes sections). Consumed by execution-time readers only.

### Architectural split (confirming the by-design boundary)

| Category | Skills | Read strategy |
|---|---|---|
| Execution-time | `execute-plan`, `implement-phase*` (Step B.0), `fix*` | Scoped via `phases-slice.py` (through `source-reread.md`) — correct |
| Authoring-time | `write-plan`, `write-plan-cloud`, `write-plan-cognito`, `add-phase`, `spec-phases`, `realign-spec`, `retro`, `write-manual-testing-doc` | Full file — **correct when planning all phases; defective only when a subset is targeted** |

## Theories

### Theory 1: Plan family has no targeted-phase mode — **CONFIRMED**
- **Hypothesis:** The `/write-plan*` skills recognize only PHASES.md path tokens and unconditionally read/plan the full file, so a targeted-phase invocation (`… phase 9`) is silently ignored and pays a full-file read.
- **Supporting evidence:** The cited Step 1a argument-resolution + Step 1b full-read lines in all three skills; `write-plan-cognito`'s own "ALL phases" contract; the operator-confirmed symptom.
- **Contradicting evidence:** None. `write-plan-cloud` even names "unless the user scoped a subset" but provides no parsing/branch to act on it.
- **Status:** Confirmed.

## Proven Findings

**Cause (label: `traced`).** The `/write-plan` family (`write-plan`, `write-plan-cloud`, `write-plan-cognito`) has no phase-selector token in its Step 1a argument resolution, and Step 1b reads PHASES.md in full with no conditional branch. The serving path from the reported symptom to the fix site:

```
/write-plan-cognito <PHASES.md> phase 9
  → Step 1a resolve args     write-plan-cognito/SKILL.md:61-64   (only .md tokens parsed; "phase 9" dropped)
  → Step 1b full read        write-plan-cognito/SKILL.md:68-69   (715-line Read)          ← FIX SITE (read branch)
  → Step 2 phase scan        write-plan-cognito/SKILL.md:91      (plans ALL unchecked phases) ← FIX SITE (scope branch)
```

The fix site (Step 1a phase-token parsing + a conditional scoped read at Step 1b + Step-2 scope narrowing) lies **on** the traced serving path. Not runtime-coupled — the behavior is fully determined by the skill prose and verifiable by reading it.

**Fix shape (for `/plan-bug`):** Add an optional phase-selector token (e.g. `phase <id>` / `--phase <id>`) to the Step 1a argument resolution of the three plan skills. When present, replace the Step 1b full `Read` with `python ~/.claude/scripts/phases-slice.py <PHASES.md> --phase <id> --notes all` and narrow Step 2's phase scan to the targeted id. When **absent**, behavior is byte-identical to today (full read, plan all phases) — preserving the operator-confirmed by-design authoring path. Mirror the argument-hint/description to document the new mode.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Plan (Cognito) | `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md` (Step 1a `:61-64`, Step 1b `:68-69`, Step 2 `:91`, argument-hint `:3`) | Reported surface; full read + all-phase plan on a targeted invocation |
| Plan (generic) | `user/skills/write-plan/SKILL.md` (Step 1a `:70`, Step 1b `:76`) | Same defect shape |
| Plan (cloud) | `user/skills/write-plan-cloud/SKILL.md` (Step 1a `:43`, Step 1b `:48`) | Same defect shape; prose already gestures at subset scoping with no mechanism |

## Open Questions

- **Selector syntax** — `phase <id>` (as invoked) vs `--phase <id>` (flag). `/plan-bug` should pick one and apply it uniformly across the three skills. Repeatable for a phase range?
- **`--batch` interaction** — should the autonomous path (`/plan-feature` → `/write-plan --batch`) ever pass a phase selector, or is targeting strictly an interactive-operator convenience? (Current lean: interactive-only; batch keeps planning all unchecked phases.)

## Resolution

**Status:** Fixed (edits landed on `main`; verified via projection + lint + doc-drift gates). Implemented directly from the Concluded SPEC's "Fix shape" — the bug was not in `docs/bugs/queue.json` (filed directly via `/spec-bug`, no PHASES/plan), so a formal `bug-state.py __mark_fixed__` receipt gate does not apply. Left in place with `Status: Fixed` per the established convention for non-adhoc harness bugs (e.g. `build-queue-eta-marker-mojibake-on-redirected-stdout`, the `pr-review-*` set); `docs/bugs/_archive/` holds older adhoc pipeline spin-offs, not directly-filed bugs.

Added an OPTIONAL, repeatable, interactive-only phase selector (`--phase <id>` and/or bare `phase <id>`) to all three plan skills. When present (and NOT `--batch`), the skill slices PHASES.md via `phases-slice.py … --phase <id> --notes all` and narrows the phase scan to the targeted id(s); when absent, behavior is byte-identical to before (full read, plan all unchecked phases). The `--batch` path always ignores the selector.

**Resolved decisions applied:** (1) selector syntax = both `--phase <id>` flag AND bare `phase <id>`, repeatable (matching `phases-slice.py`'s `action="append"`); (2) `--batch` ignores the selector (interactive-only); (3) no selector ⇒ byte-identical to today.

**Edits (file:line, per the traced fix sites):**

- `user/skills/write-plan/SKILL.md`
  - Frontmatter `description`/`argument-hint` (`:2-3`) — document the optional `[--phase <id> ...]` mode.
  - Batch Mode section (`:34`) — added the "phase selector is IGNORED under `--batch`" clause.
  - Step 1a "Resolve PHASES.md Paths (+ optional phase selector)" (`~:70`) — parse + strip the repeatable selector into `TARGET_PHASES` before path resolution; empty under `--batch`.
  - Step 1b "Read Everything" (`~:76`) — conditional scoped read via `phases-slice.py --phase <id> --notes all` (script-unavailable fallback: `grep -n '^#\{2,3\} Phase'` + bounded Read); full read unchanged when no selector.
  - Step 1c "Build the Cross-Feature Phase Queue" (`~:103`) — restrict the unchecked-phase scan to `TARGET_PHASES` when non-empty.
- `user/skills/write-plan-cloud/SKILL.md`
  - Frontmatter `description`/`argument-hint` (`:3-4`).
  - Step 1a (`~:43`) — same selector parse/strip.
  - Step 1b "Read ONLY the PHASES.md spine yourself" (`~:48`) — phase-targeted scoped read narrows the plan to the targeted phases' unchecked deliverables (feeding Step 1d/Step 2's in-scope work queue); default full read unchanged. Replaced the prior mechanism-less "unless the user scoped a subset" gesture.
- `repos/cognito-forms/.claude/skills/write-plan-cognito/SKILL.md`
  - Frontmatter `description`/`argument-hint` (`:2-3`).
  - Batch Mode section (`:31`) — "phase selector is IGNORED under `--batch`" clause.
  - Step 1a (`~:63`) — selector parse/strip.
  - Step 1b "Read Everything" (`~:68`) — conditional scoped read; full read unchanged.
  - Step 1c phase scan (`~:91`) — restrict to `TARGET_PHASES` when non-empty.

The execution-side Cognito lane contract (`execution-contract-cognito-lanes.md`) was intentionally left untouched — it already reads scoped via `source-reread.md`; only the authoring path changed.

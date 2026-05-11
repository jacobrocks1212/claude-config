---
name: lazy-status
description: Read-only progress dashboard — shows current feature state, queue progress, and next /lazy action
model: haiku
---

# Lazy Status

Read-only dashboard for mobile development workflow. Reports current feature progress without executing anything.

---

## Step 1: Load Queue

Read `docs/features/queue.json` from the project root. Extract the `queue` array.

If the file doesn't exist, report: "queue.json not found — run /lazy setup first" and STOP.

---

## Step 2: Determine Completed Features

Read `docs/features/ROADMAP.md`. A feature is complete if its ROADMAP row contains `~~` (strikethrough) AND the word `COMPLETE`.

Count how many queue items are complete by matching each `queue[].name` against ROADMAP strikethrough rows.

---

## Step 3: Find Current Feature

Iterate the queue array in order. The first feature whose name does NOT match a completed ROADMAP row is the current feature.

If all features are complete, report: "ALL FEATURES COMPLETE — nothing left in queue" and STOP.

---

## Step 4: Detect Current State

For the current feature, resolve `spec_path = docs/features/{spec_dir}` (spec_dir from queue.json).

Check filesystem state in this order (first match wins):

| Check | State | Next /lazy Action |
|-------|-------|-------------------|
| `{spec_path}/BLOCKED.md` exists | blocked | present blocker + await input |
| `{spec_path}/SPEC.md` missing | needs spec | /spec |
| SPEC.md exists but no `RESEARCH_SUMMARY.md` | needs research | /spec (research) |
| `{spec_path}/PHASES.md` missing | needs phases | /spec-phases |
| PHASES.md has `- [ ]` unchecked items AND no plan in `plans/` or root `PLAN.md` | needs plan | /write-plan |
| PHASES.md has `- [ ]` unchecked items AND plan exists (in `plans/` or root `PLAN.md`) | implementing | /execute-plan |
| All deliverables checked AND no `VALIDATED.md` | needs validation | /mcp-test |
| `VALIDATED.md` exists AND no retro plan in `plans/retro-*` | needs retro | /retro --auto |
| `VALIDATED.md` exists AND retro plan exists AND no `RETRO_DONE.md` | retro executing | /execute-plan (retro) |
| `VALIDATED.md` exists AND `RETRO_DONE.md` exists | ready to mark complete | mark complete |

To count phases and determine current phase number:
- Count `### Phase` headings in PHASES.md → total phases
- For each phase section, check if ALL its `- [x]` deliverables are checked → phase is complete
- Current phase = first phase with any `- [ ]` unchecked deliverable

---

## Step 5: Gather Additional Context

Run these in parallel:
1. `git log --oneline -1` → last commit
2. Check if `{spec_path}/mcp-tests/` directory exists and count symlinks in it
3. If BLOCKED.md exists, read first 5 lines for blocker summary

---

## Step 6: Format and Output

Output this exact format (fill in values):

```
## AlgoBooth Progress

**Current:** {feature name} (Phase {current}/{total} — {state})
**Tier:** {tier} — {tier name}
**Queue:** {completed}/{total queue length} features complete ({remaining} remaining)
**Last commit:** {short hash} "{commit message}"
**Blockers:** {None | first line of BLOCKED.md details}
**MCP Tests:** {count} scenarios linked | Not yet created | Skipped (see SKIP_MCP_TEST.md)
**Next /lazy action:** {the action from the table above}
```

Tier names: 1=High-Compound-Value, 2=Synthesis & Expression, 3=Track Ecosystem, 4=DJ Performance, 5=Long Tail, non-audio=Non-Audio

Do NOT execute any skills or modify any files. Report only.

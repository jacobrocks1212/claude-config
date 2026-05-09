## Plan Mode Gate (MANDATORY — DO NOT SKIP)

Determine whether this skill requires plan mode before proceeding.

### Decision Logic

1. **Check this skill's frontmatter** for a `plan-mode` field:
   - `plan-mode: required` → Enter plan mode unconditionally. Proceed to step 2.
   - `plan-mode: flag` → Check `$ARGUMENTS` for `--plan`. If present, strip `--plan` from arguments (so downstream steps don't see it) and proceed to step 2. If `--plan` is absent, **skip this gate entirely** — do not enter plan mode.
   - Field absent or any other value → **Skip this gate entirely.**

2. **Enter plan mode:** If not already in plan mode, call `EnterPlanMode` now. All subsequent work in this skill must be drafted as a plan for user approval. Call `ExitPlanMode` when the plan is complete and ready for review.

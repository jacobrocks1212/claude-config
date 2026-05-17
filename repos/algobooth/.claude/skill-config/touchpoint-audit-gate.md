## Touchpoint Audit Gate (MANDATORY — BEFORE DRAFTING PLAN)

For each PHASES.md or work-unit the plan will modify, collect the target
file paths. Paths must be **relative to the AlgoBooth repo root** (the
cwd when npm runs).

```bash
npm run audit:touchpoints -- --json <path1> <path2> ... > /tmp/touchpoint-audit.json
```

Parse the output. Identify all entries where `verdict.kind === "block"`.

**If any verdict is `block`:**

1. Read the `recommendation` field for each blocked file.
2. The plan **MUST** include a **"Phase 0: Decomposition"** entry BEFORE
   the phases that touch blocked files. Document:
   - Which files are being decomposed
   - The decomposition strategy (from `recommendation`: `split-first`,
     `decompose-store`, etc.)
   - Which subsequent phase picks up the original work after decomposition
3. OR — if decomposition is genuinely out of scope (e.g., the user
   explicitly wants a hotfix that must touch `voice.rs`), surface the
   block report to the user via `AskUserQuestion` with the following
   options:
   - **Add a decomposition phase** (recommended — preserves long-term health)
   - **Acknowledge and proceed without** (records the decision as a
     deliberate exception in a §Plan Notes section at the bottom of
     the plan)

**If no verdict is `block`:**

Continue to plan drafting. Warn verdicts are informational — note them
in a §Touchpoint Summary table at the top of the plan so the implementer
is aware.

**When to skip:** pure documentation changes (no source files modified),
or plans that touch only brand-new files (no existing LOC to grow).
Note the skip reason in the plan.

**Heuristic note:** the audit is regex-based, not AST. Some `block`
verdicts may be conservative. The `AskUserQuestion` branch above covers
the case where the human disagrees with the block. Document any
overrides explicitly in §Plan Notes so the decision is auditable.

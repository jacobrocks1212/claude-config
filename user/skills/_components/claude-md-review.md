## CLAUDE.md Updates (rare — only durable structural knowledge)

**Most implementation work warrants no CLAUDE.md / CLAUDE.local.md update.** Producing nothing
here is the normal, unremarkable outcome — not a skip. The burden of proof is on writing, not on
abstaining: default to "No CLAUDE.md updates required," state that, and move on. Only write when a
piece of knowledge affirmatively passes the bar below.

Still, briefly consider whether this work surfaced durable structural knowledge worth capturing:

- **Project root CLAUDE.md / CLAUDE.local.md** — new architecture patterns, commands, critical
  rules, gotchas
- **Subdirectory CLAUDE.md / CLAUDE.local.md files** — new modules, changed APIs/conventions, new
  gotchas. A directory-level file is the right home for things a fresh agent can't infer from
  filenames (coupled-pair sync rules, "edit here not there", fail-OPEN guards, file contracts)
- **docs/CLAUDE.md** — if doc structure changed

### The bar (must pass ALL of this before writing anything)

**Generalization test** — every candidate update must pass all four questions:

| Question | If NO → | If YES → |
|----------|---------|----------|
| Would this prevent at least 3 different specific mistakes? | Drop it — over-fitted to one incident | Proceed |
| Would a reader understand this without knowing what produced it? | Rewrite to remove incident-specific language | Proceed |
| Does this duplicate what the target file already handles? | Drop it — the existing rule wasn't followed, not missing | Proceed |
| Is this so broad it would false-positive in normal work? | Narrow the scope or add a qualifying condition | Proceed |

**Durability checklist** — every candidate update must also satisfy all of:
- No references to specific phases, batches, or implementation steps (e.g., "Phase 4", "Batch 2")
- No references to specific features or tasks by name unless permanently relevant to the codebase
- No "just added" / "recently changed" language — this rots immediately
- Still useful to a reader 6 months from now with no context about this session
- Captures a general pattern or invariant, not a one-time incident

If a candidate fails either gate, don't write it. If the changes clearly warrant a NEW CLAUDE.md /
CLAUDE.local.md (a new subdirectory with meaningful conventions, or a non-obvious gotcha that just
passed the bar above), create it.

Rules for what does get written:
- **Lean and durable only** — structure, conventions, gotchas. Anchor a gotcha to its concrete
  failure (the error text, the burned feature), not abstract advice.
- Do NOT add volatile info (test counts, line numbers, version strings, dates that will rot).

<!-- parity: the generalization test + durability checklist above are an aligned copy of /retro's
     (user/skills/retro/SKILL.md, "Generalization rule (MANDATORY)" + "### CLAUDE.md Updates").
     Editing one should prompt a check of the other. -->

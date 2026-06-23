## Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

This is a post-implementation gate, not a nicety: durable structural knowledge that isn't written
down gets re-derived by the next agent every cycle. Review whether this work warrants CLAUDE.md updates:

- **Project root CLAUDE.md** — new architecture patterns, commands, critical rules, gotchas
- **Subdirectory CLAUDE.md files** — new modules, changed APIs/conventions, new gotchas. A
  directory-level CLAUDE.md is the right home for the things a fresh agent can't infer from the
  filenames (coupled-pair sync rules, "edit here not there", fail-OPEN guards, file contracts).
- **docs/CLAUDE.md** — if doc structure changed

If the changes warrant a NEW CLAUDE.md (a new subdirectory with meaningful conventions, or a
non-obvious gotcha you just hit), create it.

Rules:
- **Lean and durable only** — structure, conventions, gotchas. Anchor a gotcha to its concrete
  failure (the error text, the burned feature), not abstract advice.
- Do NOT add volatile info (test counts, line numbers, version strings, dates that will rot).
- If no updates are needed, explicitly state "No CLAUDE.md updates required" and move on.

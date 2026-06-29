## Re-read Source Documents (MANDATORY — DO NOT SKIP)

Before launching any subagent in this batch, the orchestrating agent must re-read from disk:

1. **The current phase's section in PHASES.md** (deliverables, prerequisites, testing strategy, integration notes) — the file may have been updated by prior batches in this same phase. **Read only the current-phase SLICE, not the whole file** — see "PHASES.md slice read" below.
2. **All prior phases' Implementation Notes** in the same PHASES.md (patterns, imports, gotchas, actual file paths that may differ from the plan)
3. **The relevant sections of SPEC.md** that this phase implements (as listed in the per-phase plan's "SPEC.md references" field)

### PHASES.md slice read (read the current-phase slice + a compact index — never the whole file)

PHASES.md no longer carries the (monotonically growing) Implementation Notes — those live in a sibling `IMPLEMENTATION_NOTES.md`. PHASES.md is now a thin checklist, but it still grows one phase section per phase, and re-reading it in full at every batch boundary and on every compaction recovery is wasteful. So scope the read:

- **Phase-boundary marker (settled — OQ2):** phase sections are delimited by a level-2-or-3 Markdown heading whose text begins with `Phase` followed by an identifier — i.e. lines matching `^#{2,3}\s+Phase\s+<id>` (e.g. `## Phase 3 — Thin PHASES.md …`). This is the SAME canonical marker `lazy_core.parse_phases()` keys off (`_PHASE_HEADING_RE`); slice readers MUST reuse it rather than inventing a new delimiter.
- **Read the current-phase slice only.** Locate the `^#{2,3}\s+Phase N` heading for the phase being executed and read from that line up to (but not including) the next `^#{2,3}\s+Phase` heading (or EOF). Use `Read`'s `offset`/`limit` (or `grep -n '^#\{2,3\} Phase' PHASES.md` to find the boundary line numbers first, then an offset/limit read) — do NOT read the file whole.
- **Plus a compact completed-phases index.** Read only the small header region of PHASES.md (the top `## Touchpoint`/`**Status:**` preamble and the list of `## Phase N — <title>` heading lines with their `**Status:**`) so you know which prior phases are Complete — NOT their bodies. A `grep -n '^#\{2,3\} Phase\|^\*\*Status:\*\*'` over PHASES.md gives this index cheaply.
- **Do not load prior phases' bodies or notes by default.** If you need a specific prior phase's detail, slice-read that one phase section on demand. Prior-phase Implementation Notes (item 2 above) live in the sibling `IMPLEMENTATION_NOTES.md`; read them from there when needed.

This re-read is required because the context window may have been compacted since the plan was drafted. The orchestrating agent must have fresh, accurate content before composing subagent prompts.

**Do NOT rely on cached/remembered content — read the files.**

4. **The plan file** (if this is an `/implement-phase-batch` execution) — re-read the current phase's section from the plan file at `~/.claude-personal/plans/`. After compaction, your awareness of the plan's execution model, mandatory rules, and batch structure may be stale. If you cannot recall which batch you're on or what the plan's constraints are, re-read the full plan header + current phase section.

## Re-read Source Documents (MANDATORY — DO NOT SKIP)

Before launching any subagent in this batch, the orchestrating agent must re-read from disk:

1. **The current phase's section in PHASES.md** (deliverables, prerequisites, testing strategy, integration notes) — the file may have been updated by prior batches in this same phase. **Read only the current-phase SLICE, not the whole file** — see "PHASES.md slice read" below.
2. **Prior phases' Implementation Notes** — read from the sibling `IMPLEMENTATION_NOTES.md` when present (sibling-then-embedded order; see "Prior Implementation Notes read" below), falling back to embedded notes in PHASES.md for in-flight features predating the D3 writer flip. These contain patterns, imports, gotchas, and actual file paths that may differ from the plan — this read is what stops a later work unit from repeating a hiccup an earlier one already hit and documented.
3. **The SPEC content this phase implements.** If the plan carries a per-phase `SPEC excerpts` block (v3 pointer-based plans), those verbatim excerpts ARE the working SPEC content for the batch — do NOT read SPEC.md in full. Escalate to an on-disk SPEC.md read ONLY when an excerpt is ambiguous, contradicts observed code, or a lane needs context the excerpt doesn't carry — and then read just the named section, not the whole file (note the escalation + reason in the phase's Implementation Notes so the planner can fix the excerpt next time). Plans without excerpts (v2 and earlier): read the sections listed in the per-phase "SPEC.md references" field.

### PHASES.md slice read (SCRIPT-OWNED — run `phases-slice.py`, never read the whole file)

PHASES.md no longer carries the (monotonically growing) Implementation Notes — those live in a sibling `IMPLEMENTATION_NOTES.md`. PHASES.md is a thin checklist, but it still grows one phase section per phase; re-reading it whole at every batch boundary and compaction recovery is the documented context-plateau cost, and the earlier grep-then-ranged-Read prose choreography was measurably ignored in the field. The scoped read is therefore **one deterministic command**:

```bash
python ~/.claude/scripts/phases-slice.py <path/to/PHASES.md> --phase <id> --no-preamble
```

- Prints the phase index (every phase's heading, line range, `**Status:**`, checkbox tally) + the FULL slice of the requested phase, and — when a sibling `IMPLEMENTATION_NOTES.md` exists — its per-phase section index. Omit `--phase` to auto-select the active phase (first with an unchecked deliverable); include the preamble (drop `--no-preamble`) on the FIRST read of a run only. `--checklist` prints just a phase's checkbox lines (the cloud-saturation / completion-audit view); `--notes <id>`/`--notes all` appends Implementation-Notes sections.
- Phase boundaries are the canonical `^#{2,3}\s+Phase <id>` marker (`lazy_core._PHASE_HEADING_RE`) — the script reuses it; never invent a new delimiter or re-derive slices by hand. If the script is unavailable (exit 1 on a machine without it), fall back to `grep -n '^#\{2,3\} Phase' PHASES.md` + a bounded offset/limit `Read` of the current phase only.
- **Do not load prior phases' bodies or notes by default.** Slice a specific prior phase (`--phase <id>`) or notes section (`--notes <id>`) on demand.

This re-read is required because the context window may have been compacted since the plan was drafted. The orchestrating agent must have fresh, accurate content before composing subagent prompts.

**Do NOT rely on cached/remembered content — read the files.**

### Prior Implementation Notes read (sibling-then-embedded)

Prior-phase Implementation Notes live in the sibling `IMPLEMENTATION_NOTES.md` (since the D3 writer flip in plan-skills-redesign Phase 3); PHASES.md is now a thin checklist. Apply the canonical sibling-then-embedded read order for item 2 above:

- **Sibling-first.** Look for `<dir-of-PHASES.md>/IMPLEMENTATION_NOTES.md`. If it exists and contains at least one heading block matching `^#{2,4}\s+(Implementation Notes|Phase\s+\S)`, read prior-phase notes sections from it.
- **Embedded fallback.** If the sibling is absent or a bare placeholder (preamble only, no notes content), read `## Implementation Notes` blocks from PHASES.md itself. These carry valid notes for features whose notes predate the flip.
- **A bare scaffold does not count as evidence.** A sibling file with only a title/preamble and no content headings falls through to the embedded fallback — do not treat a placeholder as presence.

See `~/.claude/skills/_components/implementation-notes-read-order.md` for the full canonical rule (used by all consumer skills).

4. **The plan file** (if this is an `/implement-phase-batch` execution) — re-read the current phase's section from the plan file at `~/.claude-personal/plans/`. After compaction, your awareness of the plan's execution model, mandatory rules, and batch structure may be stale. If you cannot recall which batch you're on or what the plan's constraints are, re-read the full plan header + current phase section.

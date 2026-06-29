## Implementation Notes read order (sibling-then-embedded)

When reading prior-phase Implementation Notes, use this canonical order:

1. **Sibling-first.** Look for a sibling `IMPLEMENTATION_NOTES.md` adjacent to the PHASES.md being processed (path: `<dir-of-PHASES.md>/IMPLEMENTATION_NOTES.md`). If it exists AND contains at least one `## Phase N — …` or `#### Implementation Notes` heading block, read per-phase sections from it. A bare scaffold file (only a title/preamble, no notes content) does NOT count — fall through to step 2.
2. **Embedded fallback.** If the sibling is absent or is a bare placeholder, read `## Implementation Notes` blocks embedded inside PHASES.md itself (legacy pre-D3 location). These still carry valid notes for in-flight features whose notes predate the D3 writer flip.

**Why sibling-first:** the shared `phases-update.md` writer (since the D3 writer flip in plan-skills-redesign Phase 3) appends all new notes to `IMPLEMENTATION_NOTES.md`, not to PHASES.md. PHASES.md is now a thin checklist. Features that began before the flip still have embedded notes in PHASES.md; the embedded fallback ensures they are not silently lost.

**Evidence threshold for the sibling:** the file must match `^#{2,4}\s+(Implementation Notes|Phase\s+\S)` on at least one line — i.e. it contains a per-phase notes section or an `#### Implementation Notes (Phase N)` block, not just a preamble. This is the same threshold the harness `_sibling_impl_notes_present()` helper uses (`_SIBLING_IMPL_NOTES_HEADING_RE = re.compile(r'^#{2,4}\s+Implementation Notes\b', re.MULTILINE)`).

**Practical read steps:**
- Check whether `IMPLEMENTATION_NOTES.md` exists alongside PHASES.md.
- If yes, scan it for heading lines matching the above pattern.
- If found: read the relevant per-phase section(s) from `IMPLEMENTATION_NOTES.md`.
- If absent or no content headings: read `## Implementation Notes` from PHASES.md.

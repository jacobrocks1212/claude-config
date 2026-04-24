# Analyze Edits: $ARGUMENTS

> **Note:** The `/save` command now incorporates this analysis automatically. Use this standalone skill only when you want to analyze an existing scene file without modifying it (e.g., reviewing older scenes for patterns).

You are analyzing user edits to a scene and generalizing patterns into reference documents.

## Argument Format

The argument should specify the scene file, e.g.:
- `1.1` — Chapter 1, Scene 1
- `1 scene 2` — Chapter 1, Scene 2
- `the-arrival scene 1` — Scene 1 of "The Arrival"

## Your Task

1. **Load the Edited Scene** — Read the scene file:
   - `Chapters/[chapter]/scenes/scene-[N].md`

2. **Load Reference Docs** — Read current reference documents:
   - `Docs/writing-rules.md` — Current writing guidelines
   - `Docs/used-phrases.md` — Phrases already used (to check for new additions)
   - `Characters/jake.md` — Jake's character sheet
   - `Characters/josh.md` — Josh's character sheet (if he appears)
   - `Characters/sadie.md` — Sadie's character sheet (if she appears)
   - `Characters/georgia.md` — Georgia's character sheet (if she appears)

3. **Analyze the Edits** — Look for patterns that should be generalized:
   - **Dialogue style** — Tighter phrasing, specific word choices, speech patterns
   - **Character voice** — New verbal tics, tone adjustments, personality traits
   - **Show vs. tell** — Places where exposition was cut or replaced with action
   - **Physical beats** — How dialogue is grounded in action
   - **Sensory details** — Specific details that work well
   - **Banter patterns** — How characters interact
   - **Brand usage** — Real brands vs. generic terms
   - **Typos or errors** — Flag any that need fixing

4. **Propose Reference Doc Updates** — For each pattern found:
   - Explain what you observed in the edit
   - Quote the specific before/after (if available) or the edited text
   - Propose the specific addition to the appropriate reference doc
   - Ask for approval before making changes

5. **Update Reference Docs** — Once approved:
   - Update `Docs/writing-rules.md` with new general rules
   - Update character sheets with voice/trait discoveries
   - Create new reference docs if needed (e.g., `Docs/dialogue-guide.md`)

6. **Update used-phrases.md** — Scan the scene for new trackable items:
   - Distinctive phrases or turns of phrase
   - New similes or metaphors
   - New eyebrow descriptions for Sadie
   - Character-specific dialogue patterns
   - Add to appropriate section with `Ch[N] Sc[N]` location tag

7. **Update Slash Commands** — If new reference docs are created:
   - Update `.claude/commands/write-scene.md` to include the new doc in Load Context
   - Update `.claude/commands/refine-chapter.md` to include the new doc in Load Context
   - Update any other relevant slash commands

## Output Format

Present findings in this structure:

```
## Edits Analysis: [Scene Name]

### Pattern 1: [Name]
**Observed:** [What you noticed]
**Example:** [Quote from the edited text]
**Proposed update:** [Which doc] — [Specific text to add]

### Pattern 2: [Name]
...

### Errors Found
- [Line X]: "[error]" should be "[correction]"

### Summary of Proposed Changes
- `Docs/writing-rules.md`: [brief description]
- `Characters/josh.md`: [brief description]
- [etc.]

Ready to apply these changes?
```

## Related Skills

- **`/save`** — Preferred for new scenes: writes to disk + runs this analysis automatically
- **`/show-dont-tell-sweep`** — If edits reveal a "show don't tell" pattern, sweep other scenes
- **`/prose-voice-aligner`** — If voice adjustments are recurring, check other scenes for drift

## Begin

Start by reading the specified scene file and the current reference docs, then analyze and present your findings.
